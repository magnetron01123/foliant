"""Tests fuer den DDB-Artefaktvertrag (importer/ddb_artefakt.py) und den Offline-Import
(importer/import_ddb.py) - vollstaendig synthetisch, ohne Netz, ohne echte Secrets/Texte.

Kerninvarianten (DDB-Auftrag): fehlerhafte/leere/geschrumpfte Artefakte aendern NICHTS;
die OEFFENTLICHE DB bleibt byteweise unveraendert; Aktivierung der privaten Kandidaten-DB
ist atomar; Re-Import ist idempotent."""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from importer.ddb_artefakt import kategorie_aus_breadcrumb, pruefe_artefakt
from importer.import_ddb import importiere_ddb_artefakt

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ddb"

_BUCH = {"id": 999999, "kuerzel": "ddb-synthetic-en", "titel": "Synthetic Handbook (Fixture)",
         "sprache": "en", "edition": "2024", "lizenz": "privat", "prioritaet": 40}


def _artefakt_kopie(tmp_path: Path) -> Path:
    ziel = tmp_path / "artefakt" / "export-1"
    ziel.mkdir(parents=True, exist_ok=True)
    shutil.copy(_FIXTURE / "manifest-v1.json", ziel / "manifest.json")
    shutil.copy(_FIXTURE / "entries-v1.jsonl", ziel / "entries.jsonl")
    return ziel


def _schreibe_artefakt(tmp_path: Path, eintraege: list[dict], **manifest_override) -> Path:
    """Synthetisches Artefakt mit KORREKTEN Hashes bauen (Fehlerfaelle via override)."""
    ziel = tmp_path / "artefakt" / "export-x"
    ziel.mkdir(parents=True, exist_ok=True)
    for e in eintraege:
        e.setdefault("body_sha256",
                     hashlib.sha256(e["body_md"].encode("utf-8")).hexdigest())
        e.setdefault("breadcrumb", ["Synthetic Handbook"])
        e.setdefault("category", "regel")
        e.setdefault("title", f"Titel {e['ddb_id']}")
    jsonl = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in eintraege)
    (ziel / "entries.jsonl").write_text(jsonl, encoding="utf-8")
    manifest = {"schema_version": 1, "status": "complete",
                "source_key": _BUCH["kuerzel"], "ddb_source_id": _BUCH["id"],
                "title": _BUCH["titel"], "language": "en", "edition": "2024",
                "license": "privat", "exported_at": "2026-07-10T13:00:00Z",
                "entry_count": len(eintraege),
                "entries_sha256": hashlib.sha256(jsonl.encode("utf-8")).hexdigest()}
    manifest.update(manifest_override)
    (ziel / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return ziel


@pytest.fixture()
def dbs(tmp_path):
    """Oeffentliche Basis-DB (mit einem Nicht-DDB-Eintrag) + Pfad fuer die private DB."""
    oeffentlich = tmp_path / "foliant.sqlite"
    con = sqlite3.connect(oeffentlich)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,"
                "prioritaet) VALUES ('srd-de','SRD (Deutsch)','de','2024','pdf','CC-BY-4.0',10)")
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,"
                "edition,seite,body_md) VALUES (1,'zauber','Feuerball',NULL,'de','2024',"
                "'139','8W6 Feuerschaden.')")
    con.commit()
    con.close()
    return {"oeffentlich": oeffentlich, "privat": tmp_path / "private" / "foliant-private.sqlite"}


def _hash(pfad: Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


# ------------------------------- Artefaktvertrag -------------------------------

def test_vertrags_fixture_ist_gueltig(tmp_path):
    g = pruefe_artefakt(_artefakt_kopie(tmp_path), erwartet={
        "source_key": _BUCH["kuerzel"], "ddb_source_id": _BUCH["id"],
        "language": "en", "edition": "2024"})
    assert g["manifest"]["entry_count"] == 3 and len(g["eintraege"]) == 3
    assert g["fehlende_parents"] == 0


def test_kategorien_mapping_breadcrumb():
    assert kategorie_aus_breadcrumb(["PHB", "Spells", "X"]) == "zauber"
    assert kategorie_aus_breadcrumb(["PHB", "Monsters"]) == "monster"
    assert kategorie_aus_breadcrumb(["PHB", "Bestiary", "A"]) == "monster"
    assert kategorie_aus_breadcrumb(["PHB", "Equipment"]) == "gegenstand"
    assert kategorie_aus_breadcrumb(["PHB", "Magic Items", "B"]) == "gegenstand"
    assert kategorie_aus_breadcrumb(["PHB", "Classes", "Fighter"]) == "klasse"
    assert kategorie_aus_breadcrumb(["PHB", "Species"]) == "spezies"
    assert kategorie_aus_breadcrumb(["PHB", "Races"]) == "spezies"
    assert kategorie_aus_breadcrumb(["PHB", "Backgrounds"]) == "hintergrund"
    assert kategorie_aus_breadcrumb(["PHB", "Feats"]) == "talent"
    assert kategorie_aus_breadcrumb(["PHB", "Chapter 7: Using Ability Scores"]) == "regel"


@pytest.mark.parametrize("kaputt, fehler", [
    ({"status": "partial"}, "complete"),
    ({"schema_version": 99}, "schema_version"),
    ({"edition": "2014"}, "erwartet"),
    ({"entries_sha256": "0" * 64}, "Hash"),
    ({"entry_count": 7}, "entry_count"),
])
def test_manifest_fehler_werden_abgelehnt(tmp_path, kaputt, fehler):
    a = _schreibe_artefakt(tmp_path, [{"ddb_id": "1", "body_md": "Text."}], **kaputt)
    with pytest.raises(ValueError, match=fehler):
        pruefe_artefakt(a, erwartet={"source_key": _BUCH["kuerzel"], "edition": "2024"})


def test_eintrags_fehler_werden_abgelehnt(tmp_path):
    with pytest.raises(ValueError, match="doppelte ddb_id"):
        pruefe_artefakt(_schreibe_artefakt(tmp_path, [
            {"ddb_id": "1", "body_md": "A."}, {"ddb_id": "1", "body_md": "B."}]))
    with pytest.raises(ValueError, match="body_sha256"):
        pruefe_artefakt(_schreibe_artefakt(
            tmp_path, [{"ddb_id": "1", "body_md": "A.", "body_sha256": "f" * 64}]))
    with pytest.raises(ValueError, match="Zyklus"):
        pruefe_artefakt(_schreibe_artefakt(tmp_path, [
            {"ddb_id": "1", "parent_id": "2", "body_md": "A."},
            {"ddb_id": "2", "parent_id": "1", "body_md": "B."}]))
    with pytest.raises(ValueError, match="nicht-leeren"):
        pruefe_artefakt(_schreibe_artefakt(tmp_path, [{"ddb_id": "1", "body_md": " "}]))


def test_partial_verzeichnis_nie_importierbar(tmp_path):
    a = _schreibe_artefakt(tmp_path, [{"ddb_id": "1", "body_md": "Text."}])
    partial = a.parent / ".partial-abc"
    a.rename(partial)
    with pytest.raises(ValueError, match="partial"):
        pruefe_artefakt(partial)


# ------------------------------- Offline-Import -------------------------------

def test_import_aktiviert_private_db_und_laesst_oeffentliche_unveraendert(tmp_path, dbs):
    vorher = _hash(dbs["oeffentlich"])
    bericht = importiere_ddb_artefakt(_artefakt_kopie(tmp_path), _BUCH,
                                      oeffentliche_db=dbs["oeffentlich"],
                                      private_db=dbs["privat"])
    assert _hash(dbs["oeffentlich"]) == vorher            # byteweise unveraendert
    assert dbs["privat"].exists() and bericht["aktiviert"] == str(dbs["privat"])
    con = sqlite3.connect(f"file:{dbs['privat']}?mode=ro", uri=True)
    try:
        n = con.execute("SELECT count(*) FROM eintraege e JOIN quellen q ON "
                        "q.id=e.quelle_id WHERE q.kuerzel='ddb-synthetic-en'").fetchone()[0]
        assert n == 3
        assert con.execute("SELECT lizenz, herkunft FROM quellen WHERE "
                           "kuerzel='ddb-synthetic-en'").fetchone() == ("privat", "ddb")
        # oeffentlicher Bestand ist in der privaten DB weiter enthalten (Kopie-Basis):
        assert con.execute("SELECT count(*) FROM eintraege WHERE name_de='Feuerball'"
                           ).fetchone()[0] == 1
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()
    assert bericht["kategorien"] == {"monster": 1, "regel": 1, "zauber": 1}
    assert "nicht ueber den authlosen" in bericht["hinweis"]


def test_import_in_bedienten_bestand_merged_und_erhaelt(tmp_path, dbs):
    """Eigentuemer-Modus (B2 bewusst aufgehoben): ziel_db == bediente DB. DDB wird IN die
    bediente DB gemerged, bestehende Inhalte (Feuerball) bleiben, atomar aktiviert."""
    served = dbs["oeffentlich"]                       # ziel == bediente DB
    bericht = importiere_ddb_artefakt(_artefakt_kopie(tmp_path), _BUCH,
                                      oeffentliche_db=served, private_db=served)
    assert bericht["aktiviert"] == str(served)
    con = sqlite3.connect(f"file:{served}?mode=ro", uri=True)
    try:
        assert con.execute("SELECT count(*) FROM eintraege WHERE name_de='Feuerball'"
                           ).fetchone()[0] == 1            # Altbestand erhalten
        assert con.execute("SELECT count(*) FROM eintraege e JOIN quellen q ON "
                           "q.id=e.quelle_id WHERE q.herkunft='ddb'").fetchone()[0] == 3
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()


def test_dry_run_aendert_nichts(tmp_path, dbs):
    vorher = _hash(dbs["oeffentlich"])
    bericht = importiere_ddb_artefakt(_artefakt_kopie(tmp_path), _BUCH,
                                      oeffentliche_db=dbs["oeffentlich"],
                                      private_db=dbs["privat"], dry_run=True)
    assert bericht["dry_run"] is True and bericht["eintraege_neu"] == 3
    assert not dbs["privat"].exists()
    assert _hash(dbs["oeffentlich"]) == vorher
    assert not list(dbs["privat"].parent.glob("*.kandidat.sqlite"))


def test_fehlerhaftes_artefakt_laesst_alles_unveraendert(tmp_path, dbs):
    importiere_ddb_artefakt(_artefakt_kopie(tmp_path), _BUCH,
                            oeffentliche_db=dbs["oeffentlich"], private_db=dbs["privat"])
    privat_vorher = _hash(dbs["privat"])
    kaputt = _schreibe_artefakt(tmp_path, [{"ddb_id": "1", "body_md": "X."}],
                                entries_sha256="0" * 64)
    with pytest.raises(ValueError):
        importiere_ddb_artefakt(kaputt, _BUCH, oeffentliche_db=dbs["oeffentlich"],
                                private_db=dbs["privat"])
    assert _hash(dbs["privat"]) == privat_vorher
    assert not list(dbs["privat"].parent.glob("*.kandidat.sqlite"))


def test_schrumpf_schutz_und_force(tmp_path, dbs):
    importiere_ddb_artefakt(_artefakt_kopie(tmp_path), _BUCH,
                            oeffentliche_db=dbs["oeffentlich"], private_db=dbs["privat"])
    klein = _schreibe_artefakt(tmp_path, [{"ddb_id": "9", "body_md": "Nur einer."}])
    with pytest.raises(ValueError, match="Schrumpf"):
        importiere_ddb_artefakt(klein, _BUCH, oeffentliche_db=dbs["oeffentlich"],
                                private_db=dbs["privat"])
    bericht = importiere_ddb_artefakt(klein, _BUCH, oeffentliche_db=dbs["oeffentlich"],
                                      private_db=dbs["privat"], erlaube_schrumpfen=True)
    assert bericht["eintraege_neu"] == 1 and bericht["backup"]
    assert Path(bericht["backup"]).exists()               # Backup der vorherigen privaten DB


def test_reimport_idempotent(tmp_path, dbs):
    a = _artefakt_kopie(tmp_path)
    for _ in range(2):
        bericht = importiere_ddb_artefakt(a, _BUCH, oeffentliche_db=dbs["oeffentlich"],
                                          private_db=dbs["privat"])
    assert bericht["eintraege_neu"] == 3 and bericht["eintraege_alt"] == 3
    con = sqlite3.connect(f"file:{dbs['privat']}?mode=ro", uri=True)
    try:
        assert con.execute("SELECT count(*) FROM eintraege").fetchone()[0] == 4  # 3 + Feuerball
        n_f = con.execute("SELECT count(*) FROM eintraege_fts").fetchone()[0]
        assert n_f == 4                                   # FTS synchron
    finally:
        con.close()


def test_zerlege_eintrag_heading_split():
    """Ein DDB-Abschnitt mit ###-Unterbegriffen wird in Einzeleintraege zerlegt;
    ein Abschnitt ohne Unterheadings bleibt unveraendert (nie Inhalt verlieren)."""
    from importer.import_ddb import _zerlege_eintrag
    gross = {"title": "Rules Definitions", "category": "regel",
             "body_md": "## Rules Definitions\n\n### Ability Check\n\nText A ausreichend "
                        "lang fuer die Schwelle.\n\n### Advantage\n\nText B ebenfalls lang "
                        "genug fuer den Schwellwert im Splitter."}
    teile = _zerlege_eintrag(gross)
    namen = [t["name"] for t in teile]
    assert "Ability Check" in namen and "Advantage" in namen
    assert any("Text A" in t["body_md"] for t in teile)

    klein = {"title": "Kurzer Abschnitt", "category": "monster",
             "body_md": "## Kurzer Abschnitt\n\nNur ein Absatz ohne Unterheadings."}
    teile2 = _zerlege_eintrag(klein)
    assert len(teile2) == 1 and teile2[0]["name"] == "Kurzer Abschnitt"


def test_kapitel_header_werden_verworfen():
    """QS-Fund: generische DDB-Kapitel-Titel ('Species Descriptions', 'Feats', 'Equipment',
    'Magic Items') lecken als eigene Eintraege in Options-Kategorien und verschmutzen die
    Charakter-Listen. _ist_kapitel_header erkennt sie exakt+case-insensitiv; echte Optionen
    ('Elf', 'Fireball', 'Soldier', 'Fire Bolt') bleiben unberuehrt."""
    from importer.import_ddb import _ist_kapitel_header
    for header in ("Species", "Species Descriptions", "Backgrounds", "Feats",
                   "Feat Descriptions", "Equipment", "Magic Items", "Spells",
                   "spell descriptions", "  Classes  ", "Character Origins",
                   "Character Classes", "Subclasses",
                   "Origin Feats", "General Feats", "Fighting Style Feats", "Epic Boon Feats",
                   "Chapter 5: Feats", "Chapter 12: Monsters", "Ch. 11: Spells"):
        assert _ist_kapitel_header(header), header
    # ECHTER Regeltext mit header-aehnlichem Namen MUSS bleiben (nie Inhalt loeschen) -
    # ebenso echte Optionen und Kapitel-lose Namen.
    for echt in ("Elf", "Fireball", "Soldier", "Fire Bolt", "Longsword", "Aboleth",
                 "Spellcasting", "Second Wind", "Aasimar Traits", "Barbarian Class Features",
                 "Level 3 Wizard Spells", "Life Domain Spells", "Chapterhouse", "", None):
        assert not _ist_kapitel_header(echt), echt


def test_backup_rotation_behaelt_juengste_und_schont_pre_ddb(tmp_path):
    """QS-Prozess: Auto-Sicherungen duerfen die Pi-SD nicht unbegrenzt fluten. _rotiere_backups
    behaelt die N juengsten '<stem>.backup-*.sqlite' und loescht aeltere - die einmalige
    Pre-DDB-Sicherung '<name>.sqlite.backup-*' hat ein ANDERES Muster und bleibt unberuehrt."""
    import os as _os

    from importer.import_ddb import _rotiere_backups
    db = tmp_path / "foliant.sqlite"
    db.write_bytes(b"aktuell")
    pre_ddb = tmp_path / "foliant.sqlite.backup-2026-07-01"     # einmalige Vorab-Sicherung
    pre_ddb.write_bytes(b"unberuehrbar")
    # Fuenf Auto-Sicherungen mit aufsteigender mtime (juengste zuletzt).
    sicherungen = []
    for i in range(5):
        p = tmp_path / f"foliant.backup-2026-07-1{i}T000000+0000.sqlite"
        p.write_bytes(b"x")
        _os.utime(p, (1_700_000_000 + i, 1_700_000_000 + i))
        sicherungen.append(p)

    geloescht = _rotiere_backups(db, behalten=3)

    uebrig = sorted(p.name for p in tmp_path.glob("foliant.backup-*.sqlite"))
    assert len(uebrig) == 3, uebrig                            # nur 3 juengste bleiben
    assert sicherungen[0] in geloescht and sicherungen[1] in geloescht
    assert sicherungen[4].exists() and sicherungen[3].exists() and sicherungen[2].exists()
    assert pre_ddb.exists(), "Pre-DDB-Sicherung darf NICHT rotiert werden"
    assert db.exists(), "die aktive DB ist keine Sicherung"


def test_buch_aus_manifest_und_import_all(tmp_path, dbs, monkeypatch):
    """import-all leitet die Buch-Konfig aus dem Manifest ab (keine [[ddb.buch]]-Config)
    und importiert alle vorhandenen Artefakte in die private DB."""
    from importer.import_ddb import (buch_aus_manifest, importiere_ddb_artefakt,
                                     neueste_artefakte)
    basis = tmp_path / "artifacts"
    # Zwei Buecher, je ein (jueng­stes) Artefakt.
    for kuerzel in ("ddb-a-en", "ddb-b-en"):
        ziel = basis / kuerzel / "20260101T000000Z"
        ziel.mkdir(parents=True)
        shutil.copy(_FIXTURE / "entries-v1.jsonl", ziel / "entries.jsonl")
        m = json.loads((_FIXTURE / "manifest-v1.json").read_text())
        m["source_key"] = kuerzel
        (ziel / "manifest.json").write_text(json.dumps(m), encoding="utf-8")

    artefakte = neueste_artefakte(basis)
    assert len(artefakte) == 2
    buch = buch_aus_manifest(artefakte[0])
    assert buch["kuerzel"] == "ddb-a-en" and buch["edition"] == "2024"
    assert buch["prioritaet"] == 40 and buch["lizenz"] == "privat"

    for artefakt in artefakte:
        importiere_ddb_artefakt(artefakt, buch_aus_manifest(artefakt),
                                oeffentliche_db=dbs["oeffentlich"], private_db=dbs["privat"])
    con = sqlite3.connect(f"file:{dbs['privat']}?mode=ro", uri=True)
    try:
        quellen = {r[0] for r in con.execute("SELECT kuerzel FROM quellen WHERE herkunft='ddb'")}
        assert quellen == {"ddb-a-en", "ddb-b-en"}
    finally:
        con.close()


def test_falsche_buchkonfig_wird_abgelehnt(tmp_path, dbs):
    falsch = dict(_BUCH, edition="2014")
    with pytest.raises(ValueError, match="erwartet"):
        importiere_ddb_artefakt(_artefakt_kopie(tmp_path), falsch,
                                oeffentliche_db=dbs["oeffentlich"],
                                private_db=dbs["privat"])
    unvollstaendig = {k: v for k, v in _BUCH.items() if k != "edition"}
    with pytest.raises(ValueError, match="edition"):
        importiere_ddb_artefakt(_artefakt_kopie(tmp_path), unvollstaendig,
                                oeffentliche_db=dbs["oeffentlich"],
                                private_db=dbs["privat"])


def test_p0_inhaltsart_wandert_bis_in_die_quelle(tmp_path):
    """SYN-P0-007: die Katalog-Klassifikation ('abenteuer_setting') erreicht ueber das
    Manifest die quellen-Tabelle - auch auf Bestands-DBs OHNE die neue Spalte (defensiver
    ALTER); Alt-Manifeste ohne Feld gelten als 'regelwerk'."""
    import json
    import sqlite3

    from importer.import_ddb import buch_aus_manifest, importiere_ddb_artefakt

    schema = (Path(__file__).resolve().parent.parent / "db" / "schema.sql")
    # Basis-DB OHNE inhaltsart-Spalte (wie der Pi-Bestand vor der Migration):
    basis = tmp_path / "foliant.sqlite"
    con = sqlite3.connect(basis)
    con.executescript(schema.read_text(encoding="utf-8"))
    # Alt-Schema nachbilden (VOR der inhaltsart-Spalte, aber MIT UNIQUE-Constraint -
    # 'CREATE TABLE AS SELECT' wuerde das Constraint verlieren und den Upsert brechen):
    con.execute("DROP TABLE quellen")
    con.execute(
        "CREATE TABLE quellen (id INTEGER PRIMARY KEY, kuerzel TEXT UNIQUE NOT NULL, "
        "titel TEXT NOT NULL, sprache TEXT NOT NULL, edition TEXT NOT NULL, "
        "herkunft TEXT NOT NULL, lizenz TEXT, prioritaet INTEGER NOT NULL DEFAULT 100, "
        "dateipfad TEXT)")
    con.commit(); con.close()

    artefakt = tmp_path / "a" / "20260712T000000Z"
    artefakt.mkdir(parents=True)
    body = "*Kontext: Regeln*\n\nEin Abschnitt."
    import hashlib
    zeile = json.dumps({"ddb_id": "1", "title": "Testabschnitt", "breadcrumb": ["Buch"],
                        "category": "regel", "body_md": body,
                        "body_sha256": hashlib.sha256(body.encode()).hexdigest()},
                       ensure_ascii=False) + "\n"
    (artefakt / "entries.jsonl").write_text(zeile, encoding="utf-8")
    manifest = {"schema_version": 1, "status": "complete", "source_key": "ddb-test-en",
                "ddb_source_id": 1, "title": "Testbuch", "language": "en",
                "edition": "2024", "license": "privat",
                "exported_at": "2026-07-12T00:00:00+00:00", "entry_count": 1,
                "entries_sha256": hashlib.sha256(zeile.encode()).hexdigest(),
                "inhaltsart": "abenteuer_setting"}
    (artefakt / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    buch = buch_aus_manifest(artefakt)
    assert buch["inhaltsart"] == "abenteuer_setting"
    ziel = tmp_path / "privat.sqlite"
    importiere_ddb_artefakt(artefakt, buch, oeffentliche_db=basis, private_db=ziel)
    con = sqlite3.connect(f"file:{ziel}?mode=ro", uri=True)
    art = con.execute("SELECT inhaltsart FROM quellen WHERE kuerzel='ddb-test-en'").fetchone()[0]
    con.close()
    assert art == "abenteuer_setting"

    # Alt-Manifest ohne Feld -> 'regelwerk' (Bestandsartefakte bleiben importierbar):
    manifest.pop("inhaltsart")
    alt = tmp_path / "a2" / "20260712T000001Z"
    alt.mkdir(parents=True)
    (alt / "entries.jsonl").write_text(zeile, encoding="utf-8")
    manifest["source_key"] = "ddb-alt-en"
    (alt / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    buch2 = buch_aus_manifest(alt)
    assert buch2["inhaltsart"] == "regelwerk"


def test_kuratierter_inhaltsart_override():
    """SYN-P0-007 (12.07.2026): bekannte Setting-/Abenteuerbaende (DDB-Kategorie
    'Expanded Rules', von der Automatik nicht erkannt) werden per kuratierter Liste
    fest als abenteuer_setting gefuehrt - auch wenn das Manifest 'regelwerk' sagt."""
    import json
    import hashlib
    from importer.import_ddb import buch_aus_manifest, _ABENTEUER_SETTING_KUERZEL

    assert "ddb-rthw-en" in _ABENTEUER_SETTING_KUERZEL
    import tempfile
    d = Path(tempfile.mkdtemp())
    body = "text"
    (d / "entries.jsonl").write_text(
        json.dumps({"ddb_id": "1", "title": "T", "breadcrumb": [], "category": "regel",
                    "body_md": body,
                    "body_sha256": hashlib.sha256(body.encode()).hexdigest()}) + "\n")
    (d / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "status": "complete", "source_key": "ddb-rthw-en",
        "ddb_source_id": 232, "title": "Ravenloft", "language": "en", "edition": "2024",
        "license": "privat", "exported_at": "x", "entry_count": 1, "entries_sha256": "y",
        "inhaltsart": "regelwerk"}))          # Manifest sagt regelwerk ...
    buch = buch_aus_manifest(d)
    assert buch["inhaltsart"] == "abenteuer_setting"   # ... Override gewinnt
