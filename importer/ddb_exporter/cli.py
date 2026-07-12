"""DDB-Exporter-CLI (kurzlebiger Prozess mit Netz + Secret, OHNE jeden DB-Zugriff).

Befehle:
  list-owned                          eigene Sourcebooks samt DDB-IDs anzeigen
  export --quelle <kuerzel> [--dry-run]   ein konfiguriertes Buch -> Artefakt

SECRET-LEBENSZYKLUS (Vorschlag §9): Cobalt kommt verdeckt ueber getpass (TTY) oder aus
einem ausdruecklich gemounteten /run/secrets/ddb_cobalt - NIE aus argv, .env oder dem
Compose-Environment. ZIP, DB3 und Schluessel leben nur im Work-Verzeichnis und werden
auf Erfolgs- UND Fehlerpfaden geloescht; --debug-behalten ist die einzige Ausnahme.
Ein Lock je Buch verhindert parallele Exporte."""
from __future__ import annotations

import argparse
import getpass
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app import db as _db
from importer.ddb_exporter import artifact, book_archive, katalog
from importer.ddb_exporter.ddb_client import DdbClient, DdbFehler
from importer.ddb_exporter.html_to_markdown import html_zu_markdown


_KEYCHAIN_DIENST = "foliant-ddb-cobalt"


def _secret_datei() -> Path:
    """Container-Standard /run/secrets/ddb_cobalt; FOLIANT_COBALT_DATEI (nur ein PFAD,
    kein Secret!) erlaubt denselben Mechanismus ausserhalb von Compose."""
    return Path(os.environ.get("FOLIANT_COBALT_DATEI") or "/run/secrets/ddb_cobalt")


def _cobalt_aus_keychain() -> str | None:
    """macOS-Keychain (OS-verschluesselt): einmal ablegen, dann unbeaufsichtigt lesbar
    bis der Cobalt-Wert ablaeuft - der Automatik-Weg fuer wiederkehrende Kaeufe.
      Ablegen:  security add-generic-password -U -a foliant -s foliant-ddb-cobalt -w
      (das -w ohne Wert fragt verdeckt nach - der Wert steht so nie in argv)."""
    if sys.platform != "darwin":
        return None
    try:
        aus = subprocess.run(
            ["security", "find-generic-password", "-a", "foliant",
             "-s", _KEYCHAIN_DIENST, "-w"],
            capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    wert = (aus.stdout or "").strip()
    return wert or None


def _lies_cobalt() -> str:
    """Reihenfolge: Secret-Datei -> /run/secrets -> macOS-Keychain -> verdeckte TTY.
    Der Cobalt-WERT kommt NIE aus argv oder einer Umgebungsvariablen."""
    datei = _secret_datei()
    if datei.is_file():
        wert = datei.read_text(encoding="utf-8").strip()
        if not wert:
            sys.exit(f"Secret-Datei {datei} ist leer - Abbruch.")
        return wert
    aus_keychain = _cobalt_aus_keychain()
    if aus_keychain:
        return aus_keychain
    if not sys.stdin.isatty():
        sys.exit("Kein TTY, keine Secret-Datei und kein Keychain-Eintrag "
                 f"('{_KEYCHAIN_DIENST}') - Cobalt wird NIE aus Argumenten/Umgebung "
                 "gelesen. Einmalig ablegen: security add-generic-password -U -a foliant "
                 f"-s {_KEYCHAIN_DIENST} -w")
    wert = getpass.getpass("CobaltSession-Cookie (Eingabe bleibt unsichtbar): ")
    if not wert.strip():
        sys.exit("Leere Eingabe - Abbruch.")
    return wert.strip()


def _konfig() -> dict:
    return _db.lade_konfig().get("ddb", {}) or {}


def _buch(kuerzel: str) -> dict:
    buch = next((b for b in (_konfig().get("buch") or [])
                 if b.get("kuerzel") == kuerzel), None)
    if buch is None:
        sys.exit(f"Buch '{kuerzel}' nicht in config/foliant.toml ([[ddb.buch]]).")
    for pflicht in ("id", "kuerzel", "titel", "sprache", "edition", "prioritaet"):
        if buch.get(pflicht) in (None, ""):
            sys.exit(f"[[ddb.buch]] '{kuerzel}': Pflichtfeld '{pflicht}' fehlt - "
                     f"es wird nichts geraten.")
    # Eine explizit in der Config gesetzte edition ist eine bewusste Eigentuemer-Angabe
    # und gilt als sicher (die Buch-DB darf sie dennoch bestaetigen/korrigieren).
    # inhaltsart ist OPTIONAL lesbar (SYN-P0-007): manuell konfigurierte Buecher sind im
    # Regelfall Regelwerke; Abenteuer/Setting kann der Eigentuemer explizit kennzeichnen.
    return {**buch, "edition_sicher": True,
            "inhaltsart": buch.get("inhaltsart") or "regelwerk"}


def _transport():
    import httpx
    return httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)


def cmd_list_owned(args) -> None:
    with _transport() as transport:
        client = DdbClient(transport, _lies_cobalt())
        print(f"Angemeldet als: {client.pruefe_token()}")
        buecher = client.eigene_buecher()
        diagnose = client.lizenz_uebersicht() if getattr(args, "diagnose", False) else None
    if buecher:
        print(f"{len(buecher)} eigene Sourcebooks:")
        for b in sorted(buecher, key=lambda x: x["name"]):
            print(f"  id={b['id']:<8} {b['name']}")
    else:
        print("Keine eigenen Sourcebooks gefunden (isOwned).")
    if diagnose:
        print("\nDiagnose (secret-frei) - Lizenz-Bloecke der Antwort:")
        for block in diagnose["bloecke"]:
            print(f"  EntityTypeID={block['entity_type_id']}: "
                  f"{block['eintraege']} Eintraege, {block['owned']} owned, "
                  f"owned_ids={block['owned_ids']}")
        print(f"  Antwortstruktur: {diagnose['top_level'][:400]}")


def _artefakt_basis() -> Path:
    return _db.projekt_pfad(_konfig().get("artifact_dir", "data/private/ddb-artifacts"))


def _exportiere_buch(transport, client, buch: dict, *, dry_run: bool) -> Path | None:
    """Ein besessenes Buch -> Artefakt. Erwartet einen bereits authentifizierten Client
    (fuer sync: ein Login fuer viele Buecher). Lock je Buch; ZIP/DB3 werden immer
    aufgeraeumt. Rueckgabe: Artefaktpfad (oder None bei dry_run)."""
    artefakt_basis = _artefakt_basis()
    work = _db.projekt_pfad(_konfig().get("work_dir", "data/private/ddb-work")) \
        / f"{buch['kuerzel']}-{uuid.uuid4().hex[:8]}"
    lock = artefakt_basis / buch["kuerzel"] / ".lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.touch(exist_ok=False)
    except FileExistsError:
        raise SystemExit(f"Export fuer '{buch['kuerzel']}' laeuft bereits (Lock: {lock}).")
    try:
        url = client.buch_url(int(buch["id"]))
        archiv = book_archive.lade_archiv(transport, url, work / "buch.zip")
        print(f"  Archiv geladen ({archiv.stat().st_size} Bytes).")
        db3 = book_archive.extrahiere_buch_db(archiv, work)
        schluessel = client.buch_schluessel(int(buch["id"]))
        # AUTORITATIVE Edition aus der Buch-DB (V1/Q3: nie raten). Sie hat Vorrang vor
        # der katalog-Vermutung; ist sie unbestimmbar UND der Katalog unsicher, wird das
        # Buch NICHT mit geratener Edition geschrieben.
        db_edition = book_archive.lies_edition(db3, schluessel, int(buch["id"]))
        if db_edition:
            if buch.get("edition") and buch["edition"] != db_edition:
                print(f"  Edition korrigiert: {buch['edition']} -> {db_edition} "
                      f"(laut Buch-DB, autoritativ)")
            buch = {**buch, "edition": db_edition}
        elif not buch.get("edition_sicher"):
            raise SystemExit(
                f"Edition nicht sicher bestimmbar (Buch-DB ohne eindeutige Regelversion, "
                f"Katalog unsicher) - Buch NICHT importiert (V1/Q3: keine geratene "
                f"Edition). Bei Bedarf in config/foliant.toml als [[ddb.buch]] mit "
                f"edition explizit setzen.")
        zeilen = book_archive.lies_content(db3, schluessel)
        quelle_art = "Content"
        if not zeilen:
            # Aeltere Buecher ohne gerenderten Content-Text: aus den strukturierten
            # Detailtabellen (Zauber/Monster/Talent/Spezies ...) einzeln aufbauen.
            zeilen = book_archive.lies_strukturierte_eintraege(db3, schluessel)
            quelle_art = "Detailtabellen"
        eintraege, zaehler = artifact.baue_eintraege(zeilen, buch["titel"], html_zu_markdown)
        print(f"  Quelle: {quelle_art}")
        kategorien: dict[str, int] = {}
        for e in eintraege:
            kategorien[e["category"]] = kategorien.get(e["category"], 0) + 1
        print(f"  {len(zeilen)} Content-Zeilen -> {len(eintraege)} Eintraege "
              f"({zaehler['leer']} leer, {zaehler['fehlende_parents']} fehlende Parents); "
              f"Kategorien: {kategorien}")
        if not eintraege:
            raise SystemExit("  Kein nicht-leerer Eintrag - leeres Buch ist ein Fehler.")
        if dry_run:
            print("  Dry-run: kein Artefakt geschrieben.")
            return None
        ziel = artifact.schreibe_artefakt(
            artefakt_basis, buch, eintraege, zaehler,
            export_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            exported_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        print(f"  Artefakt: {ziel}")
        return ziel
    finally:
        shutil.rmtree(work, ignore_errors=True)   # private Buchinhalte NIE liegen lassen
        lock.unlink(missing_ok=True)


def cmd_export(args) -> None:
    buch = _buch(args.quelle)
    with _transport() as transport:
        client = DdbClient(transport, _lies_cobalt())
        print(f"Angemeldet als: {client.pruefe_token()}")
        eigene = {b["id"]: b["name"] for b in client.eigene_buecher()}
        if int(buch["id"]) not in eigene:
            sys.exit(f"Buch-ID {buch['id']} ist laut DDB NICHT im eigenen Besitz "
                     f"(isOwned) - Export abgelehnt, kein Bypass (Leitplanke).")
        print(f"Eigenes Buch bestaetigt: {eigene[int(buch['id'])]}")
        ziel = _exportiere_buch(transport, client, buch, dry_run=args.dry_run)
    if ziel:
        print(f"Weiter (offline, ohne Secret): python -m app.admin ddb-import-all")


def cmd_inspect(args) -> None:
    """Diagnose (secret-frei): Buch herunterladen, entschluesseln und die Tabellen +
    Zeilenzahlen + Spalten ausgeben (keine Zellwerte). Fuer die Analyse von Buechern
    ohne Content-Text. Schreibt kein Artefakt."""
    buch_id = int(args.id)
    work = _db.projekt_pfad(_konfig().get("work_dir", "data/private/ddb-work")) \
        / f"inspect-{uuid.uuid4().hex[:8]}"
    try:
        with _transport() as transport:
            client = DdbClient(transport, _lies_cobalt())
            print(f"Angemeldet als: {client.pruefe_token()}")
            url = client.buch_url(buch_id)
            archiv = book_archive.lade_archiv(transport, url, work / "buch.zip")
            db3 = book_archive.extrahiere_buch_db(archiv, work)
            schluessel = client.buch_schluessel(buch_id)
            tabellen = book_archive.inspiziere_tabellen(db3, schluessel)
        for t in sorted(tabellen, key=lambda x: -x["zeilen"]):
            if t["zeilen"] > 0:
                print(f"  {t['tabelle']:<28} {t['zeilen']:>5} Zeilen | "
                      f"{', '.join(t['spalten'][:10])}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def cmd_sync(args) -> None:
    """Automatik: alle EIGENEN Regelbuecher auto-aufloesen und exportieren - ohne
    manuelle [[ddb.buch]]-Pflege. Abenteuer/Charakterpakete/Playtest werden nach Scope
    uebersprungen (transparent); bereits exportierte Buecher werden nur mit --force neu
    geladen."""
    with _transport() as transport:
        client = DdbClient(transport, _lies_cobalt())
        print(f"Angemeldet als: {client.pruefe_token()}")
        kat = katalog.lade_katalog(transport)
        owned = client.eigene_buecher()
        beschluss = [katalog.klassifiziere(b["id"], kat) for b in owned]
        importierbar = [r for r in beschluss if r["importieren"]]
        uebersprungen = [r for r in beschluss if not r["importieren"]]
        print(f"\n{len(owned)} eigene Sourcebooks: {len(importierbar)} Regelbuecher, "
              f"{len(uebersprungen)} uebersprungen.")
        print("--- uebersprungen (Scope/Edition) ---")
        for r in uebersprungen:
            print(f"  id={r['id']:<4} {r['titel'][:44]:<46} {r['grund']}")

        exportiert, uebergangen, leer_oder_fehler = [], [], []
        for r in importierbar:
            buch = {"id": r["id"], "kuerzel": r["kuerzel"], "titel": r["titel"],
                    "sprache": r["sprache"], "edition": r["edition"],
                    "edition_sicher": r.get("edition_sicher", False), "lizenz": "privat",
                    # SYN-P0-007: Katalog-Klassifikation PERSISTENT mitnehmen - vorher
                    # existierte sie nur als Konsolenhinweis dieses Laufs.
                    "inhaltsart": r.get("inhaltsart", "regelwerk")}
            vorhanden = sorted((_artefakt_basis() / r["kuerzel"]).glob("2*T*Z"))
            if vorhanden and not args.force:
                uebergangen.append(r["kuerzel"])
                continue
            print(f"\n[{r['kuerzel']}] {r['titel']} (Edition {r['edition']})")
            # Ein einzelnes Buch darf den Gesamtlauf NIE abbrechen: manche Buecher liefern
            # keinen Content-Text (leer), andere sind ueber die Mobile-API nicht ladbar.
            try:
                if _exportiere_buch(transport, client, buch, dry_run=args.dry_run):
                    exportiert.append(r["kuerzel"])
            except (SystemExit, DdbFehler, book_archive.ArchivFehler, ValueError) as fehler:
                print(f"  uebersprungen: {str(fehler).strip()}")
                leer_oder_fehler.append(r["kuerzel"])
    print(f"\nFertig: {len(exportiert)} exportiert, {len(uebergangen)} bereits vorhanden, "
          f"{len(leer_oder_fehler)} ohne Content/nicht ladbar "
          f"({', '.join(leer_oder_fehler) or '-'}). "
          f"\nImport offline: python -m app.admin ddb-import-all")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(
        prog="ddb-exporter",
        description="Kurzlebiger DDB-Buch-Export (eigene Buecher -> Artefakt); "
                    "beruehrt NIE eine Foliant-Datenbank.")
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("list-owned", help="eigene Sourcebooks anzeigen")
    pl.add_argument("--diagnose", action="store_true",
                    help="secret-freie Blockuebersicht der Lizenz-Antwort mit ausgeben")
    pl.set_defaults(func=cmd_list_owned)
    pe = sub.add_parser("export", help="ein konfiguriertes Buch exportieren")
    pe.add_argument("--quelle", required=True, help="kuerzel aus [[ddb.buch]]")
    pe.add_argument("--dry-run", action="store_true",
                    help="Abruf + Bericht, aber kein Artefakt schreiben")
    pe.set_defaults(func=cmd_export)
    pi = sub.add_parser("inspect", help="Tabellenstruktur eines Buches anzeigen (Diagnose)")
    pi.add_argument("--id", required=True, help="DDB-Source-ID des eigenen Buches")
    pi.set_defaults(func=cmd_inspect)
    ps = sub.add_parser("sync", help="ALLE eigenen Regelbuecher automatisch exportieren "
                                     "(ohne manuelle Config)")
    ps.add_argument("--dry-run", action="store_true",
                    help="nur auflisten/pruefen, keine Artefakte schreiben")
    ps.add_argument("--force", action="store_true",
                    help="bereits exportierte Buecher erneut laden")
    ps.set_defaults(func=cmd_sync)
    args = p.parse_args(argv)
    try:
        args.func(args)
    except (DdbFehler, book_archive.ArchivFehler, ValueError) as fehler:
        sys.exit(f"Export abgebrochen: {fehler}")


if __name__ == "__main__":
    main()
