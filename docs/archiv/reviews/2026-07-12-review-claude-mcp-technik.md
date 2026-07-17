# Unabhängige MCP- und Technikreview: Foliant

## 1. Metadaten der Review

| Feld | Wert |
|---|---|
| Reviewer | claude |
| Review-Typ | MCP- und Technikreview |
| Datum | 2026-07-12 |
| Untersuchter Git-Commit | `5cc67289a8066ce83b3a62aa9822165b1acfacbb` („Projekt-Aufraeumen: Archiv, Doku-Refresh, Konventionen", 2026-07-11) |
| Untersuchter Branch | `main` (Arbeitsbaum zu Beginn sauber) |
| Untersuchte Umgebung | Entwicklungs-Mac (Python 3.13.5, lokale Dev-DB mit 2.621 Einträgen aus 2 Quellen); der Produktions-Pi wurde **nicht** direkt geprüft |
| Sprache/Framework | Python 3.12/3.13 · FastMCP 2.14.7 (exakt gepinnt) · zugrunde liegendes `mcp`-SDK 1.28.1 · Starlette/uvicorn · SQLite + FTS5 |
| Transport | Streamable HTTP (`mcp.http_app(...)`, `stateless_http=true`) hinter uvicorn, Cloudflare Named Tunnel |
| Ziel-Client | Claude Custom Connector (Desktop/Mobile); keine weiteren Clients vorgesehen |

**Ausgeführte Prüfungen (alle lokal, nicht destruktiv):**

| Prüfung | Ergebnis |
|---|---|
| `pytest` (Haupt-venv `.venv`) | **98 passed, 5 skipped** (1,1 s; Skips: 3 Modul-Skips für `.venv-ddb`-Tests, 1 Verhaltenstest T10, 1 OCR-Integrationstest ohne Tesseract) |
| `pytest tests/test_ddb_*` (in `.venv-ddb`) | **24 passed, 1 FAILED** — `test_schreibe_artefakt_atomar_und_validiert` (Details: TECH-002) |
| `python -m app.admin status` | 2.621 Einträge (srd-de 1.639, open5e-srd-2024 982), Glossar 1.402 Begriffe |
| `python -m app.admin check` | **OK** (Struktur, FTS, Editionen; Warnung: 176 Einträge mit HTML-Resten) |
| `python -m tests.smoke_test` | **OK** (0 Probleme, alle 16 Tools gegen echte Daten) |
| MCP-In-Memory-Client (`fastmcp.Client`) | Handshake, `tools/call`, Fehlerpfade (Typfehler, ungültige Edition) manuell exerziert |
| Schema-Introspektion (`mcp.get_tools()`) | 16 Tools; Input-/Output-Schemas erfasst |
| Verhaltens-Sonden | ungültige `kategorie`, leerer/5.000-Zeichen-Suchbegriff, Latenzmessung (20–44 ms/Aufruf am Mac) |

**Nicht mögliche / bewusst unterlassene Prüfungen:**
- Kein Zugriff auf den Raspberry Pi → Live-Endpoint, Tunnel, IP-Allowlist im Feld, echte Bestandsgröße (~9.490 Einträge) nur aus der Doku übernommen (als Annahme markiert).
- Kein DDB-Export-Lauf (bräuchte das Cobalt-Secret — bewusst nicht angefasst).
- OCR-Integrationstest übersprungen (Tesseract lokal nicht installiert; läuft laut Test-Skip im Pi-Container).
- Verhalten realer Claude-Clients (Weitergabe der Server-`instructions`) ist nicht messbar prüfbar; das Projekt adressiert das selbst über drei Kanäle.

**Ausgeschlossene Inhalte (Unabhängigkeit):** Der Ordner `docs/reviews` war zu Beginn nicht vorhanden und wurde ausschließlich für diese Datei angelegt. Zur Wahrung der Unabhängigkeit wurden außerdem die projektinternen Audit-/Bewertungsdokumente `docs/QS-BERICHT-datenbank.md` und `docs/ABNAHME-PROTOKOLL.md` **nicht inhaltlich gelesen**; sie fließen nur als „existieren und werden referenziert" in die Doku-Bewertung ein. Unvermeidbar sind Kommentare im Quellcode, die frühere Funde erwähnen — alle Befunde dieser Review wurden unabhängig am Code bzw. durch eigene Ausführung verifiziert.

---

## 2. Executive Summary

Foliant ist ein **ungewöhnlich reifer MVP**. Die Architektur (strikte Trennung Import ↔ Laufzeit, Artefaktvertrag mit Hashes für DDB, transaktionale Importe mit Schrumpf-Schutz, getesteter ASGI-Zugriffsfilter) ist durchdacht und konsequent umgesetzt. Das Kernversprechen — geerdete, versionierte, deutsch-first Regelauskünfte — ist technisch tragfähig verankert: Jeder Eintrag trägt Quelle und Edition (DB-erzwungen `NOT NULL`), jede Tool-Antwort führt Zitat und Regelversion mit, und die Verhaltenssteuerung läuft über drei Kanäle, wobei die **Grounding-Hinweise in den Tool-Ausgaben** (der zuverlässigste Kanal) durchgängig implementiert sind. Die Testbasis ist mit ~123 Testfunktionen für ein Ein-Personen-Hobby-Projekt außergewöhnlich; alle Abnahmetests des Haupt-venvs sind grün, `admin check` und Smoke-Test laufen sauber.

**Kein Befund blockiert den aktuellen Betrieb.** Die zwei wichtigsten Punkte:

1. **TECH-001 (Hoch, nachgewiesen):** Ungültige Werte für `kategorie`/`quelle` in `foliant_suche_regeln` werden nicht validiert und erzeugen ein **falsches „Nichts im Bestand"** für tatsächlich vorhandene Inhalte — inklusive des Grounding-Hinweises, der das Modell anweist, dem Nutzer genau das zu sagen. Das untergräbt punktuell das wichtigste Qualitätsversprechen (B1/B2-Ehrlichkeit) und ist inkonsistent zur vorbildlichen Editions-Validierung.
2. **TECH-002 (Mittel, nachgewiesen):** Ein Rundreise-Test der DDB-Pipeline schlägt fehl, weil eine Testerwartung nach Einführung des Kapitel-Header-Filters nicht nachgezogen wurde — sichtbar nur im selten gefahrenen `.venv-ddb`. Das zeigt eine Lücke im Definition-of-Done: „pytest grün" gilt derzeit faktisch nur für das Haupt-venv.

Daneben: fehlende Enum-Constraints in den Tool-Schemas, offene Versionspins (Reproduzierbarkeit der Pi-Rebuilds), das Geheimpfad-Token in uvicorn-Access-Logs, eine veraltete Aussage in `ATTRIBUTION.md` sowie die selbst erkannten Betriebslücken (Monitoring, Off-Site-Backup). Alles gut behebbar; ein priorisierter Maßnahmenplan steht in Kapitel 14.

**Gesamturteil:** MVP-reif für den Eigenbetrieb; nach Behebung von TECH-001/002 und den M3/M4-Betriebspunkten auch reif für die Spielrunde. Bewertungen in Kapitel 17 (Durchschnitt ≈ 8/10).

---

## 3. Untersuchungsumfang und Vorgehen

1. **Repository-Inventur:** vollständige Dateiliste (82 getrackte Dateien), Git-Historie, `.gitignore`/`.dockerignore`-Abgleich (keine Daten/Secrets im Index — verifiziert per `git ls-files`).
2. **Dokumentation:** `README.md`, `PROJEKT-UEBERSICHT.md`, `docs/foliant-anforderungen.md` (Rev. 8), `docs/foliant-technisches-konzept.md`, `docs/foliant-mcp-best-practices.md`, `docs/DEPLOY-raspberry-pi.md`, `docs/DDB-IMPORT-anleitung.md` (überflogen), `docs/CLAUDE-PROJEKT-ANWEISUNG.md`, `docs/MVP-ABGLEICH-UND-ROADMAP.md`, `docs/ATTRIBUTION.md`, `CLAUDE.md` — ohne `docs/reviews` und ohne QS-/Abnahme-Berichte (siehe Metadaten).
3. **Quellcode vollständig gelesen:** `app/` (Server, Zugriff, DB-Schicht, Glossar, beide Tool-Module, Admin-CLI, Macken-Register), `db/` (Schema + Init), `config/` (Stil, Beispiel- und lokale Config), `importer/` (Markdown/PDF/OCR/Open5e/Glossar/DDB inkl. Exporter-Paket und frhof-Reparaturmodul), `tests/` (Abnahme, Smoke, Zugriff vollständig; übrige Module per Testfunktions-Katalog und Stichproben).
4. **Dynamische Prüfungen:** siehe Metadaten-Tabelle. Alle Läufe gegen temporäre Fixture-DBs bzw. lesend gegen die lokale Dev-DB; keine Produktionssysteme berührt, keine Projektdatei verändert.
5. **Gezielte Sonden** für Hypothesen (ungültige Parameter, Schema-Gestalt, Latenz, größte Einträge) mit dokumentierten Ergebnissen.

---

## 4. Überblick über die untersuchte Architektur

```
IMPORT (einmalig, Netz erlaubt)                LAUFZEIT (dauerhaft, offline)
─────────────────────────────────              ─────────────────────────────
PDF → pymupdf4llm → Markdown ─┐                Claude ──HTTPS──► Cloudflare Tunnel
Open5e-API ───────────────────┤ Chunker               /<token>/mcp     │
dnddeutsch-API → Glossar ─────┤ (SPLIT/MERGE/         ▼                ▼
DDB-Exporter → Artefakt ──────┘  BEREINIGUNG)   ZugriffsFilter (ASGI: CF-IP-Allowlist)
   (eigener Container,             │                   │
    Secret nur im RAM)             ▼                   ▼
                            SQLite + FTS5 ◄─── FastMCP (16 Tools, stateless HTTP)
                                 ▲                (nur lokale, lesende Abfragen)
                            Admin-CLI (docker exec) · Datasette (127.0.0.1)
```

Tragende Entscheidungen (alle im Code wiedergefunden und konsistent):
- **Ein internes Schema für alle Quellen** (`quellen` + `eintraege` + `glossar` + FTS5-external-content mit Triggern); Provenienz (Quelle/Edition/Seite/Lizenz) als First-Class-Felder.
- **`edition NOT NULL`** auf Quelle und Eintrag; `admin check` prüft zusätzlich Quelle↔Eintrag-Editionsgleichheit.
- **Dreistufige Suche** (FTS direkt → Glossar-Brücke mit 2 Hops → rapidfuzz-Fallback) mit deterministischem Ranking (Exakt vor Präfix vor Lauf-Ordinal; dokumentiert, warum bm25-Scores verschiedener Läufe nicht verglichen werden).
- **Editions-Trennung im SQL vor dem Limit**, Fremd-Editionen als separater Lauf (`aeltere_staende`/`andere_fassungen`) — keine stille Vermischung (V5/Q1 technisch erzwungen).
- **Verlustsichere Importe:** vollständiges Parsen vor jedem Löschen, eine Transaktion für Quellen-Upsert + Ersetzen + FTS-Rebuild, Schrumpf-Schutz (50 % bzw. 70 % DDB) mit bewusstem `--force`.
- **DDB zweistufig:** kurzlebiger, gehärteter Exporter-Container (read_only, `cap_drop: ALL`, tmpfs noexec, kein DB-Mount) schreibt hash-versiegelte Artefakte; Offline-Import validiert den Vertrag, baut eine Kandidaten-DB und aktiviert atomar (`os.replace`) mit Backup-Rotation.
- **Zugang:** Geheimpfad aus `FOLIANT_PFAD_TOKEN` + IP-Allowlist auf Anthropics Egress-Ranges via `CF-Connecting-IP`, als reiner ASGI-Wrapper (bewusst kein BaseHTTPMiddleware, um Streaming nicht zu brechen); `/health` bleibt offen und inhaltsfrei.

---

## 5. Stärken des Projekts

1. **Grounding als Systemeigenschaft, nicht als Hoffnung.** Die B1-Regel („nur aus dem Bestand") ist auf drei Kanälen verdrahtet; entscheidend: die Hinweise stehen **in den Tool-Ausgaben selbst** (`HINWEIS_LEER`, `HINWEIS_ALT`, `HINWEIS_MEHRDEUTIG`, `hinweis_uebersetzung`, Grenzen-/Datenbasis-Blöcke der Build-Prüfung). Das ist die robusteste bekannte Technik, um Client-Varianz bei Server-Instructions zu überleben.
2. **Provenienz durchgängig.** Jede Detail-Antwort enthält `zitat` (Quelle · Seite · Regelversion), `lizenz` und bei CC-BY die Attribution; Dubletten bleiben als `weitere_quellen` sichtbar; die Build-Prüfung belegt jede Aussage mit echten DB-Zitaten (`datenbasis`) statt hartkodierter Regelwerte — Regelkonstanten werden zur Laufzeit am Bestand verifiziert (`_regel_beleg` mit Anker-Texten).
3. **Ehrlichkeit als API-Design.** `foliant_pruefe_build` unterscheidet `verstoesse_gefunden` / `unvollstaendig` / `legal_soweit_pruefbar`, listet `nicht_pruefbar` und `grenzen` explizit — „unvollständig ist kein Legalitätsnachweis" ist im Ergebnisschema kodiert, nicht nur im Prosa-Hinweis.
4. **Import-Robustheit.** A7-Transaktionen, Schrumpf-Schutz, Pagination-Härtung (Host-Pinning, Zyklenerkennung, Seiten-Obergrenze), Guardrail gegen Scan-PDF-Rumpfimporte, `use_ocr=False` gegen stilles pymupdf4llm-OCR — jede dieser Leitplanken ist getestet.
5. **Vorbildliches Secret-Handling.** Cobalt kommt nur aus Secret-Datei / macOS-Keychain / verdeckter TTY (nie argv/.env/Logs), Fehlermeldungen sind nachweislich secret-frei (eigener Test), signierte URLs werden redigiert, der Exporter-Container ist maximal eingeschränkt und hat keinen DB-Zugriff.
6. **Bekannte-Macken-Register** (`app/bekannte_macken.py`) plus quellspezifische SPLIT/MERGE/BEREINIGUNG-Regeln: Datenfallen werden einmal gelöst und dokumentiert — genau das richtige Muster für PDF-Ingestion.
7. **Testkultur:** ~123 Testfunktionen inkl. Abnahme T1–T12 (serverseitig), Zugriffsfilter-Matrix, Zip-Slip-Abwehr, Backup-Rotation, Determinismus-Tests; Smoke-Test feuert jedes Tool gegen echte Daten und prüft Deutsch-Term-Logik.
8. **Ehrliche Dokumentation.** Die Doku benennt eigene Grenzen (Verhaltensschicht nicht beweisbar erzwingbar, OCR-Qualitätserwartung, ToS-Grauzone, offene M-Punkte) statt sie zu überdecken; PROJEKT-UEBERSICHT als Wegweiser funktioniert.

---

## 6. Kritische und hohe Befunde

Es wurden **keine kritischen Befunde** identifiziert. Ein hoher Befund:

### TECH-001 — Unvalidierte `kategorie`/`quelle` erzeugen falsches „nicht im Bestand"

| | |
|---|---|
| Schweregrad | **Hoch** (grenzwertig zu Mittel; Begründung unten) |
| Bereich | MCP-Tools / Eignung als Wissenssystem |
| Datei | `app/tools/nachschlagen.py` (`foliant_suche_regeln`), `app/db.py` (`_roh_suche`, `_fuzzy_treffer`) |
| Status | **Nachgewiesen** (lokal reproduziert) |

**Beobachtung:** `edition` wird streng validiert (unbekannter Wert → strukturiertes `fehler`-Feld mit den verfügbaren Versionen, A1). `kategorie` und `quelle` dagegen fließen ungeprüft als SQL-Filter ein. Reproduziert: `foliant_suche_regeln("Feuerball", kategorie="spell")` liefert `{"treffer": [], "hinweis": "Nichts im Bestand gefunden. Sag das ehrlich mit ❌ …"}` — obwohl „Feuerball" mit `kategorie="zauber"` 2 Treffer hat. Dieselbe Mechanik gilt für falsche `quelle`-Kürzel. Die Parametervalidierung ist insgesamt inkonsistent: `edition` strikt, `methode` strikt (`foliant_hol_attributswerte`), `kategorie`/`quelle` still-leer, `richtung` still-Fallback auf `auto`.

**Auswirkung/Risiko:** Das Modell erhält die explizite Anweisung, dem Nutzer ein ehrliches „nicht im Bestand — eventuell fehlt ein Buch" zu geben. Bei einem Parameterfehler des Modells (naheliegend: englische Kategoriennamen wie `spell`/`monster` statt `zauber`/`monster`-Kleinschreibung, oder Buchtitel statt Kürzel bei `quelle`) entsteht so eine **selbstbewusst falsche Negativauskunft** — der direkteste Angriff auf das wichtigste Projektversprechen (T2-Ehrlichkeit). Einstufung „Hoch", weil das Schema die Werte nicht constrained (kein Enum, siehe TECH-003) und der Fehler vom Nutzer nicht erkennbar ist; frequenzmindernd wirkt, dass die Docstrings die gültigen Werte nennen.

**Empfehlung (konkret):**
1. In `fts_suche` (oder in der Tool-Schicht) analog `_pruefe_edition` eine `_pruefe_kategorie`/`_pruefe_quelle` ergänzen: Whitelist = die 8 bekannten Kategorien (wie `admin check` `ERLAUBT_KAT`) bzw. `SELECT kuerzel FROM quellen`; Verstoß → `{"treffer": [], "fehler": "Unbekannte Kategorie 'spell' — gültig: regel, zauber, …", "hinweis": "Parameter korrigieren, NICHT 'nicht gefunden' melden."}`.
2. Zusätzlich Schema-Härtung per `Literal` (siehe TECH-003), damit der Fehler schon in der Client-Validierung scheitert.
3. Regressionstest: ungültige Kategorie darf nie `HINWEIS_LEER` liefern (Kapitel 15, Test V1).

---

## 7. Mittlere und niedrige Befunde

### TECH-002 — Veralteter DDB-Rundreise-Test schlägt fehl; `.venv-ddb`-Suite außerhalb des DoD

| | |
|---|---|
| Schweregrad | Mittel |
| Bereich | Tests/QS, Prozess |
| Datei | `tests/test_ddb_exporter.py:298` (`test_schreibe_artefakt_atomar_und_validiert`); Ursache in `importer/import_ddb.py` (`_KAPITEL_HEADER`-Filter) |
| Status | **Nachgewiesen** (`.venv-ddb`: 1 failed) |

**Beobachtung:** Der Test erwartet nach der Artefakt-Rundreise `eintraege_neu == 2`; tatsächlich importiert wird 1. Ursache: Die Fixture enthält einen Eintrag mit Titel „Spells", und der (bewusst eingeführte) Kapitel-Header-Filter aus den QS-Commits `c116770`/`195fa65` verwirft ihn jetzt korrekt — die Testerwartung (samt Folgekommentar „Auch der 'Spells'-Übersichtsknoten…") wurde nicht angepasst. Der Test läuft nur in `.venv-ddb` (Modul-Skip im Haupt-venv), sodass „pytest grün" im DoD dies nicht abdeckt.

**Auswirkung:** Kein Produktionsfehler, aber eine rote Suite bedeutet: künftige echte Regressionen in der DDB-Kette würden im Rauschen untergehen; das DoD ist faktisch enger als dokumentiert.

**Empfehlung:** Testerwartung auf den gefilterten Stand heben (z. B. `eintraege_neu == 1` plus expliziter Assert, dass „Spells" verworfen wurde) **und** einen Sammel-Befehl ins DoD aufnehmen (z. B. `make test` = `.venv`-pytest + `.venv-ddb`-pytest), dokumentiert in CLAUDE.md unter „Definition of Done".

### TECH-003 — Tool-Schemas ohne Enums/Constraints und ohne Annotations

| | |
|---|---|
| Schweregrad | Mittel |
| Bereich | MCP-Schemas |
| Datei | `app/tools/nachschlagen.py`, `app/tools/charakter.py` (Signaturen) |
| Status | Nachgewiesen (Schema-Introspektion) |

**Beobachtung:** Alle Wertemengen-Parameter sind als freie Strings deklariert: `kategorie: str | None` (8 gültige Werte), `edition: str` (Werte im Bestand), `richtung: str` (3 Werte), `methode`/`attributsmethode` (2 Werte), `kategorie` bei `foliant_liste_talente` (4 Werte). Die generierten JSON-Schemas enthalten daher keine `enum`-Constraints; `output_schema` ist durchgängig das generische `{"type":"object","additionalProperties":true}`. Tool-Annotations (`readOnlyHint` etc.) werden nicht gesetzt, obwohl alle 16 Tools strikt lesend sind.

**Auswirkung:** Der Client kann falsche Werte nicht vorab abfangen (verstärkt TECH-001); das Modell muss gültige Werte aus dem Beschreibungstext extrahieren; Clients können die Harmlosigkeit der Tools nicht maschinell erkennen.

**Empfehlung:** `typing.Literal["regel","zauber",…] | None` für `kategorie`, `Literal["en_de","de_en","auto"]` für `richtung`, `Literal["standard_array","point_buy"]` für Methoden — FastMCP generiert daraus Enum-Schemas (edition bewusst frei lassen, da bestandsabhängig, mit Laufzeitvalidierung). Beim Registrieren `mcp.tool(fn, annotations={"readOnlyHint": True})` setzen. Optional: knappe `output_schema`-Definitionen für die stabilen Kernfelder (`treffer`, `gefunden`, `zitat`, `ergebnis`), damit `structuredContent` verlässlich typisiert ist.

### TECH-004 — Offene Versionspins gefährden reproduzierbare Pi-Rebuilds

| | |
|---|---|
| Schweregrad | Mittel |
| Bereich | Abhängigkeitsmanagement / Betrieb |
| Datei | `requirements.txt`, `Dockerfile` |
| Status | Nachgewiesen (Datei-Inhalt); Risiko, kein aktueller Fehler |

**Beobachtung:** Nur `fastmcp==2.14.7` ist exakt gepinnt; `uvicorn>=0.30`, `httpx>=0.27`, `pymupdf4llm>=0.0.17`, `rapidfuzz>=3.0`, `ocrmypdf>=16.0`, `pytest>=8.0` sind offen. Jeder Deploy erfordert laut CLAUDE.md zwingend `docker compose up -d --build` — das zieht bei jedem Rebuild potenziell neue Versionen. Ausgerechnet `pymupdf4llm` ist im Projekt als „umgebungsempfindlich" dokumentiert (stilles OCR ab 1.28, Heading-Drift), d. h. die Erfahrung, dass Minor-Updates dieses Stacks Verhalten ändern, liegt bereits vor. Zudem enthält das Produktions-Image Testwerkzeuge (`pytest`) und dauerhaft `build-essential`.

**Empfehlung:** Lockfile einführen (`pip-compile` → `requirements.lock` mit `--require-hashes`, oder schlicht alle Zeilen exakt pinnen; mindestens `pymupdf4llm`, `uvicorn`, `httpx` exakt). Dev-/Test-Abhängigkeiten in `requirements-dev.txt` auslagern; optional Multi-Stage-Build ohne `build-essential` im Final-Image.

### TECH-005 — Betriebslücken: kein Monitoring, kein Off-Site-Backup (bestätigt offene M3-Punkte)

| | |
|---|---|
| Schweregrad | Mittel |
| Bereich | Betrieb/Zuverlässigkeit (B9/O1) |
| Datei | — (Roadmap M3; `docker-compose.yml` bietet `/health` bereits an) |
| Status | Bestätigte Lücke (im Projekt selbst erkannt) |

**Beobachtung:** `/health` existiert und bleibt absichtlich offen, aber nichts pollt ihn; die einzige DB-Kopie (samt der aufwendig kuratierten Importe) liegt auf der Pi-SD-Karte — SD-Karten sind der klassische Single Point of Failure dieses Setups. Antwortzeiten unter Sessionlast (B9) sind auf dem Pi nicht gemessen (lokal am Mac: 20–44 ms pro Tool-Aufruf bei 2.621 Einträgen; auf dem Pi mit ~9.490 Einträgen und schwächerer CPU konservativ einige 100 ms zu erwarten — voraussichtlich unkritisch, aber unbelegt).

**Empfehlung:** (a) Externen Uptime-Monitor auf `https://<host>/health` (der Filter lässt `/health` durch; ggf. Monitor-IP in `FOLIANT_ERLAUBTE_IPS`); (b) nächtlicher Cron auf dem Pi: `sqlite3 data/foliant.sqlite ".backup ..."` + Kopie off-site (rsync zum Mac reicht); (c) einmalige Latenzmessung auf dem Pi via erweitertem Smoke (Kapitel 15, Test V4).

### TECH-006 — `ATTRIBUTION.md` widerspricht dem tatsächlichen Betriebsmodell

| | |
|---|---|
| Schweregrad | Niedrig |
| Bereich | Dokumentation/Recht |
| Datei | `docs/ATTRIBUTION.md` (Absatz 2) |
| Status | Nachgewiesen (Widerspruch zu CLAUDE.md/README/Roadmap) |

**Beobachtung:** Das Dokument behauptet, DDB-Inhalte lägen **nur** in der privaten DB und „die öffentliche, authlos getunnelte `data/foliant.sqlite` bleibt frei von DDB-Inhalten"; die Bereitstellung sei „eine separate, noch offene Eigentümer-Entscheidung". Laut CLAUDE.md, README und Roadmap ist diese Entscheidung längst getroffen und umgesetzt: `ins_hauptbestand = true` auf dem Pi, 10 DDB-Bücher in der bedienten DB, Zugang inzwischen durch Geheimpfad + IP-Allowlist geschützt (nicht mehr „authlos offen").

**Empfehlung:** Absatz aktualisieren: DDB-Inhalte werden bewusst über den zugangsgeschützten Endpoint der privaten Runde bereitgestellt (Eigentümer-Entscheidung vom 11.07.2026), Schutzmaßnahmen benennen. Gerade bei einem rechtlich sensiblen Thema sollte die dokumentierte Lage der realen entsprechen.

### TECH-007 — 22-kB-Inhaltsverzeichnis liegt als `regel`-Eintrag im Bestand

| | |
|---|---|
| Schweregrad | Niedrig |
| Bereich | Datenqualität/Suche |
| Datei | `importer/import_markdown.py` (`SPLIT_REGELN["srd-de"]`, Regel `(r"^Verzeichnis der Wertekästen", 2, None)`) |
| Status | Nachgewiesen (größter Eintrag der Dev-DB: `Verzeichnis der Wertekästen`, 22.431 Zeichen, kategorie `regel`) |

**Beobachtung:** Die Skip-Regel greift über den **Kontextpfad der Eltern** — sie verwirft Einträge *unterhalb* des Kapitels, aber der Kapitelkopf selbst wird mit der Fallback-Regel zum `regel`-Eintrag und sammelt das gesamte Verzeichnis (alle Monsternamen mit Seitenzahlen) ein. Folge: ein FTS-Rauschtreffer, der bei fast jeder Monster-Suche als schwacher Zusatztreffer mitspielt (Body-Gewicht 1 dämpft, eliminiert aber nicht).

**Empfehlung:** Skip-Kriterium zusätzlich auf den Eintragsnamen anwenden (z. B. Regel-Erweiterung: Kapitel, deren *eigener* Name das Muster matcht, ebenfalls `None`), oder Eintrag per `BEREINIGUNG` entfernen; danach Re-Import + `admin check`.

### TECH-008 — Geheimpfad-Token landet im Klartext in Access-/Filter-Logs

| | |
|---|---|
| Schweregrad | Niedrig |
| Bereich | Sicherheit/Logging |
| Datei | `Dockerfile` (uvicorn-CMD ohne `--no-access-log`), `app/zugriff.py:87/102` (`print(... {scope.get('path')})`) |
| Status | Nachgewiesen (Konfigurationslage); Exposition nur lokal |

**Beobachtung:** uvicorn loggt per Default jede Request-Zeile inkl. Pfad — der Pfad **ist** hier das Secret. Auch die Blockier-Prints geben den vollen Pfad aus. Die Logs sind nur lokal (`docker compose logs`), aber sie wandern in jedes Log-Bundle/Debug-Paste und überleben Token-Rotationen. `server.py` kürzt das Token beim Startup-Print bereits vorbildlich auf 4 Zeichen — dieselbe Sorgfalt fehlt an den anderen zwei Stellen.

**Empfehlung:** `--no-access-log` in den uvicorn-Aufruf; in `zugriff.py` den Pfad vor dem Print redigieren (z. B. erstes Pfadsegment auf 4 Zeichen kürzen). Rotation-Anleitung um „alte Logs gelten als tokenbelastet" ergänzen.

### TECH-009 — `print`-basiertes Logging ohne Level/Zeitstempel

| | |
|---|---|
| Schweregrad | Niedrig |
| Bereich | Diagnose/Betrieb |
| Datei | `app/zugriff.py`, `app/server.py`, `importer/*` (durchgängig `print(...)`) |
| Status | Nachgewiesen |

**Beobachtung:** Sicherheitsrelevante Ereignisse (blockierte IPs) und Import-Verläufe gehen als ungestempelte `print`-Zeilen nach stdout; es gibt keine Log-Level, keine Korrelation mit uvicorn-Logs. Für Docker-Betrieb funktional, aber Diagnose („seit wann blockt der Filter Anthropic-IPs?") ist erschwert.

**Empfehlung:** Minimal-invasive Umstellung auf `logging` (ein `logging.getLogger("foliant")`, uvicorn-kompatible Konfiguration); Blockierungen als `WARNING`, Importe als `INFO`. Kein großes Refactoring nötig — ~15 Aufrufstellen.

### TECH-010 — DDB-Kapitel-Header-Filter verwirft rein namensbasiert und unbilanziert

| | |
|---|---|
| Schweregrad | Niedrig (mögliches Risiko, nicht nachgewiesen als Datenverlust) |
| Bereich | Import/Datenvollständigkeit |
| Datei | `importer/import_ddb.py` (`_KAPITEL_HEADER`, `_ist_kapitel_header`, Verwendung in `importiere_ddb_artefakt`) |
| Status | Mögliches Risiko |

**Beobachtung:** Der Filter verwirft Einträge allein anhand des Titels („spells", „equipment", „backgrounds", „Chapter N…"), ohne die Body-Länge zu prüfen. Der Code-Kommentar begründet das mit „nie echte Optionen (nur Kapitel-Vorspann)" — für die bisher importierten Bücher per QS belegt. Ein künftiges Buch, dessen Kapitel „Spells"/„Equipment" *substanziellen* Einleitungs-Regeltext vor dem ersten Unter-Heading trägt, würde diesen Text still verlieren. Der Import-Bericht zählt die verworfenen Einträge nicht (kein „silent-cap"-Ausweis).

**Empfehlung:** (a) Zusatzbedingung „nur verwerfen, wenn Body < ~300 Zeichen (nach Kontextzeile)", (b) Anzahl und Namen der verworfenen Header in den Bericht aufnehmen (`"verworfene_kapitel_header": [...]`) — dann bleibt jede Kappung sichtbar. Testidee in Kapitel 15 (V8).

### TECH-011 — Doku-Zahlendrift (klein)

| | |
|---|---|
| Schweregrad | Niedrig |
| Bereich | Dokumentation |
| Datei | `docs/MVP-ABGLEICH-UND-ROADMAP.md` („pytest grün (81/4-skip)" vs. aktuell 98/5), `PROJEKT-UEBERSICHT.md`/`README.md` (Buchzählung „8 DDB + 2 Druck" vs. „10 DDB-Bücher" — gemeint ist dasselbe) |
| Status | Nachgewiesen |

**Empfehlung:** Zahlen beim nächsten Doku-Touch aktualisieren; alternativ Testzahl aus der Doku streichen (veraltet naturgemäß).

### TECH-012 — Repo-/Image-Hygiene

| | |
|---|---|
| Schweregrad | Niedrig |
| Bereich | Wartbarkeit |
| Datei | Projektwurzel (`Neuer Ordner/` leer, `foliant-dokumente.zip`, `foliant-mvp-geruest.zip`), `requirements.txt` (pytest im Prod-Image) |
| Status | Nachgewiesen |

**Beobachtung:** Ein leerer Ordner „Neuer Ordner" und zwei als „entpackt, redundant" markierte ZIP-Archive liegen im Arbeitsverzeichnis (gitignored, aber rsync-Deploy ohne passende Excludes würde die ZIPs auf den Pi kopieren — die dokumentierte rsync-Zeile in `docs/DEPLOY-raspberry-pi.md` schließt sie nicht aus, die in `CLAUDE.md` auch nicht).

**Empfehlung:** Löschen bzw. in `docs/archiv/` verschieben; rsync-Excludes um `*.zip` ergänzen oder auf `--filter=':- .gitignore'` umstellen.

### TECH-013 — Kleine Verhaltens-/Zukunftskanten (Sammel-Befund)

| | |
|---|---|
| Schweregrad | Niedrig |
| Bereich | Tools/DB-Schicht |
| Status | Analytisch hergeleitet, Einzelfälle verifiziert |

1. **`aeltere_staende`-Pauschale:** Beim Standard `edition="2024"` wird *jede* andere Edition als „älterer Stand" etikettiert (`nachschlagen.py:86-88`). Heute korrekt (nur 2014 existiert); eine künftige *neuere* Edition (z. B. „2025") würde falsch als älter deklariert. → Beim Etikettieren `edition < STANDARD_EDITION` prüfen oder beim Einführen neuer Editionen bewusst nachziehen (Hinweis auch: `admin check` whitelistet hart `{"2024","2014"}` — gewollter Guardrail, aber als Pflege-Punkt dokumentieren).
2. **Mehrdeutig-Fehlklassifikation:** Fordert man explizit z. B. `edition="2014"` an und es existiert genau **ein** nicht-exakter Kandidat einer anderen Edition, antwortet `_hole_detail` mit `mehrdeutig` + Kandidaten statt „in dieser Regelversion nicht vorhanden" (`nachschlagen.py:243-249`). Fachlich harmlos (Kandidaten werden gezeigt), aber die Benennung führt das Modell leicht in eine Rückfrage statt einer klaren Negativauskunft.
3. **`hole_eintrag`** selektiert `q.edition AS quelle_edition`, das Feld wird nirgends verwendet (Mini-Totcode).
4. **IPv4-mapped-IPv6:** Käme `CF-Connecting-IP` je als `::ffff:160.79.x.x` an, würde die Allowlist blocken (fail-closed, Verfügbarkeits-, kein Sicherheitsrisiko). Nur relevant, falls Cloudflare das Format je ändert.

### TECH-014 — Skalierungs-Hinweise (heute unkritisch)

| | |
|---|---|
| Schweregrad | Hinweis |
| Bereich | Performance/Datenmodell |
| Datei | `app/glossar.py` (`lookup`, `exakte_entsprechungen`), `app/db.py` (`_brueckennamen`, `_fuzzy_treffer`) |
| Status | Analytisch; Messwerte vorhanden |

Jeder Such-Aufruf lädt die komplette `glossar`-Tabelle mehrfach nach Python (Lookup je Richtung, 2-Hop-Brücke, Dubletten-Brücke) und jeder Null-Treffer scannt alle Eintragsnamen für rapidfuzz. Bei 1.402 Glossar-Zeilen / 2.621 Einträgen kostet die Gesamtsuche 20–35 ms (Mac). Das skaliert linear: nach M1 (drei deutsche Grundbücher + Vollseeding) sind Glossar ~3–5× und Bestand ~2× größer, auf dem Pi zusätzlich Faktor CPU. Vermutlich weiterhin unter 1 s — aber ohne Messung. **Empfehlung:** erst messen (Test V4), bei Bedarf: normalisierte Spalten (`term_de_norm`, `term_en_norm`) mit Index für exakte Lookups + prozessweiter Glossar-Cache mit mtime-Invalidierung. Die ungenutzten `*_meta`-Tabellen sind als bewusste Phase-1-Entscheidung dokumentiert und in Ordnung.

### TECH-015 — Kein Rate-/Größenlimit am Endpoint

| | |
|---|---|
| Schweregrad | Hinweis |
| Bereich | Robustheit/DoS |
| Status | Analytisch; Exposition stark gemindert |

Es gibt keine App-seitigen Limits für Aufruffrequenz oder Suchbegriffslänge (5.000-Zeichen-Query: 19 ms, kein Fehler — geprüft). Da nur Anthropic-Egress + Token-Kenntnis den Endpoint erreichen, ist das Missbrauchsfenster klein (böswillige Mitspieler bzw. geleakte URL + Claude). Für die Zielgruppe (<5 Nutzer) akzeptabel; optional `suchbegriff = suchbegriff[:200]` als Kappung und ein Hinweis in der Spieler-Anleitung.

---

## 8. Bewertung der MCP-Tools und Schemas

**Tool-Inventar (16, verifiziert):** `foliant_suche_regeln`, `foliant_hol_regel|zauber|monster|gegenstand`, `foliant_uebersetze_begriff`, `foliant_liste_klassen|spezies|hintergruende|talente`, `foliant_hol_klasse|spezies|hintergrund|talent`, `foliant_hol_attributswerte`, `foliant_pruefe_build`. Dazu `GET /health` als Custom-Route (bewusst kein Tool).

**Was gut ist:**
- **Namensschema** `foliant_<verb>_<nomen>` ist konsistent, kollisionssicher neben anderen Connectoren und für ein Sprachmodell gut unterscheidbar; das Suche-knapp/Detail-voll-Muster (BP #1) ist sauber durchgezogen und hält die Kontextlast klein (Suchtreffer: Name/Auszug/Zitat; Details: voller `regeltext_md`).
- **Tool-Beschreibungen** sind vorbildlich: Sie nennen Zweck, Parameterwerte, Verhalten bei Mehrdeutigkeit/anderen Editionen **und** die Kernregeln (Grounding, Zitatpflicht, Deutsch-first) — Kanal 2 der Verhaltenssteuerung. Die Schritt-Hinweise (B7-Reihenfolge) in den Listen-Tools sind eine clevere Nutzung von Kanal 3.
- **Zuschnitt:** Die Trennung `hol_zauber`/`hol_monster`/… je Kategorie ist für die Modell-Auswahl besser als ein generisches `hol_eintrag(kategorie=…)`, weil die Kategorie schon in der Tool-Wahl kodiert ist. Überschneidung besteht nur bewusst (Suche findet alles, Detail-Tools sind kategorien-scharf). 16 Tools sind für Claude-Clients gut handhabbar; nicht zu kleinteilig, nicht zu breit.
- **Fehlerverhalten über MCP geprüft:** Typfehler → saubere Pydantic-Validierungsfehler (`ToolError` mit Feldpfad); Fachfehler (unbekannte Edition) → strukturierte `fehler`+`hinweis`-Felder im Ergebnis statt Exceptions — genau richtig, denn so bleibt der Grounding-Hinweis beim Modell. `stateless_http=True` ist die richtige Wahl für den Connector-Betrieb (kein Session-Verlust bei Reconnects).
- **Mehrdeutigkeit** (B4) ist als eigenes Antwortformat (`mehrdeutig` + `kandidaten` mit Unterscheidungsmerkmalen) implementiert und getestet.

**Was fehlt/schwächelt:** die Punkte aus TECH-001 (Validierungslücke `kategorie`/`quelle`), TECH-003 (keine Enums, generische Output-Schemas, keine `readOnlyHint`-Annotations) und TECH-013.2 (Mehrdeutig-Benennung im Editions-Sonderfall). Resources und Prompts werden nicht genutzt — für diesen Anwendungsfall die **richtige** Entscheidung (Claude-Connector-Support für Tools ist am verlässlichsten; die Attribution wäre ein Resource-Kandidat, wird aber pragmatisch in den Detail-Antworten mitgeführt). Eine explizite Server-`version` in `serverInfo` fehlt (Kosmetik).

**MCP-Konventionen:** Initialisierung, Capabilities und Streamable-HTTP übernimmt FastMCP 2.14.7 korrekt; ein eigener End-to-End-HTTP-Test (initialize → tools/list → tools/call über den ASGI-Stack inkl. Geheimpfad) fehlt allerdings in der Suite — heute wird der Filter auf Scope-Ebene und die Tools auf Funktionsebene getestet, die volle Kette nur manuell (Kapitel 15, V3).

---

## 9. Bewertung des Wissens- und Datenmodells

**Struktur:** Das Modell (`quellen` → `eintraege` mit `kategorie`, zweisprachigen Namen, `edition`, `seite`, `body_md`; `glossar` mit Offiziell-Flag und Herkunft; FTS5-external-content mit Triggern) ist für den Zweck **genau richtig dimensioniert**: einfach genug für SQLite-Wartbarkeit, ausdrucksstark genug für Provenienz, Editionslogik und Deutsch-first. Die Entscheidung, alle Quellen auf ein Schema zu normalisieren und die Provenienz sichtbar zu halten, ist im Code konsequent umgesetzt.

**Version/Quelle/Gültigkeit:** `edition NOT NULL` auf beiden Ebenen + `admin check`-Kreuzprüfung + Editions-Filter vor dem SQL-Limit erfüllen V1–V5/Q1/Q3 technisch, nicht nur konventionell. V7 („erweiterbares Versionsschema") ist als freies Textfeld umgesetzt — ausreichend, aber zwei Stellen müssten bei einer neuen Edition angefasst werden (TECH-013.1: `aeltere_staende`-Etikett, `admin check`-Whitelist); das sollte als Pflegehinweis dokumentiert sein.

**Dubletten/Präzedenz:** `quellen.prioritaet` (dt. Quellen 10–30 < DDB 40–45 < Open5e 60+) plus Glossar-gestützte DE↔EN-Dubletten-Erkennung (nur exakte Entsprechungen — bewusst kein Fuzzy) ist eine belastbare Q2-Umsetzung; `weitere_quellen` erhält die Provenienz. **Grenze (bewusst):** Inhaltliche *Widersprüche* zwischen Quellen gleicher Edition werden nicht als Konflikt angezeigt, sondern durch die kanonische Quelle still entschieden — für RAW-Nachschlagen akzeptabel, für spätere Errata-Arbeit wäre ein Diff-/Konfliktausweis eine Ausbaustufe.

**Regeln↔Ausnahmen/Verknüpfungen:** Beziehungen laufen implizit über die Kontextzeile (`*Kontext: Klassen > Kämpfer*`) und Namenskonventionen (`<Klasse>-Unterklasse: <Name>`, `*Subclass of: X*`). Das funktioniert (Klassen→Unterklassen-Zuordnung, Kinder-Aggregation bei Spezies/Talenten), ist aber **stringbasiert und quellformat-abhängig** — die fragilste Stelle des Datenmodells. Sie ist durch Tests und das Macken-Register gut abgesichert; bei wachsender Quellenzahl wäre eine explizite `parent_id`-Spalte die robustere Ausbaustufe.

**Skalierung:** Kuratierte Reparatur-Module pro Druck-Buch (`frhof_reparatur.py`, efota-Wortlisten) sind Handarbeit pro Quelle — als bewusster Pilot dokumentiert und qualitativ beeindruckend, aber nicht automatisierbar; die Kapazitätsgrenze ist der Kurator, nicht die Technik. Glossar-Zugriffsmuster siehe TECH-014. Bestandsgrößen (10³–10⁵ Einträge) sind für SQLite/FTS5 problemlos.

**Nachvollziehbarkeit:** Jede Antwort ist auf einen `eintraege`-Datensatz mit Quelle/Seite/Edition zurückführbar; Datasette bietet den Admin-Blick. Das erfüllt die Belegbarkeits-Anforderung des Wissenssystems vollständig.

---

## 10. Bewertung von Sicherheit und Robustheit

**Angriffsfläche Laufzeit:** minimal und gut verstanden. Nur lesende SQL-Zugriffe, durchgängig parametrisiert (verifiziert; die f-String-Stellen betreffen nur IN-Platzhalterlisten und ein `LIKE`-Muster aus DB-eigenen Werten). FTS5-Query-Injection ist durch Token-Quoting in `_fts_match` neutralisiert (Operatoren/NEAR/Klammern wirkungslos — gute, oft übersehene Härtung). Kein Laufzeit-Netzzugriff (Importer-Module importieren `httpx` lazy). Keine Datei-Schreiboperationen im Tool-Pfad; Pfade werden projektroot-relativ aufgelöst.

**Zugang:** Zwei-Schichten-Modell (Geheimpfad + Anthropic-IP-Allowlist über `CF-Connecting-IP`) ist für die Bedrohungslage (private Runde, geleakte URL) angemessen und **getestet** (Rand-IPs, kaputte Header, `/health`-Ausnahme, Lifespan-Durchleitung, Fail-closed bei öffentlichen Peers ohne CF-Header). Das Vertrauen in `CF-Connecting-IP` ist korrekt begründet (einziger Weg zum Server ist der ausgehende cloudflared-Tunnel; Port 8000 an 127.0.0.1 gebunden — in `docker-compose.yml` verifiziert). Pfad-Normalisierungs-Bypässe (`/health/../…`) greifen nicht (exakter Vergleich, ASGI-Pfad unnormalisiert → fail-closed). Restpunkte: Token in Access-Logs (TECH-008); statische IP-Ranges als Verfügbarkeitsrisiko, falls Anthropic sie erweitert (fail-closed; im Code als Prüfhinweis dokumentiert).

**Prompt-Injection/Tool-Poisoning:** Die Tool-Ausgaben enthalten Buchtexte — theoretisch könnten importierte Inhalte Anweisungen enthalten; die Quellen sind aber kuratiert (eigene Bücher, SRD, Open5e), und der DDB-HTML-Weg entfernt aktive Inhalte (script/style/iframe/on*-Handler/`javascript:`-Links) und neutralisiert `ddb://`-Links. Für die private Nutzung ist das Risiko gering; die Grounding-Hinweise in Ausgaben sind selbst statische Serverstrings (kein User-Content). Solide.

**Secrets:** Cobalt-Handling ist die stärkste Einzeldisziplin des Projekts (Datei/Keychain/TTY, nie argv/env/Logs; secret-freie Fehlermeldungen sind eigens getestet; Work-Verzeichnisse werden auf allen Pfaden aufgeräumt; Exporter-Container ohne DB-Mount, `read_only`, `cap_drop: ALL`, `no-new-privileges`, tmpfs `noexec`). `.env`/DBs/Quellen sind git- und dockerignoriert (verifiziert: 82 Index-Dateien, keine Daten). Die `.claude/settings.json` verbietet Claude Code sogar das Lesen von `.env` und DBs — ungewöhnlich sorgfältig.

**DoS/Ressourcen:** keine App-Limits (TECH-015), aber stark gemindertes Expositionsfenster; SQLite-Verbindung pro Aufruf verhindert Thread-Probleme (dokumentierte FastMCP-Threadpool-Falle). Antwortgrößen sind faktisch durch die Chunk-Größen begrenzt (größter Eintrag 22 kB — und der ist selbst ein Befund, TECH-007).

**Fazit Sicherheit:** dem Einsatzzweck angemessen bis überdurchschnittlich; keine kritischen Lücken gefunden.

---

## 11. Bewertung der Tests

**Bestand:** ~123 Testfunktionen in 15 Modulen + ein Smoke-Skript gegen echte Daten. Reproduzierbar: Haupt-Suite läuft offline in 1,1 s gegen Fixture-DBs (`tmp_path`+`monkeypatch` auf `standard_pfad` — sauberes Muster), deterministisch (keine Netz-/Zeitabhängigkeiten; Determinismus des Rankings/der Artefakte wird sogar explizit getestet).

**Abdeckung der Hauptrisiken — stark:**
- Abnahme T1–T12 serverseitig (Zitatpflicht, ehrliches Nicht-gefunden inkl. Grounding-Hinweis, `*`-Logik, Altstand-Kennzeichnung, 2024-Primär, zweisprachige Brücke inkl. Plural-/Flexions-Regression, Mehrdeutigkeit, Build-Prüfung positiv+negativ, Import-Pflichtversion).
- Import-Sicherheit (A7: Rollback, Schrumpf-Schutz, idempotente Re-Importe, leere Antworten), Open5e-Pagination-Härtung, OCR-Triage/Guardrails, Chunker-Reparaturen (Fragmente, Label-Headings, NFC/Soft-Hyphen), DDB-Vertrag (Hashes, Parent-Zyklen, Zip-Slip, Secret-freie Fehler, Backup-Rotation, Dry-Run), Zugriffsfilter-Matrix, Geheimpfad-Routing an echten Starlette-Routen.
- MCP-Schemas werden **indirekt** getestet (Tools als Funktionen; Pydantic validiert an der MCP-Grenze) — ein expliziter Schema-/E2E-HTTP-Test fehlt (s. u.).

**Lücken:**
1. **Rote `.venv-ddb`-Suite** (TECH-002) und kein Gesamt-Testbefehl über beide venvs; keine CI (bei Solo-Betrieb verschmerzbar, ein lokaler `make test` genügt).
2. **Tool-Auswahl/Verhalten** (T2/T10/T12-Verhaltensschicht) bleibt manuell — bekannt und ehrlich dokumentiert; automatisierbar erst mit LLM-im-Loop (nach MVP sinnvoll).
3. **Fehlerhafte Eingaben:** Typfehler deckt Pydantic ab, fachliche Falschwerte teilweise (Edition ja, Kategorie/Quelle nein — Testlücke deckungsgleich mit TECH-001).
4. **Performance/B9:** keinerlei Latenz-Assertions.
5. **End-to-End über HTTP:** initialize/tools-list/call durch den kompletten ASGI-Stack (Filter + FastMCP) wird nicht automatisiert geprüft.

Konkrete Ergänzungsvorschläge: Kapitel 15.

---

## 12. Bewertung der Dokumentation und Installation

**Stärken:** Der Dokumentensatz ist für die Projektgröße herausragend: klarer Wegweiser (`PROJEKT-UEBERSICHT.md` mit Dokument-Zweck-Tabelle und Konvention „kleingeschrieben = zeitlos, GROSS = lebend"), verbindlicher Anforderungskatalog mit Revisionshistorie, technisches Konzept mit Entscheidungslog inkl. Begründungen, Schritt-für-Schritt-Deploy (Pi, Tunnel, Zugangsschutz inkl. Rotationsanleitung und optionaler WAF-Regel), DDB-Anleitung, Copy-Paste-Projektanweisung für den Claude-Client mit ehrlicher Wirkungstabelle der drei Kanäle. Der README-Schnellstart wurde nachvollzogen: venv → `init_db` → Config → Import → `check`/Smoke funktioniert wie beschrieben (lokale Dev-DB existiert genau nach diesem Muster). Fehlermeldungen der CLI sind konsequent handlungsleitend („erst `python db/init_db.py …` ausführen", „edition ist Pflicht … [[quelle]]-Block nötig").

**Ein neuer Entwickler** kann das Projekt ohne internes Vorwissen starten; MVP-Umfang und Nicht-Ziele sind explizit (§3/§8 des Anforderungskatalogs). Entwicklungs- (Mac, venv, Dev-DB) und Produktionsbetrieb (Pi, Docker, Tunnel) sind klar getrennt; die Betriebsgrenze „Code ist ins Image gebacken — ohne Rebuild läuft still der alte Stand" ist prominent dokumentiert (die wichtigste Betriebsfalle dieses Setups).

**Schwächen:** TECH-006 (ATTRIBUTION widerspricht Betriebsrealität — der einzige inhaltlich relevante Drift), TECH-011 (Zahlendrift), TECH-012 (rsync-Excludes decken die Root-ZIPs nicht). Eine „spielerfeste" Endnutzer-Anleitung fehlt noch (bekannt, M4). Kleinigkeit: `docs/DEPLOY` Schritt 4 zeigt als Health-Antwort `{"status":"ok","name":"Foliant"}` — tatsächlich ist der Name „Foliant für D&D".

---

## 13. Empfohlene Zielarchitektur für die nächste Ausbaustufe

Die bestehende Architektur trägt die geplanten Ausbaustufen (M1–M5, §9-Ausbauten) **ohne Umbau**. Empfohlen wird Evolution statt Revolution:

1. **Schema-Härtung der Tool-Grenze (kurzfristig):** Literal-Enums + Laufzeitvalidierung aller Wertemengen-Parameter + `readOnlyHint`-Annotations + minimale Output-Schemas für stabile Kernfelder. Ziel: Der Client kann Fehlaufrufe abfangen, bevor sie zu falschen Negativauskünften werden.
2. **Betriebs-Schicht (kurzfristig, M3):** Health-Monitoring, nächtliches Off-Site-Backup (SQLite `.backup` + rsync), Log-Hygiene (`--no-access-log`, `logging`-Modul), gepinnte Requirements. Ziel: Der Pi darf ausfallen, ohne dass Importarbeit oder eine Spielsession verloren geht.
3. **Test-Konsolidierung:** ein Befehl für beide venvs + E2E-HTTP-Test + Latenz-Smoke auf dem Pi. Ziel: DoD = ein grüner Befehl.
4. **Mittelfristig (nach M1):** explizite `parent_id`-Beziehung in `eintraege` statt String-Konventionen (Kontextzeile bleibt für Anzeige), sobald die dritte Quellfamilie die Options-Erkennung erneut verkompliziert; Glossar-Lookup auf indizierte Normalspalten umstellen, wenn die Pi-Messung >1 s pro Suche zeigt.
5. **Für die §9-Stufen unverändert gültig:** getrennte Datenräume/Server je Rolle (Spoiler-Isolation strukturell, nie filterbasiert — deckt sich mit BP #10); Hausregeln als Overlay-Quelle mit eigener `prioritaet`-Ebene und sichtbarer Kennzeichnung; universelle Quersuche als Komfort-Tool erst nach Verhaltens-Testharness.

---

## 14. Priorisierter Maßnahmenplan

### Vor dem nächsten internen Test
| Prio | Befund | Ziel | Umsetzung | Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| 1 | TECH-001 | Kein falsches „nicht im Bestand" durch Parameterfehler | `_pruefe_kategorie`/`_pruefe_quelle` analog `_pruefe_edition`; strukturiertes `fehler`-Feld mit gültigen Werten | `foliant_suche_regeln("Feuerball", kategorie="spell")` liefert `fehler`, nie `HINWEIS_LEER`; neuer pytest deckt es | S |
| 2 | TECH-002 | Beide Test-venvs grün | Rundreise-Erwartung an Kapitel-Header-Filter anpassen; `make test` (oder Skript) fährt `.venv` + `.venv-ddb`; DoD in CLAUDE.md ergänzen | Ein Befehl, Exit 0, beide Suiten | S |

### Vor externen Nutzertests (= Freigabe an die Runde)
| Prio | Befund | Ziel | Umsetzung | Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| 3 | TECH-003 | Schema verhindert Fehlaufrufe | `Literal`-Typen für kategorie/richtung/methoden; `readOnlyHint`-Annotations | `tools/list` zeigt Enums; Schema-Snapshot-Test grün | S |
| 4 | TECH-005 | Ausfall-/Verlustsicherheit | Uptime-Monitor auf `/health`; Cron: SQLite-`.backup` + Off-Site-Kopie; einmalige Pi-Latenzmessung | Monitor alarmiert bei Stopp; Restore-Probe aus Off-Site-Kopie erfolgreich; Suchlatenz Pi dokumentiert < 2 s | M |
| 5 | TECH-008 | Token nicht in Logs | uvicorn `--no-access-log`; Pfad-Redaktion in `zugriff.py`-Prints | `docker compose logs` enthält Token nicht mehr | S |
| 6 | TECH-006 | Doku = Realität (Recht) | ATTRIBUTION.md-Absatz zur DDB-Bereitstellung aktualisieren | Dokument nennt getroffene Entscheidung + Schutzmaßnahmen | S |
| 7 | (M4, bestätigt) | Spielerfestes Onboarding | Kurzanleitung Connector-URL/Aktivierung/Beispielfragen/Fallback | Nicht-technischer Mitspieler verbindet sich eigenständig | S |

### Vor Veröffentlichung des MVP (breiterer Dauerbetrieb)
| Prio | Befund | Ziel | Umsetzung | Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| 8 | TECH-004 | Reproduzierbare Rebuilds | Voll-Pinning/Lockfile; `requirements-dev.txt` trennen | Zwei Rebuilds im Abstand von Wochen ergeben identische Versionsstände | S |
| 9 | TECH-009 | Diagnosefähige Logs | `logging`-Umstellung mit Leveln | Blockierte Zugriffe erscheinen als WARNING mit Zeitstempel | S |
| 10 | TECH-007 | Suchrauschen entfernen | ToC-Kapitelkopf beim srd-de-Import verwerfen; Re-Import | Kein `Verzeichnis der Wertekästen`-Eintrag; `admin check` OK | S |
| 11 | TECH-010 | Keine stillen Import-Kappungen | Body-Längen-Bedingung + Drop-Bilanz im DDB-Bericht | Bericht listet verworfene Header; Test V8 grün | S |
| 12 | TECH-012 | Deploy-Hygiene | ZIPs/„Neuer Ordner" archivieren; rsync-Excludes erweitern | Frischer rsync-Lauf überträgt keine Archive | S |

### Nach dem MVP
| Prio | Befund | Ziel | Umsetzung | Größe |
|---|---|---|---|---|
| 13 | (T2/T10/T12) | Verhaltensschicht automatisieren | LLM-Judge-Harness: Skript stellt die Checklisten-Fragen über einen echten Claude-Aufruf mit Connector und bewertet die Antwort regelbasiert | M |
| 14 | TECH-014 | Suchlatenz langfristig sichern | Glossar-Normalspalten + Index; Prozess-Cache | M |
| 15 | (O4, bestätigt) | Feedback-Schleife | `admin merke`-Kommando oder geteilte Meldedatei; Triage-Routine | S |

### Langfristige Weiterentwicklung
| Prio | Ziel | Umsetzung | Größe |
|---|---|---|---|
| 16 | Strukturelle Spoiler-Isolation (A3) | getrennte DB/Server je Rolle; nie filterbasiert | L |
| 17 | Beziehungsmodell | `parent_id` in `eintraege`; Options-Erkennung datenbankgestützt statt String-Konvention | M |
| 18 | Feinere Versionierung (V7-Ausbau) | Errata-/Druckstand als Zusatzfelder; `aeltere_staende`-Logik editionsvergleichend (TECH-013.1) | M |

---

## 15. Empfohlene zusätzliche Tests

1. **V1 — Parametervalidierung (zu TECH-001):** Für jede Wertemenge (kategorie, quelle, richtung, kategorie@liste_talente): ungültiger Wert ⇒ Antwort enthält `fehler` mit gültigen Werten und **nie** `HINWEIS_LEER`; gültige Werte unverändert.
2. **V2 — Schema-Snapshot:** `await mcp.get_tools()` ⇒ Golden-File mit Tool-Namen, Pflichtparametern, Enums, Annotations. Schützt gegen stille Schema-Drift bei FastMCP-Upgrades (wichtig wegen TECH-004).
3. **V3 — End-to-End über HTTP:** `httpx.ASGITransport(app=server.app)` mit gesetztem `FOLIANT_PFAD_TOKEN`: initialize → tools/list → `tools/call foliant_suche_regeln` über `/token/mcp` mit erlaubter CF-IP (Erfolg) und fremder CF-IP (403 auch für gültige MCP-Payload). Deckt die reale Kette Filter→FastMCP→Tool ab.
4. **V4 — Latenz-Budget (B9):** Smoke-Erweiterung: 10 repräsentative Aufrufe, Assertion „p95 < 2 s" — einmal auf dem Pi gegen den echten Bestand fahren und Messwert im Repo festhalten.
5. **V5 — Editions-Zukunftsprobe (zu TECH-013.1):** Fixture mit `edition="2025"`: prüfen, wie Suche (Benennung `aeltere_staende`?), Detail-Fallback und `admin check` reagieren; gewünschtes Verhalten festschreiben.
6. **V6 — Robustheits-Fuzzing der Tool-Grenze:** Suchbegriffe/Namen mit Emoji, RTL-Zeichen, Nullbyte, 100-kB-String, reinen FTS-Operatoren (`AND NEAR( ) *"`), leerem String ⇒ nie Exception, immer strukturierte Antwort mit Hinweis. (Stichproben dieser Review: leer/5 kB ok — als Dauertest verankern.)
7. **V7 — Chunker-Verlustbilanz:** Für srd-de/efota/frhof-Fixture-Markdown: Summe der Chunk-Bodies ≥ X % des bereinigten Inputs (erkennt künftige Split-Regel-Regressionen als Textverlust statt erst in der Stichprobe).
8. **V8 — Kapitel-Header-Drop (zu TECH-010):** Artefakt-Fixture mit „Spells"-Kapitel, dessen Body > 300 Zeichen Regeltext enthält ⇒ wird importiert; Stub-Variante (< 300 Zeichen) ⇒ verworfen **und** im Bericht gezählt.
9. **V9 — Liste↔Detail-Rundreise als pytest:** Für jede Options-Liste: jeder gelistete Name ist per zugehörigem `hol_*` abrufbar (heute nur im Smoke für je 1 Beispiel; als Fixture-Test verallgemeinern).
10. **V10 — Glossar-Dedupe-Vollständigkeit:** Für jede DE/EN-Options-Dublette im Bestand existiert ein exaktes Glossar-Paar (verhindert Wiederauftreten des „Boon of Fate neben Gabe des Schicksals"-Musters nach neuen Importen).

---

## 16. Offene Fragen und Annahmen

1. **Annahme Pi-Zustand:** Live-Bestand (~9.490 Einträge, 12 Quellen), funktionierender Tunnel und Allowlist wurden aus CLAUDE.md/README übernommen; diese Review hat den Pi nicht erreicht. Die lokale Dev-DB (2 Quellen) verhält sich wie dokumentiert.
2. **Annahme Anthropic-Egress:** Die Allowlist-Ranges entsprechen der im Code zitierten Doku-Seite (Stand 11.07.2026). Änderungen wirken fail-closed (Ausfall statt Öffnung) — Restfrage: Gibt es einen Prüf-Rhythmus dafür? (Empfehlung: in die M3-Monitoring-Routine aufnehmen.)
3. **Nicht bewertet (außerhalb des Auftrags):** fachliche Korrektheit der D&D-Inhalte (separater Regelwerk-Review), die rechtliche ToS-Einschätzung der DDB-Nutzung (im Projekt als bewusste Eigentümer-Entscheidung dokumentiert) sowie die inhaltliche Qualität der OCR-/Reparatur-Ergebnisse (dazu existieren projektinterne QS-Dokumente, die aus Unabhängigkeitsgründen nicht gelesen wurden).
4. **Offene Frage Client-Verhalten:** Ob Claude-Clients die Server-`instructions` durchreichen, bleibt unbeobachtbar; die Drei-Kanal-Strategie kompensiert das by design. Die manuelle Schicht-3-Abnahme (T2/T10/T12 im Chat) ist der richtige nächste Schritt und steht laut Roadmap noch aus.
5. **Offene Frage Mehrbenutzer:** Bei gleichzeitiger Nutzung durch die Runde teilen sich alle einen unauthentifizierten Endpoint — Missbrauch wäre nicht attribuierbar (kein per-User-Audit). Für <5 vertraute Personen akzeptabel; bewusst so entschieden (kein OAuth möglich).

---

## 17. Gesamturteil zur MVP-Reife

| Dimension | Note (1–10) | Begründung |
|---|---|---|
| MCP-Konformität | **8** | Sauberes Tool-Design, korrekte Streamable-HTTP-Nutzung, stateless, geprüfte Fehlerpfade; Abzug für fehlende Enums/Output-Schemas/Annotations (TECH-003) und fehlenden E2E-Protokolltest. |
| Architektur | **9** | Import/Laufzeit-Trennung, Artefaktvertrag, transaktionale Importe, getesteter Zugriffsfilter — durchgängig begründet und dokumentiert; kaum Abzüge (stringbasierte Beziehungs-Konventionen als fragilste Stelle). |
| Codequalität | **8** | Konsistent, sprechend benannt, typisiert, bemerkenswert gut kommentiert (Kommentare erklären *warum*); Abzüge: sehr lange Funktionen (`foliant_pruefe_build` ~360 Zeilen), Regex-dichte Importer-Passagen, `print`-Logging. |
| Zuverlässigkeit | **8** | Schrumpf-Schutz, Determinismus, ehrliche Fehlerpfade; Abzug für TECH-001 (falsche Negativauskunft möglich) und ungemessene Pi-Latenz (B9). |
| Sicherheit | **8** | Vorbildliches Secret-Handling, gehärteter Exporter, getestete Allowlist, FTS-Query-Härtung; Abzüge: Token in Access-Logs, keine Rate-Limits (bewusst), statische IP-Ranges. |
| Testabdeckung | **8** | ~123 Tests, Risiko-orientiert, schnell, deterministisch; Abzüge: rote `.venv-ddb`-Suite (TECH-002), Verhaltensschicht manuell, kein E2E-HTTP-/Performance-Test. |
| Dokumentation | **9** | Vollständig, ehrlich, betriebsorientiert, mit Wegweiser und Entscheidungslog; Abzug für ATTRIBUTION-Drift und kleine Zahlendrift. |
| Erweiterbarkeit | **8** | Ein Schema, Quellenregister, quellspezifische Regeln, klare Ausbaupfade; Abzüge: Handkuratierung pro Druck-Buch skaliert personell, String-Konventionen statt Beziehungen, zwei Stellen editions-hart. |
| **Allgemeine MVP-Reife** | **8** | Für den definierten Zweck (private Runde, <5 Nutzer) heute betreibbar; die verbleibende Arbeit ist klein, bekannt und größtenteils bereits in der eigenen Roadmap erfasst. |

**Kernaussage:** Foliant ist technisch geeignet, Regelwissen **korrekt, nachvollziehbar, reproduzierbar und zuverlässig** bereitzustellen — die Grounding-, Provenienz- und Versionsmechanik ist nicht nur behauptet, sondern in Schema, Tool-Ausgaben und Tests verankert. Vor der Freigabe an die Spielrunde sollten TECH-001 und TECH-002 behoben (beides klein), die Schemas gehärtet (TECH-003) und die zwei Betriebspunkte Monitoring/Off-Site-Backup (TECH-005) geschlossen werden. Nichts davon stellt Architektur oder Datenmodell infrage.

---

## Bestätigung der Unversehrtheit des Projekts

`git status` nach Abschluss der Review: einziger neuer, ungetrackter Inhalt ist `docs/reviews/` mit genau dieser Datei (`2026-07-12-review-claude-mcp-technik.md`); **keine bestehende Projektdatei wurde verändert oder gelöscht** (keine modifizierten Einträge im Status; alle Prüfläufe arbeiteten gegen temporäre Fixture-Datenbanken bzw. rein lesend gegen die lokale Dev-Datenbank).
