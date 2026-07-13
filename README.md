# Foliant für D&D

[![CI](https://github.com/magnetron01123/foliant/actions/workflows/ci.yml/badge.svg)](https://github.com/magnetron01123/foliant/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)

Self-hosted MCP-Server als **Regel-Nachschlagewerk für D&D 5e (Fassung 2024)**, Deutsch-first —
kurz: **Foliant**.
Beantwortet Regelfragen (Kampf + außerhalb), liefert Steckbriefe und unterstützt die
Charaktererstellung — geerdet auf importierte Quellen, mit Quelle/Seite/Version und korrektem
Spieldeutsch (englischer Begriff in Klammern, `*` wenn keine offizielle Übersetzung).

## Aufbau
- `PROJEKT-UEBERSICHT.md` — **Wegweiser** über alle Dokumente (dort starten).
- `docs/foliant-anforderungen.md` — verbindliche Anforderungen (das „Was", Rev. 8).
- `CLAUDE.md` — operative Anleitung für Claude Code (Betrieb, Pipelines, Gotchas).
- `app/` — FastMCP-Server, Tools, Zugriffsschutz, Admin-CLI. `importer/` — PDF/OCR/
  Markdown/Glossar/Open5e/DDB. `db/` — Schema + Init. `config/` — Verhaltensregeln +
  Config-Vorlage. `tests/` — Abnahme (T1–T12), Smoke, Regressionen. `docs/archiv/` — historisch.

## Stand (11.07.2026)
**MVP komplett und live** auf dem Raspberry Pi: ~9490 Einträge aus 12 Quellen
(dt. SRD 5.2.1, Open5e, 10 D&D-Beyond-Bücher), 17 Tools, Zugang über Geheimpfad +
IP-Allowlist, Datenbank-QS abgeschlossen. Offene Schritte bis zur Gruppennutzung:
`docs/MVP-ABGLEICH-UND-ROADMAP.md`.

## Schnellstart Entwicklung (am Mac)
1. `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
2. `python db/init_db.py data/foliant.sqlite`
3. `cp config/foliant.example.toml config/foliant.toml` und Quellen/Pfade eintragen.
4. Importieren: `python -m app.admin import --quelle srd-de` (bzw. `open5e-srd-2024`,
   `glossar`); prüfen mit **`make test`** (= pytest beider venvs + `admin check` +
   Smoke + Golden-Suite gegen den echten Bestand).
5. Server lokal: `.venv/bin/uvicorn app.server:app --port 8000` → `GET /ready` = 200,
   MCP-Endpoint unter `http://localhost:8000/mcp` (Dev ohne Geheimpfad).

Betrieb/Deployment (Pi, Docker, Tunnel, Zugangsschutz, OCR-Vorstufe, DDB-Import):
`docs/DEPLOY-raspberry-pi.md` und `docs/DDB-IMPORT-anleitung.md`.

## Öffentlicher Code, private Inhalte
Dieses Repository enthält den **Quellcode** und die **SRD-5.2.1-Import-Pipeline** (CC-BY-4.0)
als vollständiges Referenzbeispiel. Es enthält **keine** kommerziellen Regelinhalte. Die aus
gekauften Druck-Büchern abgeleiteten Import-Reparaturen liegen bewusst in privaten,
`.gitignore`-ten Modulen (`importer/frhof_reparatur.py`, `importer/reparatur_ddb_privat.py`,
`tests/test_ddb_druck_privat.py`). Ohne sie bleibt der Server voll funktionsfähig — nur die
kommerziellen Druck-Importe entfallen (die zugehörigen Tests überspringen sich selbst).

## Mitwirken
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — Setup, Tests, die vier Kernregeln.
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — Verhaltenskodex.
- [`SECURITY.md`](SECURITY.md) — Sicherheitsmodell und privater Meldeweg.

## Lizenz & Recht
- **Code:** MIT — siehe [`LICENSE`](LICENSE).
- **SRD 5.2.1** (deutsch/englisch) und **Open5e-Daten:** CC-BY-4.0, siehe
  [`docs/ATTRIBUTION.md`](docs/ATTRIBUTION.md).
- **Kommerzielle D&D-Bücher** (z. B. via D&D Beyond) sind urheberrechtlich geschützt, werden
  nicht mitgeliefert und nur privat/rechtmäßig erworben zum Eigenbedarf verarbeitet.
