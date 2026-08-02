"""Facetten-Abgleich gegen die Geschwisterfassungen (Befund 01.08.2026).

Alle vier Konstellationen stammen aus dem Pi-Vollbestand, nicht aus der Fantasie:

  K1  Verschmolzener Statblock, Fremdblock ZUERST: Der deutsche Ghul traegt den Kopf
      der Geisternaga, `monster_hg` nimmt den ersten Treffer -> HG 8 statt 1. Eine
      HG-1-Suche fand den Ghul nicht, eine HG-8-Suche lieferte ihn falsch.
  K2  Verschmolzener Statblock, eigener Block zuerst: Facette ist bereits richtig -
      der Abgleich muss sie BESTAETIGEN und nicht anfassen (sechs solche Faelle).
  K3  Verrutschte Kopfzeile: EIN Wert im Text, andere Fassung sagt etwas anderes.
      Wird NICHT korrigiert, nur gemeldet - der Trockenlauf am Vollbestand zeigte,
      dass diese Klasse auch echte Editions-/Uebersetzungsdifferenzen enthaelt
      ('Summon Celestial' Grad 5 gegen 'Celestisches Wesen beschwoeren' Grad 7).
  K4  Echte Uneinigkeit / fehlende Zeugen: Da wird NICHTS geraten.
"""
import sqlite3

import pytest

from importer.fassungsabgleich import gleiche_facetten_ab, widersprueche
from tests.hilfen import SCHEMA


@pytest.fixture()
def bestand(tmp_path):
    pfad = tmp_path / "abgleich.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet,"
        "inhaltsart) VALUES (?,?,?,?,?,?,?,?)",
        [("srd-de", "SRD (Deutsch)", "de", "2024", "pdf", "CC-BY-4.0", 10, "regelwerk"),
         ("ddb-br-en", "Basic Rules", "en", "2024", "ddb", "privat", 30, "regelwerk"),
         ("open5e", "SRD 5.2", "en", "2024", "api", "CC-BY-4.0", 40, "regelwerk")])
    con.executemany(
        "INSERT INTO eintraege (id,quelle_id,kategorie,name_de,name_en,sprache,edition,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [# K1: Fremdblock zuerst - der Text nennt HG 8 (Naga) VOR HG 1 (Ghul)
         (1, 1, "monster", "Ghul", None, "de", "2024",
          "**HG** 8 (EP 3.900)\n\n**RK** 12 **TP** 22\n\n**HG** 1 (EP 200)"),
         (2, 2, "monster", None, "Ghoul", "en", "2024", "**CR** 1"),
         (3, 3, "monster", None, "Ghoul", "en", "2024", "**CR** 1"),
         # K2: eigener Block zuerst - Facette stimmt schon
         (4, 1, "monster", "Worg", None, "de", "2024",
          "**HG** 1/2 (EP 100)\n\n**HG** 9 (EP 5.000)"),
         (5, 2, "monster", None, "Worg", "en", "2024", "**CR** 1/2"),
         # K3: verrutschte Kopfzeile - ein Zeuge genuegt, wenn er eindeutig ist
         (6, 2, "zauber", None, "Hideous Laughter", "en", "2024", "*Evocation Cantrip*"),
         (7, 3, "zauber", None, "Hideous Laughter", "en", "2024", "*Level 1 Enchantment*"),
         # K4a: mehrdeutig OHNE Zeugen -> kein Wert (nicht raten)
         (8, 1, "monster", "Einzelgaenger", None, "de", "2024",
          "**HG** 5\n\n**HG** 12"),
         # K4b: Geschwister UNEINIG -> nichts anfassen
         (9, 1, "monster", "Streitfall", None, "de", "2024", "**HG** 3"),
         (10, 2, "monster", None, "Streitfall", "en", "2024", "**CR** 4"),
         (11, 3, "monster", None, "Streitfall", "en", "2024", "**CR** 5")])
    con.executemany("INSERT INTO monster_meta (eintrag_id, hg) VALUES (?,?)",
                    [(1, "8"), (2, "1"), (3, "1"), (4, "1/2"), (5, "1/2"),
                     (8, "5"), (9, "3"), (10, "4"), (11, "5")])
    con.executemany("INSERT INTO zauber_meta (eintrag_id, grad) VALUES (?,?)",
                    [(6, 0), (7, 1)])
    # Die Glossar-Bruecke traegt die DE/EN-Zuordnung - ohne sie faende 'Ghul' kein
    # 'Ghoul' und der Abgleich liefe am echten Bestand ins Leere.
    con.execute("INSERT INTO glossar (term_de, term_en, offiziell, quelle) "
                "VALUES ('Ghul','Ghoul',1,'srd-de')")
    con.commit()
    con.close()
    return sqlite3.connect(pfad)


def _hg(con, eid):
    return con.execute("SELECT hg FROM monster_meta WHERE eintrag_id=?", (eid,)).fetchone()[0]


def test_fremdblock_zuerst_wird_korrigiert(bestand):
    """K1 - der Befund, der den Abgleich ausgeloest hat."""
    protokoll = gleiche_facetten_ab(bestand)
    assert _hg(bestand, 1) == "1"
    eintrag = next(p for p in protokoll if p["eintrag_id"] == 1)
    assert (eintrag["vorher"], eintrag["nachher"]) == ("8", "1")
    assert eintrag["grund"] == "mehrdeutig" and eintrag["zeugen"] == ["1"]


def test_richtige_facette_bleibt_unangetastet(bestand):
    """K2 - sechs der neun verschmolzenen Statblocks sind bereits richtig. Ein Abgleich,
    der sie 'korrigiert', waere schlimmer als der Fehler."""
    protokoll = gleiche_facetten_ab(bestand)
    assert _hg(bestand, 4) == "1/2"
    assert not [p for p in protokoll if p["eintrag_id"] == 4]


def test_blosser_widerspruch_wird_nur_gemeldet(bestand):
    """K3 - der Zaubergrad steht nur EINMAL im Text. Ihn zu ueberschreiben hiesse, einen
    FREMDEN Wert einzubringen; genau daran waere im Trockenlauf 'Summon Celestial'
    kaputtgegangen. Der Fall gehoert in den Bericht, nicht in ein stilles UPDATE."""
    protokoll = gleiche_facetten_ab(bestand)
    grad = bestand.execute("SELECT grad FROM zauber_meta WHERE eintrag_id=6").fetchone()[0]
    assert str(grad) == "0", "Widerspruch wurde stillschweigend ueberschrieben"
    assert not [p for p in protokoll if p["eintrag_id"] == 6]
    gemeldet = widersprueche(bestand)
    fall = next(w for w in gemeldet if w["eintrag_id"] == 6)
    assert fall["eigener"] == "0" and fall["fassungen"] == ["1"]


def test_ohne_zeugen_wird_nicht_geraten(bestand):
    """K4a - zwei Kandidaten, keine andere Fassung: eine fehlende Facette ist ein
    fehlendes Feld, ein geratener Wert eine falsche Auskunft (Regel 1)."""
    gleiche_facetten_ab(bestand)
    assert _hg(bestand, 8) is None


def test_uneinige_fassungen_aendern_nichts(bestand):
    """K4b - widersprechen sich die Quellen selbst, ist das ein echter Konflikt und
    keine Importpanne. Den legt der Detailabruf offen (⚖️), er wird nicht wegkorrigiert."""
    protokoll = gleiche_facetten_ab(bestand)
    assert _hg(bestand, 9) == "3"
    assert not [p for p in protokoll if p["eintrag_id"] == 9]


def test_lauf_ist_idempotent(bestand):
    """Zweiter Lauf auf demselben Bestand: nichts mehr zu tun. Sonst pendelte eine
    Facette bei jedem Seed-Lauf zwischen zwei Werten."""
    gleiche_facetten_ab(bestand)
    assert gleiche_facetten_ab(bestand) == []
