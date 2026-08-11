"""Datenkonzept-Verbesserungen (12.07.2026, Datenbank-Konzept-Review):
#1 admin backup (Online-Backup + Verifikation + Aufbewahrung),
#2 idempotenter Schema-Sicherstellungs-Schritt in db.connect() (inhaltsart + ehrliche user_version),
#3 zauber_meta/monster_meta aus Open5es nativen Feldern (Facetten-Seitenwagen) + Detail-Ausgabe.
"""
import re
import sqlite3
import types
from pathlib import Path

import pytest

from app import admin
from app import db as adb
from app.tools import nachschlagen as ns
from importer import facetten_seeder as seeder
from tests.hilfen import SCHEMA

_SCHEMA = SCHEMA
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
    """Alt-DB (v0, quellen OHNE inhaltsart) -> connect() zieht Spalte nach + user_version=3.

    Seit v3 gehoeren die vier Provenienz-Spalten dazu. Sie werden mitgeprueft, weil sie
    denselben Weg gehen und derselbe Fehler sie treffen wuerde: `CREATE TABLE IF NOT
    EXISTS` in schema.sql legt einer BESTEHENDEN Tabelle keine Spalte an - ohne den
    ALTER-Nachzug bekaeme der Pi sie erst bei einem Neuaufbau der Datenbank."""
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
        spalten = {r[1] for r in c.execute("PRAGMA table_info(quellen)")}
        assert "inhaltsart" in spalten
        assert {"importiert_am", "versions_stand", "quell_url", "quell_hash"} <= spalten
        assert c.execute("PRAGMA user_version").fetchone()[0] == 3
    finally:
        c.close()
    adb.connect(str(pfad)).close()                       # idempotent: zweiter Aufruf kein Fehler


def test_schema_ensure_senkt_hoehere_version_nicht(tmp_path):
    """Eine kuenftige v4 darf NICHT auf 3 zurueckgesetzt werden (nur anheben)."""
    pfad = tmp_path / "v4.sqlite"
    con = sqlite3.connect(pfad)
    con.execute("CREATE TABLE quellen (id INTEGER PRIMARY KEY, inhaltsart TEXT)")
    con.execute("PRAGMA user_version = 4")
    con.commit()
    con.close()
    c = adb.connect(str(pfad))
    try:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 4
    finally:
        c.close()


def test_schema_ensure_ruestet_die_nutzindizes_nach(tmp_path):
    """Audit 28.07.2026: die Indizes aus dem Initial-Commit deckten die realen Zugriffe
    nicht - quelle_id (Re-Import-DELETE) und die Namensspalten liefen als Full Scan.
    schema.sql legt sie fuer neue DBs an, dieser Punkt fuer die bestehenden."""
    pfad = tmp_path / "ohne-indizes.sqlite"
    con = sqlite3.connect(pfad)
    con.execute("CREATE TABLE quellen (id INTEGER PRIMARY KEY, kuerzel TEXT UNIQUE)")
    con.execute("CREATE TABLE eintraege (id INTEGER PRIMARY KEY, quelle_id INTEGER, "
                "kategorie TEXT, name_de TEXT, name_en TEXT, sprache TEXT, edition TEXT, "
                "seite TEXT, body_md TEXT)")
    con.commit()
    con.close()
    c = adb.connect(str(pfad))
    try:
        vorhanden = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        # Erwartung direkt aus der EINEN Schema-Datei lesen, nicht aus einer zweiten
        # Python-Liste (die gab es bis zum 31.07.2026 und musste von Hand synchron
        # gehalten werden). So deckt der Test auch jeden kuenftigen Index ab.
        erwartet = set(re.findall(r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (\w+)",
                                  _SCHEMA.read_text(encoding="utf-8")))
        assert erwartet, "keine Indizes in db/schema.sql gefunden - Regex pruefen"
        assert erwartet <= vorhanden, f"fehlend: {sorted(erwartet - vorhanden)}"
        # Und sie werden auch BENUTZT - sonst waeren sie nur Ballast.
        plan = " ".join(r[-1] for r in c.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM eintraege WHERE quelle_id = 1"))
        assert "idx_eintraege_quelle" in plan, plan
    finally:
        c.close()
    adb.connect(str(pfad)).close()                    # idempotent


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
    d = ns.foliant_hol_eintrag("zauber", "Fireball")
    assert d["gefunden"] is True
    assert d["facetten"] == {"grad": 3, "schule": "Hervorrufung", "klassen": "Wizard, Sorcerer"}
    assert "**Level:** 3" in d["regeltext_md"]           # Facetten ERGAENZEN, ersetzen body_md nie


def test_kein_facetten_feld_ohne_meta_zeile(tmp_path, monkeypatch):
    pfad = _baue_db(tmp_path)
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    d = ns.foliant_hol_eintrag("monster", "Goblin")                 # kein monster_meta-Eintrag angelegt
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


# ------------------------------------------------- Konfig-Cache (Lastmessung 28.07.2026)

def test_konfig_wird_gecacht_und_bei_aenderung_neu_gelesen(tmp_path, monkeypatch):
    """lade_konfig() las die TOML bei JEDEM Tool-Aufruf frisch vom Datentraeger und parste
    sie neu - `protokolliere` allein ruft zwei Konfig-Leser, `standard_pfad` einen weiteren.
    Der Cache haengt an (mtime, Groesse): eine geaenderte Datei wird beim naechsten Aufruf
    gelesen, ein Neustart ist nicht noetig."""
    datei = tmp_path / "foliant.toml"
    datei.write_text('[db]\npfad = "a.sqlite"\n', encoding="utf-8")
    monkeypatch.setattr(adb, "_KONFIG", datei)
    monkeypatch.setattr(adb, "_KONFIG_CACHE", None)

    assert adb.lade_konfig()["db"]["pfad"] == "a.sqlite"
    datei.write_text('[db]\npfad = "b.sqlite"\n', encoding="utf-8")
    import os
    os.utime(datei, (0, 0))                      # mtime erzwingen (gleiche Sekunde moeglich)
    assert adb.lade_konfig()["db"]["pfad"] == "b.sqlite", "Cache verschlaeft die Aenderung"


def test_konfig_cache_ueberlebt_mutation_durch_aufrufer(tmp_path, monkeypatch):
    """Ein Aufrufer, der am Ergebnis herumschreibt, darf den Cache nicht vergiften."""
    datei = tmp_path / "foliant.toml"
    datei.write_text('[protokoll]\naktiv = true\n', encoding="utf-8")
    monkeypatch.setattr(adb, "_KONFIG", datei)
    monkeypatch.setattr(adb, "_KONFIG_CACHE", None)

    erste = adb.lade_konfig()
    erste["protokoll"]["aktiv"] = False
    assert adb.lade_konfig()["protokoll"]["aktiv"] is True


def test_fehlende_konfig_ist_kein_fehler(tmp_path, monkeypatch):
    monkeypatch.setattr(adb, "_KONFIG", tmp_path / "gibtsnicht.toml")
    monkeypatch.setattr(adb, "_KONFIG_CACHE", None)
    assert adb.lade_konfig() == {}


def test_standard_pfad_nutzt_den_konfig_cache():
    """Befund 30.07.2026: standard_pfad parste config/foliant.toml bei JEDEM Aufruf frisch,
    obwohl der Cache elf Zeilen tiefer steht - und lade_konfig nennt `standard_pfad` im
    eigenen Docstring als einen der Aufrufer, die er entlasten sollte. Eine halb gelandete
    Aenderung, deren Kommentar 100 % behauptete.

    Geprueft wird die KOPPLUNG, nicht die Laufzeit: eine Zeitmessung waere auf fremder
    Hardware flatterig. Faellt der Cache-Aufruf wieder weg, zaehlt der Zaehler nicht mehr
    mit und der Test schlaegt an."""
    from app import db as adb

    aufrufe = []
    echt = adb.lade_konfig
    try:
        adb.lade_konfig = lambda: (aufrufe.append(1), echt())[1]
        adb.standard_pfad()
    finally:
        adb.lade_konfig = echt
    assert aufrufe, "standard_pfad liest die TOML wieder am Cache vorbei"


def test_ranking_faltet_diakritika_wie_die_gruppierung(tmp_path, monkeypatch):
    """Der Gruppenschluessel in _dedupe_und_sortiere faltet Diakritika (norm_begriff), der
    Exakt-Namens-Boost daneben tat es nicht (eigene .lower()-Kopie db._norm). Eine Anfrage
    OHNE Umlaut verlor dadurch die Namensgleichheit und damit den Boost.

    Gemessen am echten Bestand ueber 120 Namen mit Diakritika: 6 rankten anders, 3 mit
    einem ANDEREN Top-Treffer ('Fluche' -> 'Fluch' statt 'Flueche'). Das ist der
    Alltagsfall, nicht der Sonderfall - auf einer Handy-Tastatur schreibt niemand Umlaute.
    norm_begriff sagt genau das in seinem eigenen Docstring (A3).

    Geprueft wird seit dem 06.08.2026 das VERHALTEN, nicht der Quelltext: die fruehere
    `inspect.getsource`-Regex auf `_dedupe_und_sortiere` hielt eine Schreibweise fest, kein
    Ergebnis - sie waere gruen geblieben, wenn die Faltung an einer anderen Stelle der
    Kette weggefallen waere, und rot bei einer harmlosen Umbenennung.

    Der Aufbau ist genau der Fall aus dem Docstring: 'Fluch' steht im rohen FTS-Lauf VORN
    (sein Rumpf nennt den Suchbegriff mehrfach), nur der diakritika-feste Exakt-Boost hebt
    'Flüche' darueber. Faellt die Faltung weg, dreht sich die Reihenfolge."""
    from app.glossar import norm_begriff
    from app.tools import suche as su

    pfad = tmp_path / "diakritika.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,"
                "prioritaet) VALUES ('srd-de','SRD 5.2.1 (Deutsch)','de','2024','pdf',"
                "'CC-BY-4.0',10)")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (1,'regel',?,NULL,'de','2024',?,?)",
        [("Flüche", "1", "Sammelabschnitt ueber magische Buerden. " + "Fuelltext " * 80),
         ("Fluch", "2", "Fluch Fluch Fluch Flüche Flüche Flüche Flüche")])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)

    for anfrage in ("Fluche", "Flüche"):     # ohne und mit Umlaut - dasselbe Ergebnis
        treffer = su.foliant_suche_bestand(anfrage)["treffer"]
        assert treffer and treffer[0]["name_de"] == "Flüche", (anfrage, treffer)
    assert norm_begriff("Flüche") == norm_begriff("Fluche")


def test_ddb_artefakt_kennt_dieselben_kategorien():
    """`importer/ddb_artefakt.KATEGORIEN_ERLAUBT` ist eine bewusste KOPIE von
    `app.db.KATEGORIEN` - das Modul ist architekturneutral und laeuft auch im separaten
    Exporter-Venv, wo die App-Abhaengigkeiten fehlen; ein Import zoege sie herein.

    Eine Kopie ohne Waechter laeuft aber auseinander, und der Schaden waere still: Eine
    neue Kategorie in app.db, die hier fehlt, laesst die Artefakt-Validierung jeden Eintrag
    dieser Kategorie abweisen - der DDB-Import verlaese sich auf 'kenne ich nicht' statt
    zu importieren. Dieser Test laeuft im HAUPT-Testlauf und sieht damit beide Seiten."""
    from importer import ddb_artefakt

    assert ddb_artefakt.KATEGORIEN_ERLAUBT == set(adb.KATEGORIEN)


def test_neue_db_nimmt_alle_inhaltsarten_an(tmp_path):
    """Eine frisch angelegte Datenbank muss alle vier inhaltsart-Werte annehmen.

    Vorgeschichte (31.07.2026): Das Schema trug einen CHECK auf diese Spalte. Beim Zuwachs
    um 'errata'/'regelauslegung' zeigte sich, dass er eine Migrationsfalle ist - `CREATE
    TABLE IF NOT EXISTS` erneuert eine BESTEHENDE Tabelle nicht, `ALTER TABLE` erzeugt
    keine Constraint, und der alte CHECK quittierte den ersten Errata-Import mit
    'IntegrityError'. Der Wertraum steht seither allein in `importer/quellen.INHALTSARTEN`,
    und dieser Test haelt fest, dass das Schema ihn nicht wieder einschraenkt."""
    import pytest
    from importer.quellen import INHALTSARTEN, registriere_quelle

    pfad = tmp_path / "frisch.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.commit()
    con.close()

    c = adb.connect(str(pfad))
    try:
        for art in sorted(INHALTSARTEN):
            registriere_quelle(c, kuerzel=f"q-{art}", titel="T", sprache="en",
                               edition="2024", herkunft="pdf", inhaltsart=art)
        c.commit()
        assert {r[0] for r in c.execute("SELECT inhaltsart FROM quellen")} == INHALTSARTEN
        # Der Validator bleibt die Leitplanke - ein Tippfehler kommt weiterhin nicht durch,
        # und zwar auf JEDER Datenbank, auch ohne CHECK (SPEC.md par. 7: alles ausser
        # 'abenteuer_setting' gilt der Ausgabe als unmarkiert).
        with pytest.raises(ValueError, match="inhaltsart"):
            registriere_quelle(c, kuerzel="q-tippfehler", titel="T", sprache="en",
                               edition="2024", herkunft="pdf", inhaltsart="abenteur_setting")
    finally:
        c.close()


def test_check_meldet_eine_datenbank_mit_veraltetem_check(tmp_path, capsys):
    """Eine Datenbank, die den alten v2-CHECK noch traegt, kann der Schema-Nachzug NICHT
    heilen (einen CHECK aendert SQLite nur ueber einen Tabellen-Neuaufbau, und ein
    automatischer DROP TABLE auf dem Produktionsbestand ist kein Migrationsschritt).

    Also muss sie wenigstens AUFFALLEN, bevor der erste Errata-Import mit einem
    IntegrityError abbricht - mit dem Weg dazu in der Meldung."""
    from app.admin import _pruefe_inhaltsarten

    pfad = tmp_path / "v2-mit-check.sqlite"
    con = sqlite3.connect(pfad)
    con.execute("CREATE TABLE quellen (id INTEGER PRIMARY KEY, kuerzel TEXT UNIQUE NOT NULL, "
                "titel TEXT NOT NULL, sprache TEXT NOT NULL, edition TEXT NOT NULL, "
                "herkunft TEXT NOT NULL, lizenz TEXT, prioritaet INTEGER NOT NULL DEFAULT 100, "
                "inhaltsart TEXT NOT NULL DEFAULT 'regelwerk' "
                "  CHECK (inhaltsart IN ('regelwerk','abenteuer_setting')), "
                "dateipfad TEXT)")
    con.commit()

    assert _pruefe_inhaltsarten(con) == 1
    ausgabe = capsys.readouterr().out
    assert "VERALTETER CHECK" in ausgabe
    assert "admin backup" in ausgabe          # der Weg steht in der Meldung
    con.close()

    # Gegenprobe: die aktuelle Schema-Datei loest die Meldung NICHT aus.
    sauber = tmp_path / "aktuell.sqlite"
    c2 = sqlite3.connect(sauber)
    c2.executescript(_SCHEMA.read_text(encoding="utf-8"))
    c2.commit()
    assert _pruefe_inhaltsarten(c2) == 0
    c2.close()
