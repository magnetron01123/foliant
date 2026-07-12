"""Blocker-Regression SYN-P0-001 (Synthese 2026-07-12, verifiziert): Fuzzy-Glossartreffer
sind Suchvorschlaege, NIE fachliche Identitaet.

Der Realbestand-Fall: 'Aktionen' matcht die Glossarzeile 'Reaktionen' mit fuzz.ratio 88.9
(Cutoff 88). Vor dem Fix wurde daraus (a) die 'offizielle Uebersetzung'
'Reaktionen (Reactions)', (b) ein Exakt-Treffer im Detailabruf (hol_regel('Aktionen')
lieferte den Monster-Reaktionen-Eintrag S. 299 mit Beleg) und (c) ein falsches
Klammer-Original in der Anzeige. Fixture bildet genau diese Konstellation nach."""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app import glossar as gl
from app.tools import nachschlagen as ns

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    pfad = tmp_path / "foliant-identitaet.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
        "VALUES ('srd-de','SRD 5.2.1 (Deutsch)','de','2024','pdf','CC-BY-4.0',10)")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (1,'regel',?,NULL,'de','2024',?,?)",
        [("Aktionen", "11",
          "*Kontext: Die Spielregeln > Kampf*\n\nWenn du etwas tust, fuehrst du eine "
          "Aktion aus: Angriff, Zauber wirken, Spurt, Rueckzug ..."),
         ("Reaktionen", "299",
          "*Kontext: Monster > Elemente von Wertekästen*\n\nWenn einem Monster Reaktionen "
          "zur Verfuegung stehen, sind sie in diesem Abschnitt aufgefuehrt.")])
    # Glossar kennt NUR 'Reaktionen' - fuzzy-nah zu 'Aktionen' (ratio 88.9 >= Cutoff 88):
    con.execute(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
        "VALUES ('Reactions','Reaktionen',1,'Spielerhandbuch 2024','2024')")
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def test_lookup_traegt_matchtyp(bestand):
    con = adb.connect(str(adb.standard_pfad()))
    try:
        zeilen = gl.lookup(con, "Aktionen", richtung="de_en")
        assert zeilen and all(z["match"] == "fuzzy" for z in zeilen)
        exakt = gl.lookup(con, "Reaktionen", richtung="de_en")
        assert exakt and exakt[0]["match"] == "exakt"
        # term_de nutzt nur exakte Zeilen: fuer 'Actions' gibt es keine -> Fallback (S3/4).
        assert gl.term_de(con, "Actions") == ("Actions", False)
        assert gl.term_de(con, "Reactions") == ("Reaktionen", True)
    finally:
        con.close()


def test_uebersetzung_erfindet_keine_identitaet(bestand):
    """'Aktionen' darf NIE als 'Reaktionen (Reactions)' bestaetigt werden - hoechstens
    als ausdruecklich unbestaetigter Aehnlichkeits-Kandidat."""
    u = ns.foliant_uebersetze_begriff("Aktionen")
    assert u["gefunden"] is False and "begriffe" not in u
    assert any(a["term_de"] == "Reaktionen" for a in u.get("aehnliche_begriffe", []))
    assert "NICHT ungeprueft" in u["hinweis"]


def test_detailabruf_waehlt_keinen_fremden_eintrag(bestand):
    """hol_regel('Aktionen') liefert den Aktionen-Eintrag - nicht die Monster-Reaktionen."""
    d = ns.foliant_hol_regel("Aktionen")
    assert d["gefunden"] is True and d["name_de"] == "Aktionen", d
    assert "Reaktionen" not in (d.get("anzeige_name") or "")
    # Anzeige haengt kein fuzzy-fremdes Original an ('Aktionen (Reactions)' waere falsch):
    assert "(Reactions)" not in d["anzeige_name"]


def test_suche_boostet_fuzzy_nicht_als_exakt(bestand):
    """Suche 'Aktionen': der Aktionen-Eintrag steht vor dem fuzzy-nahen Reaktionen-Eintrag."""
    s = ns.foliant_suche_regeln("Aktionen")
    assert s["treffer"] and s["treffer"][0]["name_de"] == "Aktionen"
