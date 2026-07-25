# Foliant — Einstieg für Claude Code

Foliant ist ein self-hosted MCP-Server: **Regel-Nachschlagewerk für D&D 5e (Fassung 2024),
Deutsch-first**, plus ein Charakterbogen-Übersetzer als zweiter Dienst. **MVP komplett und
live** auf dem Pi (`pi@<pi-host>`, `~/foliant`).

**Die Dokumentation besteht aus genau vier Dateien. Halte es dabei — nichts Neues anlegen:**

| Datei | Wofür | Wann lesen |
|---|---|---|
| **`SPEC.md`** | das verbindliche „Was": Anforderungen, Sprach-/Versionsregeln, Verhalten, Abnahme | bei **jeder fachlichen Frage** zuerst |
| **`CONCEPT.md`** | das „Wie": Architektur, Datenmodell, Pipelines, Betrieb, Entscheidungen, Gotchas | vor jeder technischen Änderung |
| **`BACKLOG.md`** | was offen ist, Abnahme-Checkliste, erledigte Chronik | vor jeder Planung |
| **`README.md`** | Einstieg, Schnellstart, Nutzung, Recht | selten |

Historisches (erledigte Aufträge, Review-Volltexte, abgelöste Statusberichte) steht **nur in
der Git-Historie**. Die SYN-IDs aus Code-Kommentaren löst `CONCEPT.md` §14 auf.

## Die vier nicht verhandelbaren Regeln (Details: SPEC.md §7)

1. **Geerdet, keine Halluzination.** Antworten NUR aus dem Bestand. Nichts gefunden → ehrlich
   „nicht gefunden". Kein Auffüllen aus Allgemeinwissen, 2014 oder Homebrew.
2. **Version immer.** Jeder Eintrag trägt seine Regelversion, jede Auskunft nennt sie;
   Standard 2024. `edition` ist NOT NULL. **Editionen werden NIE geraten** — unklar heißt:
   nicht importieren.
3. **Deutsch-first.** Offizieller deutscher Begriff, Englisch IMMER in Klammern; fehlt
   offizielles Deutsch → markierte Wiedergabe mit `*`. Deutsche Quellen haben Vorrang.
4. **Keine Spoiler, kein Scope-Creep.** Keine Abenteuer-/Kampagneninhalte, keine Rollen, kein
   Würfeln, kein Charakter-Speichern. **Spoiler-Schutz ist die oberste Verhaltensregel.**

Die Verhaltensregeln laufen über drei Kanäle: `config/stil.py`, die Tool-Beschreibungen und —
am zuverlässigsten — die **Grounding-Hinweise in den Tool-Ausgaben**. Das Copy-Paste-Duplikat
für Davids Claude-Projekt steht in `SPEC.md` §8; **bei Änderungen beide synchron halten.**

## Was am teuersten schiefgeht (voll: CONCEPT.md §12)

- **Nach jeder Code-Änderung auf dem Pi: `docker compose up -d --build foliant`.** Der Code
  ist ins Image gebacken; ohne Rebuild läuft still der alte Stand weiter und meldet „Erfolg".
- **Einzelne Dienste nur mit `--no-deps` bauen** — sonst startet `depends_on` den Live-MCP durch.
- **`make test` ist das EINE Gate**, aber die lokale Dev-DB ist oft nur ein SUBSET → bei
  korpusabhängigen Fällen trügerisch grün. Nach jedem Deploy / srd-de-Re-Import zusätzlich
  **`make test-golden-pi PI=pi@<host>`**.
- **`rsync` aufs Pi nie mit `--delete` und nie mit `data/`** — die Mac-DB würde den vollen
  Bestand überschreiben, gitignorierte Privatmodule verschwänden.
- **Davids Smarthome-Tunnel auf dem Pi NIE anfassen.**

## Arbeitsweise in diesem Repo

- **Nie direkt auf `main`** — ein Branch pro Arbeitsthema, PR erst wenn das Thema fertig ist,
  niemals selbst mergen.
- Code, Commits und Branch-Namen auf Englisch; **Kommentare und Doku auf Deutsch**. Ein
  Kommentar begründet eine Einschränkung, die der Code nicht selbst zeigt.
- Der Branch `archiv-privat-vor-veroeffentlichung` ist der einzige Git-Stand der privaten
  Druck-Reparatur-Module und wurde nie gepusht — **nicht löschen**.
