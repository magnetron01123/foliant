"""Breadcrumb als Spalte (Phase 5, Befund E4/C4).

`CONCEPT.md` dokumentierte eine Spalte `eintraege.kontext`, die es nicht gab - der
Breadcrumb stand nur als Textzeile im body_md und wurde per `LIKE '*Kontext: ...*%'`
gesucht, also im Full Scan.

Die zwei tragenden Zusicherungen dieses Umbaus:
  1. Der BODY bleibt unveraendert. Der Breadcrumb steht weiter als Zeile darin - haenge
     ich ihn dort ab, aendert sich der inhalts_hash und der gesamte Bestand braeuchte
     einen Re-Import (und die 2014-Namensreparatur waere hin).
  2. Fehlt die Spalte, muss alles weiterlaufen. Der SERVING-Pfad ist read-only und
     migriert NICHT: zwischen Deploy und erstem Import-Lauf gibt es die Spalte nicht.
"""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app.tools import charakter as ch
from importer.import_markdown import _chunks, importiere_markdown

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

_MARKDOWN = ("# Klassen\n\n## Kämpfer\n\nDer Kämpfer ist ein Krieger.\n\n"
             "### Kampfstile\n\nWähle einen Kampfstil.\n\n"
             "## Magier\n\nDer Magier wirkt Zauber.\n")


@pytest.fixture()
def con(tmp_path):
    pfad = tmp_path / "kontext.sqlite"
    c = sqlite3.connect(pfad)
    c.executescript(_SCHEMA.read_text(encoding="utf-8"))
    c.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
              "VALUES ('srd-de','SRD','de','2024','pdf',10)")
    c.commit()
    c.close()
    v = adb.connect(str(pfad))
    yield v
    v.close()


def test_import_fuellt_die_spalte(con):
    with con:
        importiere_markdown(con, "srd-de", _MARKDOWN, edition="2024", kategorie="klasse")
    zeilen = {n: k for n, k in con.execute("SELECT name_de, kontext FROM eintraege")}
    assert zeilen["Kämpfer"] == "Klassen"
    assert zeilen["Kampfstile"] == "Klassen > Kämpfer"


def test_body_bleibt_unveraendert(con):
    """Die wichtigste Zusicherung: der Breadcrumb steht ZUSAETZLICH weiter im Body.
    Faellt er dort weg, aendert sich der inhalts_hash des gesamten Bestands."""
    with con:
        importiere_markdown(con, "srd-de", _MARKDOWN, edition="2024", kategorie="klasse")
    body = con.execute("SELECT body_md FROM eintraege WHERE name_de='Kampfstile'").fetchone()[0]
    assert body.startswith("*Kontext: Klassen > Kämpfer*")


def test_spalte_und_bodyzeile_stimmen_immer_ueberein(con):
    """Zwei Quellen fuer dieselbe Aussage sind eine Fehlerquelle - der Test haelt sie
    zusammen."""
    with con:
        importiere_markdown(con, "srd-de", _MARKDOWN, edition="2024", kategorie="klasse")
    for kontext, body in con.execute("SELECT kontext, body_md FROM eintraege"):
        assert adb.kontext_aus_body(body) == kontext


def test_migration_fuellt_bestands_db_aus_dem_body(tmp_path):
    """Bestands-DB ohne die Spalte: connect() legt sie an UND backfillt sie einmalig -
    ohne dass der Bestand angefasst werden muss."""
    pfad = tmp_path / "alt.sqlite"
    c = sqlite3.connect(pfad)
    c.execute("CREATE TABLE quellen (id INTEGER PRIMARY KEY, kuerzel TEXT UNIQUE)")
    c.execute("CREATE TABLE eintraege (id INTEGER PRIMARY KEY, quelle_id INTEGER, "
              "kategorie TEXT, name_de TEXT, name_en TEXT, sprache TEXT, edition TEXT, "
              "seite TEXT, body_md TEXT)")
    c.executemany("INSERT INTO eintraege (id, body_md) VALUES (?,?)",
                  [(1, "*Kontext: Zauber > Beschreibungen*\n\nFeuerball ..."),
                   (2, "Ein Eintrag ganz ohne Breadcrumb.")])
    c.commit()
    c.close()

    v = adb.connect(str(pfad))
    try:
        assert "kontext" in {r[1] for r in v.execute("PRAGMA table_info(eintraege)")}
        werte = dict(v.execute("SELECT id, kontext FROM eintraege"))
        assert werte[1] == "Zauber > Beschreibungen"
        assert werte[2] is None            # kein Breadcrumb -> ehrlich NULL, kein ""
    finally:
        v.close()
    adb.connect(str(pfad)).close()         # idempotent


def test_lesepfad_kommt_ohne_die_spalte_aus(tmp_path):
    """Der Serving-Pfad migriert nicht. Auf einer DB ohne die Spalte darf die
    Klassen-Abfrage nicht sprengen, sondern muss auf die LIKE-Suche zurueckfallen."""
    pfad = tmp_path / "ohne-spalte.sqlite"
    c = sqlite3.connect(pfad)
    c.execute("CREATE TABLE eintraege (id INTEGER PRIMARY KEY, kategorie TEXT, "
              "name_de TEXT, edition TEXT, body_md TEXT)")
    c.execute("INSERT INTO eintraege VALUES (1,'klasse','Kampfstile','2024',"
              "'*Kontext: Klassen > Kämpfer*\n\nWähle einen Stil.')")
    c.commit()
    c.close()
    lese = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    try:
        bedingung, params = ch._kontext_bedingung(lese, "Klassen > Kämpfer")
        assert "kontext" not in bedingung, "ohne Spalte darf sie nicht abgefragt werden"
        treffer = lese.execute(
            f"SELECT name_de FROM eintraege WHERE kategorie='klasse' AND {bedingung}",
            params).fetchall()
        assert treffer == [("Kampfstile",)]
    finally:
        lese.close()


def test_lesepfad_nutzt_die_spalte_wenn_sie_da_ist(con):
    with con:
        importiere_markdown(con, "srd-de", _MARKDOWN, edition="2024", kategorie="klasse")
    bedingung, params = ch._kontext_bedingung(con, "Klassen > Kämpfer")
    assert "kontext = ?" in bedingung
    treffer = [r[0] for r in con.execute(
        f"SELECT name_de FROM eintraege WHERE kategorie='klasse' AND {bedingung}",
        params)]
    assert treffer == ["Kampfstile"]


def test_kontext_helfer_bevorzugt_die_spalte():
    """_kontext nimmt den Eintrag (Spalte gewinnt) oder - fuer Altaufrufer - den Body."""
    assert ch._kontext({"kontext": "Klassen > Magier", "body_md": "*Kontext: Falsch*\n\nx"}) \
        == "Klassen > Magier"
    assert ch._kontext({"kontext": None, "body_md": "*Kontext: Zauber*\n\nx"}) == "Zauber"
    assert ch._kontext("*Kontext: Regeln > Kampf*\n\nx") == "Regeln > Kampf"
    assert ch._kontext(None) == ""


def test_chunks_liefern_den_kontext_getrennt():
    chunks = {c["name"]: c for c in _chunks(_MARKDOWN, kategorie_standard="klasse",
                                            split_regeln=[("", 3, "klasse")])}
    assert chunks["Kampfstile"]["kontext"] == "Klassen > Kämpfer"
    assert chunks["Kampfstile"]["body"].startswith("*Kontext: Klassen > Kämpfer*")
