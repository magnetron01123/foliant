"""Abfrage-Protokoll (O4/M5): Zeilen entstehen mit korrektem Suchweg, ein kaputter
Log-Pfad bricht NIE den Lookup, die Rotation deckelt die Groesse, und der
admin-suchbericht aggregiert die Kurations-Signale."""
import argparse
import json
import sqlite3
from pathlib import Path

import pytest

from app import admin as adm
from app import db as adb
from app import protokoll as _protokoll
from app.tools import nachschlagen as ns
from app.tools import suche as su
from tests.hilfen import SCHEMA

_SCHEMA = SCHEMA
@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    pfad = tmp_path / "foliant-protokolltest.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
        "VALUES ('srd-de','SRD 5.2.1 (Deutsch)','de','2024','pdf','CC-BY-4.0',10)")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [(1, "monster", "Nachtmahr", "Nightmare", "de", "2024", "350",
          "*Kontext: Monster*\n\nEin schauriges Pferd."),
         # Ohne Glossar-Zeile: Tippfehler landen hier NUR ueber den Fuzzy-Fallback
         # (mit Glossar-Zeile griffe vorher die Glossar-Bruecke).
         (1, "zauber", "Feuerball", None, "de", "2024", "241",
          "*Kontext: Zauber*\n\n8W6 Feuerschaden im Umkreis von sechs Metern.")])
    con.execute(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
        "VALUES ('Nightmare','Nachtmahr',1,'Spielerhandbuch 2024','2024')")
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    monkeypatch.setattr(_protokoll, "_fehler_in_folge", 0)
    return pfad


def _zeilen() -> list[dict]:
    con = _protokoll.verbinde_lesend()
    if con is None:
        return []
    try:
        return [dict(r) for r in con.execute("SELECT * FROM abfragen ORDER BY id")]
    finally:
        con.close()


def test_suche_schreibt_zeile_mit_suchweg(bestand):
    su.foliant_suche_bestand("Nachtmahr")                    # direkter FTS-Treffer
    su.foliant_suche_bestand("gibtesnichtxyz")               # ehrlicher Nulltreffer
    su.foliant_suche_bestand("Feurball")                     # Tippfehler -> fuzzy
    su.foliant_suche_bestand("Nacthmahr")                    # Tippfehler -> Glossar-Bruecke
    z = _zeilen()
    assert [r["werkzeug"] for r in z] == ["suche_bestand"] * 4
    assert z[0]["suchweg"] == "direkt" and z[0]["anzahl_treffer"] >= 1
    assert z[1]["suchweg"] == "-" and z[1]["anzahl_treffer"] == 0
    assert z[2]["suchweg"] == "fuzzy"
    assert z[3]["suchweg"].startswith("glossar:")
    assert all(r["dauer_ms"] is not None for r in z)


def test_detail_und_uebersetzung_werden_geloggt(bestand):
    ns.foliant_hol_eintrag("monster", "Nachtmahr")
    ns.foliant_uebersetze_begriff("Nightmare")
    ns.foliant_uebersetze_begriff("Totally Unknown Term")
    z = _zeilen()
    assert z[0]["werkzeug"] == "hol_monster" and z[0]["gefunden"] == 1
    assert z[0]["suchweg"] == "name"
    assert z[1]["werkzeug"] == "uebersetze_begriff" and z[1]["suchweg"] == "exakt"
    assert z[2]["gefunden"] == 0 and z[2]["suchweg"] == "-"


def test_kaputter_logpfad_bricht_lookup_nicht(bestand, tmp_path, monkeypatch):
    """Die wichtigste Leitplanke: das Log ist Beiwerk - ein unbeschreibbarer Pfad darf
    die fertige Antwort nie verwerfen."""
    monkeypatch.setattr(_protokoll, "protokoll_pfad",
                        lambda: tmp_path / "gibt-es-nicht" / "log.sqlite")
    antwort = su.foliant_suche_bestand("Nachtmahr")
    assert antwort["treffer"], "Lookup muss trotz Log-Fehler normal liefern"
    assert _protokoll._fehler_in_folge == 1


def test_logging_deaktiviert_sich_nach_fehlerserie(bestand, tmp_path, monkeypatch):
    monkeypatch.setattr(_protokoll, "protokoll_pfad",
                        lambda: tmp_path / "gibt-es-nicht" / "log.sqlite")
    monkeypatch.setattr(_protokoll, "_MAX_FEHLER", 3)
    for _ in range(5):
        _protokoll.protokolliere(werkzeug="suche_bestand", suchbegriff="x")
    # Nach 3 Fehlschlaegen in Folge schaltet protokoll_aktiv() ab - der Zaehler
    # waechst nicht weiter, weil gar kein Schreibversuch mehr stattfindet.
    assert _protokoll._fehler_in_folge == 3
    assert not _protokoll.protokoll_aktiv()


def test_rotation_deckelt_zeilenzahl(bestand, monkeypatch):
    monkeypatch.setattr(_protokoll, "max_zeilen", lambda: 5)
    monkeypatch.setattr(_protokoll, "_ROTATIONS_QUOTE", 1)   # Rotation bei jedem Write
    for i in range(12):
        _protokoll.protokolliere(werkzeug="suche_bestand", suchbegriff=f"begriff {i}")
    z = _zeilen()
    assert len(z) == 5
    assert z[-1]["suchbegriff"] == "begriff 11"              # die NEUESTEN ueberleben


def test_suchbericht_aggregiert_kurationssignale(bestand, capsys):
    su.foliant_suche_bestand("gibtesnichtxyz")
    su.foliant_suche_bestand("gibtesnichtxyz")
    su.foliant_suche_bestand("Feurball")                     # fuzzy
    ns.foliant_uebersetze_begriff("Totally Unknown Term")    # Glossar-Luecke
    adm.cmd_suchbericht(argparse.Namespace(tage=30, limit=10, json=True))
    bericht = json.loads(capsys.readouterr().out)
    assert bericht["anfragen_gesamt"] == 4
    assert bericht["nulltreffer"][0]["begriff"] == "gibtesnichtxyz"
    assert bericht["nulltreffer"][0]["anzahl"] == 2
    assert bericht["fuzzy_treffer"][0]["begriff"] == "feurball"
    assert bericht["uebersetzungs_luecken"][0]["begriff"] == "totally unknown term"
    assert bericht["dauer_ms_p50"] is not None


def test_suchbericht_ohne_protokoll_ist_freundlich(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(_protokoll, "protokoll_pfad", lambda: tmp_path / "leer.sqlite")
    adm.cmd_suchbericht(argparse.Namespace(tage=30, limit=10, json=False))
    assert "Kein Abfrage-Protokoll" in capsys.readouterr().out


def test_interne_sonden_landen_nicht_im_abfrage_protokoll(tmp_path, monkeypatch):
    """Protokolliert wird auf WERKZEUG-Ebene, nicht auf der internen Detailfunktion.

    Bis zum 31.07.2026 sass der Hook auf `_hole_detail`, die `app/tools/charakter.py`
    dreimal als interne Sonde ruft. Am Live-Protokoll gemessen stand dadurch
    'Schritt 3: Attributswerte' mit 186 Treffern als VIERTHAEUFIGSTER Suchbegriff im
    Bericht - hinter 'Feuerball' und 'Kämpfer'. Kein Nutzer hat das je gesucht. Umgekehrt
    tauchten die drei Charakter-Werkzeuge selbst nie auf. `admin suchbericht` ist die
    Kurationsliste (O4/M5); was darin steht, entscheidet ueber die naechste Handarbeit."""
    from app import protokoll as p
    from app.tools import charakter as ch
    from app.tools import nachschlagen as ns

    ziel = tmp_path / "prot.sqlite"
    monkeypatch.setattr(p, "protokoll_pfad", lambda: ziel)

    ch.foliant_hol_attributswerte("standard_array")   # ruft intern _hole_detail
    ch.foliant_pruefe_build("Kämpfer", 3)             # ruft intern _hole_detail
    ns.foliant_hol_eintrag("regel", "Kurze Rast")     # echter Werkzeugaufruf

    con = sqlite3.connect(ziel)
    try:
        begriffe = [r[0] for r in con.execute("SELECT suchbegriff FROM abfragen")]
    finally:
        con.close()
    assert "Schritt 3: Attributswerte" not in begriffe, (
        "interne Sonde im Abfrage-Protokoll - der Suchbericht meldet sie als "
        "Nutzeranfrage und verwaessert die Kurationsliste")
    assert len(begriffe) == 1, f"erwartet genau den Werkzeugaufruf, protokolliert: {begriffe}"
