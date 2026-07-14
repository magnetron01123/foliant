"""Schmale Web-App (Starlette): Upload eines DDB-PDF -> gefüllter deutscher Bogen (AUFTRAG §6).

Eigenständige ASGI-App NEBEN dem MCP-Server (kein Eingriff in app/server.py, kein öffentliches
MCP-Token, keine Persistenz). Verarbeitung im Speicher (BytesIO), eine Konvertierung gleichzeitig
(Semaphore -> 429), Gesamt-Zeitlimit, `no-store`/`noindex`/strikte CSP. Fehlermeldungen deutsch,
ohne Stacktraces/Charakterdaten/Secrets (§6.3, §10).

Terminologie läuft in-process über `app.glossar` (read-only Glossar-DB-Pfad). Der Provider kommt
aus der .env (`ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL`); fehlt er, meldet nur `POST /bogen`
'Übersetzung momentan nicht verfügbar' - die App startet trotzdem.
"""
from __future__ import annotations

import asyncio
import re
import sqlite3
from pathlib import Path

import fitz
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.responses import HTMLResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from app.charakterbogen.ddb_pdf import DDBFormatFehler, extrahiere
from app.charakterbogen.de_bogen import rendere
from app.charakterbogen.uebersetzer import (
    ProviderNichtKonfiguriert, UebersetzungsFehler, provider_aus_env, uebersetze,
)

_HIER = Path(__file__).parent
_INDEX = (_HIER / "templates" / "index.html").read_text(encoding="utf-8")
_STATIC = _HIER / "static"

MAX_BYTES = 15 * 1024 * 1024        # §7.1: Standard 15 MB
MAX_SEITEN = 50
ZEITLIMIT_S = 90.0                  # klar unter dem Cloudflare-Origin-Timeout

# Öffentliche Fehlertexte (AUFTRAG §6.3) - keine Interna.
NICHT_PDF = "Bitte wähle eine PDF-Datei aus."
KEIN_DDB = "Kein unterstützter D&D-Beyond-Charakterbogen."
NICHT_SICHER = "Dieser PDF-Bogen kann nicht sicher verarbeitet werden."
UEBERSETZUNG_WEG = "Die Übersetzung ist momentan nicht verfügbar. Bitte versuche es später erneut."
PASST_NICHT = ("Der vollständige Inhalt passt nicht auf den offiziellen deutschen "
               "Charakterbogen. Es wurde keine unvollständige PDF erzeugt.")
KONVERTER_BELEGT = "Gerade wird bereits ein Charakterbogen verarbeitet. Bitte versuche es gleich noch einmal."

_HTML_HEADER = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": ("default-src 'none'; style-src 'self'; script-src 'self'; "
                                "img-src 'self' data:; form-action 'self'; base-uri 'none'"),
}


def _seite(fehler: str | None = None) -> str:
    if not fehler:
        return _INDEX
    banner = f'<p class="fehler">{fehler}</p>'
    return _INDEX.replace("</form>", banner + "</form>", 1)


def _sicherer_name(name: str) -> str:
    sauber = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip()).strip("_")
    return sauber or "charakterbogen"


# --- deterministische Konvertierung (läuft im Threadpool) --------------------

def _konvertiere(pdf_bytes: bytes, provider, glossar_pfad: str | None,
                 template_pfad: str | None) -> tuple[bytes, str]:
    charakter = extrahiere(pdf_bytes)                       # -> DDBFormatFehler bei Nicht-DDB
    con = sqlite3.connect(glossar_pfad or ":memory:")
    con.row_factory = sqlite3.Row
    try:
        uebersetze(charakter, con, provider)               # -> Provider-/Übersetzungsfehler
    finally:
        con.close()
    pdf = rendere(charakter, template_pfad=template_pfad)   # -> Überlauf hart? (Renderer entscheidet)
    return pdf, _sicherer_name(charakter.identitaet.name)


def _pruefe_sicher(pdf_bytes: bytes) -> str | None:
    """Struktur-/Sicherheitsprüfung vor dem Parsen (§7.1). Gibt einen Fehlertext oder None."""
    if len(pdf_bytes) > MAX_BYTES:
        return NICHT_SICHER
    if not pdf_bytes.startswith(b"%PDF"):
        return NICHT_PDF
    try:
        d = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return NICHT_PDF
    try:
        if d.needs_pass or d.is_encrypted or d.page_count > MAX_SEITEN:
            return NICHT_SICHER
    finally:
        d.close()
    return None


# --- App-Fabrik --------------------------------------------------------------

def erstelle_app(provider=None, glossar_pfad: str | None = None,
                 template_pfad: str | None = None) -> Starlette:
    """Baut die ASGI-App. Alle externen Abhängigkeiten sind injizierbar (Tests)."""
    sem = asyncio.Semaphore(1)

    async def index(request):
        return HTMLResponse(_seite(), headers=_HTML_HEADER)

    async def gesund(request):
        return PlainTextResponse("ok")

    async def bogen(request):
        if sem.locked():
            return HTMLResponse(_seite(KONVERTER_BELEGT), status_code=429, headers=_HTML_HEADER)
        async with sem:
            form = await request.form()
            datei = form.get("datei")
            if not isinstance(datei, UploadFile):
                return HTMLResponse(_seite(NICHT_PDF), status_code=400, headers=_HTML_HEADER)
            roh = await datei.read()

            fehler = _pruefe_sicher(roh)
            if fehler:
                code = 413 if fehler is NICHT_SICHER and len(roh) > MAX_BYTES else 400
                return HTMLResponse(_seite(fehler), status_code=code, headers=_HTML_HEADER)

            try:
                prov = provider if provider is not None else provider_aus_env()
            except ProviderNichtKonfiguriert:
                return HTMLResponse(_seite(UEBERSETZUNG_WEG), status_code=503, headers=_HTML_HEADER)

            try:
                pdf, name = await asyncio.wait_for(
                    run_in_threadpool(_konvertiere, roh, prov, glossar_pfad, template_pfad),
                    timeout=ZEITLIMIT_S)
            except DDBFormatFehler:
                return HTMLResponse(_seite(KEIN_DDB), status_code=422, headers=_HTML_HEADER)
            except (ProviderNichtKonfiguriert, UebersetzungsFehler):
                return HTMLResponse(_seite(UEBERSETZUNG_WEG), status_code=503, headers=_HTML_HEADER)
            except (asyncio.TimeoutError, Exception):  # noqa: B014 - nichts leaken
                return HTMLResponse(_seite(NICHT_SICHER), status_code=500, headers=_HTML_HEADER)

            kopf = dict(_HTML_HEADER)
            kopf["Content-Disposition"] = f'attachment; filename="{name}-deutsch.pdf"'
            return Response(pdf, media_type="application/pdf", headers=kopf)

    routen = [
        Route("/", index, methods=["GET"]),
        Route("/bogen", bogen, methods=["POST"]),
        Route("/health", gesund, methods=["GET"]),
        Mount("/static", StaticFiles(directory=str(_STATIC)), name="static"),
    ]
    return Starlette(routes=routen)


# ASGI-Einstiegspunkt für uvicorn (nutzt .env-Provider + Standard-Vorlage/DB).
app = erstelle_app()
