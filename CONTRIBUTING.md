# Mitwirken an Foliant

Danke für dein Interesse! Foliant ist ein Deutsch-first Regel-Nachschlagewerk für
D&D 5e (Fassung 2024) als self-hosted MCP-Server. Bitte lies vor dem ersten Beitrag die
vier nicht verhandelbaren Kernregeln — sie prägen fast jede Designentscheidung.

## Die vier Kernregeln

1. **Geerdet, keine Halluzination.** Antworten kommen ausschließlich aus dem importierten
   Bestand. Nichts gefunden → ehrliches „nicht gefunden", niemals aus Allgemeinwissen,
   der 2014er-Edition oder Homebrew auffüllen.
2. **Version immer.** Jeder Eintrag trägt seine Regelversion (`edition`, NOT NULL); jede
   Auskunft nennt sie. Standard ist 2024; ältere Stände werden klar gekennzeichnet.
   Editionen werden nie geraten.
3. **Deutsch-first.** Offizieller deutscher Begriff, englisches Original immer in
   Klammern dahinter; fehlt eine offizielle Übersetzung, wird eine konsistente deutsche
   Wiedergabe mit `*` markiert.
4. **Keine Spoiler, kein Scope-Creep.** Keine Abenteuer-/Kampagnenhandlung, keine Rollen,
   kein Würfeln, kein Charakter-Speichern. Der Spoiler-Schutz ist die oberste
   Verhaltensregel.

Details: `docs/foliant-anforderungen.md` (das verbindliche „Was"), `PROJEKT-UEBERSICHT.md`
(Wegweiser über alle Dokumente), `CLAUDE.md` (Betrieb, Import-Pipelines, Gotchas).

## Entwicklungsumgebung

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
make test          # pytest (Abnahme T1–T12, Smoke, Regressionen) + admin check
```

Voraussetzung: Python 3.11+ (getestet auf 3.12). Der DDB-Exporter nutzt eine zweite
Umgebung (`requirements-ddb.txt`) und ist für den öffentlichen Beitrag nicht nötig.

## Vor dem Pull Request

- **Tests grün:** `make test` (bzw. `pytest`) muss ohne Fehler durchlaufen. Neue
  Funktionalität braucht Tests; Bugfixes brauchen einen Regressionstest, der ohne den
  Fix fehlschlägt.
- **Grounding-Prinzip achten:** Neue Tool-Ausgaben nennen Quelle/Seite/Version und
  erfinden nichts. Verhaltensregeln laufen über drei Kanäle (`config/stil.py`,
  Tool-Beschreibungen, Grounding-Hinweise in den Tool-Ausgaben).
- **Stil:** Der Code ist durchgehend deutschsprachig kommentiert. Halte dich an den
  vorhandenen Stil (Namensgebung, Kommentardichte, Idiom). Ein Kommentar begründet eine
  Einschränkung, die der Code nicht selbst zeigt — kein Nacherzählen der nächsten Zeile.

## Was NICHT ins Repository gehört

- **Geheimnisse:** `.env`, Token, D&D-Beyond-Cobalt, Datenbanken (`data/`), Quell-PDFs
  (`quellen/`) — alle bereits `.gitignore`-t.
- **Kommerzielle Regelinhalte:** Aus gekauften Büchern abgeleitete Texte, Kapitelstrukturen
  oder Reparaturdaten. Die buchspezifischen Druck-Reparaturen liegen bewusst in privaten,
  `.gitignore`-ten Modulen (`importer/frhof_reparatur.py`,
  `importer/reparatur_ddb_privat.py`, `tests/test_ddb_druck_privat.py`); der öffentliche
  Code enthält als Referenz nur die SRD-5.2.1-Pipeline (CC-BY-4.0). Fehlen diese Module,
  bleibt der Server voll funktionsfähig — nur die kommerziellen Druck-Importe entfallen.

## Fehler melden

Für **Sicherheitslücken** siehe [SECURITY.md](SECURITY.md) (privater Meldeweg). Für
Bugs und Ideen nutze die Issue-Vorlagen. Bitte keine urheberrechtlich geschützten
Regeltexte in Issues zitieren.
