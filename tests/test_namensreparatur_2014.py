"""Namensreparatur der 2014-Scans: Varianten-Bildung und belegter Abgleich.
Kern der Absicherung sind die Negativfaelle - ein falsch 'reparierter' Name waere
schlimmer als ein zerrissener, weil er echte Inhalte unter falschem Namen zeigt."""
import sqlite3
from pathlib import Path

import pytest

from importer.import_glossar import _namensvarianten, repariere_2014_namen
from importer import namensreparatur as nr

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture()
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "namen.sqlite")
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA.read_text(encoding="utf-8"))
    c.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,"
              "prioritaet) VALUES ('phb-2014-de','PHB (de)','de','2014','pdf','privat',80)")
    yield c
    c.close()


def _eintrag(c, name):
    c.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,body_md)"
              " VALUES (1,'regel',?, 'de','2014','Regeltext.')", (name,))


def _glossarzeile(c, en, de):
    c.execute("INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
              "VALUES (?,?,1,'Test','2014')", (en, de))


def test_varianten_decken_die_ocr_schaeden_ab():
    assert "FERN SCHRITT" in _namensvarianten("FERN SCHRITT SCHRITT")
    assert "INVESTITUR DES GESTEINS" in _namensvarianten("INVESTITUR DES DES GESTEIN S")
    assert _namensvarianten("OTTOS TANZ.")[0] == "OTTOS TANZ"
    assert _namensvarianten("Sauber") == ["Sauber"]


def test_repariert_zerrissenes_kompositum_gegen_glossar(con):
    _eintrag(con, "SEELEN KÄFIG")
    _glossarzeile(con, "Soul Cage", "Seelenkäfig")
    con.commit()
    assert repariere_2014_namen(con, mit_netz=False) == 1
    assert con.execute("SELECT name_de FROM eintraege").fetchone()[0] == "Seelenkäfig"


def test_repariert_wortdopplung(con):
    _eintrag(con, "FERN SCHRITT SCHRITT")
    _glossarzeile(con, "Far Step", "Fernschritt")
    con.commit()
    assert repariere_2014_namen(con, mit_netz=False) == 1
    assert con.execute("SELECT name_de FROM eintraege").fetchone()[0] == "Fernschritt"


def test_ohne_beleg_bleibt_der_name_unberuehrt(con):
    """Kein Glossar-Eintrag = keine Korrektur. Lieber ein zerrissener Name als ein
    falscher - geraten wird nicht (B4)."""
    _eintrag(con, "VÖLLIG UNBEKANNTER ZAUBER")
    con.commit()
    assert repariere_2014_namen(con, mit_netz=False) == 0
    assert con.execute("SELECT name_de FROM eintraege").fetchone()[0] == \
        "VÖLLIG UNBEKANNTER ZAUBER"


def test_unsauberes_ziel_wird_abgelehnt(con):
    """Das ZIEL muss sauber sein - sonst repariert man Muell auf Muell."""
    _eintrag(con, "STEIN WAND")
    _glossarzeile(con, "Stone Wall", "Stein W and")      # kaputtes Kurzfragment 'W'
    con.commit()
    assert repariere_2014_namen(con, mit_netz=False) == 0


def test_bereits_korrekte_namen_bleiben_stehen(con):
    _eintrag(con, "Seelenkäfig")
    _glossarzeile(con, "Soul Cage", "Seelenkäfig")
    con.commit()
    assert repariere_2014_namen(con, mit_netz=False) == 0
