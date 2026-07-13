"""Foliant - FastMCP-Server (Einstiegspunkt).
Verbindungstest: GET /health (das Phase-0-Echo-Tool wurde nach Abschluss von Phase 1
entfernt - jedes echte Tool beweist die Verbindung, und weniger Tools = weniger Kontextlast).
Tool-Namen einheitlich foliant_<verb>_<nomen> (BP #2).

WICHTIG (Review-Fund): Die Verhaltensregeln werden ueber DREI Kanaele zugestellt, weil
Server-`instructions` nicht von jedem MCP-Client zuverlaessig ans Modell gereicht werden:
  1. FastMCP(instructions=...)            (hier verdrahtet)
  2. Kurzfassung in jeder Tool-Beschreibung (Phase 1, TODO(claude-code))
  3. Grounding-Hinweise IN den Tool-AUSGABEN (Phase 1, TODO(claude-code)) - z. B. liefert eine
     leere Suche explizit {"treffer": [], "hinweis": "Nichts im Bestand - ehrlich sagen, nicht
     aus Allgemeinwissen antworten."}
"""
from __future__ import annotations

import os

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.db import lade_konfig
from app.zugriff import ZugriffsFilter
from config.stil import INSTRUCTIONS

# SYN-P1-003 (codex TECH-020): alle 17 Tools sind strikt lesend/idempotent -
# die Annotations machen das fuer Clients maschinenlesbar (Planung, Caching,
# Sicherheitsheuristiken); openWorldHint=False: geschlossener lokaler Bestand.
_NUR_LESEND = {"readOnlyHint": True, "idempotentHint": True,
               "openWorldHint": False}

# A8: die [server]-Einstellungen der config/foliant.toml werden tatsaechlich verwendet
# (Defaults = bisheriges Verhalten). Anzeigename/Branding: "Foliant für D&D" ordnet nach
# aussen ein, wofuer der Server ist (Connector-Liste in Claude, serverInfo im
# MCP-Handshake). Rufname im Text bleibt "Foliant".
_SERVER_KONFIG = lade_konfig().get("server", {}) or {}
_NAME = _SERVER_KONFIG.get("name", "Foliant für D&D")
mcp = FastMCP(name=_NAME, instructions=INSTRUCTIONS)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "name": _NAME})


@mcp.custom_route("/ready", methods=["GET"])
async def ready(_: Request) -> JSONResponse:
    """Readiness (SYN-P1-011): /health prueft nur den Prozess - eine fehlende/korrupte
    DB galt als 'healthy', waehrend alle Tools leer liefen. Hier: DB read-only oeffnen,
    Kernabfrage + FTS-Probe; jeder Fehler -> 503 mit secret-freiem Grund. Der
    Compose-Healthcheck zeigt hierauf."""
    import sqlite3

    from app.db import standard_pfad
    pfad = standard_pfad()
    if not pfad.exists():
        return JSONResponse({"status": "nicht_bereit", "grund": "keine Datenbank"},
                            status_code=503)
    try:
        con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
        try:
            n = con.execute("SELECT count(*) FROM eintraege").fetchone()[0]
            fts = con.execute("SELECT count(*) FROM eintraege_fts").fetchone()[0]
        finally:
            con.close()
        if n == 0 or n != fts:
            return JSONResponse({"status": "nicht_bereit",
                                 "grund": f"Bestand leer oder FTS inkonsistent "
                                          f"({n}/{fts})"}, status_code=503)
        return JSONResponse({"status": "bereit", "eintraege": n})
    except sqlite3.Error as fehler:
        return JSONResponse({"status": "nicht_bereit",
                             "grund": type(fehler).__name__}, status_code=503)


# Phase 1: Nachschlage-Tools (F1/F2). Docstrings = Tool-Beschreibungen inkl. Kurzregeln
# (Kanal 2); die Grounding-Hinweise stecken in den Tool-AUSGABEN (Kanal 3).
from app.tools import nachschlagen as _nachschlagen

mcp.tool(_nachschlagen.foliant_suche_bestand, annotations=_NUR_LESEND)
mcp.tool(_nachschlagen.foliant_hol_regel, annotations=_NUR_LESEND)
mcp.tool(_nachschlagen.foliant_hol_zauber, annotations=_NUR_LESEND)
mcp.tool(_nachschlagen.foliant_filter_zauber, annotations=_NUR_LESEND)
mcp.tool(_nachschlagen.foliant_hol_monster, annotations=_NUR_LESEND)
mcp.tool(_nachschlagen.foliant_hol_gegenstand, annotations=_NUR_LESEND)
mcp.tool(_nachschlagen.foliant_uebersetze_begriff, annotations=_NUR_LESEND)

# Phase 2: Charaktererstellung (F3/B7) - Listen KNAPP, Details voll, Build-Pruefung ehrlich
# ueber ihre Grenzen (Q4). Reihenfolge-Fuehrung (Klasse -> Hintergrund -> Spezies -> Details)
# steckt in den Tool-Ausgaben (Kanal 3).
from app.tools import charakter as _charakter

mcp.tool(_charakter.foliant_liste_klassen, annotations=_NUR_LESEND)
mcp.tool(_charakter.foliant_liste_hintergruende, annotations=_NUR_LESEND)
mcp.tool(_charakter.foliant_liste_spezies, annotations=_NUR_LESEND)
mcp.tool(_charakter.foliant_liste_talente, annotations=_NUR_LESEND)
mcp.tool(_charakter.foliant_hol_klasse, annotations=_NUR_LESEND)
mcp.tool(_charakter.foliant_hol_hintergrund, annotations=_NUR_LESEND)
mcp.tool(_charakter.foliant_hol_spezies, annotations=_NUR_LESEND)
mcp.tool(_charakter.foliant_hol_talent, annotations=_NUR_LESEND)
mcp.tool(_charakter.foliant_hol_attributswerte, annotations=_NUR_LESEND)
mcp.tool(_charakter.foliant_pruefe_build, annotations=_NUR_LESEND)

# Zugang (NF3/NF4, M3 - Details in app/zugriff.py): GEHEIMPFAD aus FOLIANT_PFAD_TOKEN
# (.env auf dem Pi; leer = /mcp fuer Dev/Tests) + IP-Allowlist als ASGI-Wrapper. Die
# Verbindungs-URL ist damit https://<host>/<token>/mcp - die URL selbst ist der Schluessel.
_PFAD_TOKEN = os.environ.get("FOLIANT_PFAD_TOKEN", "").strip().strip("/")
_BASIS_PFAD = _SERVER_KONFIG.get("pfad", "/mcp")
_MCP_PFAD = f"/{_PFAD_TOKEN}{_BASIS_PFAD}" if _PFAD_TOKEN else _BASIS_PFAD
# SYN-P1-004 (fail-open): Compose defaultete das Token auf leer - der Endpoint lag dann
# still offen unter /mcp, geschuetzt nur durch die geteilte IP-Allowlist. Im
# Produktionsmodus (FOLIANT_PRODUKTION=an, setzt der Container) bricht der Start ohne
# starkes Token hart ab; Dev/Tests bleiben ohne Token lauffaehig.
if os.environ.get("FOLIANT_PRODUKTION", "aus").strip().lower() == "an" \
        and len(_PFAD_TOKEN) < 16:
    raise RuntimeError(
        "FOLIANT_PRODUKTION=an verlangt ein FOLIANT_PFAD_TOKEN mit mindestens 16 "
        "Zeichen (.env; erzeugen: python3 -c \"import secrets; "
        "print(secrets.token_urlsafe(18))\") - Start abgebrochen statt fail-open.")
if _PFAD_TOKEN:
    print(f"foliant: MCP-Endpoint unter /{_PFAD_TOKEN[:4]}…{_BASIS_PFAD} (Geheimpfad aktiv)")
else:
    print("foliant: KEIN Geheimpfad gesetzt (FOLIANT_PFAD_TOKEN) - Endpoint liegt offen "
          "unter /mcp (ok fuer Dev, nicht fuer den Pi-Betrieb).")

app = ZugriffsFilter(mcp.http_app(path=_MCP_PFAD,
                                  stateless_http=bool(_SERVER_KONFIG.get("stateless_http", True))))

if __name__ == "__main__":
    mcp.run()
