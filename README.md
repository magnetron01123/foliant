# Foliant für D&D

[![CI](https://github.com/magnetron01123/foliant/actions/workflows/ci.yml/badge.svg)](https://github.com/magnetron01123/foliant/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)

Self-hosted MCP-Server als **Regel-Nachschlagewerk für D&D 5e (Fassung 2024)**, Deutsch-first
— kurz: **Foliant**. Beantwortet Regelfragen (Kampf + außerhalb), liefert Steckbriefe und
unterstützt die Charaktererstellung — geerdet auf importierte Quellen, mit Quelle, Seite und
Regelversion, in korrektem Spieldeutsch (englischer Begriff in Klammern, `*` wenn keine
offizielle Übersetzung existiert).

Daneben läuft der **Charakterbogen-Übersetzer**: ein englischer D&D-Beyond-PDF-Export wird zum
ausgefüllten offiziellen deutschen WotC-Bogen 2024, druckbar.

## Der Kern in drei Sätzen

1. **Geerdet:** Foliant antwortet nur aus dem importierten Bestand; findet es nichts, sagt es
   das — statt zu erfinden. Websuche nur als klar gekennzeichneter Fallback, niemals Spoiler.
2. **Deutsch-first:** offizielle deutsche Begriffe, englisches Original in Klammern, `*` wenn
   keine offizielle Übersetzung existiert.
3. **Version immer:** aktuelle Regeln (2024) als Standard; ältere Stände klar gekennzeichnet.

## Stand (29.07.2026)

**MVP komplett und live** auf einem Raspberry Pi 4: ~12 500 Einträge aus 15 Quellen (dt. SRD
5.2.1, drei deutsche 2014-Bücher, Open5e, D&D-Beyond-Bücher), 6 Tools, Zugang über geheimen
Pfad + IP-Allowlist, Datenbank-QS abgeschlossen. Der Charakterbogen-Übersetzer läuft als
eigener Container daneben, der Discord-Bot ebenso. Maßgeblich ist immer `admin status`.
Was noch offen ist: [BACKLOG.md](BACKLOG.md).

## Dokumentation — vier Dateien, mehr nicht

| Datei | Enthält |
|---|---|
| **[SPEC.md](SPEC.md)** | Das verbindliche **„Was"**: Anforderungen, Sprach- und Versionsregeln, Verhalten, Abnahmekriterien (die Projektanweisung selbst steht in [`config/projektanweisung.md`](config/projektanweisung.md)) |
| **[CONCEPT.md](CONCEPT.md)** | Das **„Wie"**: Architektur, Datenmodell, Import-Pipelines, Betrieb und Deployment, Entscheidungen, Fallen, Sicherheitsmodell |
| **[BACKLOG.md](BACKLOG.md)** | Was **offen** ist: Phasen mit Gates, Abnahme-Checkliste, Rest-Posten, Ausbaustufen |
| **README.md** | Diese Datei: Einstieg, Schnellstart, Nutzung, Recht |

`CLAUDE.md` ist kein fünftes Dokument, sondern der Einstiegspunkt für Claude Code — er
verweist nur auf die vier oben.

## Aufbau des Repositorys

```
app/         FastMCP-Server, Tools, Zugriffsschutz, Admin-CLI, Charakterbogen-Übersetzer
importer/    PDF · OCR · Markdown · Glossar · Open5e · DDB
db/          Schema + Init          config/   Verhaltensregeln + Config-Vorlage
tests/       Abnahme (T1–T12), Smoke, Golden-Suite am echten Bestand
deploy/      Caddyfile              .github/  CI
```

## Schnellstart (Entwicklung am Mac)

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
python db/init_db.py data/foliant.sqlite
cp config/foliant.example.toml config/foliant.toml    # Quellen/Pfade eintragen
python -m app.admin import --quelle srd-de            # bzw. open5e-srd-2024, glossar
make test                                             # das EINE Gate
.venv/bin/uvicorn app.server:app --port 8000          # GET /ready == 200
```

Der MCP-Endpoint liegt lokal unter `http://localhost:8000/mcp` (Dev ohne Geheimpfad).
### Foliant in Discord

Auf dem Server der Runde: **`/regel <frage>`** eingeben oder **@Foliant** erwähnen — die
Antwort öffnet einen Thread, in dem Nachfragen mit Gesprächskontext möglich sind — auch
nach einem Server-Neustart, denn der Bot liest den Thread dann aus der Discord-Historie
zurück. Wer nur für sich nachschlagen möchte, nimmt **`/regel-privat <frage>`**: die
Antwort sieht dann niemand sonst, dafür gibt es keinen Thread für Nachfragen. Es gilt ein
gemeinsames Tageslimit als Kostendeckel.
Einrichtung (einmalig, Betreiber): [CONCEPT.md](CONCEPT.md) §9 „Discord-Bot einrichten".

Betrieb, Deployment und die Import-Wege im Detail: [CONCEPT.md](CONCEPT.md) §8–9.

## Nutzung

### Foliant im Claude-Chat
Custom Connector mit der **vollen URL inkl. Geheimpfad** hinzufügen —
`https://<host>/<token>/mcp`, kein OAuth. Einrichten am Desktop; benutzen geht danach auch aus
der Mobile-App. Für konsistentes Verhalten die **Projektanweisung** in ein Claude-Projekt
einfügen — sie steht kopierbereit auf der Charakterbogen-Website im Abschnitt „Foliant im
Claude-Chat“ (der gemeinsame Ort für alle Mitspieler; Quelle ist
[`config/projektanweisung.md`](config/projektanweisung.md)).

### Charakterbogen-Übersetzer — Kurzanleitung für die Runde

Ihr habt euren Charakter in **D&D Beyond**, aber der Bogen ist auf Englisch? Auf der Seite
macht ihr daraus in etwa einer Minute einen **deutschen Charakterbogen** auf der offiziellen
deutschen WotC-Vorlage (2024) — fertig zum Ausdrucken.

1. **Anmelden.** Es gibt nur ein Feld: das **Kennwort**. Kein Benutzername, keine
   Registrierung. Danach bleibt ihr **30 Tage angemeldet**.
2. **Bei D&D Beyond exportieren.** Charakter öffnen → *Character Sheet → Print/Export* → als
   **englisches** PDF speichern.
3. **PDF hochladen**, etwa eine Minute warten, **herunterladen.** Das war's.

**Häufige Fragen**
- *Was passiert mit meinen Daten?* Nichts wird gespeichert. Das PDF wird nur im
  Arbeitsspeicher verarbeitet; nach dem Download ist alles weg.
- *Funktioniert ein deutscher DDB-Export?* Nein — nur **englische** Exporte.
- *Warum hat mein Bogen plötzlich mehr Seiten?* Passt der Inhalt nicht auf die zwei Seiten der
  Vorlage, kommt automatisch eine Anhang-Seite dazu. Es geht nichts verloren.
- *Was bedeutet das Sternchen?* Zum Beispiel „Angriffe abwehren\* (Deflect Attacks)": Für
  diesen Begriff gibt es (noch) **keine offizielle deutsche Fassung** — das ist eine sinngemäße
  Übersetzung, das Original steht in Klammern. Begriffe **ohne** Sternchen sind die
  **amtlichen** Bezeichnungen.
- *„Gerade belegt"?* Es läuft immer nur **eine** Konvertierung gleichzeitig. Kurz warten.

**Eine Bitte:** Behaltet URL und Kennwort in der Runde — bitte nicht weitergeben. Danke! 🎲

## Öffentlicher Code, private Inhalte

Dieses Repository enthält den **Quellcode** und die **SRD-5.2.1-Import-Pipeline** (CC-BY-4.0)
als vollständiges Referenzbeispiel. Es enthält **keine** kommerziellen Regelinhalte. Die aus
gekauften Druck-Büchern abgeleiteten Import-Reparaturen liegen bewusst in privaten,
gitignorierten Modulen (`importer/frhof_reparatur.py`, `importer/reparatur_ddb_privat.py`,
`tests/test_ddb_druck_privat.py`). Ohne sie bleibt der Server voll funktionsfähig — nur die
kommerziellen Druck-Importe entfallen, die zugehörigen Tests überspringen sich selbst.

## Mitwirken

Vor dem ersten Beitrag bitte die **vier nicht verhandelbaren Kernregeln** in
[SPEC.md](SPEC.md) §7 lesen — sie prägen fast jede Designentscheidung. Für Pull Requests gilt:
`make test` muss grün sein, neue Funktionalität braucht Tests, Bugfixes brauchen einen
Regressionstest, der ohne den Fix fehlschlägt. Der Code ist durchgehend deutschsprachig
kommentiert; halte dich an den vorhandenen Stil. Details: [CONCEPT.md](CONCEPT.md) §11.

**Nicht ins Repository gehören:** Geheimnisse (`.env`, Token, DDB-Cobalt), Datenbanken
(`data/`), Quell-PDFs (`quellen/`) — alle bereits gitignored — und kommerzielle Regelinhalte.
Bitte auch keine urheberrechtlich geschützten Regeltexte in Issues zitieren.

**Sicherheitslücken** bitte **nicht** über öffentliche Issues melden, sondern über die private
„Report a vulnerability"-Funktion (GitHub → *Security* → *Advisories*). Das Sicherheitsmodell
steht in [CONCEPT.md](CONCEPT.md) §13.

Umgangston: freundlich, respektvoll, sachlich — im Zweifel gilt der
[Contributor Covenant](https://www.contributor-covenant.org/de/version/2/1/code_of_conduct.html).

## Lizenz & Recht

- **Code:** MIT — siehe [LICENSE](LICENSE).
- **SRD 5.2.1:** Dieses Projekt nutzt Material aus dem **System Reference Document 5.2.1**
  („SRD 5.2.1") von Wizards of the Coast LLC, verfügbar unter https://www.dndbeyond.com/srd.
  Das SRD 5.2.1 steht unter der **Creative Commons Attribution 4.0 International License**
  (https://creativecommons.org/licenses/by/4.0/legalcode).
- **Open5e** (`api.open5e.com`): OGL 1.0a (srd-2014) bzw. CC-BY-4.0 (srd-2024); Attribution
  gemäß den jeweiligen Open5e-Dokumenten.
- **Offizielle Errata** (PHB/DMG/MM): von Wizards of the Coast frei zum Herunterladen
  angeboten, aber **nicht** frei lizenziert — „frei verteilt" ist keine offene Lizenz. Sie
  werden wie die Kaufbücher behandelt (nicht mitgeliefert, nur für den Eigenbedarf) und
  tragen deshalb `lizenz = "WotC (frei verteilt, keine offene Lizenz)"`. Der Präfix
  `CC-BY` wird bewusst vermieden: er löst in der Ausgabe automatisch die SRD-Attribution
  aus, und die wäre hier eine falsche Rechtsaussage.
- **Deutsche Begriffe** u. a. über dnddeutsch.de (Ulisses-Terminologie).
- **Kommerzielle D&D-Bücher** (z. B. via D&D Beyond) sind urheberrechtlich geschützt, werden
  nicht mitgeliefert und nur privat, rechtmäßig erworben und zum Eigenbedarf verarbeitet
  (`lizenz = "privat"`, `herkunft = "ddb"` an jedem Eintrag). Sie werden der eigenen Spielrunde
  über einen zugangsgeschützten Endpoint bereitgestellt — bewusste, protokollierte
  Eigentümer-Entscheidung ([SPEC.md](SPEC.md) §12.1). Eine Weitergabe über die Runde hinaus
  findet nicht statt.
