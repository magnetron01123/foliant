"""Zugangsschutz-Tests (M3, NF3/NF4): Geheimpfad + IP-Allowlist (app/zugriff.py).

Der Filter ist ein reiner ASGI-Wrapper -> hier ohne HTTP-Client direkt mit
handgebauten Scopes getrieben (dependency-frei, deckt genau die Entscheidungslogik ab).
Kernszenarien: Anthropic-Egress darf; fremde Edge-IP wird 403; lokale Aufrufe ohne
CF-Header (compose-Healthcheck, Container-curl) duerfen; /health bleibt immer offen;
FOLIANT_IP_FILTER=aus schaltet ab. Geheimpfad: server.app routet unter /<token>/mcp,
der alte /mcp existiert dann nicht mehr."""
from __future__ import annotations

import asyncio
import importlib

from app.zugriff import ZugriffsFilter


def _scope(pfad="/geheim/mcp", cf_ip=None, peer="203.0.113.9"):
    headers = [(b"host", b"dnd.example")]
    if cf_ip is not None:
        headers.append((b"cf-connecting-ip", cf_ip.encode()))
    return {"type": "http", "method": "POST", "path": pfad,
            "headers": headers, "client": (peer, 12345)}


def _rufe(filter_, scope) -> int | str:
    """Treibt den Filter; Rueckgabe: 'durchgelassen' oder der gesendete Statuscode."""
    ergebnis = {}

    async def innen(scope, receive, send):
        ergebnis["durch"] = True

    async def send(nachricht):
        if nachricht["type"] == "http.response.start":
            ergebnis["status"] = nachricht["status"]

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    filter_.app = innen
    asyncio.run(filter_(scope, receive, send))
    return "durchgelassen" if ergebnis.get("durch") else ergebnis.get("status")


def test_anthropic_egress_darf():
    f = ZugriffsFilter(None, aktiv=True, extra_ranges=[])
    # 160.79.104.0/21 deckt 104.0-111.255; Rand-IPs beidseitig pruefen.
    assert _rufe(f, _scope(cf_ip="160.79.104.1")) == "durchgelassen"
    assert _rufe(f, _scope(cf_ip="160.79.111.254")) == "durchgelassen"
    assert _rufe(f, _scope(cf_ip="2607:6bc0::1")) == "durchgelassen"


def test_fremde_edge_ip_wird_blockiert():
    f = ZugriffsFilter(None, aktiv=True, extra_ranges=[])
    assert _rufe(f, _scope(cf_ip="160.79.112.1")) == 403      # knapp AUSSERHALB des /21
    assert _rufe(f, _scope(cf_ip="203.0.113.50")) == 403      # beliebige Fremd-IP
    assert _rufe(f, _scope(cf_ip="nicht-parsebar")) == 403    # kaputter Header -> zu


def test_lokale_aufrufe_ohne_cf_header_duerfen():
    f = ZugriffsFilter(None, aktiv=True, extra_ranges=[])
    assert _rufe(f, _scope(cf_ip=None, peer="127.0.0.1")) == "durchgelassen"   # Container-curl
    assert _rufe(f, _scope(cf_ip=None, peer="192.168.131.5")) == "durchgelassen"  # LAN
    assert _rufe(f, _scope(cf_ip=None, peer="testclient")) == "durchgelassen"  # Test-Harness
    # ECHTE oeffentliche IP (Doku-Ranges wie 203.0.113.x gelten in Python als is_private!):
    assert _rufe(f, _scope(cf_ip=None, peer="8.8.8.8")) == 403                 # oeffentlich


def test_health_bleibt_immer_offen():
    f = ZugriffsFilter(None, aktiv=True, extra_ranges=[])
    assert _rufe(f, _scope(pfad="/health", cf_ip="203.0.113.50")) == "durchgelassen"


def test_filter_abschaltbar_und_extra_ranges():
    aus = ZugriffsFilter(None, aktiv=False, extra_ranges=[])
    assert _rufe(aus, _scope(cf_ip="203.0.113.50")) == "durchgelassen"
    heim = ZugriffsFilter(None, aktiv=True, extra_ranges=["203.0.113.0/24"])
    assert _rufe(heim, _scope(cf_ip="203.0.113.50")) == "durchgelassen"


def test_lifespan_scope_laeuft_durch():
    """uvicorn startet die App ueber den Wrapper - lifespan darf nie gefiltert werden."""
    f = ZugriffsFilter(None, aktiv=True, extra_ranges=[])
    gesehen = {}

    async def innen(scope, receive, send):
        gesehen["typ"] = scope["type"]

    f.app = innen
    asyncio.run(f({"type": "lifespan"}, None, None))
    assert gesehen["typ"] == "lifespan"


def test_geheimpfad_verschiebt_mcp_endpoint(monkeypatch):
    """Mit FOLIANT_PFAD_TOKEN liegt der MCP-Endpoint unter /<token>/mcp; /mcp existiert
    nicht mehr. Ohne Token bleibt /mcp (Dev). Geprueft an den echten Starlette-Routen."""
    import app.server as server

    def routen(app_) -> set[str]:
        innen = app_.app if isinstance(app_, ZugriffsFilter) else app_
        return {r.path for r in innen.routes}

    monkeypatch.setenv("FOLIANT_PFAD_TOKEN", "test-token-123")
    neu = importlib.reload(server)
    assert any(p.startswith("/test-token-123/mcp") for p in routen(neu.app)), routen(neu.app)
    assert not any(p == "/mcp" or p.startswith("/mcp/") for p in routen(neu.app))
    assert "/health" in routen(neu.app)                     # Health bleibt an der Wurzel

    monkeypatch.delenv("FOLIANT_PFAD_TOKEN")
    alt = importlib.reload(server)
    assert any(p.startswith("/mcp") for p in routen(alt.app))


def test_produktionsmodus_bricht_ohne_starkes_token_ab(monkeypatch):
    """SYN-P1-004 (fail-open): FOLIANT_PRODUKTION=an ohne >=16-Zeichen-Token bricht den
    Start hart ab, statt still offen unter /mcp zu servieren."""
    import importlib

    import app.server as server
    monkeypatch.setenv("FOLIANT_PRODUKTION", "an")
    monkeypatch.setenv("FOLIANT_PFAD_TOKEN", "kurz")             # < 16 Zeichen
    import pytest
    with pytest.raises(RuntimeError, match="mindestens 16"):
        importlib.reload(server)
    # Mit starkem Token startet er:
    monkeypatch.setenv("FOLIANT_PFAD_TOKEN", "x" * 20)
    importlib.reload(server)
    # Dev-Modus (Produktion aus) bleibt ohne Token lauffaehig:
    monkeypatch.delenv("FOLIANT_PRODUKTION")
    monkeypatch.delenv("FOLIANT_PFAD_TOKEN")
    importlib.reload(server)


def test_pfad_wird_in_logs_redigiert():
    """SYN-P1-004: der Pfad IST das Secret (Geheimpfad-Token) - Blockier-Logs kuerzen es."""
    f = ZugriffsFilter(None, aktiv=True, extra_ranges=[])
    red = f._redigiere_pfad("/supergeheimestoken123/mcp")
    assert "supergeheimestoken123" not in red and red.startswith("/supe")


def test_serving_verbindung_ist_read_only(tmp_path):
    """SYN-P1-005 + TECH-020: connect_readonly erlaubt keine Schreibtransaktion -
    zweite Leitplanke neben dem read-only Volume-Mount."""
    import sqlite3
    from pathlib import Path

    from app import db as adb
    pfad = tmp_path / "ro.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript((Path(__file__).resolve().parent.parent / "db" /
                       "schema.sql").read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft) "
                "VALUES ('x','X','de','2024','pdf')")
    con.commit(); con.close()
    ro = adb.connect_readonly(str(pfad))
    try:
        assert ro.execute("SELECT count(*) FROM quellen").fetchone()[0] == 1   # lesen ok
        import pytest
        with pytest.raises(sqlite3.OperationalError):
            ro.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft) "
                       "VALUES ('y','Y','de','2024','pdf')")
    finally:
        ro.close()


def test_ready_endpoint_spiegelt_db_zustand(tmp_path, monkeypatch):
    """SYN-P1-011: /ready liefert 503 bei fehlender/leerer DB (statt wie /health immer
    200) - Monitoring/Neustartlogik sehen einen kaputten Bestand."""
    import asyncio
    import json as _json

    import app.server as server
    from app import db as adb

    # Fehlende DB -> 503
    monkeypatch.setattr(adb, "standard_pfad", lambda: tmp_path / "fehlt.sqlite")
    r = asyncio.run(server.ready(None))
    assert r.status_code == 503

    # Gefuellte, konsistente DB -> 200
    import sqlite3
    from pathlib import Path
    pfad = tmp_path / "da.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript((Path(__file__).resolve().parent.parent / "db" /
                       "schema.sql").read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft) "
                "VALUES ('x','X','de','2024','pdf')")
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,body_md) "
                "VALUES (1,'regel','R','de','2024','ausreichend langer Regeltext hier')")
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')"); con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    r2 = asyncio.run(server.ready(None))
    assert r2.status_code == 200 and _json.loads(bytes(r2.body))["eintraege"] == 1
