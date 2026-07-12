"""Blocker-Regression SYN-P0-006 (Synthese 2026-07-12, verifiziert): Ungueltige
kategorie-/quelle-/richtung-Parameter erzeugten ein falsches 'Nichts im Bestand' -
inklusive des B1-Ehrlichkeitshinweises, der das Modell zur Fehlanzeige anwies.
Reproduzierter Realfall: suche_regeln('Feuerball', kategorie='spell') -> leer + Leerhinweis,
obwohl der Feuerball mit kategorie='zauber' zwei Treffer hatte."""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app.tools import charakter as ch
from app.tools import nachschlagen as ns

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    pfad = tmp_path / "foliant-validierung.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
        "VALUES ('srd-de','SRD 5.2.1 (Deutsch)','de','2024','pdf','CC-BY-4.0',10)")
    con.execute(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (1,'zauber','Feuerball','Fireball','de','2024','139','8W6 Feuer.')")
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def test_ungueltige_kategorie_ist_kein_leerer_bestand(bestand):
    """Der Realfall der Synthese: englischer Kategoriewert fuer vorhandenen Inhalt."""
    s = ns.foliant_suche_regeln("Feuerball", kategorie="spell")
    assert s["treffer"] == [] and "fehler" in s
    assert "spell" in s["fehler"] and "zauber" in s["fehler"]      # gueltige Werte genannt
    assert "KEIN 'nicht im Bestand'" in s["hinweis"]
    assert "Nichts im Bestand" not in s.get("hinweis", "")         # nie der B1-Leerhinweis
    # Gueltige Kategorie liefert den Treffer weiterhin:
    assert ns.foliant_suche_regeln("Feuerball", kategorie="zauber")["treffer"]


def test_quellen_titel_statt_kuerzel_wird_erklaert(bestand):
    """Haeufigster Fehlaufruf: der Treffer-TITEL als quelle-Filter (SYN-P1-002-Nachbar)."""
    s = ns.foliant_suche_regeln("Feuerball", quelle="SRD 5.2.1 (Deutsch)")
    assert s["treffer"] == [] and "fehler" in s
    assert "srd-de" in s["fehler"] and "Titel" in s["fehler"]
    assert ns.foliant_suche_regeln("Feuerball", quelle="srd-de")["treffer"]


def test_ungueltige_talent_kategorie(bestand):
    antwort = ch.foliant_liste_talente(kategorie="origin")
    assert antwort["talente"] == [] and "fehler" in antwort
    assert "herkunft" in antwort["fehler"]


def test_ungueltige_glossar_richtung(bestand):
    u = ns.foliant_uebersetze_begriff("Feuerball", richtung="de-en")
    assert u["gefunden"] is False and "fehler" in u
    assert "auto" in u["fehler"]


def test_p2_grenzen_gegen_ueberlast(bestand):
    """SYN-P2-004 (codex TECH-013): ueberlange Query wird gekappt (kein Crash, kein
    ausuferndes Fuzzy), limit ueber der Obergrenze wird gedeckelt."""
    from app import db as adb
    r = ns.foliant_suche_regeln("Feuerball " + "z" * 5000)
    assert isinstance(r["treffer"], list)                 # kein Crash, echte Antwort
    con = adb.connect(str(adb.standard_pfad()))
    try:
        erg = adb.fts_suche(con, "Feuerball", limit=99999)
        assert len(erg["treffer"]) <= adb.MAX_LIMIT
    finally:
        con.close()


def test_p2_glossar_cache_invalidiert_nach_aenderung(bestand):
    """SYN-P2-004: der Glossar-Cache liefert nach einer Aenderung (neue Zeile ->
    andere Zeilenzahl) die aktuellen Daten, nicht den alten Stand."""
    from app import db as adb
    from app import glossar as gl
    con = adb.connect(str(adb.standard_pfad()))
    try:
        assert gl.lookup(con, "Feuerball", richtung="de_en") == []   # noch nichts
        con.execute("INSERT INTO glossar (term_en,term_de,offiziell) "
                    "VALUES ('Fireball','Feuerball',1)")
        con.commit()
        zeilen = gl.lookup(con, "Feuerball", richtung="de_en")
        assert zeilen and zeilen[0]["term_en"] == "Fireball"         # Cache invalidiert
    finally:
        con.close()
