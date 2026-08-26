"""Ein deutscher Zaubername mit zwei offiziellen englischen Partnern - der Grad entscheidet.

Anlass (14.08.2026): Die drei als „Facetten-Widersprueche" gemeldeten Beschwoerungszauber
waren gar kein Datenfehler. `Celestisches Wesen beschwoeren` trug gleichzeitig
`Conjure Celestial` (7. Grades, wie der deutsche SRD-Eintrag) und `Summon Celestial`
(5. Grades) als OFFIZIELL. Der Fassungsabgleich verglich daraufhin zwei verschiedene
Zauber und meldete den Gradunterschied als Widerspruch: Die Daten stimmten, die Bruecke
war falsch.

Der Test haelt beide Richtungen fest - dass die widersprechende Bruecke faellt UND dass
die Regel schweigt, wo sie nicht entscheiden kann. Das zweite ist das wichtigere: Ein
Kanonisierer, der raet, richtet mehr Schaden an als eine fehlende Zeile.
"""
from __future__ import annotations

import sqlite3

import pytest

from importer.import_glossar import kanonisiere_zauberkonflikte
from tests.hilfen import neue_db


def _bestand(tmp_path):
    con = neue_db(tmp_path / "t.sqlite")
    con.execute("INSERT INTO quellen (id, kuerzel, titel, sprache, edition, herkunft) "
                "VALUES (1,'srd-de','SRD','de','2024','pdf')")
    con.execute("INSERT INTO quellen (id, kuerzel, titel, sprache, edition, herkunft) "
                "VALUES (2,'en','EN','en','2024','pdf')")
    return con


def _zauber(con, eintrag_id, quelle, name_de, name_en, grad):
    con.execute("INSERT INTO eintraege (id, quelle_id, kategorie, name_de, name_en, "
                "sprache, edition, body_md) VALUES (?,?,?,?,?,?,?,?)",
                (eintrag_id, quelle, "zauber", name_de, name_en,
                 "de" if name_de else "en", "2024", "x" * 40))
    con.execute("INSERT INTO zauber_meta (eintrag_id, grad) VALUES (?,?)", (eintrag_id, grad))


def _paar(con, term_en, term_de, offiziell=1):
    con.execute("INSERT INTO glossar (term_en, term_de, offiziell, quelle) "
                "VALUES (?,?,?,'test')", (term_en, term_de, offiziell))


def test_widersprechender_partner_wird_demotet(tmp_path):
    """Der reale Fall: derselbe deutsche Name, zwei Zauber, zwei Grade."""
    con = _bestand(tmp_path)
    _zauber(con, 1, 1, "Celestisches Wesen beschwören", None, 7)
    _zauber(con, 2, 2, None, "Conjure Celestial", 7)
    _zauber(con, 3, 2, None, "Summon Celestial", 5)
    _paar(con, "Conjure Celestial", "Celestisches Wesen beschwören")
    _paar(con, "Summon Celestial", "Celestisches Wesen beschwören")
    con.commit()

    assert kanonisiere_zauberkonflikte(con) == 1
    offiziell = {r[0] for r in con.execute(
        "SELECT term_en FROM glossar WHERE term_de='Celestisches Wesen beschwören' "
        "AND offiziell=1")}
    assert offiziell == {"Conjure Celestial"}
    # Demotet, nicht geloescht: als Suchvariante bleibt die Zeile wertvoll.
    assert con.execute("SELECT count(*) FROM glossar WHERE term_en='Summon Celestial'"
                       ).fetchone()[0] == 1


def test_ohne_passenden_partner_wird_nichts_angefasst(tmp_path):
    """Wenn KEIN Partner zum deutschen Grad passt, ist unklar, wer recht hat - dann darf
    die Regel nicht entscheiden. Raten ist hier teurer als eine offene Mehrdeutigkeit."""
    con = _bestand(tmp_path)
    _zauber(con, 1, 1, "Irgendein Zauber", None, 9)
    _zauber(con, 2, 2, None, "Spell A", 5)
    _zauber(con, 3, 2, None, "Spell B", 3)
    _paar(con, "Spell A", "Irgendein Zauber")
    _paar(con, "Spell B", "Irgendein Zauber")
    con.commit()

    assert kanonisiere_zauberkonflikte(con) == 0
    assert con.execute("SELECT count(*) FROM glossar WHERE offiziell=1").fetchone()[0] == 2


def test_gleicher_grad_bleibt_unberuehrt(tmp_path):
    """Zwei Schreibweisen desselben Zaubers sind kein Konflikt - dafuer gibt es
    kanonisiere_schreibvarianten, und die Grad-Regel hat dort nichts zu suchen."""
    con = _bestand(tmp_path)
    _zauber(con, 1, 1, "Blitz", None, 3)
    _zauber(con, 2, 2, None, "Lightning Bolt", 3)
    _zauber(con, 3, 2, None, "Lightning bolt", 3)
    _paar(con, "Lightning Bolt", "Blitz")
    _paar(con, "Lightning bolt", "Blitz")
    con.commit()

    assert kanonisiere_zauberkonflikte(con) == 0


def test_ohne_facetten_tut_die_regel_nichts(tmp_path):
    """Die Glossar-Kette laeuft auch ohne geseedete Facetten (eigener Import) - dann darf
    sie nicht scheitern, sondern schweigt."""
    con = _bestand(tmp_path)
    _paar(con, "Conjure Celestial", "Celestisches Wesen beschwören")
    _paar(con, "Summon Celestial", "Celestisches Wesen beschwören")
    con.commit()
    assert kanonisiere_zauberkonflikte(con) == 0
    assert con.execute("SELECT count(*) FROM glossar WHERE offiziell=1").fetchone()[0] == 2


def test_eindeutiger_partner_bleibt(tmp_path):
    """Ein einziger Partner ist nie ein Konflikt, auch wenn der Grad abweicht - dann ist
    die Bruecke die einzige Information, die es gibt."""
    con = _bestand(tmp_path)
    _zauber(con, 1, 1, "Einzelzauber", None, 4)
    _zauber(con, 2, 2, None, "Only Spell", 6)
    _paar(con, "Only Spell", "Einzelzauber")
    con.commit()
    assert kanonisiere_zauberkonflikte(con) == 0
    assert con.execute("SELECT offiziell FROM glossar").fetchone()[0] == 1
