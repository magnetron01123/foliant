"""DDB-Offline-Import (Phase 3): geprueftes Artefakt -> PRIVATE Kandidaten-DB.

ARCHITEKTUR (docs/ddb-architektur-entscheidung.md): Dieses Modul ist der DB-SCHREIBER der
zweistufigen Pipeline. Es liest AUSSCHLIESSLICH lokale, validierte Artefakte
(importer/ddb_artefakt.py) und enthaelt bewusst KEINEN HTTP-, Cobalt- oder
Entschluesselungscode - der kurzlebige Exporter (Netz + Secret) ist ein getrennter
Prozess ohne DB-Zugriff. Der fruehere ddb-proxy-Stub (FOLIANT_COBALT aus der Umgebung)
ist ersetzt: der self-hosted Proxy kann keine Buecher liefern (ADR).

VERLUSTSICHER (A7-Prinzipien) und PRIVAT (B2):
- Ziel ist NIE die oeffentliche data/foliant.sqlite, sondern eine private Kandidaten-
  Kopie, die erst nach allen Pruefungen atomar (os.replace) als
  data/private/foliant-private.sqlite aktiviert wird.
- Vor der Aktivierung wird die bisherige private DB als Backup gesichert.
- Null Eintraege, Hash-/Metadatenfehler oder ein Rueckgang unter min_reimport_ratio
  (Standard 0.70) brechen ab - Bestand und FTS bleiben unveraendert.
- Der oeffentliche Bestand bleibt byteweise unveraendert (Tests erzwingen das)."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from importer.ddb_artefakt import pruefe_artefakt
from importer.import_markdown import _chunks

MIN_REIMPORT_RATIO = 0.70   # Vorschlag §13: DDB-Re-Importe duerfen nicht still schrumpfen
_DDB_PRIORITAET = 40        # unter deutschen Buchquellen (10-30), ueber Open5e (60)

# Generische Kapitel-/Abschnittstitel aus dem DDB-RenderedHTML (TOC-Landeseiten), die als
# eigene Eintraege in Options-Kategorien lecken: 'Species Descriptions' als Spezies, 'Feats'
# als Talent, 'Equipment' als Klasse, 'Magic Items' als Gegenstand. Es sind NIE echte
# Optionen (nur Kapitel-Vorspann) -> beim Import verwerfen, sonst verschmutzen sie die
# Charaktererstellungs-Listen (foliant_liste_spezies etc.) und die Suche. Exakter, klein-
# geschriebener Namensabgleich = keine False-Positives (keine echte Spezies heisst 'Species',
# kein Zauber 'Spells'). QS-Fund 2026-07-11: 45 solcher Stubs ueber alle Kategorien.
_KAPITEL_HEADER = frozenset({
    "species", "species descriptions", "backgrounds", "background descriptions",
    "feats", "feat descriptions", "classes", "class descriptions",
    "character classes", "subclasses",   # M2-Abnahmefund: standen als Pseudo-Klassen in liste_klassen
    "spells", "spell descriptions", "magic items", "items", "equipment",
    "monsters", "creatures", "character creation", "character origins",
    # Talent-Gruppen-Header (~47 B Boilerplate 'These feats are in the X category.'):
    "origin feats", "general feats", "fighting style feats", "epic boon feats",
})
_KAPITEL_MUSTER = re.compile(r"^(?:chapter|ch\.)\s*\d+\b", re.IGNORECASE)  # 'Chapter 5: Feats'
# NUR inhaltsleere Titel verwerfen: 'Aasimar Traits'/'Level 3 Wizard Spells'/'Barbarian Class
# Features' tragen ECHTEN Regeltext und BLEIBEN (Umformung = separater Folge-Task).


def _ist_kapitel_header(name: str) -> bool:
    """True, wenn der Name ein generischer DDB-Kapitel-/Abschnittstitel ist (keine Option,
    kein Regeltext) - exakter Titel-Abgleich ODER 'Chapter N:'/'Ch. N:'-Muster."""
    n = (name or "").strip()
    return n.lower() in _KAPITEL_HEADER or bool(_KAPITEL_MUSTER.match(n))


# Kuratierte Inhaltsart-Overrides (SYN-P0-007, fachliche Eigentuemer-Entscheidung
# 12.07.2026): DDB kategorisiert Setting-/Abenteuerbaende teils als 'Expanded Rules', so
# dass die Katalog-Automatik (_HINWEIS_KATEGORIEN) sie NICHT als abenteuer_setting
# erkennt. Diese Baende tragen aber Kampagnen-/Setting-Lore mit Spoilergehalt und werden
# deshalb FEST als abenteuer_setting gefuehrt - unabhaengig vom Manifest, damit ein
# Re-Import die Kennzeichnung (und damit den Spoiler-Hinweis in den Tool-Ausgaben) behaelt.
_ABENTEUER_SETTING_KUERZEL = frozenset({
    "ddb-rthw-en",   # Ravenloft: The Horrors Within (Setting/Horror-Lore, Darklords)
    "ddb-cosco-en",  # Curse of Strahd: Character Options (Abenteuer-bezogen)
    "ddb-wa-en",     # Frozen Sick (Wildemount-Startabenteuer)
    "efota-en",      # Eberron: Forge of the Artificer (Setting-Band)
    "frhof-en",      # Forgotten Realms: Heroes of Faerun (Setting-Band)
})


def buch_aus_manifest(artefakt: str | Path, prioritaet: int = _DDB_PRIORITAET) -> dict:
    """Buch-Konfig direkt aus dem Artefakt-Manifest ableiten - so braucht der
    Auto-Import (ddb-import-all) KEINE [[ddb.buch]]-Config mehr. Das Manifest ist bereits
    validiert (Exporter schreibt es nur nach bestandener Vertragspruefung)."""
    m = json.loads((Path(artefakt) / "manifest.json").read_text(encoding="utf-8"))
    kuerzel = m["source_key"]
    # Kuratierter Override vor dem Manifest-Default (SYN-P0-007); Alt-Artefakte ohne
    # Feld gelten sonst als Regelwerk (nicht ablehnen).
    inhaltsart = ("abenteuer_setting" if kuerzel in _ABENTEUER_SETTING_KUERZEL
                  else m.get("inhaltsart", "regelwerk"))
    return {"id": m.get("ddb_source_id"), "kuerzel": kuerzel, "titel": m["title"],
            "sprache": m["language"], "edition": m["edition"],
            "lizenz": m.get("license", "privat"), "prioritaet": prioritaet,
            "inhaltsart": inhaltsart}


def neueste_artefakte(basis: str | Path) -> list[Path]:
    """Je Buch (Unterverzeichnis) das JUENGSTE Artefakt (export-id ist zeitsortierbar)."""
    basis = Path(basis)
    if not basis.is_dir():
        return []
    neueste: list[Path] = []
    for buch_dir in sorted(basis.iterdir()):
        exporte = sorted(buch_dir.glob("2*T*Z")) if buch_dir.is_dir() else []
        if exporte:
            neueste.append(exporte[-1])
    return neueste


def _zerlege_eintrag(eintrag: dict) -> list[dict]:
    """DDB-Content liegt ABSCHNITTSWEISE vor (ein 'Rules Definitions'-Block enthaelt 165
    Regelbegriffe als ###-Headings, ein Zauberkapitel viele Zauber). Fuer Foliants Suche
    ist ein logischer Eintrag pro Zeile der Qualitaetshebel - also denselben heading-
    basierten Chunker wie beim PDF-Import anwenden (Headings 1-4 eroeffnen Eintraege,
    Eltern-Heading wandert als Kontext in den Body). Faellt nur EIN Chunk heraus (kein
    Unterheading), bleibt der Eintrag unveraendert. Kategorie wird vom Abschnitt geerbt.
    Rueckgabe: [{name, body_md}] - mindestens der Originaleintrag."""
    body = eintrag["body_md"]
    kategorie = eintrag["category"]
    # split_regeln: Headings 1-4 splitten, Kategorie durchreichen (ein Abschnitt = eine
    # Kategorie; DDB hat keine kapitelabhaengige Kategorielogik wie das dt. SRD).
    chunks = _chunks(body, kategorie_standard=kategorie,
                     split_regeln=[("", 4, kategorie)])
    # Kein sinnvoller Sub-Split (0/1 Chunk) oder Text-vor-erstem-Heading ginge verloren
    # -> Originaleintrag behalten (nie Inhalt verlieren).
    if len(chunks) <= 1 or sum(len(c["body"]) for c in chunks) < 0.6 * len(body):
        return [{"name": eintrag["title"], "body_md": body}]
    return [{"name": c["name"], "body_md": c["body"]} for c in chunks]


def _kopiere_db(quelle: Path, ziel: Path) -> None:
    """Konsistente Kopie ueber die SQLite-Backup-API (sicher auch neben offenen Lesern)."""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{quelle}?mode=ro", uri=True)
    dst = sqlite3.connect(ziel)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


BACKUPS_BEHALTEN = 3  # Anzahl aufbewahrter Auto-Sicherungen der privaten/bedienten DB


def _rotiere_backups(private_db: Path, behalten: int = BACKUPS_BEHALTEN) -> list[Path]:
    """Behaelt nur die 'behalten' juengsten Auto-Sicherungen (<stem>.backup-*.sqlite) und
    loescht aeltere - sonst waechst die Pi-SD-Karte unbegrenzt (jede DDB-Aktivierung legt
    eine ~20-MB-Sicherung an; ein 'sync' ueber 8 Buecher = 8 Sicherungen pro Lauf). Die
    einmalige Pre-DDB-Sicherung heisst '<name>.sqlite.backup-*' und faellt NICHT unter
    dieses Muster - sie bleibt unberuehrt. Rueckgabe: geloeschte Pfade."""
    muster = private_db.stem + ".backup-*.sqlite"
    sicherungen = sorted(private_db.parent.glob(muster),
                         key=lambda p: p.stat().st_mtime, reverse=True)
    geloescht: list[Path] = []
    for alt in sicherungen[max(behalten, 0):]:
        alt.unlink(missing_ok=True)
        geloescht.append(alt)
    return geloescht


def importiere_ddb_artefakt(artefakt: str | Path, buch: dict, *,
                            oeffentliche_db: str | Path,
                            private_db: str | Path,
                            erlaube_schrumpfen: bool = False,
                            dry_run: bool = False) -> dict:
    """Importiert EIN validiertes Buch-Artefakt in die private Kandidaten-DB.

    buch: secret-freie Konfiguration ([[ddb.buch]]): source_key/kuerzel, ddb_source_id/id,
    titel, sprache, edition, lizenz ('privat'), prioritaet. Pflichtfelder werden gegen das
    Manifest geprueft - nichts wird geraten. dry_run: alle Schritte inkl. Kandidaten-DB und
    Integritaetspruefungen, aber KEINE Aktivierung (Kandidat wird verworfen).
    Rueckgabe: Bericht (Zahlen, Kategorien, Pfade)."""
    oeffentliche_db, private_db = Path(oeffentliche_db), Path(private_db)
    for pflicht in ("kuerzel", "titel", "sprache", "edition", "prioritaet"):
        if buch.get(pflicht) in (None, ""):
            raise ValueError(f"Buch-Konfiguration unvollstaendig: '{pflicht}' fehlt - "
                             f"Edition/Sprache/Prioritaet werden nicht geraten.")
    geprueft = pruefe_artefakt(artefakt, erwartet={
        "source_key": buch["kuerzel"],
        **({"ddb_source_id": buch["id"]} if buch.get("id") is not None else {}),
        "language": buch["sprache"], "edition": buch["edition"]})
    manifest, eintraege = geprueft["manifest"], geprueft["eintraege"]

    basis = private_db if private_db.exists() else oeffentliche_db
    if not basis.exists():
        raise ValueError(f"Basis-Datenbank fehlt: {basis} - erst den oeffentlichen "
                         f"Bestand aufbauen (db/init_db.py + Importe).")
    kandidat = private_db.with_name(private_db.stem + ".kandidat.sqlite")
    _kopiere_db(basis, kandidat)

    try:
        con = sqlite3.connect(kandidat)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON;")
        try:
            alt = con.execute(
                "SELECT count(e.id) FROM quellen q LEFT JOIN eintraege e "
                "ON e.quelle_id = q.id WHERE q.kuerzel = ?",
                (buch["kuerzel"],)).fetchone()[0]
            # Abschnitte heading-basiert in logische Einzeleintraege zerlegen (ein Zauber
            # / ein Regelbegriff pro Zeile) - VOR dem Schrumpf-Schutz, weil dieser die
            # tatsaechlich einzufuegenden ZEILEN mit dem Bestand vergleichen muss (nicht
            # die Artefakt-Eintraege vor der Zerlegung - sonst falscher Alarm).
            zeilen_daten = [(e["category"], sub["name"], sub["body_md"])
                            for e in eintraege if e["body_md"].strip()
                            for sub in _zerlege_eintrag(e)
                            if sub["body_md"].strip() and not _ist_kapitel_header(sub["name"])]
            if not erlaube_schrumpfen and alt and \
                    len(zeilen_daten) < alt * MIN_REIMPORT_RATIO:
                raise ValueError(
                    f"{buch['kuerzel']}: Schrumpf-Schutz - nur {len(zeilen_daten)} neue "
                    f"gegenueber {alt} bestehenden Eintraegen "
                    f"(< {int(MIN_REIMPORT_RATIO * 100)} %). Wenn beabsichtigt: --force.")
            # SYN-P0-007: Bestands-DBs (Kandidat = Kopie der Basis) kennen die neue
            # Spalte noch nicht - defensiv nachziehen statt Migrationstooling.
            try:
                con.execute("ALTER TABLE quellen ADD COLUMN inhaltsart TEXT NOT NULL "
                            "DEFAULT 'regelwerk'")
            except sqlite3.OperationalError:
                pass                                   # Spalte existiert bereits
            with con:  # EINE Transaktion: Upsert, Austausch, FTS (A7)
                con.execute(
                    "INSERT INTO quellen (kuerzel, titel, sprache, edition, herkunft, "
                    "lizenz, prioritaet, dateipfad, inhaltsart) "
                    "VALUES (?,?,?,?, 'ddb', ?,?,?,?) "
                    "ON CONFLICT(kuerzel) DO UPDATE SET titel=excluded.titel, "
                    "sprache=excluded.sprache, edition=excluded.edition, "
                    "herkunft=excluded.herkunft, lizenz=excluded.lizenz, "
                    "prioritaet=excluded.prioritaet, dateipfad=excluded.dateipfad, "
                    "inhaltsart=excluded.inhaltsart",
                    (buch["kuerzel"], buch["titel"], buch["sprache"], buch["edition"],
                     buch.get("lizenz", "privat"), buch["prioritaet"], str(artefakt),
                     buch.get("inhaltsart", "regelwerk")))
                quelle_id = con.execute("SELECT id FROM quellen WHERE kuerzel = ?",
                                        (buch["kuerzel"],)).fetchone()[0]
                con.execute("DELETE FROM eintraege WHERE quelle_id = ?", (quelle_id,))
                zeilen = [(quelle_id, kat, name, buch["sprache"], buch["edition"], body)
                          for kat, name, body in zeilen_daten]
                con.executemany(
                    "INSERT INTO eintraege (quelle_id, kategorie, name_de, name_en, "
                    "sprache, edition, seite, body_md) VALUES (?,?,NULL,?,?,?,NULL,?)",
                    zeilen)
                con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")

            # Pruefungen VOR der Aktivierung (Auftrag §3.8).
            integritaet = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            n_e = con.execute("SELECT count(*) FROM eintraege").fetchone()[0]
            n_f = con.execute("SELECT count(*) FROM eintraege_fts").fetchone()[0]
            if integritaet != "ok" or fk or n_e != n_f:
                raise ValueError(f"Kandidaten-DB inkonsistent: integrity={integritaet}, "
                                 f"fk_verstoesse={len(fk)}, eintraege={n_e}, fts={n_f}.")
            abweichend = con.execute(
                "SELECT count(*) FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
                "WHERE e.edition != q.edition").fetchone()[0]
            if abweichend:
                raise ValueError(f"Kandidaten-DB: {abweichend} Eintraege mit anderer "
                                 f"Edition als ihre Quelle (A8).")
            kategorien = {r[0]: r[1] for r in con.execute(
                "SELECT kategorie, count(*) FROM eintraege WHERE quelle_id = ? "
                "GROUP BY kategorie", (quelle_id,))}
            neu = con.execute("SELECT count(*) FROM eintraege WHERE quelle_id = ?",
                              (quelle_id,)).fetchone()[0]
        finally:
            con.close()

        backup: Path | None = None
        rotiert: list[Path] = []
        if dry_run:
            kandidat.unlink()
        else:
            if private_db.exists():
                backup = private_db.with_name(
                    private_db.stem + f".backup-{manifest['exported_at'].replace(':', '')}.sqlite")
                _kopiere_db(private_db, backup)
            os.replace(kandidat, private_db)   # atomare Aktivierung
            rotiert = _rotiere_backups(private_db)  # alte Sicherungen beschneiden (Pi-SD schonen)
        return {"quelle": buch["kuerzel"], "eintraege_neu": neu, "eintraege_alt": alt,
                "kategorien": kategorien, "fehlende_parents": geprueft["fehlende_parents"],
                "dry_run": dry_run, "aktiviert": None if dry_run else str(private_db),
                "backup": str(backup) if backup else None,
                "backups_rotiert": [str(p) for p in rotiert],
                "hinweis": ("PRIVATE Datenbank - nicht ueber den authlosen oeffentlichen "
                            "Endpoint bereitstellen (B2, eigener Go-live-Beschluss).")}
    except BaseException:
        kandidat.unlink(missing_ok=True)       # kein halber Kandidat bleibt liegen
        raise
