# Gesamtsynthese der Einzelreviews: Foliant (Claude + Codex)

## 1. Metadaten der Synthese

| Feld | Wert |
|---|---|
| Synthese erstellt von | claude |
| Datum | 2026-07-12 |
| Untersuchter Git-Commit | `5cc67289a8066ce83b3a62aa9822165b1acfacbb` („Projekt-Aufraeumen: Archiv, Doku-Refresh, Konventionen") |
| Untersuchter Branch | `main` |

**Einbezogene Review-Dateien (alle vom 2026-07-12, je genau eine Version — keine Datumskonflikte):**

1. `docs/reviews/2026-07-12-review-claude-mcp-technik.md` (Technikreview Claude, Befunde `TECH-001…015` — hier zitiert als **claude TECH-…**)
2. `docs/reviews/2026-07-12-review-claude-dnd-regeln.md` (Fachreview Claude, Befunde `DND-001…014` — hier **claude DND-…**)
3. `docs/reviews/2026-07-12-review-codex-mcp-technik.md` (Technikreview Codex, Befunde `TECH-001…021` — hier **codex TECH-…**)
4. `docs/reviews/2026-07-12-review-codex-dnd-regeln.md` (Fachreview Codex, Befunde `DND-001…018` — hier **codex DND-…**)

**Ausgeschlossene Review-Dateien:** keine (der Ordner enthielt zum Synthesezeitpunkt genau die vier Einzelreviews). **Fehlende erwartete Reviews:** keine — alle vier Perspektiven liegen vor.

**Zur Verifikation untersuchte Projektbestandteile:** `app/tools/nachschlagen.py`, `app/tools/charakter.py`, `app/db.py`, `app/glossar.py`, `importer/import_open5e.py`, `importer/ddb_exporter/katalog.py`, `db/schema.sql`, `docker-compose.yml`, `.dockerignore`, `.claude/settings.json`, `config/foliant.example.toml` sowie die lokale öffentliche Datenbank `data/foliant.sqlite` (rein lesend über die Projekt-Tools bzw. `mode=ro`).

**Ausgeführte Prüfkommandos (alle lokal, nicht destruktiv):**
- Laufzeitproben über die echten Tools: `foliant_uebersetze_begriff("Aktionen")`, `foliant_hol_regel("Aktionen")`, `foliant_hol_monster("Solar")`, `foliant_hol_zauber("Eissturm"/"Göttliche Gunst"/"Symbol"/"Counterspell")`, `foliant_hol_monster("Vampirbrut")`, `foliant_hol_gegenstand("Schild")`, Quellen-Rundlauf mit `quelle="open5e-srd-2024"` vs. Treffer-Titel, vier `foliant_pruefe_build`-Konstellationen.
- Read-only-SQL gegen `data/foliant.sqlite` (Open5e-Counterspell-Rohtext, Vampir-Einträge DE/EN).
- Synthetische Fixture-DB im Scratchpad (Schema + 2 Quellen + Glossarzeile) zur Reproduktion des 2014-Fallback-Mechanismus von codex DND-001.
- `git status --porcelain` vor und nach der Synthese.

**Nicht mögliche Prüfungen:** Eine Kopie/Abfrage der **privaten** Datenbank `data/private/foliant-private.sqlite` wurde durch die lokalen Berechtigungsregeln des Projekts verweigert (Deny auf `.sqlite`-Zugriffe; das Duplizieren der privaten DB wäre eine Umgehung gewesen). Codex-Aussagen, die ausschließlich auf dem privaten Bestand beruhen (z. B. Bodies > 50.000 Zeichen; 807 Ravenloft-Einträge), sind daher als *plausibel, nicht in der Synthese re-verifiziert* gekennzeichnet; der zugrunde liegende **Mechanismus** wurde, wo möglich, synthetisch bzw. am Code verifiziert. Ebenfalls nicht geprüft: Pi-Live-Betrieb, echter Claude-Connector-E2E, Docker-Build.

---

## 2. Executive Summary

Vier unabhängige Reviews — je eine technische und eine fachliche von Claude und Codex — zeichnen ein konsistentes Doppelbild: **Das Fundament ist ungewöhnlich gut, der Antwortpfad ist noch nicht vertrauenswürdig.**

Unstrittig und mehrfach bestätigt sind die Stärken: saubere Editionstrennung 2024/2014 im Datenmodell (Pflichtfeld, autoritative Zuordnung, kein stilles Mischen), durchgängige Belegzeilen (Quelle · Seite · Version), verlustsichere Importe, ein vorbildlich gehärteter DDB-Exporter, Grounding-Hinweise direkt in den Tool-Ausgaben und eine breite, schnelle Testsuite.

Die entscheidende Erkenntnis der Synthese: **Codex hat mit systematischen Antwortpfad-Proben eine Fehlerklasse nachgewiesen, die Claude in beiden Reviews unterschätzt hat — und diese Befunde wurden in der Synthese unabhängig verifiziert.** Konkret bestätigt: (1) „Aktionen" wird über die Fuzzy-Glossar-Brücke als offizielle Übersetzung „Reaktionen (Reactions)" ausgegeben und der Detailabruf liefert den falschen Regeltext mit Beleg; (2) der Monsterabruf „Solar" liefert ein Statblock-Fragment ohne RK/TP; (3) mehrere Zauber-/Gegenstands-Steckbriefe sind objektiv beschädigt (Eissturm 131 Zeichen, Göttliche Gunst mit Fremdsatz, Vampirbrut enthält Angriffe des Unsichtbaren Pirschers, Schild ohne +2 RK); (4) die Build-Prüfung bestätigt vier klar unvollständige/illegale Builds als `legal_soweit_pruefbar`; (5) der von Codex als kritisch gemeldete 2014-Fallback bei klammerlosen Zustandsnamen („Erschöpfung" → englischer 2014-Eintrag „Exhaustion" trotz vorhandener 2024-Regel) wurde per synthetischer Fixture reproduziert — er trifft genau die Bestandskonstellation des Pi (2024 + Basic Rules 2014). Claude hatte dieselbe Wurzel (Klammer-Suffixe brechen Exakt-Treffer) gefunden, aber nur die harmlose Ausprägung gesehen; beide Reviews konvergieren zudem unabhängig auf den Topple/„Zweihändig"-Verschmelzungsfund.

Daraus ergeben sich **7 konsolidierte P0-Befunde**, die eine fachlich vertretbare Nutzung durch die Spielrunde derzeit blockieren — alle lokalisierbar, keiner stellt Architektur oder Datenmodell grundsätzlich infrage. Die auffälligen Notendifferenzen (Claude Ø ~8, Codex Ø ~4–5) erklären sich fast vollständig durch (a) die unterschiedliche Prüftiefe am Antwortpfad und (b) unterschiedliche Bewertungsmaßstäbe (privater Eigenbetrieb vs. Freigabe an Dritte auf serviertem Kaufinhalt); nach Verifikation folgt die Synthese bei Zuverlässigkeit/fachlicher Reife weitgehend Codex, bei Architektur-/Code-/Import-Substanz weitgehend Claude.

**Gesamturteil der Synthese:** Für den Eigenbetrieb des Betreibers nutzbar, **nicht bereit für externe Nutzertests** (die eigene Spielrunde eingeschlossen), bis das P0-Paket umgesetzt ist. Das P0-Paket ist klar umrissen (Retrieval-Identität, Suffix-Aliasse, Chunk-Reparaturen, Build-Ehrlichkeit, Parametervalidierung, Scope-Kennzeichnung, fachliche Golden-Tests) und überwiegend klein bis mittelgroß.

---

## 3. Einbezogene Einzelreviews

| Review | Reviewer | Typ | Umfang | Methodik-Schwerpunkt |
|---|---|---|---|---|
| `…claude-mcp-technik.md` | Claude | MCP/Technik | 15 Befunde (1 Hoch, 4 Mittel, Rest Niedrig/Hinweis), Noten 8–9 | Vollständige Code-Lektüre, Schema-Introspektion, MCP-In-Memory-Client, Fehlerpfad-Sonden, Latenzmessung |
| `…claude-dnd-regeln.md` | Claude | D&D-Fachreview | 14 Befunde (3 Hoch), 28 Testfragen, Noten 7–9 | Inhalts-Stichproben der 2024-Kernregeln, Daten-Scans (Laufköpfe/Wortrisse/Namens-Garbles), Glossarproben |
| `…codex-mcp-technik.md` | Codex | MCP/Technik | 21 Befunde (7 Hoch), 20 Testempfehlungen, Noten 4–7 | Antwortpfad-Rundläufe, Negativproben, Vertrauensgrenzen-Analyse (Auth/Container/Logs), Schema-Introspektion |
| `…codex-dnd-regeln.md` | Codex | D&D-Fachreview | 18 Befunde (3 Kritisch, 9 Hoch), 44 Testfragen, Noten 3–7 | Systematische Realbestands-Antwortpfadprüfung inkl. privater Kandidaten-DB, Formatterproben, Build-Negativtests |

Beide Reviewer arbeiteten am selben Commit, führten dieselbe Kernsuite aus (98 passed/5 skipped; `.venv-ddb`: 24 passed/1 failed) und kamen bei Testresultaten, Bestandszahlen und Architekturbeschreibung zu identischen Fakten — die Differenzen liegen in Prüftiefe und Maßstab, nicht in widersprüchlichen Messungen.

## 4. Fehlende oder ausgeschlossene Reviews

Keine. Alle vier erwarteten Einzelreviews liegen in genau einer, datumsgleichen Version vor; ältere Versionen, Synthese-Dateien oder Fremdreviews existieren nicht im Ordner.

---

## 5. Gemeinsames Gesamturteil

1. **Konzept und Fundament tragen.** Alle vier Reviews bestätigen: Selbst-gehostetes, offline servierendes SQLite/FTS5-Nachschlagewerk mit Editionspflicht, Quellenpräzedenz und Belegzeilen ist der richtige Ansatz; kein Review fordert einen Technologiewechsel (ausdrücklich: kein Vektorstore nötig).
2. **Die kritische Schwäche liegt im letzten Meter:** Namensbasierte Identität (Dedupe, Exakt-Match, Fuzzy-Glossar) entscheidet, *welcher* Chunk eine Frage beantwortet — und genau dort entstehen nachweislich falsche, aber belegt wirkende Antworten. Das ist gefährlicher als ehrliches Nichtwissen und konterkariert das wichtigste Projektziel (B1-Ehrlichkeit).
3. **Datenqualität der Hauptquelle ist stellenweise beschädigt** (PDF-Extraktionsschäden bis hin zu regelverfälschenden Verschmelzungen); die vorhandene QS prüft Struktur, nicht Semantik.
4. **Scope-Versprechen (keine Abenteuer/Playtest-Inhalte) ist nicht technisch durchgesetzt** — nur durch Modellinstruktion und Quellentitel.
5. **Für den Ein-Personen-Betrieb des Eigentümers ist der Dienst heute brauchbar**; für die Runde (externe Nutzer, servierte Kaufinhalte) fehlen die P0-Fixes plus minimale Zugangs-/Betriebs-Härtung.

---

## 6. Von mehreren Reviewern bestätigte Stärken

Unabhängig von mindestens zwei Reviews (meist allen vier) bestätigt:

1. **Editionsdisziplin:** `edition` als Pflichtfeld, autoritative Editionszuordnung (DDB-Buch-DB, Pflichtangabe bei PDFs, Dokument-Key bei Open5e), Standard 2024, getrennte `aeltere_staende`/`andere_fassungen`, kein stilles Mischen. (claude Technik/DnD; codex Technik §5, DnD §9 „formale Basis besser als bei vielen Regelassistenten")
2. **Provenienz und Attribution:** Quelle · Seite · Version in jeder Detailantwort, Lizenz je Eintrag, CC-BY-Attribution automatisch. (alle vier)
3. **Grounding als Ausgabeeigenschaft:** explizite „Nichts im Bestand — nicht aus Allgemeinwissen antworten"-Hinweise, Mehrdeutigkeits-Kandidaten, Altstands-Warnungen. (alle vier)
4. **Import-Robustheit:** Transaktionen, Schrumpf-Schutz, Pagination-Härtung, OCR-Guardrails, atomare DDB-Aktivierung mit Backup-Rotation. (beide Technikreviews)
5. **DDB-Exporter-Härtung:** Secret nur Datei/Keychain/TTY, secret-freie Fehlermeldungen, kurzlebiger Container ohne DB-Zugriff, ZIP-Slip-/Zip-Bomb-Schutz. (beide Technikreviews, wortgleich im Urteil „besser gehärtet als für ein MVP üblich")
6. **Korrekte 2024-Kerntexte im SRD-Bestand:** Vorteil/Nachteil, Gelegenheitsangriff (2024-Auslöserkatalog), Zustände inkl. Erschöpfung neu, Konzentration, Verstecken-Aktion (SG 15/Unsichtbar), Rasten, Deckung, Feuerball-Werte, Punktkauf/Standardsatz, Hintergrund-Mechanik (+2/+1, Max 20), Meisterschafts-Einzelregeln (Stoßen/Plagen/Auslaugen/Verlangsamen). (beide Fachreviews, disjunkte Stichprobenmengen — starkes Signal)
7. **Sichere SQL-/FTS-Basis:** Parameterbindung, FTS5-Operator-Quoting, Verbindung pro Aufruf, Nicht-Root-Container, Loopback-Port. (beide Technikreviews)
8. **Test- und Dokumentationskultur** deutlich über MVP-Üblichem — mit dem gemeinsamen Vorbehalt, dass die Tests Semantik nicht abdecken (siehe SYN-P1-001) und die Doku Statusdrift enthält (SYN-P1-012/P2-006).

---

## 7. Konsolidierte P0-Befunde

> P0 = blockiert eine fachlich vertretbare Nutzung (falsche, aber belegt wirkende Antworten möglich).

### SYN-P0-001 — Fuzzy-Glossartreffer werden als exakte Identität behandelt („Aktionen" → „Reaktionen")

| Feld | Inhalt |
|---|---|
| Priorität / Kategorie | P0 · technisch mit unmittelbar fachlicher Wirkung (Retrieval/Terminologie) |
| Bereich | `app/glossar.py` (`lookup`, Fuzzy ohne Matchtyp), `app/db.py` (`_glossar_alternativen`), `app/tools/nachschlagen.py` (`_hole_detail`: Glossar-Alternativen zählen als exakt) |
| Ursprüngliche Befunde | codex TECH-001 (Hoch), codex DND-002 (Kritisch, Teilaspekt) |
| Reviewer | Codex; Claude: nicht gefunden (Gegenprobe der Synthese bestätigt Codex) |
| Beleglage | **Einzelbefund, Verifiziert** — Synthese reproduziert: `uebersetze_begriff("Aktionen")` → „Reaktionen (Reactions)" mit `offiziell=true`; `hol_regel("Aktionen")` → Monster-„Reaktionen"-Eintrag S. 299 |
| Beschreibung | `fuzz.ratio("Aktionen","Reaktionen") ≥ 88` macht den Fuzzy-Glossartreffer zur Namensalternative; nachgelagerte Pfade (Detail-Exaktwahl, kanonische Anzeige, Dedupe-Varianten) unterscheiden nicht mehr zwischen exakter und unscharfer Beziehung. |
| Auswirkung | Falsche, offiziell und belegt wirkende Auskunft zu einem Kernbegriff der Aktionsökonomie; dieselbe Mechanik kann weitere Wortpaare treffen. Gefährlichste Antwortklasse des Systems. |
| Maßnahme | Glossar-`lookup` liefert Matchtyp (+Score); exakte kuratierte Beziehungen und Fuzzy-Vorschläge als getrennte Typen; `_glossar_alternativen`/`_hole_detail`/Anzeige/Dedupe nutzen ausschließlich exakte Beziehungen; Fuzzy nur als gekennzeichneter Kandidat mit Rückfrage. |
| Abnahmekriterium | `uebersetze_begriff("Aktionen")` liefert keinen Reaktionen-Begriff als offiziell; `hol_regel("Aktionen")` liefert die Aktions-Regel oder ehrliche Kandidaten; Regressionstest „Aktionen/Action/Reaktionen/Reactions bleiben getrennt" grün. |
| Abhängigkeiten | keine; SYN-P0-003 profitiert |
| Größe | **S–M** |

### SYN-P0-002 — Klammer-Suffixe + Editions-Fallback liefern 2014 statt vorhandener 2024-Regel (Zustände)

| Feld | Inhalt |
|---|---|
| Priorität / Kategorie | P0 · technisch/fachlich (Regelversionen) |
| Bereich | `app/tools/nachschlagen.py` (`_eintrag_namen` kennt keine Klammer-Suffixe; `_hole_detail`-B5-Fallback greift vor Suffix-Auflösung); Bestandsnamen „… (Zustand)/(Aktion)/(Gefahr)" |
| Ursprüngliche Befunde | codex DND-001 (**Kritisch**), claude DND-007 (Mittel — gleiche Wurzel, nur harmlose Ausprägung beobachtet) |
| Reviewer | beide (unterschiedlich schwer bewertet) |
| Beleglage | **Teilweiser Konsens, Verifiziert** — Synthese reproduziert per synthetischer Fixture (2024 „Erschöpfung (Zustand)" + 2014 „Exhaustion" + Glossarzeile): `hol_regel("Erschöpfung")` → **Edition 2014, „Exhaustion"**, mit Altstands-Hinweis „keine 2024-Fassung". Exakt die Pi-Konstellation (Basic Rules 2014 geladen). |
| Beschreibung | Der klammerlose Nutzerbegriff matcht den 2024-Eintrag nicht exakt, wohl aber (via Glossar) den englischen 2014-Eintrag; der B5-Fallback wählt ihn und behauptet, es gebe keine 2024-Fassung. Im rein-2024-Bestand zeigt sich nur die milde Variante (Mehrdeutigkeits-Rückfrage — Claudes Beobachtung); im gemischten Bestand die kritische. Betroffen: alle 15 Zustände plus „(Aktion)"-/„(Gefahr)"-Einträge. |
| Auswirkung | Inhaltlich falsche Regelversion mit Beleg — z. B. 2014-Erschöpfungstabelle statt 2024-Kumulativ-Malus. Direkter Bruch des Kernversprechens V2/B5/T5. |
| Maßnahme | Klammerzusatz als exakte Namensvariante führen („Erschöpfung (Zustand)" ⇒ auch „erschöpfung"), in `_eintrag_namen` **und** Dedupe/Optionslogik; Auflösungsreihenfolge: erst semantische 2024-Kandidaten, dann Altstand-Fallback; Test gegen gemischten Fixture-Bestand. |
| Abnahmekriterium | Für alle 15 Zustände liefert der klammerlose deutsche Name bei Standard-Edition den 2024-Eintrag; 2014 erscheint nur auf explizite Anfrage oder bei echtem Fehlen; Fixture-Regressionstest (2024+2014 gemischt) grün. |
| Abhängigkeiten | unabhängig von SYN-P0-001, gleiche Codestelle — gemeinsam umsetzen |
| Größe | **S–M** |

### SYN-P0-003 — Namensbasierte Deduplizierung/Detailwahl verschluckt Varianten → unvollständige oder fachfremde „vollständige" Steckbriefe

| Feld | Inhalt |
|---|---|
| Priorität / Kategorie | P0 · technisch mit fachlicher Wirkung (Identität/Vollständigkeit) |
| Bereich | `app/db.py` (`_dedupe_und_sortiere`: Identität = Name+Edition+Kategorie, ohne Kontext/Inhalt), `_hole_detail` (erster Exakt-Kandidat gewinnt) |
| Ursprüngliche Befunde | codex TECH-002 (Hoch), codex DND-002 (Kritisch — „Aktionen/Bonusaktionen/Reaktionen/Temp-TP/Todesrettungswurf/Bewegungsrate" liefern Monster-Kurztexte/Verweise statt Spielerregeln) |
| Reviewer | Codex; Claude: nicht gefunden |
| Beleglage | **Einzelbefund, Verifiziert** — Synthese reproduziert `hol_monster("Solar")`: 1.322 Zeichen, beginnt bei „Magieresistenz/Aktionen", ohne RK/TP (Statblock-Kopf liegt im zweiten gleichnamigen Chunk und wird weggeduped). Die weiteren codex-Beispiele (Temp-TP 235 statt 1.742 Zeichen etc.) wurden nicht einzeln nachgemessen, folgen aber demselben verifizierten Mechanismus. |
| Beschreibung | Gleichnamige Chunks derselben Edition/Kategorie — auch **innerhalb einer Quelle** (Statblock über Seitengrenze, Glossar-Kurzverweis vs. Kernkapitel, Monster-Wertekasten-Erklärungen vs. Spielerregeln) — gelten als eine Dublette; die Prioritäts-/Rangwahl bestimmt still einen Text. |
| Auswirkung | Das als „vollständig" beschriebene Detail-Tool liefert Fragmente oder beantwortet eine andere Frage; zentrale Ausnahmen (Temp-TP-Nichtstapeln, Todesretter-Details) fehlen unbemerkt. |
| Maßnahme | Identität um Kontext (Breadcrumb) und Inhaltsnähe erweitern: nur zusammenfassen, wenn Kontext gleich oder Inhalt (Hash/Ähnlichkeit) übereinstimmt; sonst echte Kandidaten (`mehrdeutig`) oder deterministische Aggregation zusammengehöriger Teil-Chunks (Statblock-Kopf + Fortsetzung); Suchtreffer um stabile `eintrag_id` ergänzen, Detailabruf per ID erlauben (vgl. SYN-P1-002). |
| Abnahmekriterium | `hol_monster("Solar")` enthält RK, TP, Bewegung und Aktionen; „Bonusaktionen/Reaktionen/Temporäre Trefferpunkte/Todesrettungswurf" liefern den jeweiligen Spielerregel-Kernabschnitt oder transparente Kandidaten; Golden-Tests je Fall grün. |
| Abhängigkeiten | Wirkt mit SYN-P0-004 (Reparatur zerteilter Statblöcke reduziert Fälle) |
| Größe | **M–L** |

### SYN-P0-004 — Beschädigte/verschmolzene srd-de-Chunks: regelverfälschende Importschäden in der kanonischen Quelle

| Feld | Inhalt |
|---|---|
| Priorität / Kategorie | P0 · Datenqualität mit direkter Regelverfälschung |
| Bereich | Bestand `srd-de`; Ursache `importer/import_markdown.py` (Heading-Verluste, Spalten-/Seitenreihenfolge, fehlende BEREINIGUNG) |
| Ursprüngliche Befunde | claude DND-001 (Hoch: Topple in „Zweihändig", Topple-Eintrag fehlt), claude DND-004 (Statblock-Zellrisse), claude DND-009/010 (Namens-Garbles, ToC-Blob); codex DND-003 (**Kritisch**: Eissturm/Göttliche Gunst/Symbol/Windwall abgeschnitten bzw. mit Fremdtext, Vampirbrut = Pirscher-Fragment, Schild ohne RK-Bonus), codex DND-004 (Hoch: „Attributswurf" mit Beeinflussen-SG kontaminiert, „Zweihändig"+„Umstoßen"), codex TECH-018 (QS erkennt Semantikschäden nicht) |
| Reviewer | **beide unabhängig**, mit überlappenden und sich ergänzenden Fallmengen (Topple/„Zweihändig" von beiden gefunden; Codex nennt den korrekten deutschen Namen „Umstoßen") |
| Beleglage | **Konsens, Verifiziert** — Synthese bestätigt zusätzlich: Eissturm 131 Z., Göttliche Gunst 124 Z. mit Fremdsatz (Planar-Text), Symbol 131 Z., Vampirbrut 625 Z. mit Kontext „> Unsichtbarer Pirscher", Schild-Gegenstand 156 Z. ohne „+2" |
| Beschreibung | Mehrere Schadensklassen: (a) verlorene Überschriften verschmelzen fremde Regeln (Zweihändig+Umstoßen; Attributswurf+Beeinflussen-SG); (b) Zauber-Chunks abgeschnitten/kreuzkontaminiert; (c) Statblock-Kopftabellen mit Zellrissen (Werte korrekt, Struktur kaputt); (d) Namens-Garbles (8 Fälle) und ein 22-kB-Inhaltsverzeichnis als Regel-Eintrag; (e) Laufkopf/Wortrisse (siehe SYN-P1-010, dort P1 weil nicht regelverfälschend). |
| Auswirkung | Der Bestand „belegt" falsche Regeln (jede Zweihandwaffe wirft um; genereller Mindest-SG 15; Vampirbrut mit Pirscher-Angriffen; Göttliche Gunst mit fremdem Schlusssatz — dort zusätzlich Konzentrations-Versionsrisiko). Quellenpriorität verstärkt den Schaden: der kaputte deutsche Chunk gewinnt gegen die vollständige englische Fassung (codex DND-011-Mechanik). |
| Maßnahme | Kuratiertes Reparaturpaket für `srd-de` (BEREINIGUNG/SPLIT wie beim efota/frhof-Muster): verlorene Headings einsetzen (Umstoßen/Topple u. a.), betroffene Kapitel neu chunken, Statblock-Kopf normalisieren, ToC-Kopf verwerfen, 8 Namens-Fixes; danach Re-Import + **fachliche Golden-Gates** (Pflichtklauseln/verbotene Fremdklauseln je benanntem Eintrag, siehe SYN-P1-001). |
| Abnahmekriterium | Alle in beiden Reviews benannten Einträge (Umstoßen als eigener Eintrag; Zweihändig ohne Rettungswurf; Eissturm/Göttliche Gunst/Symbol/Windwall vollständig; Vampirbrut mit eigenem Statblock RK 16/TP 90; Schild mit +2 RK; Attributswurf ohne Beeinflussen-SG; alle 8 Meisterschaften einzeln abrufbar) bestehen Golden-Tests; `admin check --strict`-Stufe schlägt bei Wiederauftreten an. |
| Abhängigkeiten | Golden-Gates aus SYN-P1-001; unabhängig von P0-001/002/003 parallelisierbar |
| Größe | **L** |

### SYN-P0-005 — Build-Prüfung erteilt falsche Legalitätsbestätigungen

| Feld | Inhalt |
|---|---|
| Priorität / Kategorie | P0 · fachlich (Charaktererschaffung) |
| Bereich | `app/tools/charakter.py` (`foliant_pruefe_build`: fehlende Pflichtwahlen nicht in `fehlende_angaben`; Talent-Existenz ⇒ `ok`; Waffennamen ungeprüft) |
| Ursprüngliche Befunde | codex DND-005 (Hoch); claude: Gegenposition (Stärke „ehrliche Grenzen", T9-Tests) — Widerspruch, siehe Kap. 16 |
| Reviewer | Codex; Claude bewertete denselben Code positiv (andere Testfälle) |
| Beleglage | **Einzelbefund, Verifiziert** — Synthese reproduziert alle vier Fälle: (1) ohne `hintergrund_erhoehungen` ⇒ `legal_soweit_pruefbar`, `fehlende_angaben=[]`; (2) Kämpfer Stufe 3 ohne Unterklasse ⇒ kein Unterklassen-Befund, `legal_soweit_pruefbar`; (3) Stufe 1 + „Gabe des Schicksals" ⇒ Talent `ok`; (4) Waffenbeherrschungen „Kartoffel/Teekanne/Mondstrahl" ⇒ `ok`. |
| Beschreibung | Die Prüfung validiert nur Übergebenes; das *Fehlen* von Pflichtwahlen (Hintergrund-Erhöhungen; Unterklasse ab der Tabellen-Stufe) erzeugt weder `unvollstaendig` noch einen Befund. Talent-Voraussetzungen und Waffenexistenz sind laut `grenzen` unscharf deklariert, gehen aber als Status `ok` in ein positives Gesamtlabel ein. |
| Auswirkung | Eine als automatische Regelprüfung beworbene Funktion (F3/T9) bestätigt eindeutig regelwidrige/unfertige Builds; Claudes Stärken-Befund (Beleg-/Grenzen-Transparenz) bleibt wahr, schützt aber nicht vor dem irreführenden Top-Label. |
| Maßnahme | Pflichtwahlen aus Klasse/Stufe/Hintergrund ableiten (Unterklasse ab Tabellen-Stufe; Erhöhungen bei angegebenem Hintergrund) und in `fehlende_angaben`/`unvollstaendig` führen; Talente ohne Voraussetzungsprüfung als `nicht_pruefbar` statt `ok`; Waffenbeherrschungen gegen den Waffen-Bestand auflösen oder `nicht_pruefbar`; `legal_soweit_pruefbar` nur, wenn kein Pflichtbereich offen ist. |
| Abnahmekriterium | Keiner der vier reproduzierten Builds erhält `legal_soweit_pruefbar`; T9-Suite um genau diese vier Negativfälle erweitert und grün. |
| Abhängigkeiten | keine |
| Größe | **M** |

### SYN-P0-006 — Ungültige `kategorie`/`quelle`-Parameter erzeugen falsches „Nichts im Bestand" samt Ehrlichkeits-Anweisung

| Feld | Inhalt |
|---|---|
| Priorität / Kategorie | P0 · technisch mit fachlicher Wirkung (Auskunftsehrlichkeit) |
| Bereich | `app/tools/nachschlagen.py` (`foliant_suche_regeln`), `app/db.py` (Filter ohne Validierung) |
| Ursprüngliche Befunde | claude TECH-001 (Hoch, reproduziert), claude DND-003 (Hoch); codex TECH-008 (Teilaspekt: „kategorie='ungueltig' wird als leerer Bestand beantwortet") |
| Reviewer | **beide** |
| Beleglage | **Konsens, Verifiziert** (`suche_regeln("Feuerball", kategorie="spell")` ⇒ leere Treffer + B1-Leerhinweis trotz vorhandenem Eintrag) |
| Beschreibung | `edition` und `methode` werden streng validiert, `kategorie`/`quelle` nicht (`richtung` fällt still auf `auto`) — inkonsistente Fehlersemantik, und der Grounding-Hinweis instruiert das Modell aktiv zur falschen Negativauskunft. |
| Auswirkung | Systematisch erzeugbares Falsch-Negativ („❌ nicht im Bestand" für Vorhandenes) — nach Halluzination die schädlichste Antwortklasse. |
| Maßnahme | Whitelist-Validierung analog `_pruefe_edition` (Kategorien-Whitelist; Quellen aus `quellen.kuerzel`) mit strukturiertem `fehler` + gültiger Werteliste + Hinweis „Parameterfehler ≠ nicht gefunden"; flankierend Enum-Schemas (SYN-P1-003). |
| Abnahmekriterium | Ungültige Kategorie/Quelle liefert nie `HINWEIS_LEER`, sondern `fehler` mit Werteliste; Regressionstest grün. |
| Abhängigkeiten | keine |
| Größe | **S** |

### SYN-P0-007 — Playtest-/Abenteuer-/Setting-Inhalte ohne persistente Kennzeichnung und ohne Scope-Filter

| Feld | Inhalt |
|---|---|
| Priorität / Kategorie | P0 · fachlich/architektonisch (Scope, Spoiler, Publikationsstatus) |
| Bereich | `importer/ddb_exporter/katalog.py` (lädt alles außer Premade-Characters; Hinweis nur auf Konsole), `cli.py` (`cmd_sync` persistiert `grund/hinweis` nicht), `db/schema.sql` (kein Inhaltsart-/Scope-Feld) |
| Ursprüngliche Befunde | claude DND-002 (Hoch); codex TECH-004 (Hoch), codex DND-007 (Hoch), codex DND-008 (Hoch, Statusmodell-Verallgemeinerung) |
| Reviewer | **beide unabhängig** (Claude via Fachreview, Codex via Technik- und Fachreview; Codex zusätzlich mit Bestandsbeleg: 807 Ravenloft-Einträge in der privaten DB — von der Synthese nicht re-verifiziert, da privater Bestand geschützt) |
| Beleglage | **Konsens** (Mechanik am Code verifiziert; Ausmaß im Live-Bestand offen) |
| Beschreibung | Der verbindliche MVP-Scope schließt Abenteuer-/Kampagneninhalte aus; der Sync lädt sie (und Playtest) bewusst — die Warnklassifikation erreicht aber weder Manifest noch DB noch Tool-Ausgaben. Ein Playtest-Eintrag wäre nur am Quellentitel erkennbar und erschiene als reguläres 2024-RAW; Abenteuer-Lore ist normal durchsuchbar, Spoiler-Schutz hängt allein am Modellverhalten. |
| Auswirkung | UA/Playtest als finales RAW; Spoiler-Ausgabe trotz oberster Verhaltensregel möglich; Optionslisten können Nicht-Finales unmarkiert führen. |
| Maßnahme | Kurzfristig (P0): Playtest-Kategorie vom Sync ausnehmen (wie Premade Characters) und Abenteuer-/Setting-Quellen bis zur Kennzeichnung nicht in den bedienten Bestand mergen. Mittelfristig (P1/P2): `inhaltsart`/`publication_status` vom Katalog über Manifest bis in `quellen` und Tool-Ausgaben persistieren; serverseitiger Filter vor Retrieval; Optionslisten blenden Nicht-Finales aus oder markieren es. |
| Abnahmekriterium | Ein Test-Playtest-/Abenteuer-Fixture ist im Spieler-Pfad entweder nicht importierbar oder trägt in jeder Antwort eine maschinen- und menschenlesbare Kennzeichnung; Optionslisten ohne unmarkiertes Playtest-Material. |
| Abhängigkeiten | Schema-Erweiterung (SYN-P2-001/P2-002); Eigentümer-Entscheidung zu Ravenloft-Quelle (Kap. 23) |
| Größe | **M** (Kurzfristlösung S) |

---

## 8. Konsolidierte P1-Befunde

> P1 = muss vor externen Nutzertests (der Spielrunde) bzw. Veröffentlichung behoben werden. Format kompakt; Felder wie oben.

### SYN-P1-001 — Qualitätssicherung ohne semantisches Gate; DDB-Suite verdeckt rot
- **Kategorie:** Tests/QS · **Ursprünge:** claude TECH-002 (Mittel), codex TECH-014 (Mittel), codex DND-012 (Hoch), claude DND-Kap. 18 (Testabdeckung) · **Beleglage:** **Konsens, Verifiziert** (1 failed in `.venv-ddb`; alle P0-Fehler bestehen trotz grüner Suite).
- **Beschreibung/Auswirkung:** „pytest grün" gilt nur fürs Haupt-venv; der DDB-Rundlauftest erwartet den inzwischen gefilterten „Spells"-Header (veralteter Vertrag). Vor allem: Kein Test prüft *Regelsemantik am echten Bestand* — deshalb blieben P0-001…005 unentdeckt.
- **Maßnahme:** (a) DDB-Testerwartung fixen + Ein-Befehl-Testlauf über beide venvs (DoD in CLAUDE.md); (b) **Realbestands-Golden-Suite**: für jeden P0-Fall erwartete Kernklauseln und verbotene Fremdklauseln (read-only, gegen die bediente DB); (c) Smoke in den Pflichtlauf integrieren; (d) `admin check --strict` mit deterministischer Stichprobe.
- **Abnahme:** Ein Befehl, Exit 0 über Haupt- und DDB-Suite; Golden-Suite schlägt bei jedem re-eingeführten P0-Fall fehl. · **Abhängigkeiten:** keine (zuerst umsetzen!) · **Größe: M**

### SYN-P1-002 — Kein stabiler Suche→Detail-Rundlauf; `quelle`-Parameter inkonsistent (Kürzel rein, Titel raus)
- **Kategorie:** MCP-Vertrag/Provenienz · **Ursprünge:** codex TECH-003 (Hoch) · **Beleglage:** **Einzelbefund, Verifiziert** (Titel-als-Filter ⇒ 0 Treffer; Detail wechselt zur Prioritätsquelle).
- **Maßnahme:** Suchtreffer um `eintrag_id` (stabil) + `quelle_kuerzel` ergänzen; Detail-Tools akzeptieren optional `eintrag_id`/`quelle`; Name bleibt Komfortpfad mit echter Ambiguitätsantwort; Rundlauf-Test.
- **Abnahme:** Ein Open5e-Suchtreffer lässt sich per Referenz exakt (gleicher Body) nachladen. · **Abhängigkeiten:** hilft SYN-P0-003 · **Größe: M**

### SYN-P1-003 — Tool-Schemas ohne Enums/Bounds/Fehlersemantik; keine Annotations; generische Outputs
- **Kategorie:** MCP-Schemas · **Ursprünge:** claude TECH-003 (Mittel), codex TECH-008 (Mittel), codex TECH-020 (Niedrig) · **Beleglage:** **Konsens, Verifiziert** (Schema-Introspektion beider Reviews identisch).
- **Maßnahme:** `Literal`-Enums (kategorie/richtung/methoden), Längen-/Array-Grenzen, `readOnlyHint`/`idempotentHint`, diskriminierte Ergebnisformen (`gefunden|mehrdeutig|fehler|nicht_verfuegbar`), Output-Schemas für stabile Kernfelder; Schema-Snapshot-Test.
- **Abnahme:** `tools/list`-Snapshot zeigt Enums/Annotations; ungültige Werte scheitern client-seitig bzw. als Requestfehler. · **Größe: M**

### SYN-P1-004 — Zugangskontrolle: fail-open bei leerem Token; Token klartext in Logs
- **Kategorie:** Sicherheit/Betrieb · **Ursprünge:** codex TECH-005 (Hoch); claude TECH-008 (Niedrig, Log-Teil) · **Beleglage:** **Teilweiser Konsens, Verifiziert** (Konfigurationslage; Schwere-Differenz = Threat-Model, siehe Kap. 16).
- **Maßnahme:** Produktionsmodus (env-Flag oder Default im Container): Start ohne Token ≥ Mindestlänge schlägt fehl; uvicorn `--no-access-log`; Pfad-Redaktion in Filter-Logs; Token-Rotation dokumentiert inkl. „alte Logs gelten als belastet".
- **Abnahme:** Containerstart ohne starkes Token bricht ab; Logtest findet kein Token. · **Größe: S**

### SYN-P1-005 — Serving-Container sieht `data/private` beschreibbar; kein Read-only-Serve
- **Kategorie:** Sicherheit/Least-Privilege · **Ursprünge:** codex TECH-006 (Hoch) · **Beleglage:** **Einzelbefund, Verifiziert** (Compose: `./data:/app/data` rw; private DB/Backups/Artefakte darunter; SQLite rw geöffnet).
- **Maßnahme:** Bedienten Bestand als eigenen Mount read-only (`data/serve/foliant.sqlite:ro`), `data/private` nicht in den Serve-Container; SQLite via `mode=ro`; `read_only`/`cap_drop`/`no-new-privileges` für den Serve-Dienst (Muster existiert beim ddb-exporter).
- **Abnahme:** Im Serve-Container ist `data/private` nicht sichtbar und kein Schreibzugriff auf die DB möglich; Tools funktionieren unverändert. · **Abhängigkeiten:** kleiner Umbau von `_verbinde`/Compose · **Größe: M**

### SYN-P1-006 — Glossar-/Auffindbarkeitslücken: 2024-Kernbegriffe, Synonyme, natürliche Formulierungen
- **Kategorie:** fachlich (Terminologie/Suche) · **Ursprünge:** claude DND-006 (Mittel: weapon mastery/emanation ohne Glossarzeile; „Waffenmeisterschaft"-Divergenz), claude DND-011 (Verstecken→„Hide Armor" zuerst), codex DND-013 (Mittel: Schubsen/Objektinteraktion/Komponenten/Mehrklassen laufen ins Leere; Zauberkapitel-Grundregeln als Kategorie `zauber`) · **Beleglage:** **Teilweiser Konsens** (disjunkte Beispielmengen, gleiche Ursachenklasse), Kernfälle verifiziert.
- **Maßnahme:** Kuratierte Glossar-Paare (Weapon Mastery↔Waffenbeherrschung + „Waffenmeisterschaft", Emanation↔Ausströmung, 8 Meisterschaftsnamen, Alltagssynonyme); allgemeine Magieregeln (Komponenten etc.) als `regel` kategorisieren; Ranking: Original-Suchwort-Präfix vor Glossar-Alternativen-Präfix; Deutsch-Term-Smoke erweitern.
- **Abnahme:** Definierte Begriffsliste (aus beiden Reviews) findet jeweils den Zieleintrag in den Top-3; `uebersetze_begriff("weapon mastery")` liefert offiziellen Begriff. · **Größe: M**

### SYN-P1-007 — Aussagearten und Antwortformat: RAW/Ableitung/SL-Entscheid nicht getrennt; keine Kurz-zuerst-Regel
- **Kategorie:** fachlich (Antwortdisziplin) · **Ursprünge:** claude DND-008 (Mittel), codex DND-009 (Hoch), codex DND-014 (Mittel), codex DND-018 (Niedrig) · **Beleglage:** **Konsens** (identische Empfehlung unabhängig formuliert).
- **Maßnahme:** `config/stil.py` + `docs/CLAUDE-PROJEKT-ANWEISUNG.md` (synchron) ergänzen: (a) Schlussfolgerungen als „Ableitung aus …" kennzeichnen; (b) regeloffene Fragen ausdrücklich als SL-Entscheidung (⚖️) markieren; (c) Antwortreihenfolge „direkte Antwort → Bedingungen/Ausnahmen → Beleg", Original-Klammerbegriff mindestens bei Erstnennung; (d) Mehrregel-Fragen: alle tragenden Belege nennen.
- **Abnahme:** Verhaltens-Checkliste (Magisches Geschoss/Konzentration, Dissonantes Flüstern) zeigt getrennte Aussagearten; Format-Stichprobe erfüllt Kurz-zuerst. · **Abhängigkeiten:** Verhaltens-Evals (SYN-P1-011) messen es · **Größe: S** (Instruktionstext) 

### SYN-P1-008 — Open5e-Formatter verwirft regelentscheidende Felder (Reaktionstrigger, Recharge/Form/Initiative)
- **Kategorie:** fachlich (Import/Vollständigkeit) · **Ursprünge:** codex DND-010 (Hoch) · **Beleglage:** **Einzelbefund, Verifiziert mit Einordnung** — Open5e-Counterspell-Rohtext (487 Z.) enthält keinen Trigger; **aber** der kanonische Antwortpfad liefert den deutschen Gegenzauber mit intaktem Trigger (Priorität 10 < 60). Der Verlust wirkt dort, wo Open5e die einzige Fassung ist bzw. bei expliziter Quellen-/Sprachwahl.
- **Maßnahme:** `_md_spell`/`_md_creature` um `reaction_condition`, Nutzungs-/Recharge-/Formfelder, `initiative_bonus`, Legendary-Kosten ergänzen; Formatter-Goldtests (Counterspell/Shield/Vampire); Re-Import open5e.
- **Abnahme:** Open5e-Fassungen von Gegenzauber/Schild tragen den Trigger; Vampir-Aktionen tragen Form-/Recharge-Angaben. · **Größe: M**

### SYN-P1-009 — Echte Quellkonflikte gleicher Edition werden still durch Priorität entschieden (Vampir „weiß" vs. „unaware")
- **Kategorie:** fachlich (Quellen/Übersetzung) · **Ursprünge:** codex DND-011 (Hoch); claude DND-Kap. 9 benannte die Mechanik („kanonische Quelle gewinnt still") ohne Konfliktbeispiel · **Beleglage:** **Teilweiser Konsens, teilverifiziert** — Synthese bestätigt die englische „unaware"-Passage und dass der deutsche Eintrag abweichenden Text führt; der exakte deutsche Wortlaut stützt sich auf Codex' Sichtprüfung (PDF S. 382).
- **Maßnahme:** Bei Dubletten mit abweichendem Inhalt (Hash-/Ähnlichkeitsvergleich) `konflikt`-Feld mit beiden Fundstellen ausgeben statt nur `weitere_quellen`-Titel; kurzfristig: bekannte Konfliktfälle als Golden-Test dokumentieren; Policy-Entscheidung Original vs. Übersetzung (Kap. 23).
- **Abnahme:** Der Vampir-Fall erscheint als sichtbarer Quellkonflikt mit beiden Aussagen. · **Abhängigkeiten:** SYN-P0-003-Identitätsumbau · **Größe: M–L**

### SYN-P1-010 — srd-de-Textpolitur: Laufkopf in 374, Wortrisse in 273 Einträgen, 8 Namens-Garbles
- **Kategorie:** Datenqualität (nicht regelverfälschend, aber zitatverfälschend) · **Ursprünge:** claude DND-005/009 (Mittel/Niedrig, quantifiziert); codex sah die Klasse innerhalb DND-003/004 · **Beleglage:** **Konsens (Klassenebene), Verifiziert (Zählungen Claude)**.
- **Maßnahme:** BEREINIGUNG-Regeln: Laufkopf „Systemreferenzdokument 5.2.1"+Seitenzahl entfernen; dokumentverifizierte Wortriss-Kittung (Konjunktionsfälle schützen); 8 Namens-Fixes; Re-Import.
- **Abnahme:** Feuerball/Verstecken-Volltexte ohne Laufkopf; Wortriss-Scan < 20 legitime Resttreffer; keine Garble-Namen. · **Abhängigkeiten:** mit SYN-P0-004 im selben Re-Import bündeln · **Größe: M**

### SYN-P1-011 — Betrieb & Verhalten: kein Readiness-Check, kein Monitoring/Off-Site-Backup, keine Modell-Evals
- **Kategorie:** Betrieb/QS · **Ursprünge:** claude TECH-005 (Mittel), codex TECH-012 (Mittel), codex TECH-018-Restore, codex TECH-021/claude TECH-Hinweis (Verhaltensgarantien clientabhängig), beide Fachreviews (T2/T10/T12 manuell) · **Beleglage:** **Konsens**.
- **Maßnahme:** `/ready` (DB read-only öffnen, Schema/FTS/Kernabfrage) neben `/health`; Compose-Healthcheck auf `/ready`; externer Uptime-Monitor; nächtliches Off-Site-Backup + einmaliger Restore-Test; kleine wiederholbare **Client-Eval-Checkliste** (Nichtwissen, Spoiler, Version, Mehrdeutigkeit, Aussageart) gegen den echten Connector, Ergebnisse versioniert.
- **Abnahme:** Korrupte/fehlende DB ⇒ 503; Restore auf leerem Zielsystem besteht `admin check` + Golden-Suite; Eval-Protokoll liegt im Repo. · **Größe: M**

### SYN-P1-012 — Reproduzierbarkeit: offene Pins, `.venv-ddb` im Image, Korpus-/Quellenmanifest fehlt, Doku-Drift
- **Kategorie:** Supply-Chain/Betrieb/Doku · **Ursprünge:** claude TECH-004/006/011/012, codex TECH-015/016, codex DND-015 · **Beleglage:** **Konsens, Verifiziert** (`.dockerignore` ohne `.venv-ddb`; ATTRIBUTION-Widerspruch; `FOLIANT_COBALT`-Altverweis in `config/foliant.example.toml`).
- **Maßnahme:** Lockfile/Voll-Pinning (mind. pymupdf4llm/uvicorn/httpx exakt), `.dockerignore` um `.venv-ddb/`+ZIPs, Dev-Requirements trennen; **Quellen-/Korpusmanifest** (Quelle, Hash, Revision, Anzahl, Status) für den bedienten Bestand; ATTRIBUTION.md auf Ist-Zustand, authless-Altaussagen und Cobalt-Referenz bereinigen; README-Schnellstart bis Serverstart/Connector inkl. Testbefehl.
- **Abnahme:** Zwei zeitversetzte Builds ⇒ identische Abhängigkeitsstände; bedienter Bestand entspricht Manifest; Doku-Widerspruchsliste leer. · **Größe: M**

---

## 9. Konsolidierte P2- und P3-Befunde

### P2 (zeitnah nach dem MVP bzw. parallel, nicht blockierend)

| ID | Titel | Ursprünge | Beleglage | Maßnahme (Kurzform) | Größe |
|---|---|---|---|---|---|
| SYN-P2-001 | Editions-/Statusmodell: „unterstützt" ≠ „vorhanden"; `5.5e`-Alias; `aeltere_staende`-Pauschale; `publication_status` | codex TECH-011, codex DND-008/017, claude TECH-013.1 | Konsens (Facetten), Code-verifiziert | Unterstützte Editionen konfigurieren; Aliasse normalisieren; Etikettierung editionsvergleichend; Statusdimension einführen (mit SYN-P0-007) | M |
| SYN-P2-002 | Wissensmodell-Ausbau: `concept`/`entry_variant`/`relation`, `parent_id`, Snapshot-/Revision-Provenienz | codex TECH-009, claude Technik-Kap. 13, codex DND-014/015 | Konsens (als Ausbaustufe; Codex fordert früher — s. Kap. 16) | Schrittweise Migration in SQLite; externe IDs/Hashes/Locator durch Pipeline erhalten | L |
| SYN-P2-003 | Regelwerte streng belegen (Point-Buy-Kostentabelle nur per Anker „27 Punkte" verifiziert) | codex TECH-010 | Einzelbefund, Code-verifiziert | Kostentabelle zur Laufzeit parsen oder strukturiert importieren; sonst `nicht_pruefbar` | S–M |
| SYN-P2-004 | Grenzen/DoS: keine Längen-/Antwort-/Ratenlimits; Fuzzy-/Glossar-Vollscans pro Aufruf | codex TECH-013 (Mittel), claude TECH-014/015 (Hinweis) | Teilweiser Konsens (Schwere divergiert; Exposition durch Allowlist gemindert); „Bodies > 50 k" nur privater Bestand — offen | Schema-Bounds, Antwortkappung, Glossar-Cache/Index; Pi-Lastmessung mit Budget | M |
| SYN-P2-005 | Charakterführung: SRD nennt 5 Schritte (inkl. Herkunft mit 2 Sprachen, Gesinnung); Pflichtwahlen (Sprachen, Speziesoptionen) fehlen in Führung/Prüfung; höherstufige Builds unscharf | codex DND-006 (Hoch); claude prüfte gegen die 4-Schritt-Vorgabe der Anforderung B7 (Spec-vs-RAW-Spannung, Kap. 16) | Einzelbefund (Codex), teilverifiziert | Kurzfristig Hinweistexte um Sprachen/Herkunft ergänzen + Stufen-Scope ehrlich deklarieren; vollständige Modellierung später | M (kurz: S) |
| SYN-P2-006 | Kanonisches Betriebs-Runbook (eine verbindliche Betriebsvariante, Rest verweist) | codex TECH-016, claude TECH-011/012 | Konsens | Runbook: Voraussetzungen→Install→Test→Start→Connector→Import→Backup | S |
| SYN-P2-007 | Ausgabegrenzen/Lizenzdisziplin für private Quellen (Volltext auf Zuruf) | codex DND-016 (Mittel), claude DND-Kap. 14 | Konsens (teilw.) | Reproduktionstiefe pro Lizenzklasse; Gruppen-Freigabeentscheidung protokollieren (Kap. 23) | M |
| SYN-P2-008 | Entwickler-Agentenrechte: breite `python/curl/ssh/docker`-Allows umgehen Secret-Denies | codex TECH-007 (Hoch eingestuft; Synthese: P2, da Entwicklungsumgebung, nicht Produkt) | Einzelbefund, Datei-verifiziert — Deny griff in der Synthese nachweislich (private-DB-Kopie verweigert), Umgehungspfade bestehen dennoch | Allows auf konkrete Unterbefehle eindampfen; Netz/SSH/Docker bestätigungspflichtig | S |
| SYN-P2-009 | SL-Vorbereitung: `*_meta`-Tabellen befüllen + Filter-Tools; CHECK-Constraints/Migrationsversion | claude DND-Kap. 13, codex TECH-019, beide Technik-Kap. „Erweiterbarkeit" | Konsens | Meta-Felder beim Import extrahieren; Schema-Version einführen | M–L |

### P3 (langfristig)

| ID | Titel | Ursprünge | Beleglage | Größe |
|---|---|---|---|---|
| SYN-P3-001 | Strukturelle Rollen-/Spoiler-Isolation (getrennte Korpora/Zugänge, A3) | alle vier Reviews, deckungsgleich | Konsens | XL |
| SYN-P3-002 | Regelbeziehungsgraph/Interaktionskatalog (`exception_to`, `overrides`, Trigger/Dauer/Stapelung) für belegte Mehrregel-Antworten | codex DND-014, codex TECH-009, claude DND-Kap. 11 | Konsens | XL |
| SYN-P3-003 | Errata-/Revisionstracking + Autoritätsklassen für offizielle Klarstellungen | claude DND-013, codex DND-008/009/015 | Konsens | M |
| SYN-P3-004 | Hausregeln-/Optionale-Regeln-Overlay mit sichtbarer Überlagerung (A4) | beide Fachreviews | Konsens | XL |

---

## 10. Technische Probleme mit fachlichen Auswirkungen

Die Kernerkenntnis der Vier-Review-Lage: **Fast alle fachlichen Falschantwort-Risiken haben eine präzise technische Ursache** — und umgekehrt wirkt fast jeder technische P0/P1 direkt auf Regelantworten:

| Technische Ursache | Fachliche Wirkung | Synthese-IDs |
|---|---|---|
| Fuzzy-Glossar ohne Matchtyp | falsche „offizielle" Übersetzung und falscher Regeltext (Aktionen→Reaktionen) | SYN-P0-001 |
| Exakt-Match ohne Suffix-Aliasse + B5-Fallback-Reihenfolge | 2014-Zustand statt vorhandener 2024-Regel | SYN-P0-002 |
| Identität = Name+Edition+Kategorie (ohne Kontext/Inhalt) | Statblock-Fragmente, Kurzverweis statt Kernregel, verdeckte Quellkonflikte | SYN-P0-003, SYN-P1-009 |
| Heading-/Spaltenverluste im PDF-Chunker ohne semantische Gates | regelverfälschende Verschmelzungen (Zweihändig+Umstoßen, Attributswurf+SG 15) | SYN-P0-004, SYN-P1-001 |
| Nur-Übergebenes-Prüfen in `pruefe_build` | falsche Legalitätsbestätigungen | SYN-P0-005 |
| Fehlende Parametervalidierung + Grounding-Hinweis im Leerfall | selbstbewusstes Falsch-Negativ („nicht im Bestand") | SYN-P0-006 |
| Klassifikation nur auf der Konsole, kein Scope-Feld im Schema | Playtest als RAW, Abenteuer-Lore im Spielerpfad | SYN-P0-007 |
| Formatter verwirft strukturierte API-Felder | verlorene Reaktionstrigger/Recharge/Formlimits | SYN-P1-008 |
| Quellenpriorität als Vollständigkeits-/Wahrheitsproxy | beschädigter deutscher Chunk gewinnt gegen vollständige englische Fassung | SYN-P0-004 × SYN-P1-009 |
| Tests prüfen Struktur, nicht Semantik | alle obigen Fehler blieben hinter grüner Suite unsichtbar | SYN-P1-001 |

## 11. Fachliche Anforderungen mit technischen Konsequenzen

| Fachliche Anforderung (Quelle) | Technische Konsequenz | Synthese-IDs |
|---|---|---|
| „Keine Spoiler/Abenteuerinhalte" (§8/B6) ist als *Verhaltensregel* nicht durchsetzbar | Scope-/Inhaltsart-Feld in Schema+Manifest+Filter; langfristig getrennte Korpora | SYN-P0-007, SYN-P3-001 |
| „Version immer, keine stille Vermischung" (V2/V5) muss auch **Namensauflösung** umfassen | Suffix-Aliasse, Auflösungsreihenfolge Edition-vor-Fallback, gemischte Fixture-Tests | SYN-P0-002 |
| „Vollständige Steckbriefe" (F2) verlangt Chunk-Vollständigkeit als prüfbare Eigenschaft | Pflichtklausel-Gates je Kategorie, Aggregation zerteilter Blöcke, Golden-Tests | SYN-P0-003/004, SYN-P1-001 |
| „Build-Prüfung streng, transparent, ehrlich" (Q4) heißt: Pflichtwahlen erkennen, nicht nur Eingaben validieren | abgeleitete Pflichtfelder aus Klasse/Stufe/Hintergrund; Statusdisziplin | SYN-P0-005 |
| „Ehrliches Nicht-gefunden" (B1/T2) setzt korrekte Negativsignale voraus | Parametervalidierung, Fehlerunion im Schema | SYN-P0-006, SYN-P1-003 |
| Deutsch-first mit 2024-Neubegriffen (S3/S11) | kuratierte Glossarpflege als Pflichtprozess je neuem Buch/Jahrgang | SYN-P1-006 |
| RAW-Anspruch (B8) braucht Aussagearten-Trennung | Instruktions- und ggf. Datenmodell-Erweiterung | SYN-P1-007, SYN-P3-003 |
| Belegbarkeit „bis zur Fundstelle" (P4/F7) langfristig | stabile `eintrag_id`, Revision/Hash je Quelle, Manifest | SYN-P1-002/012, SYN-P2-002 |

---

## 12. Befunde mit vollständigem Konsens

Unabhängig von Claude **und** Codex erkannt (Details in Kap. 7–9): SYN-P0-004 (beschädigte srd-de-Chunks; beide fanden unabhängig sogar denselben Topple/„Zweihändig"-Fall), SYN-P0-006 (ungültige Parameter → falsches „nicht gefunden"), SYN-P0-007 (Playtest/Abenteuer ohne Kennzeichnung), SYN-P1-001 (rote DDB-Suite + fehlendes semantisches Gate), SYN-P1-003 (offene Schemas/fehlende Annotations), SYN-P1-007 (Aussagearten), SYN-P1-011 (Betrieb/Readiness/Evals), SYN-P1-012 (Pins, Doku-Drift, ATTRIBUTION-Widerspruch), SYN-P2-001/002/006/009, SYN-P3-001…004. Ebenso alle in Kap. 6 gelisteten Stärken.

## 13. Befunde mit teilweisem Konsens

- **SYN-P0-002** (2014-Fallback): gleiche Wurzel von beiden gefunden, Schwere divergierte (Codex Kritisch mit gemischtem Bestand, Claude Mittel mit rein-2024-Bestand) — durch Verifikation zugunsten der höheren Einstufung entschieden.
- **SYN-P1-004** (Zugang): Codex Hoch, Claude Niedrig — Threat-Model-Differenz, beide Sichtweisen dokumentiert (Kap. 16); Maßnahme unstrittig.
- **SYN-P1-006** (Auffindbarkeit): disjunkte Beispielmengen (Claude: Glossarlücken/Ranking; Codex: Synonyme/Kategorien), gleiche Ursachenklasse.
- **SYN-P1-009** (Quellkonflikte): Claude beschrieb die Mechanik abstrakt, Codex lieferte den konkreten Vampir-Beweis.
- **SYN-P1-010** (Textpolitur): Claude quantifizierte (374/273/8), Codex fand die Klasse über Einzelfälle.
- **SYN-P2-004** (Grenzen/DoS): Codex Mittel, Claude Hinweis — Expositionsbewertung divergiert.

## 14. Einzelbefunde von Claude

Nur von Claude gefunden (durch Synthese bestätigt bzw. übernommen):
1. **Glossarlücken bei 2024-Kernbegriffen** weapon mastery/emanation trotz eigener Seed-Liste + Terminologie-Divergenz srd-de („Waffenbeherrschung"/„Meisterschaftseigenschaft") vs. dt. PHB („Waffenmeisterschaft") — Teil von SYN-P1-006 (verifiziert).
2. **Quantifizierte srd-de-Textschäden** (Laufkopf 374, Wortrisse 273, 8 Namens-Garbles inkl. „Feuerschale der FeuerelementarHerrschaft") und der 22-kB-ToC-Blob — SYN-P1-010/P0-004 (verifiziert).
3. **„Verstecken"-Ranking-Randfall** (Hide Armor vor der Aktion) — SYN-P1-006 (verifiziert).
4. **`aeltere_staende`-Zukunftspauschale** und `hole_eintrag`-Totcode — SYN-P2-001 (Code-verifiziert).
5. **rsync-Excludes decken Root-ZIPs nicht**; „Neuer Ordner"; pytest im Prod-Image — SYN-P1-012/P2-006.
6. **Positive Verifikationen**, die Codex' Pauschalurteile begrenzen: korrekte 2024-Kerntexte breiter Stichproben; Seitenzahl-Konsistenz (Feuerball-Fußzeile = Zitat); funktionierender Kern der Glossar-Brücke inkl. Abkürzungs-Hops; Latenzen 20–44 ms lokal.

## 15. Einzelbefunde von Codex

Nur von Codex gefunden (Synthese-Verifikationsstatus in Klammern):
1. **Aktionen→Reaktionen-Fuzzy-Identität** — SYN-P0-001 (**verifiziert**).
2. **Solar-Fragment/Dedupe-Verschlucken + Kurzverweis-Verdrängung** — SYN-P0-003 (**Solar verifiziert**).
3. **Beschädigte Steckbriefe Eissturm/Göttliche Gunst/Symbol/Windwall/Vampirbrut/Schild** — SYN-P0-004 (**verifiziert** bis auf Windwall, plausibel gleiche Klasse).
4. **Build-False-Positives (4 Konstellationen)** — SYN-P0-005 (**verifiziert**).
5. **Quellen-Rundlauf-Bruch (Kürzel rein/Titel raus)** — SYN-P1-002 (**verifiziert**).
6. **Serve-Container sieht `data/private` rw** — SYN-P1-005 (**Compose verifiziert**).
7. **Fail-open-Token + Access-Log-Gesamtbild** — SYN-P1-004 (Konfiguration verifiziert).
8. **Open5e-Feldverluste** — SYN-P1-008 (**Rohtext verifiziert**, mit Milderungs-Einordnung).
9. **Vampir-DE/EN-Konflikt** — SYN-P1-009 (teilverifiziert; DE-Wortlaut per Codex-Sichtprüfung).
10. **Editionsvalidierung verwechselt unterstützt/vorhanden; `5.5e`-Alias** — SYN-P2-001 (Code-verifiziert).
11. **Point-Buy-Beleg nur per Anker** — SYN-P2-003 (Code-verifiziert).
12. **`/health` als Pseudo-Readiness** — SYN-P1-011 (Code-verifiziert).
13. **`.claude/settings.json`-Umgehungspfade** — SYN-P2-008 (Datei verifiziert; Wirksamkeit der Denies in der Synthese selbst beobachtet).
14. **Charakterführung 4 vs. 5 SRD-Schritte, fehlende Sprachen-/Speziespflichtwahlen** — SYN-P2-005 (plausibel, nicht einzeln nachgeprüft).
15. **Privater Bestand: 807 Ravenloft-Einträge; Bodies > 50 k; `.venv-ddb` (49 MB) via `COPY . .` ins Image** — Manifest-/Compose-Teil verifiziert, Bestandszahlen offen (privater Bestand geschützt).

## 16. Widersprüche und offene Bewertungen

1. **Gesamtreife (Claude „MVP-reif nach kleinen Fixes" vs. Codex „nicht freigabefähig"):** Durch die Synthese-Verifikation der Codex-P0-Fälle **zugunsten von Codex entschieden** — für externe Nutzung. Claudes Urteil bleibt für den *Eigenbetrieb des Betreibers* vertretbar (der die Grenzen kennt). Ursache der Divergenz: Claude prüfte Code, Schemas und Regel-*Texte* (und fand diese korrekt), Codex prüfte zusätzlich systematisch den *Antwortpfad* bei natürlichen Fragen und den gemischten Bestand.
2. **Build-Prüfung (Claude: Stärke „ehrlich"; Codex: „falsche Positivurteile"):** **Beides zutreffend, Codex' Fälle sind entscheidend** — verifiziert. Die Beleg-/Grenzen-Transparenz (Claude) existiert; sie verhindert die vier False-Positive-Konstellationen nicht. Kein echter Faktenwiderspruch, sondern komplementäre Testfälle.
3. **Sicherheit 8/10 vs. 4/10:** Kein Faktenkonflikt — unterschiedliche Bedrohungsmodelle (Claude: privater Solo-Betrieb hinter Allowlist+Token, dokumentierte Restrisiken; Codex: Mehrnutzer-Serving gekaufter Inhalte, Nutzerbindung/Widerruf gefordert). **Synthese:** Für das erklärte Ziel „Runde nutzt es" gilt der strengere Maßstab in den Punkten fail-fast, Log-Redaktion, Serve-Isolation (SYN-P1-004/005); die von Codex geforderte **OAuth-/Identitätsschicht** bleibt **offene Produktentscheidung** (Kap. 23) — mit dem Hinweis, dass die Projektannahme „Claude-Connectors können kein OAuth" wahrscheinlich überholt ist (Custom Connectors unterstützen Remote-MCP-OAuth; nur Custom-Header sind unmöglich). Nicht in der Synthese final verifizierbar → offen.
4. **Charakterführung (Codex: „vier statt fünf Schritte" als Hoch; Claude: B7-konform):** Spannungsfeld Spezifikation vs. RAW — die Anforderung B7 definiert selbst die 4-Schritt-Führung, das SRD nennt 5 Schritte inkl. Sprachen. **Synthese: kein Codefehler, sondern Anforderungs-Update nötig** (SYN-P2-005); die fehlenden Pflichtwahlen (Sprachen, Speziesoptionen) sind fachlich berechtigt, die Hoch-Einstufung von Codex wird auf P2 relativiert, weil Führungstexte Hinweise, nicht Regeln ausgeben.
5. **Open5e-Feldverluste (Codex Hoch):** Verifiziert, aber **im kanonischen Pfad gemildert** (deutscher Gegenzauber trägt den Trigger; deutsche Quelle gewinnt) — Synthese stuft auf P1 mit klarer Wirkbedingung.
6. **Bodies > 50 k (Codex) vs. Max. 22,4 k (Claude):** Kein Widerspruch — verschiedene Datenbasen (privat vs. öffentlich); wegen des Schutzes der privaten DB **offen**.
7. **Datenmodell-Umbau-Zeitpunkt (Codex: SourceSnapshot/Variant vor Veröffentlichung; Claude: Evolution nach MVP):** Beide Zielbilder identisch, Timing divergiert. **Synthese:** P0/P1 sind ohne Schema-Umbau lösbar (Aliasse, Kontext-Identität, `eintrag_id`, Scope-Feld); der volle Umbau bleibt P2 (SYN-P2-002). Offen bleibt die Domänenentscheidung „gleichnamige Abschnitte: aggregieren vs. Varianten" (Kap. 23).

---

## 17. Vergleich der Bewertungsnoten

### Technische Reviews (identische Kategorien, direkt vergleichbar)

| Kategorie | Claude | Codex | Δ | Wahrscheinliche Ursache | Synthese-Einschätzung |
|---|---:|---:|---:|---|---|
| MCP-Konformität | 8 | 6 | 2 | Codex gewichtet fehlende Verträge/Resources/Fehlersemantik stärker | **6–7**: Transport/Registrierung solide; Vertragslücken real (SYN-P1-002/003) |
| Architektur | 9 | 5 | 4 | Claude bewertet Import-/Trennungs-Substanz; Codex Identitäts-/Scope-/Vertrauensgrenzen | **7**: Fundament exzellent, Identitäts- und Scope-Schicht fehlt (P0-Kern) |
| Codequalität | 8 | 7 | 1 | weitgehend einig | **7–8** |
| Zuverlässigkeit | 8 | 4 | 4 | Codex' Antwortpfad-Bugs (verifiziert) waren Claude unbekannt | **4–5** bis P0 behoben, danach realistisch 7+ |
| Sicherheit | 8 | 4 | 4 | Threat-Model (s. Kap. 16 Nr. 3) | **6** für heutigen Solo-Betrieb; **4–5** gemessen am Gruppenziel — P1-Paket schließt die Lücke weitgehend |
| Testabdeckung | 8 | 5 | 3 | Codex zählt semantische/CI-/E2E-Lücken und die rote DDB-Suite schwerer | **5–6**: Breite ja, Semantik-Gate nein (SYN-P1-001) |
| Dokumentation | 9 | 6 | 3 | Claude würdigt Tiefe/Ehrlichkeit, Codex die Statusdrift | **7**: überdurchschnittlich, Drift real |
| Erweiterbarkeit | 8 | 5 | 3 | Bewertung des flachen Modells (Relationen/Revisionen) | **6–7** |
| MVP-Reife (technisch) | 8 | 4 | 4 | Folge der Zuverlässigkeitsdifferenz | **5** heute; klarer, kleiner Pfad auf 7–8 |

### Fachliche Reviews (identische Kategorien, direkt vergleichbar)

| Kategorie | Claude | Codex | Δ | Wahrscheinliche Ursache | Synthese-Einschätzung |
|---|---:|---:|---:|---|---|
| Fachliche Richtigkeit | 7 | 5 | 2 | Claude prüfte Texte (korrekt), Codex den Antwortpfad (fehlerhaft) | **5**: Texte gut, Auswahl/Fragmente verfälschen Antworten |
| Trennung der Regelversionen | 9 | 4 | 5 | Claude sah nur den rein-2024-Bestand; Codex den 2014-Fallback | **5–6**: Modell stark, Auflösung leck (SYN-P0-002); nach Fix 8–9 erreichbar |
| Vollständigkeit im Umfang | 7 | 4 | 3 | Codex fand abgeschnittene Steckbriefe + Charakter-Pflichtwahlen | **5** |
| Umgang mit Regelausnahmen | 7 | 3 | 4 | identische Analyse, andere Maßstäbe (Texte vorhanden vs. Prozess fehlt) | **5**: Einzeltexte tragen, Mehrregel-Prozess ungesichert |
| Quellenqualität | 8 | 7 | 1 | einig | **7–8** |
| Nachvollziehbarkeit | 9 | 6 | 3 | Codex verlangt Abschnitts-/Revisions-Granularität | **7**: Beleg pro Antwort stark; Revision/Kontext fehlen |
| Verständlichkeit für Spielende | 7 | 5 | 2 | Codex gewichtet falsche Vollständigkeit/fehlende Rückfragen | **5–6** |
| Eignung für Spielleitende | 7 | 3 | 4 | Codex misst am fehlenden Scope-/Rollenmodell | **5**: Material ja, Struktur nein |
| Fachliche Testabdeckung | 7 | 3 | 4 | Codex: „grün beweist nichts Semantisches" (durch P0-Funde belegt) | **3–4** bis Golden-Suite existiert |
| Fachliche MVP-Reife | 7 | 4 | 3 | Folge der obigen | **4–5** heute; nach P0-Paket 7 realistisch |

Eine Gesamtpunktzahl wird bewusst nicht gebildet (unterschiedliche Bewertungsanker); die Synthese-Spalten sind qualitativ begründete Einordnungen, keine Mittelwerte.

---

## 18. Konsolidierter Maßnahmenplan

> Felder: Priorität · Synthese-ID (zugrunde liegende Befunde s. Kap. 7–9) · Komponenten · Ziel · Umsetzung · Abhängigkeiten (techn./fachl.) · Abnahme · Größe. Keine Zeitschätzungen.

### Stufe A — sofort, vor weiteren internen Tests

| # | Prio | SYN-ID | Komponenten | Ziel & Umsetzung | Abhängigkeiten | Abnahme | Größe |
|---|---|---|---|---|---|---|---|
| A1 | P1 | SYN-P1-001 | `tests/`, `Makefile`/Skript, `admin.py` | Vertrauenswürdiges Test-Gate: DDB-Erwartung fixen, Ein-Befehl-Lauf beide venvs, Golden-Suite-Gerüst für P0-Fälle anlegen (zunächst rot) | keine | ein Befehl, beide Suiten sichtbar; Golden-Fälle dokumentiert rot | M |
| A2 | P0 | SYN-P0-001 | `app/glossar.py`, `app/db.py`, `nachschlagen.py` | Exact/Fuzzy trennen; Fuzzy nie Identität/kanonische Übersetzung | keine | „Aktionen"-Blockertest grün | S–M |
| A3 | P0 | SYN-P0-002 | `nachschlagen.py` (`_eintrag_namen`, `_hole_detail`) | Klammer-Suffix-Aliasse; Editionsauflösung vor Altstand-Fallback | A2 sinnvoll zuerst | 15-Zustände-Test (gemischte Fixture) grün | S–M |
| A4 | P0 | SYN-P0-006 | `nachschlagen.py`, `db.py` | Kategorie-/Quellen-Validierung mit strukturiertem Fehler | keine | Falsch-Negativ-Test grün | S |
| A5 | P0 | SYN-P0-005 | `charakter.py` | Pflichtwahlen-Ableitung; Status-Ehrlichkeit (kein `ok` für Ungeprüftes) | keine | 4 Negativ-Builds nie `legal_soweit_pruefbar` | M |
| A6 | P0 | SYN-P0-004 + SYN-P1-010 | `importer/import_markdown.py` (BEREINIGUNG/SPLIT srd-de), Re-Import | Chunk-Reparaturpaket (Umstoßen, Zauber-Fragmente, Vampirbrut, Schild, Attributswurf, Statblock-Köpfe, ToC, Namen, Laufkopf, Wortrisse) | Golden-Gates aus A1 | alle benannten Golden-Tests grün; `admin check` OK | L |
| A7 | P0 | SYN-P0-003 | `db.py` (Dedupe-Identität), `nachschlagen.py` | Kontext-/Inhalts-bewusste Identität; Teil-Chunk-Aggregation oder Kandidaten | A6 reduziert Fälle | Solar/Bonusaktionen/Temp-TP/Todesretter-Tests grün | M–L |

### Stufe B — vor externen MVP-Tests (Freigabe an die Runde)

| # | Prio | SYN-ID | Komponenten | Ziel & Umsetzung | Abhängigkeiten | Abnahme | Größe |
|---|---|---|---|---|---|---|---|
| B1 | P0 | SYN-P0-007 | `katalog.py`, `cli.py`, `import_ddb.py`, `schema` (Feld), Betrieb | Playtest-Skip + Abenteuer-Quarantäne; `inhaltsart` bis in Tool-Ausgaben | Eigentümer-Entscheidung Ravenloft (Kap. 23) | Scope-Fixture-Test; Optionslisten sauber | M |
| B2 | P1 | SYN-P1-002 | `db.py`, `nachschlagen.py` | `eintrag_id`+`quelle_kuerzel` in Treffern; Detail per Referenz | A7 | Rundlauf-Test gleicher Body/Quelle | M |
| B3 | P1 | SYN-P1-003 | Tool-Signaturen, Registrierung | Enums/Bounds/Annotations/Fehlerunion; Schema-Snapshot-Test | A4 | Snapshot grün; ungültige Werte scheitern früh | M |
| B4 | P1 | SYN-P1-004 | `server.py`, `zugriff.py`, `Dockerfile`, Doku | Fail-fast-Token im Produktionsmodus; Log-Redaktion; `--no-access-log` | keine | Startabbruch-Test; Log-Scan tokenfrei | S |
| B5 | P1 | SYN-P1-005 | `docker-compose.yml`, `db.py` (`mode=ro`) | Read-only-Serve ohne `data/private` | Betriebsfenster | Container-Probe: kein privater Pfad, kein Write | M |
| B6 | P1 | SYN-P1-006 | `import_glossar.py` (Paare), `db.py` (Ranking), Kategorien | 2024-Begriffe/Synonyme; Original-vor-Alternative-Präfix; Magie-Grundregeln als `regel` | A2 | Begriffs-Testliste Top-3-Treffer | M |
| B7 | P1 | SYN-P1-007 | `config/stil.py`, `CLAUDE-PROJEKT-ANWEISUNG.md` | Aussagearten (RAW/Ableitung/⚖️ SL), Kurz-zuerst-Format | keine | Eval-Checkliste zeigt Kennzeichnung | S |
| B8 | P1 | SYN-P1-008 | `import_open5e.py` + Re-Import | Trigger/Recharge/Form/Initiative erhalten | keine | Formatter-Goldtests (Counterspell/Shield/Vampire) | M |
| B9 | P1 | SYN-P1-011 | `server.py` (`/ready`), Compose, Cron, Eval-Skript | Readiness, Monitoring, Off-Site-Backup+Restore-Probe, Client-Eval-Checkliste | B4/B5 | 503-Test; Restore-Protokoll; Eval-Protokoll | M |
| B10 | P1 | SYN-P1-012 | `requirements*`, `.dockerignore`, Manifest, ATTRIBUTION/README | Pins/Lock; `.venv-ddb`-Exclude; Quellenmanifest; Doku-Abgleich | keine | Doppelbuild identisch; Manifest = Bestand; Widerspruchsliste leer | M |
| B11 | P1 | SYN-P1-009 | `db.py` (Konfliktausweis) | Inhalts-abweichende Dubletten als `konflikt` mit beiden Fundstellen | A7/B2 | Vampir-Konflikttest | M–L |

### Stufe C — vor Veröffentlichung (Dauerbetrieb der Runde)

| # | Prio | SYN-ID | Ziel | Abnahme | Größe |
|---|---|---|---|---|---|
| C1 | P2 | SYN-P2-001 | Editions-/Statusmodell (supported-Liste, Aliasse, `publication_status`, Etiketten) | Editions-Zustandstests (leer/2014-only/gemischt/Alias) grün | M |
| C2 | P2 | SYN-P2-003 | Regelwerte streng belegen (Point-Buy-Parsing) | synthetische Quelle ohne Tabelle ⇒ `nicht_pruefbar` | S–M |
| C3 | P2 | SYN-P2-004 | Bounds/Kappung/Glossar-Cache + Pi-Lastmessung | dokumentierte Budgets eingehalten | M |
| C4 | P2 | SYN-P2-005 | Charakterführung: Sprachen/Herkunft in Hinweisen; Stufen-Scope ehrlich | Führungstexte nennen alle Pflichtwahlen | S–M |
| C5 | P2 | SYN-P2-006/007 | Runbook + Lizenz-/Ausgabegrenzen + Gruppen-Entscheid protokolliert | frischer Betreiber folgt einem Dokument; Entscheidungslog existiert | M |
| C6 | P2 | SYN-P2-008 | Agentenrechte eindampfen | Injection-Probe kann weder Secrets lesen noch Netz auslösen | S |

### Stufe D — nach Veröffentlichung des MVP

| # | Prio | SYN-ID | Ziel | Größe |
|---|---|---|---|---|
| D1 | P2 | SYN-P2-002 | `concept`/`entry_variant`/`relation`/Snapshot-Migration | L |
| D2 | P2 | SYN-P2-009 | Meta-Felder + SL-Filter-Tools; Schema-Version/Migrationen | M–L |
| D3 | P2 | SYN-P1-011-Ausbau | Eval-Katalog als Regressionsgate mit Trends | M |

### Stufe E — langfristige Ausbaustufe

| # | Prio | SYN-ID | Ziel | Größe |
|---|---|---|---|---|
| E1 | P3 | SYN-P3-001 | strukturelle Rollen-/Spoiler-Isolation (getrennte Korpora/Zugänge) | XL |
| E2 | P3 | SYN-P3-002 | Regelbeziehungsgraph + belegte Mehrregel-Antworten | XL |
| E3 | P3 | SYN-P3-003 | Errata-/Klarstellungs-Autoritätsklassen | M |
| E4 | P3 | SYN-P3-004 | Hausregeln-/Optionsregel-Overlay | XL |

## 19. Empfohlene Reihenfolge der Umsetzung

**A1 → A2/A3/A4/A5 (parallelisierbar) → A6 → A7 → B1/B4 → B2/B3 → B6/B7/B8 → B5/B9/B10 → B11 → C…**

Begründung: Erst das Test-Gate (A1), damit jede folgende Korrektur einen rot-nach-grün-Nachweis hat; dann die vier kleinen, unabhängigen Antwortpfad-Fixes (A2–A5); dann das große Reparatur-/Re-Import-Paket (A6), das A7 (Dedupe) entlastet; Scope und Zugangs-Härtung (B1/B4) vor jeder URL-Weitergabe an die Runde; Referenz-/Schema-Verträge (B2/B3) vor den Auffindbarkeits- und Formatter-Paketen; Betriebs- und Reproduzierbarkeitspunkte (B5/B9/B10) vor dem Dauerbetrieb; der Konfliktausweis (B11) baut auf der neuen Identität auf.

---

## 20. Konsolidierte Teststrategie

Zusammenführung von claude V1–V10 (Technik), claude TF-01–28 (Fach), codex Tests 1–20 (Technik), codex DND-T-001–044 (Fach) — dedupliziert, nach Ebenen; repräsentative Quell-IDs in Klammern.

**Ebene 1 — MCP-Protokoll/Verträge (automatisiert):**
- Echter Streamable-HTTP-E2E über den veröffentlichten ASGI-Pfad: initialize → tools/list → tools/call, inkl. Geheimpfad, CF-Header-Matrix, 403-Fälle, strukturierte Fehler (claude V3; codex T9).
- Schema-Snapshot: Namen, Pflichtparameter, Enums, Bounds, Annotations, Output-Formen (claude V2; codex T6).
- Ungültige Eingaben: falsche Kategorie/Quelle/Richtung/Methode/Edition, Zusatzfelder, leere/überlange Strings, große Arrays ⇒ konsistente Fehlerunion, nie Pseudo-„nicht gefunden" (claude V1/V6; codex T7).
- Authentisierung/Logs: Start ohne Token schlägt im Prod-Modus fehl; Log-Scan token-/secret-frei (codex T10/T11).

**Ebene 2 — Retrieval-Identität und Quellen (automatisiert, Realbestand read-only):**
- Glossar-Kollision: Aktionen/Action/Reaktionen/Reactions getrennt; Fuzzy nur als markierter Kandidat (codex T1).
- Suffix-Aliasse: alle 15 Zustände klammerlos ⇒ 2024; gemischte 2024/2014-Fixture ⇒ nie stiller Altstand (codex DND-T-018; claude TF-04-Fallstrick).
- Geteilte Statblöcke: Solar mit RK/TP/Aktionen; Vampirbrut eigener Block (codex T2, DND-T-028).
- Gleichnamige Kontexte ⇒ `mehrdeutig`; Inhaltskonflikt ⇒ `konflikt` mit beiden Fundstellen (codex T3/T5, DND-T-029).
- Quellen-Rundlauf: Treffer-Referenz lädt identischen Body/Quelle/Hash (codex T4; claude V9-Erweiterung Liste↔Detail).
- Editionszustände: leer/2014-only/2024-only/gemischt/Alias „5.5e" (codex T8; claude V5).

**Ebene 3 — Fachliche Golden-Suite (automatisiert, gegen bedienten Korpus):**
- Kernregeln: Vorteil/Nachteil-Aufhebung, Reaktions-Timing, Gelegenheitsangriff inkl. Zwang/Teleport-Ausnahme, Temp-TP-Nichtstapeln, Todesretter-Details, Konzentration SG-Kappe 30, Rast-Unterbrechung, Deckungs-Stapelverbot, Liegend+schwieriges Gelände (codex DND-T-001…016; claude TF-01…05/14/15/16).
- Reparatur-Regression: Umstoßen/Zweihändig, Eissturm/Göttliche Gunst/Symbol/Windwall, Schild(+2), Attributswurf ohne SG-15-Kontamination, alle 8 Meisterschaften einzeln, keine Garble-Namen, kein ToC-Treffer (claude TF-06/07, DND-001/004/009/010; codex DND-T-017/026…028/031).
- Steckbrief-Pflichtklauseln je Kategorie (Zauber: Zeit/Reichweite/Komponenten/Dauer/Effekt/Hochstufung; Monster: RK/TP/Bewegung/Werte/Aktionen; verbotene Fremdklauseln) (codex DND-003-Abnahme).
- Charakterbau: 4 False-Positive-Builds; Punktkauf-Grenzen (16 nicht kaufbar); Hintergrund-Attributsbindung; Mehrklassen ⇒ `unsupported`; drei Attributsmethoden als Wissensfrage (codex DND-T-036…041; claude TF-17/18/19).
- Version/Quelle: gezielter 2014-Abruf mit Kennzeichnung; Quellenfrage mit exakter Belegzeile ohne erfundene Seiten (claude TF-13/26; codex DND-T-042).

**Ebene 4 — Verhaltens-Evals mit echtem Client (halbautomatisiert, protokolliert):**
- Nichtwissen (Silvery Barbs), Spoiler (Strahd inkl. Folgefragen), Mehrdeutigkeit (Schild) mit Rückfrage, unvollständige Angaben (Aktionsökonomie-Frage), Aussageart-Kennzeichnung (Magisches Geschoss/Konzentration, Dissonantes Flüstern), falsche Nutzerannahme freundlich korrigieren, Kurz-vs-ausführlich, Deutsch-first-Format (claude TF-09/11/12/24/25/27; codex T19/T20, DND-T-007/025/043/044).
- Prompt-Injection: präparierter Bestandstext mit Anweisungscharakter bleibt Zitat, löst keine Toolketten aus (codex T13).

**Ebene 5 — Betrieb/Sicherheit (automatisiert wo möglich):**
- Readiness-Matrix (fehlend/korrupt/gesperrt/ungeprüft ⇒ 503) (codex T14); Backup-Restore auf leerem Host inkl. Golden-Queries (codex T18; claude Restore-Probe); Payload-/Lastbudgets auf Zielhardware (codex T15; claude V4-Latenzbudget); Serve-Container-Isolation (kein `data/private`, kein Write) (codex-Abnahme zu TECH-006); DDB-Rundlauf inkl. Header-Drop-Bilanz (claude V8; codex T16/T17); Dateizugriffs-Negativtest (Tools erreichen nur die bediente DB).

**Regressionsprinzip:** Jeder in dieser Synthese verifizierte Befund erhält vor dem Fix einen fehlschlagenden Test (rot-nach-grün-Nachweis); die Golden-Suite läuft gegen den per Manifest freigegebenen Korpus, nicht gegen beliebige lokale Stände.

---

## 21. Abnahmekriterien für externe MVP-Tests

Alle Kriterien binär (Ja/Nein), Reihenfolge = Prüfreihenfolge:

1. ☐ Frischer Checkout: dokumentierte Installation (venv + Lock/Pins) läuft ohne Zusatzwissen bis „Server antwortet auf `/ready` mit 200".
2. ☐ Ein Testbefehl führt Haupt- **und** DDB-Suite aus; Ergebnis 0 failed, 0 verdeckte Skips der DDB-Kernpfade.
3. ☐ Golden-Suite (Ebene 2+3) besteht gegen den bedienten Korpus; Korpus stimmt mit dem Quellenmanifest überein.
4. ☐ Verbindung mit dem vorgesehenen Client (Claude Custom Connector) hergestellt; `tools/list` zeigt 16 Tools mit Enums und `readOnlyHint`.
5. ☐ Zehn definierte Kernregel-Fragen (aus Ebene 3, je 5 pro Fachreview) liefern im Client korrekte, belegte 2024-Antworten.
6. ☐ „Aktionen", „Erschöpfung", „Solar", „Vampirbrut", „Schild (Gegenstand)", „Eissturm" liefern die korrekten Inhalte (P0-Verifikationsliste).
7. ☐ Unbekanntes (Silvery Barbs) ⇒ ehrliches „nicht im Bestand"; ungültige Parameter ⇒ verständlicher Parameterfehler, nie „nicht gefunden".
8. ☐ Spoiler-Probe („Wie besiege ich Strahd?" + zwei Folgefragen) wird abgelehnt; kein Playtest-/Abenteuer-Inhalt im Spielerpfad abrufbar oder alles davon sichtbar gekennzeichnet.
9. ☐ Vier Build-Negativfälle erhalten nie `legal_soweit_pruefbar`.
10. ☐ Produktionsstart ohne starkes Pfad-Token schlägt fehl; `docker compose logs` enthält das Token nicht.
11. ☐ Serve-Container hat keinen Zugriff auf `data/private` und keine Schreibmöglichkeit auf die DB.
12. ☐ `/ready` spiegelt DB-Zustand (Korrupt-Test ⇒ 503); externer Monitor eingerichtet; Off-Site-Backup existiert mit erfolgreichem Restore-Protokoll.
13. ☐ Keine offenen P0-Befunde (SYN-P0-001…007 geschlossen mit Test).
14. ☐ Bekannte offene P1-Befunde sind schriftlich dokumentiert (Datei im Repo) mit Workaround/Risikoeinordnung für die Testrunde.
15. ☐ Spielerfeste Kurzanleitung (Connector-URL, Beispielfragen, „URL nicht weitergeben", Meldeweg für falsche Antworten) liegt vor.

## 22. Abnahmekriterien für eine Veröffentlichung des MVP

Zusätzlich zu Kap. 21 (alle weiterhin erfüllt):

1. ☐ Keine offenen P0-Befunde; keine als veröffentlichungsblockierend markierten P1 (mindestens SYN-P1-002…012 geschlossen oder ausdrücklich mit Begründung zurückgestellt).
2. ☐ Automatisierte Tests umfassen: MCP-E2E über HTTP, Schema-Snapshot, Retrieval-Identität, fachliche Golden-Suite, Readiness, Log-Redaktion — als Pflicht-Gate vor jedem Deploy/Korpus-Wechsel.
3. ☐ Client-Eval-Protokoll (Ebene 4) mit definierter Bestehensquote liegt für den unterstützten Client/Modellstand vor; T10 nicht mehr „übersprungen".
4. ☐ Systemgrenzen dokumentiert und in Antworten erkennbar: RAW-Rahmen, keine Hausregeln, Build-Prüfungs-Grenzen, Aussagearten-Kennzeichnung.
5. ☐ Unterstützte Regelquellen + Editionen + Publikationsstatus je Quelle sind im Quellenmanifest dokumentiert und stimmen mit dem bedienten Korpus überein.
6. ☐ Kritische Sicherheitspunkte geschlossen: fail-fast Auth, tokenfreie Logs, read-only-Serve, kein privater Mount; Zugriff auf private Inhalte entspricht der protokollierten Eigentümer-Entscheidung.
7. ☐ Lizenz-/Quellenlage nachvollziehbar: ATTRIBUTION.md entspricht dem Ist-Zustand; CC-BY-Attribution automatisiert; DDB-Inhalte nur im entschiedenen, dokumentierten Rahmen; Reproduktionstiefe pro Lizenzklasse definiert.
8. ☐ Konfiguration reproduzierbar: Lock/Pins, Image-Digests oder dokumentierter Rebuild-Prozess, Quellen-/Korpusmanifest mit Hashes; zwei unabhängige Builds ergeben denselben Stand.
9. ☐ Fehler- und Supportwege dokumentiert: Meldeweg für falsche Antworten (O4), Log-Diagnosepfad, Restore-Runbook, Token-Rotationsprozess.
10. ☐ Mindestqualität für Regelantworten definiert und gemessen: Golden-Suite-Bestehensquote 100 % für P0-Fälle, definierte Schwelle (z. B. ≥ 95 %) für die erweiterte fachliche Suite, Latenzbudget auf Zielhardware eingehalten.

---

## 23. Offene Produkt- und Architekturentscheidungen

1. **DDB-Inhalte für die Runde (NF4):** Die Ausweitung von „privat für den Eigentümer" auf „Gruppe nutzt servierte Kaufinhalte" ist laut allen Reviews eine bewusst zu treffende, zu protokollierende Eigentümer-Entscheidung (inkl. ToS-Risiko). — *Entscheider: Betreiber.*
2. **Ravenloft-/Abenteuerquelle:** Nur Terminologie, gekennzeichnet servieren oder ganz aus dem Spielerbestand entfernen? (SYN-P0-007-Umsetzungsvariante.) — *Betreiber; fachliche Empfehlung der Synthese: bis Rollen-Trennung nicht im Spielerpfad.*
3. **Original-/Übersetzungs-Policy bei Quellkonflikten** (Vampir „weiß"/„unaware"): Welche Fassung ist normativ, wie wird der Konflikt angezeigt? — *Betreiber/Redaktion; technisch SYN-P1-009.*
4. **Identitätsmodell für gleichnamige Abschnitte:** aggregieren, Varianten zeigen oder kontextbezogen unterscheiden — Domänenentscheidung vor dem vollen `concept/variant`-Umbau (SYN-P2-002). — *offen.*
5. **Authentisierung jenseits Geheimpfad+IP-Allowlist:** OAuth-fähige Custom Connectors würden nutzerbezogenen Zugang/Widerruf erlauben; die Projektannahme „kein OAuth möglich" ist zu re-validieren. — *offen (Codex fordert, Claude-Review übernahm Projektannahme; Synthese konnte nicht final verifizieren).*
6. **Build-Prüfungs-Scope:** ehrlich auf Stufe 1 begrenzen oder Stufenfortschritt modellieren (SYN-P2-005/codex DND-006)? — *Produktentscheidung; Kurzfrist-Empfehlung: Stufe-1-Fokus mit expliziter Deklaration.*
7. **Anforderungs-Update B7:** 4-Schritt-Führung um Sprachen/Herkunfts-Pflichtwahlen ergänzen (Spec-vs-SRD-Spannung, Kap. 16 Nr. 4). — *Anforderungspflege.*
8. **Latenz-/Payload-Budgets auf dem Pi** (B9): Zielwerte festlegen, dann messen (SYN-P2-004). — *Betreiber.*

## 24. Abschließende Bewertung der MVP-Reife

**Heutiger Stand: bedingt einsatzfähig — nur für den wissenden Eigenbetrieb.** Die vier Reviews und die Synthese-Verifikation ergeben zusammen ein klares Bild: Foliant hat ein überdurchschnittlich solides Fundament (Editionsmodell, Provenienz, Import-Sicherheit, Secret-Handling, Testkultur) und gleichzeitig einen **nachgewiesen unzuverlässigen letzten Meter**: Namens-/Fuzzy-basierte Auswahl und beschädigte Chunks können falsche Regelversionen, fremde Regeltexte, unvollständige Steckbriefe und falsche Build-Freigaben erzeugen — jeweils mit überzeugender Belegzeile. Für ein System, dessen Existenzberechtigung „belegte, ehrliche Regelauskünfte" ist, ist das die definierende Lücke.

**Der Weg ist kurz und klar:** Die sieben P0-Befunde sind lokalisiert, unabhängig voneinander behebbar und überwiegend S–M-groß (nur das srd-de-Reparaturpaket und der Dedupe-Umbau sind L). Kein Befund erfordert einen Architektur- oder Technologiewechsel; ausdrücklicher Konsens beider Technikreviews ist, SQLite/FTS5 zu behalten. Nach Stufe A (P0 + Test-Gate) ist der interne Betrieb vertrauenswürdig; nach Stufe B ist die Freigabe an die Spielrunde vertretbar — gemessen an den binären Checklisten in Kap. 21/22.

**Synthese-Noten (Einordnung, keine Mittelwerte):** Technische Substanz **7/10** · Zuverlässigkeit des Antwortpfads heute **4/10** · fachliche MVP-Reife heute **4–5/10**, nach Umsetzung von Stufe A+B realistisch **7/10**. Die Differenz zwischen den Reviewern war kein Widerspruch in den Fakten, sondern in Prüftiefe und Maßstab — die Synthese übernimmt Codex' verifizierte Antwortpfad-Befunde und Claudes verifizierte Substanz-Bewertung gleichermaßen.

---

## Bestätigung der Unversehrtheit des Projekts

`git status --porcelain` nach Abschluss der Synthese zeigt ausschließlich den ungetrackten Ordner `docs/reviews/` mit den vier Einzelreviews und dieser Synthese-Datei. **Keine bestehende Projektdatei und keine der vier Einzelreviews wurde verändert.** Alle Verifikationen erfolgten lesend (Tool-Aufrufe, `mode=ro`-SQL) bzw. gegen eine synthetische Wegwerf-Fixture im sitzungs-eigenen Scratchpad außerhalb des Projekts; der Versuch, die private Datenbank zu kopieren, wurde von den Projektschutzregeln blockiert und nicht umgangen.
