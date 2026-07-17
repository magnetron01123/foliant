"""Tests für app/dnddeutsch.py: Antwort-Bewertung, Klammer-Lemma-Regel, Cache-Verhalten.

Alles offline - API-Antworten sind synthetische Dicts, `hole()` läuft gegen ein
Temp-Cache-Verzeichnis mit einem Fake-Client.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from app import dnddeutsch
from app.dnddeutsch import Zeile, zeilen_aus_antwort


def _antwort(*ergebnisse: dict) -> dict:
    return {"result": list(ergebnisse)}


def _eintrag(en: str, de: str, ulisses: str = "", buch: str | None = None) -> dict:
    r = {"name_en": en, "name_de": de, "name_de_ulisses": ulisses}
    if buch:
        r["src_de"] = {"book": buch, "book_long": f"Langname {buch}", "p": "12"}
    return r


# --- Bewertung ----------------------------------------------------------------

def test_ulisses_ist_offiziell():
    zeilen = zeilen_aus_antwort(_antwort(_eintrag("Monk", "Moench-Alt", ulisses="Mönch")))
    assert zeilen == [Zeile("Monk", "Mönch", 1, "Ulisses-Glossar (dnddeutsch.de)", None, None)]


def test_buchbeleg_ist_offiziell_mit_edition():
    zeilen = zeilen_aus_antwort(_antwort(_eintrag("Stunning Strike", "Betäubender Schlag",
                                                  buch="PHB(de)")))
    assert zeilen[0].offiziell == 1
    assert zeilen[0].edition == "2014"          # konservativ aus dem Buchkürzel
    assert zeilen[0].seite == "12"


def test_community_ohne_beleg_ist_inoffiziell():
    zeilen = zeilen_aus_antwort(_antwort(_eintrag("Foo", "Fu")))
    assert zeilen[0].offiziell == 0
    assert zeilen[0].quelle == "dnddeutsch.de (Community)"


def test_fehlerantwort_ist_none_und_leere_liste_bleibt_leer():
    assert zeilen_aus_antwort({"result": "too many hits"}) is None
    assert zeilen_aus_antwort({"result": []}) == []
    assert zeilen_aus_antwort({}) == []


# --- Klammer-Lemma-Regel --------------------------------------------------------

def test_kern_zeile_aus_klammerform():
    """'Oil (flask)' belegt zusätzlich das nackte Lemma 'Oil' (beidseitig gestrippt)."""
    zeilen = zeilen_aus_antwort(_antwort(
        _eintrag("Oil (flask)", "Öl (Flasche)", buch="PHB(de)"),
        _eintrag("Oil of Sharpness", "Öl der Schärfe", buch="DMG(de)")))
    kerne = [z for z in zeilen if z.term_en == "Oil"]
    assert kerne == [Zeile("Oil", "Öl", 1, "Langname PHB(de)", "2014", "12")]


def test_kein_kern_bei_exakt_vorhandenem_lemma():
    """Existiert 'Lamp' schon exakt, erzeugt 'Lamp (hooded)' KEINE Kern-Zeile."""
    zeilen = zeilen_aus_antwort(_antwort(
        _eintrag("Lamp", "Lampe", buch="PHB(de)"),
        _eintrag("Lamp (hooded)", "Blendlaterne", buch="PHB(de)")))
    assert [z.term_de for z in zeilen if z.term_en == "Lamp"] == ["Lampe"]


def test_kein_kern_bei_mehrdeutigkeit_oder_kommaform():
    """Zwei Klammerformen mit demselben Kern ODER invertierte Kommaformen -> nichts raten."""
    mehrdeutig = zeilen_aus_antwort(_antwort(
        _eintrag("Ale (mug)", "Bier (Krug)", buch="PHB(de)"),
        _eintrag("Ale (gallon)", "Bier (Gallone)", buch="PHB(de)")))
    assert not [z for z in mehrdeutig if z.term_en == "Ale"]
    komma = zeilen_aus_antwort(_antwort(
        _eintrag("Rope, hempen (50 feet)", "Seil aus Hanf (15 m)", buch="PHB(de)")))
    assert [z.term_en for z in komma] == ["Rope, hempen (50 feet)"]


# --- hole(): Cache-Verhalten ----------------------------------------------------

class _FakeClient:
    def __init__(self, daten: dict):
        self.daten = daten
        self.aufrufe = 0

    def get(self, url, params=None):
        self.aufrufe += 1
        client = self

        class Antwort:
            def raise_for_status(self):
                pass

            def json(self):
                return client.daten

        return Antwort()


def test_hole_cached_und_drosselt_nur_echte_zugriffe(tmp_path, monkeypatch):
    monkeypatch.setattr(dnddeutsch, "cache_verzeichnis", lambda: tmp_path)
    pausen: list[float] = []
    monkeypatch.setattr(dnddeutsch.time, "sleep", lambda s: pausen.append(s))
    client = _FakeClient(_antwort(_eintrag("Monk", "Mönch", ulisses="Mönch")))

    d1 = dnddeutsch.hole(client, "Monk", pause_s=0.5)
    d2 = dnddeutsch.hole(client, "Monk", pause_s=0.5)   # zweiter Zugriff: aus dem Cache
    assert d1 == d2
    assert client.aufrufe == 1                          # nur EIN echter API-Zugriff
    assert pausen == [0.5]                              # Drossel nur nach dem echten Zugriff
    assert json.loads((tmp_path / "monk.json").read_text())["result"]


# --- schreibe_zeilen -------------------------------------------------------------

def test_schreibe_zeilen_upsert():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE glossar (term_en TEXT, term_de TEXT, offiziell INT, "
                "quelle TEXT, edition_quelle TEXT, seite TEXT, "
                "UNIQUE(term_en, term_de))")
    zeilen = [Zeile("Oil", "Öl", 0, "dnddeutsch.de (Community)", None, None)]
    assert dnddeutsch.schreibe_zeilen(con, zeilen) == 1
    # Upsert: dieselbe Zeile mit besserem Beleg überschreibt offiziell/quelle
    dnddeutsch.schreibe_zeilen(con, [Zeile("Oil", "Öl", 1, "Langname PHB(de)", "2014", "5")])
    zeile = con.execute("SELECT offiziell, quelle FROM glossar WHERE term_en='Oil'").fetchone()
    assert tuple(zeile) == (1, "Langname PHB(de)")


def test_hole_ohne_beschreibbaren_cache(tmp_path, monkeypatch):
    """Web-Container: Cache ist read-only gemountet. Cache-HITS gelten, Cache-MISSES
    liefern die API-Antwort trotzdem - nur ohne zu speichern (kein Crash)."""
    ro = tmp_path / "cache"
    ro.mkdir()
    (ro / "monk.json").write_text(json.dumps(_antwort(_eintrag("Monk", "Mönch"))),
                                  encoding="utf-8")
    ro.chmod(0o500)                                   # lesen/betreten, nicht schreiben
    monkeypatch.setattr(dnddeutsch, "cache_verzeichnis", lambda: ro)
    monkeypatch.setattr(dnddeutsch.time, "sleep", lambda s: None)
    try:
        client = _FakeClient(_antwort(_eintrag("Martial Arts", "Kampfkünste")))
        assert dnddeutsch.hole(client, "Monk")["result"]     # Cache-HIT, kein Netz
        assert client.aufrufe == 0
        daten = dnddeutsch.hole(client, "Martial Arts")      # Cache-MISS -> API, kein Crash
        assert daten["result"][0]["name_de"] == "Kampfkünste"
        assert client.aufrufe == 1
        assert not (ro / "martial-arts.json").exists()       # nichts geschrieben
    finally:
        ro.chmod(0o700)                                      # tmp_path aufräumbar lassen


def test_hole_ohne_cache_verzeichnis(tmp_path, monkeypatch):
    """Cache weder vorhanden noch anlegbar (z.B. Pfad nicht gemountet) -> ohne Cache weiter."""
    gesperrt = tmp_path / "nicht_anlegbar"
    gesperrt.mkdir()
    gesperrt.chmod(0o500)
    monkeypatch.setattr(dnddeutsch, "cache_verzeichnis", lambda: gesperrt / "tief" / "cache")
    monkeypatch.setattr(dnddeutsch.time, "sleep", lambda s: None)
    try:
        client = _FakeClient(_antwort(_eintrag("Oil (flask)", "Öl (Flasche)")))
        assert dnddeutsch.hole(client, "Oil")["result"]
        assert client.aufrufe == 1
    finally:
        gesperrt.chmod(0o700)
