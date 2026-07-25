# SYN-Befunde — Kurzregister (Review-Runde 12.07.2026)

Am 12.07.2026 haben vier unabhängige Reviews (Claude + Codex, je Technik und D&D-Regeln)
den damaligen Stand geprüft; eine Synthese konsolidierte die Funde zu den **SYN-IDs**.
Diese IDs stehen bis heute als Begründung in Code-Kommentaren und Testnamen — dieses
Register hält fest, **wofür jede ID steht**, damit die Verweise auflösbar bleiben.

**Umsetzungsstand:** P0, P1 und die lokalen P2-Befunde sind umgesetzt und getestet
(Commit `4043b27`, „Synthese-Umsetzung: alle P0/P1 + lokale P2-Befunde"). P3 sind bewusste
Ausbaustufen nach dem MVP. Die vollständigen Review- und Synthese-Texte liegen in der
Git-Historie (`docs/archiv/reviews/` vor dem Aufräum-Commit).

## P0 — blockierten die Rundennutzung (alle umgesetzt)

| ID | Befund |
|---|---|
| SYN-P0-001 | Fuzzy-Glossartreffer wurden als exakte Identität behandelt („Aktionen" → „Reaktionen"). Fix: `match=exakt\|fuzzy` getrennt. |
| SYN-P0-002 | Klammer-Suffixe + Editions-Fallback lieferten 2014 statt der vorhandenen 2024-Regel (Zustände). Fix: Suffix-Aliasse, Edition vor Fallback. |
| SYN-P0-003 | Namensbasierte Deduplizierung verschluckte Varianten → unvollständige Steckbriefe. Fix: kontextbewusste Identität + `weitere_abschnitte`. |
| SYN-P0-004 | Beschädigte/verschmolzene srd-de-Chunks (Zweihändig+Umstoßen, Zauber-Fragmente, Statblock-Zellrisse, ToC-Blob). Fix: kuratiertes `_srd_de_reparatur`-Paket. |
| SYN-P0-005 | Build-Prüfung erteilte falsche Legalitätsbestätigungen. Fix: Pflichtwahlen/Talent-Stufen prüfen, Label `keine_verstoesse_gefunden`. |
| SYN-P0-006 | Ungültige `kategorie`/`quelle`-Parameter erzeugten ein falsches „nichts im Bestand". Fix: Whitelist-Validierung mit eigenem Fehlerpfad. |
| SYN-P0-007 | Playtest-/Abenteuer-/Setting-Inhalte ohne Kennzeichnung. Fix: Playtest-Skip + `inhaltsart` bis in die Tool-Ausgaben (Spoiler-Hinweis). |

## P1 — vor externen Nutzertests (alle umgesetzt)

| ID | Befund |
|---|---|
| SYN-P1-001 | Keine semantische QS; DDB-Suite verdeckt rot. Fix: `make test` über beide venvs + **Golden-Suite am echten Bestand**. |
| SYN-P1-002 | Kein stabiler Suche→Detail-Rundlauf. Fix: stabile `eintrag_id` in Treffern, Detailabruf per ID. |
| SYN-P1-003 | Tool-Schemas ohne Enums/Bounds/Fehlersemantik. Fix: `Literal`-Enums, Grenzen, `readOnlyHint`, diskriminierte Ergebnisformen. |
| SYN-P1-004 | Zugangskontrolle fail-open bei leerem Token; Token im Klartext in Logs. Fix: Fail-fast ab Mindestlänge, `--no-access-log`, Pfad-Redaktion. |
| SYN-P1-005 | Serving-Container sah `data/private` beschreibbar. Fix: read-only Serve ohne Privat-Mount; DDB-Import als Einmal-Container. |
| SYN-P1-006 | Glossar-/Auffindbarkeitslücken bei 2024-Kernbegriffen und Synonymen. Fix: kuratierte Kernpaare + Ranking-Korrektur. |
| SYN-P1-007 | Aussagearten (Regeltext / Ableitung / SL-Entscheid) nicht getrennt. Fix: Disziplin in `config/stil.py`, ⚖️-Kennzeichnung. |
| SYN-P1-008 | Open5e-Formatter verwarf regelentscheidende Felder (Reaktionstrigger, Recharge, Form). Fix: Felder durchgereicht. |
| SYN-P1-009 | Echte Quellkonflikte gleicher Edition wurden still per Priorität entschieden. Fix: sichtbarer Konfliktausweis. |
| SYN-P1-010 | srd-de-Textpolitur: Laufkopf in 374, Wortrisse in 273 Einträgen, 8 Namens-Garbles. Fix: im Reparaturpaket mit P0-004. |
| SYN-P1-011 | Kein Readiness-Check, kein Monitoring/Off-Site-Backup, keine Modell-Evals. Fix: `/ready`, Backup-Weg, Eval-Checkliste. |
| SYN-P1-012 | Reproduzierbarkeit: offene Pins, fehlendes Korpus-Manifest, Doku-Drift. Fix: exakte Pins, `admin manifest`, Doku-Konsolidierung. |

## P2 — umgesetzt, soweit lokal wirksam

| ID | Befund |
|---|---|
| SYN-P2-001 | Editions-/Statusmodell: „unterstützt" ≠ „vorhanden", `5.5e`-Alias, Statusdimension. |
| SYN-P2-002 | Wissensmodell-Ausbau (`concept`/`variant`/`relation`, Revisions-Provenienz) — **bewusst nach dem MVP**. |
| SYN-P2-003 | Regelwerte streng belegen (Point-Buy-Kostentabelle statt Annahme). |
| SYN-P2-004 | Grenzen/DoS: Längen-/Antwortlimits, Glossar-Cache statt Vollscan je Aufruf. |
| SYN-P2-005 | Charakterführung: Herkunft umfasst zwei Sprachen + Spezies-Pflichtwahlen. |
| SYN-P2-006 | Doku-Drift: **ein** kanonisches Betriebs-Runbook, der Rest verweist darauf (`docs/RUNBOOK.md`). |
| SYN-P2-007 | Ausgabegrenzen/Lizenzdisziplin für private Quellen. |
| SYN-P2-008 | Entwickler-Agentenrechte: breite `python/curl/ssh/docker`-Allows eingedampft (`.claude/settings.json`). |
| SYN-P2-009 | `*_meta`-Tabellen + Filter-Tools, CHECK-Constraints und Schema-Version (`user_version`). |

## P3 — bewusste Ausbaustufen (offen, nicht rundenblockierend)

| ID | Befund |
|---|---|
| SYN-P3-001 | Strukturelle Rollen-/Spoiler-Isolation (getrennte Korpora und Zugänge, A3). |
| SYN-P3-002 | Regelbeziehungsgraph/Interaktionskatalog (`exception_to`, `overrides`, Trigger/Dauer/Stapelung). |
| SYN-P3-003 | Errata-/Revisionstracking + Autoritätsklassen für offizielle Klarstellungen. |
| SYN-P3-004 | Hausregeln-/Optionale-Regeln-Overlay mit sichtbarer Überlagerung (A4). |
