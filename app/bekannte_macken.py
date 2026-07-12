"""Bekannte Quellen-/Datenmacken an EINER Stelle, kommentiert (BP #8) - damit dieselbe
Falle nicht zweimal geloest wird. TODO(claude-code): fuellen, sobald real auftretend.

Foliant-spezifische Kategorien:
- PDF-Extraktion: zerrissene Statbloecke / verbundene Tabellenzellen (PyMuPDF4LLM) -> Docling.
- Term-Mapping: Luecken im offiziellen Deutsch -> markierte dt. Wiedergabe + '*' (S5).
- dnddeutsch-API: Wildcard nur hinten; >30 Treffer = Fehler -> Suchbegriff eng fassen.
- Editions-Mix: 2014 niemals ungetaggt neben 2024 (edition NOT NULL, Q1/V5).
- Open5e-API: Community-Aggregation, Felder teils inkonsistent; 2024-Abdeckung partiell;
  Edition am Dokument-Key (srd-2024/srd-2014), nicht raten; keine Seitenzahlen.
"""

MACKEN = {
    "open5e-srd-2024": [
        "ZUSTAENDE FEHLEN KOMPLETT (10.07.2026): /v2/conditions/ liefert count=0 fuer "
        "srd-2024, und auch /v2/rules/ enthaelt keinen Conditions-Abschnitt (11 rulesets, "
        "keiner davon Zustaende). Gepackt/Grappled usw. sind also NICHT im Bestand -> "
        "Foliant sagt korrekt 'nicht gefunden' (B2). Schliessen laesst sich die Luecke "
        "erst mit dem deutschen SRD-5.2.1-PDF (enthaelt die Zustaende) oder optional "
        "srd-2014 (dann klar als 2014 getaggt).",
        "rules.document ist ein blanker String ('srd-2024'), bei allen anderen Endpunkten "
        "ein Objekt {key, name, ...} -> _dok_key() im Importer behandelt beides.",
        "desc ist bei backgrounds/feats/species/classes oft leer ('') - der eigentliche "
        "Inhalt steckt in benefits/traits/features-Listen [{name, desc}].",
        "creatures.senses/damage_immunities sind oft null; Passive Perception steht separat "
        "in passive_perception, Sichtweiten in *_sight_range-Feldern.",
        "/v2/classes/ mischt Klassen UND Unterklassen (24 Records bei 12 Klassen); "
        "Unterklassen erkennbar an subclass_of != null -> Importer stellt "
        "'*Subclass of: ...*' voran.",
        "Waffen-/Ruestungsmechanik (inkl. Weapon Mastery, 2024-Kernfeature) liegt NUR in "
        "/v2/weapons/ und /v2/armor/, nicht in /v2/items/ -> Importer mergt sie per "
        "Namens-Match in die items-Eintraege (ein logischer Eintrag pro Gegenstand).",
    ],
    "ddb-druck-pdfs (efota-en / frhof-en)": [
        "BROWSER-DRUCK-TEXTSCHICHTEN SIND BESCHAEDIGT (11.07.2026): efota reisst Woerter "
        "an der Glyphenfuge 'r|t' auf (kuratierte Join-Liste in import_markdown), frhof "
        "hat fi/fl-Ligaturen als U+FFFD und Mojibake-Smallcaps-Headings (generiertes, "
        "sichtgeprueftes Reparatur-Modul importer/frhof_reparatur.py). Original-Schicht "
        "ist trotzdem die richtige Basis - das Voll-OCR verliert Preistabellen und "
        "verschmilzt Kasten-Woerter (Kreuz-Audit).",
        "pymupdf4llm-Heading-Level sind UMGEBUNGSEMPFINDLICH (Silent-OCR sobald Tesseract "
        "im Image; use_ocr=False gesetzt). Deshalb: Konvertierung am Mac, Markdown als "
        "Import-Artefakt (quellen/md/<kuerzel>.md auf dem Pi).",
        "Manche Abschnitts-Headings existieren in KEINER Textschicht (Zierschrift als "
        "reine Grafik) -> per BEREINIGUNG wieder eingesetzt (efota: Kapitelzaeune; "
        "frhof: PLAIN_ZEILEN inkl. 7 sonst verlorener Hintergruende).",
    ],
    "srd-de": [
        "UNTERLAENGEN-FRAGMENTE (PyMuPDF4LLM, 10.07.2026): Buchstaben mit Unterlaengen "
        "(g/p) reissen aus Woertern und landen als `**<u>g</u>**`-Fragment am Zeilenende "
        "('Zauber rad **<u>g</u>**' = 'Zaubergrad'; auch doppelt: '<u>g g</u>'). "
        "importer.import_markdown._repariere_fragmente setzt sie dokumentverifiziert "
        "zurueck (~62 betroffene Zeilen).",
        "KAPITAELCHEN-Binnenheadings kommen als Gross-klein-Mischmasch an ('zAubern in "
        "rüstung', 'einen wirKenden zAuber identifizieren') - nur Kosmetik im Body "
        "(H6 wird dort nicht gesplittet), FTS ist case-insensitiv.",
        "SPACE-RISSE ohne fehlenden Buchstaben ('Charakterer stellung') sind nicht sicher "
        "von echten Zwei-Wort-Headings unterscheidbar -> bewusst NICHT repariert; betrifft "
        "nur Kapitel-Headings (Breadcrumbs), keine Eintragsnamen.",
        "STATBLOCK-KAESTEN sind `#### **<mark>Name</mark>**` (324x, auch eingebettet in "
        "Beschwoerungszaubern/Magischen Gegenstaenden) -> eigener Chunk mit kategorie "
        "'monster', NICHT in den Breadcrumb-Stack (sonst haengt 'Feuerball' unter "
        "'Drakonischer Geist').",
        "Die ZUSTAENDE stehen als H6 im Kapitel 'Regelglossar' ('Gepackt (Zustand)') - "
        "SPLIT_REGELN['srd-de'] splittet dort bis H6; damit schliesst srd-de die "
        "Zustands-Luecke von open5e-srd-2024.",
        "Einzeleintraege liegen je Kapitel auf ANDEREN Heading-Ebenen (Zauber/Gegenstaende/"
        "Talente/Hintergruende=H6, Monster=H3/H4, Klassen=H3/H5) -> kapitelabhaengige "
        "SPLIT_REGELN statt festem Level.",
        "LABEL-PSEUDO-HEADINGS (10.07.2026, Phase-2-Fund): PyMuPDF4LLM macht aus fetten "
        "Inline-Labels teils Headings ('### **Kreaturentyp:** Humanoide', '### "
        "**Reichweite:** 9 Meter') -> zerriss die Spezies Elf/Gnom/Halbling/Mensch/Tiefling/"
        "Goliath und ~110 Zauber ('Reichweite: 9 Meter' als Eintragsname). Erkennung in "
        "import_markdown._LABEL_HEADING: erster Fettblock endet mit ':' -> Fortsetzungszeile."
        " Namen mit Doppelpunkt MITTEN im Fettblock ('Kämpfer-Unterklasse: Champion', "
        "'Schritt 1: Klasse auswählen') sind echte Headings und bleiben es.",
        "SPEZIES-TABELLENKAESTEN ('Drakonische Ahnen', 'Elfische Abstammungen', "
        "'Unholdisches Erbe') liegen auf DERSELBEN Heading-Ebene wie die Speziesnamen - "
        "per Split-Level nicht trennbar. MERGE_REGELN['srd-de']: im Kapitel 'Beschreibungen "
        "der Spezies' ist nur eigenstaendig, was mit '**Kreaturentyp:**' beginnt (jede "
        "Spezies-Beschreibung tut das); Rest wird an den vorherigen Eintrag angehaengt.",
        "SPALTEN-LESEREIHENFOLGE (PyMuPDF4LLM, Talent-Seite 99): die zweispaltige Seite "
        "kommt verschraenkt an - drei 'Gabe'-Talente stehen dadurch unterm "
        "'Kampfstil-Talente'-Heading (falscher Kontext-Breadcrumb). Die BODIES sind "
        "intakt. Konsequenz: Talent-KATEGORIE nie aus dem Breadcrumb lesen, sondern aus "
        "der Typzeile im Eintrag ('_Epische-Gabe-Talent (Voraussetzung: ...)_') - so "
        "macht es charakter._TALENT_TYPZEILE.",
        "BOON/GABE-PAARE fehlen bei dnddeutsch (2024-Neubegriffe) -> ohne Glossar-Zeile "
        "dedupen die Options-Listen nicht (Boon of Fate neben Gabe des Schicksals). "
        "Geloest ueber import_glossar.SRD_2024_BEGRIFFSPAARE (bestands-belegte Paare, "
        "offline geseedet); gleiches Muster fuer 4 Unterklassen + Two-Weapon Fighting "
        "+ 25 Zauber (2024-Umbenennungen wie Fly='Flug', Schweizer ss, Neuzugaenge).",
        "SPALTEN-VERSCHRAENKUNG + VERLORENE HEADINGS (Synthese-Funde 12.07.2026, alle in "
        "importer/import_markdown._srd_de_reparatur behoben): Umstoßen-Regeltext klebte "
        "in 'Zweihändig' (jede Zweihandwaffe 'konnte umwerfen'!), 'Weitreichend' stand "
        "unter zweitem 'Nahkampfreichweite'-Heading, Vampirbrut-Karte war headinglos "
        "(Anker: Typzeile + RK-16-Kopf; blosse Typzeile kollidiert mit Todesalb!), "
        "Eissturm/Symbol/Windwall/Goettliches-Wort-Fortsetzungen lagen hinter FREMDEN "
        "Eintraegen, Beeinflussen-Absaetze im Regelglossar-'Attributswurf'. Vollseitige "
        "Monster (Solar) = H3-Abschnitt + gleichnamiger <mark>-Kasten -> MERGE_REGEL "
        "'gleicher_name_wie_vorher'. Kapitaelchen-Garbles betreffen auch NAMEN (nicht "
        "nur Bodies): 8 kuratierte Fixes; Mehrfach-g-Headings ('Übun im Um an mit' + "
        "'g g g') kittet die generische Fragment-Reparatur NICHT -> explizite Ersetzung. "
        "Laufkopf 'Systemreferenzdokument 5.2.1'+Seitenzahl stand in 374 Bodies "
        "(1 legitimer Rest in 'Rechtliche Informationen'); U+2011-Wortrisse werden "
        "dokumentvokabular-verifiziert gekittet (Ergaenzungsstriche 'Vor- oder' bleiben).",
        "GLOSSAR-FUZZY IST KEINE IDENTITAET (SYN-P0-001, 12.07.2026): fuzz.ratio 88.9 "
        "machte 'Aktionen' zur offiziellen Uebersetzung 'Reaktionen'. lookup() traegt "
        "seither match='exakt'|'fuzzy'; Identitaet/Anzeige/Uebersetzung nutzen NUR exakt "
        "- dafuer brauchen Alltags-SINGULARE eigene Zeilen (dnddeutsch liefert Plural): "
        "import_glossar.KERN_SINGULAR_PAARE.",
        "NFD + SOFT-HYPHEN (10.07.2026): PyMuPDF4LLM liefert einzelne Namen "
        "NFD-dekomponiert ('Einflüsterung' als u+Kombinationszeichen; 5 Namen) und "
        "~131 Eintraege mit U+00AD (Druck-Layout) -> exakte Stringvergleiche und "
        "FTS-Token brechen. Fix an der Wurzel: _chunks normalisiert das Markdown auf "
        "NFC und strippt U+00AD (wirkt ab dem naechsten Re-Import); alle "
        "VERGLEICHSpfade nutzen glossar.norm_begriff (NFKD-basiert, also NFD-fest).",
    ],
    "dnddeutsch-api": [
        "Wildcard '*' haengt automatisch HINTEN am Suchbegriff (nicht vorn); mehr als "
        "30 Treffer = Fehlerantwort -> Suchbegriff eng fassen.",
    ],
}
