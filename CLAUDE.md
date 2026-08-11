# Foliant — Einstieg für Claude Code

Foliant ist ein self-hosted MCP-Server: **Regel-Nachschlagewerk für D&D 5e (Fassung 2024),
Deutsch-first**, plus ein Charakterbogen-Übersetzer als zweiter Dienst. **MVP komplett und
live** auf dem Pi (SSH-Ziel: `PI=` in der `.env`; Verzeichnis `~/foliant`).

**Die Dokumentation besteht aus genau vier Dateien. Halte es dabei — nichts Neues anlegen:**

| Datei | Wofür | Wann lesen |
|---|---|---|
| **`SPEC.md`** | das verbindliche „Was": Anforderungen, Sprach-/Versionsregeln, Verhalten, Abnahme | bei **jeder fachlichen Frage** zuerst |
| **`CONCEPT.md`** | das „Wie": Architektur, Datenmodell, Pipelines, Betrieb, Entscheidungen, Gotchas | vor jeder technischen Änderung |
| **`BACKLOG.md`** | was offen ist, Abnahme-Checkliste, Rest-Posten | vor jeder Planung |
| **`README.md`** | Einstieg, Schnellstart, Nutzung, Recht | selten |

Historisches (erledigte Aufträge, Review-Volltexte, abgelöste Statusberichte) steht **nur in
der Git-Historie**. Die SYN-IDs aus Code-Kommentaren löst `CONCEPT.md` §14 auf.

**Die Doku wird mitgetestet** — `tests/test_doku_pflege.py`, Teil von `make test`. Sechs
Prüfungen: §-Verweise treffen ein Kapitel · die Stand-Angabe ist nicht älter als der jüngste
im Text genannte Vorgang · jede SPEC-Anforderung hat einen Status im BACKLOG · genannte
Dateien existieren · kein wortgleicher Absatz in zwei Dateien · es bleiben genau vier
Doku-Dateien. Vier Regeln beim Schreiben, an denen die Trennung schon zweimal erodiert ist:

1. **SPEC nennt keine Modul-, Spalten- oder Funktionsnamen.** Was etwas *können muss*, steht
   dort; *wie* es gebaut ist, in `CONCEPT.md` — mit Verweis statt Wiederholung.
2. **BACKLOG führt nur Offenes.** Erledigtes geht ins Entscheidungsregister (`CONCEPT.md`
   §10), zu den Gotchas (§12) oder in die Git-Historie — nicht als ✅-Zeile stehen bleiben.
3. **Kapitelnummern sind kein stabiler Anker.** Auf Regeln mit ihrer ID verweisen (S4, V9,
   B11), nicht mit „§5" — Nummern verschieben sich, IDs nie.
4. **Jede Passage trägt die heute geltende Regel plus höchstens einen Begründungssatz** —
   außerhalb von `CONCEPT.md` §10, §12 und §14. Verlauf, Messreihen und Vorher/Nachher
   gehören ins Entscheidungsregister oder in die Git-Historie. Redigiert wird beim
   Anfassen: wer eine Passage ändert, kürzt ihren Changelog gleich mit weg.

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
für Davids Claude-Projekt steht in `config/projektanweisung.md` (Wegweiser: `SPEC.md` §8);
**bei Änderungen beide synchron halten** — `tests/test_verhaltensregeln.py` prüft das.

## Was am teuersten schiefgeht (voll: CONCEPT.md §12)

- **Nach jeder Code-Änderung auf dem Pi: `docker compose up -d --build foliant`.** Der Code
  ist ins Image gebacken; ohne Rebuild läuft still der alte Stand weiter und meldet „Erfolg".
- **Einzelne Dienste nur mit `--no-deps` bauen** — sonst startet `depends_on` den Live-MCP durch.
- **`make test` ist das EINE Gate**, aber die lokale Dev-DB ist oft nur ein SUBSET → bei
  korpusabhängigen Fällen trügerisch grün. Nach jedem Deploy / srd-de-Re-Import zusätzlich
  **`make test-golden-pi`**.
- **`rsync` aufs Pi nie mit `--delete` und nie mit `data/`** — die Mac-DB würde den vollen
  Bestand überschreiben, gitignorierte Privatmodule verschwänden.
- **Facetten nie über einen Re-Import nachziehen**, sondern mit
  `admin import --quelle facetten`. Ein Re-Import spielt die rohen OCR-Namen wieder ein und
  macht die Namensreparatur der 2014-Scans zunichte.
- **Davids Smarthome-Tunnel auf dem Pi NIE anfassen.**

## Arbeitsweise in diesem Repo

- **Nie direkt auf `main`** — ein Branch pro Arbeitsthema, PR erst wenn das Thema fertig ist,
  niemals selbst mergen.
- **Bezeichner, Kommentare und Doku auf Deutsch; Branch- und Commit-Namen auf Englisch.**
  Ein Kommentar begründet eine Einschränkung, die der Code nicht selbst zeigt. Zu den
  begründeten Ausnahmen (ddb_exporter-Module, `seed_*`, `cmd_<cli-name>`): `CONCEPT.md` §10.
- Der Branch `archiv-privat-vor-veroeffentlichung` hält den Repo-Stand vor der
  Veröffentlichung und wurde nie gepusht — **nicht löschen**.
- ⚠️ **Die privaten Druck-Reparatur-Module haben NIRGENDS einen Git-Stand.**
  `importer/frhof_reparatur.py` und `importer/reparatur_ddb_privat.py` sind gitignored, und
  der Archiv-Branch enthält sie **nicht** (am 28.07.2026 mit `git ls-tree` geprüft — bis
  dahin behauptete diese Datei das Gegenteil). Jede Änderung daran ist unwiderruflich:
  **vorher sichern.** Eine Sicherung liegt in `data/private/module-sicherung-2026-07-28/`.
