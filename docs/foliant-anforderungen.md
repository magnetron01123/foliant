# Foliant — Anforderungskatalog (MVP)

**D&D-5e-Regelassistent für die eigene Runde · Deutsch-first · Stand: 07.07.2026 · Rev. 8**

> **Zweck dieses Dokuments:** Es hält **alle Anforderungen** an den MVP klar und strukturiert fest — das **„Was", nicht das „Wie"**. Auf dieser Basis wird anschließend in einem separaten Schritt die **technische Umsetzung** erarbeitet. Frühere Dokumente (Recherche, Konzept) liefern nur Kontext; maßgeblich für den Leistungsumfang ist ab jetzt dieses Dokument.
>
> **Rev. 2:** Begriffsübernahme aus älteren offiziellen deutschen Ausgaben präzisiert (§5, §6) — **Terminologie wird getrennt von der Regelversionierung behandelt.**
>
> **Rev. 3:** Klärungspunkte beantwortet (§11): DDB-Charakter-Abruf bleibt draußen (nächste Stufe); Versionsschema erweiterbar (§6 V7); noch nicht aktualisierte Altregeln bewusst nutzbar, aber immer als alter Stand gekennzeichnet (§6 V8).
>
> **Rev. 4:** Charaktererstellungs-Hilfe **inkl. automatischer Build-Prüfung** im MVP bestätigt (K1b); K3 bewusst beibehalten; **Maßnahmen zur Problemvermeidung** ergänzt (neues §12).
>
> **Rev. 5:** Bedien- & Interaktionsanforderungen aus Spielersicht ergänzt (neues §13) — u. a. geerdete Antworten/keine Halluzination, ehrliche Lücken, zweisprachige tolerante Suche, Mehrdeutigkeit auflösen, klare Umfangs-Ablehnung.
>
> **Rev. 6:** Prozess-Lücken geschlossen — **Abnahme- & Testkriterien** (neues §14) und **Betrieb & Pflege** (neues §15: Backup, Aktualisierung, Import-Qualitätsprüfung, Feedback, Secrets).
>
> **Rev. 7:** Übersetzung optimiert (§5) — offizielles Deutsch 2024 ist breit verfügbar (dt. Grundregelwerke 2024). Daher: **deutscher Regeltext primär** (S10), volle Fallback-Leiter, **immersionswahrende markierte deutsche Wiedergabe statt Englisch** (S3.4), Konsistenz & robuste Begriffserkennung (S11). `*` wird zur Ausnahme.
>
> **Rev. 8:** Open5e (API, engl.) als MVP-Quelle aufgenommen (F5b); **Seitenzahl optional** — Pflicht ist die Quelle (Buch/Dokument + Edition), Seite nur wenn vorhanden (P4/F7). Open5e wird ohne Seite zitiert.

---

## 1. Zweck & Name

- **Name:** **Foliant**.
- **Zweck:** Foliant ist ein privat betriebener Assistent, der als **Regel-Nachschlagewerk** für D&D 5e dient — Regeln nachschlagen, Steckbriefe abrufen, bei der Charaktererstellung unterstützen. Antworten in korrektem Spieldeutsch, mit belegten Quellen und eindeutiger Regelversion.
- Foliant soll **vollständig funktionieren, gut umsetzbar und später ausbaubar** sein — und dabei **nur so komplex wie nötig**.

---

## 2. Leitprinzipien (gelten übergreifend)

- **P1 — Aktuelle Regeln zuerst:** Standard ist stets das aktuelle Regelwerk (D&D 2024, „5.5e"). Ältere Regelstände werden nicht stillschweigend beigemischt.
- **P2 — Version immer sichtbar:** Jede gespeicherte Regel trägt ihre D&D-Regelversion; jede Regelauskunft nennt sie (Details §6). *Sehr wichtig,* weil wir nach aktuellen Regeln spielen und ältere Regeln oft angepasst werden müssen, damit sie passen.
- **P3 — Deutsch-first, offiziell:** korrekte offizielle deutsche Begriffe, **nicht** wörtlich übersetzt; englisches Original **immer** in Klammern; fehlt eine offizielle Übersetzung, Kennzeichnung mit `*` (Details §5).
- **P4 — Belegt:** jede Regelauskunft mit **Quelle** (immer); **Seite** nur, wenn die Quelle eine hat (§4 F7).
- **P5 — So einfach wie möglich:** keine Features über den definierten Umfang hinaus; Komplexität nur dort, wo eine Anforderung sie zwingend verlangt.

---

## 3. Umfang (Scope)

| Im MVP | Nicht im MVP (ggf. später) |
|---|---|
| Regeln nachschlagen (Kampf + außerhalb) | Kampagnen-/Abenteuerinhalte, Spoiler |
| Steckbriefe (Zauber, Monster, Gegenstände) | Trennung Spielleiter/Spieler, Rollen, Tokens |
| Charaktererstellung unterstützen \* | **DDB-Charakter-Abruf** (bestehende Charaktere laden) |
| Quellen-Import aus eigenen PDFs | Würfel-Tool, Initiative-Tracker |
| **Quellen-Import aus D&D Beyond (Bücher)** | Hausregeln-Overlay |
| **Quellen-Import aus Open5e (API, engl.)** | |
| Deutsch-Ausgabe mit Begriffs-/Quellenregeln | |
| Regelversion bei jeder Ablage | |

\* Charaktererstellungs-Hilfe **inkl. automatischer Build-Prüfung** ist im MVP enthalten (F3); Verlässlichkeits-Maßnahmen in §12 (Q4).

---

## 4. Funktionale Anforderungen

**F1 — Regeln nachschlagen.** Volltextsuche über alle eingelesenen Regelwerke, für Kampf *und* außerhalb (Zustände, Ruhephasen, Fertigkeits-/Attributsproben, Umgebung, soziale Interaktion usw.). Ergebnis mit Fundstelle, Quelle, ggf. Seite und Regelversion.

**F2 — Steckbriefe.** Exakte Einzelabfrage kompletter Einträge für Zauber (Spell), Monster und Gegenstände (Item).

**F3 — Charaktererstellung unterstützen.** Aktive Hilfe beim Bauen eines Charakters nach **aktuellen** Regeln: Optionen liefern (Spezies, Klassen inkl. Unterklassen, Hintergründe, Talente), Attributswert-Methoden (Standard-Array / Point-Buy) und eine **automatische Build-Prüfung** auf Regelkonformität. Die Beratung führt Claude; Foliant liefert Daten und Prüfung. Verlässlichkeits-Maßnahmen für die Prüfung: §12 (Q4).

**F4 — Quellen-Import aus eigenen PDFs.** Eigene, legal vorliegende Regelwerk-PDFs müssen eingelesen und durchsuchbar gemacht werden können. (Wichtig — u. a. liegt das offizielle deutsche SRD nur als PDF vor.)

**F5 — Quellen-Import aus D&D Beyond (Bücher).** Auf D&D Beyond gekaufte Regelwerke müssen als Quellen importiert werden können. (Wichtig. Betrifft ausschließlich **Bücher/Regelinhalte**, nicht Charaktere.)

**F5b — Quellen-Import aus Open5e (API).** Der Open5e-Content (engl., CC/OGL) muss als Quelle importiert werden können — eine breite Sofort-Basis (Zauber, Monster, Hintergründe) ohne eigene Bücher. **Einmaliger** Import in denselben Bestand, **kein** Laufzeit-API-Aufruf. Englisch → mit offiziellen deutschen Begriffen annotiert (S3-Fallback); **geringere Präzedenz** als deutsche Quellen (Q2). Abdeckung ist partiell und editionsgetaggt (srd-2024/srd-2014).

**F6 — Mischbetrieb der Quellen.** PDF-, DDB- und Open5e-Quellen landen im selben durchsuchbaren Bestand; welche Quelle über welchen Weg kommt, ist frei wählbar (z. B. deutsche PDF vor Open5e, wo vorhanden).

**F7 — Quellenangabe.** Jede Regelauskunft nennt die **Quelle** (Buch/Dokument + Edition) — **immer**. Eine **Seitenzahl nur, wenn die Quelle eine hat** (Bücher/PDFs); Quellen ohne Seiten (z. B. Open5e-API) werden allein mit Quelle/Edition zitiert.

*(Sprach-/Übersetzungsregeln → §5, Regelversion → §6 — jeweils als eigener Anforderungsblock.)*

---

## 5. Sprach- & Übersetzungsanforderungen

**S1 — Sprache:** Antworten in korrektem Spieldeutsch.

**S2 — Korrekte, nicht wörtliche Begriffe:** Verwendet werden die **offiziellen** deutschen Begriffe, keine wörtlichen Eigenübersetzungen.

**S3 — Begriffsquellen (Priorität, von oben nach unten):** Korrekte deutsche Begriffe stammen aus vorhandenen **offiziellen** Quellen, in dieser Reihenfolge:

1. **Aktuelles offizielles Deutsch 2024** — deutsches SRD 5.2.1 **und** die offiziellen deutschen Grundregelwerke 2024 (Spielerhandbuch, Spielleiterhandbuch, Monsterhandbuch), sofern als Quelle vorhanden; im Glossar der Ulisses-2024-Begriff (dnddeutsch.de `name_de_ulisses`).
2. Offizielles Deutsch aus **älteren** offiziellen Büchern (z. B. „Van Richtens Ratgeber zu Ravenloft" – DE, 2014-Basis) sowie dem **Ulisses-Glossar** (dnddeutsch.de `name_de_ulisses`).
3. **Inoffizielle**/Community-Übersetzung → `*`.
4. **Keine** offizielle Entsprechung → **konsistente, markierte deutsche** Wiedergabe mit `*` — *nicht* Englisch mitten im Satz (Immersion); englisches Original wie immer in Klammern.

Stufen 1–2 gelten als offiziell (**kein** `*`); Stufen 3–4 werden mit `*` markiert.

**S4 — Englisches Original immer in Klammern:** bei **jeder** Nennung, z. B. „Gelegenheitsangriff (Opportunity Attack)".

**S5 — Kennzeichnung fehlender offizieller Übersetzung:** Gibt es keinen offiziellen deutschen Begriff (nur eine inoffizielle/eigene Übersetzung oder gar keine), wird der Begriff mit **`*`** markiert und einmalig erläutert („\* keine offizielle deutsche Übersetzung").

**S6 — Offiziell vs. inoffiziell unterscheidbar:** Intern muss erkennbar sein, ob ein Begriff offiziell belegt ist oder nicht — das ist die Grundlage für die `*`-Kennzeichnung.

**S7 — Terminologie ist editionsübergreifend (Begriffe ≠ Regeln).** Offizielle deutsche **Begriffe** dürfen aus älteren offiziellen deutschen Büchern übernommen werden, auch wenn der zugehörige **Inhalt** aus einem neueren, noch nicht übersetzten englischen Buch stammt. Ein aus einer Altausgabe übernommener Begriff gilt als korrekt/offiziell und erhält **weder** ein `*` **noch** eine „veraltet"-Kennzeichnung. Grund: Die deutsche Vokabel für ein Konzept ist weitgehend stabil, während sich die *Regel* dahinter ändern kann — Letzteres regelt allein §6 am **Inhalt**, nicht am Begriff.

**S8 — Konfliktregel & Bedeutungsdrift.** Gibt es für denselben Begriff einen **neueren** offiziellen deutschen Begriff, hat dieser Vorrang vor dem älteren. Hat sich die Bedeutung oder Benennung zwischen Editionen geändert, folgt der Begriff dem **aktuellen** Regelinhalt; die Versionskennzeichnung am Inhalt (§6) bleibt davon unberührt.

**S9 — Herkunft des Begriffs mitführen.** Zu jedem Begriff wird intern seine Quelle gespeichert (welches Buch/Glossar, welche Ausgabe) — als Grundlage für die Offiziell-Prüfung (S6) und die Konfliktregel (S8). Für den Nutzer sichtbar ist davon nur die `*`-Kennzeichnung bzw. die normale Quellenangabe.

> **Beispiel (das genannte Muster):** Inhalt aus „Ravenloft: Horrors Within" (EN, nicht übersetzt) → der **Regeltext** bleibt englisch und wird mit seiner Regelversion getaggt (§6). Die deutschen **Begriffe** dazu werden, soweit vorhanden, aus „Van Richtens Ratgeber zu Ravenloft" (DE, 2014-Basis) übernommen und gelten als offiziell (**kein** `*`). Nur Begriffe, für die es **nirgends** ein offizielles Deutsch gibt, bekommen `*`.

**S10 — Immersion zuerst: deutscher Regeltext primär.** Wo deutsche Quellen vorliegen, wird der **deutsche Regeltext direkt** verwendet — dazu werden die offiziellen deutschen Quellen importiert: **deutsches SRD 5.2.1** sowie die **offiziellen deutschen Grundregelwerke 2024 (Spielerhandbuch, Spielleiterhandbuch, Monsterhandbuch) als PDF**, dazu weitere vorhandene deutsche Bücher. Die Kombination „englischer Text + Begriffsannotation" greift nur für Inhalte, die es **ausschließlich** auf Englisch gibt. (Größter Immersions-Hebel.)

**S11 — Konsistenz & robuste Begriffserkennung.** Ein Begriff erhält **eine** kanonische deutsche Fassung, die überall gleich verwendet wird (Wiedererkennung = Immersion). Die Begriffserkennung normalisiert **Flexion, Groß-/Kleinschreibung und Komposita**, damit ein vorhandener offizieller Begriff nicht fälschlich als „fehlt" gilt und ein **unnötiges `*`** kassiert.

---

## 6. Regelversionierung (sehr wichtig)

**V1 — Version bei der Ablage:** Jeder gespeicherte Regel-/Inhaltseintrag trägt **zwingend** seine **D&D-Regelversion** — Pflicht: 2024 („5.5e") vs. 2014 („5e"); Quellbuch, wo ohnehin bekannt; Errata-/Ausgabestand optional.

**V2 — Aktuell als Standard:** Auskünfte beziehen sich standardmäßig auf das **aktuelle** Regelwerk (2024).

**V3 — Version in der Antwort:** Jede Regelauskunft nennt die Regelversion (zusätzlich zu Quelle, ggf. Seite).

**V4 — Ältere Stände markieren:** Liegt Inhalt nur in einer älteren Version vor, wird das in der Antwort **deutlich kenntlich gemacht**, mit Hinweis, dass eine Anpassung an die aktuellen Regeln nötig sein kann.

**V5 — Keine stille Vermischung:** Ältere und aktuelle Regelstände werden nie ununterscheidbar zusammengeführt.

**V6 — Terminologie ausgenommen.** Die Versionsregeln V1–V5 betreffen **Regelinhalte**. Aus älteren offiziellen deutschen Büchern übernommene **Begriffe** (S7) gelten *nicht* als „älterer Regelstand" und werden nicht als anpassungsbedürftig markiert.

**V7 — Erweiterbares Versionsschema.** Die Regelversion wird als **strukturiertes, erweiterbares** Feld abgelegt (nicht als starres 2024/2014-Flag), damit spätere Ausbaustufen feinere Granularität (Quellbuch, Errata, Druckauflage) oder weitere Editionen **ohne Migration** ergänzen können.

**V8 — Noch nicht aktualisierte Altregeln bewusst nutzbar.** Ältere Regelinhalte dürfen aufgenommen und durchsucht werden — gerade Regeln ohne 2024-Entsprechung können relevant sein. Werden sie ausgegeben, erfolgt **immer** ein deutlicher **Hinweis auf den alten Stand** (V4), damit klar ist, dass ggf. eine Anpassung an die aktuellen Regeln nötig ist.

---

## 7. Nicht-funktionale Anforderungen

**NF1 — Self-hosted:** Betrieb auf eigener Hardware, in eigener Kontrolle.

**NF2 — Zugang über Claude:** Nutzung als Custom Connector in Claude; der kostenlose Free-Plan (genau ein Connector) muss genügen.

**NF3 — Privat:** ausschließlich für die eigene Runde; keine öffentliche Bereitstellung.

**NF4 — Legale Quellen:** frei lizenziertes SRD (CC-BY-4.0) sowie eigene, legal erworbene Inhalte. DDB-Extraktion nur privat (ToS-Grauzone, bewusst akzeptiert).

**NF5 — Kosten:** keine laufenden Kosten außer Strom; Software Open Source, Inhalte bereits vorhanden.

**NF6 — Nur so komplex wie nötig.**

**NF7 — Erweiterbar:** spätere Ausbaustufen (§9) müssen ohne Neuaufbau andocken können.

**NF8 — Einfache Ersteinrichtung** für Nutzer (URL als Connector eintragen, im Chat aktivieren).

---

## 8. Ausdrücklich nicht im MVP (Nicht-Ziele)

- Keine Kampagnen-/Abenteuerinhalte, keine Spoiler-Verwaltung.
- Keine Rollentrennung Spielleiter/Spieler, keine Tokens oder getrennten Zugänge.
- **Kein DDB-Charakter-Abruf** (bestehende Charaktere aus D&D Beyond laden).
- Kein Würfel-Tool, kein Initiative-Tracker.
- Kein Hausregeln-Overlay.

---

## 9. Spätere Ausbaustufen (nur vorgemerkt, nicht v1)

- **A1 — DDB-Charakter-Abruf:** bestehende Charaktere/Gruppe aus D&D Beyond laden.
- **A2 — Kampagnenspezifik:** Inhalte und Kontext je Kampagne (z. B. Fluch des Strahd).
- **A3 — Rollen SL/Spieler + Spoiler-Schutz:** getrennte Zugänge und ein separater Abenteuer-Bereich, der über einen Spieler-Zugang technisch nie geöffnet wird.
- **A4 — Hausregeln:** eigene Tischregeln, die die RAW-Antwort sichtbar überlagern.

---

## 10. Gesetzte technische Rahmenbedingungen (bereits entschieden — Kontext, nicht Teil der Anforderungsdefinition)

Aus früheren Entscheidungen fixiert; dienen der nachfolgenden technischen Ausarbeitung als Randbedingungen und können dort bestätigt/angepasst werden:

- MCP-Server auf Basis **FastMCP**, Anbindung als Claude Custom Connector.
- **SQLite** mit Volltextsuche (**FTS5**) als Datenbasis.
- **Cloudflare Tunnel** für die öffentliche Erreichbarkeit.
- Deutsch-/Begriffsabgleich über die **dnddeutsch.de**-Glossar-API.
- DDB-Quellen-Extraktion über die **MrPrimate-Toolchain** als Einmal-Import.

---

## 11. Entscheidungen

**Alle Klärungspunkte beantwortet (07.07.2026):**

- **K1 → DDB-Charaktere:** Im MVP **nur Quellen-Import**; **kein** Abruf bestehender Charaktere → nächste Ausbaustufe (§9 A1).
- **K1b → Charaktererstellungs-Hilfe:** **im MVP enthalten**, inkl. **automatischer Build-Prüfung** (F3). Verlässlichkeit über §12 (Q4).
- **K2 → Versionierung:** wie empfohlen — 2024/2014 Pflicht, Quellbuch wo bekannt, Errata optional; Schema **erweiterbar** (§6 V7).
- **K3 → Altbücher:** **Begriffe *und* Regeln** — bewusst beibehalten, weil es das Wissen vergrößert. Die Verwässerungs-Gefahr der Suche wird über §12 (Q1–Q2) abgefangen; alte Regeln immer als alter Stand gekennzeichnet (§6 V4/V8).

---

## 12. Maßnahmen zur Problemvermeidung (Qualität & Integrität)

Diese Anforderungen fangen die im Entwurf benannten Risiken ab — vor allem die durch das Beibehalten alter Regeln (K3), die Build-Prüfung (K1b) und den Mehrquellen-Import (PDF + DDB) entstehenden.

**Q1 — Suche: aktuell zuerst.** Jede Suche liefert standardmäßig **2024**-Inhalte. Existiert zu einem Treffer eine 2024-Fassung, ist sie die primäre Antwort; ältere Fassungen erscheinen nur als **klar als alt gekennzeichneter Zusatz** oder auf ausdrücklichen Wunsch — nie anstelle der aktuellen. (Gegen Such-Verwässerung durch K3.)

**Q2 — Dubletten & Quellen-Präzedenz.** Kommt derselbe Inhalt in gleicher Version aus mehreren Quellen (z. B. ein 2024-Zauber aus SRD *und* gekauftem PHB), wird eine **kanonische Quelle** bestimmt, damit keine redundanten Treffer entstehen. Die Präzedenz-Reihenfolge wird beim Import festgelegt.

**Q3 — Pflicht-Version, keine „verwaisten" Inhalte.** Kein Inhalt gelangt **ohne** gesetzte Regelversion und Quellenangabe in den Bestand. Bei PDFs, deren Version nicht automatisch erkennbar ist, wird sie **pro Dokument beim Import explizit gesetzt**; fehlt sie, wird nicht importiert. (Sichert V1, F7.)

**Q4 — Build-Prüfung: streng, transparent, ehrlich über Lücken.** Die automatische Build-Prüfung (F3) validiert **ausschließlich gegen 2024** und mischt keine Altregeln ein. Sie **nennt ihre Datenbasis** und weist **offen aus, was sie nicht prüfen kann** (z. B. „Option X nicht im Bestand"), statt still zu bestehen oder durchfallen zu lassen. Sie versteht sich als **Hilfe, nicht als letzte Instanz**.

**Q5 — Begriffskonflikte kontrolliert auflösen.** Weicht ein Begriff zwischen Altbuch und neuerer Quelle ab, gewinnt der **neuere offizielle** Begriff (S8); der Konflikt wird intern **protokolliert** (S9) und bleibt so prüfbar.

**Q6 — Recht & Attribution.** Die CC-BY-Pflichtattribution (SRD) wird mitgeführt; aus D&D Beyond gewonnene Inhalte bleiben **strikt privat** und werden nicht weitergegeben (NF4).

**Q7 — Laufzeit ohne externe Abhängigkeit.** DDB-Quellen werden **einmalig importiert**, nicht zur Laufzeit abgefragt; das Nachschlagen funktioniert vollständig **offline**. Da der Charakterabruf draußen ist, hat der MVP zur Laufzeit **keine** DDB-Abhängigkeit.

*Die konkrete Umsetzung dieser Maßnahmen (Ranking, Dedup-Mechanik, Import-Ablauf) gehört in die technische Ausarbeitung.*

---

## 13. Bedien- & Interaktionsanforderungen (aus Spielersicht)

Ergebnis eines Durchspielens aus Spielersicht (Charakter bauen → im Spiel Regeln fragen). Es geht um Bedien-, Umgangs- und Regelprobleme und ihre Lösung — **keine neuen Features**.

**B1 — Geerdete Antworten, kein Halluzinieren.** Regel- und Charakterauskünfte stützen sich **ausschließlich** auf den importierten Bestand. Findet Foliant nichts, wird das **klar gesagt** („dazu finde ich nichts im Bestand"), statt aus allgemeinem Wissen zu antworten oder zu erfinden. *Wichtigste Maßnahme* — das Modell bringt sehr viel D&D-Wissen (inkl. 2014 und Homebrew) mit und füllt Lücken sonst selbst.

**B2 — Lücken ehrlich benennen.** Ist eine gewünschte Option/Regel nicht im Bestand (z. B. nicht im SRD: Aasimar, Artificer, viele Unterklassen), sagt Foliant das **ausdrücklich**, statt sie stillschweigend zu übergehen oder zu ersetzen — damit klar ist, dass ggf. ein Buch importiert werden muss. (Erweitert Q4 auf alle Abfragen.)

**B3 — Suche zweisprachig & tolerant.** Die Suche akzeptiert deutsche **und** englische Begriffe (Brücke über das Glossar, S3) sowie gängige Abkürzungen und kleine Tippfehler/Schreibvarianten. „opportunity attack", „Gelegenheitsangriff" und „AoO" landen beim selben Eintrag.

**B4 — Mehrdeutigkeit auflösen statt raten.** Passen mehrere Einträge (z. B. „Schild" = Zauber *oder* Rüstung), liefert Foliant die **Kandidaten mit Unterscheidungsmerkmal** (Typ, Quelle, Version) zurück, damit rückgefragt werden kann — statt eine Möglichkeit zu raten.

**B5 — Alten Regelstand verständlich einordnen.** Gibt es **keine** 2024-Fassung, wird nicht bloß eine 2014-Regel mit `*` ausgegeben, sondern klar eingeordnet: „Keine 2024-Fassung im Bestand; hier der 2014-Stand — ggf. anzupassen." Ruhig und handlungsleitend. (Verfeinert V4/Q1 für die Ausgabe.)

**B6 — Außerhalb des Umfangs klar ablehnen.** Fragen zu Abenteuer-/Kampagneninhalten (z. B. „Wie besiege ich Strahd?", „Was passiert in Kapitel 3?") werden **klar als außerhalb des Umfangs** behandelt und **nicht** aus allgemeinem Wissen beantwortet (Spoiler- und Halluzinationsgefahr). Das hält zugleich die Grenze zur späteren Kampagnen-/Spoiler-Stufe (A2/A3) sauber.

**B7 — Charakterbau in korrekter 2024-Reihenfolge führen.** Beim Erstellen leitet Foliant Schritt für Schritt in der **2024-Reihenfolge** (Klasse → Hintergrund → Spezies → Details), statt alle Optionen auf einmal auszuschütten. Die Reihenfolge/Anleitung ist im Server hinterlegt (wie die Stil-Regeln), damit die Führung konsistent ist.

**B8 — Erwartungen setzen: kein Gedächtnis, keine Hausregeln.** Foliant **speichert den Charakter nicht** und kennt **keine Hausregeln** (beides spätere Stufen). Der Spieler wird darauf hingewiesen, den Charakterbogen anderswo zu führen (Papier/DDB) und dass Auskünfte **RAW** sind — so entstehen keine falschen Erwartungen.

**B9 — Schnell & verfügbar im Spielbetrieb.** Nachschlagen muss **zügig** antworten und der Dienst während einer Session **erreichbar** sein — im laufenden Spiel zählt Tempo mehr als beim Charakterbau. (Betriebs-/Antwortzeit-Qualität; Umsetzung in der Techspec.)

**B10 — Einrichtung spielerfest.** Das Eintragen des Connectors muss auch für nicht-technische Mitspieler mit einer **klaren Kurzanleitung** gelingen; da Custom Connectors Beta sind, gehört ein **Fallback**/Hinweis dazu, falls die Verbindung hakt. (Verstärkt NF8.)

---

## 14. Abnahme- & Testkriterien

Definiert „fertig" und macht die Anforderungen — besonders die Verhaltensregeln — **prüfbar**. Jede Zeile ist ein konkreter Test.

- **T1 (F7/P4):** Eine im Bestand vorhandene Regelfrage wird mit **Quelle und Regelversion** beantwortet (Seite, wenn die Quelle eine hat; Open5e ohne Seite).
- **T2 (B1/B2):** Eine Frage nach etwas, das **nicht** im Bestand ist (z. B. Aasimar bei reinem SRD), liefert ein **ehrliches „nicht gefunden"** — keine erfundene Antwort.
- **T3 (S4/S5):** Ein Begriff ohne offizielle deutsche Übersetzung erscheint **mit `*`** und englischem Original in Klammern; ein offizieller Begriff **ohne** `*`.
- **T4 (S3/S7):** Ein aus einem Altbuch stammender offizieller deutscher Begriff wird verwendet und **nicht** mit `*` markiert.
- **T5 (V2/V4/B5):** Existiert nur eine 2014-Regel, wird sie **klar als alter Stand** ausgegeben („keine 2024-Fassung … ggf. anzupassen").
- **T6 (Q1):** Bei 2024- *und* 2014-Treffer steht die **2024-Fassung primär**, die 2014 nur als markierter Zusatz.
- **T7 (B3):** „opportunity attack", „Gelegenheitsangriff" und „AoO" führen zum **selben Eintrag**.
- **T8 (B4):** Ein mehrdeutiger Begriff („Schild") liefert **Kandidaten mit Unterscheidungsmerkmal**, keine geratene Einzelantwort.
- **T9 (F3/Q4):** Ein **illegaler Build** wird erkannt und begründet; was die Prüfung nicht prüfen kann, benennt sie offen.
- **T10 (B6):** „Wie besiege ich Strahd?" wird **als außerhalb des Umfangs** behandelt, nicht aus allgemeinem Wissen beantwortet.
- **T11 (Q3):** Ein Import **ohne gesetzte Regelversion** wird abgelehnt.
- **T12 (B7):** Der Charakterbau wird in **2024-Reihenfolge** geführt (Klasse → Hintergrund → Spezies).

---

## 15. Betrieb & Pflege

Lebenszyklus-Anforderungen, damit Foliant über die erste Version hinaus verlässlich bleibt.

- **O1 — Backup & Wiederherstellung.** Der Datenbestand (importierte Quellen, Glossar, Versionstags) wird **regelmäßig gesichert**; eine Wiederherstellung ist **ohne erneuten DDB-/PDF-Import** möglich. Sonst ist der gesamte Import-Aufwand bei Datenverlust verloren.
- **O2 — Inhalte aktuell halten.** Neue Errata, neue Bücher oder eine aktualisierte Glossar-Quelle lassen sich **nachträglich importieren**, ohne Neuaufbau; dabei greifen dieselbe Pflicht-Versionierung (Q3) und Qualitätsprüfung (O3). Das erweiterbare Versionsschema (V7) trägt das.
- **O3 — Import-Qualitätsprüfung vor Freigabe.** Neu importierter Inhalt — v. a. aus PDF — wird vor der Freischaltung **stichprobenartig geprüft** (korrekte Zahlen, Leserichtung, keine zerrissenen Statblöcke), damit keine fehlerhaften Regeln in die Suche gelangen. (Ergänzt Q3 um die inhaltliche Qualität.)
- **O4 — Feedback-/Korrekturschleife.** Schlechte Suchtreffer oder falsche Auskünfte werden **gesammelt und nachgezogen** (Synonyme, Chunking, Korrekturen); ein einfacher Melde-Weg ist vorzusehen.
- **O5 — Secrets sicher halten.** Zugangsdaten (v. a. der Cobalt-Cookie für den DDB-Import) werden **nur server-seitig** gehalten und **erneuert**, wenn sie ablaufen (Logout/Passwortwechsel). Ohne gültigen Cookie schlägt nur der DDB-*Import* fehl, nicht der laufende Betrieb (Q7).

---

## 16. Belege (externe Fakten, die den Umfang geprägt haben)

- Offizielles **deutsches SRD 5.2.1** liegt nur als **PDF** vor (Ankündigung dnddeutsch, Dez. 2025; WotC-Lokalisierungsplan). → begründet F4.
- **SRD 5.2.1** ist CC-BY-4.0 und deckt nur eine Teilmenge des 2024er-PHB (je 1 Unterklasse, 4 Hintergründe, kein Aasimar/Artificer …). → begründet F5 (Lücken via eigene Bücher/DDB).
- **DDB-Bücher** sind kein Download; Extraktion nur über die MrPrimate-Toolchain, Regelinhalte teils Patreon-gated bzw. via eigenem Proxy (`github.com/MrPrimate/ddb-proxy`, `docs.ddb.mrprimate.co.uk`). → prägt F5.
- **Claude Custom Connectors:** Beta, Free-Plan = genau ein Connector (`support.claude.com`). → prägt NF2.
- **D&D 2024** wird auf D&D Beyond als „5.5e", 2014 als „5e" geführt; beide bleiben unterstützt. → prägt P1/§6.
- **Begriffs-Beispiel (von dir):** „Van Richtens Ratgeber zu Ravenloft" (DE, Ulisses, 2014-Basis) liefert offizielle deutsche **Begriffe**, die auch für neueres, unübersetztes Material („Ravenloft: Horrors Within", EN) gelten. → prägt S3/S7 (Titel als Beispiel übernommen, nicht eigenständig geprüft).
- **Offizielles Deutsch 2024 ist verfügbar:** deutsches Spielerhandbuch 2024 (8. Mai 2025), Spielleiterhandbuch (26. Juni 2025), Monsterhandbuch (Sept. 2025); das dt. Spielerhandbuch enthält ein Regelglossar (ab ~S. 360) mit den neuen 2024-Begriffen (u. a. Ausströmung/Emanation, Waffenmeisterschaft/Weapon Mastery, Expertise, Gepackt/Grappled). Quellen: dnddeutsch.de, buffed.de, gamestar.de, amazon.de. → entkräftet die frühere Annahme „offizielles Deutsch dünn"; prägt S3/S10.
- **Open5e** (`api.open5e.com`, v2): CC/OGL-Community-Aggregation mit partieller 2024-Abdeckung (srd-2024 u. a. Hintergründe/Zauber/Kreaturen) neben srd-2014; englisch, keine Seitenzahlen. → prägt F5b/F7.
