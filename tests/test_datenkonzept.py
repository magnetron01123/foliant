"""Datenkonzept-Verbesserungen (12.07.2026, Datenbank-Konzept-Review):
#1 admin backup (Online-Backup + Verifikation + Aufbewahrung),
#2 idempotenter Schema-Sicherstellungs-Schritt in db.connect() (inhaltsart + ehrliche user_version),
#3 zauber_meta/monster_meta aus Open5es nativen Feldern (Facetten-Seitenwagen) + Detail-Ausgabe.
"""
import sqlite3
import types
from pathlib import Path

import pytest

from app import admin
from app import db as adb
from app.tools import nachschlagen as ns
from importer import facetten_seeder as seeder

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def _baue_db(tmp_path, name="foliant.sqlite"):
    """Schema + eine Open5e-Quelle, ein Zauber MIT zauber_meta, ein Monster OHNE Facette."""
    pfad = tmp_path / name
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
                "VALUES ('open5e-srd-2024','SRD 5.2 (Open5e)','en','2024','open5e','CC-BY-4.0',60)")
    qid = con.execute("SELECT id FROM quellen").fetchone()[0]
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,"
                "seite,body_md) VALUES (?, 'zauber', NULL,'Fireball','en','2024',NULL,?)",
                (qid, "**Level:** 3, **School:** Evocation\n\nA bright streak flashes ..."))
    zid = con.execute("SELECT id FROM eintraege WHERE name_en='Fireball'").fetchone()[0]
    # Wertraum wie der Seeder ihn schreibt: kanonischer Schul-Schluessel, nicht die
    # englische Anzeigeform - die Ausgabe uebersetzt ihn nach 'Hervorrufung' (Deutsch-first).
    con.execute("INSERT INTO zauber_meta (eintrag_id,grad,schule,klassen) "
                "VALUES (?,3,'hervorrufung','Wizard, Sorcerer')", (zid,))
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,"
                "seite,body_md) VALUES (?, 'monster', NULL,'Goblin','en','2024',NULL,?)",
                (qid, "**CR** 1/4\n\nSmall humanoid ..."))
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    return pfad


# --------------------------------------------------------------------------- #2

def test_schema_ensure_zieht_inhaltsart_nach_und_setzt_version(tmp_path):
    """Alt-DB (v0, quellen OHNE inhaltsart) -> connect() zieht Spalte nach + user_version=2."""
    pfad = tmp_path / "alt.sqlite"
    con = sqlite3.connect(pfad)
    con.execute("CREATE TABLE quellen (id INTEGER PRIMARY KEY, kuerzel TEXT UNIQUE NOT NULL, "
                "titel TEXT NOT NULL, sprache TEXT NOT NULL, edition TEXT NOT NULL, "
                "herkunft TEXT NOT NULL, lizenz TEXT, prioritaet INTEGER NOT NULL DEFAULT 100, "
                "dateipfad TEXT)")
    con.commit()
    con.close()
    con = sqlite3.connect(pfad)                          # Vorbedingung pruefen
    assert con.execute("PRAGMA user_version").fetchone()[0] == 0
    assert "inhaltsart" not in {r[1] for r in con.execute("PRAGMA table_info(quellen)")}
    con.close()

    c = adb.connect(str(pfad))                           # der Migrationspunkt
    try:
        assert "inhaltsart" in {r[1] for r in c.execute("PRAGMA table_info(quellen)")}
        assert c.execute("PRAGMA user_version").fetchone()[0] == 2
    finally:
        c.close()
    adb.connect(str(pfad)).close()                       # idempotent: zweiter Aufruf kein Fehler


def test_schema_ensure_senkt_hoehere_version_nicht(tmp_path):
    """Eine kuenftige v3 darf NICHT auf 2 zurueckgesetzt werden (nur anheben)."""
    pfad = tmp_path / "v3.sqlite"
    con = sqlite3.connect(pfad)
    con.execute("CREATE TABLE quellen (id INTEGER PRIMARY KEY, inhaltsart TEXT)")
    con.execute("PRAGMA user_version = 3")
    con.commit()
    con.close()
    c = adb.connect(str(pfad))
    try:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 3
    finally:
        c.close()


def test_schema_ensure_ist_no_op_ohne_quellen(tmp_path):
    """Uninitialisierte DB (keine quellen-Tabelle) -> kein Crash, nichts angelegt."""
    c = adb.connect(str(tmp_path / "leer.sqlite"))
    try:
        assert not c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='quellen'").fetchone()
    finally:
        c.close()


# --------------------------------------------------------------------------- #3 (Import)
# Der frühere Open5e-Sonderweg (_facetten/_schreibe_facetten aus den nativen API-Feldern)
# ist am 28.07.2026 entfallen: er schrieb in einen ZWEITEN Wertraum ('10.0' statt '10',
# 'Evocation' statt 'hervorrufung'). Die Facetten schreibt jetzt für ALLE Quellen
# importer/facetten_seeder.py — Tests dafür in tests/test_facetten_seeder.py.

def test_facetten_cascade_beim_reimport(tmp_path):
    """FK ON DELETE CASCADE: der Re-Import-DELETE räumt die Meta-Zeilen mit weg."""
    pfad = tmp_path / "wiring.sqlite"
    con0 = sqlite3.connect(pfad)
    con0.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con0.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
                 "VALUES ('open5e-srd-2024','x','en','2024','open5e',60)")
    con0.commit()
    con0.close()
    con = adb.connect(str(pfad))                         # foreign_keys=ON via connect()
    try:
        qid = con.execute("SELECT id FROM quellen").fetchone()[0]
        con.executemany(
            "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,"
            "seite,body_md) VALUES (?,?,NULL,?, 'en','2024',NULL,?)",
            [(qid, "zauber", "Fireball", "**Level:** 3 · **School:** Evocation"),
             (qid, "monster", "Goblin", "**CR** 1/4 Small humanoid **AC** 15 **HP** 7")])
        with con:
            assert seeder.seed_facetten(con, qid)["zauber"] == 1
        assert con.execute("SELECT count(*) FROM zauber_meta").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM monster_meta").fetchone()[0] == 1
        con.execute("DELETE FROM eintraege WHERE quelle_id=?", (qid,))   # Re-Import-Simulation
        con.commit()
        assert con.execute("SELECT count(*) FROM zauber_meta").fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM monster_meta").fetchone()[0] == 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #3 (Konsument)

def test_facetten_im_zauber_detail(tmp_path, monkeypatch):
    pfad = _baue_db(tmp_path)
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    d = ns.foliant_hol_zauber("Fireball")
    assert d["gefunden"] is True
    assert d["facetten"] == {"grad": 3, "schule": "Hervorrufung", "klassen": "Wizard, Sorcerer"}
    assert "**Level:** 3" in d["regeltext_md"]           # Facetten ERGAENZEN, ersetzen body_md nie


def test_kein_facetten_feld_ohne_meta_zeile(tmp_path, monkeypatch):
    pfad = _baue_db(tmp_path)
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    d = ns.foliant_hol_monster("Goblin")                 # kein monster_meta-Eintrag angelegt
    assert d["gefunden"] is True
    assert "facetten" not in d                            # ehrlich: kein Feld statt leeres/geratenes


# --------------------------------------------------------------------------- #1 (Backup)

def test_backup_erstellt_und_verifiziert(tmp_path, monkeypatch):
    pfad = _baue_db(tmp_path)
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    ziel = tmp_path / "bkp"
    admin.cmd_backup(types.SimpleNamespace(ziel=str(ziel), behalten=14))
    dateien = list(ziel.glob("foliant-*.sqlite"))
    assert len(dateien) == 1
    v = sqlite3.connect(f"file:{dateien[0]}?mode=ro", uri=True)
    try:
        assert v.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert v.execute("SELECT count(*) FROM eintraege").fetchone()[0] == 2
    finally:
        v.close()


def test_backup_aufbewahrung(tmp_path, monkeypatch):
    pfad = _baue_db(tmp_path)
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    ziel = tmp_path / "bkp"
    ziel.mkdir()
    for tag in ("20200101-000000", "20200102-000000", "20200103-000000",
                "20200104-000000", "20200105-000000"):
        (ziel / f"foliant-{tag}.sqlite").write_bytes(b"alt")
    admin.cmd_backup(types.SimpleNamespace(ziel=str(ziel), behalten=3))
    rest = sorted(p.name for p in ziel.glob("foliant-*.sqlite"))
    assert len(rest) == 3                                 # 2 neueste Dummys + das echte (heute)
    assert "foliant-20200101-000000.sqlite" not in rest   # aelteste entfernt
    assert "foliant-20200103-000000.sqlite" not in rest


def test_backup_verwirft_bei_fehlender_db(tmp_path, monkeypatch):
    monkeypatch.setattr(adb, "standard_pfad", lambda: tmp_path / "gibtsnicht.sqlite")
    with pytest.raises(SystemExit):
        admin.cmd_backup(types.SimpleNamespace(ziel=str(tmp_path / "bkp"), behalten=14))
