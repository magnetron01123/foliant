"""Deutsch-Qualitaets-Gate (12.07.2026): schuetzt die Terminologie-Qualitaet - der Faktor,
an dem die Nutzung des MCP haengt. Kern: 'ein falscher deutscher Begriff ist schlimmer als
ein ehrliches *'. Deshalb (a) Kanonisierung (kuratierte Fassung schlaegt konkurrierende
dnddeutsch-Alt-/Schweizer-/Tippfehler-Form), (b) Audit laeuft, (c) Bestands-Invariante:
kein kuratierter Begriff traegt noch einen konkurrierenden OFFIZIELLEN deutschen Zweitbegriff.
"""
import json
import sqlite3
import types
from pathlib import Path

import pytest

from app import admin
from app import db as adb
from importer.import_glossar import (SRD_2024_BEGRIFFSPAARE, kanonisiere_konflikte,
                                     seed_kern_singulare, seed_srd_paare)

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def _leere_db(tmp_path, name="foliant.sqlite"):
    pfad = tmp_path / name
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.commit()
    con.close()
    return pfad


# --------------------------------------------------------------------------- Kanonisierung

def test_kanonisiere_demotet_konkurrenz_laesst_homonym(tmp_path):
    pfad = _leere_db(tmp_path)
    con = adb.connect(str(pfad))
    try:
        seed_srd_paare(con)            # u. a. Chain Lightning -> Kettenblitz (kuratiert, offiziell)
        # Konkurrenz-Zeile (dnddeutsch-Altform), offiziell=1 - das 'falsches Deutsch'-Risiko:
        con.execute("INSERT INTO glossar (term_en,term_de,offiziell,quelle) "
                    "VALUES ('Chain Lightning','Kugelblitz',1,'dnddeutsch.de (Community)')")
        # Echtes HOMONYM ohne kuratierte Fassung - muss UNBERUEHRT bleiben:
        con.executemany("INSERT INTO glossar (term_en,term_de,offiziell,quelle) VALUES (?,?,?,?)",
                        [("Hide", "Fell", 1, "x"), ("Hide", "Verstecken", 1, "x")])
        con.commit()

        demotet = kanonisiere_konflikte(con)
        assert demotet >= 1
        # Kuratierte Fassung bleibt offiziell:
        assert con.execute("SELECT offiziell FROM glossar WHERE term_en='Chain Lightning' "
                           "AND term_de='Kettenblitz'").fetchone()[0] == 1
        # Konkurrenz demotet (kein zweiter 'offizieller' Begriff mehr):
        assert con.execute("SELECT offiziell FROM glossar WHERE term_en='Chain Lightning' "
                           "AND term_de='Kugelblitz'").fetchone()[0] == 0
        # Homonym unberuehrt (beide bleiben offiziell - zwei echte Konzepte):
        hide = [r[0] for r in con.execute("SELECT offiziell FROM glossar WHERE term_en='Hide'")]
        assert hide == [1, 1]
    finally:
        con.close()


def test_kanonisierung_ist_idempotent(tmp_path):
    pfad = _leere_db(tmp_path)
    con = adb.connect(str(pfad))
    try:
        seed_srd_paare(con)
        seed_kern_singulare(con)
        con.execute("INSERT INTO glossar (term_en,term_de,offiziell,quelle) "
                    "VALUES ('Fly','Fliegen',1,'dnddeutsch')")
        con.commit()
        erst = kanonisiere_konflikte(con)
        zweit = kanonisiere_konflikte(con)          # zweiter Lauf findet nichts mehr
        assert erst >= 1 and zweit == 0
    finally:
        con.close()


# --------------------------------------------------------------------------- Audit

def test_glossar_audit_json(tmp_path, capsys):
    pfad = _leere_db(tmp_path)
    con = adb.connect(str(pfad))
    try:
        con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
                    "VALUES ('srd-de','x','de','2024','pdf',10)")
        con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
                    "VALUES ('open5e-srd-2024','y','en','2024','open5e',60)")
        con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,body_md) "
                    "VALUES (1,'zauber','Feuerball','de','2024','x')")
        # englischer Eintrag OHNE Bruecke -> muss als en_ohne zaehlen:
        con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_en,sprache,edition,body_md) "
                    "VALUES (2,'monster','Chain Devil','en','2024','y')")
        con.commit()
    finally:
        con.close()
    admin.cmd_glossar_audit(types.SimpleNamespace(db=str(pfad), luecken=5, json=True))
    bericht = json.loads(capsys.readouterr().out)
    monster = next(k for k in bericht["kategorien"] if k["kategorie"] == "monster")
    assert monster["en"] == 1 and monster["en_ohne"] == 1
    assert "Chain Devil" in monster["luecken_namen"]


# --------------------------------------------------------------------------- Bestands-Invariante

def test_bediente_db_kein_kuratierter_konflikt():
    """Am ECHTEN Bestand (skippt ohne DB): kein kuratierter term_en traegt noch einen
    KONKURRIERENDEN offiziellen deutschen Zweitbegriff - sonst waere die Kanonisierung nach
    einem Reseed zurueckgefallen (Regressionswaechter fuer die Deutsch-Qualitaet)."""
    pfad = adb.standard_pfad()
    if not pfad.exists():
        pytest.skip("keine bediente DB (data/foliant.sqlite) - Datenstufe uebersprungen")
    con = adb.connect_readonly(str(pfad))
    try:
        if not con.execute("SELECT count(*) FROM glossar").fetchone()[0]:
            pytest.skip("Glossar leer")
        kuratiert = {}
        for term_en, term_de in SRD_2024_BEGRIFFSPAARE:
            kuratiert.setdefault(term_en.lower(), set()).add(term_de)
        verstoesse = []
        for te, kanon in kuratiert.items():
            offizielle = {r[0] for r in con.execute(
                "SELECT term_de FROM glossar WHERE lower(term_en)=? AND offiziell=1", (te,))}
            fremd = offizielle - kanon
            if fremd:
                verstoesse.append((te, fremd))
        assert not verstoesse, f"Kuratierte Begriffe mit konkurrierendem Offiziell: {verstoesse}"
    finally:
        con.close()
