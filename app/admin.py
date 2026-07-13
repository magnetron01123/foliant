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
import sqlite3
import sys
from pathlib import Path

from app import db as _db


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
    try:                                   # Bestands-DBs ohne inhaltsart-Spalte (SYN-P0-007)
        zeilen = c.execute(
            "SELECT q.kuerzel, q.edition, q.sprache, q.inhaltsart, count(e.id) AS n "
            "FROM quellen q LEFT JOIN eintraege e ON e.quelle_id=q.id "
            "GROUP BY q.id ORDER BY q.prioritaet").fetchall()
    except sqlite3.OperationalError:
        zeilen = c.execute(
            "SELECT q.kuerzel, q.edition, q.sprache, 'regelwerk' AS inhaltsart, "
            "count(e.id) AS n FROM quellen q LEFT JOIN eintraege e ON e.quelle_id=q.id "
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


def cmd_import(args) -> None:
    """Importer nach Quellen-Kuerzel waehlen. Wege:
      glossar            -> dnddeutsch-Seeding (Kernbegriffe + Abkuerzungen)
      open5e-*           -> Open5e-API (Dokumente aus config [open5e].dokumente)
      <kuerzel aus toml> -> PDF-/Markdown-Quelle laut [[quelle]]-Registereintrag
    Nach jedem Import wird die FTS neu aufgebaut (Leitplanke)."""
    kuerzel = args.quelle
    if kuerzel == "glossar":
        from importer.import_glossar import (KERNBEGRIFFE_EN, kanonisiere_konflikte,
                                             seed_abkuerzungen, seed_glossar,
                                             seed_glossar_aus_bestand, seed_kern_singulare,
                                             seed_monster_bruecke_aus_bestand, seed_srd_paare)
        c = _con(getattr(args, "db", None))
        n = seed_glossar(c, KERNBEGRIFFE_EN)
        a = seed_abkuerzungen(c)
        p = seed_srd_paare(c)
        k = seed_kern_singulare(c)
        b = seed_glossar_aus_bestand(c)
        mb = seed_monster_bruecke_aus_bestand(c)   # Struktur-Abgleich dt./engl. Monster (Dedup)
        d = kanonisiere_konflikte(c)   # zuletzt: kuratierte Fassung schlaegt konkurrierende (Deutsch-Qualitaet)
        print(f"Glossar: {n} Kern-Zeilen, {a} Abkuerzungen, {p} SRD-Paare, "
              f"{k} Kern-Singulare, {b} Zeilen aus Bestandsnamen, {mb} Monster-Bruecken, "
              f"{d} Konflikte kanonisiert.")
        c.close()
        return

    c = _con(getattr(args, "db", None))
    try:
        force = bool(getattr(args, "force", False))
        if kuerzel.startswith("open5e"):
            from importer.import_open5e import import_open5e
            dokumente = (_db.lade_konfig().get("open5e", {}) or {}).get("dokumente") or ["srd-2024"]
            # A7: EINE Transaktion fuer Quellen-Upsert, Ersetzen und FTS-Rebuild -
            # jeder Fehler rollt komplett zurueck, der alte Bestand bleibt.
            with c:
                n = import_open5e(c, dokumente, erlaube_schrumpfen=force)
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
            if str(p).lower().endswith(".pdf"):
                from importer.pdf_nach_markdown import pdf_zu_markdown
                markdown = pdf_zu_markdown(p)
            else:  # Markdown-Datei oder -Verzeichnis (z. B. engl. SRD-Repo)
                dateien = sorted(p.rglob("*.md")) if p.is_dir() else [p]
                if not dateien:
                    sys.exit(f"Quelle '{kuerzel}': keine Markdown-Dateien unter {pfad} - "
                             f"Import abgebrochen, alter Bestand bleibt (A7).")
                markdown = "\n\n".join(d.read_text(encoding="utf-8") for d in dateien)
            # A7: Quellen-Upsert + Ersetzen + FTS-Rebuild in EINER Transaktion - sonst
            # koennte ein fehlgeschlagener Import geaenderte Quellen-Metadaten (z. B.
            # edition) neben alten Eintraegen zuruecklassen (A8-Konsistenz).
            with c:
                # inhaltsart aus der Config honorieren (SYN-P0-007): Abenteuer-/Setting-
                # Baende (z. B. Druck-Buecher efota/frhof) MUESSEN 'abenteuer_setting' tragen,
                # sonst greift der Spoiler-Schutz nicht. Default 'regelwerk'.
                c.execute(
                    "INSERT INTO quellen (kuerzel, titel, sprache, edition, herkunft, "
                    "lizenz, prioritaet, dateipfad, inhaltsart) VALUES (?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(kuerzel) DO UPDATE SET titel=excluded.titel, "
                    "sprache=excluded.sprache, edition=excluded.edition, "
                    "herkunft=excluded.herkunft, lizenz=excluded.lizenz, "
                    "prioritaet=excluded.prioritaet, dateipfad=excluded.dateipfad, "
                    "inhaltsart=excluded.inhaltsart",
                    (kuerzel, eintrag.get("titel", kuerzel), eintrag.get("sprache", "de"),
                     eintrag["edition"], eintrag.get("herkunft", "pdf"),
                     eintrag.get("lizenz"), eintrag.get("prioritaet", 100),
                     eintrag.get("dateipfad"), eintrag.get("inhaltsart", "regelwerk")))
                n = importiere_markdown(c, kuerzel, markdown, edition=eintrag["edition"],
                                        kategorie=eintrag.get("kategorie", "regel"),
                                        erlaube_schrumpfen=force)
        print(f"Import '{kuerzel}': {n} Eintraege, FTS neu aufgebaut.")
    finally:
        c.close()


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
            c.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
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


def cmd_reindex(_args) -> None:
    c = _con()
    _db.fts_rebuild(c)
    n = c.execute("SELECT count(*) FROM eintraege").fetchone()[0]
    print(f"FTS neu aufgebaut ({n} Eintraege).")
    c.close()


def cmd_check(_args) -> None:
    """Konsistenz- und Mini-Qualitaetschecks (O3-Unterstuetzung); ausfuehrlicher:
    tests/smoke_test.py gegen echte Daten."""
    c = _con()
    fehler = 0
    sv = c.execute("PRAGMA user_version").fetchone()[0]
    hat_inhaltsart = any(r[1] == "inhaltsart"
                         for r in c.execute("PRAGMA table_info(quellen)"))
    print(f"Schema-Version: {sv}" + ("" if sv >= 2 and hat_inhaltsart else
          "  HINWEIS: Alt-Schema (<v2) - inhaltsart-Spalte fehlt evtl.; "
          "Importer ruesten sie defensiv nach, aber ein Reinit auf v2 ist sauberer"))
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
    if n_e:
        beispiel = c.execute(
            "SELECT e.name_de, e.name_en, e.edition, q.titel FROM eintraege e "
            "JOIN quellen q ON q.id=e.quelle_id ORDER BY random() LIMIT 3").fetchall()
        print("Stichprobe:", [f"{r[0] or r[1]} ({r[2]}, {r[3]})" for r in beispiel])
    c.close()
    if fehler:
        sys.exit(f"check: {fehler} Problem(e) gefunden.")
    print("check: OK")


def cmd_manifest(_args) -> None:
    """Korpus-Manifest (SYN-P1-012/DND-015): reproduzierbarer Fingerabdruck des BEDIENTEN
    Bestands - Quellen (Kuerzel/Edition/Sprache/Inhaltsart/Lizenz/Anzahl) plus ein
    inhaltsbasierter Hash. So laesst sich pruefen, ob der Pi-Bestand dem lokal getesteten
    entspricht (Freigabe gegen einen bekannten Stand statt gegen eine beliebige Datei).
    Ausgabe als JSON auf stdout - in die Versionsverwaltung/Release-Notiz uebernehmbar."""
    import hashlib
    import json

    c = _con()
    try:
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
        manifest = {"schema_version": sv, "eintraege_gesamt": sum(q["n"] for q in quellen),
                    "glossar_zeilen": gl, "inhalts_hash": h.hexdigest(), "quellen": quellen}
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    finally:
        c.close()


def cmd_glossar_audit(args) -> None:
    """Deutsch-Qualitaets-Audit (READ-ONLY, schreibt nichts). Fuer den bedienten Bestand:
    deutsche Eintraege sind per se deutsch; die deutsche ANZEIGE englischer Eintraege haengt
    an einer Glossar-Bruecke (term_en -> term_de). Je Kategorie:
      en_offiziell = engl. Namen mit EXAKTer offizieller Bruecke (sauberes Deutsch, kein *)
      en_stern     = nur inoffizielle Bruecke (-> *-Kennzeichnung)
      en_ohne      = KEINE Bruecke (-> nur Englisch; die eigentliche Deutsch-Luecke)
    Plus Konflikte (ein EN-Begriff -> mehrere OFFIZIELLE dt. Begriffe = 'falsches Deutsch'-
    Risiko, schlimmer als *). Hinweis: dedupt der Bestand einen engl. Eintrag ohnehin gegen
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
        konflikte = [dict(kandidat=r[0], anzahl=r[1], deutsche=r[2]) for r in c.execute(
            "SELECT term_en, count(DISTINCT term_de) AS n, group_concat(DISTINCT term_de) "
            "FROM glossar WHERE offiziell=1 AND coalesce(quelle,'') NOT LIKE 'abkuerzung%' "
            "GROUP BY lower(term_en) HAVING n > 1 ORDER BY n DESC, term_en")]

        bericht = {"kategorien": [], "konflikte": konflikte}
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
            print(f"\n  ⚠️ {len(konflikte)} Konflikt(e) (ein EN -> mehrere offizielle DE - pruefen!):")
            for k in konflikte[:15]:
                print(f"     {k['kandidat']} -> {k['deutsche']}")
        else:
            print("\n  Keine EN->mehrere-offizielle-DE-Konflikte. ✓")
    finally:
        c.close()


def cmd_backup(args) -> None:
    """Online-Backup der SQLite-Datei ueber die SQLite-Backup-API - konsistent AUCH bei
    laufendem Import (anders als cp/rsync auf eine offene DB). Danach eine selbst-enthaltene
    Verifikation (integrity_check + FTS-Zeilengleichheit + nicht leer), sonst wird das Backup
    verworfen. Aufbewahrung: nur die neuesten --behalten Dateien. Fuer Off-Site: dieses
    Kommando per Cron laufen lassen und danach das Ziel-Verzeichnis auf ein zweites Geraet
    rsyncen (docs/RUNBOOK.md) - der eigentliche M3-Schutz gegen Datenverlust."""
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


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="foliant-admin", description="Foliant Admin-CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Bestand zusammenfassen (Import-Kontrolle)").set_defaults(func=cmd_status)
    sub.add_parser("manifest", help="Korpus-Fingerabdruck (Quellen + Inhalts-Hash) als JSON"
                   ).set_defaults(func=cmd_manifest)
    pi = sub.add_parser("import", help="Quelle importieren")
    pi.add_argument("--quelle", required=True, help="kuerzel aus config, z. B. srd-de")
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
    sub.add_parser("reindex-fts", help="FTS-Index neu aufbauen").set_defaults(func=cmd_reindex)
    sub.add_parser("check", help="Smoke-/Qualitaetschecks").set_defaults(func=cmd_check)
    pg = sub.add_parser("glossar-audit",
                        help="Deutsch-Qualitaet messen: offiziell-Deckung/*-Quote/Luecken + Konflikte (read-only)")
    pg.add_argument("--db", help="Ziel-DB-Pfad (Standard: [db].pfad)")
    pg.add_argument("--luecken", type=int, default=0,
                    help="je Kategorie bis zu N fehlende EN-Namen listen (Kuratier-Kandidaten)")
    pg.add_argument("--json", action="store_true", help="Maschinenlesbare JSON-Ausgabe")
    pg.set_defaults(func=cmd_glossar_audit)
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
                        help="EIN DDB-Artefakt in die PRIVATE DB importieren")
    pd.add_argument("--artefakt", required=True, help="Artefakt-Verzeichnis")
    pd.add_argument("--dry-run", action="store_true",
                    help="alles pruefen, nichts aktivieren")
    pd.add_argument("--force", action="store_true",
                    help="Schrumpf-Schutz (min_reimport_ratio) bewusst uebergehen")
    pd.set_defaults(func=cmd_ddb_import)
    pa = sub.add_parser("ddb-import-all",
                        help="ALLE vorhandenen DDB-Artefakte in die PRIVATE DB importieren")
    pa.add_argument("--dry-run", action="store_true", help="pruefen, nichts aktivieren")
    pa.add_argument("--force", action="store_true", help="Schrumpf-Schutz uebergehen")
    pa.set_defaults(func=cmd_ddb_import_all)
    pr = sub.add_parser("ddb-remove", help="eine DDB-Quelle aus der bedienten DB entfernen")
    pr.add_argument("--quelle", required=True, help="kuerzel der DDB-Quelle")
    pr.set_defaults(func=cmd_ddb_remove)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
