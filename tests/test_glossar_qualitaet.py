"""Regressionstests A9 (Glossar: korrekte Edition + kanonische Auswahl) - offline,
mit gefakter dnddeutsch-Antwort (kein Netz, kein Cache)."""
import sqlite3
from pathlib import Path

import pytest

import importer.import_glossar as ig
from app import glossar as gl

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture()
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "glossar.sqlite")
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA.read_text(encoding="utf-8"))
    yield c
    c.close()


def test_a9_ulisses_ist_nicht_automatisch_2024(con, monkeypatch):
    """Ein Ulisses-Begriff mit 2014-Buchbeleg (PHB(de)) wird NICHT als 2024 markiert;
    ohne sicheren Beleg bleibt die Edition unbekannt (NULL) - nichts wird geraten."""
    antworten = {
        "witch bolt": {"result": [{
            "name_en": "Witch Bolt", "name_de": "Hexenpfeil",
            "name_de_ulisses": "Hexenpfeil",
            "src_de": {"book": "PHB(de)", "book_long": "Spielerhandbuch (2014)", "p": "290"}}]},
        "weird begriff": {"result": [{
            "name_en": "Weird Begriff", "name_de": "Seltsamer Begriff",
            "name_de_ulisses": "Seltsamer Begriff", "src_de": {}}]},
        "community only": {"result": [{
            "name_en": "Community Only", "name_de": "Nur Community",
            "name_de_ulisses": "", "src_de": {}}]},
    }
    monkeypatch.setattr(ig, "_hole_api", lambda client, begriff: antworten[begriff])
    monkeypatch.setattr(ig, "_PAUSE_S", 0)

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    import httpx
    monkeypatch.setattr(httpx, "Client", lambda **kw: _FakeClient())
    ig.seed_glossar(con, list(antworten))

    zeilen = {r["term_en"]: r for r in con.execute("SELECT * FROM glossar")}
    assert zeilen["Witch Bolt"]["offiziell"] == 1
    assert zeilen["Witch Bolt"]["edition_quelle"] == "2014"        # nicht 2024!
    assert zeilen["Weird Begriff"]["offiziell"] == 1               # Ulisses = offiziell ...
    assert zeilen["Weird Begriff"]["edition_quelle"] is None       # ... Edition unbekannt
    assert zeilen["Community Only"]["offiziell"] == 0              # '*'-Fall (T3)


def test_a9_kanonische_auswahl_deterministisch(con):
    """Fuer einen englischen Begriff gewinnt: offiziell > neuere belegte Edition >
    unbekannte Edition > Community; Alphabet nur als letzter Determinismus-Anker."""
    con.executemany(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle,seite) "
        "VALUES (?,?,?,?,?,?)",
        [("Sample Term", "Alter Begriff", 1, "Spielerhandbuch (2014)", "2014", "10"),
         ("Sample Term", "Neuer Begriff", 1, "Spielerhandbuch 2024", "2024", "12"),
         ("Sample Term", "Unbekannt-Edition", 1, "Ulisses-Glossar (dnddeutsch.de)", None, None),
         ("Sample Term", "Aaa Community", 0, "dnddeutsch.de (Community)", None, None)])
    con.commit()
    zeilen = gl.lookup(con, "Sample Term", richtung="en_de")
    assert [z["term_de"] for z in zeilen][:3] == \
        ["Neuer Begriff", "Alter Begriff", "Unbekannt-Edition"]
    assert zeilen[-1]["term_de"] == "Aaa Community"        # trotz Alphabet ganz hinten
    de, offiziell = gl.term_de(con, "Sample Term")
    assert (de, offiziell) == ("Neuer Begriff", True)      # S8: neuer offizieller gewinnt
