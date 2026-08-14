# Foliant — Konzept & Betrieb (das „Wie")

**Stand: 14.08.2026 · MVP live auf dem Raspberry Pi**

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
| `foliant` | MCP-Server (uvicorn), 6 Tools, **read-only** auf `data/foliant.sqlite` |
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

Schema: `db/schema.sql` (getestet, `user_version = 3`). Kernprinzip: **Datenshape über alle
Quellen vereinheitlichen, Provenienz (Quelle/Edition/Seite) sichtbar behalten.**

- **`quellen`** — Register aller Quellen: `edition` (2024/2014, **NOT NULL**), `sprache`,
  `herkunft` (pdf/ddb/srd-md/open5e/manuell), `lizenz`, `prioritaet` (Dubletten-Präzedenz;
  **kleiner = Vorrang**, Bänder s. u.), `inhaltsart`.
  **`inhaltsart` (vier Werte)** entscheidet, welchen Hinweis eine Antwort daraus trägt:
  `regelwerk` (keiner) · `abenteuer_setting` (🚫 Spoiler-Schutz) · `errata` (📌 offizielle
  Korrektur zum Grundtext) · `regelauslegung` (⚖️ Sage Advice, kein Regeltext).
  **Warum Errata eine eigene Quelle sind und nicht in den `body_md` eingerechnet werden
  (V9):** Ein eingerechneter Text wäre nicht mehr der Buchtext — die Provenienz ginge
  verloren, `body_md` und damit der korpusweite `inhalts_hash` verschöben sich bei jedem
  Errata-Update, und niemand könnte mehr sagen, was im Buch steht und was korrigiert wurde.
  Der Wertraum steht **allein in `importer/quellen.INHALTSARTEN`**, validiert in
  `registriere_quelle` — dem **einen** Schreibweg, also greift die Prüfung auf jeder
  Datenbank. Bewusst **kein CHECK im Schema**: eine geschlossene Wertliste, die noch wachsen
  kann, ist dort eine Migrationsfalle (§12). `admin check` meldet zusätzlich unbekannte
  Werte **im Bestand** sowie eine Datenbank mit veraltetem CHECK — beides kann ein CHECK
  nicht, er verhindert nur neue Werte und findet keine vorhandenen.
  **Provenienz (v3, 31.07.2026):** `importiert_am` (ISO-8601 UTC, setzt
  `registriere_quelle` selbst), `versions_stand` (Errata-/Druckstand als Freitext),
  `quell_url`, `quell_hash` (sha256 der Quelldatei beim Import). Alle vier optional —
  eine Quelle ohne sie bleibt gültig, sie kann nur weniger über sich sagen. Sie
  beantworten die Frage, die der korpusweite `inhalts_hash` **nicht** beantwortet:
  *welche Fassung dieses einen Buches steckt im Bestand?* `admin quellen-auffrischen`
  lässt `importiert_am` und `quell_hash` bewusst stehen (`setze_importzeit=False`) — dort
  wurde keine Datei gelesen, und ein fortgeschriebener Hash belegte nichts.
  **Beschriftungs-Standard:** `titel` trägt **nur den Werktitel** — kein „(Deutsch)",
  „(2014)", „(D&D Beyond)", „(Druck)". Sprache, Regelstand und Bezugsweg stehen in
  `sprache`, `edition` und `herkunft` und werden **daraus** angezeigt; sonst hängt jeder
  Importweg einen anderen Zusatz an denselben Werktitel und die Quellen sind nebeneinander
  nicht mehr vergleichbar. Durchgesetzt beim **Schreiben**
  (`importer/quellen.werktitel`, gerufen in `registriere_quelle`); Bestands-DBs zieht
  `db.stelle_schema_sicher()` einmalig nach (`normalisiere_titel`).
- **`eintraege`** — Inhalts-Chunks (Rückgrat): `kategorie`, `name_de`/`name_en`, `edition`
  (**NOT NULL** → kein verwaister Inhalt), `seite` (optional), `body_md`, `kontext`
  (Breadcrumb). FK-Cascade von `quellen`.
  `kontext` trägt den Breadcrumb (`Klassen > Kämpfer`) **zusätzlich** zur `*Kontext: …*`-Zeile
  im `body_md` — der Body bleibt unangetastet, sonst änderte sich der `inhalts_hash` und der
  gesamte Bestand bräuchte einen Re-Import. Bestands-DBs backfillt
  `db.stelle_schema_sicher()` einmalig aus dem Body; die Lesepfade kommen ohne die Spalte
  aus, weil der Serving-Pfad read-only ist und **nicht** migriert.
  **Ehrlich zur Wirkung:** Der Laufzeitgewinn ist klein (Faktor 1,7 auf einer Abfrage, die
  ohnehin auf `kategorie` + `edition` vorfiltert). Der Ertrag ist, dass der Breadcrumb ein
  *Feld* ist statt eines in ein LIKE-Muster interpolierten Strings.
- **`zauber_meta`/`monster_meta`/`gegenstand_meta`** — strukturierte Facetten, erscheinen
  additiv als `facetten` in den Detail-Tools (der `body_md` bleibt unangetastet).
  `zauber_meta`: `grad`, `schule`, `klassen`, `reichweite_m`, `komponenten`, `dauer_min`,
  `konzentration`, `ritual` · `monster_meta`: `hg`, `typ`, `rk`, `tp` ·
  `gegenstand_meta`: `seltenheit` (noch ungeschrieben), `preis_cent`.
  **Einziger Schreiber: `importer/facetten_seeder.py`** — er leitet aus `body_md` ab, mit
  genau den Parsern, die der Serving-Pfad ohnehin ruft (`app/facetten.py`,
  `srd_zauberbruecken.kopf_felder`, `srd_begriffsbruecken.preis_cent_von`). Ein zweiter
  Schreiber aus nativen API-Feldern erzeugte einen zweiten Wertraum (`schule = "Evocation"`
  statt kanonisch `"hervorrufung"`) und damit Facetten, die kein Filter fand.
  Gespeichert wird immer der **kanonische Schlüssel**; die deutsche Anzeigeform macht erst
  die Ausgabe (`_facetten_von`). Was der Text nicht hergibt, bleibt `NULL` — nie geraten.

  **Nachgeschaltet: `importer/fassungsabgleich.py`** (01.08.2026). Steckt durch einen
  Chunking-Unfall ein zweiter Statblock im Eintrag, gibt der Text **mehrere** Werte her und
  der Parser nimmt den ersten — der deutsche Ghul stand so mit HG 8 (Geisternaga) statt 1 da,
  eine HG-1-Suche fand ihn nicht. Der Abgleich lässt in diesem Fall die **anderen Fassungen
  derselben Kreatur** entscheiden, welcher der im Text stehenden Werte der eigene ist
  (Namensbrücke über das Glossar, gleiche Edition, Einstimmigkeit). Er bringt **nie** einen
  Wert ein, der nicht im eigenen Text steht; ohne eindeutige Zeugen bleibt die Facette `NULL`.
  Der bloße **Widerspruch** (ein Wert im Text, andere Fassung sagt etwas anderes) wird
  ausdrücklich **nicht** korrigiert, sondern nur gemeldet: Ein erster Entwurf hätte
  `Summon Celestial` im PHB von Grad 5 auf 7 gezogen, Zeuge war der deutsche SRD-Eintrag
  „Celestisches Wesen beschwören" über eine Glossarzeile aus einem 2014er Band. Dahinter kann
  ein Schaden, eine Editionsdifferenz oder eine falsche Begriffszuordnung stecken — das
  entscheidet ein Mensch, nicht die Heuristik. `admin import --quelle facetten` gibt beide
  Listen aus: die Korrekturen einzeln und die gemeldeten Widersprüche daneben.
- **`glossar`** — DE↔EN: `term_de` (kanonisch), `offiziell` (1 → kein `*`, 0 → `*`), `quelle`,
  `edition_quelle`. Grundlage für Begriffswahl und `*`-Kennzeichnung (S6/S9).
- **`eintraege_fts`** — FTS5 (external-content) über `name_de, name_en, body_md`, Tokenizer
  `unicode61 remove_diacritics 2`, plus **drei Trigger** (INSERT/UPDATE/DELETE).

**Getestet:** Trigger feuern, bm25 rankt, `edition NOT NULL` greift, Cascade-Delete lässt die
FTS sauber. Alt-DBs heilt `app.db.connect()` beiläufig auf den aktuellen Stand (v3, inkl. der
Provenienz-Spalten) — jeder Import-/Admin-Aufruf genügt.

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

**Quellbezug: fehlt die Datei, holt der Import sie** (`importer/quellbezug.py`). Führt ein
`[[quelle]]`-Block eine `quell_url` und liegt unter `dateipfad` nichts, lädt der Import die
Datei dorthin — der Weg für frei verteilte PDFs (die drei Errata-Bände). Netz ist hier nichts
Neues: `glossar` und `open5e` rufen an derselben Stelle APIs, die Laufzeit bleibt offline (Q7).

Der Bezug braucht ein **beschreibbares** `quellen/`. Am Mac ist es das; im Pi-Container
bewusst nicht (`:ro`) — dort ist der Weg zweistufig (§8, „Errata importieren").

**Die tragende Regel: eine VORHANDENE Datei wird nie angefasst.** Nicht überschrieben, nicht
verglichen, nicht „aktualisiert". Unter `quellen/` liegen kuratierte und reparierte PDFs — ein
Bezug, der die Originaldatei ersetzt, macht stundenlange Handarbeit lautlos zunichte, und zwar
genau dann, wenn jemand routiniert einen Re-Import fährt. Wer eine neue Auflage will, löscht
die Datei bewusst. Dazu drei Prüfungen, bevor eine Antwort als Quelldatei gilt: **https**,
ein Größen-Deckel und die **magischen Bytes** — nicht der Content-Type, denn ein Portal, das
eine Anmelde- oder Cloudflare-Seite mit HTTP 200 ausliefert, ist der Normalfall, und ein
HTML-Dokument namens `PHB-2024_v1.pdf` fiele sonst erst im PDF-Parser auf. Führt die Config
einen `quell_hash`, ist er ein **Pin** (V10): passt er nicht, liegt an derselben URL ein
anderer Inhalt — dann bricht der Import ab, statt `versions_stand` zu einer falschen Aussage
über den Bestand zu machen.

| Quelle | Weg |
|---|---|
| **Born-digital-PDF** (dt. SRD) | `[[quelle]]`-Block in `config/foliant.toml` → `admin import --quelle <kuerzel>` |
| **Frei verteilte PDFs** (Errata) | dasselbe, plus `quell_url` (+ `quell_hash` als Pin) — die Datei holt der Import |
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
- **Abkürzungen (S12, 31.07.2026):** Das Register `config/abkuerzungen.py` ist die eine
  Definition — der Glossar-Seeder, die Verhaltensregel und der Charakterbogen-Übersetzer
  lesen dieselbe Liste. Zwei Richtungen mit verschiedenen Zusagen: **Ausgabe** deutsch
  (RK, TP, SG, HG, EP, ÜB, W20, STÄ/GES/KON/INT/WEI/CHA), **Eingabe** versteht auch
  englisch (AC, DC, CR, d20, STR → derselbe Eintrag). Jede empfohlene Form ist im
  deutschen SRD 5.2.1 ausgezählt belegt (`tests/test_abkuerzungen.py` prüft das gegen den
  echten Bestand). Vorher lag das Wissen an drei Stellen, die nichts voneinander wussten —
  und ausgerechnet der MCP-Server hatte **keine** Regel, deutsch abzukürzen: im Glossar
  standen `XP`, `CR`, `PB`, während das deutsche Buch 388-mal `EP`, 356-mal `HG` und
  341-mal `ÜB` schreibt.
  **Durchsetzung über alle drei Kanäle** — bewusst, weil die Projektanweisung jede Person
  selbst einrichten muss und genau das nicht jede tut: `hinweis_abkuerzungen` hängt an
  jeder Such- und Detailantwort, die Tool-Beschreibungen tragen die Kurzform (der Server
  liefert sie mit dem Schema aus, ohne Zutun des Clients), und die Instruktion nennt sie
  ebenfalls. Der Hinweis wird **aus dem Register gebaut**, nicht abgeschrieben — sonst
  liefe er der Liste beim ersten Zuwachs davon.
  Dazu die Auflösung im Text: `begriffe_im_text` nimmt Abkürzungen von der
  `_MIN_LEMMA`-Schwelle aus (sie sind keine Alltagswörter) und matcht sie **schreibungs­-
  genau**. Das ist die Sicherung, nicht ein Detail: `PP` ist die Platinmünze, `pp.` die
  Seitenangabe in jedem Errata-Kopf. An einem echten Aboleth-Statblock löst das AC, HP,
  CR, DC, XP und die sechs Attributskürzel auf.
- **Dubletten/Präzedenz** über `quellen.prioritaet` (dt. Quellen < DDB < Open5e; die
  Bänder stehen in `importer/quellen.py`, s. u.). Echte **Quellkonflikte gleicher
  Edition** werden nicht still entschieden, sondern ausgewiesen (SYN-P1-009).
- **Fundstelle der unterlegenen Fassung bleibt erhalten** (31.07.2026): `weitere_quellen`
  nennt sie als `"Player's Handbook, S. 241"`, `weitere_fassungen`/`weitere_fundstellen`
  führen `seite` und `quelle` als eigene Felder. Vorher lag die Seite in der DB und fiel
  aus der Antwort — eine Auskunft konnte nicht sagen, wo man die Regel *aufschlägt*,
  obwohl genau das ein gedrucktes Buch wertvoll macht. Regel 1 hält dabei von selbst: die
  Seite stammt aus der Zeile genau dieses Eintrags in genau dieser Quelle; führt die
  Quelle keine (Open5e), steht nur der Titel da.
- **Revisionsquellen nehmen am Dedupe NICHT teil.** Treffer aus `errata`- und
  `regelauslegung`-Quellen werden vor der Gruppenbildung ausgesondert und als eigene
  Treffer angehängt. Grund: Ein Erratum zu „Fireball" *heißt* „Fireball" und trägt
  dieselbe Edition und Kategorie — es liefe damit in die Gruppe des Grundtexts und
  verschwände dort in `weitere_fassungen`, also aus der Trefferliste. Ein Namenszusatz
  hülfe nicht (die Klammer-Suffix-Logik zieht ihn ab, und die Glossar-Brücke führt
  trotzdem in die Gruppe). Bei einem **exakten Namenstreffer** hält ihr Prioritätsband
  (70, hinter jedem Regelwerk) sie zuverlässig hinter dem Grundtext; bei unscharfen
  Volltext-Treffern entscheidet dagegen zuerst die Relevanz (A6), dort kann ein Erratum
  also vorn stehen. Das ist gewollt und unschädlich — der Treffer trägt seine
  Kennzeichnung mit, und die verlangt ausdrücklich, Grundtext und Korrektur zusammen
  wiederzugeben.

---

## 6. MCP-Tools

Namensschema `foliant_<verb>_<nomen>` (kollisionsfrei neben anderen Connectoren). Die Suche
liefert **knappe** Treffer, der Detailabruf die volle Ausgabe — das hält die Kontextlast
niedrig. **Sechs Werkzeuge, sechs verschiedene Handlungen:**

| Werkzeug | Wofür |
|---|---|
| `foliant_suche_bestand` | Freitext ODER Struktur-Filter über den ganzen Bestand, knappe Treffer |
| `foliant_hol_eintrag` | ein Eintrag vollständig; `kategorie` ist **Pflicht** (die acht aus dem Datenmodell) |
| `foliant_liste_optionen` | wählbare Optionen einer Kategorie (Klasse/Hintergrund/Spezies/Talent) |
| `foliant_uebersetze_begriff` | Glossar DE↔EN, auch Abkürzungen |
| `foliant_hol_attributswerte` | Attributsvergabe 2024, am Bestand belegt |
| `foliant_pruefe_build` | Build gegen den 2024-Bestand prüfen |

**Warum `kategorie` Pflicht ist und nicht optional:** Sie ist der Disambiguator — ohne sie
liefert der Detailpfad bei „Schild" still den Gegenstand statt des Zaubers. Vorher trugen
acht `foliant_hol_<typ>`-Werkzeuge dieselbe Unterscheidung im *Namen*; als Parameter kostet
sie ein Feld statt eines halben Schemas (rund 1 170 Token weniger je Verbindung).

- **Status:** `/health` (offen), `/ready` (prüft DB + FTS, 503 bei kaputtem Bestand)

**Wo der Code liegt:**

| Datei | Inhalt |
|---|---|
| `ausgabe.py` | WIE ein Treffer beim Modell ankommt: knappe/volle Form, Deutsch-first-Anzeigename, Zitat, Spoiler-Kennzeichnung — und die **Grounding-Hinweise** (Kanal 3) |
| `suche.py` | `foliant_suche_bestand` samt Facetten-Validierung und SQL-Vorfilter |
| `nachschlagen.py` | Detailabruf (`foliant_hol_eintrag`) und das Glossar-Werkzeug |
| `charakter.py` | Optionslisten, Attributsregeln, Build-Prüfung |

Die Richtung ist eine Regel, kein Zufall: **`ausgabe.py` kennt die Werkzeuge nicht** —
sonst greift der eine Werkzeug-Pfad in die Interna des anderen, statt dass beide dieselbe
Schicht importieren.
Die **Namensrelevanz** (`_name_score`, `_eintrag_namen`) liegt in
[`app/glossar.py`](app/glossar.py) — dort, wo auch ihre Schwelle `FUZZY_NAME` und die
Normalisierung wohnen; sie war die einzige Stelle, an der sich Such- und Detailpfad
berührten. `Kategorie` liegt neben `KATEGORIEN` in [`app/db.py`](app/db.py).

Alle Tools sind als `readOnlyHint` deklariert, haben `Literal`-Enums und Bounds und liefern
diskriminierte Ergebnisformen (`gefunden|mehrdeutig|fehler|verfuegbar`). Suchtreffer
tragen eine stabile `eintrag_id`, über die der Detailabruf denselben Eintrag exakt nachlädt.

**Arbeitsteilung:** Der Server liefert Daten, Suche und Validierung; **Claude führt das
Gespräch.** Die Verhaltensregeln laufen über drei Kanäle — der zuverlässigste sind die
**Grounding-Hinweise in den Tool-Ausgaben** (siehe [SPEC.md](SPEC.md) §7).

**Wo die Prompt-Texte liegen.** Die drei Kanäle speisen sich aus zwei Dateien, die synchron
bleiben müssen (`tests/test_verhaltensregeln.py` erzwingt das für die tragenden Regeln):
`config/stil.py` (Server-Instruktion + Tool-Beschreibungen) und `config/projektanweisung.md`
(Copy-Paste ins Claude-Projekt). Dazu kommt **`config/discord_zusatz.md`** — **kein vierter
Kanal**, sondern eine Darstellungs-Ergänzung: Sie hängt an der Projektanweisung und regelt
nur, was Discord anders kann als der Chat (~1800 Zeichen je Absatz, keine Markdown-Tabellen
und keine `#`-Überschriften, Statblöcke daher als Codeblock oder fette Feldzeilen). Eine
*Verhaltens*regel gehört dort nie hinein, sonst kennt der MCP-Weg sie nicht — genau das prüft
`test_discord_zusatz_ist_nur_darstellung`.

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
| `glossar_export.py` | Erzeugt die Web-DB für den Web-Container: Glossar **und** Quellen-Metadaten (Titel, Sprache, Regelversion, Eintragszahl) — kein Buchtext, keine Dateipfade. Läuft nach jedem `admin import` automatisch; bleibt bewusst ohne `app.db`-Abhängigkeit, damit es mit dem System-Python des Wirts läuft, bevor `web` startet (§12). |
| `web.py` | Starlette-App: `GET /`, `POST /bogen`, `GET /health`. Kennwort-Seite, Ein-Konvertierung-Semaphore, keine Persistenz, `no-store`/CSP. |

### Die tragenden Entwurfsregeln

**Zwei LLM-Stufen statt einer.** (1) Belegte Begriffe kommen deterministisch aus dem Glossar.
(2) Stufe 1 übersetzt unbelegte Eigennamen („Warrior of Shadow") in einem kurzen eigenen
Aufruf → S4/S5-Form mit `*` **und** als bindende Vorgabe für Stufe 2. (3) Stufe 2 übersetzt die
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
- **Nie stumm überlaufen:** Auto-Fit → S4-Klammer opfern → horizontal stauchen.
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
python -m app.admin import --quelle errata-phb-2024-en  # offizielle Korrekturen, PDF wird geholt
python -m app.admin import --quelle errata-dmg-2024-en
python -m app.admin import --quelle errata-mm-2025-en
python -m app.admin import --quelle glossar             # inkl. Kern-Singulare
```
Reihenfolge: **Bestand → Facetten → Glossar.** Die Facetten laufen automatisch am Ende jedes
Quellen-Imports mit — auch beim DDB-Import (Voll-Lauf, idempotent, ~0,1 s je 3000 Einträge).
*Bis zum 31.07.2026 stimmte dieser Satz nur für `admin import`; der DDB-Weg rief den Seeder
nie, seine Bücher lagen also ohne Facetten im Bestand.* Für eine bestehende DB
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
  **Zwei Signalarten, und die erste ist die stärkere.** Ganz oben stehen die von der Runde
  **markierten Antworten** (👎 in Discord → Tabelle `rueckmeldungen`, §9): ein Urteil, kein
  Messwert — genau die Fehlerklasse, die *gefunden* hat und trotzdem falsch war und deshalb
  in keiner Statistik auftaucht. Danach die gemessenen:
  Nulltreffer/Fuzzy-Landungen/Mehrdeutigkeiten/Übersetzungs-Lücken sind die
  Kuratier-Kandidaten für Glossar-Paare und Chunking-Korrekturen; der Kopf liefert die
  B9-Antwortzeiten (p50/p95). Die Log-DB liegt bewusst außerhalb von Backup-Glob und
  Manifest.
- **Zum bloßen Nachschauen** („was liegt gerade an?") genügt `admin suchbericht` ohne
  `--json`: Die markierten und die gelobten Antworten stehen als **erste zwei Abschnitte**,
  mit Datum, Frage und anklickbarem Link. Eine Auswertung braucht es dafür nicht.
  Der `datasette`-Container wäre der komfortablere Weg und ist auf beide DBs eingestellt —
  **auf dem Pi läuft er aber nicht** (04.08.2026 geprüft): Das offizielle Image ist
  amd64-only und stirbt auf ARM64 mit `exec format error`, und der im compose-Kommentar
  genannte Ausweg („im foliant-Container nachinstallieren") scheitert an dessen
  `read_only`-Härtung. Beides bleibt so — die Härtung ist mehr wert als der Komfort.
- **Der Durchgang läuft zeitgesteuert, nicht auf Zuruf** (04.08.2026). Zweimal pro Woche
  fährt eine geplante Aufgabe auf Davids Mac den Ablauf aus
  `.claude/ablaeufe/rueckmeldungen.md`: Bericht holen (`make bericht-pi`), Gesprächskontext
  je Markierung nachladen (`make kontext-pi`), gegen die Regel-IDs prüfen, **Freigabekarten**
  vorlegen. **Ohne neue Rückmeldung endet sie ohne Ausgabe** — eine Aufgabe, die
  regelmäßig Erfolg meldet, wird weggeklickt, und mit ihr die Meldung, die zählt.
  Sichtungsstand: `config/rueckmeldungen_stand.json` (Hochwassermarke, Entscheidung je
  Befund; bewusst versioniert statt in der Protokoll-DB, damit der Fortschritt im Diff
  steht und die Produktion keinen Schreibbefehl braucht). Umgesetzt wird **nichts** ohne
  Davids Freigabe, mit einer benannten Ausnahme (11.08.2026): ein 👍 auf eine
  Bestandsaussage darf ohne Rückfrage einen Golden-Test bekommen — die einzige Klasse, die
  kein Verhalten ändert. Format, Schranken und Ablage: `.claude/ablaeufe/rueckmeldungen.md`,
  bewacht von `tests/test_rueckmeldungs_ablauf.py`; die übrigen Zeitläufe:
  `.claude/ablaeufe/LIESMICH.md`.

### Admin-CLI (vollständig)
```
status        Bestand je Quelle/Edition/Kategorie + Glossar
manifest      Korpus-Fingerabdruck (inhalts_hash) - nach jedem Import festhalten
quellen-register  Quellen-Register als TOML aus der DB - Wiederherstellungs-Artefakt (ohne Buchtitel); erneuern mit `make register-vom-pi`
import        --quelle <kuerzel> | glossar | facetten (Facetten ohne Re-Import nachziehen)
quellen-auffrischen  Quellen-METADATEN (Titel, Prioritaet, Lizenz, inhaltsart, versions_stand, quell_url) aus der config nachziehen - ohne Re-Import, Eintraege bleiben unberuehrt
pdf-triage    welche PDFs haben keine Textschicht?
ocr-pdf       --datei <pfad> [--redo] [--voll]
reindex-fts   FTS neu aufbauen
check         Integritaet, FK, FTS-Suchbarkeit, Editionen, Textqualitaet, Facetten-Deckung, Prioritaets-Baender, Qualitaets-Basiswerte
qualitaet-basis  Basiswert bekannter Datenmaengel neu erheben [--schreiben] - nur am Vollbestand sinnvoll
glossar-audit Glossar-Stand und -Herkunft pruefen
glossar-paare Kandidaten fuer neue Glossar-Paare zeigen [--nur-neue] [--json]
suchbericht   Kuratier-Signale: MARKIERTE Antworten, Nulltreffer, Fuzzy, Mehrdeutigkeiten
backup        konsistentes, verifiziertes Online-Backup mit Rotation
ddb-pruefe | ddb-import | ddb-import-all | ddb-remove
```

**Bewusst kein öffentliches Admin-Panel** — das wäre auf dem getunnelten Pi unnötige
Angriffsfläche. Der grafische Blick läuft über Datasette an `127.0.0.1` per SSH-Tunnel:
```
docker compose --profile admin up -d datasette
ssh -L 8001:localhost:8001 <nutzer>@<pi-ip>     # dann http://localhost:8001
```

### Errata importieren (offizielle Korrekturen)

Die drei Errata-PDFs (PHB 2024, DMG 2024, MM 2025) bietet WotC frei zum Herunterladen an;
die drei `[[quelle]]`-Blöcke liegen **einsatzbereit in
[`config/foliant.example.toml`](config/foliant.example.toml)** (`errata-*`, `inhaltsart =
"errata"`, Band 70, `quell_url` + gepinnter `quell_hash`) — dort und nicht in
`config/foliant.toml`, weil die echte Config gitignored **und** vom Deploy-Rsync
ausgeschlossen ist: jedes Gerät führt seine eigene. Die Blöcke enthalten nichts Privates
(freie WotC-URLs plus Prüfsummen), also einmal in die eigene `foliant.toml` übernehmen.
Danach **ein Befehl je Band, die PDF holt der Import selbst** (§4 „Quellbezug"):

```
.venv/bin/python -m app.admin import --quelle errata-phb-2024-en
.venv/bin/python -m app.admin import --quelle errata-dmg-2024-en
.venv/bin/python -m app.admin import --quelle errata-mm-2025-en
```

**Auf dem Pi geht der Bezug NICHT im Container** (Befund beim ersten echten Pi-Import,
03.08.2026). `quellen/` ist dort absichtlich `:ro` gemountet (`docker-compose.yml`), damit
die getunnelte Laufzeit keine Quelldateien schreiben kann — und ein `docker compose run -v`
hebt das **nicht** auf: Compose behält den `:ro`-Mount der Service-Definition. Diese
Härtung bleibt. Der Weg auf dem Pi ist deshalb zweistufig, wie beim DDB-Import: **Datei auf
dem Host holen, Import im Container.**

```sh
# auf dem Pi, im Host-Verzeichnis ~/foliant/quellen/errata/
curl -fsSL -o PHB-2024_v1.pdf <quell_url aus der config>
sha256sum PHB-2024_v1.pdf          # MUSS dem quell_hash der config entsprechen
docker compose exec -T foliant python -m app.admin import --quelle errata-phb-2024-en
```

Der Hash-Vergleich ist hier **Handarbeit und deshalb Pflicht**: Er ist die einzige Prüfung,
die auf diesem Weg entfällt — `hole_wenn_fehlt` fasst eine vorhandene Datei nicht an und
prüft dann auch ihren Hash nicht (§4, tragende Regel). Wer ihn überspringt, importiert im
Zweifel eine neue Auflage unter `versions_stand = "Errata Version 1.0"`.

*Offen als Verbesserung:* ein eigener Import-Profil-Service mit `quellen` read-write, wie es
`ddb-exporter` für sein Secret schon macht — dann gilt der Ein-Befehl-Weg auch auf dem Pi
([BACKLOG.md](BACKLOG.md) §4).

Errata-PDFs haben keine Heading-Struktur, die der Konverter erkennen könnte — jede
Korrektur ist ein Absatz mit fettem Kopf (`**_Polymorph (p. 306)._**`).
`_errata_headings` in `importer/import_markdown.py` macht daraus `### Polymorph`; ohne
diesen Schritt entstünde **ein Riesen-Chunk je Rubrik**, in dem die Suche nichts findet
(derselbe Fehler wie bei den 2014-Scans, 27.07.2026).

**Am echten Dokument justiert (03.08.2026).** Bis dahin war das Muster nur aus dem
veröffentlichten Aufbau abgeleitet, und der erste echte Import zeigte, warum das nicht
reicht — mit zwei Befunden, von denen der zweite der schlimmere war:

1. **Vier der 17 PHB-Korrekturen beginnen mitten in der Zeile,** direkt hinter dem
   Satzende der vorigen (`… to move”. **_Poisoner (p. 206)._** In the Brew Poison …`).
   Der Kopf-Regex verlangte den Zeilenanfang — Poisoner, Conjure Fey, Polymorph und
   Shapechange fehlten stumm im Bestand. `_ERRATA_KOPF_MITTEN` setzt sie jetzt zuerst auf
   eigene Zeilen.
2. **Die Bilanz zählte falsch — blind und laut zugleich.** Kandidat war „fetter Lauf am
   Zeilenanfang": die vier verpassten Köpfe waren damit *nie* Kandidaten, dafür galt der
   Dokumenttitel (`**Player’s Handbook (2024)**`) als verpasster Kopf. Gemeldet wurde
   „1 von 14" — ein Fehlalarm, während der echte Ausfall unerwähnt blieb. **Das ist die
   Lehre für jede Zählung dieser Art:** Sie muss messen, was gesucht wird (Köpfe *mit
   Seitenangabe*, wo immer sie stehen), nicht, was leicht zu zählen ist.

Endstand: **43 Korrekturen** aus drei PDFs (PHB 17, MM 24, DMG 2 — der DMG-Band ist
wirklich so klein), Bilanz still. Greift das Muster bei einer künftigen Fassung nicht,
meldet die Bilanz `WIRKUNGSLOS` — dann das Muster nachziehen, statt den Riesen-Chunk zu
importieren.

Zwei Dinge, die dabei bewusst so sind: Der **Eintragsname ist die betroffene Regel**
(„Fireball") — nur so findet das Erratum, wer nach der Regel sucht; die Kollision mit dem
Grundtext löst die Dedupe-Ausnahme (§5). Und `eintraege.seite` trägt die Seite **im
Errata-PDF**, nicht die Buchseite: Letztere steht im Body („Offizielle Korrektur zu
S. 275 im Grundbuch"), denn das Erratum *steht* nicht auf S. 275, es sagt nur etwas
darüber.

### Glossar-Lücken kuratieren (M5)

`admin suchbericht` weist Begriffe aus, für die `foliant_uebersetze_begriff` **keinen
exakten Eintrag** fand — der Abschnitt „Uebersetzungs-Luecken". Das sind genau die
Stellen, an denen ein Modell sonst selbst eine `*`-Wiedergabe bildet, und zwar je Gespräch
eine andere (real belegt: „Heldenhafte Inspiration" direkt neben dem Vordruck „Heldische
Inspiration"). Gefüllt wird **messwertgetrieben** — was gefragt wurde, nicht was denkbar
ist.

**Verbindlich dabei:** Eine Community-Übersetzung (Foundry-Sprachpakete, Forenfassungen,
maschinelle Vorschläge) darf als Nachschlagehilfe dienen, wird aber **nie `offiziell = 1`**
— sie kommt mit `offiziell = 0` und einer Herkunftsmarke in `glossar.quelle` herein und
trägt in der Ausgabe ihren `*`. Offiziell ist nur, was in einer offiziellen Quelle belegt
ist (S3-Leiter). Bulk-Importe ganzer Community-Sprachpakete sind bewusst **nicht** der
Weg: sie fluten Fuzzy-Suche und Konflikt-Gate mit ungeprüften Zeilen und erzeugen laufende
Pflege für Begriffe, nach denen nie jemand fragt.

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
Das ist der **eine** Weg: `make test` → Eval-Reports retten → laufende Images als
`:vorher` taggen → rsync → `docker compose up -d --build --no-deps foliant web discord` →
Golden-Suite am Vollbestand → **`admin check --vollbestand`** (`make check-pi`). Die
Schritte hängen zusammen, weil das Weglassen jedes einzelnen schon schiefgegangen ist
(Rebuild vergessen → alter Code meldet „Erfolg"; Golden vergessen → korpusabhängige
Regression bleibt unentdeckt).

**Warum die Gates trotzdem hinten stehen — und was daraus folgt:** Die Golden-Suite
braucht den Vollbestand, und der liegt nur auf dem Pi; sie kann also nicht vor dem
Live-Schalten laufen. Genau deshalb gibt es seit dem 14.08.2026 zwei Ergänzungen: `test`
als *Vorbedingung* (was schon der Mac durchfallen lässt, hat auf dem Pi nichts verloren)
und `make rollback-pi` als Rückweg — die vorherigen Images liegen als `:vorher` bereit,
werden zurückgetauscht und durchlaufen dieselben Gates. Vorher gab es auf dem Pi
ausschließlich `:latest`, der alte Stand war nach dem Build überschrieben.

**Wartung:** `make pflege-pi` zeigt die Belegung; erst `make pflege-pi LOESCHEN=ja` gibt
Build-Cache älter als sieben Tage frei. Bewusst nicht Teil des Deploys — ein Löschschritt,
der ungefragt mitläuft, erwischt irgendwann das Falsche.

**Alle drei Code-Dienste, nicht nur `foliant`:** `web` und `discord` backen dasselbe Image
aus demselben Repo — wird nur `foliant` gebaut, laufen Bot und Website nach einem Deploy
still mit dem alten Stand weiter. `--no-deps` verhindert dabei, dass `depends_on` den Tunnel
mit durchstartet (§12).

**Warum der Check dazugehört:** `make test` fährt ihn lokal, aber die Dev-DB ist ein
**Subset** (7 von 18 Quellen) — alles, was erst am Vollbestand sichtbar wird, fällt dort
nicht auf. `admin check` endet bei Problemen mit Exitcode ≠ 0 und bricht damit den Deploy
ab: Ein Import, der **neue** Datenmängel einschleppt, geht nicht mehr still live (was
bekannt ist, steht in `config/qualitaet_basis.json`).

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

**Der Weg ist ein Skript, der Bot-Token die einzige Eingabe:**

```sh
bash deploy/discord_einrichten.sh          # laeuft LOKAL am Mac, Pi-Ziel aus .env
```

Es fragt Application ID und Server-ID selbst bei Discord ab
(`deploy/discord_api.py` → `/users/@me` und `/users/@me/guilds`), baut den Einladungslink
mit **genau** den fünf Rechten, die `app/discord_bot/bot.py` braucht, schreibt
`DISCORD_BOT_TOKEN` und `DISCORD_GUILD_ID` in die Pi-`.env` und startet den Dienst.
Kein Abtippen von IDs, kein Entwicklermodus. Der Token wird verdeckt gelesen, **nie** als
Argument übergeben (in `ps` sichtbar) und auf dem Pi nach dem Setzen geschreddert — dasselbe
Muster wie beim DDB-Cobalt.

Zwei Dinge bleiben Handarbeit, weil Discord sie nicht über die API zulässt:
1. Application + Bot im **Entwicklerportal** anlegen (discord.com/developers) und den Token
   erzeugen (*Bot → Reset Token*).
2. **Message Content Intent aktivieren** (Privileged Intent; Review-Pflicht erst ab
   100 Servern — irrelevant bei einer Guild). Ohne das reagiert der Bot nicht auf @Mentions.

Optional das Profilbild: `deploy/discord_avatar.svg` nach PNG rendern und unter *Bot → Avatar*
hochladen (Discord nimmt kein SVG) —
`qlmanage -t -s 512 -o /tmp deploy/discord_avatar.svg` legt `/tmp/discord_avatar.svg.png` ab.

**Von Hand** geht es weiter mit Scopes `bot` + `applications.commands`, den Rechten *Send
Messages*, *Create Public Threads*, *Send Messages in Threads*, *Read Message History*,
`DISCORD_BOT_TOKEN` + `DISCORD_GUILD_ID` in die Pi-`.env` und
`docker compose up -d --build --no-deps discord`.

**Weitere `.env`-Schalter** (alle optional): `DISCORD_KANAL_IDS`, `DISCORD_TAGESDECKEL`
(Default 100/Tag), `DISCORD_COOLDOWN_S` (Default 10 s zwischen zwei Fragen desselben
Nutzers). `DISCORD_GUILD_ID` ist Pflicht — ohne sie startet der Bot nicht.

**Nutzung und Betrieb:**
- Logs: `docker compose logs -f discord`.
- Befehle: `/regel <frage>`, `/regel-privat <frage>` (ephemer, ohne Thread), `/hilfe`
  (statisch, ohne API-Kosten), `/bestand` (Bücherliste, ephemer, ohne API-Kosten),
  Kontextmenü „Foliant fragen", @Mention. Beide `/regel`-Formen
  tragen eine optionale `fassung`-Wahl (2024/2014). Was die Befehle können und **warum sie so
  geschnitten sind**, steht im Entscheidungsregister (§10).
- **Rückmeldung der Runde:** Eine **👎-Reaktion** auf eine Bot-Antwort macht sie zum
  Kurations-Kandidaten, eine **👍-Reaktion** zum Kandidaten für Regressionsschutz; der Bot
  bestätigt beides mit 📝, das Zurücknehmen löscht den Eintrag. Warum es diesen Meldeweg
  gibt und warum er im Bericht vor jeder Statistik steht: §8.
  Logik discord-frei in `app/discord_bot/rueckmeldung.py`, Ablage in
  `protokoll.rueckmeldungen` (was dort steht und was nicht: §13). Getrennte Abfragen mit
  eigenem Limit je Art: 👍 kommt reflexhaft und damit häufiger, und ein gemeinsames Limit
  ließe einen Schwall Lob die Fehlermeldungen verdrängen.
  Das Recht *Add Reactions* trägt nur die Bestätigung: fehlt es, wird die Markierung
  dennoch notiert. `deploy/discord_einrichten.sh` fordert es an; wer den Bot vorher
  eingeladen hat, ruft den Einladungslink erneut auf.
- **Kontrolle:** Discord-Anfragen erscheinen im Abfrage-Protokoll (`admin suchbericht`) —
  derselbe Kurations-Kreislauf wie beim MCP.
- **Für die Runde erklärt** ist der Bot auf der Website (Karte „Foliant in Discord",
  `app/charakterbogen/templates/index.html`): Befehle, Threads, `/regel-privat`, Schranken
  und der Hinweis, dass Discord Antworten dauerhaft im Kanal stehen lässt. Ändern sich
  Befehle oder Schranken, gehört die Karte mitgezogen — sie ist das, was die Spieler lesen.

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
- **Die Buchliste („Was steckt drin?") kommt aus der Web-DB**, nicht aus dem Template. Nach
  einer Änderung an den Quellen-Metadaten — etwa dem Beschriftungs-Standard (§3) — genügt
  ein Lauf, der die DB read-write öffnet und die Web-DB neu schreibt:
  ```sh
  docker compose exec foliant python -m app.admin import --quelle facetten
  ```
  Der Weg ist bewusst dieser: er fasst den Bestand nicht an (kein Re-Import, keine
  zerstörte Namensreparatur), zieht aber `stelle_schema_sicher()` und am Ende die Web-DB
  nach. Ohne ihn zeigt die Seite die alten Titel weiter.

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
Merge in die bediente DB (**so läuft der Pi**, siehe [SPEC.md](SPEC.md) §12 Nr. 1). Ohne die Zeile
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
| **Quellen-Macken beim Code, der sie behandelt** | Die Eigenheiten einer Quelle stehen im Modul-Docstring ihres Importers, die Reparatur daneben — damit dieselbe Falle nicht zweimal gelöst wird. Ein *zentrales* Macken-Modul gab es; es wurde von keinem Codepfad gelesen und beschrieb ein zweites Mal, was längst am Lösungsort stand `app/bekannte_macken.py`, 123 Zeilen, seit dem Initial-Commit mit `TODO: fuellen` — entfernt am 29.07.2026 |
| **Build-Prüfung minimal** | wenige klare Checks statt einer vollständigen Regel-Engine |
| **DELETE-Journal** | Kompatibilität mit Bind-Mount-Volumes |
| **Alles auf dem Pi** | Ein-Geräte-Wunsch; PyMuPDF4LLM ist ARM-tauglich |
| **Docker** | Mehrprojekt-Isolation + ARM64-Portabilität (Pi → Mac mini) |
| **Kein Runtime-Cache** | lokales FTS5 ist schneller als jeder Cache-Layer drumherum |
| **Seite optional, Quelle Pflicht** | API-Quellen (Open5e) haben keine Seiten; entlastet auch das PDF-Parsing |
| **meta-Tabellen nur additiv** | spart Importer-Aufwand, streicht kein Feature |
| **Errata/Auslegung als `inhaltsart`-Werte, nicht als neue Spalte** (31.07.2026) | Die Pipeline gibt es schon: Config-Pflichtfeld → Validator in `registriere_quelle` → DB → Web-Export → Tool-Ausgabe (SYN-P0-007). Eine eigene Spalte hätte jede dieser Stationen neu verkabeln müssen, und semantisch ist es dieselbe Achse: *was für eine Art Inhalt ist diese Quelle?* Der Spoiler-Schutz bleibt unberührt, weil alle Auswerter auf `== 'abenteuer_setting'` prüfen — die eine Ausnahme (`web.py`, `!= 'abenteuer_setting'`) wurde auf eine Positivliste umgestellt |
| **Sage Advice trägt `edition = "2014"`** | Das Compendium legt ausschließlich die 2014er Regeln aus; für 2024 gibt es keinen Nachfolger. Gewollte Folge: bei der Standardsuche erscheinen seine Treffer unter `andere_editionen` statt als vermeintliches 2024-Ruling. Der Auto-Import lehnt den Band weiter ab (seine DDB-Kategorie trägt kein 5e/5.5e-Präfix) — der explizite `[[ddb.buch]]`-Block ist der Weg, weil dort die Edition **gesetzt** und nicht geraten wird |
| **Errata-Lizenz nicht „CC-BY…"** | Die Errata-PDFs sind frei verteilt, aber nicht frei lizenziert. Der Präfix `CC-BY` löst in `app/tools/ausgabe.py` automatisch die SRD-Attribution aus — sie hier anzuhängen wäre eine falsche Rechtsaussage |
| **Antwortgerüst wird gemessen, nicht begutachtet** (07./08.08.2026) | Der LLM-Richter lag bei Strukturfragen in 2 von 3 Urteilen falsch, während der echte Verstoß unbemerkt in derselben Antwort stand — Struktur ist messbar (`pruefe_geruest`), der Richter behält nur Weiches. Drei Folge-Lehren aus derselben Woche: (1) Jedes neue Prüfmuster wird erst an den gespeicherten Antworten bezahlter Läufe kalibriert (vier von fünf F2-Fehlschlägen waren Fehlalarme des Musters, nicht des Modells). (2) Ein Kanal-3-Hinweis wirkt nur am Werkzeug, das die Antwort tatsächlich liefert — die „Rest-Streuung" waren Listen-Antworten, und die Optionslisten trugen als einziger Weg die Kopfzeilen-Regel nicht. (3) Wo eine Regel zweimal nicht wirkt, wirkt ein wörtliches Muster-Beispiel (DC4: 2/3 rot → 5/5 grün) |
| **`max_tokens` 8000 + Runden-Cap-Schlussrunde ohne Werkzeuge** (08.08.2026) | Seit B15 setzt eine Unterklassen-Auskunft fünf Stufen-Merkmale zu EINER Antwort zusammen — die riss bei 4000 und 6000 jeweils kurz vor der Pflicht-Belegzeile ab. Und am Rundendeckel kam vorher eine LEERE Antwort zurück: acht Runden bezahlte Recherche, nichts geliefert. Die Schlussrunde geht ohne `tools` raus und braucht den expliziten Auftrag — ohne ihn produzierte das Modell einen Denkblock und keinen Text |

### Entscheidung: Bekannte Quellfehler kennzeichnen, nie korrigieren (03.08.2026)

Das Datenbank-Audit fand drei Stellen, an denen nicht der Import falsch ist, sondern **die
Quelle**: Das offizielle deutsche SRD 5.2.1 druckt auf S. 302 „TP 287 (23W12+161)" (die
Formel ergibt 310,5) und auf S. 381 „TP 65 (10W8+30)" (ergibt 75); der Open5e-Datensatz des
Oktopus trägt KON 0 und einen Rettungswurf +30.

Der naheliegende Griff — `body_md` reparieren — verbietet sich hier, obwohl er bei OCR-Rissen
richtig ist. **Das Kriterium ist, wo der Schaden entstand.** Ein OCR-Riss ist ein
Extraktionsschaden: Die Reparatur stellt wieder her, was gedruckt steht. Hier steht das
Gegenteil: gedruckt ist es wirklich so. Eine stille Korrektur stünde in keinem Diff, wäre
beim nächsten Re-Import weg und ließe den Bestand etwas sagen, was seine Quelle nicht sagt.

Also die Bauform von V9, nur ohne amtliches Dokument: **Die Korrektur steht daneben.**
`config/quellfehler.py` führt je Fall den falschen Wortlaut, den belegten richtigen Wert und
den Beleg **aus dem Bestand selbst** (englische Fassung, offizielles Erratum, Rechenweg);
die Auskunft trägt ihn als `hinweis_quellfehler` neben dem unveränderten Regeltext.

Dasselbe Register ist die geprüfte Ausnahmeliste der neuen TP-Formel-Prüfung — Beleg, kein
Deckel: Eine Abweichung **ohne** Registereintrag bricht den Deploy, und ein Registereintrag,
dessen Wortlaut nicht mehr im Bestand steht, wird gemeldet statt still ignoriert.
Ausdrücklich **kein** `inhaltsart = 'errata'`: Für den Vampir-Vertrauten gibt es kein
WotC-Erratum, und eine selbstgeschriebene Notiz als amtliche Korrektur einzuspielen wäre
eine Falschaussage über den Rechteinhaber.

### Entscheidung: Errata-Kategorien bleiben `regel` — der Rückweg löst es besser (03.08.2026)

BACKLOG §4 fragte, ob die 43 Errata statt `kategorie = "regel"` die Kategorie ihrer
PDF-Rubrik tragen sollen, damit `foliant_hol_eintrag(kategorie="zauber")` sie findet. Die
Antwort ist **nein**, und zwar aus drei am echten Dokument gemessenen Gründen:

1. **Die Rubrik ist nicht zuverlässig.** `pymupdf4llm` liest das zweispaltige PHB-Errata in
   Druckspalten-Reihenfolge: „Conjure Minor Elementals" und „Conjure Woodland Beings" landen
   physisch **unter** „Appendix C: Rules Glossary", obwohl sie zu Kapitel 7 gehören. Eine
   rubrikgetriebene Zuordnung träfe 41 von 43 — und läge bei zwei Zaubern falsch.
2. **Eine Rubrik ist gar nicht abbildbar.** „Character Origins" führt Spezies *und*
   Hintergründe *und* Herkunftstalente; jede Zuordnung wäre geraten (Regel 1).
3. **Es löst das Problem nicht ganz.** Selbst mit perfekten Kategorien bliebe die
   Auffindbarkeit an die Kategorie gebunden.

Stattdessen der **Rückweg**: Detailabruf und Suche hängen die passenden Nachträge als
`revisionen` an (siehe unten). Das wirkt für **alle** 43 Korrekturen, unabhängig von Rubrik
und Kategorie, braucht keinen Re-Import und lässt den Kategorie-Filter die harte Zusage
bleiben, die er ist. Eine halb korrekte `kategorie`-Spalte wäre schlechter als eine
durchgehend konservative — sie sieht autoritativ aus.

### Entscheidung: Der Rückweg vom Grundtext zu seinem Nachtrag (03.08.2026)

Der Revisions-Layer kannte bis zum Audit nur **eine** Richtung: Drei Stellen nehmen
Errata/Auslegungen aus etwas heraus (Dublettengruppe, Fassungsvergleich, Optionslisten).
Dass es zu einem Eintrag eine Korrektur *gibt*, erfuhr man allein dadurch, dass die
Volltextsuche sie zufällig danebenspülte — und genau das fiel weg, sobald ein
Kategorie-Filter griff oder der Eintrag direkt geladen wurde. Also in den beiden Fällen, in
denen jemand **gezielt** nach der Regel fragt.

Der Abgleich läuft über **Namen plus Glossar-Brücke**, nicht über die Kategorie: Alle 46
Errata-Zeilen tragen `name_de = NULL`, der kanonische Grundtext kommt meist deutsch aus
`srd-de` mit `name_en = NULL`. Ohne Brücke fände man nur die zufällig gleichlautenden Fälle
(Balor, Kraken) — mit ihr 27 der 46 Zeilen. Die Edition muss übereinstimmen; die Kategorie
wird bewusst ignoriert (siehe Entscheidung darüber).

Zwei Fallen, beide im Code kommentiert: Der Hinweis darf **nicht** nach `hinweis_inhaltsart`
(dort filtert `_markiere_inhaltsart` am Symbol — ein 📌 aus dem Nachschlag ließe ein echtes
Erratum aus dem Sammelhinweis fallen, derselbe Erosionspfad wie §12), und die Liste darf
nicht durch `_markiere_inhaltsart` laufen. Kosten am Vollbestand gemessen: 0,3 ms je
Detailabruf gegen ein p95-Budget von 191 ms bei vier Spielern.

### Entscheidung: Prioritätsbänder statt vier unabhängiger Zahlen (31.07.2026)

Die Frage aus BACKLOG §4 („Quellen-Wertigkeit explizit machen") ist beantwortet. Vorher
vergaben **vier Stellen** unabhängig Prioritäten — Config-Vorlage 10/20/60, DDB fest 40,
Open5e 60+Laufindex, Admin-Rückfall 100 —, ohne dass irgendwo stand, warum eine Zahl so
ausfällt. Jetzt belegt jede **Quellenklasse** einen Zehnerbereich, definiert in
`importer/quellen.py` (`band_fuer`), von den Importern bezogen und von `admin check`
überwacht:

| Band | Quellenklasse |
|---|---|
| 10 | deutsches Kernregelwerk 2024 (Kaufbuch) |
| 20 | deutsches SRD / freie deutsche Quellen |
| 30 | deutsche Altbücher 2014 (Scans) |
| 40 | englische Kaufbücher (DDB/PDF) |
| 60 | englische freie API-/SRD-Quellen |
| 70 | Errata & offizielle Regelauslegung |
| 100 | unklassifiziert (`STANDARD_PRIORITAET`) |

Ein Band ist **zehn breit**, damit ein Import innerhalb seiner Klasse feinsortieren darf
(Open5e legt je Dokument einen Laufindex drauf). `admin check` **warnt** bei Abweichung,
bricht aber nicht ab: die Bänder ordnen Klassen, sie sind keine Invariante.

**Das gekaufte deutsche Vollbuch rankt vor dem deutschen SRD** (Band 10 gegen 20) — es ist
die Obermenge und das Buch, das am Tisch aufgeschlagen wird. Das Gegenargument steht
bewusst dabei: kommt das PHB als OCR-Scan herein, ist das SRD der sauberere Text. Die
Entscheidung ist eine Config-Zeile plus `admin quellen-auffrischen`, also jederzeit
umkehrbar; solange `phb-2024-de` nicht importiert ist, ändert sie ohnehin nichts (die
relative Ordnung aller vorhandenen Quellen bleibt gleich). Entschärft wird sie zusätzlich
dadurch, dass die unterlegene Fassung ihre Fundstelle behält (§5) und Wortlaut-Abweichungen
als Quellkonflikt ausgewiesen werden (SYN-P1-009).

### Entscheidung: Instruktions-Budget durch Entdoppeln (31.07.2026)

`config/stil.py` stand bei 7486 von 7500 erlaubten Zeichen — 14 Zeichen Luft, und der
Test-Docstring behauptete dabei „~6000". Gelöst **ohne Regelverlust**: Der Abschnitt
„QUELLEN & VERSION" wiederholte zwei Regeln von weiter oben und fehlte im zweiten Kanal
ohnehin ganz. Stand danach 7154. Wenn das Budget wieder eng wird, ist Entdoppeln der erste
Griff — eine Regel zu streichen der letzte.

### Entscheidung: `ddb_exporter`-Module tragen englische Namen (P1-006)

Die Namenskonvention lautet „Bezeichner deutsch" (CLAUDE.md). `importer/ddb_exporter/`
bricht sie bewusst: `book_archive`, `ddb_client`, `html_to_markdown`, `cli`. Die Module
bilden fremdes Vokabular ab — D&D-Beyond-API-Felder, Cobalt, Sourcebook, Artefakt-Manifest
—, und eine deutsche Hülle um englische Feldnamen macht den Abgleich mit der API schwerer
statt leichter. Die Grenze läuft am Paket: außerhalb von `ddb_exporter/` gilt Deutsch,
auch für die Aufrufer.

### Entscheidung: `seed_*` bleibt als Verbfamilie (P1-008)

`seed_glossar`, `seed_flexionsbruecke_aus_bestand`, `seed_*` in den Brücken-Modulen: ein
englisches Verb in sonst deutschem Code. „Seeden" ist der eingeführte Fachbegriff für
*abgeleitete Daten aus vorhandenem Bestand erzeugen* und trennt diese Läufe sichtbar vom
`import_*`, das externe Quellen einliest. Eine deutsche Übersetzung („anlegen", „befüllen")
verwischt genau diesen Unterschied. Als **Familie** angeglichen, nicht einzeln.

### Konvention: `cmd_<cli-name>` spiegelt den CLI-Namen (P1-003)

Jede Admin-Unterbefehls-Funktion heißt wie ihr CLI-Name mit Präfix `cmd_` — so findet man
von `admin suchbericht` zu `cmd_suchbericht`, ohne zu suchen. **Die CLI-Namen selbst sind
stabil** und werden nicht umbenannt: Makefile, Deploy-Ablauf und Doku zitieren sie wörtlich,
eine Umbenennung bräche dokumentierte Befehlszeilen.

### Gemessen und verworfen (28.–29.07.2026)

Drei Ausbauten wurden am **Pi-Vollbestand** nachgemessen und danach nicht gebaut. Sie stehen
hier, damit sie nicht als „naheliegende Verbesserung" wiederkommen — die Messung ist der
Beleg, nicht die Meinung.

| Vorhaben | Warum nicht |
|---|---|
| **Relationstabelle `eintrag_bezug`** (SYN-E1) | (a) Der Übersetzungsbezug ergäbe 2151 Paare — genau das, was `_dedupe_und_sortiere` ohnehin je Anfrage rechnet, bei 83 ms Suchzeit und **ohne einen einzigen Leser**. (b) Der Editionsbezug über Namensgleichheit (535 Fälle) funktioniert heute schon als `andere_fassungen`. (c) **Der namensgebende Umbenennungsfall „Rasse" → „Spezies" existiert im Bestand nicht** (0 Glossarzeilen). Die 21 Kandidaten sind Klammer-Suffixe und Singular/Plural — beides deckt `KLAMMER_SUFFIX` bzw. `kanonisiere_schreibvarianten` ab. Dazu ist `eintrag_id` nicht importstabil: die Tabelle bräuchte nach jedem Import einen Neuaufbau, also ein neuer Fehlermodus ohne Nutzen |
| **`edition_quelle` im Glossar nachziehen** (29 % ohne Edition) | Von den 12 echten Konflikten tragen **8 auf beiden Seiten schon eine Edition** — dort ändert Nachziehen nichts. Die übrigen 4 sind die Randfälle ohne Bestandsbezug (Kobold Press, Sandy Petersen, Ulisses), wo eine WotC-Edition zu behaupten **Raten wäre** (Regel 2). Nutzen null, Preis 773 geratene Zeilen plus ein gestörter Konfliktstand |
| **Kategorie-Korrektor für die 24 Zauberkapitel-Abschnitte** | Der Detektor stufte 134 statt 24 Einträge herab, hätte also echte Zauber verborgen — schlimmer als der Befund. Der Breadcrumb weist sie ohnehin als Regelabschnitt aus |

### Entscheidung: Facetten-Vorfilter mit dem Textprädikat als Autorität (28.07.2026)

Der Facetten-Filter parste für **jeden** Eintrag der Kategorie den vollen Body — 1627
`zauber_grad`-Aufrufe je Filteranfrage, 41 % der Profilzeit, der aus der Lastmessung benannte
B9-Hebel. Gelöst **nicht** als „SQL statt Text": Ausgeschlossen werden nur Zeilen, deren
gespeicherter Meta-Wert nachweislich ein anderer ist (dieselben Parser, also äquivalent);
Zeilen **ohne** Meta laufen weiter durch das Textprädikat, damit eine ungeseedete Datenbank
nicht still nichts liefert. Ertrag: 3,5–6,2× je Anfrage, p95 bei vier Spielern 584 → 191 ms.

Die Äquivalenzprobe **schlug zuerst fehl** — und genau das war der Fund: Datenbanken können
noch Meta-Zeilen aus dem in Phase 3 entfernten Open5e-Schreiber tragen (`Evocation` statt
`hervorrufung`), und ein Vorfilter dagegen wirft passende Einträge *still* weg. Deshalb prüft
`_meta_ist_kanonisch` den Wertraum an den Daten selbst (`ritual`/`rk` gab es beim alten
Schreiber nicht) und schaltet den Vorfilter sonst **ganz ab**. Wer hier optimiert, muss diese
Probe erhalten.

### Entscheidung: Das Konflikt-Gate muss 0 erreichen können (27.07.2026)

`admin glossar-audit` meldete dauerhaft „12 echte Konflikte" — eine Zahl, die nie 0 werden
konnte. **Eine Kennzahl, die immer rot ist, hört man auf zu lesen**, und dann fällt der erste
*echte* neue Konflikt beim nächsten Import nicht mehr auf. Am dt. SRD 2024 nachgemessen
(Auszählung im Fließtext) zerfielen die 12 in drei Klassen; nur zwei Fälle waren überhaupt
Dubletten:

| Klasse | Fälle | Behandlung |
|---|---|---|
| **Vom SRD entschieden** | `Tree Stride` (Baumwandeln, Gegenform 0×) · `Sunlight Sensitivity` (Gegenform 0×) | in `KERN_SINGULAR_PAARE` → `kanonisiere_konflikte` demotet die Dublette zur Suchvariante. **Ableitung, keine Setzung** |
| **Geprüfte Homonyme** | `Hide` (Fell/Verstecken) · `Divination` (Schule/Zauber) · `Lucky` (Talent/Halbling-Merkmal) · `Armor` (Ober-/Unterkategorie) · `Weapon Mastery` (srd-de/gedrucktes PHB) | **beide Formen richtig** — eine Auflösung wäre Datenverlust. Stehen in `GEPRUEFTE_HOMONYME`, das Audit weist sie getrennt aus |
| **Randfälle ohne Bestandsbezug** | `Drown` · `Immolation` · `Investigator` · `Shoggoth` · `Mask of the Wild` | aus Abenteuer-/Drittanbieterbänden oder 2014-Merkmalen ohne 2024-Entsprechung — keine Wirkung auf Auskünfte, bewusst unangetastet |

`GEPRUEFTE_HOMONYME` ist ein **Beleg, kein Deckel**: Es führt die erwarteten Formen explizit
mit, und taucht eine **dritte** auf, gilt der Fall wieder als ungeprüft und erscheint als
echter Konflikt. Ein eigener Test hält das fest. Dieselbe Logik trägt
`config/qualitaet_basis.json` für die Datenmängel (§12) — ein Basiswert, gegen den eine Zahl
steigen *oder* fallen kann, statt einer Dauerwarnung.

### Entscheidung: Das Quellen-Register wird erzeugt, nicht gepflegt (14.08.2026)

`config/foliant.toml` ist gitignored, aus dem Deploy-`rsync` ausgeschlossen und von
`admin backup` nicht erfasst. Die Folge war kein Datenverlust, sondern etwas Leiseres: Pi
und Mac trugen **zwei verschiedene Register** — 12 gegen 8 Quellenblöcke, sieben Kürzel
disjunkt —, und keines beschrieb den Produktionsbestand vollständig. Die sieben
DDB-Quellen standen in gar keiner der beiden Dateien.

Die Datenbank weiß es besser. `quellen` führt alle 18 Quellen mit Edition, Lizenz,
Priorität, `inhaltsart`, Herkunft und Pfad — und genau diese Angaben macht Kernregel 2
(„Editionen werden NIE geraten") nach einem Kartenausfall unersetzlich: Raten ist
verboten, also muss es aufgeschrieben sein. `config/quellen-register.toml` ist deshalb ein
**Erzeugnis** aus der DB (`admin quellen-register`, Logik in `importer/quellen.py` neben
dem Schreibweg), kein von Hand gepflegtes zweites Register — das wäre wieder eine Datei,
die auseinanderlaufen kann.

Drei bewusste Festlegungen:

- **Wiederherstellungs-Artefakt, kein Laufzeit-Eingang.** `lade_konfig` bleibt unberührt.
  Eine zweite Konfigurationsquelle wäre ein tägliches Risiko für einen Nutzen, den man
  hoffentlich nie braucht.
- **Ohne Buchtitel** (Davids Entscheidung): Das Repo ist öffentlich. Die Kürzel stehen
  ohnehin darin, die Dateipfade sind durchgehend kürzelbasiert — geprüft, es leckt keiner.
  Beim Wiederherstellen sind 18 Titel nachzutragen; alles, was man nicht raten darf,
  steht da.
- **Solange kein Off-Site-Spiegel existiert** (M3, am 14.08.2026 zurückgestellt), ist
  diese Datei im Git das Einzige, was einen Kartenausfall überlebt.

### Entscheidung: Der Korpus bekommt einen Sollstand (14.08.2026)

`admin check` verglich die Eintragszahl bis dahin nur mit der eigenen FTS-Zeilenzahl. Das
findet einen kaputten Index, aber keinen fehlenden Bestand: Geht ein Buch verloren, fallen
**beide** Zahlen gemeinsam, der Vergleich bleibt grün, und ein Rückgang galt als „Basiswert
nachziehen". Die Frage „ist noch alles da?" konnte das Gate nicht stellen.

`config/korpus_soll.json` beantwortet sie — Kürzel, Edition, Sprache, `inhaltsart` und
Eintragszahl je Quelle, erhoben aus `berechne_manifest`. Eine fehlende Quelle und ein
Einbruch über 5 % sind am Vollbestand Fehler, eine neue Quelle ist ein Hinweis.

Zwei Entwurfsentscheidungen tragen das:

- **`--vollbestand` trennt die Welten.** Auf der Dev-Maschine fehlen 11 der 18 Quellen —
  das ist der Normalfall, kein Befund. Ohne diese Trennung stünde die Prüfung lokal
  dauerhaft rot, und eine Kennzahl, die immer rot ist, hört man auf zu lesen (dieselbe
  Lehre wie beim Konflikt-Gate weiter oben). `make check-pi` setzt das Flag, `make test`
  nicht.
- **Kein Inhalts-Hash als Gate.** Der Hash aus dem Manifest ändert sich bei jedem
  legitimen Import; als Schranke wäre er eine Dauerwarnung. Er bleibt, wo er hingehört —
  im Eval-Report als Stempel des gemessenen Stands.

Nachgezogen wird der Sollstand nach einem *beabsichtigten* Import mit `make soll-vom-pi`
(liest den Pi, schreibt lokal, gehört in den Commit). Buchtitel stehen bewusst nicht in
der Datei, solange offen ist, ob DDB-Titel öffentlich stehen dürfen (BACKLOG M9).

### Entscheidung: Der Discord-Bot bleibt Nachschlagewerk im Gespräch (30.07.–02.08.2026)

Der Bot wird **kein zweites Avrae**. Die Abgrenzung ist inhaltlich, nicht technisch: Avrae
automatisiert den Spieltisch (Würfeln, Initiative, Kampf, Charakterbögen aus D&D Beyond,
Alias-Scripting) und schlägt englische Einträge nach. Foliant *erklärt* Regeln auf Deutsch,
geerdet im eigenen Bestand, mit Belegzeile und Regelversion — und lehnt Spoiler ab. Beide
können im selben Server nebeneinander laufen, ohne sich zu überschneiden.

**Nicht-Ziele** (damit künftige Feature-Ideen daran gemessen werden): kein Würfeln, keine
Initiative-/Kampfverwaltung, kein Charakter-Speichern, kein Alias-Scripting, kein Homebrew,
keine Direktbefehl-Nachschlager (`/zauber`, `/monster`) — die Antwort ist die *Erklärung*,
nicht der Datenbank-Auszug —, kein Charakterbogen-Upload (der bleibt auf der Website).

| Entscheidung | Warum |
|---|---|
| **`/regel-privat` als eigener Befehl, nicht als Schalter `privat:True` an `/regel`** | Discord zeigt bei der Eingabe von „/regel" beide Namen mit Beschreibung an — die Wahl steht damit **vor** dem Tippen. Der Schalter war nur zu finden, wenn man ihn schon kannte. Ephemere Nachrichten können keinen Thread tragen, deshalb sagt der Bot das dazu. **Keine Vertraulichkeitszusage** (§13) |
| **Thread-Wiederaufbau aus der Discord-Historie statt persistentem Verlauf** | Der Verlauf ist in-memory, ein Neustart löscht ihn. `app/discord_bot/wiederaufbau.py` liest den Thread dann aus der Historie zurück (max. 40 Nachrichten) — **kein neuer State**, die Historie *ist* die Persistenz. Der Vergessen-Hinweis bleibt für den Fall, dass dort nichts Verwertbares steht |
| **`fassung` (2024/2014) wandert nur als Klartext in die Frage** | Die Regelversion steuert das Modell über die `edition`-Filter der Tools. Ein zweiter Steuerweg hätte dieselbe Regel ein zweites Mal behauptet |
| **`/hilfe` ist statisch und ephemer** | Eine Kurzanleitung braucht kein Modell — so kostet der häufigste Erstkontakt keine API-Token |
| **`/bestand` liest die DB direkt, statt das Modell zu fragen** (03.08.2026) | „Steht das Buch überhaupt drin?" ist keine Regelfrage, sondern eine Abfrage über den Schrank — eine Modellschleife dafür kostet Token und könnte die Liste zusätzlich falsch zusammenfassen. Ephemer und ohne Schranken wie `/hilfe`. Die Gruppierung (Regelwerke / Errata / Abenteuer) und die Beschriftung teilt sich der Befehl mit der Website-Karte über **`app/bestand.py`**: Zwei Oberflächen auf dieselbe Frage sind zwei Stellen, an denen eine Einordnung driften kann — und ein Abenteuerband, der im Bot unter „Regelwerke" stünde, wäre eine falsche Ansage darüber, wozu Foliant aus ihm antwortet (Spoiler-Schutz). Darstellung bleibt getrennt: HTML-Tabelle dort, **Fließtext-Liste** hier. Der erste Wurf war eine Codeblock-Tabelle — Discord bricht Codeblöcke am Handy aber bei ~40 Zeichen hart um, aus vier Spalten wurde Zeilensalat (Rückmeldung der Runde, 03.08.2026). Listenzeilen brechen weich um und tragen ihre Bedeutung im Wort („Regeln 2024") statt in der Spaltenposition |
| **Kontextmenü „Foliant fragen"** (Rechtsklick → Apps) | Der Spieltisch-Fall „stimmt das überhaupt?" ohne Abtippen; läuft über denselben Weg wie `/regel` |
| **Schranken fallen fail-soft, nie still aus** | Ein ungültiges `DISCORD_COOLDOWN_S` fällt auf den Standard zurück, statt die Schranke abzuschalten |
| **Threads entstehen über den KANAL, nicht über die Nachricht** (Live-Befund 03.08.2026) | Die Antwort auf einen Slash-Befehl kommt aus `interaction.followup.send(wait=True)` und ist damit eine `WebhookMessage` — **ohne Guild-Referenz**. `Message.create_thread()` wirft dort `ValueError`, noch **vor** jedem HTTP-Aufruf, und lief damit am `except discord.HTTPException` vorbei: `/regel` im Kanal lieferte Teil 1 der Antwort und brach dann ab — kein Thread, keine Folgeteile, kein Gesprächskontext. Der @Mention-Weg war nicht betroffen (echte Message), **deshalb fiel es nicht auf**. `TextChannel.create_thread(message=…)` nimmt jeden Snowflake, also genügt die ID — ein Weg für beide Einstiege. Lehre: Ein Fallback, der nur `HTTPException` fängt, deckt eine Bibliothek nicht ab, die auch vor dem Netz schon werfen kann |
| **👍 als zweite Markierung — Polarität ist keine Nuance** (04.08.2026) | Der Meldeweg trug bewusst nur 👎, begründet so: zwei Emoji mit feinen Bedeutungsunterschieden müsste man erklären, und ein Meldeweg, den man erklären muss, wird nicht benutzt. Die Begründung gilt weiter — sie trifft 👍 nur nicht. Ihr Gegenstand ist *Nuance* (👎 gegen 😕 gegen 🤔: „welches nehme ich?"); 👍/👎 ist Polarität, das eine Emoji-Paar, das in jedem Chat dasselbe heißt. Dazu: die Runde reagiert ohnehin schon mit 👍 — das Signal fiel bisher nur stumm auf den Boden, und ein Meldeweg, der bereits benutzt wird, ist der billigste denkbare Ausbau. Umgesetzt **ohne Schema-Migration**, weil `art` beim Bau als Feld statt als Tabelle-je-Art angelegt wurde. Zwei Konstruktionsregeln, die aus der Asymmetrie folgen — 👎 ist eine Beschwerde und selten, 👍 ist Höflichkeit und häufig: Lob fließt **nie** in die Kurationsliste (getrennte Abfrage, getrenntes Limit), und „kein Artefakt" ist ein zulässiges Ergebnis eines 👍, sonst wird jede Nettigkeit zu einem Test und die Suite verrottet |
| **Erster Kurations-Durchgang aus 👎-Markierungen** (04.08.2026) | Drei markierte Antworten, drei Befunde — und alle drei lagen **nicht** am Modell. (1) Der Eintragsname blieb englisch mit `*`, weil die Begriffsannotation nur `body_md` durchsuchte: Das Modell bekam 30 amtliche Begriffe aus dem Fließtext und ausgerechnet für die Überschrift keinen. (2) Ein Monster-Merkmal wurde als allgemeine Regel ausgegeben — B4 stand längst in beiden Prompt-Kanälen, half aber nicht; der Hinweis musste auf Kanal 1. (3) Die Spekulation über ein fehlendes Buch war **regelkonform**: `HINWEIS_LEER` und beide Prompt-Kanäle gaben sie wörtlich vor. **Die Lehre:** Ein wiederholter Verstoß gegen eine Regel, die bereits in beiden Prompt-Kanälen steht, ist kein Modellfehler — dann sitzt die Regel im falschen Kanal oder die Daten tragen sie nicht. Deshalb führt `config/rueckmeldungen_stand.json` je Befund eine `ursache` (code/verhalten/daten/meldeweg); erst die Struktur macht Wiederholungstäter sichtbar |
| **Prompt-Caching formt die Anfrage an drei Stellen — der Eval bleibt außen vor** (09.08.2026) | `system_cachen=True` (nur der Bot) setzt einen festen Breakpoint auf den System-Block, einen request-weiten Breakpoint für den wachsenden Teil (Tool-Ergebnisse, Thread-Verlauf), und entzieht dem Modell die Werkzeuge in der Schlussrunde per `tool_choice: none` statt sie wegzulassen. Der dritte Punkt ist der unauffälligste: Werkzeuge stehen **ganz oben** im Präfix (tools → system → messages), wer dort etwas ändert, verwirft alles dahinter — das Weglassen entzog also nicht nur die Werkzeuge, es warf den kompletten Cache weg und schrieb einen nie wieder gelesenen neuen. Der Eval fährt weiter ohne all das: seine Anfrageform ist die Messgrundlage (`SchleifenErgebnis.verbrauch` zählt die Token-Felder mit, weil ein verfehlter Cache sich **nirgends** meldet — er kostet nur still den vollen Preis). Am deployten Stand nachgemessen: eine Folgefrage liest 43.415 Token aus dem Cache, schreibt null und lässt 6 Token ungecacht — **100 % Trefferquote**, gegenüber rund 5,3 ct je Frage vorher jetzt 1,4 ct. Dass `tool_choice: none` die Auskunft beim Runden-Cap nicht verändert, ist an DC3 gegengeprüft (je zwei Läufe beider Formen, gleiche Inhalte, keine leere Antwort) |
| **Die zwei Breakpoints bekommen verschiedene Lebensdauern: System 1 h, Verlauf 5 min** (09.08.2026) | Gemessen statt geschätzt — `count_tokens` gegen die echte API: das feste Präfix ist **11.638 Token**, eine Werkzeug-Ausgabe 4.283. Das Präfix wird **zwischen** Fragen gelesen, und das Abfrage-Protokoll (1997 Aufrufe, 26.07.–09.08.2026, zu 113 Fragen gebündelt) zeigt dort einen **Median von 14 Minuten**; nur 27–31 % der Lücken liegen unter 5 Minuten. Die Voreinstellung wäre also meist abgelaufen — deshalb dort eine Stunde, die bei der ersten Frage 2× statt 1,25× kostet und sich ab der zweiten zurückzahlt. Der Verlauf hat den umgekehrten Lebenslauf: Er wächst **jede Runde** um rund 4.500 Token und wird Sekunden später gelesen, wofür die Voreinstellung reicht; eine Stunde legte dort nur den doppelten Schreibpreis auf einen Block, der ohnehin gleich veraltet — über einen Spielabend (30 Fragen, 14 Minuten Abstand) gerechnet **43 % teurer**. Nur bei reinen Thread-Nachfragen wäre die Stunde auch dort besser, dem selteneren Fall. Die erste Fassung setzte beide auf eine Stunde; das war mit einer zu groben Byte→Token-Schätzung gerechnet und fiel, sobald die echten Zahlen vorlagen |
| **Prüfen + Reservieren der Ein-Anfrage-Regel ist atomar** (Review 02.08.2026) | Vorher schlüpften zwei schnelle Nachrichten desselben Nutzers durch. Aus demselben Review: Kanal-Fallback, wenn Discord den Thread verweigert (vorher war die *bezahlte* Antwort weg), und zwei Rebuild-Randfälle (allein stehende `max_tokens`-Meldung galt als Antwort; „vollständig" zählte auf der gefilterten Historie) |

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
- **Doku-Pflege** (`tests/test_doku_pflege.py`): §-Verweise treffen ein Kapitel, die
  Stand-Angabe ist nicht älter als der jüngste im Text genannte Vorgang, die vier
  Stand-Angaben liegen höchstens einen Tag auseinander, jede SPEC-Anforderung hat einen
  Status im BACKLOG, genannte Dateien existieren, kein wortgleicher Absatz in zwei
  Dateien, es bleiben genau vier Doku-Dateien. Warum als Test
  und nicht als Vorsatz: Am 03.08.2026 waren alle vier Stand-Angaben veraltet, SPEC verwies
  fünfmal auf ein Kapitel, das es nie gab, und vier Anforderungen hatten keinen Status —
  jeder Befund in Sekunden prüfbar, keiner aufgefallen, weil kein Test die Doku ansah.
  Dieselbe Lehre wie bei `config/qualitaet_basis.json` (§12): Was niemand vergleicht,
  driftet. Der Test prüft **Konsistenz, nicht Wahrheit** — ob eine Aussage noch zum Code
  passt, sieht nur ein Mensch.
- `admin check` + `tests/smoke_test.py` (deckt alle 6 Tools ab, prüft aktiv auf Header-Müll);
  der Smoke-Test lenkt das Abfrage-Protokoll bewusst in eine Wegwerf-Datei um — er läuft
  über `python -m` und damit an der `conftest.py`-Isolation vorbei

**Die CI fährt dieselben zwei Stufen** (`.github/workflows/ci.yml`): einen Job je
Anforderungsdatei. Bis zum 31.07.2026 installierte sie nur `requirements.txt`, wodurch die
26 DDB-Tests sich dort **still übersprangen** — genau der Zustand, den `make test` lokal
verhindert. Der zweite Job schlägt fehl, wenn sie doch übersprungen werden.

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
System-Prompt aus `config/projektanweisung.md` — dieselbe Leseestelle wie Website und
Kanal-Sync-Test; die DC-Fälle fahren zusätzlich den Discord-Zusatz). Der deterministische
Grader ist zweistufig: fallspezifische Marker (`pruefe_deterministisch`, inkl. Opt-in
`statblock_vollstaendig`) plus das Antwortgerüst für **jede** Antwort (`pruefe_geruest`:
Kopf-Emoji, Meta-Verbotsliste, Beleg zuletzt, ein Angebot). Der LLM-Richter bewertet nur
noch, was sich nicht messen lässt (Wiedergabetreue, Spoiler-Feinheiten) — Struktur wird
gemessen, nicht begutachtet (Register §10). **Bewusst NICHT in `make test`** — kostet
API-Tokens (24 ausführbare Fälle × 3–5 Runden, niedrige einstellige Dollar). Report nach
`evals/ergebnisse/` (gitignored) mit den §2-Pflichtfeldern Datum/Modell/`inhalts_hash`;
am Subset markiert er `korpus: lokal (Subset?)` — beweiskräftig ist der Pi-Lauf:
```
ANTHROPIC_API_KEY=sk-… make eval-verhalten-pi
```
**Vierte Schicht, nur am Pi: Lastmessung als Wächter.** `make lasttest-pi`
(`evals/lasttest.py`) fährt die Sessionlast mehrerer gleichzeitiger Spieler gegen den
Vollbestand und **bricht bei p95 > 1000 ms ab**. Die Messung ist damit nicht nur ein
Befund, sondern eine Grenze — B9 kann nicht mehr lautlos wegbrechen. Zahlen und Vorgeschichte
(GIL-Sättigung, Facetten-Vorfilter): [BACKLOG.md](BACKLOG.md) §1/M3.

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

- **Ein einseitiges PDF hat keine falsche Seitenzahl.** Die drei Errata-Quellen tragen
  durchgehend `seite = '1'`, und das sieht nach einem nicht gefüllten Feld aus. Es ist
  aber die richtige Angabe: Die Errata-PDFs sind einseitig. Beim DB-Audit vom 03.08.2026
  war das einer von zwei geprüften Nicht-Befunden — der zweite sind treu reproduzierte
  WotC-Klammer-Typos, die in `config/quellfehler.py` als Quellfehler stehen und deshalb
  ebenfalls nicht „repariert" gehören. Ein Wert, der wie ein Platzhalter aussieht, ist
  erst dann einer, wenn die Quelle es hergibt.
- **Ein Meldeweg, der ein Eingabezeichen nicht kennt, schweigt — er meckert nicht.**
  Der Daumen-Vergleich entfernte den Variantenselektor, nicht die fünf Hautton-Zeichen.
  Wer den Ton einmal eingestellt hat, sendet auf dem Handy fortan die geschmückte Form,
  und die ergab weder eine Protokollzeile noch die 📝-Quittung (Review 11.08.2026). Bei
  einem Kanal, dessen ganzer Zweck die Rückmeldung ist, kostet so ein Loch nicht ein
  Ereignis, sondern die Statistik: Niemand meldet, dass das Melden nicht geht. Wer ein
  Zeichen vergleicht, vergleicht deshalb die nackte Form — und prüft **den ganzen
  Zeichenbereich**, nicht die zwei Varianten, die gerade aufgefallen sind.
- **Eval-Reports leben IM Container und überleben einen Rebuild nicht.** Sie sind aber
  die einzige Kalibriergrundlage: Neue Prüfmuster laufen erst gegen die `antwort`-Felder
  bezahlter Läufe, bevor sie Code werden (Fehlalarm-Reihe A3 → B1 → F2). Seit dem
  08.08.2026 sichert `make deploy-pi` sie deshalb selbst (erster Schritt, fehlertolerant)
  nach `evals/ergebnisse/pi/` (gitignored) — zweimal in einer Woche wären sie sonst weg
  gewesen. Nur wer am Pi von Hand neu baut (`docker compose up -d --build` per SSH),
  muss weiterhin selbst vorher `docker compose cp foliant:/app/evals/ergebnisse …` ziehen.
- **pymupdf4llm OCRt textlose Seiten STILL, sobald Tesseract installiert ist** →
  `use_ocr=False` in `pdf_nach_markdown` ist Pflicht und gesetzt; OCR nur über die Vorstufe.
- **Eine Struktur-Reparatur wird über den KAPITELBEREICH begrenzt, nicht über den Inhalt.**
  Beim Entwirren der Statblock-Verschränkung (03.08.2026) sollte eine Regel „nur dort
  greifen, wo Statblöcke stehen" — erkannt daran, dass der Folgeeintrag eine
  Rüstungsklasse führt. Fallen, Gifte und magische Gegenstände führen aber ebenfalls eine,
  also verschob sie fünfzehn Überschriften der Regelkapitel und der Bestand verlor 5093
  Zeichen. Erst die harte Grenze am Kapitelkopf („ab `# Monster von A–Z`") trug. **Der
  Wächter, der es fand, war der Namensdiff gegen den vorherigen Stand** — die reine
  Eintragszahl fiel nur um zwölf und sah harmlos aus.
- **Nach JEDEM Re-Import einer PDF-Quelle gehört `admin import --quelle glossar` hinterher.**
  Die Namensreparatur (`importer/namensreparatur.py`) läuft in der Glossar-Kette, nicht im
  Import — ein Re-Import spielt also den rohen PDF-Namen wieder ein (`Gar l gy` statt
  `Gargyl`). Real passiert am 03.08.2026 beim srd-de-Re-Import auf dem Pi: Lokal war alles
  grün, weil dort zufällig die Glossar-Kette danach lief; auf dem Pi lief sie nicht, und
  `check-pi` brach den Deploy ab. **Genau so soll es sein** — der Basiswert-Vergleich in
  `admin check` hat den Regress gefangen, bevor ihn jemand am Spieltisch gemerkt hätte.
- **`body_md` niemals von Hand korrigieren, auch wenn die Quelle sich nachweislich irrt.**
  Die Änderung stünde in keinem Diff, wäre beim nächsten Re-Import weg, und der Bestand
  sagte etwas, was sein Buch nicht sagt. Belegte Quellfehler gehören ins Register
  (`config/quellfehler.py`), das die Korrektur **daneben** stellt — §10.
- **Eine Zahl, die zerrissen ist, sieht aus wie eine Zahl.** Die PDF-Tabellenextraktion
  trennt gelegentlich an einer Zellgrenze (`|**RK**1|3|` meint 13), und die Facetten-Regex
  liest korrekt bis zum Trenner — vier Tiere trugen dadurch Rüstungsklasse 1. Solche Risse
  gehören ins Bereinigungsregister des Importers, **nicht** in eine tolerantere Leseregex:
  die bedient auch Open5e und DDB und ließe den kaputten Text stehen, den das Modell
  zitiert. Gefunden hat sie erst die rechnerische Plausibilitätsprüfung (§11) — eine
  falsche Zahl fällt nur über ihren Widerspruch zu einer anderen auf.
- **Ein Prüfmuster ohne Abdeckungszahl ist wertlos.** Die DDB-Quellen escapen ihr Markdown
  (`10d8 \+ 20\)`); ein TP-Muster ohne toleriertes Backslash überspringt sie stumm und
  meldet trotzdem „OK". `admin check` weist deshalb neben den Befunden aus, wie viele
  Ausdrücke die Prüfung überhaupt gesehen hat.
- **Das Pi-Image backt den Code ein** (`COPY`). Ein reines `rsync` aktualisiert die Dateien,
  **nicht den laufenden Container** — ein Import lief dann still mit ALTEM Code weiter und
  meldete „erfolgreich" bei unveränderten Daten. Nach jeder Code-Änderung Pflicht:
  `docker compose up -d --build foliant`.
- **`docker compose up --build web gateway` baut über `depends_on` AUCH `foliant` neu** und
  startet den Live-MCP durch → immer **`--no-deps`**.
- **Die glossar-nur-DB muss existieren, BEVOR `web` startet** — sonst legt Docker ein
  Verzeichnis statt der Datei an.
- **Eine neue Spalte in `quellen` braucht DREI Stellen, nicht eine.** `db/schema.sql` legt
  sie nur in **frisch angelegten** DBs an (`CREATE TABLE IF NOT EXISTS` fügt einer
  bestehenden Tabelle nichts hinzu) → zusätzlich `QUELLEN_PROVENIENZ_SPALTEN` in
  `app/db.py` für den ALTER-Nachzug **und** `_AKTUALISIERT` plus die INSERT-Spaltenliste in
  `importer/quellen.registriere_quelle`, sonst frischt der Upsert sie nie auf. Wer eine Spalte
  ins Web durchreichen will, trägt sie außerdem in `QUELLEN_SPALTEN`
  (`app/charakterbogen/glossar_export.py`) ein — eine Positivliste, damit interne Felder
  nicht versehentlich öffentlich werden.
- **Handgeschriebene Tabellen-Definitionen in Fixtures laufen dem Schema davon.** Beim
  Schema-Zuwachs v3 brach `tests/test_quellen_beschriftung.py` an einer abgetippten
  `CREATE TABLE quellen (...)` — einem stillen Zweitschema. Fixtures speisen sich aus
  `db/schema.sql` (`_db.SCHEMA_DATEI`), dann kann das nicht wieder passieren.
- **Eine Kennzahl ohne Basiswert ist keine Warnung, sondern Rauschen.** `admin check` gab
  Zahlen aus, aber niemand verglich sie mit dem letzten Stand. Folge (01.08.2026): Die
  gemeldeten OCR-Risse waren von 51 (so stand es im BACKLOG) auf 91 gewachsen, ohne dass
  es auffiel — und 42 davon waren gar keine Risse, sondern alphabetische Registerköpfe aus
  DDB-Büchern (`B | Monsters`, `Spells J`), die die 49 echten Befunde überdeckten. Seither
  hält `config/qualitaet_basis.json` den Stand **je Quelle** fest: steigt eine Zahl, bricht
  der Check (neuer Mangel); sinkt sie, meldet er „nachziehen"; bleibt sie gleich, ist er
  still. Die Datei liegt im Git, damit das Anheben einer Zahl im Diff steht und begründet
  werden muss — es ist eine Entscheidung, keine Buchführung. Quellen, die in der geprüften
  Datenbank fehlen, werden übersprungen (das Mac-Subset führt vier von fünfzehn; sonst
  meldete der Vergleich lauter Scheinverbesserungen).
- **Eine Kennzeichnung, die eine andere unterdrückt, ist kein Schutz mehr.** Der
  Sammelhinweis für die Nebenlisten (`_markiere_inhaltsart`) brach ab, sobald irgendein
  `hinweis_inhaltsart` stand — folgenlos, solange nur Abenteuerbände markiert wurden (es
  war derselbe Text). Mit Errata nicht mehr: 📌 im Detail plus Abenteuerband in
  `andere_fassungen` liess den 🚫-Satz lautlos wegfallen. Wer eine zweite Marker-Art
  einführt, muss jede Stelle prüfen, die „es steht ja schon ein Hinweis da" annimmt.
- **Ein CHECK auf einem Wertraum, der noch wachsen kann, ist eine Migrationsfalle.**
  SQLite ändert eine Constraint nur über einen Tabellen-Neuaufbau (CREATE + COPY + DROP +
  RENAME) — `CREATE TABLE IF NOT EXISTS` erneuert nichts, `ALTER TABLE` erzeugt nichts.
  Beim Zuwachs von `inhaltsart` um `errata`/`regelauslegung` hätte der alte CHECK jede mit
  v2 angelegte Datenbank beim ersten Errata-Import mit `IntegrityError` abbrechen lassen
  (real reproduziert). Deshalb: **geschlossene Wertlisten gehören in den Python-Validator
  am einen Schreibweg**, nicht ins Schema — dort greifen sie auch auf Datenbanken, die den
  CHECK nie hatten. Was das Schema nicht kann, macht `admin check`: vorhandene Fehlwerte
  finden. Gilt genauso für `edition` (nur `length > 0`, seit jeher aus demselben Grund).
- **`srd_zauberbruecken.fingerabdruck` ist die Beweisgrundlage der 106 geseedeten
  Zauber-Brücken — seine Regexe bleiben roh.** Sie sind nachweislich zu streng
  (`**Komponenten:** V, G, M` läuft ins Leere, weil die zwei Sterne zwischen Label und Wert
  stehen; `Range:?` trifft ohne Wortgrenze das `Range` in `Ranger`). Wer sie „repariert",
  verschiebt Glossar-Paare. Für die Facetten gibt es deshalb `kopf_felder()` mit
  auszeichnungsfreiem Kopf und wortgrenzen-festen Labeln — `tests/test_facetten_seeder.py`
  hält fest, dass der Abdruck sich dabei nicht bewegt.
- **Der Quellbezug ersetzt NIE eine vorhandene Datei.** Wer `quell_url` als „hol die
  aktuelle Fassung" liest, liegt falsch: Der Schritt greift nur, wenn unter `dateipfad`
  nichts liegt. Das ist Absicht — unter `quellen/` stehen kuratierte und reparierte PDFs,
  und ein Bezug, der sie überschreibt, vernichtet Handarbeit beim routinierten Re-Import.
  Eine neue Auflage kommt herein, indem man die Datei bewusst löscht (und dann `quell_hash`
  UND `versions_stand` nachzieht, sonst bricht der Pin den Import ab — richtig so).
- **Ein Re-Import spielt die rohen OCR-Namen wieder ein** und macht die Namensreparatur der
  betroffenen Quelle zunichte. Facetten deshalb nie über einen Re-Import nachziehen, sondern
  mit `import --quelle facetten`. Musste ein Re-Import doch sein (z. B. nach einem
  Chunking-Fix), ist die **Reparatur danach nachzuziehen**: `import --quelle glossar` bringt
  `repariere_2014_namen` und die kuratierten Titel (`namensreparatur.KURATIERTE_TITEL`) mit.
  Die CLI-Hilfe des Kommandos sagt das seit dem 31.07.2026 selbst — vorher stand es nur in
  einem Backlog-Absatz, den beim Re-Import niemand liest.
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
- **Ein Test, der beim ersten Lauf grün ist, ist noch kein Test.** Am 04.08.2026 deckten
  frisch geschriebene Regressionstests zwei Fixes ab — und einer davon ließ sich
  rückstandslos zurückdrehen, ohne dass etwas fehlschlug: Der Test prüfte die
  Glossar-Funktion direkt statt den Weg durch `ausgabe._detail`, den die Antwort
  tatsächlich nimmt. **Gegenprobe: Fix kaputtmachen, Test muss fallen.** Kostet eine
  Minute und ist der Unterschied zwischen abgesichert und beruhigt.
  Am selben Abend dieselbe Falle in ihrer zweiten Form: Die Mutation traf den
  Struktur-Pfad der Suche, der Test den Freitext-Pfad — grün, obwohl kaputt. **Hat eine
  Funktion mehrere Aufrufstellen, muss die Gegenprobe jede einzeln treffen**; ein
  Sammelhinweis, der nur an einem Ausgabeweg hängt, fehlt genau dem, der ihn braucht.
  Dritte Form (06.08.2026): **Die Gegenprobe kann auch an den TESTDATEN scheitern.** Der
  Schutz von `term_de` gegen fuzzy-fremde Übersetzungen war nur mit `"Actions"` geprüft —
  dessen `fuzz.ratio` zu `"Reactions"` ist 87.5 und liegt damit *unter* dem Cutoff 88, es
  entstand also gar keine Fuzzy-Zeile. Der Schutz ließ sich rückstandslos ausbauen, ohne
  dass etwas fiel. **Wer eine Schwelle absichert, braucht einen Fall auf der scharfen
  Seite** (jetzt `Retrained`/`Restrained` mit 94.7).
- **Discord-REST ohne `User-Agent` antwortet mit „error code: 1010".** Cloudflare weist
  jeden eigenen Client ab, der keinen setzt — und die Meldung nennt weder Header noch
  Cloudflare als Ursache. Sie sieht aus wie ein Rechteproblem am Bot-Token und kostete am
  04.08.2026 eine Viertelstunde Suche an der falschen Stelle. `deploy/discord_api.py::hole`
  setzt ihn; **das ist der Grund, warum der Kontext-Abruf dort angebaut wurde** statt in
  einem eigenen Modul — sonst lernt der zweite Client dieselbe Falle noch einmal.
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
- **Korpus-DB-Journal = DELETE** (Bind-Mount) — nicht auf WAL umstellen. Gilt für
  `data/foliant.sqlite`; das Abfrage-Protokoll liegt bewusst auf **WAL**
  (`app/protokoll.py`) — eigene Datei, eigene Schreiblast, kein Widerspruch.
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
  `query_only=ON`); alle 6 Tools sind `readOnlyHint`. **Jeder** Lesepfad geht über
  `db.connect_readonly` — auch `/ready`, das bis zum 31.07.2026 ein rohes `sqlite3.connect`
  ohne `query_only` benutzte und damit als einziger Pfad ohne die zweite Leitplanke lief.
- **Fail-fast:** Mit `FOLIANT_PRODUKTION=an` verweigert der Server den Start, wenn das
  Pfad-Token kürzer als 16 Zeichen ist.
- **Eingabegrenzen:** Suchanfragen sind längenbegrenzt, `limit` wird gedeckelt (DoS-Schutz).
- **Abfrage-Protokoll ohne PII:** Das Log (`data/foliant-protokoll.sqlite`) enthält nur
  Suchbegriffe, Filter und Zeiten — keine Nutzerkennungen, IPs oder Gesprächsinhalte. Es
  ist die einzige Schreib-Ausnahme des Serving-Pfads und liegt deshalb in einer eigenen
  Datei; die bediente Korpus-DB bleibt strikt `mode=ro`.
  Dieselbe Zusage gilt für die Tabelle `rueckmeldungen` (§9): Sie hält die **Frage** —
  dieselbe Datenklasse wie `suchbegriff` — und einen **Nachrichten-Link**. Bewusst *nicht*
  den Antworttext (das wäre Gesprächsinhalt in einer Log-Datei, und der Link führt in einem
  Klick dorthin, wo die Antwort ohnehin steht) und **keine Nutzerkennung**: Wer markiert
  hat, ist für die Kuration ohne Bedeutung, und die Markierung soll kein Sozialprotokoll
  werden. Deshalb zählt auch nicht, wie oft markiert wurde — `UNIQUE(art, verweis)` ist die
  Entdopplung, die ohne Nutzer-Identität funktioniert. Der Schnitt gilt für **beide**
  Vorzeichen: Auch ein 👍 hinterlässt keine Spur, wer gelobt hat. Entdoppelt wird je Art,
  ein strittiges Paar (👎 *und* 👍 an derselben Antwort) steht deshalb als zwei Zeilen da
  — das ist der Befund, nicht seine Auflösung.
- **Laufzeit offline** (MCP), read-only auf legal erworbenen Daten; Admin-Funktionen **nie**
  über den Tunnel, nur lokal/SSH.
- **Discord-Bot:** keine eingehende HTTP-Fläche (nur ausgehend zu Discord/Anthropic);
  Zugangskontrolle ist die **Guild-Sperre** plus Nutzer-Cooldown und Tagesdeckel. Die
  Tools laufen in-process am `ZugriffsFilter` vorbei — bewusst, wie beim Eval-Harness:
  der Filter schützt den HTTP-Weg, nicht die Prozessgrenze (SPEC.md §12 Nr. 6). Der
  Spoiler-Schutz bleibt prompt-basiert; im gemeinsamen Kanal sieht jeder jede Antwort
  (Ausnahme: `/regel-privat` antwortet ephemer nur dem Fragenden — das ist Rücksicht
  auf den Kanal, **keine** Vertraulichkeitszusage: Discord entscheidet, wie lange eine
  ephemere Nachricht lebt, und der Rebuild liest ohnehin nur echte Kanalbeiträge).
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
**P3-003 Errata-Tracking — seit 03.08.2026 mit Inhalt** (eigene `inhaltsart`-Werte
`errata`/`regelauslegung`, Kennzeichnung 📌/⚖️ in beiden Ausgabewegen, Dedupe-Schutz gegen
Verdrängung des Grundtexts, Prioritätsband 70, Chunking am echten Dokument justiert und
**43 Korrekturen aus den drei WotC-Errata importiert**, deren PDFs der Import selbst holt).
Offen bleibt die **Regelauslegung**: Sage Advice ist noch nicht eingebunden, und der
bediente Pi-Bestand trägt die Errata erst nach einem Deploy — [BACKLOG.md](BACKLOG.md) §4 ·
P3-004 Hausregeln-Overlay. Siehe [BACKLOG.md](BACKLOG.md) §4.
