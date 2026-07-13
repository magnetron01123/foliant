# Foliant — Anleitung für Claude Code

Foliant ist ein self-hosted MCP-Server: ein **Regel-Nachschlagewerk für D&D 5e (Fassung 2024),
Deutsch-first**. Die **verbindlichen Anforderungen** stehen in `docs/foliant-anforderungen.md`
(Rev. 8) — bei fachlichen Fragen zuerst dort nachsehen. Wegweiser über alle Dokumente:
`PROJEKT-UEBERSICHT.md`. Historische Arbeitsaufträge liegen in `docs/archiv/`.

**STATUS (11.07.2026): MVP komplett und live.** Server auf dem Pi (`pi@<pi-host>`,
`~/foliant`), öffentlich via Cloudflare Named Tunnel unter Geheimpfad + IP-Allowlist.
Bestand ~9490 Einträge aus 12 Quellen (dt. SRD 5.2.1, Open5e, 8 DDB-Bücher, 2 DDB-Druck-
Bücher), 17 Tools, Datenbank-QS abgeschlossen (`docs/QS-BERICHT-datenbank.md`). Offen ist
die Roadmap `docs/MVP-ABGLEICH-UND-ROADMAP.md` (M-Phasen bis zur Gruppennutzung) — NICHTS
aus den abgeschlossenen Phasen neu bauen.

## Oberste Regeln (nicht verhandelbar)
1. **Geerdet, keine Halluzination (B1):** Antworten NUR aus dem Bestand. Nichts im Bestand →
   ehrlich „nicht gefunden". Kein Auffüllen aus Allgemeinwissen/2014/Homebrew.
2. **Version immer (§6):** Jeder Eintrag trägt seine Regelversion; jede Auskunft nennt sie;
   Standard 2024; ältere Stände klar kennzeichnen. `edition` ist in der DB NOT NULL.
   **Editionen werden NIE geraten** — beim DDB-Import autoritativ aus der Buch-DB, bei
   PDFs pro Buch explizit gesetzt; unklar = nicht importieren.
3. **Deutsch-first (§5):** offizieller deutscher Begriff, Englisch IMMER in Klammern; fehlt
   offizielles Deutsch → markierte deutsche Wiedergabe mit `*`. Deutsche Quellen haben Vorrang.
4. **Keine Spoiler / kein Scope-Creep:** keine Abenteuer-/Kampagneninhalte, keine Rollen,
   kein Würfeln, kein Charakter-Speichern (§8/§9). Spoiler-Schutz ist oberste Verhaltensregel.
5. **Verhaltensregeln über DREI Kanäle:** `config/stil.py` (Server-Instruktionen) +
   Tool-Beschreibungen + **Grounding-Hinweise in den Tool-AUSGABEN** (zuverlässigster Kanal).
   Kern-Duplikat für Davids Claude-Projekt: `docs/CLAUDE-PROJEKT-ANWEISUNG.md` —
   **bei Änderungen beide synchron halten.**

## Betriebsmodell & Deploy
- **Pi = Betrieb + Importe, Mac = Entwicklung/Administration.** Importe laufen via
  `docker compose exec foliant python -m app.admin …` auf dem Pi.
- Deploy: `rsync` (Excludes: .git, .venv*, data, quellen, .env, config/foliant.toml, .claude)
  → **danach ZWINGEND `docker compose up -d --build foliant`** — der Code ist ins Image
  gebacken; ohne Rebuild läuft still der alte Stand weiter und meldet „Erfolg".
- **Zugang** (`app/zugriff.py`): MCP-Endpoint unter `/<FOLIANT_PFAD_TOKEN>/mcp` (Token in
  Pi-`.env`) + IP-Allowlist auf Anthropics Egress-Ranges via `CF-Connecting-IP`.
  Rotation: Token ändern → rebuild → neue URL an die Runde. `/health` bleibt offen.
- Admin-CLI: `status | import | reindex-fts | check | manifest | pdf-triage | ocr-pdf | ddb-*`.
  Nach jedem Import: **`make test`** (Gate über beide venvs + Golden-Suite) und
  `admin manifest` als Korpus-Fingerabdruck festhalten. Kanonischer Betriebsweg:
  `docs/RUNBOOK.md`; Verhaltensabnahme: `docs/EVAL-CHECKLISTE.md`.

## Import-Pipelines (welcher Weg für welche Quelle)
- **Born-digital-PDF** (z. B. dt. SRD): `[[quelle]]`-Block in `config/foliant.toml` →
  `admin import --quelle <kuerzel>`. Chunking über `SPLIT_REGELN`/`MERGE_REGELN`/`BEREINIGUNG`
  je Quelle in `importer/import_markdown.py` — der wichtigste Qualitätshebel, an echten
  Seiten justieren.
- **Gescannte PDFs:** `admin pdf-triage` (Befund) → `admin ocr-pdf` (OCRmyPDF/Tesseract;
  `--redo` bei Alt-OCR, `--voll` = kompletter Neuaufbau) → normale Pipeline. Guardrail
  lehnt mehrheitlich textlose PDFs ab. Doku: `docs/DEPLOY-raspberry-pi.md`.
- **Browser-Druck-PDFs (DDB-Ausdrucke):** Textschichten sind beschädigt (Kerning-Risse,
  Mojibake-Fonts, fi/fl-Verlust). Muster-Pilot: efota (Original + kuratierte Reparatur)
  und frhof (Original + generiertes Reparatur-Modul `importer/frhof_reparatur.py`,
  sichtgeprüft). **Konvertierung am Mac, Markdown ist das Import-Artefakt**
  (`quellen/md/<kuerzel>.md` auf dem Pi) — pymupdf4llm-Headings sind umgebungsempfindlich.
  Qualitätsnachweis per Kreuz-Audit (Original vs. OCR: Würfel/Zahlen/Preise seitenweise).
- **DDB-Bücher (Konto):** `docker compose --profile ddb run --rm ddb-exporter sync`
  (Cobalt kurzzeitig in `~/.ddb-cobalt`, danach löschen) → `admin ddb-import-all`.
  Doku: `docs/DDB-IMPORT-anleitung.md`.

## Gotchas (kuratiert — Details in `app/bekannte_macken.py`)
- **pymupdf4llm OCRt textlose Seiten STILL, sobald Tesseract installiert ist** →
  `use_ocr=False` in `pdf_nach_markdown` ist Pflicht und gesetzt; OCR nur über die Vorstufe.
- `bm25()` liefert negative Werte → `ORDER BY bm25(...) ASC`.
- Nach jedem Import FTS-`rebuild` (macht der Importer/Admin selbst).
- DB-Journal = DELETE (Bind-Mount) — nicht auf WAL umstellen.
- SQLite im Threadpool: pro Tool-Aufruf eigene Connection.
- Dubletten gleicher Version über `quellen.prioritaet` (klein = Vorrang; dt. Quellen < DDB
  < Open5e). CC-BY-Attribution des SRD mitführen (`docs/ATTRIBUTION.md`).
- Python-Testfalle: Doku-IPs (`203.0.113.x`) gelten als `is_private`.
- DDB: ToS-Grauzone, nur privat; Cobalt nie in argv/.env/Logs/Git.
- Davids Smarthome-Tunnel auf dem Pi NIE anfassen.

## Definition of Done & Tests
- **`make test`** = das EINE Gate: Haupt-Suite (inkl. Abnahme T1–T12 + Golden-Suite
  `tests/test_golden_bestand.py`, die Regel-SEMANTIK am echten Bestand prüft) + DDB-Suite
  in `.venv-ddb` (sonst unsichtbar rot!) + `admin check` + `tests/smoke_test.py`.
  Synthese-Fund 12.07.2026: grüne Strukturtests bewiesen keine Inhalte — nach jedem
  srd-de-Re-Import ist die Golden-Suite Pflicht.
- T2/T10/T12 sind **Verhaltenstests** → manuelle Checkliste `docs/ABNAHME-PROTOKOLL.md`
  (Schicht 1+2 bestanden; Schicht 3 macht David im Chat).
- Wichtigster Dauertest: **T2** — Frage außerhalb des Bestands → ehrliches „nicht gefunden".

## Offene Arbeit (Stand 11.07.2026 — Details in der Roadmap)
- **M2 Schicht 3:** Davids 3-Fragen-Checkliste (nachdem er das Claude-Projekt eingerichtet hat).
- **M3-Betrieb:** Uptime-Monitoring + Off-Site-Backup der SQLite.
- **M4:** spielerfeste Kurzanleitung für die Runde.
- **M1:** deutsche 2024-Grundregelwerke, sobald David PDFs liefert (OCR-Weg steht).
- **O4:** Feedback-/Korrektur-Meldeweg. — Und Davids Cobalt-Rotation (DDB-Logout).
