"""Regressionstests A7 (Re-Import atomar und verlustsicher) aus dem Korrekturauftrag.

Grundsatz: Ein fehlgeschlagener, leerer oder unplausibel geschrumpfter Import darf NIE
einen vorhandenen, funktionierenden Quellenbestand ersetzen. Alle Tests laufen gegen
temporaere Datenbanken; Open5e wird ueber einen Fake-httpx-Client simuliert (kein Netz)."""
import json
import sqlite3
from pathlib import Path

import pytest

from importer.import_markdown import importiere_markdown

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

_MD_OK = "# **Kapitel**\n\n### **Erster Eintrag**\n\nInhalt eins.\n\n### **Zweiter Eintrag**\n\nInhalt zwei.\n"


def _neue_db(pfad) -> sqlite3.Connection:
    con = sqlite3.connect(pfad)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
        "VALUES ('srd-de','SRD (Deutsch)','de','2024','pdf','CC-BY-4.0',10)")
    con.commit()
    return con


def _befuelle(con, n=5) -> None:
    with con:
        importiere_markdown(con, "srd-de", "# **K**\n\n" + "\n\n".join(
            f"### **Alt {i}**\n\nAlter Inhalt {i}." for i in range(n)), edition="2024")


def _bestand(con) -> tuple[int, int]:
    e = con.execute("SELECT count(*) FROM eintraege").fetchone()[0]
    f = con.execute("SELECT count(*) FROM eintraege_fts").fetchone()[0]
    return e, f


@pytest.fixture()
def con(tmp_path):
    c = _neue_db(tmp_path / "import-safety.sqlite")
    yield c
    c.close()


def test_leerer_reimport_erhaelt_bestand(con):
    """Leeres Markdown (auch: leeres Quellverzeichnis -> leerer Join) ersetzt nichts."""
    _befuelle(con)
    vorher = _bestand(con)
    for leer in ("", "   \n\n", "Nur Praeambel ohne Heading."):
        with pytest.raises(ValueError, match="[Kk]ein"):
            with con:
                importiere_markdown(con, "srd-de", leer, edition="2024")
        assert _bestand(con) == vorher, f"Bestand nach leerem Import veraendert: {leer!r}"


def test_exception_beim_schreiben_rollt_zurueck(con, monkeypatch):
    """Exception mitten im Ersetzen (nach DELETE/INSERT, vor Transaktionsende) laesst
    Bestand UND FTS unveraendert."""
    import importer.import_markdown as im
    _befuelle(con)
    vorher = _bestand(con)
    original = im._ersetze_bestand

    def kaputt(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Simulierter Absturz nach dem Schreiben")

    monkeypatch.setattr(im, "_ersetze_bestand", kaputt)
    with pytest.raises(RuntimeError):
        with con:
            importiere_markdown(con, "srd-de", _MD_OK, edition="2024",
                                erlaube_schrumpfen=True)
    assert _bestand(con) == vorher
    namen = {r[0] for r in con.execute("SELECT name_de FROM eintraege")}
    assert namen == {f"Alt {i}" for i in range(5)}


def test_schrumpf_schwelle_verlangt_force(con):
    """Unerwartet grosser Rueckgang bricht ab; erlaube_schrumpfen=True laesst ihn zu."""
    _befuelle(con, n=10)
    klein = "# **K**\n\n### **Einzig**\n\nNur noch ein Eintrag."
    with pytest.raises(ValueError, match="[Ss]chrumpf"):
        with con:
            importiere_markdown(con, "srd-de", klein, edition="2024")
    assert _bestand(con)[0] == 10
    with con:
        n = importiere_markdown(con, "srd-de", klein, edition="2024",
                                erlaube_schrumpfen=True)
    assert n == 1 and _bestand(con) == (1, 1)


def test_erfolgreicher_reimport_ersetzt_exakt_einmal(con):
    """Erfolgsfall: ersetzt exakt einmal, eintraege und FTS bleiben synchron."""
    _befuelle(con)
    with con:
        n = importiere_markdown(con, "srd-de", _MD_OK, edition="2024",
                                erlaube_schrumpfen=True)
    assert n == 2 and _bestand(con) == (2, 2)
    treffer = con.execute(
        "SELECT count(*) FROM eintraege_fts WHERE eintraege_fts MATCH 'Zweiter'").fetchone()[0]
    assert treffer == 1


# --------------------------- Open5e (Fake-httpx, kein Netz) ---------------------------

class _FakeAntwort:
    def __init__(self, status_code=200, daten=None):
        self.status_code = status_code
        self._daten = daten or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._daten


class _FakeClient:
    """Minimaler httpx.Client-Ersatz: URL -> vorbereitete Antwort(en)."""
    def __init__(self, antworten, **_kwargs):
        self._antworten = antworten

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None):
        wert = self._antworten.get(url.split("?")[0])
        if callable(wert):
            return wert(url, params)
        if wert is None:
            return _FakeAntwort(404)
        return wert


def _fake_httpx(monkeypatch, antworten):
    import httpx

    import importer.import_open5e as io5
    monkeypatch.setattr(httpx, "Client",
                        lambda **kw: _FakeClient(antworten, **kw))
    # Basis-URL fest verdrahten: Tests bleiben unabhaengig von config/foliant.toml (A8).
    monkeypatch.setattr(io5, "_api_base", lambda: _API)


def _open5e_db(tmp_path):
    con = sqlite3.connect(tmp_path / "open5e-safety.sqlite")
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
        "VALUES ('open5e-srd-2024','SRD 5.2 (Open5e)','en','2024','open5e','CC-BY-4.0',60)")
    con.execute(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (1,'zauber',NULL,'Old Spell','en','2024',NULL,'Old body.')")
    con.commit()
    return con


_API = "https://api.open5e.com/v2/"
_DOKUMENTE_OK = _FakeAntwort(200, {"results": [{"key": "srd-2024", "name": "SRD 5.2"}]})


def _leere_endpunkte(ausser=()):
    from importer.import_open5e import _ENDPUNKTE
    antworten = {}
    for endpunkt, _kat in _ENDPUNKTE:
        if endpunkt not in ausser:
            antworten[f"{_API}{endpunkt}/"] = _FakeAntwort(200, {"results": [], "next": None})
    return antworten


def test_open5e_api_fehler_erhaelt_bestand(tmp_path, monkeypatch):
    """404/HTTP-Fehler beim Dokumentabruf ersetzt keine vorhandenen Daten."""
    from importer.import_open5e import import_open5e
    con = _open5e_db(tmp_path)
    try:
        _fake_httpx(monkeypatch, {f"{_API}documents/": _FakeAntwort(500)})
        with pytest.raises(Exception):
            with con:
                import_open5e(con, ["srd-2024"])
        assert con.execute("SELECT count(*) FROM eintraege").fetchone()[0] == 1
    finally:
        con.close()


def test_open5e_leere_antwort_erhaelt_bestand(tmp_path, monkeypatch):
    """Durchgehend leere API-Antworten (0 Datensaetze) ersetzen den Bestand nicht."""
    from importer.import_open5e import import_open5e
    con = _open5e_db(tmp_path)
    try:
        antworten = {f"{_API}documents/": _DOKUMENTE_OK, **_leere_endpunkte()}
        _fake_httpx(monkeypatch, antworten)
        with pytest.raises(ValueError, match="[Kk]ein"):
            with con:
                import_open5e(con, ["srd-2024"])
        assert con.execute("SELECT count(*) FROM eintraege").fetchone()[0] == 1
        assert con.execute("SELECT name_en FROM eintraege").fetchone()[0] == "Old Spell"
    finally:
        con.close()


def test_open5e_pagination_zyklus_bricht_ab(tmp_path, monkeypatch):
    """Eine next-URL, die auf sich selbst zeigt (Zyklus), fuehrt zum Abbruch statt zur
    Endlosschleife; der Bestand bleibt."""
    from importer.import_open5e import import_open5e
    con = _open5e_db(tmp_path)
    try:
        zyklus = _FakeAntwort(200, {"results": [{"name": "Loop", "desc": "x",
                                                 "document": {"key": "srd-2024"}}],
                                    "next": f"{_API}rules/"})
        antworten = {f"{_API}documents/": _DOKUMENTE_OK, **_leere_endpunkte(ausser=("rules",)),
                     f"{_API}rules/": zyklus}
        _fake_httpx(monkeypatch, antworten)
        with pytest.raises(ValueError, match="[Zz]yklus|[Pp]agination"):
            with con:
                import_open5e(con, ["srd-2024"])
        assert con.execute("SELECT count(*) FROM eintraege").fetchone()[0] == 1
    finally:
        con.close()


def test_open5e_fremder_host_wird_abgelehnt(tmp_path, monkeypatch):
    """next-URLs ausserhalb des konfigurierten Open5e-Hosts werden nicht verfolgt."""
    from importer.import_open5e import import_open5e
    con = _open5e_db(tmp_path)
    try:
        boese = _FakeAntwort(200, {"results": [{"name": "X", "desc": "x",
                                                "document": {"key": "srd-2024"}}],
                                   "next": "https://boese.example.com/daten"})
        antworten = {f"{_API}documents/": _DOKUMENTE_OK, **_leere_endpunkte(ausser=("rules",)),
                     f"{_API}rules/": boese}
        _fake_httpx(monkeypatch, antworten)
        with pytest.raises(ValueError, match="[Hh]ost|https"):
            with con:
                import_open5e(con, ["srd-2024"])
        assert con.execute("SELECT count(*) FROM eintraege").fetchone()[0] == 1
    finally:
        con.close()


def test_a8_quellen_upsert_aktualisiert_alle_felder(tmp_path, monkeypatch):
    """A8: Ein Re-Import aktualisiert Titel, Lizenz UND Prioritaet der Quelle -
    nichts bleibt stillschweigend auf alten Werten."""
    from importer.import_open5e import import_open5e
    con = _open5e_db(tmp_path)
    try:
        con.execute("UPDATE quellen SET titel='Veraltet', lizenz='falsch', prioritaet=99")
        con.commit()
        regeln = _FakeAntwort(200, {"results": [
            {"name": "New Rule", "desc": "Fresh.", "document": "srd-2024"}], "next": None})
        antworten = {f"{_API}documents/": _DOKUMENTE_OK, **_leere_endpunkte(ausser=("rules",)),
                     f"{_API}rules/": regeln}
        _fake_httpx(monkeypatch, antworten)
        with con:
            import_open5e(con, ["srd-2024"], erlaube_schrumpfen=True)
        q = con.execute("SELECT titel, lizenz, prioritaet, edition FROM quellen").fetchone()
        assert q["titel"] == "SRD 5.2 (Open5e)"
        assert q["lizenz"] == "CC-BY-4.0" and q["prioritaet"] == 60      # A10-Lizenz je Dokument
        assert q["edition"] == "2024"
    finally:
        con.close()


def test_a8_pfade_projektroot_relativ():
    """A8: relative Pfade loesen ab Projektroot auf, nicht ab Arbeitsverzeichnis."""
    from app.db import projekt_pfad
    from importer.import_glossar import _cache_verzeichnis
    projekt = Path(__file__).resolve().parent.parent
    assert projekt_pfad("data/x.sqlite") == projekt / "data/x.sqlite"
    assert projekt_pfad("/absolut/bleibt.sqlite") == Path("/absolut/bleibt.sqlite")
    assert _cache_verzeichnis() == projekt / "data/cache/dnddeutsch"


def test_open5e_erfolg_ersetzt_exakt_einmal(tmp_path, monkeypatch):
    """Erfolgsfall: neuer Bestand ersetzt den alten exakt einmal, FTS synchron."""
    from importer.import_open5e import import_open5e
    con = _open5e_db(tmp_path)
    try:
        regeln = _FakeAntwort(200, {"results": [
            {"name": "New Rule", "desc": "Fresh rule text.", "document": "srd-2024"}],
            "next": None})
        antworten = {f"{_API}documents/": _DOKUMENTE_OK, **_leere_endpunkte(ausser=("rules",)),
                     f"{_API}rules/": regeln}
        _fake_httpx(monkeypatch, antworten)
        with con:
            n = import_open5e(con, ["srd-2024"], erlaube_schrumpfen=True)
        assert n == 1
        e, f = (con.execute("SELECT count(*) FROM eintraege").fetchone()[0],
                con.execute("SELECT count(*) FROM eintraege_fts").fetchone()[0])
        assert (e, f) == (1, 1)
        assert con.execute("SELECT name_en FROM eintraege").fetchone()[0] == "New Rule"
    finally:
        con.close()
