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
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

import fitz
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from app.charakterbogen.ddb_pdf import DDBFormatFehler, extrahiere
from app.charakterbogen.de_bogen import rendere
from app.charakterbogen.uebersetzer import (
    DnddeutschNachschlager, ProviderNichtKonfiguriert, UebersetzungsFehler,
    provider_aus_env, uebersetze,
)

_HIER = Path(__file__).parent
_STATIC = _HIER / "static"


def _mit_versionsstempel(html: str) -> str:
    """Haengt den Inhalts-Hash an die statischen Verweise (site.css/site.js).

    Ohne das liefert der Browser - und vor allem Cloudflares Edge-Cache - nach
    einem Deploy weiter die ALTE Datei aus: die Seite sieht dann unveraendert
    aus, obwohl der Server laengst den neuen Stand hat. Der Stempel aendert sich
    nur, wenn sich die Datei aendert, und macht den Cache damit selbstheilend.
    """
    for name in ("site.css", "site.js"):
        datei = _STATIC / name
        if not datei.exists():
            continue
        stempel = hashlib.sha256(datei.read_bytes()).hexdigest()[:8]
        html = html.replace(f"static/{name}", f"static/{name}?v={stempel}")
    return html


_INDEX = _mit_versionsstempel(
    (_HIER / "templates" / "index.html").read_text(encoding="utf-8"))
_ANMELDUNG = _mit_versionsstempel(
    (_HIER / "templates" / "anmeldung.html").read_text(encoding="utf-8"))

MAX_BYTES = 15 * 1024 * 1024        # §7.1: Standard 15 MB
MAX_SEITEN = 50
ZEITLIMIT_S = 100.0                 # Unter Cloudflares Proxy-Read-Timeout (120 s, nur für
                                    # Enterprise änderbar): der Nutzer soll unsere deutsche
                                    # Fehlermeldung sehen, nicht Cloudflares Error 524. Auf dem Pi
                                    # GEMESSEN: 58 s für einen echten Bogen — 70 s wären zu knapp,
                                    # 100 s lassen Luft und bleiben 20 s unter der Kante.

# Öffentliche Fehlertexte (AUFTRAG §6.3) - keine Interna.
NICHT_PDF = "Bitte wähle eine PDF-Datei aus."
KEIN_DDB = "Kein unterstützter D&D-Beyond-Charakterbogen."
NICHT_SICHER = "Dieser PDF-Bogen kann nicht sicher verarbeitet werden."
UEBERSETZUNG_WEG = "Die Übersetzung ist momentan nicht verfügbar. Bitte versuche es später erneut."
PASST_NICHT = ("Der vollständige Inhalt passt nicht auf den offiziellen deutschen "
               "Charakterbogen. Es wurde keine unvollständige PDF erzeugt.")
KONVERTER_BELEGT = "Gerade wird bereits ein Charakterbogen verarbeitet. Bitte versuche es gleich noch einmal."
KENNWORT_FALSCH = "Das Kennwort stimmt nicht."
ZU_VIELE_VERSUCHE = "Zu viele Fehlversuche. Bitte warte ein paar Minuten."
KEIN_ZUGANG = "Der Zugang ist nicht eingerichtet. Bitte WEB_PASSWORT in der .env setzen."

_HTML_HEADER = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": ("default-src 'none'; style-src 'self'; script-src 'self'; "
                                "img-src 'self' data:; form-action 'self'; base-uri 'none'"),
}


def _mit_fehler(vorlage: str, fehler: str | None) -> str:
    if not fehler:
        return vorlage
    banner = f'<p class="fehler">{fehler}</p>'
    return vorlage.replace("</form>", banner + "</form>", 1)


_MCP_START = "<!--MCP-LINK-START-->"
_MCP_ENDE = "<!--MCP-LINK-ENDE-->"
MCP_FEHLT = ("Der Foliant-Link ist auf diesem Server noch nicht hinterlegt — "
             "frag David nach dem Link.")


def _bereite_index(mcp_url: str | None) -> str:
    """Setzt den MCP-Link in die Seite ein. Ohne konfigurierten Link zeigt der Abschnitt
    einen Hinweis statt eines leeren Feldes (fail-soft; die Erklärung bleibt lesbar)."""
    if mcp_url:
        return _INDEX.replace("{{MCP_URL}}", mcp_url)
    vor, _, rest = _INDEX.partition(_MCP_START)
    _, _, nach = rest.partition(_MCP_ENDE)
    return f'{vor}<p class="mini">{MCP_FEHLT}</p>{nach}'


def _anmeldeseite(fehler: str | None = None) -> str:
    return _mit_fehler(_ANMELDUNG, fehler)


def _sicherer_name(name: str) -> str:
    sauber = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip()).strip("_")
    return sauber or "charakterbogen"


# --- Zugang: EIN Kennwort, kein Benutzername (Eigentümer-Wunsch) --------------
# Die Website ist authlos gebaut und jede Konvertierung kostet API-Geld -> ohne Schranke wäre sie
# ein offenes Portemonnaie (der Hostname steht über Certificate-Transparency-Logs öffentlich).
# Statt HTTP-Basic-Auth (hässlicher Browser-Dialog MIT Benutzerfeld) eine eigene Kennwort-Seite.
# Fehlt WEB_PASSWORT, ist die Seite ZU (fail-closed) - nie versehentlich offen.

KEKS = "bogen_zugang"
KEKS_GUELTIG_S = 30 * 24 * 3600     # 30 Tage - die Runde soll sich nicht dauernd neu anmelden
MAX_VERSUCHE = 8                    # je Absender-IP
SPERRE_S = 300.0

_fehlversuche: dict[str, list[float]] = {}


def _signatur(passwort: str, ablauf: int) -> str:
    return hmac.new(passwort.encode(), str(ablauf).encode(), hashlib.sha256).hexdigest()


def _keks_wert(passwort: str) -> str:
    ablauf = int(time.time()) + KEKS_GUELTIG_S
    return f"{ablauf}.{_signatur(passwort, ablauf)}"


def _keks_gueltig(passwort: str, wert: str | None) -> bool:
    """Signiert mit dem Kennwort selbst: ändert David es, sind alle alten Kekse sofort tot."""
    if not passwort or not wert or "." not in wert:
        return False
    roh, _, sig = wert.partition(".")
    try:
        ablauf = int(roh)
    except ValueError:
        return False
    if ablauf < time.time():
        return False
    return secrets.compare_digest(sig, _signatur(passwort, ablauf))


def _absender(request) -> str:
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


def _gesperrt(ip: str) -> bool:
    jetzt = time.monotonic()
    treffer = [t for t in _fehlversuche.get(ip, []) if jetzt - t < SPERRE_S]
    if treffer:
        _fehlversuche[ip] = treffer
    else:
        _fehlversuche.pop(ip, None)
    return len(treffer) >= MAX_VERSUCHE


def _fehlversuch(ip: str) -> None:
    _fehlversuche.setdefault(ip, []).append(time.monotonic())


# --- deterministische Konvertierung (läuft im Threadpool) --------------------

def _konvertiere(pdf_bytes: bytes, provider, glossar_pfad: str | None,
                 template_pfad: str | None, nachschlager=None) -> tuple[bytes, str]:
    charakter = extrahiere(pdf_bytes)                       # -> DDBFormatFehler bei Nicht-DDB
    # Glossar strikt READ-ONLY öffnen (Container mountet es ro; kein Journal/WAL-Schreibversuch)
    # - der Nachschlager schreibt deshalb hier nie, er liefert sein Direktergebnis.
    if glossar_pfad:
        con = sqlite3.connect(f"file:{glossar_pfad}?mode=ro&immutable=1", uri=True)
    else:
        con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    try:
        uebersetze(charakter, con, provider, nachschlager=nachschlager)
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
                 template_pfad: str | None = None, passwort: str | None = None,
                 mcp_url: str | None = None, nachschlager_factory=None) -> Starlette:
    """Baut die ASGI-App. Alle externen Abhängigkeiten sind injizierbar (Tests).
    `mcp_url` erscheint NUR hinter der Anmeldung (der Geheimpfad ist Teil der URL).
    `nachschlager_factory` (z.B. `DnddeutschNachschlager`) wird PRO Konvertierung
    aufgerufen (frisches Zeitbudget); Default None = netzfrei (Tests)."""
    sem = asyncio.Semaphore(1)
    index_html = _bereite_index(mcp_url)

    def _seite(fehler: str | None = None) -> str:
        return _mit_fehler(index_html, fehler)

    def angemeldet(request) -> bool:
        return _keks_gueltig(passwort, request.cookies.get(KEKS))

    async def index(request):
        if not passwort:
            return HTMLResponse(_anmeldeseite(KEIN_ZUGANG), status_code=503, headers=_HTML_HEADER)
        if not angemeldet(request):
            return HTMLResponse(_anmeldeseite(), status_code=401, headers=_HTML_HEADER)
        return HTMLResponse(_seite(), headers=_HTML_HEADER)

    async def anmeldung(request):
        if not passwort:
            return HTMLResponse(_anmeldeseite(KEIN_ZUGANG), status_code=503, headers=_HTML_HEADER)
        ip = _absender(request)
        if _gesperrt(ip):
            return HTMLResponse(_anmeldeseite(ZU_VIELE_VERSUCHE), status_code=429, headers=_HTML_HEADER)

        form = await request.form()
        eingabe = str(form.get("kennwort") or "")
        if not secrets.compare_digest(eingabe, passwort):
            _fehlversuch(ip)
            await asyncio.sleep(1.0)        # bremst Durchprobieren, stört einen Menschen nicht
            return HTMLResponse(_anmeldeseite(KENNWORT_FALSCH), status_code=401, headers=_HTML_HEADER)

        antwort = RedirectResponse("/", status_code=303, headers=_HTML_HEADER)
        antwort.set_cookie(KEKS, _keks_wert(passwort), max_age=KEKS_GUELTIG_S, httponly=True,
                           samesite="lax",
                           # Secure nur, wenn wirklich HTTPS davor liegt (Cloudflare/cloudflared
                           # setzen den Header) - sonst wäre die lokale Abnahme über http kaputt.
                           secure=request.headers.get("x-forwarded-proto", "").lower() == "https")
        return antwort

    async def gesund(request):
        return PlainTextResponse("ok")

    async def bogen(request):
        if not passwort or not angemeldet(request):
            return HTMLResponse(_anmeldeseite(), status_code=401, headers=_HTML_HEADER)
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

            nachschlager = nachschlager_factory() if nachschlager_factory else None
            try:
                pdf, name = await asyncio.wait_for(
                    run_in_threadpool(_konvertiere, roh, prov, glossar_pfad, template_pfad,
                                      nachschlager),
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
        Route("/anmeldung", anmeldung, methods=["POST"]),
        Route("/bogen", bogen, methods=["POST"]),
        Route("/health", gesund, methods=["GET"]),
        Mount("/static", StaticFiles(directory=str(_STATIC)), name="static"),
    ]
    return Starlette(routes=routen)


def _mcp_url_aus_env() -> str | None:
    """FOLIANT_MCP_URL gewinnt; sonst aus Basis-URL + Geheimpfad-Token zusammengesetzt
    (beides liegt auf dem Pi ohnehin in der .env). Fehlt beides -> None (Hinweis-Text)."""
    url = (os.environ.get("FOLIANT_MCP_URL") or "").strip()
    if url:
        return url
    token = (os.environ.get("FOLIANT_PFAD_TOKEN") or "").strip().strip("/")
    basis = (os.environ.get("FOLIANT_BASIS_URL") or "").strip().rstrip("/")
    if token and basis:
        return f"{basis}/{token}/mcp"
    return None


# ASGI-Einstiegspunkt für uvicorn. Glossar-DB, Vorlage, Kennwort, MCP-Link und Provider aus
# der Umgebung. Fehlt WEB_PASSWORT, ist die Seite zu (fail-closed) - nie versehentlich offen.
# Der dnddeutsch-Nachschlager ist in Produktion AN (Cache unter data/cache/dnddeutsch als
# Volume mounten, sonst zahlt jeder Container-Neustart den Erstkontakt erneut).
app = erstelle_app(
    glossar_pfad=os.environ.get("CHARAKTERBOGEN_GLOSSAR") or None,
    template_pfad=os.environ.get("CHARAKTERBOGEN_VORLAGE") or None,
    passwort=os.environ.get("WEB_PASSWORT") or None,
    mcp_url=_mcp_url_aus_env(),
    nachschlager_factory=DnddeutschNachschlager,
)
