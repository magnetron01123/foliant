"""Zauber-Bruecken ueber den Zauberkopf: Normalisierung (Schule, Fuss->Meter, G=S,
Dauer), Eindeutigkeits- und Widerspruchsregel. Die Negativfaelle sind die eigentliche
Absicherung - ein falsches Paar ist schlimmer als eine Luecke."""
import sqlite3
from pathlib import Path

import pytest

from importer import srd_zauberbruecken as zb
from tests.hilfen import SCHEMA

_SCHEMA = SCHEMA
DE_TOTSTELLEN = ("*Kontext: Zauber*\n\nNekromantie des 3. Grades (Ritual) "
                 "Zeitaufwand: 1 Aktion Reichweite: Berührung Komponenten: V, G, M "
                 "(eine Prise Graberde) Wirkungsdauer: 1 Stunde\n\nDu berührst eine "
                 "bereitwillige Kreatur.")
EN_REVIVIFY = ("*Kontext: R Spells*\n\n3rd\\-level necromancy Casting Time: 1 action "
               "Range: Touch Components: V, S, M (diamonds worth 300 gp) "
               "Duration: Instantaneous\n\nYou touch a creature that has died.")
DE_FEUERBALL = ("*Kontext: Zauber*\n\nHervorrufung des 3. Grades Zeitaufwand: 1 Aktion "
                "Reichweite: 45 m Komponenten: V, G, M (Fledermauskot) "
                "Wirkungsdauer: unmittelbar\n\n8W6 Feuerschaden.")
EN_FIREBALL = ("*Kontext: F Spells*\n\n3rd\\-level evocation Casting Time: 1 action "
               "Range: 150 feet Components: V, S, M (bat guano) "
               "Duration: Instantaneous\n\n8d6 fire damage.")


@pytest.fixture()
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "zauber.sqlite")
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA.read_text(encoding="utf-8"))
    c.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
        "VALUES (?,?,?,?,?,?,?)",
        [("phb-2014-de", "PHB 2014 (de)", "de", "2014", "pdf", "privat", 80),
         ("ddb-2014-en", "Basic Rules (en)", "en", "2014", "ddb", "privat", 40)])
    yield c
    c.close()


def _fuege(c, quelle_id, name, body, sprache):
    c.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,"
              "edition,body_md) VALUES (?,?,?,?,?,?,?)",
              (quelle_id, "regel", name if sprache == "de" else None,
               name if sprache == "en" else None, sprache,
               "2014" if quelle_id == 1 else "2014", body))


def test_fingerabdruck_normalisiert_beide_sprachen_gleich():
    """Derselbe Zauber muss in beiden Sprachen denselben Abdruck ergeben: 150 feet =
    45 m, G(este) = S(omatic), 8W6 = 8d6, unmittelbar = Instantaneous."""
    assert zb.fingerabdruck(DE_FEUERBALL, deutsch=True) == \
        zb.fingerabdruck(EN_FIREBALL, deutsch=False)
    abdruck = zb.fingerabdruck(DE_FEUERBALL, deutsch=True)
    assert abdruck[0] == 3 and abdruck[1] == "evocation"
    assert abdruck[2] == 45 and abdruck[3] == "MSV"
    assert abdruck[4] == (False, 0) and abdruck[5] == "aktion"
    assert abdruck[7] == ("8d6",)


def test_kein_zauberkopf_gibt_none():
    assert zb.fingerabdruck("*Kontext: Regeln*\n\nEinfacher Fliesstext.", True) is None
    assert zb.fingerabdruck("", False) is None
    assert zb.fingerabdruck(None, True) is None


def test_zaubertrick_und_ritual_werden_erfasst():
    trick = zb.fingerabdruck("Hervorrufung-Zaubertrick Zeitaufwand: 1 Aktion", True)
    assert trick[0] == 0 and trick[1] == "evocation"
    assert zb.fingerabdruck(DE_TOTSTELLEN, deutsch=True)[6] is True     # Ritual
    assert zb.fingerabdruck(EN_REVIVIFY, deutsch=False)[6] is False


def test_dauer_trennt_totstellen_von_revivify():
    """DER Fall, an dem ein schmalerer Abdruck scheiterte: beide sind Nekromantie
    3. Grades mit Beruehrung, V/S/M und 1 Aktion. Nur die Wirkungsdauer
    (1 Stunde vs. unmittelbar) unterscheidet sie - und das Ritual-Flag."""
    de = zb.fingerabdruck(DE_TOTSTELLEN, deutsch=True)
    en = zb.fingerabdruck(EN_REVIVIFY, deutsch=False)
    assert de[:4] == en[:4]                      # Grad/Schule/Reichweite/Komponenten gleich
    assert de[4] == (False, 60) and en[4] == (False, 0)
    assert de != en, "Abdruecke muessen sich unterscheiden - sonst Falschpaar"


def test_paart_nur_bei_beidseitiger_eindeutigkeit(con):
    _fuege(con, 1, "FEUERBALL", DE_FEUERBALL, "de")
    _fuege(con, 2, "Fireball", EN_FIREBALL, "en")
    con.commit()
    paare, report = zb.finde_zauber_paare(con)
    assert [(p[0], p[1]) for p in paare] == [("Fireball", "FEUERBALL")]
    assert not report


def test_kollision_wird_verworfen_statt_geraten(con):
    """Zwei deutsche Zauber mit identischem Abdruck: keine Paarung, Report statt Rateschluss."""
    _fuege(con, 1, "FEUERBALL", DE_FEUERBALL, "de")
    _fuege(con, 1, "ZWILLINGSZAUBER", DE_FEUERBALL, "de")
    _fuege(con, 2, "Fireball", EN_FIREBALL, "en")
    con.commit()
    paare, report = zb.finde_zauber_paare(con)
    assert paare == []
    assert report and "nicht eindeutig" in report[0]


def test_widerspruch_zu_belegtem_glossarpaar_wird_verworfen(con):
    """Sagt das Glossar bereits etwas anderes, ist der Abdruck-Treffer nicht belastbar -
    die belegte Zeile gewinnt, der Fund wird gemeldet statt geschrieben."""
    _fuege(con, 1, "FEUERBALL", DE_FEUERBALL, "de")
    _fuege(con, 2, "Fireball", EN_FIREBALL, "en")
    con.execute("INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
                "VALUES ('Fireball','Feuerkugel',1,'Spielerhandbuch','2014')")
    con.commit()
    paare, report = zb.finde_zauber_paare(con)
    assert paare == []
    assert report and "widerspricht belegtem Paar" in report[0]


def test_gleichnamige_brauchen_keine_bruecke(con):
    _fuege(con, 1, "Illusion", DE_FEUERBALL, "de")
    _fuege(con, 2, "illusion", EN_FIREBALL, "en")
    con.commit()
    paare, _ = zb.finde_zauber_paare(con)
    assert paare == []


def test_reichweiten_sonderformen():
    assert zb._reichweite("Reichweite: Berührung", True) == "beruehrung"
    assert zb._reichweite("Range: Touch", False) == "beruehrung"
    assert zb._reichweite("Reichweite: Selbst", True) == "selbst"
    assert zb._reichweite("Range: Self (30-foot radius)", False) == "selbst"
    assert zb._reichweite("Range: 120 feet", False) == 36
    assert zb._reichweite("Reichweite: 36 m", True) == 36
    assert zb._reichweite("Range: 1 mile", False) == 1600
