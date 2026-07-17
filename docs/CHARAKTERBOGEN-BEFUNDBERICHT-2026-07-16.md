# Charakterbogen-Übersetzer — Befundbericht E2E-Test (16.07.2026)

> **STATUS: UMGESETZT (16.07.2026, Review-Runde 2).** Alle Punkte P1–P10 sind implementiert
> (Details: `docs/CHARAKTERBOGEN-MVP.md`, Abschnitt „Review-Runde 2"); die offenen Fragen
> wurden mit den Empfehlungen dieses Berichts entschieden. Zusätzlich gefunden und behoben:
> `fitz.get_text_length` misst Nicht-ASCII zu schmal (jetzt `Font.text_length`), Textebene
> verklebte bei wortweisem Setzen (jetzt Läufe je Font), DDB-Bullet U+2022 im Zeichen-Sanitizer,
> Schadensarten/Aktionsnamen/Heldische Inspiration als belegte Glossar-Kernpaare.
> Der Bericht bleibt als Beleg- und Methodik-Dokument stehen.

**Zweck:** Arbeitsgrundlage für die nächste Überarbeitungsrunde. Jeder Befund ist belegt,
verifiziert und mit Ursache + Lösungsansatz versehen. Reihenfolge = Abarbeitungsreihenfolge.

**Testgegenstand:** Commit `6cb9029` (main, PR #4 gemergt). Echter Lauf mit echtem Provider
(`ANTHROPIC_MODEL=claude-sonnet-5`), Charakter „Sorin Vale" (Mönch 5, Krieger des Schattens),
Quelle `vorlagen/charakterboegen/ddb-beispiele/Magnetron44523_168310785.pdf` (5 S.) →
3-seitiger DE-Bogen. Übersetzungsdauer 42,7 s.

**Methodik:** 4 unabhängige Prüf-Perspektiven (Layout / Sprache / Vollständigkeit / pingeliger
Spieler), jeder Befund anschließend von einem separaten Agenten adversarial gegengeprüft
(Auftrag: *widerlegen*). 37 Roh-Befunde → 24 verifiziert (davon 23 bestätigt + nicht quelltreu,
1 quelltreu). 13 Verifikationen fielen dem Session-Limit zum Opfer; die betroffenen
Layout-Befunde habe ich stattdessen **selbst deterministisch nachgemessen** (siehe P1/P5).

**Prüf-Artefakte:** `/private/tmp/claude-501/…/d51f9956-…/scratchpad/` — `uebersetzt.pdf`,
`ue_s{0,1,2}.png` (+ `_oben`/`_unten` in 3.6x), `uebersetzt_text.json`, `quelle_en.json`,
`ddb_s0…4.png`. Skript: `e2e_uebersetzt.py`. Journal aller Agenten:
`~/.claude/projects/…/subagents/workflows/wf_76924bb4-a7b/journal.jsonl`.

---

## Gesamturteil

**Das Fundament trägt.** Die Übertragung ist inhaltlich nahezu verlustfrei: alle 23 Merkmale,
alle 3 Zauber mit korrekten K/R/M-Marken, alle 6 Ausrüstungsgegenstände, 18 Fertigkeiten,
sämtliche Kampfwerte sind da. **Jede** nachgerechnete Distanz (1,5/3/9/12/18 m, 4,5-m-Kugel)
und **jeder** der >25 stichprobenartig verglichenen Würfel-/SG-/Bonuswerte stimmt exakt mit
dem DDB-Original. Die Review-Runde-1-Fixes halten: Attribute, Modifikatoren, Marken, Rauten,
Münzen und Tabellenzeilen sitzen sauber.

**Aber:** ein sachlich **verfälschender** Fehler (erfundene Armbrust-Vertrautheit), eine
Box-Kollision im Kopf, und ein `*`-System, das in **beide** Richtungen unzuverlässig ist —
es setzt Sterne auf belegte Begriffe und lässt sie bei unbelegten weg. Für einen pingeligen
Spieler ist das der Vertrauenskiller: Wenn die Fußnote nachweislich Falsches behauptet,
glaubt man ihr nirgends mehr.

**Roter Faden der Befunde:** Fast alles Verbleibende ist **eine Vertrauensgrenze zu viel zum
Sprachmodell**. Wo deterministisch gearbeitet wird (Zahlen, Marken, Geometrie), ist das
Ergebnis exzellent. Wo das LLM entscheidet, was es nicht entscheiden sollte (Listen zerlegen,
Zustandsbegriffe wählen), entstehen die Fehler.

---

## P1 — Erfundene Waffenvertrautheit „Armbrust" ⛔ SACHLICH FALSCH

**Symptom:** Bogen S1: „**Armbrust**, Handarmbrust, Krummsäbel, Kurzschwert, einfache Waffen
(Crossbow, Hand, Scimitar, Shortsword, Simple Weapons)" — **5** deutsche Einträge gegenüber
**4** englischen.

**Beleg:** `quelle_en.json` → `uebungen.waffen` = **ein** String `"Crossbow, Hand, Scimitar,
Shortsword, Simple Weapons"`. „Crossbow, Hand" ist DDBs **invertierte** Schreibweise für **eine**
Waffe (Hand Crossbow = Handarmbrust). Das DDB-Original (`ddb_s0.png`, PROFICIENCIES & TRAINING)
zeigt denselben Wortlaut. 3 von 4 Perspektiven meldeten dies unabhängig; alle 3 Verifikationen
bestätigten: **nicht quelltreu**.

**Warum es zählt:** Der Bogen bescheinigt eine Vertrautheit mit *allen* Armbrüsten, die der
2024-Mönch (einfache Waffen + Kriegswaffen mit Eigenschaft *Leicht*) **nicht hat**. Ein Spieler
würde am Tisch mit einer schweren Armbrust auftauchen. Das ist keine Stilfrage.

**Ursache:** Der Listenstring läuft als `art="liste"` **ungeteilt ins LLM** (`uebersetzer.py:102`
→ `_anwenden` Z. 69). Das Modell zerlegt ihn naiv am Komma und macht aus „Crossbow" + „Hand"
zwei Waffen. **Regressionsverdacht:** Am 14.07. erkannte dasselbe Modell die invertierte Waffe
noch korrekt (Memory) — d. h. das Verhalten ist **nicht-deterministisch**. Ob der neue kompakte
Prompt (`ddbd727`) es begünstigt hat, ist offen. Genau deshalb darf diese Entscheidung nicht
beim LLM liegen.

**Lösung (deterministisch, vor dem LLM):** Invertierte DDB-Namen im Extractor normalisieren,
bevor irgendetwas gesplittet wird: Muster `Crossbow, (Hand|Light|Heavy)` → `Hand Crossbow` etc.,
danach Items einzeln über `app.glossar` auflösen. Zielausgabe: „Handarmbrust, Krummsäbel,
Kurzschwert, einfache Waffen (…)". **Regressionstest:** Anzahl deutscher Items == Anzahl
normalisierter englischer Items.

---

## P2 — `*`-System unzuverlässig in beide Richtungen ⛔ VERTRAUENSKILLER

Die Fußnote verspricht: `*` = „kein offizieller deutscher Begriff belegt". Beide Richtungen brechen.

**(a) Stern auf belegten Begriffen:** „Mittelgroß\* (Medium)" — im Glossar **offiziell belegt**
(SRD 5.2.1, 2024). Ebenso „Betäubender Schlag\* (Stunning Strike)" (laut Verifier via MCP im
Pi-Bestand belegt, dt. Publikation).

**(b) Fehlender Stern auf unbelegten Begriffen:** „Heldenhafte Inspiration" trägt **keinen**
Stern, obwohl das Glossar für „Heroic Inspiration" **keinen** Eintrag hat.

**(c) Derselbe Begriff mal mit, mal ohne Stern:** „Schlagserie\* (Flurry of Blows)" in der
Waffentabelle vs. „Schlagserie" ohne Stern in *Fokus des Mönchs*. „Mittelgroß\*" im Kopffeld vs.
„Mittelgroß" ohne Stern im Spezies-Merkmal.

**Ursache — zwei getrennte Wurzeln:**

1. **Glossar-Stand (kein Code-Bug):** Der Lauf nutzte die lokale `data/foliant.sqlite` mit
   **1442** Glossar-Zeilen. Ich habe danach `admin import --quelle glossar` laufen lassen →
   **1548** Zeilen, und `terminologie.aufloesen(con, "Medium")` liefert **jetzt** „Mittelgroß
   (Medium)" **ohne** Stern. Befund (a) ist damit für „Medium" ein **Artefakt der veralteten
   Mac-DB** — exakt die in `CLAUDE.md` dokumentierte **Korpus-Lücke**. ⚠️ **Der Test muss gegen
   den vollen Pi-Bestand wiederholt werden, bevor irgendein `*`-Fix am Code geschieht.**
2. **Freitext-Begriffe werden nie aufgelöst (echter Bug):** `vorgaben` wird in
   `uebersetzer.py:100` **nur** aus `art="term"`-Feldern mit exaktem Treffer gefüllt. Begriffe,
   die ausschließlich **im Fließtext** vorkommen, sieht das Glossar nie — das LLM erfindet sie
   frei und ungekennzeichnet. Das erklärt (b) und (c) vollständig.

**Lösung:** `app.glossar.begriffe_im_text()` **existiert bereits** (im MCP-Server für
`begriffe_deutsch` im Einsatz) und tut genau das Richtige. Verifiziert:

```
begriffe_im_text(con, "…a creature Grappled by you… You gain Heroic Inspiration…")
→ [{'term_de': 'Angriffswürfe', 'term_en': 'Attack Rolls', …},
   {'term_de': 'Gepackt', 'term_en': 'Grappled', 'offiziell': 1, …}]
```

→ Vor dem LLM-Lauf jeden Freitext damit scannen und die Treffer in `vorgaben` mitgeben.
Das behebt P2(b)/(c), P3 und P4 **in einem Zug** und ist regelbasiert (Datenprinzip:
quellengetrieben, keine Einzelfall-Kuratierung).

---

## P3 — Zustandsbegriff verfehlt: „ergriffene Kreatur" statt **Gepackt (Grappled)**

**Symptom:** Talent *Ringer (Grappler)*: „Vorteil auf Angriffswürfe gegen eine von dir
**ergriffene** Kreatur".

**Beleg:** Die Quelle schreibt großgeschrieben „a creature **Grappled** by you" — die
**Zustandsreferenz**, keine freie Formulierung. Das Glossar kennt „Gepackt (Grappled)",
**offiziell=1**, Quelle Spielerhandbuch (selbst nachgeprüft, s. o.).

**Warum es zählt:** „ergriffen" kappt die Regelverknüpfung zum Zustand *Gepackt* und bricht mit
der Option „Ringen" im selben Absatz. Der Spieler findet die Regel nicht.

**Ursache/Lösung:** Identisch zu P2(2) — großgeschriebene Zustandsbegriffe müssen vor dem
Freitext-Lauf gegen das Glossar aufgelöst und als `vorgaben` erzwungen werden.

---

## P4 — Terminologie-Kollision mit der **Vorlage selbst**

**Symptom:** Das Spezies-Merkmal *Findigkeit* sagt „Du erhältst **Heldenhafte** Inspiration" —
wenige Zentimeter daneben ist auf demselben Bogen das Feld „**HELDISCHE** INSPIRATION"
vorgedruckt. Zwei Namen für dieselbe Ressource auf einer Seite.

**Ursache:** Kein Glossar-Eintrag für „Heroic Inspiration" → LLM erfindet frei.

**Lösung (regelbasiert, elegant):** Der **vorgedruckte deutsche WotC-Bogen ist selbst eine
offizielle Quelle**. Die Vorlagen-Labels als Glossar-Einträge seeden (Quelle: „Charakterbogen
2024 DE", offiziell=1) → „Heldische Inspiration" wird automatisch gezogen, ohne Stern, und
Text und Vordruck können gar nicht mehr auseinanderlaufen. Gleiches Muster für alle
Feld-Labels der Vorlage.

**Verwandt (gleiche Wurzel, eigener Fall):** *Lebender Schatten* übersetzt die 2024-Aktion
„**Magic**" als „Aktion Angriff oder **Zauber**" — „Zauber" bezeichnet auf dem ganzen Bogen
aber *spells*. Verifier-Empfehlung: Glossar-Brücke `Magic (Aktion)` ↔ **„Magie wirken"**
quellengetrieben aus `srd-de` seeden (nicht „Aktion Magie*" erfinden).

---

## P5 — Text läuft aus seiner Box (Kollision im Kopf) ⛔ SELBST NACHGEMESSEN

**Symptom:** „Krieger des Schattens\* (Warrior of Shadow)" liegt sichtbar **auf** dem
Stufe/EP-Oval.

**Messung (deterministisch, nicht per Auge):**

| Feld | Box | Text @ minsize | Ergebnis |
|---|---|---|---|
| `identitaet.unterklasse` | 85,0 pt | 116,7 pt @6.0 | **Überlauf +31,7 pt** |
| Zauber-Reichweite „9 m/1,5 m Würfel" | 42 pt | 43,7 pt @6.0 | **Überlauf +1,7 pt** |
| Zauber-Reichweite „18 m/4,5 m Kugel" | 42 pt | 47,0 pt @6.0 | **Überlauf +5,0 pt** |

Der gemessene Text der Unterklassen-Zeile reicht von x=155 bis **x=271,7**, das Rect endet bei
**x=240**; das Oval beginnt bei x≈249.

**Ursache (eine gemeinsame Wurzel für beide Befunde!):** `_fit_size` (`de_bogen.py:56`)
verkleinert nur **bis** `minsize` — passt es dann *immer noch* nicht, wird der Text
**trotzdem ungekürzt gezeichnet**. Es gibt keinen Umgang mit „passt nicht".

**Lösung:** In `_zeichne_einzeilig` einen definierten Umgang mit Restüberlauf ergänzen. Optionen
(Entscheidung nötig, s. u.): (a) horizontal stauchen via `fitz` Textmatrix, (b) intelligent
kürzen — bei `Deutsch (English)`-Form zuerst die Klammer opfern, (c) `minsize` feldweise senken,
(d) zweizeilig setzen. **Nie** stumm überlaufen lassen.

---

## P6 — Fortsetzungsseite ist verwaist

**Symptom:** Seite 2 beginnt mit „Wenn du den Schaden auf 0 reduzierst…" — ohne zu sagen, dass
das zu *Angriffe abwehren* gehört. Zusätzlich ist der **komplette Kopf der Vorlagen-Kopie leer**
(kein Charaktername). Eine lose Seite 2 ist weder einem Charakter noch einem Merkmal zuzuordnen.

**Ursache:** `_fortsetzungskopf` greift nur im **Satz**-Split-Zweig von `_para`
(`de_bogen.py:181`), nicht beim **Zeilen**-Split innerhalb eines Merkmals über Boxgrenzen hinweg.
Seite 1 setzt korrekt „(Fortsetzung nächste Seite)", das Gegenstück auf Seite 2 fehlt.

**Lösung:** (a) Wiederholungskopf „Angriffe abwehren\* (Deflect Attacks) (Fortsetzung)" beim
Box-Übergang — der Merkmalsname ist an der Bruchstelle bekannt. (b) Kopf der Vorlagen-Kopie
mindestens mit Charaktername/Klasse/Stufe befüllen (DDB tut das auf jeder Seite).
**Nebenbefund:** Aktionsklammer „Angriff abwehren" (Singular) vs. Merkmalsname „Angriffe
abwehren" — vereinheitlichen.

---

## P7 — Deutsche Notation/Typografie: Restlücken

| # | Symptom | Ursache | Lösung |
|---|---|---|---|
| a | Trefferwürfel „**5d8**" statt „5W8" — die **einzige** nicht eingedeutschte Würfelangabe (alle anderen: 1W8+4, 1W10+9, 2W8+4, W20) | `kampf.trefferwuerfel` ist ein **roher String**, kein `UeText` → läuft nie durch die d→W-Wandlung | Zentrale deterministische Normalisierung `(\d*)d(\d+)` → `\1W\2` auf **jedes** gerenderte Feld, nicht nur Fließtext |
| b | Zauber-Notizen „D: 1 Min, **V/S**" / „**S**/M" — „S"=somatic ist englisch, deutsch **G** (gestisch); „D:"=Duration | Notiz-String wird durchgereicht | Regex im vorhandenen Notiz-Normalisierer: `V/S`→`V/G`, `S/M`→`G/M`, `D:`→`WD:` |
| c | Anführungszeichen kaputt: „…Tabelle **·**Wille des Schattens**"**…" | `_ERSATZ` (`de_bogen.py:36`) kennt **U+201E/U+201A** nicht → Helvetica rendert `·` | Deutsche Quotes in `_ERSATZ` ergänzen |
| d | Streuzeichen „[Erhöhe zwei Werte (+2 / +1) **·**]" | verwaister Aufzählungspunkt aus der Quelle | im Bereinigungsschritt strippen |

---

## P8 — Grammatik-/Stilpatzer des LLM

| Stelle | Ist | Soll |
|---|---|---|
| *Vielseitigkeit* | „Du erhältst **einen** Ursprungs-Talent" | „**ein** Ursprungstalent" (Neutrum) |
| *Fokus des Mönchs* | „…Energievorrat anzuzapfen, **die** Fokuspunkte genannt werden" | Kongruenz: „…in Form von Fokuspunkten anzuzapfen" |
| Talent-Überschrift | „Nebelwanderer Attributswerterhöhung" | Durchkopplung: „Nebelwanderer-Attributswerterhöhung" |
| *Ringer* | „Vorteil **auf** Angriffswürfe" | idiomatisch „Vorteil **bei** Angriffswürfen" |

**Hinweis:** Das sind LLM-Ausgaben, nicht deterministisch reproduzierbar — Einzelkorrekturen im
Code wären wirkungslos. Hebel ist der System-Prompt (Genus-/Kongruenz-/Durchkopplungs-Regel)
plus die `vorgaben`-Anreicherung aus P2.

---

## P9 — Informationsverluste gegenüber DDB (Design-Entscheidungen nötig)

Alle Werte sind **extrahiert** und liegen im Modell — sie werden nur **nicht gerendert**, weil die
deutsche Vorlage kein Feld dafür hat. Kein Extraktions-Bug; es braucht eine Entscheidung.

| Was | Im Modell | Bewertung |
|---|---|---|
| **Dunkelsicht 18 m** (`kampf.sinne`) | `"Darkvision 60 ft."`, `de=None` | steht nur versteckt im Fließtext — **der schmerzhafteste Verlust am Tisch** |
| **Traglast** 17/120/240 lb. | vollständig | Summe + Grenzwerte fehlen ganz, obwohl Einzelgewichte in kg umgerechnet sind |
| **Passive Einsicht 16 / Untersuchung 9** | vollständig | Vorlage hat nur *ein* Passiv-Feld; ableitbar |
| **Zauber-Herkunft + Seitenrefs** (293/298/260) | `zauber[].quelle/.seite` | Vorlage hat keine Spalte |
| **ACTIONS/BONUS ACTIONS** (18 Standardaktionen) | `aktionen[]` | Feld wird **von niemandem konsumiert** (nur `ddb_pdf.py:297` befüllt es); großteils statisches Regel-Boilerplate |
| **Spielername** „Magnetron44523" | `identitaet.spielername` | Vorlage hat kein Feld |

**Vorschlag:** Dunkelsicht + Traglast rendern (freie Flächen: Notizen-Spalte der Waffentabelle,
Fuß der Ausrüstungs-Box). Rest bewusst als dokumentierte Auslassung führen. **Braucht Davids
Entscheid** — es ist die Grenze zwischen „Vorlage treu" und „Werkzeug nützlich".

---

## P10 — Layout-Feinschliff (nachrangig)

- **Schriftgrad-Sprung** auf der Fortsetzungsseite: linke Spalte klein, rechte ~1,5× größer.
  Ursache: `_grossbox` (`de_bogen.py:409`) ruft `_para` **pro Spalte** → jede fittet eigenständig.
  Lösung: Größe **einmal pro Kasten** bestimmen (wie bereits bei `_waffen_tabelle` gelöst).
- **Kein rechter Innenabstand:** Text berührt Rahmen/Spaltentrenner (S1 Klassenmerkmale/Talente,
  S2 rechts, Waffen-Namensspalte). Lösung: 2–3 pt Padding auf die Box-Rects.
- **„(Milestone)"** füllt das Oval randvoll (39,6/54 pt — kein Überlauf, nur optisch gedrängt).
- **Zauber-Reichweite:** Zeile 1 zentriert, Zeilen 2–3 linksbündig kleiner (Folge des
  Per-Zelle-Autofits — gleicher Hebel wie beim Schriftgrad-Sprung).

---

## Abarbeitungs-Reihenfolge (Empfehlung)

**Vorab, zwingend:** Bogen gegen den **vollen Pi-Glossar-Stand** neu erzeugen. Die lokale
Mac-DB war um 106 Zeilen veraltet; mindestens „Mittelgroß" verliert dadurch seinen Stern.
Ohne diesen Schritt behebt man Phantom-Befunde (Korpus-Lücke, `CLAUDE.md`).

1. **P1** Armbrust — deterministische Normalisierung *(sachlich falsch, sofort)*
2. **P2(2) + P3 + P4** — `begriffe_im_text()` in `vorgaben` einhängen + Vorlagen-Labels ins
   Glossar seeden *(ein Fix, drei Befunde, regelbasiert)*
3. **P5** Box-Überlauf — gemeinsamer Fix für Unterklasse + Zauber-Reichweite
4. **P6** Fortsetzungskopf + Kopfzeile der Kopie
5. **P7** Notation/Typografie *(billig, rein deterministisch)*
6. **P8** System-Prompt schärfen
7. **P10** Layout-Feinschliff
8. **P9** — **erst nach Davids Entscheid**

## Offene Fragen an David

1. **P9:** Dunkelsicht/Traglast/passive Werte auf freie Flächen rendern — oder Vorlagentreue
   über Nützlichkeit? (Meine Empfehlung: Dunkelsicht + Traglast ja, Rest dokumentiert weglassen.)
2. **P5:** Bei Restüberlauf lieber stauchen, kürzen (Klammer zuerst opfern) oder zweizeilig?
3. **P4:** Vorlagen-Labels als **offizielle** Glossar-Quelle akzeptieren? (Sie stehen gedruckt
   auf dem lizenzierten WotC-Bogen — nach meiner Einschätzung die sauberste Quelle überhaupt.)
