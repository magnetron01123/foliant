# Foliant — Projektübersicht

**Stand: 25.07.2026 · MVP komplett und live** (Raspberry Pi, ~9490 Einträge aus 12 Quellen,
16 Tools, Zugang über Geheimpfad + IP-Allowlist). Daneben live: der **Charakterbogen-
Übersetzer** (`dnd.magnetron.me`, eigene Website neben dem MCP). Was bis zur Gruppennutzung
fehlt: `docs/ROADMAP.md`.

Dieser Wegweiser fasst zusammen, was Foliant ist, wo das Projekt steht und **welches Dokument
wofür da ist**.

## Was ist Foliant?
Ein privat betriebener MCP-Server, der Claude zum **deutschsprachigen Regel-Nachschlagewerk für
D&D 5e (Fassung 2024)** macht: Regeln nachschlagen (Kampf + außerhalb), Steckbriefe (Zauber/
Monster/Gegenstände) und Unterstützung bei der Charaktererstellung. Antworten in korrektem
Spieldeutsch, geerdet auf importierte Quellen, mit Quelle und Regelversion. Läuft self-hosted
(Raspberry Pi 4), genutzt über den Claude-Client. Daneben liefert der **Charakterbogen-
Übersetzer** englische D&D-Beyond-PDF-Exporte fertig übersetzt auf den offiziellen deutschen
WotC-Bogen 2024 aus (eigene Website, gleicher Pi, eigener Container).

## Aktueller Stand
- **MVP-Funktionsumfang erfüllt** (Abgleich mit Anforderungen Rev. 8 → `docs/ROADMAP.md`).
- **Bestand:** dt. SRD 5.2.1, Open5e (srd-2024), 8 DDB-Bücher (Editionen autoritativ) und
  2 DDB-Druck-Bücher (Eberron: Forge of the Artificer, FR: Heroes of Faerûn) — letztere mit
  Kreuz-Audit + Sichtprüfung qualitätsgesichert. Datenbank-QS abgeschlossen.
- **Zugang privat:** Geheimpfad + Anthropic-IP-Allowlist.
- **Verhalten gehärtet:** Prioritätsleiter (Bestand > alles), Websuche nur gekennzeichnet,
  Spoiler-Schutz oberste Regel, einheitliches Format-/Emoji-Schema.
- **Charakterbogen-Übersetzer live:** zweistufige Übersetzung, deterministische Listen,
  amtliche 2024-Begriffe aus dem eigenen Bestand, nachfragegetriebenes Glossar-Nachschlagen,
  Kennwortschutz.
- **Offen bis Gruppennutzung:** M2 Schicht 3 (3-Fragen-Checkliste), M3-Betrieb (Monitoring +
  Off-Site-Spiegel), M4 (Connector-Anleitung für die Runde), M1 (dt. Bücher, wartet auf PDFs),
  O4 (Feedback-Meldeweg) — Details in `docs/ROADMAP.md`.

## Alle Dokumente

**Konvention:** kleingeschriebene `foliant-*`-Dateien = zeitlose Grundlagen (das „Was"/„Wie");
GROSSGESCHRIEBENE Dateien = lebende Status-/Betriebsdokumente.

| Datei | Sicht | Zweck |
|---|---|---|
| `PROJEKT-UEBERSICHT.md` | — | dieser Wegweiser |
| `README.md` | — | Kurzüberblick + Schnellstart |
| `CLAUDE.md` | technisch | operative Anleitung für Claude Code (Betrieb, Pipelines, Gotchas) |
| `CHANGELOG.md` | — | nennenswerte Änderungen |
| **Grundlagen** | | |
| `docs/foliant-anforderungen.md` | **fachlich** | verbindlicher Anforderungskatalog (Rev. 8) |
| `docs/foliant-technisches-konzept.md` | **technisch** | Architektur, Datenmodell, Pipeline, Entscheidungen (inkl. ADR DDB-Import) |
| `docs/syn-befunde-register.md` | technisch | Kurzregister der SYN-IDs aus der Review-Runde 12.07.2026 |
| `db/schema.sql` | technisch | SQLite-Schema (getestet) |
| **Betrieb** | | |
| `docs/RUNBOOK.md` | **Betrieb** | kanonischer Weg von Null bis „Runde nutzt es" |
| `docs/DEPLOY-raspberry-pi.md` | Betrieb | Deployment, Zugangsschutz, Importe (PDF/OCR/DDB), laufender Betrieb |
| `docs/CLAUDE-PROJEKT-ANWEISUNG.md` | Betrieb | Copy-Paste-Anweisung für Davids Claude-Projekt |
| **Status & Plan** | | |
| `docs/ROADMAP.md` | **Status/Plan** | Ist vs. Anforderungen, offene Phasen, bekannte Rest-Posten |
| `docs/ABNAHME-UND-EVAL.md` | Status | MVP-Abnahme §14 (T1–T12) + Verhaltens-Checkliste für den Chat |
| **Charakterbogen-Übersetzer** | | |
| `docs/CHARAKTERBOGEN-MVP.md` | **technisch** | Pipeline, Module, Entwurfsregeln, Deployment |
| `docs/CHARAKTERBOGEN-ANLEITUNG-RUNDE.md` | Spieler | Kurzanleitung für die Runde (Upload → fertiger dt. Bogen) |
| **Recht & Mitwirken** | | |
| `docs/ATTRIBUTION.md` | — | Lizenzen/Attribution (SRD CC-BY, Open5e, DDB privat) |
| `CONTRIBUTING.md` · `CODE_OF_CONDUCT.md` · `SECURITY.md` | — | Beitrag, Verhaltenskodex, Sicherheitsmodell |

> **Historisches** (erledigte Arbeitsaufträge, Review-Volltexte, abgelöste Statusberichte)
> steht **nur noch in der Git-Historie**. Einstieg: `git log --diff-filter=D --name-only`
> bzw. der Aufräum-Commit „Doku konsolidiert". Die SYN-IDs aus den Reviews bleiben über
> `docs/syn-befunde-register.md` auflösbar.

## Wie alles zusammenhängt
**Anforderungen** (das „Was") → **Technisches Konzept** (das „Wie") → **CLAUDE.md** (Umsetzung
und Betrieb durch Claude Code) → **RUNBOOK/DEPLOY** (der Weg in den Betrieb) →
**ROADMAP/ABNAHME** (wo wir stehen).

## Der Kern in drei Sätzen
1. **Geerdet:** Foliant antwortet nur aus dem importierten Bestand; findet es nichts, sagt es
   das — statt zu erfinden. Websuche nur als klar gekennzeichneter Fallback, niemals Spoiler.
2. **Deutsch-first:** offizielle deutsche Begriffe, englisches Original in Klammern, `*` wenn
   keine offizielle Übersetzung existiert.
3. **Version immer:** aktuelle Regeln (2024) als Standard; ältere Stände klar gekennzeichnet.

## Nächste Schritte
1. David: Claude-Projekt anlegen (`docs/CLAUDE-PROJEKT-ANWEISUNG.md`) → dann die
   3-Fragen-Abnahme (`docs/ABNAHME-UND-EVAL.md`, Schicht 3).
2. M3-Betrieb: Uptime-Monitoring + Off-Site-Spiegel der Backups.
3. M4: spielerfeste Connector-Kurzanleitung für die Runde.
