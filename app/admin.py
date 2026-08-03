"""Foliant - Admin-CLI (Terminal). Aktionen + Status auf dem Pi, via `docker compose exec`.
Kein Web, keine oeffentliche Flaeche -> null Angriffsflaeche. Fuer grafisches Durchsuchen der
Inhalte siehe Datasette (docker compose --profile admin up -d datasette), nur localhost.

Beispiele:
  docker compose exec foliant python -m app.admin status
  docker compose exec foliant python -m app.admin import --quelle srd-de
  docker compose exec foliant python -m app.admin reindex-fts
"""
from __future__ import annotations
import argparse
import hashlib
import re
import sqlite3
import sys
from pathlib import Path

from app import db as _db
from importer import quellen as _quellen
from importer.quellen import STANDARD_PRIORITAET, registriere_quelle


def _con(pfad_override: str | None = None) -> sqlite3.Connection:
    pfad = Path(pfad_override) if pfad_override else _db.standard_pfad()
    if not pfad.exists():
        sys.exit(f"DB fehlt: {pfad}  ->  erst `python db/init_db.py {pfad}` ausfuehren.")
    return _db.connect(str(pfad))


def cmd_status(_args) -> None:
    c = _con()
    n = c.execute("SELECT count(*) FROM eintraege").fetchone()[0]
    print(f"Eintraege gesamt: {n}\n")
    print("Je Quelle (nach Prioritaet):")
    # Kein Alt-Schema-Rueckfall mehr: `_con()` geht ueber `db.connect()`, und das fuehrt
    # `stelle_schema_sicher()` mit - die inhaltsart-Spalte existiert danach IMMER.
    # Der frueher hier stehende except-Zweig war seit dem gemeinsamen Migrationspunkt
    # unerreichbar (am v0-Schema nachgestellt, 31.07.2026).
    zeilen = c.execute(
        "SELECT q.kuerzel, q.edition, q.sprache, q.inhaltsart, count(e.id) AS n "
        "FROM quellen q LEFT JOIN eintraege e ON e.quelle_id=q.id "
        "GROUP BY q.id ORDER BY q.prioritaet").fetchall()
    for r in zeilen:
        art = "" if r["inhaltsart"] == "regelwerk" else f"  [{r['inhaltsart']}]"
        print(f"  {r['kuerzel']:<16} {r['edition']:<5} {r['sprache']:<3} {r['n']:>6}{art}")
    print("\nJe Kategorie:")
    for r in c.execute("SELECT kategorie, count(*) AS n FROM eintraege GROUP BY kategorie ORDER BY n DESC"):
        print(f"  {r['kategorie']:<14} {r['n']:>6}")
    print("\nJe Edition:")
    for r in c.execute("SELECT edition, count(*) AS n FROM eintraege GROUP BY edition ORDER BY edition"):
        print(f"  {r['edition']:<6} {r['n']:>6}")
    g = c.execute("SELECT count(*) FROM glossar").fetchone()[0]
    off = c.execute("SELECT count(*) FROM glossar WHERE offiziell=1").fetchone()[0]
    print(f"\nGlossar: {g} Begriffe ({off} offiziell, {g - off} mit '*')")
    c.close()


def _datei_hash(pfad) -> str | None:
    """sha256 der Quelldatei zum Importzeitpunkt - oder None, wenn es keine EINE Datei
    gibt (Verzeichnis-Import) oder sie nicht lesbar ist.

    Wozu: Der Bestand konnte bisher nicht sagen, WELCHE Fassung eines Buches drinsteckt.
    Der korpusweite `inhalts_hash` (admin manifest) beantwortet eine andere Frage - er
    aendert sich bei jedem Import irgendeiner Quelle. Kommt spaeter eine korrigierte
    Auflage derselben PDF, faellt der Unterschied hier auf, statt unbemerkt zu bleiben.

    Ein Fehlschlag ist bewusst kein Importabbruch: die Provenienz ist eine Zugabe, ihr
    Fehlen macht den Regeltext nicht falsch. Lieber eine Quelle ohne Hash als ein
    verweigerter Import wegen einer Nebensache."""
    try:
        if not pfad or not pfad.is_file():
            return None
        h = hashlib.sha256()
        with open(pfad, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def cmd_import(args) -> None:
    """Importer nach Quellen-Kuerzel waehlen. Wege:
      glossar            -> dnddeutsch-Seeding (Kernbegriffe + Abkuerzungen) UND die
                            belegte Reparatur zerrissener Eintragsnamen im BESTAND.
                            Beides in einer Kette, weil die Reparatur das geseedete
                            Glossar als Beleggrundlage braucht (importer/import_glossar
                            ._KETTE) - der Name des Kommandos verschweigt das sonst,
                            und BACKLOG.md par. 1/M1 muss deshalb daran erinnern.
      facetten           -> Facetten aus dem vorhandenen Bestand nachziehen (kein Import)
      open5e-*           -> Open5e-API (Dokumente aus config [open5e].dokumente)
      <kuerzel aus toml> -> PDF-/Markdown-Quelle laut [[quelle]]-Registereintrag
    Nach jedem Import wird die FTS neu aufgebaut (Leitplanke) und der Facetten-Seeder
    gefahren - Reihenfolge insgesamt: Bestand, dann Facetten, dann Glossar.

    Die Web-DB wird am ENDE jedes Zweigs nachgezogen (Befund 31.07.2026): Der
    glossar-Zweig kehrte vorher vor der Auffrischung zurueck - ausgerechnet der
    einzige Zweig, der das Glossar aendert, also genau das, was die Web-DB traegt.
    Die Website zeigte danach bis zum naechsten Quellen-Import den alten Stand."""
    from importer.facetten_seeder import seed_facetten

    kuerzel = args.quelle
    if kuerzel == "facetten":
        # Nachruest-Weg fuer Bestands-DBs: Facetten OHNE Re-Import nachziehen. Wichtig,
        # weil ein Re-Import die Namensreparatur der 2014-Scans zunichte machen wuerde
        # (BACKLOG §1/M1) - der Bestand darf dafuer nicht angefasst werden muessen.
        c = _con(getattr(args, "db", None))
        with c:
            bilanz = seed_facetten(c)
        print("Facetten: " + ", ".join(f"{n} {k}" for k, n in bilanz.items()))
        c.close()
        _web_db_auffrischen(getattr(args, "db", None))
        return

    if kuerzel == "glossar":
        # Die Kette samt ihrer Reihenfolge gehoert der Fachschicht (importer.import_glossar
        # ._KETTE) - sie ist Fachwissen, kein Bedien-Detail. D2: EINE Transaktion darum,
        # damit sie ganz oder gar nicht landet.
        from importer.import_glossar import seed_alles

        c = _con(getattr(args, "db", None))
        with c:
            bilanz = seed_alles(c)
        print("Glossar: " + ", ".join(f"{n} {was}" for was, n in bilanz.items()) + ".")
        c.close()
        _web_db_auffrischen(getattr(args, "db", None))
        return

    c = _con(getattr(args, "db", None))
    facetten: dict[str, int] = {}
    try:
        force = bool(getattr(args, "force", False))
        if kuerzel.startswith("open5e"):
            from importer.import_open5e import import_open5e
            dokumente = (_db.lade_konfig().get("open5e", {}) or {}).get("dokumente") or ["srd-2024"]
            # A7: EINE Transaktion fuer Quellen-Upsert, Ersetzen und FTS-Rebuild -
            # jeder Fehler rollt komplett zurueck, der alte Bestand bleibt.
            with c:
                n = import_open5e(c, dokumente, erlaube_schrumpfen=force)
                facetten = seed_facetten(c)
        else:
            eintrag = next((q for q in _db.lade_konfig().get("quelle", [])
                            if q.get("kuerzel") == kuerzel), None)
            if eintrag is None:
                sys.exit(f"Quelle '{kuerzel}' nicht in config/foliant.toml registriert "
                         f"([[quelle]]-Block noetig: edition ist Pflicht, Q3).")
            if not eintrag.get("edition"):
                sys.exit(f"Quelle '{kuerzel}' hat keine edition in der config - "
                         f"Import abgelehnt (Q3/T11).")
            from importer.import_markdown import importiere_markdown
            pfad = eintrag.get("dateipfad")
            if not pfad:
                sys.exit(f"Quelle '{kuerzel}': dateipfad fehlt in der config.")
            # A8: Quellpfade projektroot-relativ aufloesen (Container-CWD ist egal).
            p = _db.projekt_pfad(pfad)
            # Fehlt die Datei, aber die Quelle fuehrt eine `quell_url`? Dann holen, statt
            # den Nutzer mit "dateipfad fehlt" in den Browser zu schicken (O2). Eine
            # VORHANDENE Datei fasst der Bezug nie an - siehe importer/quellbezug.py.
            from importer.quellbezug import BezugFehler, hole_wenn_fehlt
            try:
                gemeldet = hole_wenn_fehlt(p, eintrag.get("quell_url"),
                                           erwarteter_hash=eintrag.get("quell_hash"))
            except BezugFehler as fehler:
                sys.exit(f"Quelle '{kuerzel}': {fehler}")
            if gemeldet:
                print(gemeldet)
            if not p.exists():
                # Ohne URL (gekaufte PDFs, Scans) bleibt es bei der gewohnten Meldung -
                # jetzt aber mit dem Hinweis, dass es einen Bezugsweg gibt.
                sys.exit(f"Quelle '{kuerzel}': {pfad} fehlt. Datei dorthin legen - oder "
                         f"eine `quell_url` in den [[quelle]]-Block, wenn die Quelle "
                         f"frei herunterladbar ist.")
            if str(p).lower().endswith(".pdf"):
                from importer.pdf_nach_markdown import pdf_zu_markdown
                markdown = pdf_zu_markdown(p)
            else:  # Markdown-Datei oder -Verzeichnis (z. B. engl. SRD-Repo)
                dateien = sorted(p.rglob("*.md")) if p.is_dir() else [p]
                if not dateien:
                    sys.exit(f"Quelle '{kuerzel}': keine Markdown-Dateien unter {pfad} - "
                             f"Import abgebrochen, alter Bestand bleibt (A7).")
                markdown = "\n\n".join(d.read_text(encoding="utf-8") for d in dateien)
            # PFLICHT wie `edition` (Eigentuemer-Entscheidung 31.07.2026): `inhaltsart`
            # entscheidet ueber die Spoiler-Kennzeichnung bis in die Tool-Ausgaben
            # (SYN-P0-007) - die OBERSTE Verhaltensregel (SPEC.md par. 7). Der frueher
            # stille Rueckfall auf 'regelwerk' war die einzige Stelle, an der eine neue
            # Quelle diesen Schutz verlieren konnte, ohne dass irgendwo etwas stand: kein
            # Fehler, keine Warnung, nur eine fehlende Kennzeichnung im Chat. `admin
            # check` findet das hinterher nur ueber eine Wortliste - die kennt den Titel
            # des naechsten Bandes nicht. Also lieber ein abgelehnter Import als ein
            # ungekennzeichneter Abenteuerband: Regel 1 - nichts wird geraten.
            if not eintrag.get("inhaltsart"):
                sys.exit(
                    f"Quelle '{kuerzel}': inhaltsart fehlt in der config - Import "
                    f"abgelehnt (SYN-P0-007). Trage im [[quelle]]-Block genau eine der "
                    f"folgenden Zeilen ein:\n"
                    f"  inhaltsart = \"regelwerk\"            # Regelband\n"
                    f"  inhaltsart = \"abenteuer_setting\"    # Abenteuer-/Kampagnenband "
                    f"-> Spoiler-Schutz\n"
                    f"  inhaltsart = \"errata\"               # offizielle Korrektur zum "
                    f"Grundtext\n"
                    f"  inhaltsart = \"regelauslegung\"       # offizielle Auslegung "
                    f"(Sage Advice), kein Regeltext")
            # A7: Quellen-Upsert + Ersetzen + FTS-Rebuild in EINER Transaktion - sonst
            # koennte ein fehlgeschlagener Import geaenderte Quellen-Metadaten (z. B.
            # edition) neben alten Eintraegen zuruecklassen (A8-Konsistenz).
            with c:
                registriere_quelle(
                    c, kuerzel=kuerzel, titel=eintrag.get("titel", kuerzel),
                    sprache=eintrag.get("sprache", "de"), edition=eintrag["edition"],
                    herkunft=eintrag.get("herkunft", "pdf"), lizenz=eintrag.get("lizenz"),
                    prioritaet=eintrag.get("prioritaet", STANDARD_PRIORITAET),
                    dateipfad=eintrag.get("dateipfad"),
                    inhaltsart=eintrag["inhaltsart"],   # oben als Pflicht geprueft
                    versions_stand=eintrag.get("versions_stand"),
                    quell_url=eintrag.get("quell_url"),
                    quell_hash=_datei_hash(p))
                n = importiere_markdown(c, kuerzel, markdown, edition=eintrag["edition"],
                                        kategorie=eintrag.get("kategorie", "regel"),
                                        erlaube_schrumpfen=force)
                facetten = seed_facetten(c)
        # Bewusst der VOLL-Lauf statt nur der importierten Quelle: er ist idempotent und
        # billig (0,1 s auf 3000 Eintraegen) und zieht beilaeufig Quellen mit, die ueber
        # einen anderen Weg hereingekommen sind - sonst bliebe wieder unbemerkt eine
        # Tabelle leer (genau Befund C1). Innerhalb der Import-Transaktion, damit ein
        # Fehlschlag keinen halben Facettenstand hinterlaesst.
        print(f"Import '{kuerzel}': {n} Eintraege, FTS neu aufgebaut, "
              + ", ".join(f"{z} {k}-Facetten" for k, z in facetten.items()) + ".")
        # D1: was der Import verworfen oder nicht repariert hat - EINE Zeile. Interessant
        # ist weniger der Absolutwert als die Veraenderung zum letzten Lauf; eine
        # wirkungslose Reparatur (verschobener PDF-Anker) faellt so sofort auf.
        # Die Bilanz fuehrt NUR der Markdown-Importer (importer/import_markdown._BILANZ).
        # Nach einem Open5e-Lauf stuende hier der Stand des letzten PDF-/Markdown-Imports
        # - im frischen Prozess also eine Nullzeile, die so aussaehe, als sei nichts
        # verworfen worden (Befund 31.07.2026). Deshalb nur im Markdown-/PDF-Zweig.
        if not kuerzel.startswith("open5e"):
            from importer.import_markdown import letzte_bilanz
            bilanz = letzte_bilanz()
            print("  " + bilanz.zeile())
            if bilanz.auffaellig:
                print("  ^ Reparaturen ohne Anker heissen: die Quelle hat sich verschoben. "
                      "Stichprobe fahren, bevor der Bestand freigegeben wird.")
    finally:
        c.close()
    _web_db_auffrischen(getattr(args, "db", None))


def _web_db_auffrischen(db_override: str | None) -> None:
    """Die Web-DB (Glossar + Quellen-Metadaten) nach jedem Import nachziehen.

    Ohne das zeigt die Website einen Stand von gestern - und seit dem 30.07.2026 zeigt
    sie die Buchliste, also faellt genau das auf. Der Aufruf ist bewusst NICHT scharf:
    ein fehlgeschlagener Export darf einen gelungenen Import nicht nachtraeglich als
    Fehler dastehen lassen. Er meldet sich, statt zu werfen.

    Nur fuer den Hauptbestand: ein DDB-Import in die private DB hat auf der Website
    nichts verloren (SPEC.md par. 14)."""
    from app.charakterbogen.glossar_export import exportiere

    korpus = Path(db_override) if db_override else _db.standard_pfad()
    if korpus.resolve() != _db.standard_pfad().resolve():
        return
    ziel = _db.projekt_pfad("data/glossar_web.sqlite")
    if not ziel.parent.exists():
        return
    try:
        n_glossar, n_quellen = exportiere(str(korpus), str(ziel))
        print(f"  Web-DB aufgefrischt: {n_quellen} Quellen, {n_glossar} Glossarzeilen.")
    except Exception as fehler:                      # noqa: BLE001 - Beiwerk, nie fatal
        print(f"  WARNUNG: Web-DB nicht aufgefrischt ({type(fehler).__name__}: {fehler}). "
              f"Die Website zeigt bis zum naechsten Lauf den alten Stand.")


def cmd_ddb_pruefe(args) -> None:
    """Reine Artefakt-Validierung gegen den Vertrag (kein DB-Zugriff, keine Config);
    Exitcode != 0 bei jedem Fehler."""
    from importer.ddb_artefakt import pruefe_artefakt
    try:
        g = pruefe_artefakt(args.artefakt)
    except (ValueError, OSError, KeyError) as fehler:
        sys.exit(f"Artefakt ungueltig: {fehler}")
    m = g["manifest"]
    print(f"Artefakt OK: {m['title']} ({m['source_key']}, Edition {m['edition']}) - "
          f"{m['entry_count']} Eintraege, {g['fehlende_parents']} fehlende Parents.")


def _ddb_ziel_db():
    """Ziel-Datenbank des DDB-Imports. Standard = separate private DB (DDB-Inhalte
    NICHT im oeffentlichen Bestand, B2). Wer DDB-Inhalte bewusst bereitstellen will
    (Eigentuemer-Entscheidung), setzt in config/foliant.toml [ddb].ziel_db auf die
    bediente DB (z. B. 'data/foliant.sqlite') - dann merged der Import dorthin (weiter
    atomar, mit Backup + Integritaetspruefung). ins_hauptbestand=true ist die Kurzform."""
    ddb_konfig = _db.lade_konfig().get("ddb", {}) or {}
    if ddb_konfig.get("ins_hauptbestand"):
        return _db.standard_pfad()
    ziel = ddb_konfig.get("ziel_db") or ddb_konfig.get(
        "private_db", "data/private/foliant-private.sqlite")
    return _db.projekt_pfad(ziel)


def cmd_ddb_import(args) -> None:
    """Offline-Import eines validierten Artefakts in die PRIVATE Kandidaten-DB
    (die oeffentliche data/foliant.sqlite bleibt unveraendert, B2). Buch-Metadaten aus
    dem Manifest - keine [[ddb.buch]]-Config noetig."""
    from importer.import_ddb import buch_aus_manifest, importiere_ddb_artefakt
    try:
        buch = buch_aus_manifest(args.artefakt)
        bericht = importiere_ddb_artefakt(
            args.artefakt, buch, oeffentliche_db=_db.standard_pfad(),
            private_db=_ddb_ziel_db(), erlaube_schrumpfen=args.force,
            dry_run=args.dry_run)
    except (ValueError, OSError) as fehler:
        sys.exit(f"DDB-Import abgebrochen (Bestand unveraendert): {fehler}")
    for k, v in bericht.items():
        print(f"  {k}: {v}")


def cmd_ddb_import_all(args) -> None:
    """AUTOMATIK: alle vorhandenen DDB-Artefakte (je Buch das juengste) offline in die
    private DB importieren - Metadaten je aus dem Manifest. Ein Buch-Fehler stoppt den
    Rest nicht; die oeffentliche DB bleibt unveraendert (B2)."""
    from importer.import_ddb import (buch_aus_manifest, importiere_ddb_artefakt,
                                     neueste_artefakte)
    ddb_konfig = _db.lade_konfig().get("ddb", {}) or {}
    basis = _db.projekt_pfad(ddb_konfig.get("artifact_dir", "data/private/ddb-artifacts"))
    artefakte = neueste_artefakte(basis)
    if not artefakte:
        sys.exit(f"Keine DDB-Artefakte unter {basis} - erst 'ddb-exporter sync' laufen lassen.")
    ok, fehler = 0, 0
    for artefakt in artefakte:
        try:
            buch = buch_aus_manifest(artefakt)
            bericht = importiere_ddb_artefakt(
                artefakt, buch, oeffentliche_db=_db.standard_pfad(),
                private_db=_ddb_ziel_db(), erlaube_schrumpfen=args.force,
                dry_run=args.dry_run)
            print(f"  {buch['kuerzel']:<26} {bericht['eintraege_neu']:>5} Eintraege "
                  f"(Edition {buch['edition']})")
            ok += 1
        except (ValueError, OSError) as f:
            print(f"  FEHLER bei {artefakt.parent.name}: {f}")
            fehler += 1
    print(f"\n{ok} Buecher importiert, {fehler} Fehler. Ziel (privat): {_ddb_ziel_db()}")
    if fehler:
        sys.exit(1)


def cmd_ddb_remove(args) -> None:
    """Eine DDB-Quelle sauber aus der bedienten DB entfernen (Quelle + Eintraege via
    Cascade, danach FTS-Rebuild) - z. B. ein Buch mit unbestimmbarer Regelversion."""
    ziel = _ddb_ziel_db()
    if not ziel.exists():
        sys.exit(f"Ziel-DB fehlt: {ziel}")
    c = _db.connect(str(ziel))
    try:
        with c:
            weg = c.execute("DELETE FROM quellen WHERE kuerzel = ? AND herkunft='ddb'",
                            (args.quelle,)).rowcount
            _db.fts_rebuild(c)
        print(f"'{args.quelle}': {weg} Quelle(n) entfernt, FTS neu aufgebaut."
              if weg else f"Keine DDB-Quelle '{args.quelle}' in {ziel.name}.")
    finally:
        c.close()


def cmd_pdf_triage(args) -> None:
    """Textschicht-Befund fuer PDFs (Scan-Erkennung VOR dem Import): ohne --datei werden
    alle PDFs unter quellen/ und data/ocr/ geprueft. Befunde: digital (direkt importieren),
    mischform (einzelne textlose Zierseiten), scan (erst `ocr-pdf`)."""
    from importer.ocr_vorstufe import triagiere_pdf
    if args.datei:
        dateien = [_db.projekt_pfad(args.datei)]
    else:
        dateien = sorted(p for verz in ("quellen", "data/ocr")
                         for p in _db.projekt_pfad(verz).glob("*.pdf"))
    if not dateien:
        sys.exit("Keine PDFs gefunden (quellen/, data/ocr/) - --datei <pfad> angeben.")
    for pfad in dateien:
        try:
            t = triagiere_pdf(pfad)
        except (FileNotFoundError, RuntimeError, ValueError) as fehler:
            print(f"{pfad}: FEHLER {fehler}")
            continue
        print(f"{Path(t['datei']).name}: {t['befund'].upper():9} "
              f"{t['mit_text']}/{t['seiten']} Seiten mit Text "
              f"({t['leer']} leer, {t['duenn']} duenn, {t['mit_bildern']} mit Bildern)")
        print(f"  -> {t['empfehlung']}")


def cmd_ocr_pdf(args) -> None:
    """OCR-Vorstufe: legt eine Textschicht in ein gescanntes PDF (OCRmyPDF/Tesseract,
    Standard 'deu+eng'). Ausgabe nach data/ocr/ (quellen/ ist read-only gemountet);
    danach den [[quelle]]-dateipfad in config/foliant.toml auf die Ausgabedatei zeigen
    lassen und normal importieren. Einmaliger Lauf, auf dem Pi ~15-45 min pro Buch."""
    from importer.ocr_vorstufe import OCR_VERZEICHNIS, fuehre_ocr_aus
    eingabe = _db.projekt_pfad(args.datei)
    if not eingabe.exists():
        sys.exit(f"PDF nicht gefunden: {eingabe}")
    ausgabe = _db.projekt_pfad(args.ausgabe) if args.ausgabe else \
        _db.projekt_pfad(OCR_VERZEICHNIS) / f"{eingabe.stem}.ocr.pdf"
    if ausgabe.exists() and not args.force:
        sys.exit(f"Ausgabe existiert schon: {ausgabe} - OCR ist teuer; bewusst neu: --force.")
    if args.redo and args.voll:
        sys.exit("--redo und --voll schliessen sich aus (redo ersetzt Alt-OCR, "
                 "voll baut die komplette Textschicht neu).")
    modus = "voll" if args.voll else ("redo" if args.redo else "standard")
    try:
        fuehre_ocr_aus(eingabe, ausgabe, sprache=args.sprache, modus=modus,
                       jobs=args.jobs)
    except RuntimeError as fehler:
        sys.exit(f"OCR abgebrochen: {fehler}")
    print(f"\nFertig: {ausgabe}\nNaechste Schritte:\n"
          f"  1. config/foliant.toml: [[quelle]]-Block mit dateipfad = \"{ausgabe.relative_to(_db.projekt_pfad('.'))}\" "
          f"(edition PFLICHT - nie raten, Q3)\n"
          f"  2. python -m app.admin import --quelle <kuerzel>\n"
          f"  3. Stichprobe (O3): admin check + Suche nach bekannten Begriffen des Buchs")


_METADATEN = ("titel", "sprache", "edition", "herkunft", "lizenz", "prioritaet",
              "inhaltsart", "versions_stand", "quell_url")
# `quell_hash` und `importiert_am` stehen bewusst NICHT hier: beide sind Aussagen ueber
# einen tatsaechlichen IMPORTVORGANG, nicht ueber die Config. Sie hier mitzuziehen hiesse,
# einen Hash fortzuschreiben, dessen Datei niemand gelesen hat - eine Provenienz, die
# nichts belegt, ist schlimmer als keine.


def cmd_quellen_auffrischen(args) -> None:
    """Quellen-METADATEN aus der Config in den Bestand ziehen - ohne Re-Import.

    Der Anlass war ein Tippfehler in einem Buchtitel ('Ianathars' statt 'Xanathars', ein
    falsch erkannter erster Buchstabe). Bis dahin gab es dafuer nur zwei Wege: den
    Re-Import - der bei den 2014-Scans die Namensreparatur zunichte macht (CLAUDE.md) -
    oder ein UPDATE von Hand auf der Produktions-DB. Beides ist zu viel Risiko fuer eine
    geaenderte Zeichenkette.

    Angefasst wird NUR die Zeile in `quellen`, nie ein Eintrag. Neu angelegt wird nichts:
    ein Config-Block ohne importierte Eintraege wuerde sonst als leere Quelle auf der
    Website stehen. Am Ende laeuft die Web-DB-Auffrischung wie nach jedem Import, sonst
    zeigte die Seite weiter den alten Titel.

    WAS DIE CONFIG NICHT SAGT, BLEIBT STEHEN. Der Import darf fuer einen fehlenden
    optionalen Wert den Standard einsetzen - er baut die Quelle ja neu auf. Hier waere
    das ein stiller Datenverlust, und beim ersten Lauf am 31.07.2026 war es genau das:
    der Config-Block von `efota-en` fuehrt kein `inhaltsart`, also setzte der Standard
    'regelwerk' - und nahm einem Setting-Band den SPOILER-SCHUTZ (SPEC.md §7, die
    oberste Verhaltensregel). Deshalb faellt jeder nicht genannte Wert auf den
    BESTEHENDEN zurueck, nicht auf einen Standard."""
    c = _con(getattr(args, "db", None))
    try:
        vorher = {r["kuerzel"]: dict(r) for r in c.execute(
            f"SELECT kuerzel, dateipfad, quell_hash, {', '.join(_METADATEN)} FROM quellen")}
        bloecke = [q for q in _db.lade_konfig().get("quelle", [])
                   if q.get("kuerzel") in vorher]
        aenderungen: list[str] = []
        with c:
            for eintrag in bloecke:
                kuerzel = eintrag["kuerzel"]
                steht = vorher[kuerzel]

                def wert(feld: str, _e=eintrag, _s=steht):
                    """Config gewinnt, sonst bleibt der Bestandswert."""
                    return _e[feld] if _e.get(feld) not in (None, "") else _s[feld]

                if not wert("edition"):
                    print(f"  uebersprungen: '{kuerzel}' hat weder in der config noch im "
                          f"Bestand eine edition (Q3/T11 - wird nicht geraten).")
                    continue
                registriere_quelle(
                    c, kuerzel=kuerzel, titel=wert("titel"), sprache=wert("sprache"),
                    edition=wert("edition"), herkunft=wert("herkunft"),
                    lizenz=wert("lizenz"), prioritaet=wert("prioritaet"),
                    dateipfad=wert("dateipfad"), inhaltsart=wert("inhaltsart"),
                    versions_stand=wert("versions_stand"), quell_url=wert("quell_url"),
                    # Hash und Importzeit gehoeren zu einem IMPORT, nicht zu einer
                    # Metadaten-Pflege: hier wurde keine Datei gelesen. Beide bleiben
                    # deshalb stehen, statt geleert oder auf "jetzt" gesetzt zu werden -
                    # A8 gilt fuer die Config-Felder, nicht fuer Belege eines frueheren
                    # Laufs.
                    quell_hash=steht.get("quell_hash"), setze_importzeit=False)
                nachher = dict(c.execute(
                    f"SELECT kuerzel, {', '.join(_METADATEN)} FROM quellen "
                    f"WHERE kuerzel = ?", (kuerzel,)).fetchone())
                aenderungen += [f"  {kuerzel}: {feld} {vorher[kuerzel][feld]!r} -> "
                                f"{nachher[feld]!r}"
                                for feld in _METADATEN
                                if vorher[kuerzel][feld] != nachher[feld]]
        print(f"Quellen aufgefrischt: {len(bloecke)} Config-Bloecke geprueft, "
              f"{len(aenderungen)} Feld(er) geaendert.")
        print("\n".join(aenderungen) if aenderungen else "  (nichts zu tun)")
    finally:
        c.close()
    _web_db_auffrischen(getattr(args, "db", None))


def cmd_reindex(_args) -> None:
    c = _con()
    with c:                    # fts_rebuild committet nicht mehr selbst - die Transaktion fuehrt der Aufrufer
        _db.fts_rebuild(c)
    n = c.execute("SELECT count(*) FROM eintraege").fetchone()[0]
    print(f"FTS neu aufgebaut ({n} Eintraege).")
    c.close()


# Woerter, die einen Abenteuer-/Kampagnenband verraten - in Kuerzel ODER Titel, deutsch
# und englisch. Bewusst eine WARNUNG und kein Fehler: die Liste kann nur Verdacht
# aeussern, entscheiden muss der Betreiber (Regel 1 - nichts wird geraten).
#
# Die Weltnamen kamen am 31.07.2026 dazu. Vorher fehlte "Forgotten Realms: Heroes of
# Faerûn" in der Liste - der Band lief als 'regelwerk', und der Verdacht schlug nie an,
# weil kein einziges Wort passte. Seit `inhaltsart` Pflicht ist, kann kein Band den Wert
# mehr AUSLASSEN; diese Liste faengt nur noch den falsch GESETZTEN Wert, und dafuer sind
# die grossen Settings die lohnendsten Eintraege.
_SPOILER_WOERTER = ("abenteuer", "adventure", "kampagne", "campaign", "setting",
                    "fluch des", "curse of", "descent", "vecna", "strahd", "ravenloft",
                    "waterdeep", "avernus", "wildemount", "eberron", "spelljammer",
                    "faerûn", "faerun", "realms", "dragonlance", "krynn", "greyhawk",
                    "planescape", "ravnica", "theros", "strixhaven")


# Gepruefte Ausnahmen: Der TITEL klingt nach Abenteuerband, der INHALT ist reines
# Regelmaterial. Wie bei GEPRUEFTE_HOMONYME im Glossar steht der BELEG dabei, und die
# Ausnahme gilt nur, solange er zutrifft - eine Liste, die man einmal fuellt und nie
# wieder prueft, ist ein Deckel und kein Beleg.
#
# Der Wert ist die Menge der Kategorien, die die Quelle fuehren DARF. Kommt etwas anderes
# dazu, ist der Fall nicht mehr geprueft und der Verdacht schlaegt wieder an - genau das
# soll er auch, denn dann hat sich der Bestand geaendert.
_GEPRUEFTE_REGELWERKE: dict[str, tuple[frozenset[str], str]] = {
    "ddb-mcv1-en": (
        frozenset({"monster"}),
        "Monstrous Compendium Vol. 1: Spelljammer Creatures - am Pi-Bestand geprueft "
        "(01.08.2026): 40 Eintraege, ALLE kategorie='monster', Eintragsnamen sind "
        "Statblock-Abschnitte (Traits/Actions/Bonus Actions/Description). Eine reine "
        "Werte-Sammlung ohne Handlung, Orte oder Geheimnisse - 'spelljammer' im Titel "
        "ist die Weltzugehoerigkeit der Kreaturen, nicht ein Kampagnenband."),
}


# Alphabetische REGISTERKOEPFE, keine Risse: 'B | Monsters', 'Spells J', 'Magic Items U'.
# Der einzelne Buchstabe ist dort der Registerbuchstabe, nicht ein abgetrenntes Wortstueck.
#
# Am Pi-Vollbestand ausgezaehlt (01.08.2026): 42 der 91 gemeldeten Treffer waren solche
# Koepfe - fast die Haelfte der Warnung war Rauschen, und zwar Rauschen aus DDB-Buechern,
# die gar keine Scans sind. Es ueberdeckte die 49 echten Risse und machte die Zahl
# unbrauchbar: BACKLOG nannte 51 (die Scans), gemeldet wurden 91 (sieben Quellen), und
# die Differenz erklaerte niemand.
#
# Positivliste statt Heuristik, weil der strukturelle Unterschied nicht allgemein
# entscheidbar ist: 'Spells J' und 'D ORNENWAND' sehen gleich aus - Buchstabe am Rand,
# Wort daneben. Nur die Kenntnis, dass 'Spells' ein Registerwort und 'ORNENWAND' ein
# Fragment ist, trennt sie. Kommt ein Buch mit einem anderen Registerwort, schlaegt die
# Warnung an - dann wird es einmal geprueft und hier ergaenzt (Beleg, kein Deckel).
# Die Registerwoerter sind am Bestand belegt, nicht geraten: 'Monsters' 26x, 'Spells'
# 14x, 'Magic Items' 2x (Auszaehlung am Pi-Vollbestand 01.08.2026). Das Muster laesst
# auch das GESCHUETZTE Leerzeichen zu - DDB setzt es zwischen Registerbuchstabe und
# Trennstrich ('B | Monsters'), und im Quelltext waere es unsichtbar.
_REGISTER_WOERTER = ("Monsters", "Spells", "Magic Items")
_REGISTER_KOPF = re.compile(
    "^(?:[A-Z][\\s|\\u00a0]+)?(?:" + "|".join(_REGISTER_WOERTER)
    + ")(?:[\\s|\\u00a0]+[A-Z])?$")


QUALITAET_BASIS = _db.projekt_pfad("config/qualitaet_basis.json")


def _lade_basiswerte() -> dict:
    """Der dokumentierte Stand bekannter Datenmaengel (config/qualitaet_basis.json).
    Fehlt die Datei, entfaellt der Vergleich - der Check laeuft dann wie zuvor."""
    import json

    try:
        return json.loads(QUALITAET_BASIS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _messe_logik(c: sqlite3.Connection) -> tuple[dict, dict, dict, list[str]]:
    """Die rechnerischen Widersprueche im Bestand, je Pruefung und Quelle gezaehlt.

    Liefert (befunde_je_quelle, geprueft_gesamt, beispiele) - EIN Durchgang ueber alle
    Bodys fuer alle drei Textpruefungen (app/logikpruefung.py).

    `geprueft` ist keine Zierde: Ein Muster, das nach einem Formatwechsel ins Leere
    greift, meldet null Befunde - genau wie ein sauberer Bestand. Erst die Zahl daneben
    macht die beiden unterscheidbar (dieselbe Lehre wie bei den Qualitaets-Basiswerten:
    eine Kennzahl ohne Bezugsgroesse ist Rauschen).

    Bekannte Fehler der QUELLEN selbst (config/quellfehler.py) zaehlen NICHT als Befund,
    solange ihr Wortlaut noch genau so im Bestand steht - sie sind belegt und
    dokumentiert. Steht er nicht mehr da, faellt das als eigene Meldung auf: Beleg, kein
    Deckel (dasselbe Prinzip wie bei den geprueften Homonymen)."""
    from collections import Counter

    from app import logikpruefung as _logik
    from config import quellfehler as _quellfehler

    befunde: dict[str, Counter] = {art: Counter()
                                   for art in ("tp_formel", "attribut", "wuerfel")}
    geprueft: Counter = Counter()
    beispiele: dict[str, list] = {art: [] for art in befunde}
    entschuldigt: set[tuple[str, str]] = set()

    for name_de, name_en, kuerzel, body in c.execute(
            "SELECT e.name_de, e.name_en, q.kuerzel, e.body_md FROM eintraege e "
            "JOIN quellen q ON q.id = e.quelle_id"):
        for art, n in _logik.zaehle_geprueft(body).items():
            geprueft[art] += n
        bekannt = _quellfehler.quellfehler_zu(kuerzel, name_de, name_en)
        if bekannt and bekannt.steht_noch_im_bestand(body):
            entschuldigt.add((bekannt.quelle, bekannt.name))
        for fund in _logik.pruefe_text(body):
            if bekannt and bekannt.deckt_ab(fund.fundstelle):
                continue                   # belegter Quellfehler, siehe Registerkommentar
            befunde[fund.art][kuerzel] += 1
            if len(beispiele[fund.art]) < 3:
                beispiele[fund.art].append(f"{name_de or name_en}: {fund.fundstelle}")

    # Registereintraege, deren Wortlaut nicht mehr im Bestand steht - der Fall ist damit
    # ungeprueft, nicht geheilt. Quellen, die diese DB gar nicht fuehrt, bleiben aussen vor
    # (Mac-Subset, gleiche Regel wie im Basiswert-Vergleich).
    vorhanden = {r[0] for r in c.execute("SELECT kuerzel FROM quellen")}
    for eintrag in _quellfehler.BEKANNTE_QUELLFEHLER:
        if eintrag.quelle in vorhanden and (eintrag.quelle, eintrag.name) not in entschuldigt:
            print(f"Quellfehler-Register veraltet: '{eintrag.name}' ({eintrag.quelle}) - der "
                  f"dokumentierte Wortlaut {eintrag.wortlaute} steht nicht mehr im Bestand. "
                  f"Eintrag in config/quellfehler.py pruefen und nachziehen  WARNUNG")
    belegt = sorted(f"{name} ({quelle})" for quelle, name in entschuldigt)
    return befunde, dict(geprueft), beispiele, belegt


def _vergleiche_je_quelle(vorhanden: set[str], soll: dict, ist, was: str) -> tuple[int, list]:
    """Ein Basiswert-Vergleich je Quelle: steigt = FEHLER, sinkt = nachziehen, gleich =
    still. Quellen, die diese Datenbank nicht fuehrt, werden uebersprungen - das Mac-Subset
    meldete sonst lauter Scheinverbesserungen (CONCEPT.md §11, Korpus-Luecke).

    Als Helfer herausgezogen (03.08.2026), weil derselbe Dreisatz jetzt fuer sechs
    Kennzahlen gilt statt fuer eine."""
    fehler, gesunken = 0, []
    for quelle in sorted(set(soll) | set(ist)):
        if quelle not in vorhanden:
            continue
        erwartet, gemessen = soll.get(quelle, 0), ist.get(quelle, 0)
        if gemessen > erwartet:
            print(f"NEUE {was} in '{quelle}': {gemessen} statt {erwartet} dokumentierten "
                  f"- ein Import hat sie eingeschleppt  FEHLER")
            fehler += 1
        elif gemessen < erwartet:
            gesunken.append(f"{was}/{quelle} {erwartet}->{gemessen}")
    return fehler, gesunken


def _pruefe_gegen_basiswerte(c: sqlite3.Connection, meta: list, risse: list,
                             logik: dict | None = None) -> int:
    """Vergleicht die gemessenen Maengel mit dem dokumentierten Stand und liefert die Zahl
    der FEHLER (Anstiege).

    Der Punkt der ganzen Uebung: Bis zum 01.08.2026 gab `admin check` nur Zahlen aus.
    Niemand verglich sie mit dem letzten Stand - also fiel weder auf, dass die gemeldete
    Zahl von 51 (BACKLOG §3) auf 91 gewachsen war, noch dass 42 davon gar keine Risse
    sind, sondern Registerkoepfe aus DDB-Buechern. Eine Kennzahl, die niemand nachrechnet,
    ist keine Warnung mehr, sondern Hintergrundrauschen.

    Die drei Faelle und was sie bedeuten:
      STEIGT  -> FEHLER. Ein Import hat einen NEUEN Mangel eingeschleppt. Das ist der
                 eine Fall, der jemanden erreichen muss, und deshalb bricht er den Check.
      SINKT   -> Hinweis. Etwas wurde repariert; der Basiswert gehoert nachgezogen, damit
                 die Verbesserung nicht spaeter unbemerkt wieder verlorengeht.
      GLEICH  -> still. Alles wie dokumentiert.

    Quellen, die in DIESER Datenbank fehlen, werden uebersprungen: Das Mac-Subset fuehrt
    vier von fuenfzehn Quellen, und ein Vergleich gegen fehlende Buecher meldete lauter
    Scheinverbesserungen (CONCEPT.md par. 11, Korpus-Luecke)."""
    basis = _lade_basiswerte()
    if not basis:
        return 0
    from collections import Counter

    vorhanden = {r[0] for r in c.execute("SELECT kuerzel FROM quellen")}
    fehler, gesunken = _vergleiche_je_quelle(
        vorhanden, basis.get("ocr_risse_je_quelle", {}),
        Counter(q for _n, q in risse), "Namensmaengel")
    # Die drei Logikpruefungen teilen sich denselben Dreisatz (03.08.2026). Ihr Basiswert
    # steht je Quelle, damit das Mac-Subset keine Scheinverbesserung meldet.
    for schluessel, art, was in (("wuerfel_risse_je_quelle", "wuerfel", "Wuerfelrisse"),
                                 ("tp_formel_abweichungen_je_quelle", "tp_formel",
                                  "TP-Formel-Abweichungen"),
                                 ("attributs_abweichungen_je_quelle", "attribut",
                                  "Attributs-Abweichungen")):
        n, gs = _vergleiche_je_quelle(vorhanden, basis.get(schluessel, {}),
                                      (logik or {}).get(art, {}), was)
        fehler += n
        gesunken += gs
    soll_meta = basis.get("metadaten_namen_gesamt", 0)
    if len(meta) > soll_meta:
        print(f"NEUE Metadaten-Namen: {len(meta)} statt {soll_meta} dokumentierten  FEHLER")
        fehler += 1
    if gesunken:
        print(f"Namensmaengel gesunken ({', '.join(gesunken)}) - Basiswert nachziehen: "
              f"admin qualitaet-basis --schreiben")
    if not fehler and not gesunken:
        print(f"Qualitaets-Basiswerte: unveraendert seit {basis.get('erhoben_am', '?')}  OK")
    return fehler


def cmd_qualitaet_basis(args) -> None:
    """Den Basiswert bekannter Datenmaengel neu erheben (config/qualitaet_basis.json).

    Bewusst ein eigenes Kommando und kein Automatismus: Eine Zahl anzuheben heisst, einen
    Mangel als bekannt zu akzeptieren - das ist eine Entscheidung, keine Buchfuehrung.
    Die Datei liegt im Git, damit die Aenderung im Diff steht und im Commit begruendet
    werden muss.

    NUR am Vollbestand sinnvoll: Aus dem Mac-Subset erhoben, wuerde die Datei fuer elf
    Quellen eine Null behaupten, die dort nur fehlen."""
    import json

    c = _con(getattr(args, "db", None))
    try:
        from importer.import_markdown import KOPF_HEADING
        namen = [(r[0], r[1]) for r in c.execute(
            "SELECT DISTINCT coalesce(e.name_de, e.name_en, ''), q.kuerzel "
            "FROM eintraege e JOIN quellen q ON q.id = e.quelle_id")]
        quellen = c.execute("SELECT count(*) FROM quellen").fetchone()[0]
        eintraege = c.execute("SELECT count(*) FROM eintraege").fetchone()[0]
        # Dieselbe Messstelle wie `check` - eine zweite Kopie der Muster waere genau die
        # Dopplung, gegen die META_TABELLEN angetreten ist.
        logik, _geprueft, _bsp, _belegt = _messe_logik(c)
    finally:
        c.close()
    from collections import Counter
    meta = {(n, q) for n, q in namen if KOPF_HEADING.match(n)}
    risse = {(n, q) for n, q in namen
             if re.search(r"(?:^|\s)[B-HJ-Zb-hj-zÄÖÜäöüß](?:\s|$)", n)
             and not _REGISTER_KOPF.match(n)}

    def _sortiert(zaehler) -> dict:
        return dict(sorted(zaehler.items(), key=lambda kv: (-kv[1], kv[0])))

    alt = _lade_basiswerte()
    neu = dict(alt)
    neu["erhoben_am"] = __import__("datetime").date.today().isoformat()
    neu["erhoben_an"] = f"{eintraege} Eintraege, {quellen} Quellen"
    neu["ocr_risse_je_quelle"] = _sortiert(Counter(q for _n, q in risse))
    neu["metadaten_namen_gesamt"] = len(meta)
    neu["wuerfel_risse_je_quelle"] = _sortiert(logik["wuerfel"])
    neu["tp_formel_abweichungen_je_quelle"] = _sortiert(logik["tp_formel"])
    neu["attributs_abweichungen_je_quelle"] = _sortiert(logik["attribut"])
    if not getattr(args, "schreiben", False):
        print("Vorschau (nichts geschrieben - mit --schreiben uebernehmen):")
        print(json.dumps({k: v for k, v in neu.items() if not k.startswith("_")},
                         ensure_ascii=False, indent=2))
        return
    QUALITAET_BASIS.write_text(json.dumps(neu, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(f"Basiswerte geschrieben: {QUALITAET_BASIS}")
    print("Die Datei liegt im Git - die Aenderung gehoert in einen Commit mit Begruendung.")


def _spoilerverdacht(c: sqlite3.Connection) -> list[tuple[str, str]]:
    """Quellen, die nach einem Abenteuerband aussehen, aber als 'regelwerk' gefuehrt sind.

    Befund 31.07.2026: `inhaltsart` entscheidet ueber die Spoiler-Kennzeichnung bis in die
    Tool-Ausgaben (SYN-P0-007) - die OBERSTE Verhaltensregel. Der DDB-Weg setzt sie
    autoritativ aus dem Buchkatalog; der PDF-/Markdown-Weg liest sie allein aus dem
    [[quelle]]-Block, und dort FEHLTE der Schluessel in der Config-Vorlage. Wer einen
    Abenteuerband einpflegt, bekommt still 'regelwerk' - ohne Fehlermeldung, nur ohne
    Spoiler-Warnung im Chat. Ein Verdacht in `admin check` ist billiger als ein Spoiler
    am Spieltisch.

    Gepruefte Ausnahmen fallen raus (_GEPRUEFTE_REGELWERKE), solange ihr Beleg traegt.
    Grund: Eine Warnung, die dauerhaft ansteht, liest bald niemand mehr - dieselbe
    Ueberlegung wie beim Konflikt-Gate des Glossars."""
    verdacht = [(r[0], r[1]) for r in c.execute(
        "SELECT kuerzel, titel FROM quellen WHERE inhaltsart = 'regelwerk' "
        "ORDER BY kuerzel")
        if any(w in f"{r[0]} {r[1]}".lower() for w in _SPOILER_WOERTER)]
    return [(k, t) for k, t in verdacht if not _beleg_traegt_noch(c, k)]


def _beleg_traegt_noch(c: sqlite3.Connection, kuerzel: str) -> bool:
    """Gilt die gepruefte Ausnahme fuer diese Quelle noch? Nur, wenn sie ausschliesslich
    die belegten Kategorien fuehrt."""
    eintrag = _GEPRUEFTE_REGELWERKE.get(kuerzel)
    if not eintrag:
        return False
    erlaubt, _beleg = eintrag
    try:
        vorhanden = {r[0] for r in c.execute(
            "SELECT DISTINCT e.kategorie FROM eintraege e JOIN quellen q "
            "ON q.id = e.quelle_id WHERE q.kuerzel = ?", (kuerzel,))}
    except sqlite3.Error:
        return False
    return bool(vorhanden) and vorhanden <= erlaubt


def _pruefe_inhaltsarten(c: sqlite3.Connection) -> int:
    """Meldet Quellen mit einem inhaltsart-Wert ausserhalb von `INHALTSARTEN`.

    Das ist die Haelfte, die ein CHECK NICHT leisten kann: Er verhindert neue falsche
    Werte, findet aber keine vorhandenen - und auf einer Datenbank, deren Spalte per
    ALTER TABLE entstand, gibt es ihn gar nicht (der Pi hat keinen). Seit v3 traegt das
    Schema deshalb bewusst keinen CHECK mehr auf diese Spalte, und diese Pruefung ist die
    Gegenprobe zum Validator in `registriere_quelle`.

    FEHLER, nicht Warnung: ein verschriebenes 'abenteur_setting' nimmt einem Band den
    Spoiler-Schutz - die oberste Verhaltensregel -, und zwar lautlos: alles, was nicht
    exakt 'abenteuer_setting' heisst, gilt der Ausgabe als unmarkiert."""
    unbekannt = [(r[0], r[1], r[2]) for r in c.execute(
        "SELECT kuerzel, titel, inhaltsart FROM quellen")
        if r[2] not in _quellen.INHALTSARTEN]
    for kuerzel, titel, wert in unbekannt:
        print(f"UNBEKANNTE inhaltsart: '{kuerzel}' ({titel}) traegt {wert!r} - erlaubt ist "
              f"{' oder '.join(sorted(_quellen.INHALTSARTEN))}  FEHLER")

    # Gegenrichtung: eine Datenbank, die den ALTEN v2-CHECK noch traegt, LEHNT die neuen
    # Werte ab - der erste Errata-Import bricht dort mit 'IntegrityError: CHECK constraint
    # failed' ab. Der Schema-Nachzug kann das nicht heilen: einen CHECK aendert SQLite nur
    # ueber einen Tabellen-Neuaufbau, und der gehoert nicht automatisch in einen
    # Migrationspunkt, der bei jedem Verbindungsaufbau laeuft (DROP TABLE auf dem
    # Produktionsbestand). Deshalb hier gemeldet statt still gemacht - mit dem Weg dazu.
    tabelle = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='quellen'").fetchone()
    definition = (tabelle[0] if tabelle else "") or ""
    if "inhaltsart IN" in definition and "errata" not in definition:
        print("VERALTETER CHECK auf quellen.inhaltsart (Stand v2): diese Datenbank nimmt "
              "'errata'/'regelauslegung' NICHT an - der Import braeche mit IntegrityError "
              "ab. Beheben: Bestand sichern ('admin backup'), dann quellen einmalig neu "
              "aufbauen (CREATE ohne CHECK, INSERT SELECT, DROP, RENAME) oder die "
              "Datenbank frisch importieren.  FEHLER")
        return len(unbekannt) + 1
    return len(unbekannt)


def _pruefe_prioritaetsbaender(c: sqlite3.Connection) -> None:
    """Meldet Quellen, deren `prioritaet` nicht im Band ihrer Klasse liegt
    (importer/quellen.band_fuer).

    WARNUNG, kein Fehler: die Baender sind eine Konvention, keine Invariante. Innerhalb
    einer Klasse ist Feinsortierung ausdruecklich erlaubt (Open5e legt einen Laufindex
    drauf), und eine bewusste Ausnahme soll man setzen koennen, ohne dass `check` rot
    wird. Was die Meldung verhindert, ist der andere Fall: eine Zahl, die niemand mehr
    begruenden kann, weil sie aus einer Zeit stammt, als vier Stellen unabhaengig
    vergaben - genau der Zustand vor dem 31.07.2026.

    Der Nutzen ist die VERGLEICHBARKEIT: steht ein deutsches Kernregelwerk ploetzlich bei
    60, ist das keine Feinsortierung mehr, sondern eine vertauschte Rangfolge - und die
    entscheidet, welcher Text bei einer Dublette gewinnt."""
    zeilen = c.execute(
        "SELECT kuerzel, titel, sprache, edition, herkunft, inhaltsart, lizenz, prioritaet "
        "FROM quellen ORDER BY prioritaet, kuerzel").fetchall()
    for q in zeilen:
        band = _quellen.band_fuer(sprache=q["sprache"], edition=q["edition"],
                                  herkunft=q["herkunft"], inhaltsart=q["inhaltsart"],
                                  lizenz=q["lizenz"])
        if not _quellen.band_passt(q["prioritaet"], band):
            print(f"Prioritaets-Band pruefen: '{q['kuerzel']}' ({q['titel']}) hat "
                  f"prioritaet={q['prioritaet']}, erwartet {band}-{band + 9}  WARNUNG")


def cmd_check(_args) -> None:
    """Konsistenz- und Mini-Qualitaetschecks (O3-Unterstuetzung); ausfuehrlicher:
    tests/smoke_test.py gegen echte Daten."""
    c = _con()
    fehler = 0
    sv = c.execute("PRAGMA user_version").fetchone()[0]
    print(f"Schema-Version: {sv}")
    n_e = c.execute("SELECT count(*) FROM eintraege").fetchone()[0]
    n_f = c.execute("SELECT count(*) FROM eintraege_fts").fetchone()[0]
    print(f"Eintraege: {n_e} / FTS-Zeilen: {n_f}" + ("  OK" if n_e == n_f else "  INKONSISTENT -> reindex-fts!"))
    fehler += 0 if n_e == n_f else 1
    verwaist = c.execute(
        "SELECT count(*) FROM eintraege WHERE edition IS NULL OR edition = '' "
        "OR quelle_id IS NULL").fetchone()[0]
    print(f"Eintraege ohne Version/Quelle (Q3): {verwaist}" + ("  OK" if verwaist == 0 else "  FEHLER"))
    fehler += verwaist
    # A8: Quellen- und Eintragsedition duerfen nicht voneinander abweichen.
    abweichend = c.execute(
        "SELECT count(*) FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
        "WHERE e.edition != q.edition").fetchone()[0]
    print(f"Eintraege mit anderer Edition als ihre Quelle (A8): {abweichend}"
          + ("  OK" if abweichend == 0 else "  FEHLER"))
    fehler += abweichend
    leere = c.execute("SELECT count(*) FROM eintraege WHERE length(trim(body_md)) < 20").fetchone()[0]
    print(f"Auffaellig kurze Eintraege (<20 Zeichen, O3-Stichprobe): {leere}")
    for kuerzel, titel in _spoilerverdacht(c):
        print(f"Spoiler-Kennzeichnung pruefen: '{kuerzel}' ({titel}) traegt "
              f"inhaltsart='regelwerk'  WARNUNG")
    fehler += _pruefe_inhaltsarten(c)
    _pruefe_prioritaetsbaender(c)

    # --- QS-Pruefungen (11.07.2026): Struktur + Textqualitaet automatisch ueberwachen ---
    # PRAGMA integrity/foreign_key: harte Strukturfehler.
    integ = c.execute("PRAGMA integrity_check").fetchone()[0]
    fk = c.execute("PRAGMA foreign_key_check").fetchall()
    print(f"integrity_check: {integ}" + ("" if integ == "ok" else "  FEHLER"))
    print(f"foreign_key_check: {len(fk)} Verstoesse" + ("  OK" if not fk else "  FEHLER"))
    fehler += (0 if integ == "ok" else 1) + len(fk)
    # FTS wirklich durchsuchbar (nicht nur zeilengleich).
    try:
        fts_ok = c.execute("SELECT count(*) FROM eintraege_fts WHERE eintraege_fts "
                           "MATCH 'dragon OR drache OR zauber OR spell'").fetchone()[0]
        print(f"FTS-Suchprobe: {fts_ok} Treffer" + ("  OK" if fts_ok else "  FEHLER (leer)"))
        fehler += 0 if fts_ok else 1
    except sqlite3.Error as e:
        print(f"FTS-Suchprobe: FEHLER {e}"); fehler += 1
    # Kategorie-/Editions-Whitelist (keine Tippfehler/Fremdwerte) - EINE Liste fuer
    # check UND Tool-Validierung (db.KATEGORIEN, SYN-P0-006).
    bad_kat = [r[0] for r in c.execute("SELECT DISTINCT kategorie FROM eintraege")
               if r[0] not in _db.KATEGORIEN]
    # kategorie ist ein geschlossener Invariant (CHECK/db.KATEGORIEN) -> harter Fehler.
    # edition ist dagegen bewusst ERWEITERBAR (V7, freies TEXT); Referenz ist die EINE
    # Liste db.UNTERSTUETZTE_EDITIONEN (kein hartkodiertes Duplikat mehr). Eine legitime,
    # noch nicht eingetragene Regelversion darf das QS-Gate NICHT hart brechen -> WARNUNG.
    unerwartete_ed = [r[0] for r in c.execute("SELECT DISTINCT edition FROM eintraege")
                      if r[0] not in _db.UNTERSTUETZTE_EDITIONEN]
    if bad_kat:
        print(f"Unerlaubte Kategorien: {bad_kat}  FEHLER"); fehler += len(bad_kat)
    if unerwartete_ed:
        print(f"Unerwartete Editionen (nicht in UNTERSTUETZTE_EDITIONEN): {unerwartete_ed}  "
              f"WARNUNG - falls beabsichtigt, db.UNTERSTUETZTE_EDITIONEN ergaenzen")
    # Textmuell (HTML-Reste/interne Links) - Warnung, kein harter Fehler.
    html = c.execute("SELECT count(*) FROM eintraege WHERE body_md LIKE '%<br%' "
                     "OR body_md LIKE '%<p>%' OR body_md LIKE '%<div%' OR body_md LIKE '%<span%' "
                     "OR body_md LIKE '%<mark>%' OR body_md LIKE '%<u>%'").fetchone()[0]
    ddb = c.execute("SELECT count(*) FROM eintraege WHERE body_md LIKE '%ddb://%' "
                    "OR name_en LIKE '%ddb://%' OR name_de LIKE '%ddb://%'").fetchone()[0]
    ent = c.execute("SELECT count(*) FROM eintraege WHERE body_md LIKE '%&amp;%' "
                    "OR body_md LIKE '%&lt;%' OR body_md LIKE '%&nbsp;%'").fetchone()[0]
    print(f"Textqualitaet: {html} mit HTML-Resten, {ddb} mit ddb://-Links, "
          f"{ent} mit HTML-Entities" + ("  OK" if not (html or ddb or ent) else "  WARNUNG"))
    # Namensqualitaet (Befund 27.07.2026): der Check sah bisher nur in die Bodys, nie auf die
    # NAMEN - so standen 46 Eintraege namens 'Zeitaufwand: 1 Aktion' unbemerkt im Bestand
    # (Chunking-Artefakt der 2014-Scans, siehe import_markdown.KOPF_HEADING). Gefunden wurden
    # sie nur per Handabfrage; diese Pruefung macht daraus einen dauerhaften Waechter, der
    # beim naechsten Buch-Import sofort anschlaegt. WARNUNG statt Fehler, weil die OCR-Risse
    # der Scans bekannt und bewusst offen sind (BACKLOG §3) - sie duerfen das Gate nicht brechen.
    import re as _re

    from importer.import_markdown import KOPF_HEADING

    _namen = [(r[0], r[1]) for r in c.execute(
        "SELECT DISTINCT coalesce(e.name_de, e.name_en, ''), q.kuerzel "
        "FROM eintraege e JOIN quellen q ON q.id = e.quelle_id")]
    meta = sorted({(n, q) for n, q in _namen if KOPF_HEADING.match(n)})
    # Einzelner Buchstabe als eigenes Wort ('D ORNENWAND', 'HEILE R') = OCR-Riss. A und I
    # sind bewusst ausgenommen: als englische Woerter ('A BOX OF NEW TOOLS', 'AS A LEVEL 1
    # CHARACTER') erzeugten sie 9 von 11 Fehlalarmen. Preis der Ausnahme: ein Riss, der
    # genau auf A oder I faellt, entgeht dem Waechter - besser als eine Warnung, die man
    # wegen Rauschens ignoriert. Die Zeichenklasse laesst A/I aus (B-H, dann J-Z).
    risse = sorted({(n, q) for n, q in _namen
                    if _re.search(r"(?:^|\s)[B-HJ-Zb-hj-zÄÖÜäöüß](?:\s|$)", n)
                    and not _REGISTER_KOPF.match(n)})
    print(f"Namensqualitaet: {len(meta)} Metadaten-Namen (Chunking-Artefakt), "
          f"{len(risse)} mit Einzelbuchstaben-Fragment (OCR)"
          + ("  OK" if not (meta or risse) else "  WARNUNG"))
    for titel, funde in (("Chunking", meta), ("OCR", risse)):
        if funde:
            quellen_ = sorted({q for _, q in funde})
            print(f"   {titel}: {[n for n, _ in funde[:3]]} ... aus {quellen_}")
    # Rechnerische Plausibilitaet (Datenbank-Audit 03.08.2026): Ein OCR-Riss oder ein
    # Importfehler aendert fast immer eine ZAHL, und eine falsche Zahl sieht aus wie eine
    # richtige. Was sie verraet, ist der Widerspruch zu einer anderen Zahl im selben Text.
    # WARNUNG statt Fehler - der Exitcode kommt allein aus dem Basiswert-Vergleich, sonst
    # stuende das Gate wegen der bekannten 2014-Scan-Risse dauerhaft rot.
    logik, geprueft, logik_beispiele, quellfehler_belegt = _messe_logik(c)
    print("Logikpruefung: "
          + ", ".join(f"{sum(logik[art].values())} {titel}"
                      for art, titel in (("tp_formel", "TP-Formeln"),
                                         ("attribut", "Attributswerte"),
                                         ("wuerfel", "Wuerfelnotationen")))
          + f"  (geprueft: {geprueft.get('tp_formel', 0)}/{geprueft.get('attribut', 0)}/"
            f"{geprueft.get('wuerfel', 0)})"
          + ("  OK" if not any(logik[a] for a in logik) else "  WARNUNG"))
    for art, titel in (("tp_formel", "TP"), ("attribut", "Attribut"), ("wuerfel", "Wuerfel")):
        if logik[art]:
            print(f"   {titel}: {logik_beispiele[art]} ... aus {sorted(logik[art])}")
    # Die entschuldigten Faelle NENNEN statt sie bloss wegzurechnen: Eine Null, die durch
    # eine Ausnahmeliste entsteht, sieht sonst aus wie eine Null ohne Maengel - und die
    # bekannten Quellfehler sollen sichtbar bleiben, nicht verschwinden.
    if quellfehler_belegt:
        print(f"   davon belegte Quellfehler der Quellen selbst (config/quellfehler.py, "
              f"nicht gezaehlt): {', '.join(quellfehler_belegt)}")
    fehler += _pruefe_gegen_basiswerte(c, meta, risse, logik)
    # Facetten-Deckung (Befund C1, 28.07.2026): Die Meta-Tabellen waren auf dem Pi LEER,
    # lokal gefuellt - und niemand merkte es, weil kein Check hinsah. WARNUNG statt Fehler:
    # eine vollstaendige Deckung ist gar nicht erreichbar (Ausruestung ohne Preisangabe
    # traegt legitim keine Facette), und eine Kennzahl, die nie gruen wird, hoert man auf
    # zu lesen (dieselbe Ueberlegung wie beim Glossar-Konflikt-Gate). Der Waechter zielt
    # auf die AUSFAELLE: eine Tabelle, die komplett leer ist, obwohl es Eintraege gibt.
    from importer.facetten_seeder import deckung

    zeilen = deckung(c)
    print("Facetten-Deckung: " + ", ".join(
        f"{kat} {mit}/{ges}" + (f" ({100 * mit // ges} %)" if ges else "")
        for kat, mit, ges in zeilen)
        + ("  OK" if all(mit or not ges for _, mit, ges in zeilen)
           else "  WARNUNG - Tabelle leer trotz Eintraegen: "
                f"`python -m app.admin import --quelle facetten` nachziehen"))
    if n_e:
        beispiel = c.execute(
            "SELECT e.name_de, e.name_en, e.edition, q.titel FROM eintraege e "
            "JOIN quellen q ON q.id=e.quelle_id ORDER BY random() LIMIT 3").fetchall()
        print("Stichprobe:", [f"{r[0] or r[1]} ({r[2]}, {r[3]})" for r in beispiel])
    c.close()
    if fehler:
        sys.exit(f"check: {fehler} Problem(e) gefunden.")
    print("check: OK")


def berechne_manifest(c: sqlite3.Connection) -> dict:
    """Korpus-Manifest (SYN-P1-012/DND-015): reproduzierbarer Fingerabdruck des BEDIENTEN
    Bestands - Quellen (Kuerzel/Edition/Sprache/Inhaltsart/Lizenz/Anzahl) plus ein
    inhaltsbasierter Hash. Als Funktion herausgeloest, damit das Eval-Harness
    (evals/verhaltens_eval.py) den BACKLOG-§2-Pflicht-Hash in seinen Report schreiben
    kann, ohne die CLI zu parsen."""
    import hashlib

    try:
        quellen = [dict(r) for r in c.execute(
            "SELECT q.kuerzel, q.titel, q.edition, q.sprache, q.inhaltsart, "
            "q.lizenz, count(e.id) AS n FROM quellen q "
            "LEFT JOIN eintraege e ON e.quelle_id=q.id GROUP BY q.id "
            "ORDER BY q.prioritaet, q.kuerzel")]
    except sqlite3.OperationalError:                 # Alt-Schema ohne inhaltsart
        quellen = [dict(r, inhaltsart="regelwerk") for r in c.execute(
            "SELECT q.kuerzel, q.titel, q.edition, q.sprache, q.lizenz, "
            "count(e.id) AS n FROM quellen q LEFT JOIN eintraege e "
            "ON e.quelle_id=q.id GROUP BY q.id ORDER BY q.prioritaet, q.kuerzel")]
    # Inhaltshash: deterministisch ueber (quelle_kuerzel, name, kategorie, edition,
    # body) aller Eintraege - unabhaengig von rowid/Importreihenfolge.
    h = hashlib.sha256()
    for r in c.execute(
            "SELECT q.kuerzel, e.kategorie, e.edition, "
            "coalesce(e.name_de,e.name_en,''), e.body_md "
            "FROM eintraege e JOIN quellen q ON q.id=e.quelle_id "
            "ORDER BY q.kuerzel, e.kategorie, coalesce(e.name_de,e.name_en,''), e.id"):
        h.update(("\x1f".join(str(x) for x in r)).encode("utf-8"))
    gl = c.execute("SELECT count(*) FROM glossar").fetchone()[0]
    sv = c.execute("PRAGMA user_version").fetchone()[0]
    return {"schema_version": sv, "eintraege_gesamt": sum(q["n"] for q in quellen),
            "glossar_zeilen": gl, "inhalts_hash": h.hexdigest(), "quellen": quellen}


def cmd_manifest(_args) -> None:
    """Ausgabe von berechne_manifest als JSON auf stdout - in die Versionsverwaltung/
    Release-Notiz uebernehmbar (Freigabe gegen einen bekannten Stand)."""
    import json

    c = _con()
    try:
        print(json.dumps(berechne_manifest(c), ensure_ascii=False, indent=2))
    finally:
        c.close()


def _teile_konflikte(c: sqlite3.Connection) -> tuple[list[dict], list[dict], list[dict]]:
    """Mehrere OFFIZIELLE deutsche Formen zu einem englischen Begriff in drei Klassen
    trennen: (echte Konflikte, durch S8 geregelte, gepruefte Homonyme).

    Nicht jede Mehrdeutigkeit ist ein Risiko. Konkurrieren eine 2014- und eine
    2024-Fassung ('Pouch': Tasche/2014 aus dem Spielerhandbuch vs. Beutel/2024 aus dem
    dt. SRD), entscheidet die kanonische Auswahlregel eindeutig - S8: der neuere
    offizielle Begriff gewinnt, und genau den zeigt glossar.term_de auch an. Solche
    Zeilen als 'falsches Deutsch'-Risiko zu zaehlen, macht die Zahl unbrauchbar: beim
    Gegenstands-Seeding auf dem Pi (26.07.2026) sprang sie von 41 auf 47, obwohl jeder
    neue Fall korrekt aufgeloest wurde.

    ECHT ist ein Konflikt, wenn die Auswahl NICHT eindeutig ist - mehrere Formen mit
    derselben neuesten Edition oder ohne belegte Edition.

    Davon abgezogen sind die GEPRUEFTEN HOMONYME (import_glossar.GEPRUEFTE_HOMONYME): dort
    sind beide deutschen Formen korrekt und kontextabhaengig (Hide -> Fell/Verstecken), eine
    'Aufloesung' waere ein Datenverlust. Sie zaehlten frueher als echte Konflikte und hielten
    das Gate dauerhaft rot - eine Kennzahl, die nie 0 wird, verliert ihren Warnwert. Der Abzug
    gilt NUR bei exakt den hinterlegten Formen: kommt eine dritte hinzu, ist der Fall wieder
    echt (die Liste belegt einen geprueften Stand, sie deckelt nicht)."""
    from collections import defaultdict

    from importer.import_glossar import GEPRUEFTE_HOMONYME

    gruppen: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in c.execute("SELECT term_en, term_de, edition_quelle FROM glossar "
                       "WHERE offiziell=1 AND coalesce(quelle,'') NOT LIKE 'abkuerzung%'"):
        gruppen[r["term_en"].lower()].append(r)

    echt: list[dict] = []
    geregelt: list[dict] = []
    homonyme: list[dict] = []
    for zeilen in gruppen.values():
        formen = {z["term_de"] for z in zeilen}
        if len(formen) < 2:
            continue
        geprueft = GEPRUEFTE_HOMONYME.get(zeilen[0]["term_en"].lower())
        if geprueft and formen == set(geprueft[0]):
            homonyme.append(dict(kandidat=zeilen[0]["term_en"],
                                 deutsche=",".join(sorted(formen)), grund=geprueft[1]))
            continue
        editionen = [int(z["edition_quelle"]) for z in zeilen
                     if str(z["edition_quelle"] or "").isdigit()]
        neueste = max(editionen, default=None)
        gewinner = {z["term_de"] for z in zeilen
                    if str(z["edition_quelle"] or "").isdigit()
                    and int(z["edition_quelle"]) == neueste}
        eintrag = dict(kandidat=zeilen[0]["term_en"], anzahl=len(formen),
                       deutsche=",".join(sorted(formen)))
        if neueste is not None and len(gewinner) == 1:
            sieger = next(iter(gewinner))
            geregelt.append({**eintrag, "gewinner": sieger, "edition": str(neueste),
                             # Explizite Liste statt String-Ersetzung: 'Klingenteufel'
                             # ist Teilstring von 'Klingenteufel (Hamatula)' und wurde
                             # sonst mitten aus dem Namen geschnitten.
                             "unterlegen": sorted(formen - {sieger})})
        else:
            echt.append(eintrag)
    echt.sort(key=lambda e: (-e["anzahl"], e["kandidat"]))
    geregelt.sort(key=lambda e: e["kandidat"])
    homonyme.sort(key=lambda e: e["kandidat"])
    return echt, geregelt, homonyme


def cmd_glossar_audit(args) -> None:
    """Deutsch-Qualitaets-Audit (READ-ONLY, schreibt nichts). Fuer den bedienten Bestand:
    deutsche Eintraege sind per se deutsch; die deutsche ANZEIGE englischer Eintraege haengt
    an einer Glossar-Bruecke (term_en -> term_de). Je Kategorie:
      en_offiziell = engl. Namen mit EXAKTer offizieller Bruecke (sauberes Deutsch, kein *)
      en_stern     = nur inoffizielle Bruecke (-> *-Kennzeichnung)
      en_ohne      = KEINE Bruecke (-> nur Englisch; die eigentliche Deutsch-Luecke)
    Plus Konflikte (ein EN-Begriff -> mehrere OFFIZIELLE dt. Begriffe = 'falsches Deutsch'-
    Risiko, schlimmer als *) - getrennt in ECHTE (Auswahl nicht eindeutig) und durch S8
    geregelte (2014 vs. 2024: der neuere Begriff gewinnt, siehe _teile_konflikte). Hinweis: dedupt der Bestand einen engl. Eintrag ohnehin gegen
    einen deutschen (gleiches Konzept), erscheint dem Nutzer die deutsche Fassung - die
    Roh-en_ohne-Zahl ist daher eine OBERGRENZE der real sichtbaren Luecke. --luecken N listet
    je Kategorie bis zu N fehlende Namen (Kuratier-Kandidaten fuer #4). --json fuer Maschinen."""
    import json as _json

    c = _con(getattr(args, "db", None))
    try:
        de_je = {r[0]: r[1] for r in c.execute(
            "SELECT kategorie, count(*) FROM eintraege WHERE sprache='de' GROUP BY kategorie")}
        # 'gedeckt' = Glossar-Bruecke ODER gleichnamiger deutscher Eintrag (das Query-Dedup
        # zeigt dann ohnehin Deutsch). Ohne den d-Join ueberzeichnet en_ohne (z. B. Aboleth=Aboleth).
        deckung = {r["kategorie"]: dict(r) for r in c.execute(
            """SELECT e.kategorie,
                      count(DISTINCT lower(e.name_en)) AS en,
                      count(DISTINCT CASE WHEN g.mx=1 OR d.hit=1 THEN lower(e.name_en) END) AS off,
                      count(DISTINCT CASE WHEN g.mx=0 AND d.hit IS NULL THEN lower(e.name_en) END) AS stern,
                      count(DISTINCT CASE WHEN g.mx IS NULL AND d.hit IS NULL THEN lower(e.name_en) END) AS ohne
               FROM eintraege e
               LEFT JOIN (SELECT lower(term_en) t, max(offiziell) mx FROM glossar
                          GROUP BY lower(term_en)) g ON g.t = lower(e.name_en)
               LEFT JOIN (SELECT DISTINCT lower(name_de) nd, 1 AS hit FROM eintraege
                          WHERE sprache='de' AND name_de IS NOT NULL) d ON d.nd = lower(e.name_en)
               WHERE e.sprache='en' AND e.name_en IS NOT NULL
               GROUP BY e.kategorie""")}
        # Abkuerzungs-Zeilen (quelle='abkuerzung', z. B. Armor Class->RK) sind BEABSICHTIGT,
        # kein Konflikt - ausschliessen, damit nur echte Term-Konflikte fuer die Review bleiben.
        konflikte, editionsgeregelt, homonyme = _teile_konflikte(c)

        bericht = {"kategorien": [], "konflikte": konflikte,
                   "konflikte_editionsgeregelt": editionsgeregelt,
                   "homonyme_geprueft": homonyme}
        for kat in _db.KATEGORIEN:
            d = deckung.get(kat, {})
            eintrag = {"kategorie": kat, "de": de_je.get(kat, 0),
                       "en": d.get("en", 0), "en_offiziell": d.get("off", 0),
                       "en_stern": d.get("stern", 0), "en_ohne": d.get("ohne", 0)}
            if getattr(args, "luecken", 0):
                eintrag["luecken_namen"] = [r[0] for r in c.execute(
                    "SELECT DISTINCT e.name_en FROM eintraege e "
                    "LEFT JOIN glossar g ON lower(g.term_en)=lower(e.name_en) "
                    "WHERE e.sprache='en' AND e.kategorie=? AND e.name_en IS NOT NULL "
                    "AND g.id IS NULL "
                    "AND NOT EXISTS (SELECT 1 FROM eintraege d WHERE d.sprache='de' "
                    "AND lower(d.name_de)=lower(e.name_en)) "
                    "ORDER BY e.name_en LIMIT ?", (kat, int(args.luecken)))]
            bericht["kategorien"].append(eintrag)

        if getattr(args, "json", False):
            print(_json.dumps(bericht, ensure_ascii=False, indent=2))
            return

        print("Deutsch-Qualitaets-Audit (bediente DB)\n")
        print(f"  {'Kategorie':<12} {'de':>6} {'en':>6} {'en+off':>7} {'en*':>6} "
              f"{'en_ohne':>8} {'*-Quote':>8}")
        ges = {"de": 0, "en": 0, "off": 0, "stern": 0, "ohne": 0}
        for e in bericht["kategorien"]:
            offen = e["en_stern"] + e["en_ohne"]
            quote = f"{100 * offen // e['en']}%" if e["en"] else "-"
            print(f"  {e['kategorie']:<12} {e['de']:>6} {e['en']:>6} {e['en_offiziell']:>7} "
                  f"{e['en_stern']:>6} {e['en_ohne']:>8} {quote:>8}")
            ges["de"] += e["de"]; ges["en"] += e["en"]; ges["off"] += e["en_offiziell"]
            ges["stern"] += e["en_stern"]; ges["ohne"] += e["en_ohne"]
            if e.get("luecken_namen"):
                print(f"      Luecken: {', '.join(e['luecken_namen'][:12])}"
                      + (" …" if len(e['luecken_namen']) >= int(args.luecken) else ""))
        offen_ges = ges["stern"] + ges["ohne"]
        gquote = f"{100 * offen_ges // ges['en']}%" if ges["en"] else "-"
        print(f"  {'GESAMT':<12} {ges['de']:>6} {ges['en']:>6} {ges['off']:>7} "
              f"{ges['stern']:>6} {ges['ohne']:>8} {gquote:>8}")
        print(f"\n  Deutsche Eintraege: {ges['de']} · englische: {ges['en']} · "
              f"davon mit offiziellem Deutsch: {ges['off']}, mit * : {ges['stern']}, "
              f"nur Englisch: {ges['ohne']}")
        if konflikte:
            print(f"\n  ⚠️ {len(konflikte)} ECHTE Konflikt(e) - Auswahl nicht eindeutig, "
                  f"pruefen (Homonyme/gleiche Edition):")
            for k in konflikte[:15]:
                print(f"     {k['kandidat']} -> {k['deutsche']}")
        else:
            print("\n  Keine echten EN->mehrere-offizielle-DE-Konflikte. ✓")
        if editionsgeregelt:
            print(f"\n  ℹ️ {len(editionsgeregelt)} weitere Mehrfachform(en) sind durch S8 "
                  f"geregelt (neuere Edition gewinnt) - kein Handlungsbedarf, z. B.:")
            for k in editionsgeregelt[:5]:
                print(f"     {k['kandidat']} -> {k['gewinner']} ({k['edition']}) "
                      f"statt {', '.join(k['unterlegen'])}")
        if homonyme:
            print(f"\n  ℹ️ {len(homonyme)} gepruefte(s) Homonym(e) - BEIDE Formen sind "
                  f"richtig, eine Aufloesung waere Datenverlust:")
            for k in homonyme:
                print(f"     {k['kandidat']} -> {k['deutsche']}  ({k['grund']})")
    finally:
        c.close()


def cmd_glossar_paare(args) -> None:
    """Vorschau der Struktur-Abgleich-Kandidaten (READ-ONLY, schreibt nichts): zeigt je
    Paar die Beweisstufe plus den Verwerfungs-Report - Davids Review VOR dem echten
    Seeding-Lauf ('admin import --quelle glossar'). Neue Paare sind solche ohne exakte
    Glossar-Zeile; nach dem Lauf muss 'glossar-audit' konfliktfrei bleiben (Gate)."""
    import json as _json

    from app import glossar as _glossar
    from importer.import_glossar import _finde_monster_paare
    from importer.srd_begriffsbruecken import finde_gegenstands_paare, seed_paar
    from importer.srd_zauberbruecken import finde_zauber_paare

    c = _con(getattr(args, "db", None))
    try:
        def _neu(term_en: str, term_de: str) -> bool:
            return _glossar.norm_begriff(term_de) not in {
                _glossar.norm_begriff(z["term_de"])
                for z in _glossar.lookup(c, term_en, richtung="en_de")
                if z["match"] == "exakt"}

        gegenstaende, report = finde_gegenstands_paare(c)
        zauber, zauber_report = finde_zauber_paare(c)
        monster = [(en, de, "statschluessel") for en, de, _k in _finde_monster_paare(c)]
        bericht = {
            "gegenstaende": [
                {"term_en": seed_paar(en, de)[0], "term_de": seed_paar(en, de)[1],
                 "beweis": stufe, "neu": _neu(*seed_paar(en, de))}
                for en, de, stufe in gegenstaende],
            "monster": [{"term_en": en, "term_de": de, "beweis": stufe,
                         "neu": _neu(en, de)} for en, de, stufe in monster],
            "zauber": [{"term_en": en, "term_de": de, "beweis": stufe,
                        "neu": _neu(en, de)} for en, de, stufe in zauber],
            "verworfen": report + zauber_report,
        }
        if getattr(args, "json", False):
            print(_json.dumps(bericht, ensure_ascii=False, indent=2))
            return
        for titel, zeilen in (("Gegenstands-Paare", bericht["gegenstaende"]),
                              ("Monster-Paare", bericht["monster"]),
                              ("Zauber-Paare (Zauberkopf-Abgleich)", bericht["zauber"])):
            neue = [z for z in zeilen if z["neu"]]
            print(f"{titel}: {len(zeilen)} belegt, davon {len(neue)} NEU")
            for z in (neue if getattr(args, "nur_neue", False) else zeilen):
                marke = "NEU " if z["neu"] else "    "
                print(f"  {marke}[{z['beweis']:<12}] {z['term_en']} -> {z['term_de']}")
            print()
        if report:
            print(f"Verworfen ({len(report)} Bucket(s) - lieber Luecke als falsches Paar):")
            for zeile in report:
                print(f"  {zeile}")
    finally:
        c.close()


def cmd_suchbericht(args) -> None:
    """Feedback-Schleife O4/M5 (READ-ONLY auf der Protokoll-DB): macht Kurations-Signale
    aus echten Anfragen sichtbar - Nulltreffer (Glossar-/Synonym-Kandidaten), Fuzzy-
    Landungen (Schreibvarianten-Kandidaten), Glossar-Bruecken (funktionierende Umwege),
    Mehrdeutigkeiten (B4-Kandidaten) und Uebersetzungs-Luecken. Kopf mit p50/p95 der
    Antwortzeiten (B9). Ohne Protokoll-DB: freundlicher Hinweis, Exit 0."""
    import json as _json
    from datetime import datetime, timedelta, timezone

    from app import protokoll as _protokoll

    con = _protokoll.verbinde_lesend()
    if con is None:
        print(f"Kein Abfrage-Protokoll unter {_protokoll.protokoll_pfad()} - es entsteht "
              f"automatisch mit der ersten Nachschlage-Anfrage ([protokoll] in "
              f"config/foliant.toml).")
        return
    try:
        tage, limit = int(args.tage), int(args.limit)
        seit = (datetime.now(timezone.utc) - timedelta(days=tage)
                ).isoformat(timespec="seconds")

        def _gruppe(wo: str, params: tuple = (), extra: str = "") -> list[dict]:
            return [dict(r) for r in con.execute(
                f"""SELECT lower(suchbegriff) AS begriff, count(*) AS anzahl,
                           max(zeitpunkt) AS zuletzt{extra}
                    FROM abfragen
                    WHERE zeitpunkt >= ? AND suchbegriff IS NOT NULL AND {wo}
                    GROUP BY lower(suchbegriff)
                    ORDER BY anzahl DESC, zuletzt DESC LIMIT ?""",
                (seit, *params, limit))]

        def _markierungen() -> list[dict]:
            """Markierte Antworten im Zeitraum. Bestands-Protokolle kennen die Tabelle
            noch nicht (sie entsteht mit der ersten Markierung) - ein fehlender Table darf
            den Bericht nicht kosten, dessen uebrige Abschnitte in Ordnung sind."""
            try:
                return [dict(r) for r in con.execute(
                    """SELECT zeitpunkt, art, frage, verweis FROM rueckmeldungen
                        WHERE zeitpunkt >= ? ORDER BY zeitpunkt DESC LIMIT ?""",
                    (seit, limit))]
            except sqlite3.OperationalError:
                return []

        dauern = sorted(r[0] for r in con.execute(
            "SELECT dauer_ms FROM abfragen WHERE zeitpunkt >= ? AND dauer_ms IS NOT NULL",
            (seit,)))

        def _perzentil(p: float) -> int | None:
            if not dauern:
                return None
            return int(dauern[min(len(dauern) - 1, int(p * len(dauern)))])

        bericht = {
            "zeitraum_tage": tage,
            "anfragen_gesamt": con.execute(
                "SELECT count(*) FROM abfragen WHERE zeitpunkt >= ?", (seit,)).fetchone()[0],
            "dauer_ms_p50": _perzentil(0.50),
            "dauer_ms_p95": _perzentil(0.95),
            # Nulltreffer ueber alle Nachschlage-Werkzeuge; Parameterfehler sind bewusst
            # KEIN Leerbefund (SYN-P0-006) und bleiben draussen.
            "nulltreffer": _gruppe("anzahl_treffer = 0 AND suchweg != 'fehler' "
                                   "AND werkzeug != 'uebersetze_begriff'"),
            "fuzzy_treffer": _gruppe("suchweg = 'fuzzy' AND werkzeug != 'uebersetze_begriff'"),
            "glossar_bruecken": _gruppe("suchweg LIKE 'glossar:%'",
                                        extra=", max(suchweg) AS bruecke"),
            "mehrdeutig": _gruppe("mehrdeutig = 1"),
            "uebersetzungs_luecken": _gruppe("werkzeug = 'uebersetze_begriff' "
                                             "AND gefunden = 0"),
            # Von der Runde MARKIERTE Antworten (👎 in Discord). Anders als alles darueber
            # kein Statistik-Signal, sondern ein Urteil: technisch gefunden, inhaltlich
            # falsch. Genau die Klasse Fehler, die kein Zaehler je zeigt.
            # Eigene Tabelle -> eigene Abfrage; `_gruppe` liest `abfragen`.
            "markiert": _markierungen(),
        }

        if getattr(args, "json", False):
            print(_json.dumps(bericht, ensure_ascii=False, indent=2))
            return

        print(f"Suchbericht (letzte {tage} Tage) - {bericht['anfragen_gesamt']} Anfragen, "
              f"Antwortzeit p50 {bericht['dauer_ms_p50']} ms / p95 "
              f"{bericht['dauer_ms_p95']} ms\n")

        def _abschnitt(titel: str, zeilen: list[dict], leer_ok: str) -> None:
            print(f"  {titel}:")
            if not zeilen:
                print(f"    {leer_ok}")
            for z in zeilen:
                zusatz = f"  [{z['bruecke'][8:]}]" if z.get("bruecke") else ""
                print(f"    {z['anzahl']:>4}x  {z['begriff']}{zusatz}  "
                      f"(zuletzt {z['zuletzt'][:10]})")
            print()

        # Bewusst VOR den Statistik-Abschnitten: Eine Antwort, die ein Spieler als falsch
        # markiert hat, ist der staerkste Kurations-Kandidat, den dieser Bericht kennt.
        print("  Von der Runde markiert (👎 in Discord - inhaltlich falsch trotz Treffer):")
        if not bericht["markiert"]:
            print("    keine ✓")
        for m in bericht["markiert"]:
            print(f"    {m['zeitpunkt'][:10]}  {m['frage'] or '(Frage nicht ermittelt)'}")
            print(f"                {m['verweis']}")
        print()

        _abschnitt("Nulltreffer (Glossar-/Synonym-Kandidaten, ggf. fehlt ein Buch)",
                   bericht["nulltreffer"], "keine - alles gefunden ✓")
        _abschnitt("Nur per Tippfehler-Toleranz gefunden (Schreibvarianten-Kandidaten)",
                   bericht["fuzzy_treffer"], "keine ✓")
        _abschnitt("Per Glossar-Bruecke gefunden (Bruecke funktioniert; [Ziel])",
                   bericht["glossar_bruecken"], "keine")
        _abschnitt("Mehrdeutig geblieben (B4 - evtl. Chunking/Namen schaerfen)",
                   bericht["mehrdeutig"], "keine ✓")
        _abschnitt("Uebersetzungs-Luecken (kein exakter Glossar-Eintrag)",
                   bericht["uebersetzungs_luecken"], "keine ✓")
        print("  Kur-Weg: Kandidaten pruefen -> Glossar-Paar/Alias ergaenzen -> "
              "'admin import --quelle glossar' (CONCEPT.md §5).")
    finally:
        con.close()


def cmd_backup(args) -> None:
    """Online-Backup der SQLite-Datei ueber die SQLite-Backup-API - konsistent AUCH bei
    laufendem Import (anders als cp/rsync auf eine offene DB). Danach eine selbst-enthaltene
    Verifikation (integrity_check + FTS-Zeilengleichheit + nicht leer), sonst wird das Backup
    verworfen. Aufbewahrung: nur die neuesten --behalten Dateien. Fuer Off-Site: dieses
    Kommando per Cron laufen lassen und danach das Ziel-Verzeichnis auf ein zweites Geraet
    rsyncen (CONCEPT.md §8) - der eigentliche M3-Schutz gegen Datenverlust."""
    import datetime

    quelle = _db.standard_pfad()
    if not quelle.exists():
        sys.exit(f"DB fehlt: {quelle}  ->  nichts zu sichern.")
    ziel_dir = Path(args.ziel) if args.ziel else (quelle.parent / "backups")
    ziel_dir.mkdir(parents=True, exist_ok=True)
    stempel = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    ziel = ziel_dir / f"{quelle.stem}-{stempel}.sqlite"

    src = _db.connect_readonly(str(quelle))              # read-only Quelle, konsistenter Snapshot
    try:
        dst = sqlite3.connect(str(ziel))
        try:
            src.backup(dst)                             # SQLite-Online-Backup (atomar konsistent)
        finally:
            dst.close()
    finally:
        src.close()

    v = sqlite3.connect(f"file:{ziel}?mode=ro", uri=True)
    try:
        integ = v.execute("PRAGMA integrity_check").fetchone()[0]
        n = v.execute("SELECT count(*) FROM eintraege").fetchone()[0]
        n_fts = v.execute("SELECT count(*) FROM eintraege_fts").fetchone()[0]
    finally:
        v.close()
    if integ != "ok" or n == 0 or n != n_fts:
        ziel.unlink(missing_ok=True)
        sys.exit(f"backup: Verifikation FEHLGESCHLAGEN (integrity={integ}, "
                 f"{n} Eintraege / {n_fts} FTS-Zeilen) - Backup verworfen, nichts geschrieben.")
    print(f"Backup OK: {ziel} ({ziel.stat().st_size // 1024} KiB, {n} Eintraege, "
          f"FTS {n_fts}, integrity ok)")

    if args.behalten > 0:
        alle = sorted(ziel_dir.glob(f"{quelle.stem}-*.sqlite"))   # Zeitstempel sortiert = chronologisch
        entfernt = 0
        for alt in alle[:-args.behalten]:
            alt.unlink(missing_ok=True)
            entfernt += 1
        if entfernt:
            print(f"Aufbewahrung: {entfernt} aeltere Backup(s) entfernt (behalte {args.behalten}).")


def baue_parser() -> argparse.ArgumentParser:
    """Der argparse-Baum, getrennt vom Lauf. Reine Extraktion aus main() - noetig, damit
    tests/test_validierung.py die Kommandoliste gegen den 'Admin-CLI (vollstaendig)'-Block
    in CONCEPT.md par. 8 pruefen kann, ohne die CLI auszufuehren. Der Block war am
    30.07.2026 unvollstaendig und nannte ein Flag, das es nie gab."""
    p = argparse.ArgumentParser(prog="foliant-admin", description="Foliant Admin-CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Bestand zusammenfassen (Import-Kontrolle)").set_defaults(func=cmd_status)
    sub.add_parser("manifest", help="Korpus-Fingerabdruck (Quellen + Inhalts-Hash) als JSON"
                   ).set_defaults(func=cmd_manifest)
    pi = sub.add_parser("import", help="Quelle importieren")
    pi.add_argument("--quelle", required=True,
                    help="kuerzel aus config, z. B. srd-de; 'glossar' = dnddeutsch-Seeding "
                         "UND Reparatur zerrissener Eintragsnamen im Bestand (deshalb nach "
                         "jedem Re-Import eines Scan-Buchs faellig); "
                         "'facetten' = Facetten aus dem Bestand nachziehen (ohne Re-Import)")
    pi.add_argument("--db", help="Ziel-DB-Pfad (Standard: [db].pfad); z. B. die private DB "
                                 "fuer ein Glossar-Reseeding nach einem DDB-Import")
    pi.add_argument("--force", action="store_true",
                    help="Schrumpf-Schutz uebergehen (A7): Import auch dann ersetzen, "
                         "wenn er deutlich kleiner ist als der Altbestand")
    pi.set_defaults(func=cmd_import)
    pt = sub.add_parser("pdf-triage",
                        help="PDFs auf Textschicht pruefen (Scan-Erkennung vor dem Import)")
    pt.add_argument("--datei", help="einzelnes PDF; ohne Angabe: alle unter quellen/ + data/ocr/")
    pt.set_defaults(func=cmd_pdf_triage)
    po = sub.add_parser("ocr-pdf",
                        help="OCR-Vorstufe fuer gescannte PDFs (OCRmyPDF/Tesseract, deu+eng)")
    po.add_argument("--datei", required=True, help="Eingabe-PDF (z. B. quellen/Buch.pdf)")
    po.add_argument("--ausgabe", help=f"Ziel (Standard: data/ocr/<name>.ocr.pdf)")
    po.add_argument("--redo", action="store_true",
                    help="vorhandene (schlechte) Alt-OCR-Textschicht ersetzen statt "
                         "textlose Seiten zu ergaenzen")
    po.add_argument("--voll", action="store_true",
                    help="KOMPLETTE Textschicht aus den Pixeln neu aufbauen (--force-ocr) - "
                         "fuer Browser-Druck-PDFs mit kaputten Fonts/Kerning-Rissen")
    po.add_argument("--sprache", default="deu+eng", help="Tesseract-Sprachen (Standard deu+eng)")
    po.add_argument("--jobs", type=int, default=0, help="parallele Worker (0 = automatisch)")
    po.add_argument("--force", action="store_true", help="vorhandene Ausgabedatei ueberschreiben")
    po.set_defaults(func=cmd_ocr_pdf)
    pq = sub.add_parser("quellen-auffrischen",
                        help="Quellen-Metadaten (Titel, Prioritaet, Lizenz, inhaltsart) "
                             "aus der config nachziehen - OHNE Re-Import, Eintraege "
                             "bleiben unberuehrt")
    pq.add_argument("--db", help="Ziel-DB-Pfad (Standard: [db].pfad)")
    pq.set_defaults(func=cmd_quellen_auffrischen)
    sub.add_parser("reindex-fts", help="FTS-Index neu aufbauen").set_defaults(func=cmd_reindex)
    sub.add_parser("check", help="Smoke-/Qualitaetschecks").set_defaults(func=cmd_check)
    pqb = sub.add_parser("qualitaet-basis",
                         help="Basiswert bekannter Datenmaengel neu erheben (nur am Vollbestand)")
    pqb.add_argument("--db", help="Ziel-DB-Pfad (Standard: [db].pfad)")
    pqb.add_argument("--schreiben", action="store_true",
                     help="config/qualitaet_basis.json wirklich ueberschreiben")
    pqb.set_defaults(func=cmd_qualitaet_basis)
    pg = sub.add_parser("glossar-audit",
                        help="Deutsch-Qualitaet messen: offiziell-Deckung/*-Quote/Luecken + Konflikte (read-only)")
    pg.add_argument("--db", help="Ziel-DB-Pfad (Standard: [db].pfad)")
    pg.add_argument("--luecken", type=int, default=0,
                    help="je Kategorie bis zu N fehlende EN-Namen listen (Kuratier-Kandidaten)")
    pg.add_argument("--json", action="store_true", help="Maschinenlesbare JSON-Ausgabe")
    pg.set_defaults(func=cmd_glossar_audit)
    pgp = sub.add_parser("glossar-paare",
                         help="Vorschau der Struktur-Abgleich-Paare (Gegenstaende/Monster) "
                              "mit Beweisstufe - Review vor 'import --quelle glossar'")
    pgp.add_argument("--nur-neue", dest="nur_neue", action="store_true",
                     help="nur Paare ohne bestehende exakte Glossar-Zeile zeigen")
    pgp.add_argument("--json", action="store_true", help="maschinenlesbare Ausgabe")
    pgp.set_defaults(func=cmd_glossar_paare)
    ps = sub.add_parser("suchbericht",
                        help="Abfrage-Protokoll auswerten: Nulltreffer, Fuzzy-Landungen, "
                             "Mehrdeutigkeiten (Kuratier-Kandidaten, O4/M5)")
    ps.add_argument("--tage", type=int, default=30, help="Zeitraum in Tagen (Default 30)")
    ps.add_argument("--limit", type=int, default=25, help="Zeilen je Abschnitt (Default 25)")
    ps.add_argument("--json", action="store_true", help="maschinenlesbare Ausgabe")
    ps.set_defaults(func=cmd_suchbericht)
    pb = sub.add_parser("backup",
                        help="Online-Backup der SQLite (konsistent) + Verifikation (M3)")
    pb.add_argument("--ziel", help="Zielverzeichnis (Standard: <db-Ordner>/backups)")
    pb.add_argument("--behalten", type=int, default=14,
                    help="nur die neuesten N Backups behalten (0 = alle behalten)")
    pb.set_defaults(func=cmd_backup)
    pp = sub.add_parser("ddb-pruefe", help="DDB-Artefakt validieren (ohne DB-Zugriff)")
    pp.add_argument("--artefakt", required=True, help="Artefakt-Verzeichnis")
    pp.set_defaults(func=cmd_ddb_pruefe)
    pd = sub.add_parser("ddb-import",
                        help="EIN DDB-Artefakt in die DDB-Ziel-DB importieren (Standard: private DB; "
                             "[ddb].ins_hauptbestand bzw. ziel_db koennen auf den "
                             "bedienten Bestand zeigen)")
    pd.add_argument("--artefakt", required=True, help="Artefakt-Verzeichnis")
    pd.add_argument("--dry-run", action="store_true",
                    help="alles pruefen, nichts aktivieren")
    pd.add_argument("--force", action="store_true",
                    help="Schrumpf-Schutz (importer/schwellen.py) bewusst uebergehen")
    pd.set_defaults(func=cmd_ddb_import)
    pa = sub.add_parser("ddb-import-all",
                        help="ALLE vorhandenen DDB-Artefakte in die DDB-Ziel-DB importieren (Standard: "
                             "private DB; siehe ddb-import)")
    pa.add_argument("--dry-run", action="store_true", help="pruefen, nichts aktivieren")
    pa.add_argument("--force", action="store_true", help="Schrumpf-Schutz uebergehen")
    pa.set_defaults(func=cmd_ddb_import_all)
    pr = sub.add_parser("ddb-remove", help="eine DDB-Quelle aus der bedienten DB entfernen")
    pr.add_argument("--quelle", required=True, help="kuerzel der DDB-Quelle")
    pr.set_defaults(func=cmd_ddb_remove)
    return p


def main(argv=None) -> None:
    args = baue_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
