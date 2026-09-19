"""Zugangsschutz-Tests (M3, NF3/NF4): Geheimpfad und Zugangsmodus (app/zugriff.py).

Geprueft wird, was dieser Dienst selbst entscheidet: server.app routet im
Geheimpfad-Modus unter /<token>/mcp und der alte /mcp existiert dann nicht mehr; im
Router-Modus serviert er das nackte /mcp; ein unbekannter FOLIANT_ZUGANG bricht ab.

Was hier NICHT mehr geprueft werden kann: ob der Endpoint tatsaechlich geschuetzt ist.
Die IP-Allowlist ist am 02.09.2026 in eine WAF-Regel an der Cloudflare-Kante gewandert
(Begruendung und Preis: app/zugriff.py, CONCEPT.md §9). Im Router-Modus liegt damit
KEINE Pruefung mehr im Dienst - eine gruene Testsuite sagt ueber die Erreichbarkeit von
aussen nichts aus."""
from __future__ import annotations

import importlib

from tests.hilfen import SCHEMA

def test_geheimpfad_verschiebt_mcp_endpoint(monkeypatch):
    """Mit FOLIANT_PFAD_TOKEN liegt der MCP-Endpoint unter /<token>/mcp; /mcp existiert
    nicht mehr. Ohne Token bleibt /mcp (Dev). Geprueft an den echten Starlette-Routen."""
    import app.server as server

    monkeypatch.setenv("FOLIANT_PFAD_TOKEN", "test-token-123")
    neu = importlib.reload(server)
    assert any(p.startswith("/test-token-123/mcp") for p in _routen(neu.app)), _routen(neu.app)
    assert not any(p == "/mcp" or p.startswith("/mcp/") for p in _routen(neu.app))
    assert "/health" in _routen(neu.app)                    # Health bleibt an der Wurzel

    monkeypatch.delenv("FOLIANT_PFAD_TOKEN")
    alt = importlib.reload(server)
    assert any(p.startswith("/mcp") for p in _routen(alt.app))


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


def test_serving_verbindung_ist_read_only(tmp_path):
    """SYN-P1-005 + TECH-020: connect_readonly erlaubt keine Schreibtransaktion -
    zweite Leitplanke neben dem read-only Volume-Mount."""
    import sqlite3

    from app import db as adb
    pfad = tmp_path / "ro.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
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
    pfad = tmp_path / "da.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
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


# --------------------------------------------------------------------------------------
# Zugangsmodus: hinter dem geteilten mcp-router haelt der ROUTER den Geheimpfad
# --------------------------------------------------------------------------------------

def _routen(app_) -> set[str]:
    # Seit dem 02.09.2026 ist `server.app` die nackte ASGI-App: der ZugriffsFilter, der
    # sie bis dahin umschloss, ist mit der IP-Allowlist entfallen (app/zugriff.py).
    return {r.path for r in app_.routes}


def test_router_modus_serviert_das_nackte_mcp(monkeypatch):
    """Der mcp-router entfernt SEIN Token und reicht /mcp weiter. Ein eigener Geheimpfad
    wuerde genau diese Anfrage mit 404 beantworten - der Dienst saehe gesund aus und
    waere trotzdem nicht bedienbar. Im Router-Modus liegt der Endpoint deshalb unter
    /mcp, und ein noch in der .env stehendes FOLIANT_PFAD_TOKEN aendert daran NICHTS
    (sonst haengt der Dienst nach einer vergessenen Aufraeumzeile still ins Leere)."""
    import app.server as server

    monkeypatch.setenv("FOLIANT_ZUGANG", "router")
    monkeypatch.setenv("FOLIANT_PFAD_TOKEN", "altes-token-das-bleiben-durfte")
    neu = importlib.reload(server)
    assert any(p.startswith("/mcp") for p in _routen(neu.app)), _routen(neu.app)
    assert not any("altes-token" in p for p in _routen(neu.app))
    assert "/health" in _routen(neu.app)

    monkeypatch.delenv("FOLIANT_ZUGANG")
    monkeypatch.delenv("FOLIANT_PFAD_TOKEN")
    importlib.reload(server)


def test_unbekannter_zugangsmodus_bricht_ab(monkeypatch):
    """Ein Tippfehler darf nicht still den anderen Modus einschalten: beide sehen im Log
    gleich gesund aus, und der Unterschied faellt erst auf, wenn ein Aufruf 404 bekommt."""
    import pytest

    from app import zugriff

    monkeypatch.setenv("FOLIANT_ZUGANG", "rooter")
    with pytest.raises(RuntimeError, match="kein gueltiger Zugangsmodus"):
        zugriff.zugangsmodus()
    monkeypatch.setenv("FOLIANT_ZUGANG", "  RouTer ")          # Rand: Leerraum + Grossschrift
    assert zugriff.zugangsmodus() == zugriff.MODUS_ROUTER
    monkeypatch.delenv("FOLIANT_ZUGANG")
    assert zugriff.zugangsmodus() == zugriff.MODUS_GEHEIMPFAD  # Standard = der strengere


def test_compose_erfuellt_den_router_vertrag():
    """Der Vertrag des geteilten Routers ist reine Namenskonvention (~/cloudflare-tunnel,
    README "The contract"): Container `<name>-mcp`, Port 8000, MCP unter /mcp, Netz
    `mcp-net`. Nichts davon steht in einer Konfigurationsdatei des Routers - eine
    Umbenennung nimmt den Dienst STILL vom Netz, kein Log sagt etwas. Genau deshalb
    haelt ein Test die drei Zeilen fest, an denen es haengt.

    Der fehlende Host-Port gehoert dazu: im Router-Modus liegt der Endpoint unter dem
    nackten /mcp, ein veroeffentlichter Port waere der direkte Weg am Router vorbei."""
    import pathlib

    import yaml

    compose = yaml.safe_load(
        (pathlib.Path(__file__).resolve().parents[1] / "docker-compose.yml")
        .read_text(encoding="utf-8"))
    dienst = compose["services"]["foliant"]
    assert dienst["container_name"] == "foliant-mcp", (
        "Der Containername IST die Route (/<token>/foliant/mcp) - ein anderer Name "
        "nimmt den Dienst still vom Netz.")
    assert "mcp-net" in dienst["networks"]
    assert compose["networks"]["mcp-net"]["external"] is True, (
        "mcp-net gehoert keinem Stack; `external: true` laesst compose lieber den Start "
        "verweigern, als ein leeres Ersatznetz zu bauen.")
    assert not dienst.get("ports"), (
        "Kein Host-Port im Router-Modus: der Endpoint liegt unter dem nackten /mcp.")
    assert "cloudflared" not in compose["services"], (
        "Foliant betreibt keinen eigenen Tunnel-Connector mehr (26.08.2026).")
