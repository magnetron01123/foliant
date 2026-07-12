# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier festgehalten.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/);
das Projekt folgt keiner festen Versionskadenz (self-hosted, nah an `main`).

## [Unreleased]

### Hinzugefügt
- Öffentliche Projektvorbereitung: MIT-`LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, Issue-/PR-Vorlagen und GitHub-Actions-CI (`pytest` auf
  Python 3.11 & 3.12).

### Geändert
- Aus kommerziellen Druck-Büchern abgeleitete Import-Reparaturen (efota/frhof) in private,
  `.gitignore`-te Module ausgelagert (`importer/reparatur_ddb_privat.py`,
  `importer/frhof_reparatur.py`, `tests/test_ddb_druck_privat.py`). Der öffentliche Code
  enthält als Referenz nur die SRD-5.2.1-Pipeline (CC-BY-4.0) und bleibt ohne die privaten
  Module voll funktionsfähig.
- Betreiber-spezifische Angaben (Pi-Host) in der Dokumentation anonymisiert.

## Stand vor der Veröffentlichung (MVP, 2026-07)

- MCP-Server (FastMCP, Streamable HTTP) mit 16 read-only Tools für Regelfragen,
  Steckbriefe (Zauber/Monster/Gegenstände/Spezies/Klassen/Hintergründe/Talente),
  Begriffsübersetzung (DE↔EN-Glossar) und Build-Prüfung.
- Deutsch-first, geerdet auf importierten Bestand mit Quelle/Seite/Version; ehrliches
  „nicht gefunden" statt Halluzination; Spoiler-Schutz als oberste Verhaltensregel.
- Import-Pipelines: born-digital-PDF (dt. SRD 5.2.1), Open5e-API, gescannte PDFs
  (OCR-Vorstufe), Browser-Druck-PDFs; SQLite + FTS5, Editionen NOT NULL,
  Quellen-Prioritäten für Dubletten.
- Zugriffsschutz: geheimer Pfad-Token + IP-Allowlist, Read-only-DB, Fail-fast in
  Produktion, Eingabegrenzen.
- Umgesetzte Review-Runde (2026-07-12): Tool-Vertrag (stabile `eintrag_id`, Enums,
  Konfliktausweis), Fuzzy-/Exakt-Trennung im Glossar, kontextbewusste Dubletten,
  Schema-Constraints, Golden-Regressionssuite gegen den echten Bestand.

[Unreleased]: https://github.com/magnetron01123/foliant/commits/main
