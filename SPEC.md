# Foliant — Spezifikation (das verbindliche „Was")

**D&D-5e-Regelassistent (Fassung 2024), Deutsch-first · self-hosted MCP-Server**
**Rev. 9 · Stand: 25.07.2026** *(Rev. 1–8: Anforderungskatalog; Rev. 9: Konsolidierung,
Widersprüche aufgelöst, Charakterbogen-Übersetzer aufgenommen)*

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
| **Charakterbogen-Übersetzer** (eigene Website, §17) | |

### Leitprinzipien (übergreifend)
- **P1 — Aktuelle Regeln zuerst:** Standard ist D&D 2024 („5.5e"). Ältere Stände werden nie
  stillschweigend beigemischt.
- **P2 — Version immer sichtbar:** Jede gespeicherte Regel trägt ihre Regelversion; jede
  Auskunft nennt sie (§3).
- **P3 — Deutsch-first, offiziell:** offizielle deutsche Begriffe, nicht wörtlich übersetzt;
  englisches Original **immer** in Klammern; fehlt offizielles Deutsch → `*` (§2).
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

## 3. Sprache & Übersetzung (§5-Regeln)

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

> **Beispiel:** Inhalt aus „Ravenloft: Horrors Within" (EN, nicht übersetzt) → der Regeltext
> bleibt englisch mit seiner Regelversion. Die deutschen Begriffe kommen aus „Van Richtens
> Ratgeber zu Ravenloft" (DE) und gelten als offiziell (kein `*`). Nur Begriffe, für die es
> **nirgends** offizielles Deutsch gibt, bekommen `*`.

---

## 4. Regelversionierung (sehr wichtig)

- **V1 — Version bei der Ablage:** Jeder Eintrag trägt **zwingend** seine Regelversion —
  Pflicht 2024 („5.5e") vs. 2014 („5e"); Quellbuch wo bekannt; Errata-Stand optional.
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

**Verbindlich:** Editionen werden **NIE geraten.** Beim DDB-Import autoritativ aus der
Buch-Datenbank, bei PDFs pro Buch explizit gesetzt. Unklar = **nicht importieren**.

---

## 5. Nicht-funktionale Anforderungen

- **NF1 — Self-hosted:** eigene Hardware, eigene Kontrolle.
- **NF2 — Zugang über Claude:** Custom Connector; der Free-Plan (genau ein Connector) genügt.
- **NF3 — Privat:** ausschließlich für die eigene Runde; keine öffentliche Bereitstellung.
- **NF4 — Legale Quellen:** frei lizenziertes SRD (CC-BY-4.0) und eigene, legal erworbene
  Inhalte. DDB-Extraktion nur privat (ToS-Grauzone, bewusst akzeptiert).
- **NF5 — Kosten:** keine laufenden Kosten außer Strom. *(Ausnahme seit §17: der
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
  **offline**. *(Gilt für den MCP-Server. Zur Abgrenzung beim Charakterbogen siehe §17.)*

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
| **Grounding-Hinweise in den Tool-AUSGABEN** | Server | **zuverlässigster Kanal** — die Hinweise stehen bei jeder Antwort im Kontext |
| Server-Instruktionen (`config/stil.py`) + Tool-Beschreibungen | Server | Grundverhalten je Verbindung |
| **Projektanweisung im Claude-Projekt** (§8) | Betreiber | System-Prompt-Ebene: stärkster Hebel für Priorität, Format, Spoiler |
| Websuche-Schalter aus | Betreiber | der einzige **harte** Garant gegen Web-Vermischung |

---

## 8. Projektanweisung (Copy-Paste ins Claude-Projekt)

Einmalig einrichten: **Projekte → Neues Projekt** („D&D Runde") → **Projektanweisungen** →
Block unten komplett einfügen → dort die D&D-Chats führen (Foliant-Connector aktiv).
Optional der harte Schalter: Websuche in den Claude-Einstellungen deaktivieren.

> **Bei Änderungen `config/stil.py` synchron halten** — die beiden sind bewusst Duplikate
> desselben Regelwerks auf zwei Kanälen.

```
Du hilfst unserer D&D-Runde (D&D 5e, Regelfassung 2024, Deutsch-first). Es gilt strikt:

OBERSTE REGEL — KEINE SPOILER:
Gib niemals Handlung, Geheimnisse, Wendungen oder Taktiken zu Abenteuern/Kampagnen
preis („Wie besiege ich X?", „Was passiert in Kapitel Y?") — weder aus Foliant, noch
aus deinem Wissen, noch aus dem Web. Lehne mit 🚫 ab und biete stattdessen die reine
REGEL-Auskunft an (z. B. allgemeine Kreaturenwerte, falls im Bestand). Beim Ablehnen
NENNE nur, was du nachschlagen könntest — nimm nichts davon vorweg. Auch beiläufige
Beispiele sind Spoiler: wer auf „Wie besiege ich X?" die Schwächen der Kreaturenart
aufzählt, hat die Frage beantwortet statt sie abzulehnen.

WISSENSQUELLEN — strikte Prioritätsleiter:
1. FOLIANT (MCP-Werkzeuge) ist die EINZIGE Quelle für Regelauskünfte. Rufe für jede
   D&D-Frage zuerst die foliant_*-Werkzeuge auf — auch wenn du die Antwort zu kennen
   glaubst. Dein Trainingswissen ist keine Quelle und wird nicht untergemischt.
2. Liefert Foliant nichts: sage das klar mit ❌ („Dazu finde ich nichts im
   Foliant-Bestand — eventuell fehlt ein Buch."). Fülle die Lücke NICHT aus
   Allgemeinwissen, 2014-Erinnerungen oder Homebrew.
3. NUR wenn ich es möchte, darfst du danach im Web suchen — Ergebnis strikt getrennt
   und gekennzeichnet: „🌐 Aus dem Web (NICHT aus dem Foliant-Bestand, ungeprüft):".
   Web- und Foliant-Inhalte nie vermischen. Spoiler-Regel gilt auch im Web.

WERKZEUG-AUSGABEN RICHTIG LESEN:
- Ein Feld "fehler" bedeutet: die ANFRAGE war ungültig, NICHT "nichts im Bestand".
  Korrigiere sie und frage erneut. Nur eine gültige Anfrage ohne Treffer rechtfertigt ❌.
- Bevor du ❌ sagst: Hast du nur ein hol_*-Werkzeug probiert, prüfe mit
  foliant_suche_bestand gegen. Die Suche versteht Deutsch UND Englisch sowie
  Abkürzungen (AoO, RK, TP).
- Mehrdeutigkeit ("Schild" = Zauber ODER Rüstung): Kandidaten mit Unterscheidungs-
  merkmal nennen und rückfragen - nie raten.
- "hinweis_gekuerzt" heißt, es gibt mehr Treffer als gezeigte - sag das dazu.
- "fremdsprachige_fassungen"/"konflikt_quellen" heißt: es gibt eine ABWEICHENDE Fassung
  (andere Sprache/Quelle). Lade sie per eintrag_id nach und lege den Unterschied offen
  (⚖️) - nie stillschweigend nur die Vorrangfassung ausgeben.
- Statblöcke/Steckbriefe VOLLSTÄNDIG wiedergeben: keine Abschnitts-Überschrift des
  Bestandstexts weglassen (Merkmale, Aktionen, Bonusaktionen, Reaktionen, Legendäre
  Aktionen). Kompakt heißt knapp formuliert, nicht gekürzt.
- "inhaltsart: abenteuer_setting" markiert einen Kampagnen-Band: Regelwerte ja,
  Handlung/Orte/Personen/Geheimnisse nein.

EINHEITLICHE DARSTELLUNG (immer dieses Schema):
- Kopfzeile: Kategorie-Emoji + fetter Name mit englischem Original in Klammern.
  📜 Regel · 🪄 Zauber · 🐉 Monster · 🎒 Gegenstand · 🧝 Spezies · ⚔️ Klasse ·
  🏕️ Hintergrund · ✨ Talent
- Antwort kompakt in Markdown; Werte als Tabelle.
- Belegzeile am Ende jeder Regelauskunft: „📖 Quelle · S. X · Regelversion 2024"
  (Seite nur, wenn die Quelle eine hat).
- ⚠️ wenn nur eine 2014-Fassung existiert („ggf. an 2024 anzupassen").

SPRACHE & BEGRIFFE (§5) — VERBINDLICH, kein Ermessen:
- Antworte AUSSCHLIESSLICH auf Deutsch — auch kurze Zwischen-/Statushinweise. Niemals
  Englisch oder eine andere Sprache im Fließtext. Kündige Werkzeugaufrufe nicht an und
  kommentiere sie nicht; gehe direkt von der Frage zur formatierten Antwort.
- Offizielle deutsche Begriffe, englisches Original immer in Klammern bei der ersten
  Nennung: „Gelegenheitsangriff (Opportunity Attack)".
- Liefert eine Tool-Ausgabe das Feld `begriffe_deutsch`, sind das die AMTLICHEN
  Übersetzungen der im Regeltext vorkommenden Fachbegriffe — diese verwenden (KEIN *),
  z. B. „Todeswolke (Cloudkill)".
- Ohne offizielle Übersetzung deutsche Wiedergabe mit * markieren (einmal erläutern):
  „Gestalt des Schreckens* (Form of Dread)".
- Lass KEINEN Fachbegriff (Merkmals-/Zaubernamen) unübersetzt englisch stehen und ersetze
  das *-System NICHT durch Prosa wie „ich übertrage sinngemäß".

AUSSAGEARTEN TRENNEN:
- Erst die direkte Antwort (Ja/Nein/Bedingung), dann Kernregel, Ausnahmen, Beleg.
  Englisches Original in Klammern bei der ersten Nennung pro Antwort.
- Eigene Schlussfolgerungen als „Ableitung aus X + Y" kennzeichnen; regelt der Text
  eine Situation nicht eindeutig: offen sagen und mit ⚖️ an die SL verweisen.
- Belegzeilen nur für wiedergegebenen Regeltext, nie unter reinen Ableitungen.

CHARAKTERERSTELLUNG: Schritt für Schritt in der 2024-Reihenfolge
Klasse → Hintergrund → Spezies → Details; Optionen nur aus dem Bestand.
Herkunft umfasst auch ZWEI SPRACHEN und Spezies-Pflichtwahlen (z. B. Abstammung) —
nicht überspringen.
```

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
  gesammelt und nachgezogen. Server-seitig erledigt: das Abfrage-Protokoll loggt jede
  Nachschlage-Anfrage (Suchweg, Trefferzahl, Dauer), `admin suchbericht` macht daraus
  Kuratier-Kandidaten (Nulltreffer, Fuzzy-Landungen, Mehrdeutigkeiten,
  Übersetzungs-Lücken). *(Regelmäßiges Sichten: BACKLOG M5.)*
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

Beim Zusammenführen der bis dahin 18 Dokumente traten fünf echte Konflikte zutage. So sind
sie entschieden:

1. **NF3 „privat, keine öffentliche Bereitstellung" vs. Bereitstellung an die Runde.**
   NF3 ist zu lesen als **„nicht öffentlich"**, nicht als „nur für eine Person". Die
   DDB-Bücher werden per `ins_hauptbestand = true` in den bedienten Bestand gemergt und der
   Runde über den zugangsgeschützten Endpoint bereitgestellt — **bewusste, protokollierte
   Eigentümer-Entscheidung (11.07.2026)**, abgesichert durch Geheimpfad + IP-Allowlist. Die
   Weitergabe von URL und Inhalten über die Runde hinaus bleibt untersagt.

2. **Frühere Annahme „DDB-Extraktion über die MrPrimate-Toolchain" — überholt.** Der
   `ddb-proxy` kann **keine Buchinhalte** liefern (nur Charaktere, Zauber, Items, Monster) —
   F5 wäre damit unerfüllbar. Umgesetzt ist ein **eigener kurzlebiger Exporter** über die
   DDB-Mobile-API mit SQLCipher-Entschlüsselung. Begründung: [CONCEPT.md](CONCEPT.md) §10,
   ADR. Der Proxy-Weg ist ausdrücklich verworfen und wird nicht wieder geöffnet.

3. **Q7/F5b „kein Laufzeit-API-Aufruf" vs. dem Charakterbogen-Übersetzer.** Q7 gilt
   unverändert für den **MCP-Server**: Regel-Nachschlagen ist vollständig offline. Der
   Charakterbogen-Übersetzer (§17) ist ein **separater Dienst** und ruft bewusst zur Laufzeit
   zwei externe Dienste: die Anthropic-API (Übersetzung) und dnddeutsch.de (Glossar-
   Nachschlagen bei unbelegten Begriffen). Beide sind auf diesen Dienst begrenzt; fällt einer
   aus, bleibt der MCP unberührt.

4. **§8-Nicht-Ziel „kein DDB-Charakter-Abruf" vs. dem Charakterbogen-Übersetzer.** Kein
   Widerspruch: A1 meint das **Laden von Charakteren aus DDB** über dessen API. Der
   Übersetzer verarbeitet ein **vom Nutzer selbst hochgeladenes PDF**; es besteht keine
   Verbindung zu DDB. B8 bleibt gewahrt — nichts wird gespeichert.

5. **B7 „vier Schritte" vs. dem SRD, das fünf nennt.** Die Vier-Schritt-Reihenfolge bleibt
   verbindlich (Klasse → Hintergrund → Spezies → Details); die im SRD zusätzlich genannten
   Pflichtwahlen (zwei Sprachen, Spezies-Optionen) sind **in Schritt „Details" enthalten und
   dürfen nicht übersprungen werden** — so ergänzt in B7 und in der Projektanweisung.

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

## 14. Charakterbogen-Übersetzer (Zusatz-Feature, §17)

Neben dem MCP-Server läuft ein zweiter Dienst: Ein englischer D&D-Beyond-PDF-Export wird
ausgelesen, übersetzt und auf den **offiziellen deutschen WotC-Charakterbogen (2024)**
übertragen — als druckbares PDF.

**Verbindliche Regeln:**
- **C1 — §5 gilt unverändert.** Ausgabe immer `Deutscher Begriff (English Original)`, `*` nur
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
