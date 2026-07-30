# Foliant — Konzept & Betrieb (das „Wie")

**Stand: 25.07.2026 · MVP live auf dem Raspberry Pi**

Die technische Sicht auf Foliant: Architektur, Datenmodell, Pipelines, Betrieb,
Entscheidungen und Fallen. Das verbindliche **„Was"** steht in [SPEC.md](SPEC.md), das
Offene in [BACKLOG.md](BACKLOG.md).

**Inhalt:** [1 Architektur](#1-architektur) · [2 Tech-Stack](#2-tech-stack) ·
[3 Datenmodell](#3-datenmodell) · [4 Ingestion](#4-ingestion-pipelines) ·
[5 Suche & Deutsch-Logik](#5-suche--deutsch-logik) · [6 MCP-Tools](#6-mcp-tools) ·
[7 Charakterbogen-Übersetzer](#7-charakterbogen-übersetzer) ·
[8 Betriebsweg](#8-betriebsweg-kanonisch) · [9 Deployment im Detail](#9-deployment-im-detail) ·
[10 Entscheidungen](#10-entscheidungen-warum-es-so-ist) ·
[11 Tests & DoD](#11-tests--definition-of-done) · [12 Gotchas](#12-gotchas) ·
[13 Sicherheitsmodell](#13-sicherheitsmodell) · [14 SYN-Register](#14-syn-befunde-register)

---

## 1. Architektur

**Betriebsmodell: der Pi betreibt, der Mac entwickelt.** Server **und** Importe laufen auf dem
Pi; der Mac dient nur der Entwicklung (Code schreiben) und Administration (Code aufs Pi
schieben, Importe per SSH auslösen). So gibt es genau einen operativen Bestand, und der Pi
überlebt einen Mac-Ausfall.

```
IMPORT (einmalig/gelegentlich)                    LAUFZEIT (dauerhaft)
──────────────────────────────                    ───────────────────────────────
Dt. SRD 5.2.1 (PDF) ─┐                             Claude (Client)   Browser
Engl. SRD (Markdown) ─┤  PyMuPDF4LLM/Docling             │              │
Eigene dt. PDFs ──────┤────────────► Markdown            ▼              ▼
Open5e (API) ─────────┤  Transform  ─► Chunks     Cloudflare Named Tunnel
DDB-Bücher (Exporter) ┘                  │                    │
dnddeutsch-API ──────────► Glossar       ▼         gateway (Caddy :8080)
                                         │           │                  │
                                         ▼           ▼                  ▼
                                   SQLite + FTS5 ◄─ foliant        web (Charakterbogen)
                                         ▲          IP-Filter +
                       Admin-CLI ────────┤          Geheimpfad
                       Datasette (127.0.0.1, read-only, SSH-Tunnel)
```

Zwei klar getrennte Ebenen:
- **Import:** Quellen → Markdown/JSON → Chunks → SQLite. **Netz nur hier.**
- **Laufzeit:** FastMCP serviert die Werkzeuge über HTTP. Nur lokale SQLite-Abfragen —
  offline, schnell, geerdet.

### Container

| Dienst | Rolle |
|---|---|
| `foliant` | MCP-Server (uvicorn), 16 Tools, **read-only** auf `data/foliant.sqlite` |
| `web` | Charakterbogen-Website (eigene Kennwort-Seite; `read_only`, `cap_drop: ALL`, 512 MB / 1 CPU) |
| `gateway` | Caddy davor; routet nach Pfad. **Keine Access-Logs** — der MCP-Pfad enthält das Geheim-Token |
| `cloudflared` | Named Tunnel → `dnd.magnetron.me`, Origin `http://gateway:8080` |
| `discord` | Discord-Bot der Runde (Threads, `/regel`); kein Port, nur ausgehend; Guild-Sperre |
| `datasette` | optional (`--profile admin`), read-only Datenblick, nur `127.0.0.1` |
| `ddb-exporter` | optional (`--profile ddb`), kurzlebiger DDB-Export, **ohne DB-Mount** |

**Gateway-Routing:** `/mcp`, `/<token>/mcp`, `/health` und `/ready` → `foliant`; alles andere
→ `web`. Ein falscher Token-Pfad landet bei `foliant` und bekommt dort 403/404, **nie**
Website-HTML. Caddy prüft den Token nicht — das bleibt in `app/zugriff.py`.

**Warum Container:** Isolation gegenüber anderen Projekten auf demselben Gerät,
ARM64-Portabilität (Pi 4 → Apple-Silicon-Mac mini, gleiches `Dockerfile`/`compose`),
reproduzierbares Neuaufsetzen. *(Alternative wäre venv + `systemd` — einfacher für ein
einzelnes Projekt, aber ohne Mehrprojekt-Isolation und nicht auf den Mac portierbar.)*

---

## 2. Tech-Stack

| Baustein | Wahl | Rolle |
|---|---|---|
| MCP-Framework | **FastMCP** | Tools + `http_app(path="/mcp", stateless_http=True)` |
| ASGI-Server | **uvicorn** | serviert `app.server:app` |
| Datenbasis/Suche | **SQLite + FTS5** | Volltext, bm25, eine Datei |
| PDF→Markdown | **PyMuPDF4LLM** (Standard), **Docling** (Fallback) | Ingestion |
| OCR-Vorstufe | **OCRmyPDF/Tesseract** (deu+eng) | gescannte PDFs |
| Deutsch-Glossar | **dnddeutsch.de-API** | offizielle Begriffe (Ulisses) |
| Weitere Quelle | **Open5e-API** (v2) | engl. Sofort-Basis |
| Container | **Docker + docker compose** | Isolation + ARM64-Portabilität |
| Erreichbarkeit | **cloudflared** (Named Tunnel) | Geheimpfad + IP-Allowlist |
| Gateway | **Caddy** | Pfad-Routing vor `foliant`/`web` |
| Übersetzung (Bogen) | **Anthropic-API** (httpx) | Modell-ID über `.env`, nicht hart kodiert |
| Daten-Inspektion | **Datasette** (optional, lokal) | read-only Admin-Blick |

Abhängigkeiten sind **exakt gepinnt** (`requirements.txt`, `requirements-ddb.txt`).
Python 3.11+ (Container: 3.12).

---

## 3. Datenmodell

Schema: `db/schema.sql` (getestet, `user_version = 2`). Kernprinzip: **Datenshape über alle
Quellen vereinheitlichen, Provenienz (Quelle/Edition/Seite) sichtbar behalten.**

- **`quellen`** — Register aller Quellen: `edition` (2024/2014, **NOT NULL**), `sprache`,
  `herkunft` (pdf/ddb/srd-md/open5e/manuell), `lizenz`, `prioritaet` (Dubletten-Präzedenz;
  **kleiner = Vorrang**), `inhaltsart` (u. a. `abenteuer_setting` → Spoiler-Hinweis).
- **`eintraege`** — Inhalts-Chunks (Rückgrat): `kategorie`, `name_de`/`name_en`, `edition`
  (**NOT NULL** → kein verwaister Inhalt), `seite` (optional), `body_md`, `kontext`
  (Breadcrumb). FK-Cascade von `quellen`.
  `kontext` trägt den Breadcrumb (`Klassen > Kämpfer`) **zusätzlich** zur `*Kontext: …*`-Zeile
  im `body_md` — der Body bleibt unangetastet, sonst änderte sich der `inhalts_hash` und der
  gesamte Bestand bräuchte einen Re-Import. Bestands-DBs backfillt
  `db.stelle_schema_sicher()` einmalig aus dem Body; die Lesepfade kommen ohne die Spalte
  aus, weil der Serving-Pfad read-only ist und **nicht** migriert.
  **Ehrlich zur Wirkung:** Der Laufzeitgewinn ist klein. Die beiden echten Abfragen
  (`charakter.py`) filtern schon auf `kategorie` + `edition` vor und liefen nie über einen
  Full Scan — gemessen **0,049 → 0,030 ms (Faktor 1,7)**. Der Ertrag liegt darin, dass der
  Breadcrumb ein *Feld* ist statt eines in ein LIKE-Muster interpolierten Strings.
- **`zauber_meta`/`monster_meta`/`gegenstand_meta`** — strukturierte Facetten, erscheinen
  additiv als `facetten` in den Detail-Tools (der `body_md` bleibt unangetastet).
  `zauber_meta`: `grad`, `schule`, `klassen`, `reichweite_m`, `komponenten`, `dauer_min`,
  `konzentration`, `ritual` · `monster_meta`: `hg`, `typ`, `rk`, `tp` ·
  `gegenstand_meta`: `seltenheit` (noch ungeschrieben), `preis_cent`.
  **Einziger Schreiber: `importer/facetten_seeder.py`** (seit 28.07.2026, Befund C1) — er
  leitet aus `body_md` ab, mit genau den Parsern, die der Serving-Pfad ohnehin ruft
  (`app/facetten.py`, `srd_zauberbruecken.kopf_felder`, `srd_begriffsbruecken.preis_cent_von`).
  Vorher schrieb **nur** der Open5e-Import, und zwar aus den nativen API-Feldern in einen
  zweiten Wertraum (`hg = "10.0"` statt kanonisch `"10"`, `schule = "Evocation"` statt
  `"hervorrufung"`) — auf dem Pi waren alle drei Tabellen deshalb schlicht leer.
  Gespeichert wird immer der **kanonische Schlüssel**; die deutsche Anzeigeform macht erst
  die Ausgabe (`_facetten_von`). Was der Text nicht hergibt, bleibt `NULL` — nie geraten.
- **`glossar`** — DE↔EN: `term_de` (kanonisch), `offiziell` (1 → kein `*`, 0 → `*`), `quelle`,
  `edition_quelle`. Grundlage für Begriffswahl und `*`-Kennzeichnung (S6/S9).
- **`eintraege_fts`** — FTS5 (external-content) über `name_de, name_en, body_md`, Tokenizer
  `unicode61 remove_diacritics 2`, plus **drei Trigger** (INSERT/UPDATE/DELETE).

**Getestet:** Trigger feuern, bm25 rankt, `edition NOT NULL` greift, Cascade-Delete lässt die
FTS sauber. Alt-DBs (v0/v1) heilt `app.db.connect()` beiläufig auf Schema v2 — jeder
Import-/Admin-Aufruf genügt.

---

## 4. Ingestion-Pipelines

**Alles wird zu Markdown.** Jede Quelle wird zuerst nach Markdown normalisiert, danach läuft
**eine** Pipeline (Chunker → SQLite). Alle Importe sind **einmalig** — kein Laufzeit-Aufruf.

**Chunking = ein logischer Eintrag pro Zeile** (ein Zauber / ein Monster / ein
Regelabschnitt), heading-basiert. **Der zentrale Qualitätshebel** — iterativ an echten Seiten
justieren über `SPLIT_REGELN` / `MERGE_REGELN` / `BEREINIGUNG` je Quelle in
`importer/import_markdown.py`.

Nach jedem Import: **FTS `rebuild`** (macht der Importer selbst). Re-Import ist **atomar**
(Kandidat → Prüfung → `os.replace`), idempotent, mit Schrumpf-Schutz.

| Quelle | Weg |
|---|---|
| **Born-digital-PDF** (dt. SRD) | `[[quelle]]`-Block in `config/foliant.toml` → `admin import --quelle <kuerzel>` |
| **Scans MIT OCR-Textschicht** (dt. 2014-Bücher) | Triage meldet „DIGITAL“ — misst aber nur, OB Text da ist, nicht die Chunk-Struktur: `pymupdf4llm` vergibt Heading-Ebenen relativ zum Gesamtdokument, dort liegt der Inhalt komplett auf H6 → eigene `SPLIT_REGELN` mit Level 6 nötig (sonst 3 Riesen-Chunks je Buch, Befund 27.07.2026). **Folgefalle:** auf H6 landet dann auch der Zauberkopf; `_LABEL_HEADING` fing nur die **fette** Form (`**Reichweite:** 9 m`), die Scans setzen sie blank → `KOPF_HEADING` |
| **Gescannte PDFs** | `admin pdf-triage` (Befund) → `admin ocr-pdf` (`--redo` bei Alt-OCR, `--voll` = Neuaufbau) → normale Pipeline |
| **Browser-Druck-PDFs** (DDB-Ausdrucke) | reparierte Original-Schicht **oder** Voll-OCR, je nach Schaden; Konvertierung am Mac |
| **DDB-Bücher** | kurzlebiger Exporter (Netz + Cobalt) → Artefakt → offline `admin ddb-import-all` |
| **Open5e** | `admin import --quelle open5e-srd-2024` (API, einmalig) |
| **Glossar** | `admin import --quelle glossar` (dnddeutsch.de; offiziell = `name_de_ulisses`) |

**Browser-Druck-PDFs im Detail:** Textschichten sind beschädigt (Kerning-Risse,
Mojibake-Fonts, fi/fl-Ligaturverlust). Zwei Muster-Piloten: `efota` (Original + kuratierte
Reparatur) und `frhof` (Original + generiertes, sichtgeprüftes Reparatur-Modul). **Die
Konvertierung nach Markdown passiert am Mac**, das Markdown ist das Import-Artefakt
(`quellen/md/<kuerzel>.md`, `dateipfad` zeigt darauf) — die pymupdf4llm-Heading-Erkennung ist
für diese PDFs umgebungsempfindlich. Qualitätsnachweis per **Kreuz-Audit** (Original vs. OCR:
Würfel/Zahlen/Preise seitenweise) plus Sichtprüfung.

**OCR-Erwartung ehrlich:** gut für Fließtext, fehleranfälliger bei Statblöcken, Tabellen und
Zahlen → Stichprobe vor Freigabe (O3). Scans unter ~300 dpi werden deutlich schlechter.
Ein **Guardrail** lehnt mehrheitlich textlose PDFs beim Import ab, statt eine Rumpf-Quelle zu
schreiben.

---

## 5. Suche & Deutsch-Logik

- **FTS5 + bm25**, mit **Exact-Name-Boost vor Substring** („Feuerball" vor „Verzögerter
  Feuerball"). Retrieval-Qualität ist der halbe Anti-Halluzinations-Schutz — schlechte Treffer
  sind die häufigste Quelle falscher Antworten.
- **Zweisprachig fast geschenkt:** `name_de` und `name_en` sind beide indexiert. Das Glossar
  überbrückt nur den *Suchbegriff*, wenn er im Eintrag nicht vorkommt.
- **Glossar-Brücken aus Struktur-Abgleich** (nie Positions- oder Übersetzungs-Raten):
  Monster über den Stat-Fingerabdruck (Typ+HG+RK+TP+Attribute; Teil-Schlüssel-Ausschluss,
  wenn eine Attributstabelle unlesbar ist), Klassenmerkmale über die Stufenstruktur,
  **Gegenstände über Preis-Buckets** (`importer/srd_begriffsbruecken.py`: Glossar-Hop →
  Kategorie-Sub-Ausschluss → Gesamt-Ausschluss; deutsche Tausenderpunkte beachten —
  „1.000 GM" ist tausend). Geseedet wird nur die **suffixfreie** Form („Backpack" →
  „Rucksack"), sonst entstünden EN→mehrere-offizielle-DE-Konflikte neben den
  dnddeutsch-Zeilen; Dedupe und Anzeige ziehen Klammer-Suffixe kanonisch ab
  (`glossar.KLAMMER_SUFFIX`). Review vor dem Lauf: `admin glossar-paare --nur-neue`,
  Gate danach: die **echten** Konflikte in `admin glossar-audit` nehmen nicht zu.
  Editionsgetrennte Mehrfachformen („Pouch": Tasche/2014 aus dem Spielerhandbuch vs.
  Beutel/2024 aus dem dt. SRD) zählen **nicht** dazu — dort entscheidet S8 eindeutig, und
  `glossar.term_de` liefert genau die neuere Fassung. Das Audit weist beide Klassen
  getrennt aus; nur „ECHTE Konflikte" (gleiche Edition oder keine belegte) brauchen
  Handarbeit.
- **Exakt vs. fuzzy ist getrennt** (SYN-P0-001): Ein Fuzzy-Glossartreffer begründet **nie**
  Identität — sonst wurde aus „Aktionen" die Regel „Reaktionen".
- **Deutsch-first-Sortierung ist explizit**, nicht dem FTS-Rang überlassen: Der englische
  Open5e-Volltreffer darf den deutschen Präfix-Titel nicht verdrängen.
- **Edition-Default 2024;** Klammer-Suffix-Aliasse verhindern, dass der Editions-Fallback eine
  2014-Fassung liefert, obwohl eine 2024-Fassung existiert (SYN-P0-002).
- **Unterabschnitts-Treffer:** Steht ein Begriff nur als Abschnitt in einem Sammel-Eintrag
  („Kampfrausch" in „Klassenmerkmale des Barbaren"), wird er vor jedem Editions-/Sprach-
  Rückfall dort gesucht — inklusive **Nachsuche nur in der Ziel-Edition**, weil am vollen
  Korpus sonst der wörtliche 2014-Treffer gewinnt.
- **Begriffs-Leiter (Deutsch):** aktuelles offizielles Deutsch 2024 → offizielles Deutsch aus
  Altbüchern + Ulisses-Glossar → inoffiziell (`*`) → keins (`*`). Englisches Original **immer**
  in Klammern.
- **Dubletten/Präzedenz** über `quellen.prioritaet` (dt. Quellen < DDB < Open5e). Echte
  **Quellkonflikte gleicher Edition** werden nicht still entschieden, sondern ausgewiesen
  (SYN-P1-009).

---

## 6. MCP-Tools

Namensschema `foliant_<verb>_<nomen>` (kollisionsfrei neben anderen Connectoren). Such-Tools
liefern **knappe** Treffer, Detail-Tools die volle Ausgabe — das hält die Kontextlast niedrig.

- **Nachschlagen (6):** `foliant_suche_bestand`, `foliant_hol_regel`, `foliant_hol_zauber`,
  `foliant_hol_monster`, `foliant_hol_gegenstand`, `foliant_uebersetze_begriff`
- **Charaktererstellung (10):** `foliant_liste_klassen|spezies|hintergruende|talente`,
  `foliant_hol_klasse|spezies|hintergrund|talent`, `foliant_hol_attributswerte`,
  `foliant_pruefe_build`
- **Status:** `/health` (offen), `/ready` (prüft DB + FTS, 503 bei kaputtem Bestand)

Alle Tools sind als `readOnlyHint` deklariert, haben `Literal`-Enums und Bounds und liefern
diskriminierte Ergebnisformen (`gefunden|mehrdeutig|fehler|verfuegbar`). Suchtreffer
tragen eine stabile `eintrag_id`, über die der Detailabruf denselben Eintrag exakt nachlädt.

**Arbeitsteilung:** Der Server liefert Daten, Suche und Validierung; **Claude führt das
Gespräch.** Die Verhaltensregeln laufen über drei Kanäle — der zuverlässigste sind die
**Grounding-Hinweise in den Tool-Ausgaben** (siehe [SPEC.md](SPEC.md) §7).

---

## 7. Charakterbogen-Übersetzer

Zweiter Dienst neben dem MCP: englischer D&D-Beyond-PDF-Export → ausgefüllter offizieller
deutscher WotC-Bogen 2024, druckbar. Anforderungen C1–C7: [SPEC.md](SPEC.md) §14.

```
DDB-PDF (EN) ──[1 Extractor]──► neutrales Modell (EN) ──[2 Übersetzer]──► Modell (DE) ──[3 Renderer]──► DE-Bogen-PDF
             deterministisch                          Claude + Foliant                 deterministisch
```

### Module (`app/charakterbogen/`)

| Datei | Rolle |
|---|---|
| `modelle.py` | Neutrales Charaktermodell. Übersetzbares als `UeText{en,de,art}`, Zahlen roh. `roh_felder` = verlustfreies Protokoll aller befüllten Widgets. |
| `ddb_pdf.py` | **Extractor**: liest verwaiste `/Widget`-Annotationen (kein AcroForm) via PyMuPDF, Smart-Join der Fragmente, Fingerprint-Prüfung der Exportfamilie. |
| `feldkarten/*.json` | `source_map` (DDB-Feld → Modellpfad), `layout_map` (Modellpfad → Position auf dem DE-Bogen), `code_map` (feste Kürzel). |
| `terminologie.py` | Löst feste Begriffe **in-process über `app.glossar`** auf — kein zweites Glossar. |
| `uebersetzer.py` | Provider-Vertrag + Anthropic-Adapter + Fake. Zweistufige Übersetzung, Übersetzungsgedächtnis, JSON-Vertrag mit 1× Retry. |
| `de_bogen.py` | **Renderer** (fitz-Overlay): zeichnet auf eine Kopie der DE-Vorlage, Auto-Fit, Fortsetzungsseiten, Kalibrier-Modus. |
| `glossar_export.py` | Erzeugt die glossar-nur-DB für den Web-Container (kein privater Buchinhalt dorthin). |
| `web.py` | Starlette-App: `GET /`, `POST /bogen`, `GET /health`. Kennwort-Seite, Ein-Konvertierung-Semaphore, keine Persistenz, `no-store`/CSP. |

### Die tragenden Entwurfsregeln

**Zwei LLM-Stufen statt einer.** (1) Belegte Begriffe kommen deterministisch aus dem Glossar.
(2) Stufe 1 übersetzt unbelegte Eigennamen („Warrior of Shadow") in einem kurzen eigenen
Aufruf → §5-Form mit `*` **und** als bindende Vorgabe für Stufe 2. (3) Stufe 2 übersetzt die
Fließtexte mit allen Namen als Vorgabe. Ohne diese Trennung hieß derselbe Name im Feld
„Krieger des Schattens" und im Fließtext „Kämpfer des Schattens". *Gemessen: Stufe 1 ≈ 6 s,
Stufe 2 ≈ 37 s, gesamt ~44 s (API-bedingt 42–80 s).*

**Listen laufen gar nicht durchs Sprachmodell** (`_liste_deterministisch`). Zwei Gründe:
- *Sachliche Fehler:* „Crossbow, Hand" ist DDBs invertierte Schreibweise für **eine** Waffe.
  Das Modell zerlegte sie am Komma zu „Armbrust" + „Handarmbrust" und bescheinigte damit eine
  Vertrautheit, die der 2024-Mönch nicht hat. Der Extractor normalisiert invertierte Namen
  jetzt **vor** allem anderen.
- *Stabilität:* „Wargong" hieß je Lauf „Kriegsgong", „Trommel" oder blieb englisch.

**Amtliche Begriffe kommen aus dem Bestand, nicht vom Modell.**
- `glossar.begriffe_im_text()` scannt jeden Fließtext **vor** dem LLM-Lauf und erzwingt
  amtliche Begriffe (Gepackt statt „ergriffen").
- **2024-Klassenmerkmalsnamen** (größter Hebel): Der Bogen sagte „Angriffe abwehren*
  (Deflect Attacks)", der Foliant amtlich **„Angriffe umleiten"** (SRD 5.2.1 de, S. 70) —
  Glossar und dnddeutsch kannten die 2024-Namen nicht, obwohl der eigene Bestand sie führt.
  `importer/srd_klassenmerkmale.py` gleicht die Struktur ab (srd-de `###### N. Stufe: Name`
  ↔ ddb-br-2024-en `Level N: Name`). **Nur beweisbare Zuordnungen** werden geseedet: srd-de
  sortiert je Stufe alphabetisch DEUTSCH, DDB alphabetisch ENGLISCH — reine Positions-Paarung
  erzeugte real `Extra Attack → Betäubender Schlag`. Stufen: (1) Anker `<K> Subclass` ↔
  `…-Unterklasse`, (2) belegte Glossar-Paare, (3) belegte Sub-Features identifizieren ihr
  Eltern-Merkmal, (4) Ausschlussprinzip bei genau einem Rest. Alles andere wird ehrlich
  verworfen. **Endstand: 214 offizielle Paare.**
- Die **Vorlagen-Labels** des gedruckten WotC-Bogens gelten selbst als offizielle Quelle
  („Heldische Inspiration") — so können Fließtext und Vordruck nicht auseinanderlaufen.

**Nachfragegetriebenes Nachschlagen schließt die Korpus-Lücke.** Das Glossar-Seeding ist
*bestandsgetrieben* (fragt nur Eintragsnamen ab) — der Bogen braucht aber Begriffe aus dem
*hochgeladenen Charakter*. Drei Bausteine: (1) `DnddeutschNachschlager` schlägt unbelegte
Begriffe VOR der LLM-Stufe bei dnddeutsch nach (gemeinsamer Cache/Drossel mit dem Importer);
Treffer → ohne Stern + Best-Effort-Upsert. Offline oder Zeitbudget (30 s) erschöpft → LLM +
ehrlicher Stern. (2) **Klammer-Lemma-Regel:** „Oil (flask)" belegt zusätzlich „Oil → Öl", nur
bei eindeutigem Kern. (3) `make glossar-vom-pi` holt die Glossar-Tabelle des vollen Bestands
in die Dev-DB — erst damit sind lokale `*`-Urteile belastbar.

*Ehrliche Sterne bleiben:* Buch-Eigennamen ohne deutsche Ausgabe („Mist Wanderer") und echt
mehrdeutige Lemmata („Rope": dnddeutsch kennt nur Hanf-/Seidenseil).

**Struktur- und Layouttreue.**
- DDB-Absatzgrenzen bleiben erhalten; der Smart-Join entscheidet an der Box-Grenze per
  `_ist_absatzwechsel` (Satzende links + Sub-Feature-Kopf rechts, im Zweifel Leerzeichen —
  nie Text zerreißen). Merkmalskopf als eigene fette Zeile, darunter die Absätze, zuletzt die
  Aktionsökonomie als `· …`-Zeilen.
- **Eine Schriftgröße je Kasten**; Fortsetzungsseiten erben die Größe der Ursprungsbox.
- **Nie stumm überlaufen:** Auto-Fit → §5-Klammer opfern → horizontal stauchen.
- **Fortsetzungskopf immer**, wenn ein Merkmal über die Box bricht; Vorlagen-Kopien tragen nur
  den **Namen** im Kopf. Seitenzahlen nur, wenn Fortsetzungsseiten eingefügt wurden.
- **Deterministische Notation:** d→W auf **jedem** Feld (5d8→5W8); Zauber-Notizen `V/S`→`V/G`,
  `S/M`→`G/M`, `D:`→`WD:`; deutsche Anführungszeichen font-sicher.
- **Mehrklassen:** „Fighter 3 / Wizard 2" ließ Klasse/Stufe stumm leer. Jetzt „Kämpfer 3 /
  Magier 2 (Fighter 3 / Wizard 2)"; die Charakterstufe ist die regeldefinierte SUMME.

**Bewusste Auslassungen** (extrahiert, aber nicht gerendert — kein Feld auf dem DE-Bogen):
passive Einsicht/Untersuchung, Zauber-Herkunft/Seitenreferenzen, der statische ACTIONS-Block
(Regel-Boilerplate), Spielername. **Gerendert** werden dagegen Dunkelsicht (zweite Zeile im
Bewegungsrate-Feld) und Traglast (kg, Fuß der Ausrüstungs-Box).

> **Nicht neu bauen:** Eine **Kurzfassung ohne Merkmalstexte** (ZIP mit zwei Bögen) war
> umgesetzt und wurde am 17.07.2026 nach zwei Nachbesserungsrunden bewusst **komplett
> entfernt** — die reine Namensliste trägt zu wenig Information. `POST /bogen` liefert genau
> EINE vollständige PDF. Strukturtreue geht vor Kompaktheit: durch die erhaltenen Absätze
> wächst ein voller Bogen von 3 auf 4 Seiten. Erwartet und akzeptiert.

### Lokal ausführen
```sh
.venv/bin/python -m pytest -q tests/test_charakterbogen_*.py          # nur synthetische Fixtures
.venv/bin/python -m uvicorn app.charakterbogen.web:app --port 8099    # GET / ohne API-Key
```
Die echten Vorlagen liegen gitignored unter `vorlagen/charakterboegen/`; die privaten
Golden-Tests laufen gegen sie und sind ebenfalls gitignored.

---

## 8. Betriebsweg (kanonisch)

**Ein** verbindlicher Weg von Null bis „Runde nutzt es". Details je Schritt in §9.

### 1. Bestand bauen
```
python db/init_db.py data/foliant.sqlite
python -m app.admin import --quelle srd-de              # dt. SRD (Reparaturpaket greift)
python -m app.admin import --quelle open5e-srd-2024     # Open5e-API
python -m app.admin import --quelle glossar             # inkl. Kern-Singulare
```
Reihenfolge: **Bestand → Facetten → Glossar.** Die Facetten laufen automatisch am Ende jedes
Quellen-Imports mit (Voll-Lauf, idempotent, ~0,1 s je 3000 Einträge). Für eine bestehende DB
ziehst du sie **ohne Re-Import** nach — wichtig, weil ein Re-Import die Namensreparatur der
2014-Scans zunichte macht:
```
python -m app.admin import --quelle facetten
```

### 2. Freigeben = testen (Pflicht-Gate)
```
make test                            # pytest (beide venvs) + admin check + smoke + Golden-Suite
make test-golden-pi                  # Golden-Suite gegen den VOLLEN Korpus — Pflicht!
python -m app.admin manifest > korpus-manifest.json
```
`make test` grün **plus** Manifest festgehalten = der Bestand ist freigabefähig.

### 3. Server starten
- **Lokal (Dev):** `.venv/bin/uvicorn app.server:app --port 8000` → `GET /ready` == 200,
  MCP unter `http://localhost:8000/mcp` (kein Geheimpfad).
- **Pi:** `.env` mit `FOLIANT_PFAD_TOKEN` (≥16 Zeichen, sonst bricht der Start ab),
  `FOLIANT_PRODUKTION=an`, `CLOUDFLARE_TUNNEL_TOKEN` → `docker compose up -d --build foliant`.

### 4. Connector eintragen
Volle URL inkl. Geheimpfad: `https://<host>/<FOLIANT_PFAD_TOKEN>/mcp` — kein OAuth.
Verhaltensschicht: Claude-Projekt mit `config/projektanweisung.md` einrichten —
die Spieler finden sie kopierbereit auf der Charakterbogen-Website („Foliant im Claude-Chat“).
Die Seite liest sie zur Laufzeit aus `config/projektanweisung.md` (über
`config.stil.projektanweisung`, dieselbe Lesestelle wie Eval, Kopier-Skript und Kanal-Sync-Test)
und verteilt so nie eine veraltete Fassung; nach Prompt-Änderungen genügt
`docker compose restart web` — die Datei ist read-only gemountet.

### 5. Abnahme fahren
Checkliste in [BACKLOG.md](BACKLOG.md) §2 im Connector durchspielen (T2/T10/T12 + P0-Prüfung).

### 6. Laufender Betrieb
- **Readiness:** `curl http://localhost:8000/ready` (503 bei kaputtem/leerem Bestand).
- **Uptime:** externer Monitor auf `https://<host>/health` (immer offen, nur Status).
- **Off-Site-Backup (nächtlich):** `admin backup` erstellt ein **konsistentes** Online-Backup
  über die SQLite-Backup-API (verträgt einen laufenden Import — anders als `cp`/`rsync` auf
  die offene Datei), **verifiziert** es (integrity_check + FTS-Zeilengleichheit; scheitert die
  Prüfung, wird die Datei verworfen) und hält die letzten `--behalten` Stände (Default 14).
  Danach das Verzeichnis auf ein zweites Gerät spiegeln — **der Spiegel-Schritt ist die
  eigentliche Off-Site-Sicherung:**
  ```
  0 3 * * * docker compose exec -T foliant python -m app.admin backup && \
            rsync -a <db-ordner>/backups/ <offsite>:foliant-backups/
  ```
  Restore-Probe: ein Backup als `data/foliant.sqlite` zurückspielen → `make test-daten` muss
  bestehen.
- **Token-Rotation bei Leak:** neuen Token in `.env` → `docker compose up -d --build foliant`
  → neue URL an die Runde. **Alte Logs gelten als tokenbelastet** (der Pfad *war* das Secret).
- **Feedback-Schleife (O4/M5):** Der Server protokolliert jede Nachschlage-Anfrage in eine
  **separate** Log-DB (`data/foliant-protokoll.sqlite`, Config `[protokoll]`, Rotation bei
  50 000 Zeilen) — die Korpus-DB bleibt read-only, ein Log-Fehler bricht nie einen Lookup.
  Regelmäßig sichten:
  ```
  docker compose exec -T foliant python -m app.admin suchbericht        # --tage 30 --json
  ```
  Nulltreffer/Fuzzy-Landungen/Mehrdeutigkeiten/Übersetzungs-Lücken sind die
  Kuratier-Kandidaten für Glossar-Paare und Chunking-Korrekturen; der Kopf liefert die
  B9-Antwortzeiten (p50/p95). Die Log-DB liegt bewusst außerhalb von Backup-Glob und
  Manifest und ist im Datasette-Container (read-only auf `data/`) direkt browsbar.

### Admin-CLI (vollständig)
```
status        Bestand je Quelle/Edition/Kategorie + Glossar
manifest      Korpus-Fingerabdruck (inhalts_hash) - nach jedem Import festhalten
import        --quelle <kuerzel> | glossar | facetten (Facetten ohne Re-Import nachziehen)
pdf-triage    welche PDFs haben keine Textschicht?
ocr-pdf       --datei <pfad> [--redo] [--voll]
reindex-fts   FTS neu aufbauen
check         Integritaet, FK, FTS-Suchbarkeit, Editionen, Textqualitaet, Facetten-Deckung
glossar-audit Glossar-Stand und -Herkunft pruefen
glossar-paare Kandidaten fuer neue Glossar-Paare zeigen [--nur-neue] [--json]
suchbericht   Auswertung des Abfrage-Protokolls: Nulltreffer, Fuzzy, Mehrdeutigkeiten
backup        konsistentes, verifiziertes Online-Backup mit Rotation
ddb-pruefe | ddb-import | ddb-import-all | ddb-remove
```

**Bewusst kein öffentliches Admin-Panel** — das wäre auf dem getunnelten Pi unnötige
Angriffsfläche. Der grafische Blick läuft über Datasette an `127.0.0.1` per SSH-Tunnel:
```
docker compose --profile admin up -d datasette
ssh -L 8001:localhost:8001 <nutzer>@<pi-ip>     # dann http://localhost:8001
```

---

## 9. Deployment im Detail

### Pi vorbereiten
**64-bit Raspberry Pi OS Lite** flashen (64-bit ist Pflicht für ARM64-Images). Dann:
```
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
sudo systemctl enable docker      # startet Docker beim Boot
```
Einmal aus- und wieder einloggen. Test: `docker run --rm hello-world`.

### Code aufs Pi
```sh
make deploy-pi
```
Das ist der **eine** Weg: rsync → `docker compose up -d --build foliant` → Golden-Suite am
Vollbestand. Alle drei Schritte hängen zusammen, weil das Weglassen jedes einzelnen schon
schiefgegangen ist (Rebuild vergessen → alter Code meldet „Erfolg"; Golden vergessen →
korpusabhängige Regression bleibt unentdeckt).

**Das SSH-Ziel steht einmalig als `PI=` in der `.env`** (gitignored; Vorlage in
`.env.example`) — nicht in dieser Doku: das Repository ist öffentlich und die
betreiberspezifischen Angaben sind bewusst anonymisiert. Einmalig übersteuern geht weiter
mit `make deploy-pi PI=pi@<host>`; fehlt beides, brechen alle Pi-Ziele mit einem Hinweis ab,
statt auf einen Platzhalter zu laufen.

> **Nie `--delete`, nie `data/` mitschicken.** Die Mac-DB ist nur ein Subset und würde den
> vollen Pi-Bestand überschreiben; gitignorierte Privatmodule würden verschwinden. Genau
> deshalb stehen die Ausschlüsse im `Makefile` und nicht als Warnung neben einer
> Kommandozeile zum Abtippen.

**Der Preis dieser Regel: der Deploy fügt hinzu und aktualisiert, er entfernt nie.** Eine
im Repository gelöschte Datei bleibt auf dem Pi liegen — und weil das Image sie per
`COPY . .` einbackt, landet sie auch im Container. Am 29.07.2026 nachgemessen: **54
verwaiste Einträge**, die älteste Schicht stammt aus der Doku-Konsolidierung vom 25.07.
(das komplette alte `docs/`-Verzeichnis).

Meist ist das harmlos (Markdown), aber **verwaister Python-Code ist es nicht** — er ist
importierbar. Deshalb nach dem Entfernen einer `.py`-Datei einmal nachsehen:
```sh
# Trockenlauf, loescht nichts - listet nur, was auf dem Pi liegt und lokal fehlt:
rsync -ani --delete <dieselben --exclude wie in make deploy-pi> ./ $PI:~/foliant/ | grep deleting
```
Aufräumen dann **gezielt von Hand**, nie per `--delete`: auf dem Pi liegen auch eigene
Sicherungen des Betreibers (`.env.save`, `config/foliant.toml.bak-*`), die ein pauschaler
Lauf mitnähme. Wer etwas entfernt, legt es besser beiseite (`mv ~/foliant-entfernt-<datum>/`)
als es zu löschen, und baut danach neu.

### Discord-Bot einrichten (einmalig)

1. **Entwicklerportal** (discord.com/developers): Application anlegen → *Bot* →
   Token erzeugen (→ `.env` `DISCORD_BOT_TOKEN`) → **Message Content Intent aktivieren**
   (Privileged Intent; Review-Pflicht erst ab 100 Servern — irrelevant bei einer Guild).
2. **Einladen** mit minimalen Scopes/Rechten: Scopes `bot` + `applications.commands`,
   Rechte *Send Messages*, *Create Public Threads*, *Send Messages in Threads*,
   *Read Message History*.
3. **`.env`**: `DISCORD_GUILD_ID` (Server-ID der Runde — Pflicht, sonst startet der Bot
   nicht), optional `DISCORD_KANAL_IDS`, `DISCORD_TAGESDECKEL` (Default 100/Tag).
4. **Start:** `docker compose up -d --build --no-deps discord` · Logs:
   `docker compose logs -f discord` · Nutzung: `/regel <frage>` oder @Foliant erwähnen;
   Folgefragen im automatisch erzeugten Thread. Nach einem Neustart vergisst der Bot
   laufende Threads und sagt das dort einmalig (Verlauf ist bewusst in-memory).
5. **Kontrolle:** Discord-Anfragen erscheinen im Abfrage-Protokoll
   (`admin suchbericht`) — derselbe Kurations-Kreislauf wie beim MCP.

### Cloudflare Named Tunnel
Zero-Trust-Dashboard → Networks → Tunnels → **Create tunnel** → Token in die Pi-`.env` als
`CLOUDFLARE_TUNNEL_TOKEN`. Public-Hostname-Route: `dnd.magnetron.me` → Service
**`http://gateway:8080`**. Unter *Additional application settings* **nichts** ändern —
insbesondere **„Disable Chunked Encoding" aus lassen** (zerstört SSE/MCP).

### Zugang absichern (zwei Schichten, ohne Nutzer-Management)
Seit dem DDB-Import serviert der Tunnel **private Buchinhalte** → der Endpoint ist nicht offen.

1. **Geheimpfad** — die URL ist der Schlüssel:
   ```
   python3 -c "import secrets; print(secrets.token_urlsafe(18))"
   # Pi-.env:  FOLIANT_PFAD_TOKEN=<wert>
   docker compose up -d --build foliant
   ```
   Connector-URL = `https://dnd.magnetron.me/<wert>/mcp`; der alte `/mcp` liefert 404.
   Geheimer **Pfad**, nicht geheime Subdomain — Subdomains leaken über
   Zertifikats-Transparenz-Logs.
2. **IP-Allowlist** — nur Anthropics veröffentlichte Egress-Ranges (`160.79.104.0/21`,
   `2607:6bc0::/48`) erreichen den MCP-Pfad; geprüft an der von der Cloudflare-Edge gesetzten
   `CF-Connecting-IP`. Eine geleakte URL ist damit **nur über Claude** nutzbar, nie per
   curl/Scanner/Browser. Lokale Aufrufe ohne Edge-Header bleiben möglich; `/health` bleibt
   immer offen. Schalter: `FOLIANT_IP_FILTER=aus`, `FOLIANT_ERLAUBTE_IPS=<cidr,cidr>`.

**Der 403-Test ist Pflicht nach jeder Caddyfile-Änderung:**
```sh
curl -s -o /dev/null -w '%{http_code}\n' -H 'CF-Connecting-IP: 8.8.8.8' \
     http://127.0.0.1:8080/<TOKEN>/mcp     # muss 403 sein
```
Ginge `CF-Connecting-IP` hinter Caddy verloren, wäre die IP-Allowlist *lautlos* aus (der Peer
wäre dann Caddy = private IP = durchgelassen).

**Optionales Edge-Upgrade** (Cloudflare → Security rules, Aktion Block):
```
(http.host eq "dnd.magnetron.me" and http.request.uri.path contains "/mcp" and not ip.src in {160.79.104.0/21 2607:6bc0::/48})
```
`http.host` **niemals** weglassen (sonst trifft die Regel Davids Smarthome-Tunnel).
`uri.path` statt `uri` (sonst umgeht `?x=/mcp` die Regel). `contains "/mcp"` hält den Token
aus der Cloudflare-Konfiguration. Regel **nie löschen und neu anlegen** — im Löschfenster
fehlt die Edge-Schicht.

**Rollback:** Tunnel-Route zurück auf `http://foliant:8000`, Save. Sekunden, keine
Datenänderung. Warum etwas blockiert wurde: Cloudflare → Security → Events (Caddy loggt
bewusst nichts).

### Website (Charakterbogen)
Authlos gebaut, und **jede Konvertierung kostet API-Geld** — der Hostname steht über
Certificate-Transparency-Logs öffentlich. Zugang deshalb über eine eigene **Kennwort-Seite in
der App**, nicht HTTP-Basic-Auth (die erzwingt im Browser immer ein Benutzerfeld;
Eigentümer-Wunsch war *ein* Kennwort).
```
# Pi-.env:
WEB_PASSWORT=<kennwort-der-runde>
ANTHROPIC_API_KEY=sk-ant-…      # eigener Workspace mit Spend-Limit (harter Kostendeckel)
ANTHROPIC_MODEL=claude-sonnet-5
```
```sh
# glossar-nur-DB erzeugen, BEVOR web startet (sonst legt Docker ein Verzeichnis an):
python3 -m app.charakterbogen.glossar_export data/foliant.sqlite data/glossar_web.sqlite
docker compose up -d --no-deps web
```
- **Fail-closed:** Fehlt `WEB_PASSWORT`, ist die Seite zu (503/401).
- Signierter `HttpOnly`-Keks (30 Tage, HMAC **mit dem Kennwort als Schlüssel** → Kennwort
  ändern entwertet alle alten Kekse sofort).
- **`POST /bogen` ist selbst gesperrt**, nicht nur die Seite versteckt.
- 8 Fehlversuche je Absender-IP → 5 min Sperre, plus 1 s Verzögerung je Fehlversuch.
- Ohne `ANTHROPIC_API_KEY` läuft alles außer `POST /bogen` (→ 503).
- **Cache mounten:** `data/cache/dnddeutsch` read-only in den Web-Container, sonst zahlt jeder
  Neustart den Erstkontakt erneut.

### DDB-Buchimport auf dem Pi
```sh
docker compose --profile ddb build ddb-exporter    # einmalig (apsw-sqlite3mc fuer arm64)

# 1. Cobalt aus einer angemeldeten dndbeyond.com-Sitzung nach ~/.ddb-cobalt legen
#    (Entwicklertools -> Application -> Cookies). Wie ein Passwort behandeln.
docker compose --profile ddb run --rm \
  -v /home/pi/.ddb-cobalt:/run/secrets/ddb_cobalt:ro ddb-exporter sync
rm -f ~/.ddb-cobalt        # Secret SOFORT entfernen

# 2. Import als Einmal-Container mit explizitem Privat-Mount (der laufende Serve-Container
#    sieht data/private NICHT)
docker compose run --rm -v ./data/private:/app/data/private \
  foliant python -m app.admin ddb-import-all
docker compose restart foliant
```

**Was `sync` lädt:** alle eigenen Regelbücher, automatisch über das öffentliche
DDB-Verzeichnis aufgelöst; schon Exportiertes wird übersprungen.
- Ältere Bücher ohne Content-Text kommen aus den strukturierten Detailtabellen.
- Abenteuer-/Setting-Bände werden geladen, aber als Spoiler-Inhalt **gekennzeichnet**
  (`inhaltsart=abenteuer_setting`). **Playtest-Material wird gar nicht erst importiert.**
- **Edition nie geraten:** autoritativ aus der Buch-DB (`RPGSourceCategory` bzw.
  `ReleaseDate`). Nicht eindeutig (z. B. „Sage Advice & Errata") → Buch wird **nicht geladen**,
  sondern gemeldet. Soll es trotzdem rein: `[[ddb.buch]]` mit explizitem `edition`.
- Varianten: `sync --dry-run` · `sync --force` (nach Errata) · `ddb-import-all --dry-run` ·
  `admin ddb-remove --quelle <kuerzel>`.
- Diagnose: `inspect --id <ddb-id>` lädt ein Buch, entschlüsselt es und zeigt Tabellen,
  Zeilenzahlen und Spalten — **keine Zellwerte**, kein Artefakt. Der Weg, wenn ein Buch
  leer ankommt und die Frage ist, ob die Struktur oder der Inhalt fehlt.

**Wohin die Bücher landen,** steuert `config/foliant.toml`: `[ddb] ins_hauptbestand = true` →
Merge in die bediente DB (**so läuft der Pi**, siehe [SPEC.md](SPEC.md) §12.1). Ohne die Zeile
landen sie in `data/private/foliant-private.sqlite`, die der Endpoint nicht serviert. Der
Merge ist in beiden Fällen atomar, mit Backup und Integritätsprüfung.

**Lokale Entwickler-Variante:** Cobalt in den macOS-Keychain
(`security add-generic-password -U -a foliant -s foliant-ddb-cobalt -w`, verdeckte Eingabe),
dann `.venv-ddb/bin/python -m importer.ddb_exporter sync` und
`.venv/bin/python -m app.admin ddb-import-all`.

### Bekannte Grenzen
- **Cloudflares Proxy-Read-Timeout: 120 s** (nur Enterprise änderbar). Die
  Bogen-Konvertierung antwortet erst am Ende → `ZEITLIMIT_S` in `web.py` sorgt dafür, dass der
  Nutzer die *deutsche* Fehlermeldung sieht statt Cloudflares Error 524.
- `asyncio.Semaphore(1)` begrenzt Nebenläufigkeit, **nicht die Rate**. Der harte Kostendeckel
  ist das Spend-Limit des API-Workspace.
- **Ressourcen:** Foliant selbst ist leichtgewichtig (< ~200 MB). Bei mehreren Projekten auf
  einem Pi 4 auf RAM achten (8-GB-Modell empfohlen).

### Umzug auf Mac mini
Gleiches Repo, gleiches `compose`. Docker via Docker Desktop oder colima, dann identisch
`docker compose up -d --build`. Tunnel-Token bleibt, URL ändert sich nicht — der Connector
läuft ohne Änderung weiter.

---

## 10. Entscheidungen (warum es so ist)

| Entscheidung | Warum |
|---|---|
| **Geheimpfad + IP-Allowlist statt OAuth** | Claude-Connectors können keine Custom-Header senden; ein server-seitiger Filter ist versioniert und testbar; OAuth wäre für < 5 Nutzer überdimensioniert |
| **Ein internes Schema für alle Quellen** | einheitlicher Tool-Output; Provenienz bleibt sichtbar |
| **Edition sichtbar, nicht wegnormalisiert** | Referenz-MCP-Server normalisieren so, „dass die LLM den Unterschied nicht sieht" — für uns ein Anti-Pattern: **Datenshape** vereinheitlichen, **Provenienz** behalten |
| **Suche und Detailabruf trennen** | Die eine Suche liefert knappe Treffer, die `hol_*` die volle Ausgabe — hält die Kontextlast niedrig. Die Aufteilung der Detailabrufe *je Entitätstyp* ist damit **nicht** begründet (Review 30.07.2026) |
| **Quellen-Macken beim Code, der sie behandelt** | Die Eigenheiten einer Quelle stehen im Modul-Docstring ihres Importers, die Reparatur daneben — damit dieselbe Falle nicht zweimal gelöst wird. Ein *zentrales* Macken-Modul gab es; es wurde von keinem Codepfad gelesen und beschrieb ein zweites Mal, was längst am Lösungsort stand (Chronik: [BACKLOG.md](BACKLOG.md) §5) |
| **Build-Prüfung minimal** | wenige klare Checks statt einer vollständigen Regel-Engine |
| **DELETE-Journal** | Kompatibilität mit Bind-Mount-Volumes |
| **Alles auf dem Pi** | Ein-Geräte-Wunsch; PyMuPDF4LLM ist ARM-tauglich |
| **Docker** | Mehrprojekt-Isolation + ARM64-Portabilität (Pi → Mac mini) |
| **Kein Runtime-Cache** | lokales FTS5 ist schneller als jeder Cache-Layer drumherum |
| **Seite optional, Quelle Pflicht** | API-Quellen (Open5e) haben keine Seiten; entlastet auch das PDF-Parsing |
| **meta-Tabellen nur additiv** | spart Importer-Aufwand, streicht kein Feature |

### ADR: DDB-Buchimport über eigenen Exporter, nicht `ddb-proxy` (10.07.2026)

**Entschieden:** mobile-API-Abruf des ganzen Buchs (user-data → available-user-content →
owned-Filter → get-book-url → ZIP → book-codes → readonly SQLCipher-v3-Entschlüsselung →
`Content.RenderedHTML` → Markdown) in einem kurzlebigen Export-Prozess **ohne DB-Zugriff**,
mit **Artefaktvertrag v1** (manifest.json + entries.jsonl) und offlinem Import.

**`ddb-proxy` ist ausdrücklich verworfen** (extern verifiziert): Der self-hosted Proxy liefert
nur Charaktere, Zauber, Items und Monster — **keine** Klassen/Spezies/Hintergründe/Talente und
keinen Buch-Fließtext; er ist ein „cut down MVP" (letzte Release Feb 2024). **F5 wäre damit
nicht erfüllbar.** Diese Notiz steht hier, damit der Weg nicht später „hilfreich" wieder
geöffnet wird — `[ddb].proxy_url` und `FOLIANT_COBALT` sind bewusst aus allen Vorlagen
entfernt. Die Bedenken gegen undokumentierte Endpunkte adressiert die Architektur durch
Kapselung in **genau ein** Adaptermodul.

**Rückfallebene:** Scheitert der Weg dauerhaft, erfüllen gekaufte deutsche Buch-PDFs über die
bestehende Pipeline den Inhaltsbedarf; DDB bliebe dann unerschlossen.

---

## 11. Tests & Definition of Done

**`make test` ist das EINE Gate.** Es umfasst:
- **Haupt-Suite** (`.venv`) inkl. Abnahme T1–T12 und der **Golden-Suite**
  (`tests/test_golden_bestand.py`), die Regel-**Semantik** am echten Bestand prüft
- **DDB-Suite** in `.venv-ddb` — sonst bleibt sie **unsichtbar rot**
- `admin check` + `tests/smoke_test.py` (deckt alle 16 Tools ab, prüft aktiv auf Header-Müll)

**Grüne Strukturtests beweisen keine Inhalte** (Synthese-Fund 12.07.2026). Nach jedem
srd-de-Re-Import ist die Golden-Suite Pflicht.

**Korpus-Lücke (verbindlich).** Die lokale Dev-DB ist oft nur ein **Subset** (z. B. ohne die
englischen DDB-Bücher), deshalb ist `make test` am Mac bei **korpusabhängigen** Fällen
trügerisch grün. Der Deutsch-first-Ranking-Bug (`hol_regel("Reaktionen")` lieferte den
längeren englischen DDB-Eintrag statt des srd-de-Kernabschnitts) war am Subset unsichtbar und
schlug erst am vollen Korpus zu. Darum nach **jedem Deploy** und **jedem srd-de-Re-Import**
zusätzlich:
```
make test-golden-pi
```

**T2/T10/T12 sind Verhaltenstests** und in pytest nicht beweisbar → Checkliste in
[BACKLOG.md](BACKLOG.md) §2. Wichtigster Dauertest: **T2** — Frage außerhalb des Bestands →
ehrliches „nicht gefunden".

**Dritte Prüfschicht, werkzeuggestützt:** `python -m evals.verhaltens_eval` fährt die
§2-Fälle gegen die echte Claude-API mit den echten Tools (in-process `fastmcp.Client`,
System-Prompt = der §8-Block aus SPEC.md, eine Quelle). Deterministische Marker-/
Format-Grader; weiche Kriterien (C3, D1 …) optional per LLM-Richter, im Report als
`weich` gekennzeichnet. **Bewusst NICHT in `make test`** — kostet API-Tokens (~15 Fälle
× 3–5 Runden, niedrige einstellige Dollar). Report nach `evals/ergebnisse/` (gitignored)
mit den §2-Pflichtfeldern Datum/Modell/`inhalts_hash`; am Subset markiert er
`korpus: lokal (Subset?)` — beweiskräftig ist der Pi-Lauf:
```
ANTHROPIC_API_KEY=sk-… make eval-verhalten-pi
```
A4 (Websuche) und E1 (Injektions-Fixture) kann das Harness nicht prüfen — sie bleiben
ehrlich `uebersprungen` und damit Handarbeit im echten Chat.

**Für Beiträge:** Neue Funktionalität braucht Tests; Bugfixes brauchen einen Regressionstest,
der **ohne** den Fix fehlschlägt. Neue Tool-Ausgaben nennen Quelle/Seite/Version und erfinden
nichts. Der Code ist durchgehend **deutschsprachig kommentiert**; ein Kommentar begründet eine
Einschränkung, die der Code nicht selbst zeigt — kein Nacherzählen der nächsten Zeile.

---

## 12. Gotchas

Kuratiert. Quellen-spezifische Eigenheiten stehen im Modul-Docstring des jeweiligen
Importers (`importer/import_open5e.py` für die Open5e-API, `importer/import_markdown.py`
für srd-de und die Druck-PDFs, `importer/import_glossar.py` für dnddeutsch.de).

- **pymupdf4llm OCRt textlose Seiten STILL, sobald Tesseract installiert ist** →
  `use_ocr=False` in `pdf_nach_markdown` ist Pflicht und gesetzt; OCR nur über die Vorstufe.
- **Das Pi-Image backt den Code ein** (`COPY`). Ein reines `rsync` aktualisiert die Dateien,
  **nicht den laufenden Container** — ein Import lief dann still mit ALTEM Code weiter und
  meldete „erfolgreich" bei unveränderten Daten. Nach jeder Code-Änderung Pflicht:
  `docker compose up -d --build foliant`.
- **`docker compose up --build web gateway` baut über `depends_on` AUCH `foliant` neu** und
  startet den Live-MCP durch → immer **`--no-deps`**.
- **Die glossar-nur-DB muss existieren, BEVOR `web` startet** — sonst legt Docker ein
  Verzeichnis statt der Datei an.
- **`srd_zauberbruecken.fingerabdruck` ist die Beweisgrundlage der 106 geseedeten
  Zauber-Brücken — seine Regexe bleiben roh.** Sie sind nachweislich zu streng
  (`**Komponenten:** V, G, M` läuft ins Leere, weil die zwei Sterne zwischen Label und Wert
  stehen; `Range:?` trifft ohne Wortgrenze das `Range` in `Ranger`). Wer sie „repariert",
  verschiebt Glossar-Paare. Für die Facetten gibt es deshalb `kopf_felder()` mit
  auszeichnungsfreiem Kopf und wortgrenzen-festen Labeln — `tests/test_facetten_seeder.py`
  hält fest, dass der Abdruck sich dabei nicht bewegt.
- **Ein Re-Import spielt die rohen OCR-Namen wieder ein** und macht die Namensreparatur der
  betroffenen Quelle zunichte. Facetten deshalb nie über einen Re-Import nachziehen, sondern
  mit `import --quelle facetten`.
- **Singular und Plural sind im Glossar zwei Inseln.** Die Seeder liefern beide Formen
  (`Opportunity Attack`/`Gelegenheitsangriff` aus dem Kernwortschatz,
  `Opportunity Attacks`/`Gelegenheitsangriffe` aus dem Spielerhandbuch), aber der Zwei-Hop
  kommt von der einen nie zur anderen. Führt der Bestand den Eintrag im Plural und tippt der
  Nutzer den Singular, landet selbst eine Kernregel in der Mehrdeutigkeit.
  `seed_flexionsbruecke_aus_bestand` schließt das — **nur** wo beide Sprachen dieselbe
  Flexionsrichtung zeigen (einseitig wäre es Stemming), und als `offiziell=0`, damit Anzeige
  und Konflikt-Gate unberührt bleiben.
- **Benchmarks gegen den Live-Bestand landen im Abfrage-Protokoll.** Die Tools loggen jeden
  Aufruf — auch synthetische. Nach einer Messreihe steht der Testbegriff als häufigster
  Nulltreffer im `admin suchbericht` und verwässert die Kurationsliste. Entweder gegen eine
  Kopie messen oder beim Sichten des Berichts wissen, was von einem selbst stammt.
- **Die Import-Bilanz ist ein Trend, kein Alarm.** Jeder Import endet mit einer Zeile
  („Bilanz: 12x Abschnitt ohne Regeltext …"). Interessant ist nicht der Absolutwert —
  ein Kapitel-Kopf ohne eigenen Text ist der Normalfall —, sondern die **Veränderung**.
  Wirklich auffällig ist nur `WIRKUNGSLOS`: eine kuratierte Reparatur hat ihren Anker
  nicht gefunden, d. h. ein Quell-Update hat sie lautlos abgeschaltet.
- **Beide Umfangs-Richtungen sind geschützt** (`importer/schwellen.py`): zu wenig ist
  Datenverlust, **zu viel ist ein Zerlegungsfehler** (falsches Split-Level → aus einem
  Buch werden Fragmente). Beide brechen ab, der Bestand bleibt; `--force` hebt beide auf.
- `bm25()` liefert negative Werte → `ORDER BY bm25(...) ASC`.
- Nach jedem Import FTS-`rebuild` (macht der Importer/Admin selbst).
- DB-Journal = **DELETE** (Bind-Mount) — nicht auf WAL umstellen.
- SQLite im Threadpool: **pro Tool-Aufruf eigene Connection**.
- Python-Testfalle: Doku-IPs (`203.0.113.x`) gelten als `is_private`.
- **DDB: ToS-Grauzone, nur privat;** Cobalt nie in argv, `.env`, Logs oder Git.
- **Davids Smarthome-Tunnel auf dem Pi NIE anfassen.**

---

## 13. Sicherheitsmodell

- **Kein Geheimnis im Repository.** Zugangs-Token, Cloudflare-Tunnel-Token und Datenbank
  liegen ausschließlich in `.env` bzw. `data/` — beide gitignored. `.env.example` zeigt die
  Variablen ohne Werte.
- **Zugang** (`app/zugriff.py`): geheimer Pfad-Token + IP-Allowlist auf `CF-Connecting-IP`.
  `/health` bleibt offen (nur Status, keine Inhalte — trägt das Monitoring).
- **Read-only-Betrieb:** Der Server öffnet die SQLite-DB schreibgeschützt (`mode=ro`,
  `query_only=ON`); alle 16 Tools sind `readOnlyHint`.
- **Fail-fast:** Mit `FOLIANT_PRODUKTION=an` verweigert der Server den Start, wenn das
  Pfad-Token kürzer als 16 Zeichen ist.
- **Eingabegrenzen:** Suchanfragen sind längenbegrenzt, `limit` wird gedeckelt (DoS-Schutz).
- **Abfrage-Protokoll ohne PII:** Das Log (`data/foliant-protokoll.sqlite`) enthält nur
  Suchbegriffe, Filter und Zeiten — keine Nutzerkennungen, IPs oder Gesprächsinhalte. Es
  ist die einzige Schreib-Ausnahme des Serving-Pfads und liegt deshalb in einer eigenen
  Datei; die bediente Korpus-DB bleibt strikt `mode=ro`.
- **Laufzeit offline** (MCP), read-only auf legal erworbenen Daten; Admin-Funktionen **nie**
  über den Tunnel, nur lokal/SSH.
- **Discord-Bot:** keine eingehende HTTP-Fläche (nur ausgehend zu Discord/Anthropic);
  Zugangskontrolle ist die **Guild-Sperre** plus Nutzer-Cooldown und Tagesdeckel. Die
  Tools laufen in-process am `ZugriffsFilter` vorbei — bewusst, wie beim Eval-Harness:
  der Filter schützt den HTTP-Weg, nicht die Prozessgrenze (SPEC.md §12 Nr. 6). Der
  Spoiler-Schutz bleibt prompt-basiert; im gemeinsamen Kanal sieht jeder jede Antwort.
- **Inhalte-Recht:** Das Repository enthält **keine** kommerziellen Regelinhalte. Die aus
  gekauften Druck-PDFs abgeleiteten Reparatur-Module (`importer/frhof_reparatur.py`,
  `importer/reparatur_ddb_privat.py`, `tests/test_ddb_druck_privat.py`) sind bewusst nicht
  Teil des öffentlichen Codes (gitignored). Ohne sie bleibt der Server voll funktionsfähig —
  nur die kommerziellen Druck-Importe entfallen, die zugehörigen Tests überspringen sich
  selbst.
- **Schwachstellen melden:** nicht über öffentliche Issues, sondern über die private
  „Report a vulnerability"-Funktion (GitHub → *Security* → *Advisories*). Bitte betroffene
  Komponente, Reproduktionsschritte und mögliche Auswirkung angeben.

---

## 14. SYN-Befunde-Register

Am 12.07.2026 prüften vier unabhängige Reviews (Claude + Codex, je Technik und D&D-Regeln) den
damaligen Stand; eine Synthese konsolidierte die Funde zu den **SYN-IDs**. Diese IDs stehen
bis heute als Begründung in Code-Kommentaren und Testnamen — hier steht, wofür jede steht.
**P0, P1 und die lokalen P2-Befunde sind umgesetzt und getestet** (Commit `4043b27`); P3 sind
bewusste Ausbaustufen. Die Review-Volltexte liegen in der Git-Historie.

### P0 — blockierten die Rundennutzung (alle umgesetzt)
| ID | Befund |
|---|---|
| P0-001 | Fuzzy-Glossartreffer wurden als exakte Identität behandelt („Aktionen" → „Reaktionen"). Fix: `match=exakt\|fuzzy` getrennt. |
| P0-002 | Klammer-Suffixe + Editions-Fallback lieferten 2014 statt der vorhandenen 2024-Regel. Fix: Suffix-Aliasse, Edition vor Fallback. |
| P0-003 | Namensbasierte Deduplizierung verschluckte Varianten → unvollständige Steckbriefe. Fix: kontextbewusste Identität + `weitere_abschnitte`. |
| P0-004 | Beschädigte srd-de-Chunks (Zweihändig+Umstoßen, Zauber-Fragmente, Statblock-Zellrisse, ToC-Blob). Fix: kuratiertes Reparaturpaket. |
| P0-005 | Build-Prüfung erteilte falsche Legalitätsbestätigungen. Fix: Pflichtwahlen/Talent-Stufen prüfen. |
| P0-006 | Ungültige Parameter erzeugten ein falsches „nichts im Bestand". Fix: Whitelist-Validierung mit eigenem Fehlerpfad. |
| P0-007 | Playtest-/Abenteuer-Inhalte ohne Kennzeichnung. Fix: Playtest-Skip + `inhaltsart` bis in die Tool-Ausgaben. |

### P1 — vor externen Nutzertests (alle umgesetzt)
| ID | Befund |
|---|---|
| P1-001 | Keine semantische QS; DDB-Suite verdeckt rot. Fix: `make test` über beide venvs + Golden-Suite. |
| P1-002 | Kein stabiler Suche→Detail-Rundlauf. Fix: stabile `eintrag_id`. |
| P1-003 | Tool-Schemas ohne Enums/Bounds/Fehlersemantik. Fix: Enums, Grenzen, `readOnlyHint`. |
| P1-004 | Zugangskontrolle fail-open bei leerem Token; Token im Klartext in Logs. Fix: Fail-fast, `--no-access-log`, Redaktion. |
| P1-005 | Serving-Container sah `data/private` beschreibbar. Fix: read-only Serve ohne Privat-Mount. |
| P1-006 | Glossar-/Auffindbarkeitslücken bei 2024-Kernbegriffen. Fix: kuratierte Kernpaare + Ranking-Korrektur. |
| P1-007 | Aussagearten (Regeltext / Ableitung / SL-Entscheid) nicht getrennt. Fix: Disziplin in `config/stil.py`. |
| P1-008 | Open5e-Formatter verwarf Reaktionstrigger/Recharge/Form. Fix: Felder durchgereicht. |
| P1-009 | Quellkonflikte gleicher Edition wurden still per Priorität entschieden. Fix: sichtbarer Konfliktausweis. |
| P1-010 | srd-de-Textpolitur: Laufkopf in 374, Wortrisse in 273 Einträgen, 8 Namens-Garbles. |
| P1-011 | Kein Readiness-Check, kein Monitoring/Backup, keine Modell-Evals. Fix: `/ready`, Backup, Eval-Checkliste. |
| P1-012 | Offene Pins, fehlendes Korpus-Manifest, Doku-Drift. Fix: exakte Pins, `admin manifest`, Konsolidierung. |

### P2 — umgesetzt, soweit lokal wirksam
P2-001 Editions-/Statusmodell · P2-002 Wissensmodell-Ausbau (*bewusst nach dem MVP*) ·
P2-003 Regelwerte streng belegen · P2-004 Grenzen/DoS · P2-005 Charakterführung (Sprachen,
Pflichtwahlen) · P2-006 ein kanonisches Runbook · P2-007 Lizenzdisziplin bei privaten Quellen ·
P2-008 Agentenrechte eingedampft · P2-009 meta-Tabellen + CHECK-Constraints.

### P3 — bewusste Ausbaustufen (offen, nicht rundenblockierend)
P3-001 strukturelle Rollen-/Spoiler-Isolation · P3-002 Regelbeziehungsgraph ·
P3-003 Errata-/Revisionstracking · P3-004 Hausregeln-Overlay. Siehe
[BACKLOG.md](BACKLOG.md) §4.
