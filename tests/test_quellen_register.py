"""Das Quellen-Register ist ein Wiederherstellungs-Artefakt - und muss es bleiben.

Anlass (Review 14.08.2026, K-01): `config/foliant.toml` ist gitignored, aus dem
Deploy-rsync ausgeschlossen und in keinem Backup. Pi und Mac trugen deshalb zwei
VERSCHIEDENE Register (12 gegen 8 Quellenbloecke, sieben Kuerzel disjunkt), und keines
beschrieb den Produktionsbestand vollstaendig - die sieben DDB-Quellen fehlten in beiden.
Faellt die SD-Karte aus, waeren Edition, Lizenz und Prioritaet jeder Quelle weg, und
geraten werden duerfen sie laut Kernregel 2 nicht.

Zwei Dinge haelt dieser Test fest: dass das eingecheckte Register zum Korpus-Sollstand
passt (sonst beschreibt es einen Bestand, den es nicht mehr gibt), und dass keine
Buchtitel hineinrutschen (Davids Entscheidung vom 14.08.2026 - das Repo ist oeffentlich).
"""
from __future__ import annotations

import json
import pathlib
import sqlite3

import pytest

from importer.quellen import REGISTER_FELDER, exportiere_register
from tests.hilfen import neue_db

WURZEL = pathlib.Path(__file__).resolve().parents[1]
REGISTER = WURZEL / "config" / "quellen-register.toml"
SOLL = WURZEL / "config" / "korpus_soll.json"


def _kuerzel_aus_register() -> list[str]:
    return [z.split("=", 1)[1].strip().strip('"')
            for z in REGISTER.read_text("utf-8").splitlines()
            if z.startswith("kuerzel =")]


def test_register_kennt_dieselben_quellen_wie_der_sollstand():
    """Zwei erzeugte Dateien ueber denselben Bestand - laufen sie auseinander, beschreibt
    mindestens eine einen Stand, den es nicht gibt. Genau so sind die beiden
    `foliant.toml` auseinandergelaufen."""
    soll = {q["kuerzel"] for q in json.loads(SOLL.read_text("utf-8"))["quellen"]}
    assert set(_kuerzel_aus_register()) == soll


def test_register_traegt_die_nicht_ratbaren_felder():
    """Edition und Prioritaet sind die Angaben, die Kernregel 2 verbietet zu raten -
    sie muessen bei JEDER Quelle stehen. Lizenz ebenso: sie entscheidet ueber die
    Attribution in der Ausgabe."""
    text = REGISTER.read_text("utf-8")
    bloecke = [b for b in text.split("[[quelle]]")[1:]]
    assert len(bloecke) == len(_kuerzel_aus_register())
    for block in bloecke:
        for feld in ("kuerzel", "sprache", "edition", "herkunft", "lizenz", "prioritaet",
                     "inhaltsart"):
            assert f"{feld} = " in block, f"{feld} fehlt in einem Quellenblock"


def test_register_enthaelt_keine_buchtitel():
    """Das Repo ist oeffentlich. Die Kuerzel stehen ohnehin darin, die Titel sollen nicht -
    auch nicht durch die Hintertuer eines Dateipfads."""
    assert "titel" not in REGISTER_FELDER
    for zeile in REGISTER.read_text("utf-8").splitlines():
        if zeile.startswith("#"):
            continue                       # der Kopf erklaert genau diese Auslassung
        assert not zeile.startswith("titel"), f"Buchtitel im Register: {zeile}"


def test_export_laesst_leere_felder_weg(tmp_path):
    """Ein `lizenz = ""` sieht aus wie eine Angabe und ist keine - bei einem Register,
    das im Ernstfall abgetippt wird, ist das der teurere Fehler."""
    con = neue_db(tmp_path / "t.sqlite")
    con.execute("INSERT INTO quellen (kuerzel, titel, sprache, edition, herkunft, lizenz, "
                "prioritaet, inhaltsart) VALUES ('x-en','Geheimer Titel','en','2024',"
                "'pdf',NULL,40,'regelwerk')")
    con.commit()
    text = exportiere_register(con, "2026-08-14")
    assert 'kuerzel = "x-en"' in text
    assert "lizenz" not in text.split("[[quelle]]")[1]
    assert "Geheimer Titel" not in text          # auch hier: kein Titel


def test_export_maskiert_anfuehrungszeichen(tmp_path):
    """Ein Wert mit Anfuehrungszeichen darf die TOML-Struktur nicht sprengen - sonst ist
    das Register im Ernstfall unlesbar, und der Ernstfall ist der einzige Fall."""
    con = neue_db(tmp_path / "t.sqlite")
    con.execute("INSERT INTO quellen (kuerzel, titel, sprache, edition, herkunft, lizenz, "
                "prioritaet, inhaltsart) VALUES ('y-en','T','en','2024','pdf',"
                "'sagt \"frei\"',40,'regelwerk')")
    con.commit()
    text = exportiere_register(con, "2026-08-14")
    assert r'lizenz = "sagt \"frei\""' in text
