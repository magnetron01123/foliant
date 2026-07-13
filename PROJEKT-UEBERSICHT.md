# Foliant — Projektübersicht

**Stand: 11.07.2026 · MVP komplett und live** (Pi, ~9490 Einträge aus 12 Quellen, 17 Tools,
Zugang über Geheimpfad + IP-Allowlist). Weg zu echten Nutzern: `docs/MVP-ABGLEICH-UND-ROADMAP.md`.

Dieser Wegweiser fasst zusammen, was Foliant ist, wo das Projekt steht und **welches Dokument
wofür da ist**.

## Was ist Foliant?
Ein privat betriebener MCP-Server, der Claude zum **deutschsprachigen Regel-Nachschlagewerk für
D&D 5e (Fassung 2024)** macht: Regeln nachschlagen (Kampf + außerhalb), Steckbriefe (Zauber/
Monster/Gegenstände) und Unterstützung bei der Charaktererstellung. Antworten in korrektem
Spieldeutsch, geerdet auf importierte Quellen, mit Quelle und Regelversion. Läuft self-hosted
(Raspberry Pi 4), genutzt über den Claude-Client.

## Aktueller Stand
- **MVP-Funktionsumfang erfüllt** (Abgleich mit Anforderungen Rev. 8 → Roadmap-Dokument).
- **Bestand:** dt. SRD 5.2.1, Open5e (srd-2024), 8 DDB-Bücher (Editionen autoritativ) und
  2 DDB-Druck-Bücher (Eberron: Forge of the Artificer, FR: Heroes of Faerûn) — letztere mit
  Kreuz-Audit + Sichtprüfung qualitätsgesichert. Datenbank-QS abgeschlossen.
- **Zugang privat:** Geheimpfad + Anthropic-IP-Allowlist (M3-Zugang erledigt).
- **Verhalten gehärtet:** Prioritätsleiter (Bestand > alles), Websuche nur gekennzeichnet,
  Spoiler-Schutz oberste Regel, einheitliches Format-/Emoji-Schema.
- **Offen bis Gruppennutzung:** M2 Schicht 3 (Davids 3-Fragen-Checkliste), M3-Betrieb
  (Monitoring + Off-Site-Backup), M4 (Spieler-Anleitung), M1 (dt. Bücher, wartet auf PDFs),
  O4 (Feedback-Meldeweg), Cobalt-Rotation (David).

## Alle Dokumente

**Konvention:** kleingeschriebene `foliant-*`-Dateien = zeitlose Grundlagen (das „Was"/„Wie");
GROSSGESCHRIEBENE Dateien = lebende Status-/Betriebsdokumente; `docs/archiv/` = historisch.

| Datei | Sicht | Zweck |
|---|---|---|
| `PROJEKT-UEBERSICHT.md` | — | dieser Wegweiser |
| `docs/foliant-anforderungen.md` | **fachlich** | verbindlicher Anforderungskatalog (Rev. 8) |
| `docs/foliant-technisches-konzept.md` | **technisch** | Architektur, Datenmodell, Pipeline, Entscheidungen |
| `docs/foliant-mcp-best-practices.md` | technisch | Best Practices aus bestehenden D&D-MCP-Servern |
| `CLAUDE.md` | technisch | operative Anleitung für Claude Code (Betrieb, Pipelines, Gotchas) |
| `docs/MVP-ABGLEICH-UND-ROADMAP.md` | **Status/Plan** | Ist vs. Anforderungen + Roadmap bis zu echten Nutzern |
| `docs/QS-BERICHT-datenbank.md` | Status | Datenbank-QS/QC inkl. Tiefen-Audit der Druck-Bücher |
| `docs/ABNAHME-PROTOKOLL.md` | Status | MVP-Abnahme §14 (Schicht 1+2 ✅, Schicht 3 = Checkliste) |
| `docs/DEPLOY-raspberry-pi.md` | Betrieb | Deployment, Zugangsschutz, OCR-Vorstufe, Betrieb |
| `docs/DDB-IMPORT-anleitung.md` | Betrieb | DDB-Buchimport (Exporter + Offline-Import) |
| `docs/CLAUDE-PROJEKT-ANWEISUNG.md` | Betrieb | Copy-Paste-Anweisung für Davids Claude-Projekt |
| `docs/ddb-architektur-entscheidung.md` | technisch | ADR: gewählte DDB-Import-Architektur |
| `docs/ATTRIBUTION.md` | — | Lizenzen/Attribution (SRD CC-BY, Open5e) |
| `db/schema.sql` | technisch | SQLite-Schema (getestet) |
| `README.md` | — | Kurzüberblick + Schnellstart |
| `docs/archiv/` | historisch | erledigte Arbeitsaufträge + überholte Entwürfe |

## Wie alles zusammenhängt
**Anforderungen** (das „Was") → **Technisches Konzept** (das „Wie") → **CLAUDE.md** (Umsetzung
und Betrieb durch Claude Code) → **Roadmap/Status-Dokumente** (wo wir stehen). Best Practices
und Attribution sind Referenz.

## Der Kern in drei Sätzen
1. **Geerdet:** Foliant antwortet nur aus dem importierten Bestand; findet es nichts, sagt es
   das — statt zu erfinden. Websuche nur als klar gekennzeichneter Fallback, niemals Spoiler.
2. **Deutsch-first:** offizielle deutsche Begriffe, englisches Original in Klammern, `*` wenn
   keine offizielle Übersetzung existiert.
3. **Version immer:** aktuelle Regeln (2024) als Standard; ältere Stände klar gekennzeichnet.

## Nächste Schritte
1. David: Claude-Projekt anlegen (`docs/CLAUDE-PROJEKT-ANWEISUNG.md`) → dann die
   3-Fragen-Abnahme (`docs/ABNAHME-PROTOKOLL.md`, Schicht 3).
2. M3-Betrieb: Uptime-Monitoring + Off-Site-Backup der Datenbank.
3. M4: spielerfeste Kurzanleitung für die Runde.
