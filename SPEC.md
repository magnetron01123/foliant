# Foliant — Spezifikation (das verbindliche „Was")

**D&D-5e-Regelassistent (Fassung 2024), Deutsch-first · self-hosted MCP-Server**
**Rev. 10 · Stand: 11.08.2026** *(Rev. 1–8: Anforderungskatalog; Rev. 9: Konsolidierung,
Widersprüche aufgelöst, Charakterbogen-Übersetzer aufgenommen; Rev. 10: Datenqualitäts-Schicht
— S12, V9, V10, B11 — und die Nummerierung aus Rev. 8 geheilt)*

Dieses Dokument definiert, **was** Foliant können muss und **wie es sich verhalten muss** —
nicht, wie es gebaut ist (das steht in [CONCEPT.md](CONCEPT.md)). Bei fachlichen Fragen gilt
dieses Dokument. Was noch offen ist, steht in [BACKLOG.md](BACKLOG.md).

---

## 1. Zweck & Umfang

**Foliant** ist ein privat betriebener Assistent als **Regel-Nachschlagewerk** für D&D 5e:
Regeln nachschlagen, Steckbriefe abrufen, bei der Charaktererstellung unterstützen. Antworten
in korrektem Spieldeutsch, mit belegten Quellen und eindeutiger Regelversion. Vollständig
funktionierend, gut umsetzbar, später ausbaubar — **und nur so komplex wie nötig**.

| Im Umfang | Ausdrücklich NICHT im Umfang |
|---|---|
| Regeln nachschlagen (Kampf + außerhalb) | Kampagnen-/Abenteuerinhalte, Spoiler-Verwaltung |
| Steckbriefe (Zauber, Monster, Gegenstände) | Rollentrennung Spielleiter/Spieler, Tokens |
| Charaktererstellung inkl. Build-Prüfung | **DDB-Charakter-Abruf** (Charaktere aus DDB laden) |
| Quellen-Import: eigene PDFs, D&D Beyond (Bücher), Open5e | Würfel-Tool, Initiative-Tracker |
| Deutsch-Ausgabe mit Begriffs-/Quellenregeln | Hausregeln-Overlay |
| Regelversion bei jeder Ablage | Charakter-Speicherung / Gedächtnis |
| **Charakterbogen-Übersetzer** (eigene Website, §14) | |

### Leitprinzipien (übergreifend)
- **P1 — Aktuelle Regeln zuerst:** Standard ist D&D 2024 („5.5e"). Ältere Stände werden nie
  stillschweigend beigemischt.
- **P2 — Version immer sichtbar:** Jede gespeicherte Regel trägt ihre Regelversion; jede
  Auskunft nennt sie (§4).
- **P3 — Deutsch-first, offiziell:** offizielle deutsche Begriffe, nicht wörtlich übersetzt;
  englisches Original **immer** in Klammern; fehlt offizielles Deutsch → `*` (§3).
- **P4 — Belegt:** jede Regelauskunft mit **Quelle** (immer); **Seite** nur, wenn die Quelle
  eine hat.
- **P5 — So einfach wie möglich:** keine Features über den definierten Umfang hinaus.

---

## 2. Funktionale Anforderungen

- **F1 — Regeln nachschlagen.** Volltextsuche über alle eingelesenen Regelwerke, für Kampf
  *und* außerhalb (Zustände, Ruhephasen, Proben, Umgebung, soziale Interaktion). Ergebnis mit
  Fundstelle, Quelle, ggf. Seite und Regelversion.
- **F2 — Steckbriefe.** Exakte Einzelabfrage kompletter Einträge für Zauber, Monster und
  Gegenstände.
- **F3 — Charaktererstellung unterstützen.** Optionen liefern (Spezies, Klassen inkl.
  Unterklassen, Hintergründe, Talente), Attributswert-Methoden (Standard-Array / Point-Buy)
  und eine **automatische Build-Prüfung** auf Regelkonformität. Die Beratung führt Claude;
  Foliant liefert Daten und Prüfung.
- **F4 — Import eigener PDFs.** Legal vorliegende Regelwerk-PDFs müssen einlesbar und
  durchsuchbar sein. *(Das offizielle deutsche SRD liegt nur als PDF vor.)*
- **F5 — Import aus D&D Beyond (Bücher).** Gekaufte Regelwerke müssen als Quellen importierbar
  sein — ausschließlich **Bücher/Regelinhalte**, nicht Charaktere.
- **F5b — Import aus Open5e (API).** Engl. CC/OGL-Content als breite Sofort-Basis.
  **Einmaliger** Import in denselben Bestand, **kein Laufzeit-API-Aufruf**. Geringere
  Präzedenz als deutsche Quellen. Abdeckung partiell und editionsgetaggt.
- **F6 — Mischbetrieb der Quellen.** Alle Quellen landen im selben durchsuchbaren Bestand;
  welcher Inhalt über welchen Weg kommt, ist frei wählbar.
- **F7 — Quellenangabe.** Jede Regelauskunft nennt die **Quelle** (Buch/Dokument + Edition) —
  **immer**. Eine **Seitenzahl nur, wenn die Quelle eine hat**; Quellen ohne Seiten (Open5e)
  werden allein mit Quelle/Edition zitiert.

---

## 3. Sprache & Übersetzung

- **S1 — Sprache:** Antworten in korrektem Spieldeutsch.
- **S2 — Korrekte, nicht wörtliche Begriffe:** die **offiziellen** deutschen Begriffe, keine
  Eigenübersetzungen.
- **S3 — Begriffsquellen (Priorität von oben nach unten):**
  1. **Aktuelles offizielles Deutsch 2024** — dt. SRD 5.2.1 und die offiziellen deutschen
     Grundregelwerke 2024 (PHB/DMG/MM), sofern vorhanden; Ulisses-2024-Begriff im Glossar.
  2. Offizielles Deutsch aus **älteren** offiziellen Büchern + Ulisses-Glossar.
  3. **Inoffizielle**/Community-Übersetzung → `*`.
  4. **Keine** offizielle Entsprechung → konsistente, markierte deutsche Wiedergabe mit `*` —
     *nicht* Englisch mitten im Satz (Immersion).

  Stufen 1–2 gelten als offiziell (**kein** `*`); Stufen 3–4 werden mit `*` markiert.
- **S4 — Englisches Original immer in Klammern**, bei jeder Erstnennung: „Gelegenheitsangriff
  (Opportunity Attack)".
- **S5 — `*` bei fehlender offizieller Übersetzung**, einmalig erläutert.
- **S6 — Offiziell vs. inoffiziell muss intern unterscheidbar sein** — Grundlage der `*`-Regel.
- **S7 — Terminologie ist editionsübergreifend (Begriffe ≠ Regeln).** Offizielle deutsche
  **Begriffe** dürfen aus älteren offiziellen deutschen Büchern übernommen werden, auch wenn
  der **Inhalt** aus einem neueren englischen Buch stammt — **ohne** `*` und **ohne**
  „veraltet"-Kennzeichnung. Die deutsche Vokabel ist stabil; die *Regel* dahinter kann sich
  ändern, und das regelt allein §4 am Inhalt.
- **S8 — Konfliktregel:** Der **neuere** offizielle deutsche Begriff hat Vorrang. Hat sich die
  Bedeutung geändert, folgt der Begriff dem **aktuellen** Regelinhalt.
- **S9 — Herkunft mitführen:** Zu jedem Begriff wird intern die Quelle gespeichert (Buch/
  Glossar, Ausgabe). Sichtbar ist davon nur die `*`-Kennzeichnung.
- **S10 — Immersion zuerst: deutscher Regeltext primär.** Wo deutsche Quellen vorliegen, wird
  der deutsche Regeltext direkt verwendet. „Englischer Text + Begriffsannotation" greift nur
  für Inhalte, die es **ausschließlich** auf Englisch gibt. *(Größter Immersions-Hebel; noch
  nicht voll eingelöst — siehe BACKLOG M1.)*
- **S11 — Konsistenz & robuste Begriffserkennung.** Ein Begriff hat **eine** kanonische
  deutsche Fassung. Die Erkennung normalisiert Flexion, Groß-/Kleinschreibung und Komposita,
  damit ein vorhandener offizieller Begriff nicht fälschlich ein `*` kassiert.
- **S12 — Abkürzungen: deutsch schreiben, englisch verstehen.** Wo eine Auskunft abkürzt,
  gilt die **offizielle deutsche** Form (RK, TP, SG, HG, EP, ÜB, W20 …) — nie die
  englische (AC, HP, DC, CR, XP, PB, d20). Eine englische Abkürzung in der **Anfrage**
  muss dagegen verstanden werden und zum deutschen Eintrag führen. Jede empfohlene Form ist
  im deutschen SRD 5.2.1 belegt und wird dagegen getestet — erfunden wird keine (Regel 1).
  Die Regel muss über **alle drei Kanäle** (§7) laufen, und das ist hier keine Redundanz,
  sondern die eigentliche Zusage: Die Projektanweisung richtet jede Person selbst ein — wer
  das nicht tut, bekäme sonst keine. Register und Durchsetzung:
  [CONCEPT.md](CONCEPT.md) §5.
- **S13 — Register: Nachschlagewerk, nicht Assistent.** Antworten klingen wie ein Regelbuch:
  sachlich, knapp, unpersönlich — kein Assistenten-Ich („Ich habe gefunden …"), keine
  Floskeln, keine eigenen Bewertungen („mächtig", „beliebt"). Die 2. Person („du") steht nur
  dort, wo der Regeltext sie selbst benutzt; den Nutzer adressiert Foliant nur im
  Abschluss-Slot des Antwortgerüsts (B12).
- **S14 — Phrasenkatalog: wiederkehrende Sätze haben EINE Formulierung.** Aussagen, die in
  vielen Antworten vorkommen, stehen wörtlich fest — das schafft Wiedererkennung und macht
  sie ohne Richter-Modell testbar:

  | Situation | Feste Phrase |
  |---|---|
  | Nicht im Bestand | „❌ Dazu finde ich nichts im Foliant-Bestand." |
  | `*`-Fußnote | „\* keine offizielle deutsche Übersetzung" |
  | Altstand-Warnung | „⚠️ Nur 2014-Fassung im Bestand — ggf. an 2024 anzupassen." |
  | Mehrdeutigkeit, Abschluss | „Welchen meinst du?" |
  | Angebot nach einer Auskunft | „Sag Bescheid, wenn du <X> im vollen Wortlaut brauchst." |
  | Web-Kennzeichnung | „🌐 Aus dem Web (NICHT aus dem Foliant-Bestand, ungeprüft):" |
  | Regellücke | „⚖️ Regelt der Text nicht eindeutig — SL entscheidet." |
- **S15 — Wiedergabetreue: Wortlaut ist Regelwirkung.** Regeltext wird wortgetreu
  wiedergegeben bzw. wortgetreu übersetzt — nie paraphrasiert, vereinfacht oder
  zusammengefasst: Modalwörter („kann"/„muss", „bis zu"/„genau") und alle Zahlen, Würfel,
  Reichweiten und Dauern exakt, in deutscher Notation (S12). Ein selbstübersetzter
  `*`-Begriff behält innerhalb eines Gesprächs dieselbe deutsche Wiedergabe (verlängert
  S11). Zusammengefasst wird nur, wo das Antwortgerüst es vorsieht (B12, breite Fragen) —
  nie innerhalb eines wiedergegebenen Merkmals, Zaubers oder Statblocks.

> **Beispiel:** Inhalt aus „Ravenloft: Horrors Within" (EN, nicht übersetzt) → der Regeltext
> bleibt englisch mit seiner Regelversion. Die deutschen Begriffe kommen aus „Van Richtens
> Ratgeber zu Ravenloft" (DE) und gelten als offiziell (kein `*`). Nur Begriffe, für die es
> **nirgends** offizielles Deutsch gibt, bekommen `*`.

---

## 4. Regelversionierung (sehr wichtig)

- **V1 — Version bei der Ablage:** Jeder Eintrag trägt **zwingend** seine Regelversion —
  Pflicht 2024 („5.5e") vs. 2014 („5e"); Quellbuch wo bekannt; Errata-Stand optional
  (seit 31.07.2026 als `quellen.versions_stand` ablegbar, siehe V9).
- **V2 — Aktuell als Standard:** Auskünfte beziehen sich standardmäßig auf 2024.
- **V3 — Version in der Antwort:** zusätzlich zu Quelle und ggf. Seite.
- **V4 — Ältere Stände markieren**, mit Hinweis, dass eine Anpassung nötig sein kann.
- **V5 — Keine stille Vermischung** von altem und aktuellem Stand.
- **V6 — Terminologie ausgenommen:** V1–V5 betreffen **Regelinhalte**. Aus Altbüchern
  übernommene **Begriffe** (S7) sind kein „älterer Regelstand".
- **V7 — Erweiterbares Versionsschema:** strukturiertes Feld, damit feinere Granularität
  (Quellbuch, Errata, Druckauflage) **ohne Migration** ergänzbar bleibt.
- **V8 — Altregeln bewusst nutzbar:** Ältere Inhalte dürfen aufgenommen und durchsucht werden
  — gerade Regeln ohne 2024-Entsprechung. Bei Ausgabe **immer** deutlicher Hinweis (V4).
- **V9 — Offizielle Nachträge stehen NEBEN dem Grundtext, nie darin.** Errata und
  offizielle Regelauslegungen (Sage Advice) werden als **eigene Quellen** geführt, nicht in
  den Buchtext eingerechnet: Ein eingerechneter Text wäre nicht mehr der Buchtext, und
  niemand könnte mehr sagen, was im Buch steht und was korrigiert wurde. Die Ausgabe
  unterscheidet deshalb drei Dinge: **Regeltext**, **offizielle Errata** (📌, die Korrektur
  gilt) und **offizielle Regelauslegung** (⚖️, kein Regelwortlaut).
  Umsetzung: [CONCEPT.md](CONCEPT.md) §3.
- **V10 — Quellen-Provenienz:** Eine Quelle muss festhalten können, WELCHE Fassung im
  Bestand steckt und woher sie kam — Errata-/Druckstand, Herkunfts-URL, Prüfsumme der
  Quelldatei, Importzeitpunkt. Alle Angaben sind **optional**: eine Quelle ohne sie bleibt
  gültig. Geraten wird nichts (Regel 1). Felder und Migrationsweg:
  [CONCEPT.md](CONCEPT.md) §3.

**Verbindlich:** Editionen werden **NIE geraten.** Beim DDB-Import autoritativ aus der
Buch-Datenbank, bei PDFs pro Buch explizit gesetzt. Unklar = **nicht importieren**.

---

## 5. Nicht-funktionale Anforderungen

- **NF1 — Self-hosted:** eigene Hardware, eigene Kontrolle.
- **NF2 — Zugang über Claude:** Custom Connector; der Free-Plan (genau ein Connector) genügt.
- **NF3 — Privat:** ausschließlich für die eigene Runde; keine öffentliche Bereitstellung.
- **NF4 — Legale Quellen:** frei lizenziertes SRD (CC-BY-4.0) und eigene, legal erworbene
  Inhalte. DDB-Extraktion nur privat (ToS-Grauzone, bewusst akzeptiert).
- **NF5 — Kosten:** keine laufenden Kosten außer Strom. *(Ausnahme seit §14: der
  Charakterbogen-Übersetzer verbraucht pro Konvertierung Anthropic-API-Guthaben; harter
  Kostendeckel per Spend-Limit im eigenen Workspace.)*
- **NF6 — Nur so komplex wie nötig.**
- **NF7 — Erweiterbar:** spätere Ausbaustufen müssen ohne Neuaufbau andocken.
- **NF8 — Einfache Ersteinrichtung:** URL als Connector eintragen, im Chat aktivieren.

---

## 6. Qualität & Integrität

- **Q1 — Suche: aktuell zuerst.** Existiert eine 2024-Fassung, ist sie die primäre Antwort;
  ältere Fassungen nur als klar gekennzeichneter Zusatz oder auf ausdrücklichen Wunsch.
- **Q2 — Dubletten & Quellen-Präzedenz.** Kommt derselbe Inhalt in gleicher Version aus
  mehreren Quellen, bestimmt eine festgelegte Präzedenz die kanonische Quelle.
- **Q3 — Pflicht-Version, keine verwaisten Inhalte.** Kein Inhalt ohne gesetzte Regelversion
  und Quellenangabe. Fehlt sie, wird **nicht importiert**.
- **Q4 — Build-Prüfung: streng, transparent, ehrlich über Lücken.** Validiert ausschließlich
  gegen 2024, mischt keine Altregeln ein, **nennt ihre Datenbasis** und weist offen aus, was
  sie nicht prüfen kann. Sie ist **Hilfe, nicht letzte Instanz**.
- **Q5 — Begriffskonflikte kontrolliert auflösen:** neuerer offizieller Begriff gewinnt (S8),
  Konflikt wird intern protokolliert (S9).
- **Q6 — Recht & Attribution.** CC-BY-Pflichtattribution (SRD) wird mitgeführt; DDB-Inhalte
  bleiben strikt privat.
- **Q7 — Nachschlagen ohne externe Abhängigkeit.** DDB- und Open5e-Quellen werden **einmalig
  importiert**, nie zur Laufzeit abgefragt; das Regel-Nachschlagen funktioniert vollständig
  **offline**. *(Gilt für den MCP-Server. Zur Abgrenzung beim Charakterbogen siehe §14.)*

---

## 7. Verhalten aus Spielersicht

- **B1 — Geerdete Antworten, kein Halluzinieren.** Auskünfte stützen sich **ausschließlich**
  auf den importierten Bestand. Findet Foliant nichts, wird das **klar gesagt**, statt aus
  Allgemeinwissen zu antworten. *Wichtigste Maßnahme überhaupt* — das Modell bringt viel
  D&D-Wissen (inkl. 2014 und Homebrew) mit und füllt Lücken sonst selbst.
- **B2 — Lücken ehrlich benennen**, statt sie stillschweigend zu übergehen oder zu ersetzen.
- **B3 — Suche zweisprachig & tolerant:** deutsche und englische Begriffe, gängige Abkürzungen
  und kleine Schreibvarianten. „opportunity attack", „Gelegenheitsangriff" und „AoO" landen
  beim selben Eintrag.
- **B4 — Mehrdeutigkeit auflösen statt raten:** Kandidaten mit Unterscheidungsmerkmal (Typ,
  Quelle, Version) zurückgeben.
- **B5 — Alten Regelstand verständlich einordnen:** „Keine 2024-Fassung im Bestand; hier der
  2014-Stand — ggf. anzupassen."
- **B6 — Außerhalb des Umfangs klar ablehnen.** Fragen zu Abenteuer-/Kampagneninhalten („Wie
  besiege ich Strahd?") werden **nicht** aus allgemeinem Wissen beantwortet.
- **B7 — Charakterbau in 2024-Reihenfolge führen:** Klasse → Hintergrund → Spezies → Details,
  Schritt für Schritt statt alles auf einmal. **Die Herkunft umfasst auch zwei Sprachen und
  Spezies-Pflichtwahlen** — nicht überspringen.
- **B8 — Erwartungen setzen:** Foliant **speichert den Charakter nicht** und kennt **keine
  Hausregeln**; Auskünfte sind **RAW**.
- **B9 — Schnell & verfügbar im Spielbetrieb.**
- **B10 — Einrichtung spielerfest:** klare Kurzanleitung plus Fallback-Hinweis (Custom
  Connectors sind Beta).
- **B11 — Nachträge kenntlich machen (V9).** Stammt ein Treffer aus einer Errata-Quelle,
  gehören **Grundtext und Korrektur zusammen** in die Antwort, mit der Aussage, dass die
  Korrektur gilt (📌) — eine Korrektur zu verschweigen ist so falsch wie sie als eigene
  Regel auszugeben. Eine offizielle Regelauslegung (⚖️) wird **als Auslegung**
  gekennzeichnet und nie als Regelwortlaut zitiert.
- **B12 — Das Antwortgerüst: eine Form für jede Antwort.** Jede Antwort — jede Kategorie,
  jeder Sonderfall — füllt dieselben fünf Slots in fester Reihenfolge; Slots dürfen
  entfallen, aber nie wandern, und außerhalb der Slots steht nichts:
  1. **Kopfzeile** — genau eine Zeile: EIN Emoji aus dem geschlossenen Katalog der
     Projektanweisung (§8; Kategorie- oder Status-Emoji) + fetter Name/Thema,
     Deutsch-first (S3–S5).
  2. **Warnung** — nur wenn nötig: die ⚠️-Zeile (B5, S14) — die einzige zulässige Aussage
     über den Bestand, weil sie eine Spielentscheidung beeinflusst.
  3. **Einordnung** — ein Halbsatz mit den Angaben, die die Kategorie definieren (Zauber:
     Grad, Schule, Klassen · Monster: Größe, Typ, HG · Unterklasse: Basisklasse · …); bei
     Ja/Nein- und Situationsfragen ist das die direkte Antwort (Ja/Nein/Bedingung).
  4. **Kern** — der Inhalt nach kategoriefestem Muster (Zauber: Steckbrief-Feldzeilen und
     Wirkungstext · Monster: vollständiger Statblock · Klassen: Merkmale nach Stufen ·
     Regel: Regeltext, dann Ausnahmen); nur Regelinhalt (B13/B14), wortgetreu (S15),
     Ableitungen und Regellücken gekennzeichnet (S14).
  5. **Abschluss** — höchstens ein Angebot (B16), dann die `*`-Fußnote (S5/S14), dann als
     letzte Zeile der Beleg: „📖 " + Quelle · Seite (wann immer die Quelle eine hat) ·
     Regelversion (F7, V3) — nur unter wiedergegebenem Regeltext, eine 📖-Zeile je
     tragender Quelle.

  Auch ❌ (nicht im Bestand), 🚫 (Spoiler/Umfang), ❓ (Mehrdeutigkeit, B4), breite
  Listenfragen, Ableitungen aus mehreren Regeln und 🌐 (Web-Fallback) sind Instanzen
  desselben Gerüsts — mit Status-Emoji in der Kopfzeile und entfallenden Slots. **Auch
  Gesprächszüge, die keine Auskunft sind** — Rückfragen (❓) und die Schritte der
  Charaktererstellung (B7) — tragen das Gerüst; „jede Antwort" kennt keine Ausnahme,
  sonst wäre die Regel nicht prüfbar.
- **B13 — Meta-Verbot: die Antwort handelt vom Spiel, nie vom Nachschlagewerk.** Keine
  Aussagen über die Sprache der Quelle, den Suchvorgang, Werkzeuge oder die Eintrags- und
  Bestandsstruktur — die Sprachherkunft zeigt allein die `*`-Fußnote; einzige Ausnahme ist
  die ⚠️-Warnung (B12).
- **B14 — Nur Regeltext; Flavor höchstens ein Satz.** Wiedergegeben wird, was Regelwirkung
  hat; beschreibender Flavor nur, wo er das Verständnis stützt, und nie mehr als ein Satz.
  Layout-Artefakte der Quelle (Werbe-Taglines, Illustratoren-Credits, Kapitel-Marketing)
  werden nie wiedergegeben — auch nicht übersetzt.
- **B15 — Fragmente unsichtbar zusammensetzen.** Ist ein Inhalt über mehrere Einträge
  verteilt (z. B. eine Unterklasse und ihre Stufen-Merkmale), holt Foliant die Teile selbst
  und liefert EIN zusammenhängendes Ergebnis — er erklärt die Struktur nicht und bietet
  keine Teile an, bevor die Kernauskunft steht.
- **B16 — Höchstens ein Angebot am Schluss.** Nach vollständiger Auskunft darf genau ein
  weiterführendes Angebot stehen (Phrase: S14) — keine Aufzählung dessen, was Foliant noch
  könnte.

### Die vier nicht verhandelbaren Kernregeln
1. **Geerdet, keine Halluzination** (B1/B2)
2. **Version immer** (V1–V5, `edition` ist NOT NULL)
3. **Deutsch-first** (S1–S11)
4. **Keine Spoiler, kein Scope-Creep** (B6, §1) — **Spoiler-Schutz ist die oberste
   Verhaltensregel.**

### Durchsetzung über drei Kanäle
Modellverhalten ist steuerbar, aber nicht beweisbar erzwingbar. Deshalb dieselben Regeln
dreifach:

| Kanal | Wer | Wirkung |
|---|---|---|
| 1. **Grounding-Hinweise in den Tool-AUSGABEN** | Server | **zuverlässigster Kanal** — die Hinweise stehen bei jeder Antwort im Kontext |
| 2. Server-Instruktionen (`config/stil.py`) + Tool-Beschreibungen | Server | Grundverhalten je Verbindung |
| 3. **Projektanweisung im Claude-Projekt** (§8) | Betreiber | System-Prompt-Ebene: stärkster Hebel für Priorität, Format, Spoiler |

Der **Websuche-Schalter** (Betreiber, Claude-Einstellungen) zählt bewusst nicht als vierter
Kanal: Er steuert kein Verhalten, sondern ist der einzige **harte** Garant gegen
Web-Vermischung. Wer „drei Kanäle" liest, meint immer die drei oben.

---

## 8. Projektanweisung (Copy-Paste ins Claude-Projekt)

**Der Text steht in [`config/projektanweisung.md`](config/projektanweisung.md)** — eine eigene
Datei, damit er ohne Eingriff in dieses Dokument bearbeitbar bleibt. Er liegt bewusst neben
`config/stil.py`: das sind die zwei Kanäle **desselben** Regelwerks, und sie müssen synchron
bleiben (`tests/test_verhaltensregeln.py` erzwingt das für die tragenden Regeln).

Einmalig einrichten: **Projekte → Neues Projekt** („D&D Runde") → **Projektanweisungen** →
Inhalt der Datei komplett einfügen → dort die D&D-Chats führen (Foliant-Connector aktiv).
Optional der harte Schalter: Websuche in den Claude-Einstellungen deaktivieren.

**Für die Runde:** Mitspieler holen den Text nicht aus dem Repository, sondern kopierbereit
auf der Charakterbogen-Website (Abschnitt „Foliant im Claude-Chat", hinter dem Kennwort). Die
Seite liest die Datei zur Laufzeit — eine Änderung erreicht nach dem `web`-Neustart alle
Spieler, ohne dass jemand eine Kopie pflegt. Für den Betreiber legt
`deploy/projektanweisung.sh` den aktuellen Stand direkt in die Zwischenablage.

Warum der Text hier nicht mehr steht: Jede neue Verhaltensregel landet in dieser Datei, und
als eingebetteter Codeblock war jede Änderung ein Eingriff in ein Doku-Dokument — inklusive
der Gefahr, die Markdown-Fences zu zerreißen, an denen die Website und die Tests hingen.

---

## 9. Betrieb & Pflege

- **O1 — Backup & Wiederherstellung.** Der Bestand wird regelmäßig gesichert;
  Wiederherstellung **ohne erneuten Import** möglich.
- **O2 — Inhalte aktuell halten.** Errata, neue Bücher, aktualisiertes Glossar sind
  nachträglich importierbar, ohne Neuaufbau; dieselbe Pflicht-Versionierung (Q3) und
  Qualitätsprüfung (O3) greifen.
- **O3 — Import-Qualitätsprüfung vor Freigabe.** Neu importierter Inhalt wird
  stichprobenartig geprüft (korrekte Zahlen, Leserichtung, keine zerrissenen Statblöcke).
- **O4 — Feedback-/Korrekturschleife.** Schlechte Treffer und falsche Auskünfte werden
  gesammelt und nachgezogen. Zwei Meldewege, weil sie verschiedene Fehler finden:
  **gemessen** — das Abfrage-Protokoll loggt jede Nachschlage-Anfrage, `admin suchbericht`
  macht daraus Kuratier-Kandidaten (Nulltreffer, Fuzzy-Landungen, Mehrdeutigkeiten,
  Übersetzungs-Lücken); und **gemeldet** — die Runde markiert eine Antwort direkt im
  Client, ohne Umweg über den Betreiber. Der zweite Weg ist kein Komfort: Eine Auskunft,
  die technisch gefunden hat und inhaltlich daneben lag, erzeugt **kein** Messsignal — sie
  fällt nur einem Menschen auf. Der Meldeweg trägt **beide Vorzeichen**: eine als falsch
  markierte Antwort wird kuriert, eine als besonders gut markierte wird gegen künftige
  Änderungen abgesichert. Lob ist dabei kein Beiwerk, sondern die einzige Quelle für die
  Frage, was schon stimmt und deshalb nicht kaputtgehen darf — Regressionsschutz braucht
  ein Urteil, und ein Messwert liefert keines. *(Umsetzung: [CONCEPT.md](CONCEPT.md) §9.
  Regelmäßiges Sichten: BACKLOG M5.)*
- **O5 — Secrets sicher halten.** Zugangsdaten (v. a. der DDB-Cobalt-Cookie) nur
  server-seitig, erneuerbar. Ohne gültigen Cookie schlägt nur der DDB-*Import* fehl, nicht
  der laufende Betrieb.

---

## 10. Abnahme- & Testkriterien

„Fertig" heißt: alle zwölf Tests erfüllt. Aktueller Stand und die durchzuführende
Chat-Checkliste stehen in [BACKLOG.md](BACKLOG.md) §2.

| Test | Prüft | Kriterium |
|---|---|---|
| **T1** | F7/P4 | Vorhandene Regelfrage → Antwort mit **Quelle und Regelversion** (Seite, wenn die Quelle eine hat) |
| **T2** | B1/B2 | Frage nach etwas **nicht** im Bestand → ehrliches „nicht gefunden", keine erfundene Antwort |
| **T3** | S4/S5 | Begriff ohne offizielle Übersetzung erscheint **mit `*`** + Original in Klammern; offizieller Begriff **ohne** `*` |
| **T4** | S3/S7 | Offizieller deutscher Begriff aus einem Altbuch wird verwendet und **nicht** mit `*` markiert |
| **T5** | V2/V4/B5 | Nur 2014-Regel vorhanden → **klar als alter Stand** ausgegeben |
| **T6** | Q1 | 2024- *und* 2014-Treffer → **2024 primär**, 2014 nur als markierter Zusatz |
| **T7** | B3 | „opportunity attack", „Gelegenheitsangriff", „AoO" → **selber Eintrag** |
| **T8** | B4 | Mehrdeutiger Begriff („Schild") → **Kandidaten mit Unterscheidungsmerkmal** |
| **T9** | F3/Q4 | **Illegaler Build** wird erkannt und begründet; Ungeprüftes offen benannt |
| **T10** | B6 | „Wie besiege ich Strahd?" → **außerhalb des Umfangs**, nicht aus Allgemeinwissen |
| **T11** | Q3 | Import **ohne gesetzte Regelversion** wird abgelehnt |
| **T12** | B7 | Charakterbau in **2024-Reihenfolge** geführt |

**T2 ist der wichtigste Dauertest.** T2, T10 und T12 sind **Verhaltenstests** — sie lassen
sich nicht in pytest beweisen und laufen als Checkliste im Chat **oder** werkzeuggestützt
über das Eval-Harness (`python -m evals.verhaltens_eval`, [CONCEPT.md](CONCEPT.md) §11);
das Ergebnis zählt gleich, festgehalten wird es in [BACKLOG.md](BACKLOG.md) §2.

---

## 11. Spätere Ausbaustufen (vorgemerkt, nicht jetzt)

- **A1 — DDB-Charakter-Abruf:** bestehende Charaktere/Gruppe aus D&D Beyond laden.
- **A2 — Kampagnenspezifik:** Inhalte und Kontext je Kampagne.
- **A3 — Rollen SL/Spieler + Spoiler-Schutz:** getrennte Zugänge, separater Abenteuer-Bereich,
  der über einen Spieler-Zugang technisch nie geöffnet wird.
- **A4 — Hausregeln:** eigene Tischregeln, die die RAW-Antwort sichtbar überlagern.

Alle docken laut Datenmodell ohne Neuaufbau an (NF7). Details: [BACKLOG.md](BACKLOG.md) §4.

---

## 12. Aufgelöste Widersprüche (Rev. 9)

Beim Zusammenführen der bis dahin 18 Dokumente traten fünf echte Konflikte zutage (Nr. 1–5).
So sind sie entschieden — Nr. 6 ist ein späterer Nachtrag:

1. **NF3 „privat, keine öffentliche Bereitstellung" vs. Bereitstellung an die Runde.**
   NF3 ist zu lesen als **„nicht öffentlich"**, nicht als „nur für eine Person". Die
   DDB-Bücher werden per `ins_hauptbestand = true` in den bedienten Bestand gemergt und der
   Runde über den zugangsgeschützten Endpoint bereitgestellt — **bewusste, protokollierte
   Eigentümer-Entscheidung (11.07.2026)**, abgesichert durch Geheimpfad + IP-Allowlist. Die
   Weitergabe von URL und Inhalten über die Runde hinaus bleibt untersagt.

2. **Frühere Annahme „DDB-Extraktion über die MrPrimate-Toolchain" — überholt.** Der
   `ddb-proxy` kann **keine Buchinhalte** liefern, F5 wäre damit unerfüllbar. Umgesetzt ist
   ein **eigener kurzlebiger Exporter**. Der Proxy-Weg ist ausdrücklich verworfen und wird
   nicht wieder geöffnet — Belege und Rückfallebene: [CONCEPT.md](CONCEPT.md) §10 (ADR).

3. **Q7/F5b „kein Laufzeit-API-Aufruf" vs. dem Charakterbogen-Übersetzer.** Q7 gilt
   unverändert für den **MCP-Server**: Regel-Nachschlagen ist vollständig offline. Der
   Charakterbogen-Übersetzer (§14) ist ein **separater Dienst** und ruft bewusst zur Laufzeit
   zwei externe Dienste: die Anthropic-API (Übersetzung) und dnddeutsch.de (Glossar-
   Nachschlagen bei unbelegten Begriffen). Beide sind auf diesen Dienst begrenzt; fällt einer
   aus, bleibt der MCP unberührt.

4. **§1-Nicht-Ziel „kein DDB-Charakter-Abruf" vs. dem Charakterbogen-Übersetzer.** Kein
   Widerspruch: A1 meint das **Laden von Charakteren aus DDB** über dessen API. Der
   Übersetzer verarbeitet ein **vom Nutzer selbst hochgeladenes PDF**; es besteht keine
   Verbindung zu DDB. B8 bleibt gewahrt — nichts wird gespeichert.

5. **B7 „vier Schritte" vs. dem SRD, das fünf nennt.** Die Vier-Schritt-Reihenfolge bleibt
   verbindlich (Klasse → Hintergrund → Spezies → Details); die im SRD zusätzlich genannten
   Pflichtwahlen (zwei Sprachen, Spezies-Optionen) sind **in Schritt „Details" enthalten und
   dürfen nicht übersprungen werden** — so ergänzt in B7 und in der Projektanweisung.

6. **NF3 vs. Discord-Bot (Nachtrag 26.07.2026).** Der Bot (`app/discord_bot/`) stellt den
   **Vollbestand inkl. der privaten DDB-Bücher** in Discord bereit — ausschließlich in
   **einer** allowlisteten Guild (`DISCORD_GUILD_ID`; fremde Server werden automatisch
   verlassen). Das ist „nicht öffentlich" im Sinne von Nr. 1: derselbe Personenkreis wie
   beim MCP-Endpoint, nur ein anderer Client. **Bewusste, protokollierte
   Eigentümer-Entscheidung (26.07.2026)** — im Wissen, dass Discord-Nachrichten
   **persistent** im Server-Verlauf stehen und für jeden späteren Mitglied des Servers
   lesbar bleiben. Die Weitergabe von Inhalten über die Runde hinaus bleibt untersagt;
   der Spoiler-Schutz bleibt prompt-basiert (A3-Rollen-Isolation ist vorgemerkt, §11).

---

## 13. Belege (externe Fakten, die den Umfang geprägt haben)

- Das offizielle **deutsche SRD 5.2.1** liegt nur als **PDF** vor → begründet F4.
- **SRD 5.2.1** ist CC-BY-4.0 und deckt nur eine Teilmenge des 2024er-PHB ab (je eine
  Unterklasse, vier Hintergründe, kein Aasimar/Artificer) → begründet F5.
- **DDB-Bücher** sind kein Download; Extraktion nur über inoffizielle Wege → prägt F5.
- **Claude Custom Connectors:** Beta, Free-Plan = genau ein Connector → prägt NF2/B10.
- **D&D 2024** wird auf D&D Beyond als „5.5e" geführt, 2014 als „5e"; beide bleiben
  unterstützt → prägt P1/§4.
- **Offizielles Deutsch 2024 ist verfügbar:** dt. Spielerhandbuch (Mai 2025),
  Spielleiterhandbuch (Juni 2025), Monsterhandbuch (Sept. 2025); das dt. PHB enthält ein
  Regelglossar mit den neuen 2024-Begriffen (Ausströmung/Emanation, Waffenmeisterschaft,
  Gepackt/Grappled) → prägt S3/S10.
- **Open5e** (`api.open5e.com`, v2): CC/OGL-Aggregation mit partieller 2024-Abdeckung neben
  srd-2014; englisch, **keine Seitenzahlen** → prägt F5b/F7.
- **Begriffs-Beispiel:** „Van Richtens Ratgeber zu Ravenloft" (DE, 2014-Basis) liefert
  offizielle deutsche Begriffe, die auch für unübersetztes neueres Material gelten → prägt
  S3/S7.

---

## 14. Charakterbogen-Übersetzer (Zusatz-Feature)

Neben dem MCP-Server läuft ein zweiter Dienst: Ein englischer D&D-Beyond-PDF-Export wird
ausgelesen, übersetzt und auf den **offiziellen deutschen WotC-Charakterbogen (2024)**
übertragen — als druckbares PDF.

**Verbindliche Regeln:**
- **C1 — S1–S12 gelten unverändert.** Ausgabe immer `Deutscher Begriff (English Original)`, `*` nur
  bei fehlendem exaktem, belegtem Glossartreffer. Nie nur Englisch.
- **C2 — Zahlen laufen nie durch das Sprachmodell.** Würfel, Modifikatoren, Rettungswürfe,
  Preise und Gewichte werden deterministisch übertragen.
- **C3 — Listen laufen nie durch das Sprachmodell.** Waffen-, Werkzeug- und Sprachlisten
  werden item-weise über das Glossar aufgelöst; Unbelegtes bleibt englisch.
- **C4 — Amtliche Begriffe schlagen Modellübersetzungen.** Was der eigene Bestand oder das
  Glossar belegt, wird erzwungen — auch mitten im Fließtext.
- **C5 — Keine Persistenz.** Das hochgeladene PDF wird nur im Arbeitsspeicher verarbeitet,
  das Ergebnis nicht abgelegt (B8).
- **C6 — Strukturtreue vor Kompaktheit.** Die Gliederung des DDB-Originals bleibt erhalten,
  auch wenn der Bogen dadurch eine Seite länger wird. Text läuft **nie** stumm über eine
  Boxgrenze.
- **C7 — Zugangsschutz ist Pflicht (fail-closed).** Jede Konvertierung kostet Geld; ohne
  gesetztes Kennwort ist die Seite zu, nicht offen.

Umsetzung: [CONCEPT.md](CONCEPT.md) §7.
