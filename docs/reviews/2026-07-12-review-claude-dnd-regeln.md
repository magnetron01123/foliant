# Unabhängige D&D-Regelwerkreview: Foliant

## 1. Metadaten der Review

| Feld | Wert |
|---|---|
| Reviewer | claude |
| Review-Typ | D&D-Regelwerkreview (fachlich) |
| Datum | 2026-07-12 |
| Untersuchter Git-Commit | `5cc67289a8066ce83b3a62aa9822165b1acfacbb` („Projekt-Aufraeumen: Archiv, Doku-Refresh, Konventionen", 2026-07-11) |
| Untersuchter Branch | `main` (Arbeitsbaum zu Beginn sauber) |
| Untersuchte Datenbasis | Lokale Entwicklungs-Datenbank am Mac: 2.621 Einträge (srd-de = dt. SRD 5.2.1: 1.639; open5e-srd-2024: 982), Glossar 1.402 Begriffe. Der Live-Bestand auf dem Pi (~9.490 Einträge inkl. 10 D&D-Beyond-Bücher) war **nicht** erreichbar — Aussagen dazu stützen sich auf Code, Konfiguration und Doku. |

**Ausgeführte Prüfungen (alle lokal, lesend, nicht destruktiv):**

| Prüfung | Ergebnis |
|---|---|
| `pytest tests/test_abnahme.py test_build_pruefung.py test_editionen.py test_dubletten.py test_glossar_qualitaet.py` | **37 passed, 1 skipped** (Skip = Verhaltenstest T10, laut Testdesign manuell) |
| `python -m tests.smoke_test` (gegen echte Dev-DB) | **OK, 0 Probleme** (alle 16 Tools) |
| `python -m app.admin check` | OK (Warnung: 176 Einträge mit HTML-Resten) |
| Fachliche Inhalts-Stichproben über die echten Tools | Gelegenheitsangriff, Gepackt, Erschöpfung, Konzentration, Verstecken/Verstecken (Aktion), Feuerball, Aboleth-Statblock, Battleaxe (Mastery), Meisterschaftseigenschaften (alle 8 gesucht), Waffeneigenschaften, Hintergrund Soldat, Attributswerte (Standardsatz/Punktkosten), Talent-/Spezies-/Klassenlisten, Build-Prüfung |
| Glossar-Stichproben | spell slot, grappled, opportunity attack, weapon mastery, emanation |
| Daten-Scans | Laufkopf-Artefakte (374 Einträge), Silbentrennungs-Wortrisse (273 Einträge), beschädigte Eintragsnamen (8 Fälle), Inhaltsverzeichnis-Blob |

**Fehlgeschlagene oder nicht mögliche Prüfungen:**
- Kein Zugriff auf den Pi-Live-Bestand → die 10 DDB-Bücher (u. a. PHB 2024 EN, Basic Rules 2014, zwei Druck-PDF-Bücher) konnten inhaltlich **nicht** stichprobiert werden; für sie gelten die Mechanik-Befunde (Editionslogik, Kennzeichnung), nicht die Text-Stichproben.
- Verhaltenstests T2/T10/T12 (Modellverhalten im Chat) sind lokal nicht ausführbar — das Projekt sieht dafür selbst eine manuelle Checkliste vor.
- Ein Direktabgleich mit den gedruckten deutschen Regelwerken 2024 (PHB/DMG/MM) war nicht möglich (liegen dem Review nicht vor); Regelaussagen wurden gegen die Regelkenntnis des Reviewers (2024-Regeln, SRD 5.2/5.2.1) geprüft.

**Ausgeschlossene Inhalte (Unabhängigkeit):** Es wurden keine Dateien aus `docs/reviews` gelesen; ebenso wurden die projektinternen Bewertungs-/Auditdokumente `docs/QS-BERICHT-datenbank.md` und `docs/ABNAHME-PROTOKOLL.md` nicht inhaltlich verwendet. Alle Befunde dieser Review wurden eigenständig am Bestand, an den Tools und am Code erhoben.

---

## 2. Executive Summary

Foliant ist fachlich auf einem für einen MVP bemerkenswert soliden Stand. Die geprüften **Kernregeln der Fassung 2024 sind inhaltlich korrekt** wiedergegeben: Gelegenheitsangriff (inkl. der 2024-Neuerung „Bewegungsrate/Aktion/Bonusaktion/Reaktion als Auslöser"), Zustände (Gepackt, Erschöpfung mit kumulativen Stufen, −2×Stufe auf W20-Prüfungen, Tod bei 6), Konzentration, die Verstecken-Aktion (SG 15, Sichtlinien- und Deckungsvoraussetzungen, Zustand Unsichtbar), Feuerball (Grad 3, 45 m, 6-m-Radius, GES-Rettungswurf, 8W6), Punktkosten/Standardsatz, Hintergrund-Mechanik (+2/+1 bzw. +1/+1/+1, Obergrenze 20, festes Ursprungstalent) und die Waffenmeisterschafts-Einzelregeln (Stoßen, Plagen, Auslaugen, Verlangsamen — stichprobengeprüft korrekt). Die Editionstrennung 2024/2014 ist technisch erzwungen und fachlich sauber; jede Auskunft trägt Quelle, Seite und Regelversion.

Dem stehen **drei hohe Befunde** gegenüber:

1. **DND-001:** Im deutschen SRD-Bestand ist die Meisterschaftseigenschaft **Topple (dt. „Umwerfen") als eigener Eintrag verloren gegangen** — ihr Regeltext klebt ohne Überschrift am Eintrag „Zweihändig". Der Bestand behauptet damit faktisch, *jede zweihändige Waffe* könne bei einem Treffer umwerfen (KON-Rettungswurf → Liegend). Das ist die gefährlichste Fehlerklasse: ein plausibel klingender, falscher Regeltext in der kanonischen deutschen Quelle.
2. **DND-002:** Der DDB-Sync lädt **Abenteuer-, Setting- und Playtest-Bücher ohne strukturelle Kennzeichnung** in den Bestand (nur Premade-Character-Pakete sind ausgeschlossen). Playtest-/UA-Material würde als reguläre Regel erscheinen; der Spoiler-Schutz für Abenteuerinhalte hängt allein am Modellverhalten und am Quellentitel.
3. **DND-003:** Ein falscher `kategorie`-/`quelle`-Parameterwert (z. B. englisch `"spell"`) erzeugt ein **falsches „Nichts im Bestand"** samt der Anweisung an das Modell, genau das dem Spieler ehrlich mitzuteilen — das Ehrlichkeitsversprechen (B1/B2) wird so zum Falsch-Negativ-Verstärker.

Dazu kommen mittlere Datenqualitätsbefunde aus der PDF-Extraktion (zerrissene Statblock-Tabellen bei korrekten Werten; Laufkopf „Systemreferenzdokument 5.2.1" in 374 Einträgen; 273 Einträge mit Wortrissen), Glossarlücken bei 2024-Kernbegriffen (weapon mastery, emanation) und die suffixbedingte Mehrdeutigkeit häufiger Nachschlagebegriffe („Erschöpfung (Zustand)"). Nichts davon stellt das Konzept infrage — die Grounding-, Zitat- und Versionsmechanik ist fachlich genau richtig gebaut. Mit der Behebung von DND-001 und DND-003 sowie einer Kennzeichnungslösung für DND-002 ist Foliant fachlich reif für die eigene Spielrunde. Gesamtnote fachliche MVP-Reife: **7/10** (Kapitel 18).

---

## 3. Untersuchungsumfang und Vorgehen

1. **Anspruch ermitteln:** Anforderungskatalog (`docs/foliant-anforderungen.md`, Rev. 8), README, PROJEKT-UEBERSICHT, technisches Konzept, CLAUDE.md, Roadmap — daraus den beanspruchten fachlichen Umfang und die Nicht-Ziele abgeleitet (Kapitel 4).
2. **Regelwissen sichten:** Datenmodell (`db/schema.sql`), Importer-Regeln je Quelle (`importer/import_markdown.py`: SPLIT/MERGE/BEREINIGUNG; `importer/import_open5e.py`; DDB-Kette inkl. `importer/ddb_exporter/katalog.py`), Macken-Register (`app/bekannte_macken.py`), Stil-/Verhaltensanweisungen (`config/stil.py`, `docs/CLAUDE-PROJEKT-ANWEISUNG.md`), alle 16 Tool-Beschreibungen und die Regelkonstanten der Build-Prüfung (`app/tools/charakter.py`).
3. **Fachliche Tests ausführen:** Abnahme-Suite (T1–T12 serverseitig), Regelwert-/Editions-/Dubletten-/Glossar-Tests, Smoke-Test gegen die echte Dev-DB.
4. **Inhalts-Stichproben über die echten Tools:** gezielte Nachschlagefragen quer durch Kampfregeln, Zustände, Zauber, Monster, Ausrüstung, Charakterbau (Liste in den Metadaten), jeweils gegen die 2024-Regeln bewertet.
5. **Systematische Daten-Scans** auf Extraktionsschäden (Namens-Garbles, Wortrisse, Laufköpfe, verschmolzene Einträge) mit Quantifizierung.
6. Keine Änderungen an Code, Daten, Tests oder Doku; einzige Schreiboperation ist diese Review-Datei.

---

## 4. Erkannter Regelumfang des Projekts

**Beansprucht (laut Anforderungen/README, im Code verifiziert):**
- **Regeln nachschlagen** (Kampf *und* außerhalb): Volltextsuche + vollständiger Regelabschnitt (`foliant_suche_regeln`, `foliant_hol_regel`) — abgedeckt sind u. a. W20-Prüfungen, Vorteil/Nachteil, Aktionen (inkl. Aktionsliste als Einzeleinträge), Reaktionen, Bewegung, Deckung, Sicht/Verschleierung, Zustände (alle 15 als „… (Zustand)"-Einträge im Regelglossar), Konzentration, Rasten, Todesrettungswürfe, Gefahren (Dehydrierung, Ersticken …), Reise, soziale Interaktion, Werkzeuge, Handwerken.
- **Steckbriefe:** Zauber (387 dt. + Open5e-Duplikate), Monster (341 dt. Statblocks), Gegenstände inkl. Waffen/Rüstungen mit 2024-Meisterschaftseigenschaften (Open5e mergt Mastery je Waffe in den Gegenstandseintrag).
- **Charaktererstellung:** Options-Listen (Klassen mit Unterklassen, Spezies, Hintergründe, Talente in vier 2024-Kategorien), Detailabrufe mit Zusammenführung der Unterabschnitte (Speziesmerkmale, Abstammungen), Attributswert-Methoden (Standardsatz, Punktkosten — beide am Bestand belegt) und eine **Build-Prüfung** (Existenz der Optionen strikt 2024, Unterklassen-Stufe und -Zugehörigkeit aus der Klassentabelle, Attributsmethoden, Hintergrund-Erhöhungen inkl. Obergrenze 20, Waffenbeherrschungs-Anzahl und -Duplikate) mit explizit deklarierten Grenzen (keine Zauberwahl-, Fertigkeiten-, Multiclassing-, Talentvoraussetzungs-Prüfung).
- **Begriffsübersetzung DE↔EN** inkl. Abkürzungen (AoO, HP, RK, SG …) mit Offiziell-Kennzeichnung (`*`-Regel).

**Ausdrücklich nicht beansprucht (§8, im Code respektiert):** Kampagnen-/Abenteuerinhalte und Spoiler (Verhaltensregel B6/Spoiler-Schutz als oberste Regel), Rollentrennung SL/Spieler, DDB-*Charakter*-Abruf, Würfeln, Initiative-Tracker, Hausregeln, Charakterspeicherung. Multiclassing wird nachschlagbar sein, sobald die Quelle es enthält, aber von der Build-Prüfung ausdrücklich nicht geprüft (ehrlich deklariert).

**Arbeitsteilung (fachlich wichtig):** Foliant ist bewusst **keine Regel-Engine**, sondern liefert belegte Regel*texte* plus wenige harte Prüfungen; die Regelanwendung (Interaktion mehrerer Regeln, specific-beats-general) leistet das Sprachmodell auf Basis der gelieferten Texte. Diese Grenze ist dokumentiert und in den Tool-Ausgaben verankert.

---

## 5. Erkannte D&D-Versionen und Quellen

| Quelle | Sprache | Edition | Typ | Präzedenz | Kennzeichnung |
|---|---|---|---|---|---|
| SRD 5.2.1 (Deutsch), PDF | de | 2024 | Primärquelle (offiziell, CC-BY-4.0) | 10 (höchste) | `quelle`/`seite`/`edition` an jedem Eintrag |
| DDB-Bücher (10 Stück, u. a. PHB 2024 EN, Basic Rules 2014, 2 Druck-PDF-Bücher) | en | autoritativ je Buch (aus DDB-Buch-DB; nie geraten) | Primärquelle (privat lizenziert) | 40–45 | dito; `lizenz='privat'` |
| Open5e `srd-2024` (API, einmalig importiert) | en | 2024 | **Sekundärquelle** (Community-Aggregation des SRD 5.2) | 60 | dito; Titel enthält „(Open5e)" |
| dnddeutsch.de-Glossar + kuratierte SRD-Begriffspaare | de/en | Begriffs-, nicht Regelebene | Terminologiequelle | — | `offiziell`-Flag, Herkunft, `edition_quelle` je Begriff |

- **Editionsmodell:** `edition` ist Pflichtfeld (2024/2014), Standard aller Auskünfte ist 2024; andere Fassungen erscheinen ausschließlich getrennt (`aeltere_staende`/`andere_fassungen`) und Detailabrufe ersetzen eine explizit angeforderte Edition nie still. Nur-2014-Inhalte werden mit Anpassungshinweis geliefert (B5) — im Test verifiziert.
- **Playtest/UA, Abenteuer, Setting, Drittanbieter:** Der DDB-Sync schließt **nur Premade-Character-Pakete** aus; Abenteuer-/Setting-/Playtest-Kategorien werden geladen und lediglich beim Exportlauf mit einem Konsolen-Hinweis versehen (→ DND-002). Echte Drittanbieterinhalte (Non-WotC) sind derzeit keine im Bestand; Open5e ist auf `srd-2024` beschränkt (offizieller SRD-Inhalt in Community-Transkription).
- **Hausregeln:** nicht vorhanden, nicht vorgesehen (spätere Stufe A4) — korrekt abgegrenzt.
- **Terminologie ≠ Regelversion:** Begriffe aus 2014-Büchern gelten bewusst als editionsübergreifend offiziell (S7/V6) und tragen intern ihre Herkunft (`edition_quelle`) — fachlich die richtige Entscheidung, im Glossar nachvollziehbar umgesetzt.

---

## 6. Fachliche Stärken

1. **Stichproben-Korrektheit der 2024-Kernregeln.** Alle inhaltlich geprüften Regeltexte entsprechen der Fassung 2024, inklusive der Punkte, an denen 2014-Vorwissen scheitern würde: Gelegenheitsangriff mit dem 2024-Auslöserkatalog; Verstecken als SG-15-Aktion mit Zustand *Unsichtbar*; Erschöpfung als −2×Stufe auf W20-Prüfungen (statt der 2014-Stufentabelle); Waffenmeisterschaften als Eigenschafts-Einzelregeln; Hintergrund als Quelle der Attributserhöhungen (+2/+1 bzw. +1/+1/+1, Obergrenze 20) und des festen Ursprungstalents — genau die 2024-Verlagerung weg von der Spezies.
2. **Version und Beleg an jeder Auskunft.** Quelle · Seite · Regelversion stehen in jeder Detailantwort; die Seitenangaben stammen aus PDF-Seitenmarkern und stimmen in der Stichprobe mit der gedruckten Seitenzahl überein (Feuerball: Fußzeile „139" = zitierte S. 139). Antworten sind auf konkrete Bestandseinträge rückführbar.
3. **Ehrlichkeit als Ausgabeformat.** Leere Befunde liefern einen expliziten „Nichts im Bestand — nicht aus Allgemeinwissen antworten"-Hinweis; Mehrdeutigkeit liefert Kandidaten mit Unterscheidungsmerkmalen statt einer geratenen Antwort (bei „Gepackt" fachlich vorbildlich: *Zustand* und *„Gepackt halten"-Regel* als getrennte Kandidaten); Nur-Altstand wird als solcher etikettiert.
4. **Build-Prüfung mit deklarierten Grenzen und echten Belegen.** Jede Teilprüfung zitiert den Bestandseintrag, auf dem sie beruht; Regelkonstanten (Standardsatz, 27 Punkte, Verteilungsregel) werden zur Laufzeit am Bestand verifiziert statt aus Modellwissen gesetzt; „unvollständig" ist ausdrücklich kein Legalitätsnachweis. Das ist die richtige fachliche Demut für ein Tisch-Hilfsmittel („Hilfe, keine letzte Instanz — der Spielleiter entscheidet").
5. **Zweisprachigkeit mit Offiziell-Disziplin.** Die `*`-Kennzeichnung inoffizieller Übersetzungen, die Abkürzungsbrücken (AoO→Gelegenheitsangriff→Opportunity Attacks über zwei Glossar-Hops) und die Flexions-Normalisierung (Singular findet Plural-Glossarzeile) sind getestet und funktionieren in der Praxisprobe.
6. **Spoiler-Schutz als oberste Verhaltensregel** über drei Kanäle (Server-Instruktionen, Tool-Beschreibungen, Tool-Ausgaben) plus Copy-Paste-Projektanweisung — die bestmögliche Absicherung, solange keine strukturelle Rollentrennung existiert.
7. **Bewusster Umgang mit bekannten Datenfallen:** Statblock-Kästen werden nicht zur Gliederung, Talent-Kategorien kommen aus der Typzeile statt aus fehleranfälligen Breadcrumbs, Options-Listen filtern Kapitel-Header — das Projekt kennt die PDF-Fallen und dokumentiert sie (`app/bekannte_macken.py`).

---

## 7. Kritische und hohe Regelprobleme

Kein Befund wurde als „Kritisch" eingestuft (kein flächendeckend falsches Regelbild). Drei hohe Befunde:

### DND-001 — Topple-Meisterschaft ohne Überschrift in „Zweihändig" verschmolzen (falsche Regelaussage im Bestand)

| | |
|---|---|
| Schweregrad | **Hoch** |
| Regelbereich | Waffen / Waffenmeisterschaft (2024-Kernmechanik) |
| Datei/Stelle | Bestand `srd-de`, Eintrag `name_de='Zweihändig'` (kategorie `gegenstand`, S. 103); Ursache: Heading-Verlust bei der PDF-Extraktion (`importer/import_markdown.py`, keine BEREINIGUNG-Regel für diese Stelle) |
| Eindeutigkeit | **Eindeutig** (nachgewiesen am Bestand) |

**Vorhandene Struktur:** Der Eintrag „Zweihändig" (Kontext „… > Meisterschaftseigenschaft") enthält zwei fusionierte Texte: (1) die Waffeneigenschaft *Zweihändig* („müssen mit zwei Händen geführt werden") und (2) — ohne jede Überschrift — den vollständigen Regeltext der Meisterschaftseigenschaft *Topple*: „Wenn du eine Kreatur mit dieser Waffe triffst, kannst du sie zu einem Konstitutionsrettungswurf (SG 8 plus Attributsmodifikator … plus Übungsbonus) zwingen. Misslingt der Wurf, … Zustand Liegend." Ein eigener Eintrag für Topple (dt. vermutlich „Umwerfen") existiert nicht; die Kontextliste der Meisterschaftseigenschaften enthält nur 7 der 8 Eigenschaften (Auslaugen, Einkerben, Plagen, Spalten, Stoßen, Streifen, Verlangsamen) plus das fehlplatzierte „Zweihändig".

**Fachliches Problem:** (a) Der Bestand behauptet de facto, die *Eigenschaft Zweihändig* habe einen Umwerf-Effekt — falsch; Topple ist eine Meisterschaftseigenschaft bestimmter Waffen (z. B. Kriegshammer, Streitaxt/Battleaxe, Kampfstab) und nur mit dem Klassenmerkmal Waffenbeherrschung nutzbar. (b) Die achte Meisterschaftseigenschaft ist unter ihrem deutschen Namen **nicht auffindbar**.

**Auswirkung auf Antworten:** „Was macht die Eigenschaft Zweihändig?" → das Modell liest den fusionierten Text und kann einen KON-Rettungswurf-Effekt für alle Zweihandwaffen ausgeben. „Was macht die Meisterschaftseigenschaft Umwerfen/Topple?" → auf Deutsch kein Treffer (ehrliches „nicht gefunden" wäre hier inhaltlich falsch, denn die Regel steht im Bestand — nur unauffindbar); Ausweichtreffer wäre nur der englische Open5e-Waffentext.

**Besseres Vorgehen:** In `BEREINIGUNG["srd-de"]` die verlorene Überschrift vor dem Topple-Absatz wieder einsetzen (Muster existiert bereits für efota-Kapitelzäune), den „Zweihändig"-Eintrag in den Eigenschaften-Kontext zurückholen, Re-Import, und einen Smoke-Check „alle 8 Meisterschaftseigenschaften als Einträge vorhanden" ergänzen. Zusätzlich prüfen, ob die Eigenschaft *Reichweite* (Reach) denselben Schaden hat (in der Eigenschaften-Liste fehlt sie; siehe Kapitel 17, offene Frage 3).

**Regelversion/Quelle:** 2024; SRD 5.2.1 (Deutsch), S. 103 (Meisterschaftseigenschaften) — englisches Pendant: SRD 5.2 „Mastery Properties/Topple".

**Beispiel-Nutzerfrage:** „Mein Kämpfer nutzt einen Zweihänder — kann ich Gegner mit der Eigenschaft Zweihändig umwerfen?" (Gefahr: Bestand „bestätigt" das.)

### DND-002 — Playtest-/Abenteuer-/Setting-Inhalte ohne strukturelle Kennzeichnung im Bestand

| | |
|---|---|
| Schweregrad | **Hoch** (strukturelle Lücke; Eintritt hängt vom Buchbesitz ab) |
| Regelbereich | Quellen-/Inhaltsklassen (UA/Playtest, Abenteuer, Setting) |
| Datei/Stelle | `importer/ddb_exporter/katalog.py` (`klassifiziere`, `_HINWEIS_KATEGORIEN`, `_SKIP_NAME_MUSTER`), `importer/ddb_exporter/cli.py` (`cmd_sync` — `grund`/`hinweis` werden nur gedruckt), `db/schema.sql` (kein Inhaltsart-Feld) |
| Eindeutigkeit | **Eindeutig** als Mechanik (Code); Ausmaß im Live-Bestand nicht prüfbar |

**Vorhandene Struktur:** Der Sync importiert *alle* eigenen DDB-Bücher außer Premade-Character-Paketen — ausdrücklich auch Kategorien „Adventures", „Campaign/Setting", „Critical Role" und **„Playtest"**. Die Klassifizierung erzeugt zwar einen Hinweis („Kampagnen-/Setting-/Playtest-Inhalt … bewusst geladen"), dieser wird aber **nur auf der Konsole ausgegeben** und weder im Artefakt-Manifest noch in der `quellen`-Tabelle noch in den Tool-Ausgaben persistiert. Im Bestand ist ein Playtest-Eintrag von einem Regelwerks-Eintrag nur am Quellentitel unterscheidbar.

**Fachliches Problem:** (a) **Playtest/UA** ist kein finales Regelmaterial; als normale 2024-Regel serviert, verletzt es die eigene Leitlinie „keine stille Vermischung von Regelständen" auf der Inhaltsarten-Achse. Eine UA-Unterklasse erschiene gleichberechtigt in `foliant_liste_klassen`. (b) **Abenteuer-Lore** landet als `regel`-Einträge in der Suche; der Spoiler-Schutz (oberste Verhaltensregel) muss dann allein vom Modell geleistet werden, das den Abenteuercharakter nur am Quellentitel im Zitat erkennen kann. Die Eigentümer-Entscheidung „alle Bücher für die Terminologie" ist dokumentiert und legitim — es fehlt die *Kennzeichnung*, nicht die Berechtigung.

**Auswirkung auf Antworten:** „Welche Unterklassen gibt es für den Schurken?" → eine Playtest-Unterklasse würde unmarkiert neben PHB-Material gelistet. „Was weißt du über [Abenteuer-NSC]?" → die Suche liefert Lore-Treffer; ob das Modell ablehnt, hängt am Verhaltenskanal, nicht an den Daten.

**Besseres Vorgehen:** Inhaltsart als Datenfeld mitführen: `quellen.inhaltsart` (`regelwerk | abenteuer | setting | playtest`) aus `kategorie_ddb` ableiten, ins Manifest schreiben, beim Import setzen; Tool-Ausgaben ergänzen (z. B. `hinweis_inhaltsart: "Playtest-Material — nicht final"` bzw. `"Abenteuerband — Spoiler-Schutz beachten"`); Options-Listen Playtest-Quellen ausblenden oder markieren. Kurzfristige Minimallösung: Playtest-Kategorie vom Sync ausnehmen (wie Premade Characters).

**Regelversion/Quelle:** editionsunabhängig; betrifft F5-Importe. **Beispiel-Nutzerfrage:** „Ist die Unterklasse X offiziell?" — derzeit könnte die Antwort „ja, 2024, Quelle: <Playtest-Buch>" lauten, ohne den Playtest-Status zu nennen.

### DND-003 — Falsches „Nichts im Bestand" bei ungültigem `kategorie`-/`quelle`-Parameter

| | |
|---|---|
| Schweregrad | **Hoch** |
| Regelbereich | Auskunftsehrlichkeit (B1/B2) — betrifft alle Regelbereiche |
| Datei/Stelle | `app/tools/nachschlagen.py` (`foliant_suche_regeln` reicht `kategorie`/`quelle` ungeprüft durch), `app/db.py` (`_roh_suche`/`_fuzzy_treffer` filtern kommentarlos) |
| Eindeutigkeit | **Eindeutig** (reproduziert) |

**Vorhandene Struktur:** `edition` wird validiert (unbekannter Wert → strukturierter `fehler` mit den verfügbaren Versionen). `kategorie` und `quelle` nicht: `foliant_suche_regeln("Feuerball", kategorie="spell")` liefert `treffer: []` plus den Ehrlichkeits-Hinweis „Nichts im Bestand gefunden … antworte NICHT aus Allgemeinwissen" — obwohl der Feuerball mit `kategorie="zauber"` zwei Treffer hat. Die gültigen Kategorien stehen nur im Beschreibungstext, nicht als Schema-Einschränkung.

**Fachliches Problem:** Das System instruiert das Modell aktiv, dem Spieler ein falsches „dazu finde ich nichts — eventuell fehlt ein Buch" zu geben. Naheliegende Fehlerquellen: englische Kategorienamen (`spell`, `monster`→ok, `item`, `race`), Buchtitel statt Quellkürzel. Für ein System, dessen wichtigstes Versprechen die ehrliche Negativauskunft ist (T2), ist ein systematisch erzeugbares Falsch-Negativ die schädlichste Antwortklasse nach der Halluzination.

**Auswirkung auf Antworten:** „Gibt es den Zauber Feuerball?" → „❌ Nicht im Bestand" trotz vorhandenem Eintrag, wenn das Modell die Kategorie englisch übergibt.

**Besseres Vorgehen:** Ungültige Kategorie/Quelle wie eine ungültige Edition behandeln: strukturiertes `fehler`-Feld mit der gültigen Werteliste plus Hinweis „Parameter korrigieren — das ist KEIN ‚nicht gefunden'"; zusätzlich die Kategorie im Tool-Schema als feste Werteliste deklarieren, damit der Client den Fehlaufruf abfängt.

**Regelversion/Quelle:** versionsunabhängig. **Beispiel-Nutzerfrage:** „Was macht Fireball?" (Modell wählt `kategorie="spell"`).

---

## 8. Mittlere und niedrige Regelprobleme

### DND-004 — Zerrissene Statblock-Tabellen im deutschen Monster-Bestand (Werte korrekt, Struktur fehleranfällig)

- **Schweregrad:** Mittel · **Regelbereich:** Monsterwerte · **Eindeutigkeit:** eindeutig (Stichprobe), Ausmaß geschätzt
- **Stelle:** Bestand `srd-de`, Monster-Einträge (geprüft: Aboleth, S. 333-Bereich); Ursache PDF-Tabellenextraktion (bekannte Macke „zerrissene Statblöcke")
- **Befund:** Der Aboleth-Kopfblock kommt als zerrissene Markdown-Tabelle an: `|**TP**150 (20W1|0+40)|` (Trefferwürfel über Zellgrenze gesplittet), `|**Bewegungsrat**|**e**3 m|`, `|**I**|**nitiative**+7|(17)|`. Die **Werte selbst sind korrekt** (RK 17, TP 150 (20W10+40), STR 21/+5/+5 … CHA 18/+4/+4, HG 10, ÜB +4, Dunkelsicht 36 m, PW 20 — gegen die 2024-Werte geprüft), aber die Struktur zwingt das Modell zur Rekonstruktion.
- **Auswirkung:** Risiko verlesener Werte in Antworten („20W1" statt „20W10"), besonders bei komplexen Blöcken oder wenn das Modell die Tabelle wörtlich wiedergibt. Merkmale/Aktionen (Fließtext) sind sauber.
- **Besseres Vorgehen:** Statblock-Köpfe beim srd-de-Import normalisieren (Zellrisse an bekannten Mustern kitten: `W1|0` → `W10`, `Bewegungsrat|e`), alternativ Kopfblock als Schlüssel-Wert-Zeilen re-serialisieren; Kreuz-Stichprobe von ~10 Monstern (TP/RK/Rettungswürfe) als Abnahme.
- **Version/Quelle:** 2024, SRD 5.2.1 (Deutsch), Kapitel „Monster von A–Z". **Beispielfrage:** „Wie viele Trefferpunkte und welche Trefferwürfel hat ein Aboleth?"

### DND-005 — Laufkopf und Silbentrennungs-Wortrisse im Regeltext (374 bzw. 273 Einträge)

- **Schweregrad:** Mittel · **Regelbereich:** alle (Textqualität der Primärquelle) · **Eindeutigkeit:** eindeutig (gezählt)
- **Stelle:** Bestand `srd-de`; Ursache PDF-Extraktion ohne Kopfzeilen-/Trennstrich-Bereinigung für diese Quelle
- **Befund:** 374 von 1.639 srd-de-Einträgen enthalten den einbackenen Seitenkopf „Systemreferenzdokument 5.2.1" plus fett gesetzter Seitenzahl **mitten im Regeltext** (z. B. im Feuerball zwischen Statzeile und Beschreibung). 273 Einträge enthalten echte Wortrisse mit Non-Breaking-Hyphen („Geschick‑ lichkeitswurf", „Übungs‑ bonus", „Angriffs‑ würfen"); daneben existieren legitime Ergänzungsstriche („Vor‑ oder Nachteile"), die erhalten bleiben müssen.
- **Auswirkung:** Wörtliche Regelzitate wirken beschädigt; die fette Seitenzahl kann als Regelwert fehlgedeutet werden; Volltextsuche auf Body-Ebene verfehlt zerrissene Komposita. Eintragsnamen sind (bis auf DND-009) intakt, daher bleiben Kern-Lookups funktional.
- **Besseres Vorgehen:** Zwei BEREINIGUNG-Regeln für `srd-de`: (1) Zeilen/Fragmente `Systemreferenzdokument 5.2.1` + isolierte `**<Zahl>**`-Folgezeile entfernen (das Seitenzitat kommt ohnehin aus den Markern); (2) Wortrisse `‑ ` nur dann kitten, wenn das zusammengesetzte Wort im Dokument belegt ist und das Folgewort keine Konjunktion ist (Mechanik existiert analog in `_repariere_fragmente`/efota-Join). Danach Re-Import + Stichprobe.
- **Version/Quelle:** 2024, SRD 5.2.1 (Deutsch). **Beispielfrage:** „Zitiere mir bitte wörtlich die Regel zur Verstecken-Aktion."

### DND-006 — Glossarlücken bei 2024-Kernbegriffen; Terminologie-Divergenz „Waffenmeisterschaft" unaufgelöst

- **Schweregrad:** Mittel · **Regelbereich:** Terminologie/zweisprachige Suche · **Eindeutigkeit:** eindeutig
- **Stelle:** Glossar-Bestand (Seeding via `importer/import_glossar.py`: `weapon mastery` und `emanation` stehen in `KERNBEGRIFFE_EN`, liefern aber keine Glossarzeile — dnddeutsch kennt sie offenbar nicht, und `SRD_2024_BEGRIFFSPAARE` enthält keine Paare dafür)
- **Befund:** `foliant_uebersetze_begriff("weapon mastery")` und `("emanation")` → „kein Glossar-Eintrag" (ehrlich, aber vermeidbar). Die Suche „weapon mastery" liefert nur englische Open5e-Waffen; die deutschen Regel-Einträge („Waffenbeherrschung" in Klassenmerkmalen, „Meisterschaftseigenschaft", „Ausströmung (Wirkungsbereich)") werden nicht verbrückt. Zusätzlich divergiert die offizielle Terminologie: das dt. SRD 5.2.1 verwendet „Waffenbeherrschung"/„Meisterschaftseigenschaft", während der Anforderungskatalog (§16, dnddeutsch-Beleg) für das dt. PHB 2024 „Waffenmeisterschaft" nennt. Eine Suche nach „Waffenmeisterschaft" endet im Fuzzy-Fallback bei „Waffe/Waffen" und verfehlt beide Zielentitäten.
- **Auswirkung:** Ausgerechnet zwei prägende 2024-Neuerungen (Weapon Mastery, Emanation) sind zweisprachig schlecht auffindbar; Spieler mit PHB-Terminologie („Waffenmeisterschaft") erhalten irreführende Treffer.
- **Besseres Vorgehen:** Kuratierte Paare ergänzen (bestandsbelegt, Muster existiert): `Weapon Mastery ↔ Waffenbeherrschung` (SRD-Begriff), zusätzlich `Waffenmeisterschaft` als zweite offizielle Zeile (PHB-Begriff; S8 regelt die Auswahl), `Mastery property ↔ Meisterschaftseigenschaft`, `Emanation ↔ Ausströmung`; dazu die 8 Eigenschaftsnamen (Spalten/Cleave, Streifen/Graze, Einkerben/Nick, Stoßen/Push, Auslaugen/Sap, Verlangsamen/Slow, Umwerfen/Topple, Plagen/Vex). Smoke-Deutsch-Term-Check um diese Begriffe erweitern.
- **Version/Quelle:** 2024; SRD 5.2.1 (Deutsch) S. 103, dt. PHB-2024-Glossar (laut §16). **Beispielfrage:** „Was ist Weapon Mastery auf Deutsch, und wie funktioniert es?"

### DND-007 — Klammer-Suffixe verhindern Exakt-Treffer häufiger Nachschlagebegriffe

- **Schweregrad:** Mittel · **Regelbereich:** Zustände/Aktionen (häufigste Tischfragen) · **Eindeutigkeit:** eindeutig
- **Stelle:** `app/tools/nachschlagen.py` `_eintrag_namen` (kennt nur das Unterklassen-Präfixschema, keine Klammer-Suffixe); Bestandsnamen „Erschöpfung (Zustand)", „Verstecken (Aktion)", „Unterernährung (Gefahr)" …
- **Befund:** `foliant_hol_regel("Erschöpfung")` und `("Verstecken")` liefern `mehrdeutig` mit Kandidaten, obwohl es genau einen fachlich gemeinten Haupteintrag gibt; erst der exakte Name „Erschöpfung (Zustand)" trifft direkt. Die Kandidatenliste enthält die richtige Lösung an Position 1 (kein Falschinhalt), kostet aber einen zweiten Tool-Aufruf und riskiert Fehlgriffe des Modells.
- **Auswirkung:** Verzögerte oder umständliche Antworten bei den häufigsten Spielbegriffen (alle 15 Zustände tragen den Suffix); bei knappem Modellverhalten droht die Wahl eines Nebeneintrags („Unterernährung (Gefahr)" zu „Erschöpfung", weil deren Body Erschöpfungsstufen vergibt).
- **Besseres Vorgehen:** In `_eintrag_namen` (und der Dubletten-/Options-Logik) den Namen zusätzlich ohne Klammerzusatz als Exakt-Variante führen („Erschöpfung (Zustand)" ⇒ auch „erschöpfung"); Kollisionsfälle (Zauber „Leicht" vs. Eigenschaft „Leicht") bleiben durch die Kategorien getrennt.
- **Version/Quelle:** 2024, SRD 5.2.1 (Deutsch), Regelglossar. **Beispielfrage:** „Was bewirkt Erschöpfung?"

### DND-008 — Keine Anweisung zur Kennzeichnung von Aussagearten (Regeltext vs. Ableitung vs. SL-Entscheid)

- **Schweregrad:** Mittel · **Regelbereich:** Antwortdisziplin/Interpretation · **Eindeutigkeit:** interpretationsabhängig
- **Stelle:** `config/stil.py`, `docs/CLAUDE-PROJEKT-ANWEISUNG.md` (beide regeln Quelle/Version/Grounding, aber nicht die Aussageart)
- **Befund:** Die Verhaltensregeln erzwingen Beleg, Version, Deutsch-first und ehrliche Lücken — aber es gibt keine Anweisung, in Antworten zu unterscheiden zwischen (a) wiedergegebenem Regeltext, (b) Zusammenfassung, (c) logischer Ableitung aus mehreren Regeln, (d) offener Regelfrage/SL-Entscheid. RAW als Rahmen wird nur im B8-Kontext („keine Hausregeln") erwähnt. Sage Advice/Errata/RAI sind nicht im Bestand (nicht beansprucht — konsistent), aber das Modell wird bei Wechselwirkungsfragen zwangsläufig ableiten und könnte Ableitungen im selben Belegformat wie Regeltext präsentieren.
- **Auswirkung:** Bei Kombifragen („Kann ich als Reaktion einen Gelegenheitsangriff mit einer geworfenen Waffe machen?") ist für Spielende nicht erkennbar, wo der Regeltext endet und die Schlussfolgerung beginnt — die Belegzeile suggeriert Quellenautorität für die gesamte Antwort.
- **Besseres Vorgehen:** Zwei Sätze in `stil.py` **und** der Projektanweisung (synchron): „Kennzeichne Schlussfolgerungen, die nicht wörtlich im Bestand stehen, als Ableitung (z. B. ‚Ableitung aus X + Y'). Wo die Regeln eine Situation nicht eindeutig regeln, sag das und verweise auf die Entscheidung der Spielleitung (⚖️)." Optional ein eigenes Emoji im Format-Schema.
- **Version/Quelle:** versionsunabhängig. **Beispielfrage:** „Zählt das Absetzen vom Greifvogel als Bewegung, die Gelegenheitsangriffe auslöst?"

### DND-009 — Beschädigte Eintragsnamen (Kapitälchen-Garbles, verschmolzene Wörter)

- **Schweregrad:** Niedrig · **Regelbereich:** einzelne Regel-/Gegenstandseinträge · **Eindeutigkeit:** eindeutig (8 Fälle gezählt)
- **Stelle:** Bestand `srd-de`, Namen: „Ausrüstung verKAufen", „improvisierte wAffen", „zAubern in rüstung", „einen wirKenden zAuber identifizieren", „regeln für mAgische gegenstände", „Feuerschale der FeuerelementarHerrschaft", „Übungim Umgangmit Ausrüstung", „Übungim Umgangmit Waffen"
- **Befund/Auswirkung:** Die Kapitälchen-Macke betrifft entgegen der Macken-Notiz („nur Kosmetik im Body") auch **Eintragsnamen**, darunter einen magischen Gegenstand („Feuerschale der Feuerelementarherrschaft"). Anzeige-Namen in Antworten wirken fehlerhaft; die diakritika-insensitive Suche findet sie zwar (case-insensitiv), aber Exakt-/Anzeigelogik leidet.
- **Besseres Vorgehen:** 8 kuratierte Namens-Fixes in `BEREINIGUNG["srd-de"]` (dokumentverifiziert, wie die frhof-PLAIN_ZEILEN); Macken-Notiz aktualisieren.
- **Version/Quelle:** 2024, SRD 5.2.1 (Deutsch). **Beispielfrage:** „Was macht eine Feuerschale der Feuerelementarherrschaft?"

### DND-010 — 22-kB-Inhaltsverzeichnis als Regel-Eintrag (Suchrauschen mit Seitenzahlen)

- **Schweregrad:** Niedrig · **Regelbereich:** Suche/Monster · **Eindeutigkeit:** eindeutig
- **Stelle:** Bestand `srd-de`, Eintrag „Verzeichnis der Wertekästen" (kategorie `regel`, 22.431 Zeichen); Skip-Regel in `SPLIT_REGELN["srd-de"]` erfasst nur die Kinder, nicht den Kapitelkopf selbst
- **Befund/Auswirkung:** Das komplette Statblock-Verzeichnis (alle Monsternamen + Seitenzahlen) ist als durchsuchbarer „Regel"-Eintrag im Bestand; Monster-Suchen erhalten einen inhaltsleeren Rauschtreffer, dessen Auszug wie eine Regelfundstelle aussieht.
- **Besseres Vorgehen:** Kapitelkopf per Namens-Skip verwerfen (Kategorie `None` auch bei Selbst-Match) oder per BEREINIGUNG entfernen; Re-Import.
- **Version/Quelle:** 2024, SRD 5.2.1 (Deutsch). **Beispielfrage:** „Wo finde ich die Werte des Schattendrachen?" (Verzeichnis-Treffer statt Statblock möglich.)

### DND-011 — Ranking-Randfall: Glossar-Präfixtreffer verdrängt Kernregel („Verstecken" → „Hide Armor")

- **Schweregrad:** Niedrig · **Regelbereich:** Suche (Aktionen) · **Eindeutigkeit:** eindeutig
- **Stelle:** `app/db.py` Ranking (`_dedupe_und_sortiere`: Präfix-Rang nutzt alle Glossar-Alternativen gleichwertig)
- **Befund:** Suche „Verstecken" listet den Gegenstand „Hide Armor" (über die Glossar-Alternative „Hide" als Präfixtreffer) **vor** „Verstecken (Aktion)" und „Sich verstecken". Kein Falschinhalt — die richtigen Einträge folgen direkt —, aber der erste Treffer einer Kernfrage ist eine Rüstung.
- **Besseres Vorgehen:** Präfixtreffer über das Original-Suchwort höher gewichten als Präfixtreffer über Glossar-Alternativen; alternativ Kategorie-Boost für `regel` bei Aktions-/Zustandsbegriffen. Mit Testfall absichern.
- **Version/Quelle:** 2024. **Beispielfrage:** „Wie funktioniert Verstecken?"

### DND-012 — Glossar zeigt teils Pluralformen als kanonische Anzeige

- **Schweregrad:** Niedrig · **Regelbereich:** Terminologie-Anzeige · **Eindeutigkeit:** eindeutig
- **Stelle:** Glossar-Bestand (dnddeutsch liefert Plural-Zeilen); `foliant_uebersetze_begriff("opportunity attack")` → „Gelegenheitsangriffe (Opportunity Attacks)", „spell slot" → „Zauberplätze (Spell Slots)"
- **Befund/Auswirkung:** Fachlich korrekt, aber als kanonische Begriffsangabe unschön (Singular ist die Zitierform). Die Herkunftsangabe „Spielerhandbuch/2014" an editionsstabilen Begriffen ist S7-konform und intern sichtbar — kein Fehler, aber erklärungsbedürftig.
- **Besseres Vorgehen:** Beim Seeding Singular-Bevorzugung, wenn dnddeutsch beide Formen liefert; sonst kuratierte Singular-Paare für die Kernbegriffe.
- **Version/Quelle:** Begriffsebene. **Beispielfrage:** „Wie heißt Opportunity Attack auf Deutsch?"

### DND-013 — Kein Errata-/Druckstand-Tracking je Quelle (Hinweis)

- **Schweregrad:** Hinweis · **Eindeutigkeit:** eindeutig (Schema)
- **Befund:** `quellen` kennt Edition, aber keinen Errata-/Druckstand; nur DDB-Artefakte tragen ein Exportdatum. Künftige Errata (WotC pflegt 2024-Inhalte nach) würden beim Re-Import den alten Text still ersetzen — nachvollziehbar wäre nur „aktuell", nicht „was galt vorher/warum weicht die Antwort vom Druckbuch ab". Der Anforderungskatalog stuft Errata-Stand bewusst als optional ein (V1) — daher nur Hinweis: bei O2-Aktualisierungen ein `stand`-Feld (Datum/Errata-Version) je Quelle mitführen und in der Belegzeile optional nennen.

### DND-014 — Wechselwirkungs-Wissen liegt vollständig beim Modell (Systemgrenze, Hinweis)

- **Schweregrad:** Hinweis · **Eindeutigkeit:** eindeutig (by design)
- **Befund:** Foliant liefert Regel*texte* mit Belegen; Regelinteraktion (specific beats general, Timing, Stapelung) leistet das Sprachmodell. Das ist die dokumentierte Arbeitsteilung und für den MVP angemessen — aber es bedeutet: Die fachliche Qualität von Wechselwirkungs-Antworten hängt an (a) der Vollständigkeit der gelieferten Texte (darum wiegen DND-001/005 schwer) und (b) der Modelldisziplin (darum DND-008). Als Absicherung empfiehlt sich der Ausbau der manuellen Verhaltens-Checkliste um 3–4 Wechselwirkungsfragen (Kapitel 16, Kategorie „Kombination").

---

## 9. Vermischung oder Unklarheit von Regelversionen

**Ergebnis: sehr gut auf der Editionsachse, lückenhaft auf der Inhaltsarten-Achse.**

- **2014 vs. 2024:** technisch getrennt erzwungen (`edition NOT NULL`; Editionsfilter vor dem Limit; getrennte Zusatzlisten `aeltere_staende`/`andere_fassungen`; Detailabruf ersetzt explizit angeforderte Editionen nie still; Build-Prüfung strikt 2024 — Nur-2014-Optionen werden `nicht_pruefbar`, nie `ok`). Die Tests decken genau die kritischen Fälle (2014-Flut verdrängt 2024 nicht; kein falscher Altstands-Fallback bei expliziter 2014-Anfrage). In der Dev-DB existiert kein 2014-Inhalt; auf dem Pi (Basic Rules 2014) greift dieselbe Mechanik — plausibel, aber nicht stichprobiert.
- **Editionszuordnung der Quellen:** nie geraten — DDB autoritativ aus der Buch-DB, PDFs per Pflichtangabe, Open5e am Dokument-Key; unklare Edition ⇒ kein Import. Fachlich vorbildlich.
- **Terminologie:** bewusst editionsübergreifend (S7/V6) mit interner Herkunft — sauber getrennt von der Regelversionierung.
- **Playtest/UA:** *nicht* über die Editionsachse abgedeckt — ein Playtest-Buch bekäme „2024" und wäre im Bestand von finalem Material nicht unterscheidbar (**DND-002**). Das ist die einzige echte Vermischungsgefahr im System.
- **Drittanbieter/Hausregeln:** nicht im Bestand, nicht vorgesehen — keine Vermischung möglich.
- **Zukunftskante (klein):** Beim Standard 2024 wird jede andere Edition pauschal als „älterer Stand" etikettiert; eine künftige *neuere* Fassung würde falsch einsortiert. Heute ohne Wirkung (nur 2024/2014 zulässig, `admin check` erzwingt das), beim Anlegen einer neuen Edition zu beachten.

---

## 10. Bewertung von Quellen und Nachvollziehbarkeit

- **Rückführbarkeit:** Jede Detailantwort trägt `zitat` (Quelle · ggf. Seite · Regelversion), `quelle`, `edition`, `sprache` und den vollständigen `regeltext_md` — eine Antwort ist damit auf den konkreten Bestandseintrag und dieser auf Buch+Seite rückführbar. Suchtreffer tragen dieselben Kennungen knapp. Das ist die stärkste Anti-Halluzinations-Struktur, die ein Retrieval-System dieser Art bieten kann: Das Modell muss Regeltext nicht erinnern, sondern bekommt ihn belegt geliefert.
- **Seitenzahlen:** stammen aus PDF-Seitenmarkern; Stichprobe konsistent (Feuerball: zitierte S. 139 = gedruckte Fußzeile 139). Quellen ohne Seiten (Open5e, DDB) zitieren korrekt ohne Seite (F7). Restrisiko: Bei mehrseitigen Einträgen zeigt `seite` die Startseite — akzeptabel und üblich.
- **Erfundene Zitate/Quellen:** Das Risiko liegt beim Modell, nicht beim Server; die Tool-Ausgaben liefern die Belegzeile fertig mit. Eine kleine Härtung wäre der explizite Hinweis „zitiere die Belegzeile unverändert" in `stil.py` (heute implizit über das Format-Schema).
- **Primär vs. Sekundär:** Deutsche PDFs und DDB-Bücher sind Primärquellen; Open5e ist eine Community-Transkription des SRD 5.2 (Sekundärquelle). Die Präzedenz (10/40/60) stellt Primärquellen korrekt nach vorn, und der Titel „… (Open5e)" macht die Herkunft sichtbar; eine *explizite* Kennzeichnung „Sekundärquelle/Community-Transkription" gibt es nicht (Hinweis; bei Abweichungen zwischen Open5e und Buchtext entscheidet stillschweigend die Priorität — `weitere_quellen` hält die Provenienz sichtbar).
- **DE/EN-Abweichungen:** strukturell gut gelöst — deutsche und englische Fassungen desselben Inhalts werden als Dublette einer kanonischen Antwort geführt (deutsche Quelle führt, S10), `andere Fassungen` bleiben abrufbar; die Glossar-Brücke ist getestet. Lücken bestehen punktuell bei neuen 2024-Begriffen (DND-006).
- **Unbelegte Behauptungen im Bestand:** keine gefunden — der Bestand enthält ausschließlich Quelltext-Chunks, keine redaktionellen Zusätze. Die Build-Prüfung belegt sogar ihre Konstanten am Bestand.

---

## 11. Bewertung von Regelausnahmen und Wechselwirkungen

**Ansatz:** Foliant beantwortet Ausnahme-/Wechselwirkungsfragen nicht selbst, sondern liefert vollständige Regelabschnitte (inkl. „Siehe auch"-Verweisen des SRD) an das Modell. Bewertung entlang der Prüfpunkte:

- **Specific beats general:** nicht als Datenrelation modelliert; die relevanten Spezialtexte sind aber als eigene Einträge abrufbar (z. B. „Gepackt halten" *neben* dem Zustand „Gepackt"; Meisterschaftseigenschaften je Waffe). Das Modell muss die Hierarchie herstellen — mit vollständigen Texten machbar, durch DND-001/005 punktuell gefährdet.
- **Trigger/Timing von Reaktionen:** Der 2024-Gelegenheitsangriffstext (inkl. „unmittelbar bevor die Kreatur die Reichweite verlässt") ist korrekt und vollständig im Bestand; „Reaktionen"-Grundregel als eigener Eintrag vorhanden.
- **Kreatur vs. Objekt, Angriff vs. Angriffsaktion, Waffenangriff vs. Angriff mit Waffe, Zauberangriff:** Die 2024-Regelglossar-Definitionen sind als H6-Einzeleinträge importiert (Stichproben: Aktionsdefinitionen, Zustandsdefinitionen gefunden) — genau die richtige Granularität, um solche Abgrenzungsfragen belegt zu beantworten.
- **Sichtbarkeit/Unsichtbarkeit:** Die Verstecken-Aktion verweist korrekt auf den Zustand *Unsichtbar* (2024-Neuerung) — im Bestand konsistent.
- **Konzentration:** Beginn/Ende/Störfaktoren vollständig im Konzentrations-Eintrag (Stichprobe korrekt).
- **Immunität/Resistenz/Verwundbarkeit, Rundendauer vs. Zugdauer, „once per turn":** als Regelglossar-Einträge bzw. in den Regeltexten enthalten; nicht einzeln stichprobiert, Struktur trägt sie.
- **Stapelung gleichnamiger Effekte:** „Der Bonus ist nicht stapelbar" existiert als eigener Eintrag (bei der Suche nach „Übungsbonus" gesehen) — gut.
- **Grenze:** Es gibt keine maschinelle Verknüpfung „Ausnahme X gehört zu Grundregel Y" (kein `parent`-/Verweisgraph). Für den MVP tragfähig, weil die SRD-Texte ihre Querverweise textlich enthalten; für spätere komplexe Wechselwirkungs-Features (z. B. „zeige alle Regeln, die Gelegenheitsangriffe modifizieren") fehlt die Struktur (Kapitel 13).

**Gesamturteil:** Die Datengrundlage für Ausnahmen/Wechselwirkungen ist gut; die Auflösung leistet das Modell. Die beiden Schwachpunkte sind Textintegrität (DND-001/004/005) und fehlende Aussageart-Kennzeichnung (DND-008).

---

## 12. Bewertung der Antwortqualität für Spielende

Direkt bewertbar sind die Tool-Ausgaben und die Verhaltensanweisungen (das Endverhalten formt das Modell; Schicht-3-Abnahme steht laut Projekt noch aus):

- **Direkte Beantwortung:** Suche-knapp/Detail-voll passt zum Frageverhalten am Tisch; `foliant_hol_regel` existiert genau deshalb, weil Such-Snippets für Regelfragen zu kurz sind — gutes fachliches Design.
- **Verständlichkeit:** Deutsche Regeltexte als Primärmaterial, einheitliches Antwortschema (Emoji-Kopfzeile, Tabellen für Werte, Belegzeile) und die B7-Schrittführung beim Charakterbau sind spielendengerecht. Wortrisse/Laufköpfe (DND-005) trüben wörtliche Zitate.
- **Ausnahmen nennen:** Die SRD-Texte enthalten „Siehe auch"-Verweise; Detailantworten liefern den ganzen Abschnitt — wichtige Ausnahmen stehen also im gelieferten Material. Ob sie genannt werden, ist Modellverhalten (Checkliste).
- **Unsicherheit/Absolutheit:** Ehrliche Leerbefunde, Mehrdeutigkeits-Kandidaten, Altstands-Warnungen und die Grenzen-/`nicht_pruefbar`-Ausweise der Build-Prüfung sind explizit im Ausgabeformat verankert — überdurchschnittlich. Es fehlt die Aussageart-Kennzeichnung (DND-008) und ein „SL entscheidet"-Baustein für regeloffene Fragen.
- **Falsche Nutzerannahmen:** Die Datenlage erlaubt Korrekturen (z. B. 2014er-Annahmen gegen 2024er-Text); die Editionstrennung liefert dafür sogar beide Stände getrennt. Kein expliziter Stil-Hinweis „freundlich korrigieren" — Kleinigkeit.
- **Kurz vs. ausführlich:** nicht adressiert (weder Parameter noch Stilregel „erst Kernaussage, dann Details"). Hinweis: eine Zeile im Format-Schema würde genügen.
- **Risiko irreführender Antworten:** hauptsächlich über die Befunde DND-001 (falscher Regeltext), DND-003 (falsches Nicht-gefunden), DND-004 (verlesbare Statblocks) und DND-011 (Rauschtreffer zuerst) — alle behebbar.

---

## 13. Eignung für eine spätere Nutzung durch Spielleitende

**Bereits tragfähig:** Monster-Statblocks (341 dt. + Open5e), Gefahren-/Umweltregeln (Dehydrierung, Ersticken, Reise), magische Gegenstände, Werkzeuge — der Bestand deckt schon heute viel SL-Material ab; die Kategorien `monster`/`gegenstand`/`regel` und die Quellen-/Editionsmechanik tragen weitere Bücher (DMG/MM) ohne Strukturänderung. Die Präzedenz-/Dubletten-Logik und das Pflicht-Editionsmodell sind genau die Grundlagen, die SL-Erweiterungen brauchen.

**Strukturelle Grenzen (erkennbar, teils geplant):**
1. **Spoiler-/Rollentrennung ist nicht strukturell:** Abenteuer-Lore kann im selben Bestand liegen (DND-002); es gibt einen Zugang für alle. Die geplante Stufe A3 (getrennte Datenräume je Rolle) ist die richtige Antwort — bis dahin sollte Abenteuer-Material gekennzeichnet oder ferngehalten werden.
2. **Keine Meta-Felder für SL-Filterfragen:** „Alle HG-5-Monster mit Flugbewegung", „alle seltenen Gegenstände" sind mangels strukturierter Felder (`monster_meta`/`gegenstand_meta` bewusst leer) nur textuell beantwortbar. Für Begegnungsvorbereitung wäre das der erste Ausbau.
3. **Kein Regel-Beziehungsgraph:** improvisierte Entscheidungen profitieren von „verwandte Regeln"-Navigation; heute nur über Kontextzeilen/Namenskonventionen angenähert.
4. **Optionale Regeln:** kein Kennzeichnungsfeld (heute nicht nötig, im DMG-Fall aber Pflicht — „optionale Regel" muss dann als Inhaltsklasse existieren, dieselbe Achse wie DND-002).
5. **Kampagnenwissen** ist per Anforderungen ausgeschlossen (A2) — die saubere Abgrenzung erleichtert die spätere getrennte Stufe.

**Fazit:** fachlich gut erweiterbar; die eine Strukturentscheidung, die vor SL-Inhalten fallen muss, ist die Inhaltsarten-Kennzeichnung (Playtest/Abenteuer/optional) — dieselbe Maßnahme wie für DND-002.

---

## 14. Mögliche urheberrechtliche oder quellenbezogene Risiken

*Keine Rechtsberatung; fachliche Sichtung der Inhaltsnutzung.*

- **Wörtliche Volltexte sind das Systemprinzip:** Der Bestand speichert und serviert komplette Regelabschnitte, Statblocks und Tabellen wortwörtlich (kein Zusammenfassen). Für **SRD 5.2.1/SRD 5.2 (CC-BY-4.0)** ist das lizenzkonform, und die Attribution wird vorbildlich mitgeführt (eigene `attribution`-Zeile in CC-BY-Detailantworten, `docs/ATTRIBUTION.md`, Lizenzfeld je Quelle). Open5e-`srd-2024` ist ebenfalls CC-BY-getaggt.
- **DDB-Bücher (geschützt):** vollständige Textübernahme in die bediente Datenbank; Nutzung ausdrücklich privat, Zugang inzwischen durch Geheimpfad + IP-Allowlist beschränkt, `lizenz='privat'` je Eintrag. Das Projekt behandelt die ToS-Grauzone als bewusste, dokumentierte Eigentümer-Entscheidung; die Ausweitung auf die Spielrunde ist in der Roadmap korrekt als eigene, noch zu treffende Entscheidung markiert. Risiko erkennbar, aber transparent verwaltet — wichtig ist, dass die Spieler-Anleitung (M4) das Weitergabeverbot ausspricht (in `docs/DEPLOY-raspberry-pi.md` bereits vorgesehen).
- **Inkonsistenz in der Doku:** `docs/ATTRIBUTION.md` behauptet noch, die bediente DB bleibe frei von DDB-Inhalten und die Bereitstellung sei offen — das widerspricht dem dokumentierten Ist-Zustand (10 DDB-Bücher in der bedienten DB). Gerade beim Rechte-Dokument sollte die Beschreibung der Realität entsprechen (Niedrig, aber im Rechtekontext relevant).
- **Herkunft je Eintrag ist lückenlos** (Quelle, Lizenz, Edition, Sprache) — die Grundvoraussetzung, um frei nutzbare von geschützten Inhalten jederzeit trennen zu können (z. B. für einen späteren „nur-SRD"-Zugang). Positiv hervorzuheben.
- **dnddeutsch.de-Glossar:** Begriffs*paare* (Wort-Zuordnungen) mit Quellenvermerk — geringes Schöpfungshöhe-Risiko, Herkunft dokumentiert, API höflich genutzt und gecacht.

---

## 15. Priorisierter fachlicher Maßnahmenplan

### Zwingend vor weiteren internen Tests
| Prio | Befunde | Ziel | Umsetzung | Fachliches Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| 1 | DND-001 | Topple korrekt und auffindbar; „Zweihändig" sauber | BEREINIGUNG-Regel setzt die verlorene Überschrift („Umwerfen"/Topple) vor den zweiten Absatz; Kontext von „Zweihändig" zurück nach „Eigenschaften"; Re-Import srd-de; parallel prüfen, ob „Reichweite (Reach)" dasselbe Schicksal hat | `foliant_hol_gegenstand`/`hol_regel` liefert alle **8** Meisterschaftseigenschaften einzeln; „Zweihändig" enthält keinen Rettungswurf-Text; Smoke-Check „8 Meisterschaften" grün | S |
| 2 | DND-003 | Kein falsches „nicht im Bestand" durch Parameterfehler | Kategorie-/Quellen-Validierung mit strukturiertem `fehler` (gültige Werte nennen) statt Leertreffer | `suche_regeln("Feuerball", kategorie="spell")` liefert Parameterfehler, nie den B1-Leerhinweis; Testfall ergänzt | S |

### Vor externen Nutzertests (Freigabe an die Runde)
| Prio | Befunde | Ziel | Umsetzung | Fachliches Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| 3 | DND-002 | Playtest/Abenteuer erkennbar | `inhaltsart` je Quelle (aus DDB-Kategorie) bis in die Tool-Ausgaben durchreichen; Playtest in Options-Listen ausblenden oder markieren; kurzfristig: Playtest vom Sync ausnehmen | Ein Playtest-Eintrag trägt in jeder Antwort einen Playtest-Hinweis; Options-Listen ohne unmarkiertes Playtest-Material | M |
| 4 | DND-006 | 2024-Kernbegriffe zweisprachig | Kuratierte Glossar-Paare: Weapon Mastery↔Waffenbeherrschung (+„Waffenmeisterschaft" als PHB-Zeile), Meisterschaftseigenschaft, Emanation↔Ausströmung, 8 Eigenschaftsnamen | `uebersetze_begriff("weapon mastery")` liefert offiziellen Begriff; Suche „Waffenmeisterschaft" findet Klassenmerkmal + Eigenschaftsregeln | S |
| 5 | DND-005 | Saubere wörtliche Zitate | srd-de-BEREINIGUNG: Laufkopf+Seitenzahl entfernen; dokumentverifizierte Wortriss-Kittung; Re-Import | Feuerball/Verstecken-Volltexte ohne „Systemreferenzdokument …"-Einschub; Wortriss-Scan < 20 Resttreffer (nur legitime Ergänzungsstriche) | M |
| 6 | DND-007 | Zustände/Aktionen direkt treffbar | Klammer-Suffix als Exakt-Namensvariante in `_eintrag_namen` | `hol_regel("Erschöpfung")` liefert direkt den Zustand (Kandidatenliste nur noch bei echter Mehrdeutigkeit wie „Schild") | S |
| 7 | DND-008 | Aussagearten getrennt | Zwei Sätze in `stil.py` + Projektanweisung (synchron): Ableitungen kennzeichnen, regeloffene Fragen an die SL verweisen (eigenes Emoji ⚖️) | Checklisten-Frage „Absitzen + Gelegenheitsangriff" liefert erkennbar getrennte Regel-/Ableitungsteile | S |

### Vor Veröffentlichung des MVP (Dauerbetrieb mit der Runde)
| Prio | Befunde | Ziel | Umsetzung | Fachliches Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| 8 | DND-004 | Verlässliche Statblock-Köpfe | Zellriss-Normalisierung beim srd-de-Import; Kreuz-Stichprobe 10 Monster (TP/RK/Retter/HG) | Stichprobe 10/10 korrekt maschinenlesbar (keine `W1|0`-Muster im Bestand) | M |
| 9 | DND-009, DND-010 | Saubere Namen, kein ToC-Rauschen | 8 Namens-Fixes + Verzeichnis-Skip; Re-Import | Keine Garble-Namen im Bestand; Monster-Suche ohne Verzeichnis-Treffer | S |
| 10 | DND-011, DND-012 | Ranking-/Anzeige-Politur | Original-Suchwort-Präfix vor Glossar-Präfix; Singular-Bevorzugung im Glossar | „Verstecken" listet die Aktion zuerst; Kernbegriffe singular | S |
| 11 | (Kap. 16) | Fachliche Regressionssicherung | Die 28 Testfragen aus Kapitel 16 als Checkliste/teilautomatisierte Suite gegen den Pi-Bestand fahren | Protokoll mit Soll/Ist je Frage; keine offenen Hoch-Abweichungen | M |

### Nach dem MVP
| Prio | Befunde | Ziel | Umsetzung | Größe |
|---|---|---|---|---|
| 12 | DND-013 | Errata-Nachvollziehbarkeit | `stand`-Feld je Quelle; bei Re-Importen Beleg um Stand ergänzen | S |
| 13 | DND-014 | Wechselwirkungs-Absicherung | Verhaltens-Checkliste um Interaktionsfragen erweitern; ggf. LLM-gestützte Regressionstests | M |
| 14 | (Kap. 13) | SL-Filterfragen | `monster_meta`/`gegenstand_meta` befüllen + Filter-Tools (HG, Typ, Seltenheit) | L |

### Spätere fachliche Erweiterungen
| Prio | Ziel | Umsetzung | Größe |
|---|---|---|---|
| 15 | Strukturelle Spoiler-/Rollentrennung (A3) | getrennte Datenräume SL/Spieler; Abenteuer-Inhalte nie im Spieler-Bestand | L |
| 16 | Optionale Regeln & Hausregeln (A4) | Inhaltsklasse „optional" (DMG) und Hausregel-Overlay mit sichtbarer Überlagerung der RAW-Antwort | L |
| 17 | Regel-Beziehungsgraph | „gehört zu/modifiziert"-Relationen für Ausnahme-Navigation | XL |

---

## 16. Empfohlene Testfragen (28)

Format je Test: **ID · Frage · Kategorie · Zweck** / Erwartete Kernaussage / Fallstricke / Version / Quelle / Verhalten bei fehlender Info.

**TF-01 · „Was bewirkt der Zustand Gepackt?" · einfache Grundregel · Zustandsdefinition korrekt liefern.**
Kernaussage: Bewegungsrate 0 (nicht erhöhbar); Nachteil auf Angriffe gegen andere als den Packenden; der Packende kann einen mitziehen. Fallstricke: 2014-Formulierung; Verwechslung mit „Gepackt halten" (Grapple-Durchführung). Version: 2024. Quelle: SRD 5.2.1 (DE) S. 208. Fehlende Info: n. a. (im Bestand).

**TF-02 · „Wie viel Schaden macht Feuerball und was kann man dagegen tun?" · einfache Grundregel · Zauberwerte + Rettungswurf.**
Kernaussage: 8W6 Feuer, GES-Rettungswurf halbiert; 6-m-Radius-Kugel, 45 m Reichweite, Grad 3. Fallstricke: Fuß→Meter-Umrechnung; höhere Grade (+1W6 je Grad). Version: 2024. Quelle: SRD 5.2.1 (DE) S. 139. Fehlende Info: n. a.

**TF-03 · „Lösen Teleportationseffekte einen Gelegenheitsangriff aus?" · Regelausnahme · Auslöserkatalog exakt lesen.**
Kernaussage: Nein — der Gelegenheitsangriff verlangt Verlassen der Reichweite mittels Aktion/Bonusaktion/Reaktion/Bewegungsrate; Teleportation nutzt keine davon. Fallstricke: „jede Bewegung löst aus"-Fehlannahme. Version: 2024. Quelle: SRD 5.2.1 (DE) S. 208 (Gelegenheitsangriff). Fehlende Info: Wenn der Teleport-Passus nicht zitierbar ist, als Ableitung kennzeichnen.

**TF-04 · „Was passiert bei sechs Erschöpfungsstufen, und was macht jede Stufe?" · häufige Spielerfrage · 2024-Erschöpfung vs. 2014-Tabelle.**
Kernaussage: kumulativ; je Stufe −2 auf W20-Prüfungen und −1,5 m Bewegungsrate; Tod bei Stufe 6. Fallstricke: 2014-Stufentabelle (Nachteil/halbe Rate etc.) darf nicht auftauchen. Version: 2024. Quelle: SRD 5.2.1 (DE) S. 206. Fehlende Info: n. a.

**TF-05 · „Ich möchte mich im Kampf verstecken — wie geht das und was bringt es?" · Kombination mehrerer Regeln · Aktion + Zustand Unsichtbar + Entdeckung.**
Kernaussage: Verstecken-Aktion: SG-15-GES(Heimlichkeit), nur bei starker Verschleierung oder ≥Dreiviertel-Deckung, außer Sichtlinie; Erfolg ⇒ Zustand Unsichtbar, Wurfergebnis = Aufspür-SG; endet u. a. durch Geräusch/Angriff. Fallstricke: 2014 hatte keinen festen SG und keinen Unsichtbar-Zustand fürs Verstecken. Version: 2024. Quelle: SRD 5.2.1 (DE) S. 218 + S. 13. Fehlende Info: n. a.

**TF-06 · „Was macht die Meisterschaftseigenschaft Umwerfen (Topple)?" · einfache Grundregel · **Prüfstein für DND-001**.**
Kernaussage: Bei Treffer KON-Rettungswurf (SG 8 + Attributsmod + ÜB), bei Misserfolg Zustand Liegend; nur mit Waffenbeherrschungs-Zugriff. Fallstricke: derzeit kein deutscher Eintrag — Antwort dürfte NICHT „gibt es nicht" lauten und NICHT der Eigenschaft „Zweihändig" zugeschrieben werden. Version: 2024. Quelle: SRD 5.2.1 (DE) S. 103. Fehlende Info: ehrlicher Hinweis + englischer Open5e-Waffentext als Fassung.

**TF-07 · „Kann ich mit einer Zweihandwaffe Gegner durch die Eigenschaft Zweihändig umwerfen?" · falsche Nutzerannahme · Gegenprobe zu DND-001.**
Kernaussage: Nein — Zweihändig regelt nur die Führung mit zwei Händen; Umwerfen ist eine eigene Meisterschaftseigenschaft bestimmter Waffen. Fallstricke: der fusionierte Bestandstext „bestätigt" die falsche Annahme. Version: 2024. Quelle: SRD 5.2.1 (DE) S. 103. Fehlende Info: n. a.

**TF-08 · „Wie viele Waffen mit Meisterschaft kann mein Kämpfer auf Stufe 1 nutzen, und wird das mehr?" · Klassenmerkmal · Klassentabellen-Lesen + Build-Prüfung.**
Kernaussage: Kämpfer Stufe 1: 3 Waffen (laut Klassentabelle), steigend auf höheren Stufen. Fallstricke: Verwechslung mit Anzahl geführter Waffen. Version: 2024. Quelle: SRD 5.2.1 (DE) Klassenmerkmale des Kämpfers. Fehlende Info: `foliant_pruefe_build` muss bei nicht parsebarer Tabelle „nicht_pruefbar" sagen.

**TF-09 · „Schild" · mehrdeutige Nutzerfrage · B4-Kandidatenverhalten.**
Kernaussage: Rückfrage mit Kandidaten: Zauber *Schild* (Reaktion, +5 RK) vs. Gegenstand *Schild* (+2 RK). Fallstricke: stilles Raten einer Bedeutung. Version: 2024. Quelle: SRD 5.2.1 (DE). Fehlende Info: n. a.

**TF-10 · „Was ist der Unterschied zwischen dem Zauber Leicht und der Waffeneigenschaft Leicht?" · ähnlich klingende Fachbegriffe · Kategorien-Trennung.**
Kernaussage: Zaubertrick *Light* (Licht) vs. Eigenschaft *Light* (leichte Waffe, Zwei-Waffen-Kampf-relevant) — zwei verschiedene Dinge, beide „Leicht" im Bestand. Fallstricke: Vermengung beider Texte. Version: 2024. Quelle: SRD 5.2.1 (DE) S. 156 bzw. S. 103. Fehlende Info: n. a.

**TF-11 · „Was macht der Zauber Silvery Barbs?" · nicht unterstützter Inhalt · T2-Ehrlichkeit.**
Kernaussage: ehrliches „nicht im Foliant-Bestand — eventuell fehlt ein Buch" (Zauber ist nicht in SRD/geladenen Quellen). Fallstricke: Modell kennt den Zauber aus Training und könnte ihn nennen. Version: —. Quelle: —. Fehlende Info: genau das ist der Test.

**TF-12 · „Wie besiege ich Strahd am besten?" · nicht unterstützter Inhalt (Spoiler) · B6/oberste Regel.**
Kernaussage: Ablehnung mit 🚫 als außerhalb des Umfangs; allenfalls Angebot regelseitiger Auskünfte (z. B. Vampir-Statblock, falls im Bestand). Fallstricke: Taktik-Tipps aus Weltwissen. Version: —. Quelle: —. Fehlende Info: n. a.

**TF-13 · „Wie funktionierte Verstecken nach den 2014er-Regeln?" · versionsabhängige Frage · gezielter Altstand-Abruf.**
Kernaussage: Wenn 2014-Quelle geladen (Pi: Basic Rules 2014): 2014-Text mit klarer 2014-Kennzeichnung; sonst ehrlich „keine 2014-Fassung im Bestand". Fallstricke: stilles Mischen mit 2024; Ausgeben der 2024-Regel als 2014. Version: 2014 (explizit). Quelle: Basic Rules 2014 (DDB) falls geladen. Fehlende Info: Hinweis auf vorhandene Fassungen.

**TF-14 · „Was ist ein Todesrettungswurf und wann würfle ich ihn?" · einfache Grundregel · Kernmechanik.**
Kernaussage: Bei 0 TP zu Beginn des eigenen Zugs W20 ohne Modifikatoren; 10+ Erfolg; 3 Erfolge stabil, 3 Misserfolge tot; 1 = zwei Misserfolge, 20 = 1 TP. Fallstricke: 2024-Detail (Natürliche 20 ⇒ 1 TP) korrekt wiedergeben. Version: 2024. Quelle: SRD 5.2.1 (DE), Regelglossar. Fehlende Info: n. a.

**TF-15 · „Ich habe den Zauber Segen aktiv und werde getroffen — was muss ich tun?" · Kombination mehrerer Regeln · Konzentration + Rettungswurf.**
Kernaussage: KON-Rettungswurf SG 10 oder halber Schaden (höherer Wert); bei Misserfolg endet Segen. Fallstricke: SG-Berechnung (mind. 10, Kappe 30 in 2024); Konzentration nur einmal pro Schadensereignis. Version: 2024. Quelle: SRD 5.2.1 (DE) S. 211 (Konzentration). Fehlende Info: n. a.

**TF-16 · „Kann ich zwei Zauber mit Konzentration gleichzeitig halten?" · häufige Spielerfrage · klare RAW-Antwort.**
Kernaussage: Nein — Wirken eines zweiten Konzentrationseffekts beendet den ersten. Fallstricke: keine. Version: 2024. Quelle: SRD 5.2.1 (DE) S. 211. Fehlende Info: n. a.

**TF-17 · „Was kostet es, meinen Attributswert per Punktkauf auf 16 zu setzen?" · falsche Nutzerannahme · Wertebereich 8–15.**
Kernaussage: Punktkauf erlaubt nur 8–15 (vor Hintergrund-Erhöhungen); 16 ist nicht kaufbar. Fallstricke: Kostentabelle extrapolieren. Version: 2024. Quelle: SRD 5.2.1 (DE) „Schritt 3: Attributswerte". Fehlende Info: Build-Prüfung muss 16 als Verstoß melden.

**TF-18 · „Mein Hintergrund Soldat gibt +2 Weisheit, oder?" · falsche Nutzerannahme · Hintergrund-Attributsbindung.**
Kernaussage: Nein — Soldat erlaubt Erhöhungen nur auf Stärke/Geschicklichkeit/Konstitution (+2/+1 oder +1/+1/+1, max. 20). Fallstricke: 2014-Denke („Attribute von der Volkswahl"). Version: 2024. Quelle: SRD 5.2.1 (DE) S. 93. Fehlende Info: n. a.

**TF-19 · „Baue mir einen legalen Stufe-1-Kämpfer mit Standardwerten, Soldat, Mensch — und prüfe ihn." · Kombination · Build-Prüfung Ende-zu-Ende (T9/T12).**
Kernaussage: Führung in 2024-Reihenfolge (Klasse→Hintergrund→Spezies→Details); Prüfung „legal_soweit_pruefbar" nur bei vollständigen Angaben, Grenzen offen ausgewiesen. Fallstricke: Unterklasse auf Stufe 1 (muss Verstoß sein); Prüfung darf Zauber-/Fertigkeitenwahl nicht „bestätigen". Version: 2024. Quelle: Bestand (mehrere). Fehlende Info: `unvollstaendig` + `fehlende_angaben`.

**TF-20 · „Welche Spezies stehen zur Wahl?" · häufige Spielerfrage · Listen-Vollständigkeit + B2.**
Kernaussage: Die 9 SRD-Spezies (inkl. Goliath, Aasimar nur falls Quelle geladen) mit Quellenangabe; Hinweis, dass fehlende Optionen fehlende Bücher bedeuten. Fallstricke: Aus Weltwissen ergänzen (z. B. Tabaxi). Version: 2024. Quelle: SRD 5.2.1 (DE) + geladene Bücher. Fehlende Info: B2-Hinweis.

**TF-21 · „Was ist eine Ausströmung (Emanation) und wo beginnt sie?" · versionsneue Mechanik · 2024-Wirkungsbereich; Prüfstein für DND-006.**
Kernaussage: 2024-Wirkungsbereichsform, geht vom Wirker/Objekt aus, bewegt sich mit; Ursprung zählt nicht zum Bereich des Würfels/…, Details laut Eintrag „Ausströmung (Wirkungsbereich)". Fallstricke: englischer Suchbegriff „emanation" muss denselben Eintrag finden (Glossarlücke!). Version: 2024. Quelle: SRD 5.2.1 (DE), Regelglossar. Fehlende Info: n. a.

**TF-22 · „AoO — was war das nochmal?" · Abkürzung · B3/T7.**
Kernaussage: Gelegenheitsangriff (Opportunity Attack) + Kurzregel. Fallstricke: Abkürzung nicht auflösbar. Version: 2024. Quelle: Glossar + SRD 5.2.1 (DE) S. 208. Fehlende Info: n. a.

**TF-23 · „Ist Two-Weapon Fighting dasselbe wie der Kampf mit zwei Waffen?" · ähnlich klingende Begriffe + versionsabhängig · 2024-Umbenennung/Terminologie.**
Kernaussage: 2024 heißt der Kampfstil „Zwei-Waffen-Kampf" (Two-Weapon Fighting); die Mechanik hängt an der Eigenschaft *Leicht* (Bonusaktions-Angriff → 2024: Teil des Angriffs mit „Leicht"). Fallstricke: 2014er dnddeutsch-Begriff „Kampf mit zwei Waffen" vs. kuratiertes 2024-Paar. Version: 2024. Quelle: SRD 5.2.1 (DE). Fehlende Info: n. a.

**TF-24 · „Zählt ein waffenloser Angriff als Waffenangriff für Wilde Angreiferin/Savage Attacker?" · widersprüchlich interpretierte Regel · RAW-Grenzen benennen.**
Kernaussage: Talenttext zitieren („Waffe"-Bezug); 2024 definiert Waffenloser Angriff separat — die Antwort muss die Definitionseinträge nebeneinanderstellen und bei Restunklarheit die SL-Entscheidung nennen. Fallstricke: apodiktische Ja/Nein-Antwort ohne Kennzeichnung der Ableitung. Version: 2024. Quelle: SRD 5.2.1 (DE), Talent + Regelglossar. Fehlende Info: Ableitung kennzeichnen (DND-008).

**TF-25 · „Ich falle 20 Meter in Wasser — wie viel Schaden?" · Frage ohne eindeutige RAW-Antwort · Fallschaden + SL-Spielraum.**
Kernaussage: RAW: 1W6 Wuchtschaden je 3 m Fall (max. 20W6), Landung liegend; Wasser mildert RAW nicht automatisch — Einordnung als SL-Entscheidung/übliche Praxis, klar getrennt. Fallstricke: Hausregeln („Wasser halbiert") als offizielle Regel ausgeben. Version: 2024. Quelle: SRD 5.2.1 (DE), Gefahren/Fallen(-schaden). Fehlende Info: SL-Kennzeichnung.

**TF-26 · „Auf welcher Seite steht die Regel für kurze Rasten, und aus welchem Buch stammt sie bei dir?" · Quellenfrage · Belegtreue.**
Kernaussage: Exakte Belegzeile (Quelle · Seite · Regelversion) aus dem Bestand; keine erfundene Seitenzahl; bei Open5e-Herkunft ausdrücklich ohne Seite. Fallstricke: Seitenzahlen aus Trainingswissen (engl. PHB) einmischen. Version: 2024. Quelle: Bestand. Fehlende Info: „Quelle ohne Seitenzahl" sagen.

**TF-27 · „Mein Magier ist Stufe 5 — was kann ich alles in einem Zug machen?" · Frage mit unvollständigen Informationen · Aktionsökonomie + Rückfrage.**
Kernaussage: Grundgerüst (Bewegung + 1 Aktion + ggf. Bonusaktion + freie Objektinteraktion; 1 Reaktion pro Runde) mit Beleg; für Konkretes (Bonusaktionszauber? Merkmale?) gezielte Rückfrage. Fallstricke: die 2014er „Bonuszauber-Regel" (nur Zaubertrick daneben) — 2024 hat die Regel geändert (ein Zauber mit Zauberplatz pro Zug); Version klar benennen. Version: 2024. Quelle: SRD 5.2.1 (DE), Regelglossar/Zauberwirken. Fehlende Info: Rückfrage statt Annahme.

**TF-28 · „Was kostet eine Heiltrankflasche und wie viel heilt sie?" · einfache Grundregel (Gegenstand) · Werte + Tabellenintegrität.**
Kernaussage: Heiltrank: 2W4+2 TP, Preis laut Ausrüstungstabelle (50 GM); als Bonusaktion? — 2024: Trinken = Bonusaktion (eigener Regelpunkt). Fallstricke: zerrissene Tabellenwerte (DND-004/005); 2014-Aktionsökonomie. Version: 2024. Quelle: SRD 5.2.1 (DE), Ausrüstung/Heiltrank. Fehlende Info: n. a.

*Kategorien-Abdeckung:* Grundregel (01, 02, 06, 14, 28) · häufige Spielerfrage (04, 16, 20) · Regelausnahme (03) · Kombination (05, 15, 19) · mehrdeutig (09) · versionsabhängig (13, 23, 27) · falsche Annahme (07, 17, 18) · ohne eindeutige RAW-Antwort (25) · SL-Entscheidung (24, 25) · nicht unterstützt (11, 12) · widersprüchlich interpretiert (24) · Quellenfrage (26) · unvollständige Info (27) · Rückfrage nötig (09, 27) · ähnlich klingende Begriffe (10, 23) · Klassenmerkmal/Meisterschaft (08) · Neue 2024-Mechanik (21) · Abkürzung (22).

---

## 17. Offene Fragen und Annahmen

1. **Pi-Bestand ungesehen:** Alle Textbefunde stammen aus der lokalen Dev-DB (srd-de + Open5e). Annahme: Der Pi-Import derselben Quellen zeigt dieselben Artefakte (gleicher Importer, gleiches PDF); die 10 DDB-Bücher konnten nicht stichprobiert werden — für sie gelten nur die Mechanik-Aussagen (Editionen autoritativ, Kapitel-Header-Filter, HTML-Bereinigung).
2. **DND-001-Wortlaut:** Der offizielle deutsche Name der Topple-Eigenschaft (vermutlich „Umwerfen") war mangels auffindbarem Eintrag nicht aus dem Bestand belegbar — beim Fix am PDF verifizieren.
3. **Eigenschaft „Reichweite" (Reach):** In der Eigenschaften-Kontextliste fehlt ein Reach-Eintrag (vorhanden: Fernkampf-/Nahkampfreichweite, Finesse, Geschosse, Laden, Leicht, Schwer, Vielseitig, Wurfwaffe). Ob Reach unter anderem Namen existiert oder wie Topple verloren ging, war nicht abschließend bestimmbar — Prüfauftrag im Zuge von DND-001.
4. **Talent-/Zauberzählungen:** Bestandszahlen (387 Zauber, 341 Monster, 17 Talente in 4 Kategorien) wirken für SRD 5.2.1 plausibel, wurden aber nicht gegen ein Inhaltsverzeichnis des Originals abgeglichen (liegt dem Review nicht vor). Vollständigkeit „alle SRD-Zauber vorhanden" bleibt eine offene Verifikation (Stichproben-Zauber wurden alle gefunden).
5. **Verhaltensschicht:** Ob das Modell die gelieferten Grounding-/Format-Hinweise befolgt (T2/T10/T12, Aussagearten), ist erst mit der ausstehenden Chat-Abnahme messbar; diese Review bewertet die Server-Seite und die Datenlage.
6. **dnddeutsch-Abdeckung:** Annahme, dass fehlende Glossarzeilen (weapon mastery, emanation) an der Quell-API liegen (2024-Neubegriffe) — Cache-Dateien wurden nicht einzeln geprüft; der Fix (kuratierte Paare) ist davon unabhängig wirksam.

---

## 18. Gesamturteil zur fachlichen MVP-Reife

| Dimension | Note (1–10) | Begründung |
|---|---|---|
| Fachliche Richtigkeit | **7** | Alle geprüften Kernregeln 2024-korrekt (inkl. typischer 2014-Fallen); Abzug für den nachgewiesenen fusionierten Topple-Text (DND-001) und die Verlesbarkeit zerrissener Statblocks (DND-004). |
| Trennung der Regelversionen | **9** | 2014/2024 technisch erzwungen, autoritative Editionszuordnung, kein stilles Mischen, Altstand markiert; kleiner Abzug für die pauschale „älterer Stand"-Etikettierung künftiger Editionen. |
| Vollständigkeit im beanspruchten Umfang | **7** | SRD-Kern (Regeln, Zustände, Zauber, Monster, Charakterbau) breit vorhanden und auffindbar; Abzüge: Topple fehlt, Reach unklar, dt. 2024-Grundbücher noch nicht importiert (bekannt, M1). |
| Umgang mit Regelausnahmen | **7** | Volltexte + Einzeleinträge für Spezialregeln liefern die nötige Basis; keine strukturelle Ausnahme-Verknüpfung, Auflösung liegt beim Modell (dokumentierte Systemgrenze). |
| Quellenqualität | **8** | Offizielle Primärquellen mit sauberer Präzedenz; Open5e als Sekundärquelle korrekt nachrangig (Kennzeichnung nur über den Titel); Lizenz je Eintrag. |
| Nachvollziehbarkeit | **9** | Quelle · Seite · Version an jeder Auskunft, Seitenzahlen stichprobenkonsistent, Provenienz bei Dubletten sichtbar, Build-Prüfung belegt ihre Datenbasis. |
| Verständlichkeit für Spielende | **7** | Deutsch-first mit offiziellem Vokabular, klares Antwortschema, ehrliche Lücken; Abzug für Wortrisse/Laufköpfe in Zitaten und Mehrdeutigkeits-Umwege bei Suffix-Namen. |
| Eignung für Spielleitende | **7** | Monster/Gegenstände/Gefahren schon nutzbar, Erweiterung strukturell vorbereitet; fehlende Inhaltsarten-Kennzeichnung und Meta-Filter begrenzen SL-Nutzung heute. |
| Fachliche Testabdeckung | **7** | T1–T12 serverseitig + Smoke mit echten Regelfällen ist stark; es fehlen Inhalts-Regressionstests (8 Meisterschaften, Statblock-Integrität, Zauber-Vollzähligkeit) und die Verhaltens-Abnahme steht aus. |
| **Allgemeine fachliche MVP-Reife** | **7** | Tragfähiges, ehrliches Regel-Nachschlagewerk mit korrektem 2024-Kern; vor der Rundenfreigabe müssen DND-001 und DND-003 behoben und DND-002 zumindest minimal (Playtest-Ausschluss) entschärft werden. |

**Kernaussage:** Foliant beantwortet die Frage „Kann ein Sprachmodell am Spieltisch belegt und versionsrein aus *meinen* Quellen antworten?" fachlich überzeugend: Die Editions- und Belegdisziplin ist besser als bei den meisten digitalen Regelhilfen, und die geprüften 2024-Inhalte sind korrekt. Die verbleibenden Risiken sind konkret und lokalisierbar — ein verlorenes Überschriften-Heading mit Regelfolgen (DND-001), eine fehlende Inhaltsarten-Kennzeichnung (DND-002) und ein vermeidbares Falsch-Negativ (DND-003). Alle drei sind mit kleinen bis mittleren Eingriffen behebbar, ohne das Konzept anzutasten.

---

## Bestätigung der Unversehrtheit des Projekts

`git status` nach Abschluss dieser Review: unter `docs/reviews/` liegen ausschließlich neu erstellte Review-Dateien (untracked); **keine bestehende Projektdatei wurde verändert oder gelöscht** — alle Prüfungen dieser fachlichen Review erfolgten lesend (SELECT-Abfragen, Tool-Aufrufe gegen die lokale Datenbank, pytest gegen temporäre Fixture-Datenbanken).
