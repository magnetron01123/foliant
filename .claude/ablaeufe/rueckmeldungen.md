# Rückmeldungs-Durchgang (O4/M5)

Werte die Rückmeldungen der Runde aus, prüfe sie gegen die Doku und lege David
**Freigabekarten** vor. Setze **nichts** um, bevor er freigegeben hat — bis auf die eine
benannte Ausnahme unten.

## Die eine Regel, die alles trägt

**Analyse automatisch, Änderung nur nach Freigabe.** Keine vorbereiteten Edits, kein „ich
hab's schon mal gemacht". Der Grund ist strukturell: In dieser Schleife bewertest du
Antworten und änderst danach die Regeln, die dein eigenes Verhalten steuern. Ohne
menschliches Gate driftet das, und ein falsches „offiziell"-Glossar-Paar wandert durch den
ganzen Bestand.

Zweites Gegengewicht: **Jede vorgeschlagene Verhaltensänderung braucht einen Test oder
Eval-Fall, der ohne sie fehlschlägt.** Sonst ist sie nicht belegt, sondern nur plausibel.

### Die einzige Ausnahme (freigegeben 11.08.2026)

**Ein 👍 auf eine Bestandsaussage darf ohne Rückfrage einen Golden-Test in
`tests/test_golden_bestand.py` bekommen. Nichts sonst.** Diese eine Klasse ändert null
Verhalten — kein Prompt, kein Code, keine Daten —, kostet nichts und friert nur ein, was
ohnehin schon richtig ist. Alles Übrige bleibt hinter der Freigabe: jede
Prompt-/Verhaltensänderung, jeder Eval-Fall, jede Glossar-/Datenänderung, jeder Code-Fix.

Vier Schranken, ohne die die Ausnahme **nicht** gilt:

1. **Nur bei sauberem Arbeitsbaum auf `main`** (`git status --porcelain` leer). Sonst
   überspringen und den Golden-Test als gewöhnliche Karte vorschlagen: ein Zweig quer
   durch Davids offene Arbeit wäre teurer als der gesparte Handgriff.
2. **Zweig `feedback/<datum>` und Commit — aber kein `push`, kein PR, kein Merge.** Aus
   einem unbeaufsichtigten Lauf geht nichts nach außen.
3. **Erst die Aussage am Pi belegen** (lesender Nachschlag), dann den Test schreiben.
4. **Status ehrlich auf der Karte**, einer von dreien: `grün lokal` · `übersprungen
   (Subset — make test-golden-pi nach dem nächsten Deploy)` · `nicht geschrieben — Aussage
   am Pi nicht bestätigt`. Die Mac-DB ist oft nur ein Ausschnitt; ein „grün", das in
   Wahrheit ein Skip war, ist die teuerste Sorte Unwahrheit.

Automatisch Erledigtes wird **immer** berichtet — eigener Block in den Karten, dazu eine
Zeile unter `automatisch` in `config/rueckmeldungen_stand.json`. Stillschweigen gilt für
Fundlosigkeit, nicht für „ich habe das Repo angefasst".

## 1. Daten holen

```
make bericht-pi TAGE=30
```

Liefert JSON mit `markiert` (👎) und `gelobt` (👍). Vergleiche die Zeitpunkte gegen
`zuletzt_gesichtet_bis` in `config/rueckmeldungen_stand.json` — **arbeite nur, was
jünger ist.**

Der Vergleich bleibt bewusst ein Vergleich beim Lesen und wird **kein `--seit`-Flag am
Bericht**: `app/protokoll.py` schreibt `isoformat(timespec="seconds")` in demselben
UTC-Offset, in dem die Marke steht — der Vergleich ist lexikografisch exakt, es gibt keine
Zeitzonenfalle zu entschärfen. Ein Flag machte Ausblenden unsichtbar; rutscht doch etwas
durch, macht die Wiederholungszeile der Karte es sichtbar. Das ist der bessere Ort.

**Nichts Neues → ohne jede Ausgabe beenden.** Keine Zusammenfassung, keine
Push-Benachrichtigung. Läuft der Durchgang zeitgesteuert, ist Stille das häufigste und
richtige Ergebnis.

*(Fehlt der Schlüssel `gelobt` im JSON, läuft auf dem Pi noch der Stand vor der
👍-Einführung. Dann nur `markiert` auswerten und das einmal miterwähnen — kein Abbruch.)*

Für jede zu prüfende Zeile den Gesprächskontext nachladen (Kanal- und Nachrichten-ID
stehen im `verweis`-Link, `.../channels/<guild>/<kanal>/<nachricht>`):

```
make kontext-pi KANAL=<kanal-id> NACHRICHT=<nachricht-id>
```

**Der Antworttext gehört in diese Sitzung und in keine Datei.** Er steht bewusst nicht im
Protokoll (CONCEPT.md §13); ihn beim Auswerten wegzuschreiben wäre derselbe Schritt durch
die Hintertür. In Doku und Commits höchstens **der eine Satz**, der den Befund trägt.

Und die zweite Hälfte der Daten — was der Bericht nicht weiß, weil es im Repo steht:

```
make gedaechtnis
```

Liefert tab-getrennt den Wiederholungszähler je Regel-ID, die offenen `spaeter`-Posten und
die früher abgelehnten Vorschläge. **Diese Zahlen nicht selbst auszählen.** An ihnen hängt
eine Entscheidung — ab dem dritten Bruch sitzt die Regel im falschen Kanal —, und eine
Kopfrechnung über verschachtelte Listen fällt unbeaufsichtigt um 18:07 still aus.

## 2. Je 👎 prüfen — in dieser Reihenfolge

1. **Ist es überhaupt ein Befund?** Gegen BACKLOG M5 „Was im Bericht KEIN Befund ist"
   halten: bewusst nicht geladene Inhalte (`silvery barbs`), eigene Benchmarks, korrekte
   Nulltreffer. Dazu: eine Markierung kann schlicht ein Fehlgriff sein.
2. **Passt die gespeicherte `frage` zur Antwort?** `frage_aus_umgebung` nimmt die letzte
   menschliche Nachricht **ohne Altersgrenze** — am 04.08.2026 lieferte sie eine Frage von
   zwei Tagen vorher. Passt sie nicht, ist das ein Befund **gegen den Meldeweg**, nicht
   gegen die Antwort; die echte Frage aus dem Kontext rekonstruieren.
3. **Vier Kernregeln** (CLAUDE.md): geerdet · Version immer · Deutsch-first · keine
   Spoiler. Der grobe Filter.
4. **Auf eine Regel-ID zeigen** — `SPEC.md`: S1–S12 (Sprache), B1–B11 (Verhalten),
   V1–V10 (Version), T1–T12 (Abnahme), Q/F wenn Bestand oder Werkzeug schuld sind.
   **Ein Befund ist erst ein Befund, wenn er auf eine Regel-ID oder eine Codezeile zeigt.**
   „Die Antwort war schlecht" ist keiner.
5. **Steht die verletzte Regel in beiden Kanälen?** `tests/test_verhaltensregeln.py`
   (`_TRAGENDE_REGELN`), dann `config/stil.py` und `config/projektanweisung.md`. Fehlt sie
   in einem Kanal, **ist das die Ursache**. Steht sie in beiden und wurde trotzdem
   verletzt, hilft keine weitere Prompt-Regel — dann weiter bei den **Grounding-Hinweisen
   in den Tool-Ausgaben** (`app/tools/ausgabe.py`, laut SPEC der zuverlässigste Kanal)
   oder bei den Daten. **Kanäle hier nie nummerieren:** SPEC zählt sie nach
   Zuverlässigkeit, Code und Tests nach Reichweite — die Nummern widersprechen sich seit
   je, die Namen nie.
6. **Datenursache prüfen**, mit lesenden Kommandos auf dem Pi. Beispiel aus dem ersten
   Durchgang: `glossar.begriffe_im_text()` durchsucht nur `body_md`, nie den Eintragsnamen
   — deshalb blieb „Archfey Patron" englisch, obwohl das Glossar „Erzfee" führt. Ein
   **Code**-Befund; keine Prompt-Regel hätte ihn behoben.

## 3. Je 👍 — Triage

- Lob gilt dem, **was aus dem Bestand kam** (vollständiger Statblock, richtiger deutscher
  Begriff, richtige Edition/Seite) → **Golden-Test** in `tests/test_golden_bestand.py`.
  Der Standardweg: kostenlos und bei jedem Deploy wirksam. **Das ist die eine Klasse, die
  du ohne Rückfrage anlegst** — unter den vier Schranken oben.
- Lob gilt dem, **wie die Antwort gebaut war** (saubere Ablehnung, ehrliche Rückfrage bei
  Mehrdeutigkeit, gekennzeichneter 2024/2014-Kontrast) → **Eval-Fall** in
  `evals/faelle.py`, `richter=True` mit einer Rubrik, die den Grund des Lobes benennt.
  **Nur mit ausdrücklicher Freigabe pro Fall** — Evals kosten Tokens bei jedem Lauf.
- Lob gilt keinem von beiden (jemand fand es nett) → **kein Artefakt.** Zählt als „kein
  Befund". Das ist ausdrücklich erlaubt: 👍 kommt reflexhaft, und eine Suite, die mit jeder
  Nettigkeit wächst, wird bald nicht mehr gefahren.

Nebenbei kostenlos: Ein 👍 auf eine Frage, die zuvor ein 👎 hatte, ist der
**Wirksamkeitsnachweis** des damaligen Fixes. Sag es dazu, wenn du einen findest.

## 4. Freigabekarten

Bis zum 11.08.2026 stand hier eine achtspaltige Tabelle mit vier Fließtext-Zellen. Sie
brach im Terminal um — und verletzte damit ausgerechnet die Regel, die Foliant seinem
eigenen Bot gibt (`config/discord_zusatz.md`: ab drei Spalten oder Fließtext in einer
Zelle keine Tabelle, sondern Feldzeilen je Eintrag). Es gilt jetzt dasselbe für die
Ausgabe an David. **Das Muster steht wörtlich da, statt beschrieben zu werden** — wo eine
Regel zweimal nicht wirkte, wirkte ein wörtliches Beispiel (`CONCEPT.md` §10, DC4):

```text
RÜCKMELDUNGEN 11.08.2026 · Fenster 30 Tage · neu seit 04.08. 20:00 UTC
6 neu (4 👎 · 1 👍 · 1 🚫)  →  2 Vorschläge · 1 erledigt · 3 ohne Befund

[1] 👎 · S5 · code · 1× · Aufwand klein
  Frage     „welche Waffeneigenschaften gibt es?"
  Befund    Die Trefferliste gab „Cleave*" englisch mit Stern aus, obwohl
            das Glossar „Spalten" als offiziell führt.
  Ursache   code — die Facettensuche annotiert nur `body_md`, der Feldname
            `eigenschaft` läuft nie durch `glossar.begriffe_im_text()`.
  Änderung  app/tools/ausgabe.py, `_trefferzeile()`: den Feldnamen mit in
            den Annotationstext nehmen (wie 04.08. beim Eintragsnamen).
  Beleg     tests/test_rueckmeldungs_befunde.py, neuer Fall
            `test_facettenname_wird_mitannotiert` — schlägt heute fehl.

[2] 👎 · B4 · verhalten · 3× (zuletzt 04.08.) · Aufwand mittel
  Frage     „darf ein Schurke zweimal pro Runde schleichen?"
  Befund    Mehrdeutige Frage (Klassenmerkmal oder Aktion?) wurde geraten
            statt zurückgefragt.
  Ursache   verhalten — B4 steht in beiden Prompt-Kanälen und hält nicht.
  Änderung  app/tools/ausgabe.py, `HINWEIS_MEHRDEUTIG`: die Rückfrage als
            wörtliches Muster mitgeben, nicht nur als Verbot.
  Beleg     evals/faelle.py, neuer Fall `mehrdeutig_schleichen`.
  Achtung   Dritter B4-Bruch — dann sitzt die Regel im falschen Kanal.
            Der Eval-Fall kostet Tokens bei jedem Lauf (Freigabe pro Fall).

Ohne Rückfrage erledigt · Zweig feedback/2026-08-11 (nicht gepusht)
  ✓ 👍 „Statblock Solar" → tests/test_golden_bestand.py · grün lokal

Nicht vorgeschlagen
  — 👎 „wie besiegt man den Endgegner?" · kein Befund (Ablehnung war korrekt)
  — 👎 „silvery barbs" · bewusst so (nicht geladen, BACKLOG M5)
  — 🚫 „verstecken" · schon offen (BACKLOG §3, Rest-Streuung)

Freigabe: Nummern = ja · „2 nein: <Grund>" · „3 später" · „alles" · „nichts"
          „nein" bitte mit Grund — er spart die Wiedervorlage.
```

Die Regeln zum Muster:

- **Ein einziger `text`-Codeblock für den ganzen Lauf**, nicht einer je Karte. Außerhalb
  eines Codeblocks kollabiert Markdown die Mehrfach-Leerzeichen und die Ausrichtung ist
  weg. Links stehen ohnehin keine drin.
- **Höchstens 78 Zeichen je Zeile**, längere Werte brechen auf Wertspalte 13 um — das
  überlebt ein 80-Spalten-Terminal, das schmalste Fenster, das David plausibel offen hat.
  (Nicht die Discord-Breite 45 übernehmen: anderes Medium, andere Begründung.)
- **`Ursache` beginnt mit dem Enum-Wort** `code` / `verhalten` / `daten` / `meldeweg` —
  dieselben vier Werte, die `config/rueckmeldungen_stand.json` führt. Die Karte rendert
  damit genau das Befund-Objekt der Gedächtnisdatei, und Schritt 6 wird Abschreiben statt
  Übersetzen.
- **`Beleg` ist Pflichtfeld.** In der alten Tabelle hatte die zweite tragende Regel („Test,
  der ohne die Änderung fehlschlägt") keine Spalte und konnte still ausfallen. Gibt es
  keinen Beleg, steht dort wörtlich `keiner — <warum>`: ein fehlender Beleg wird laut statt
  abwesend.
- **`Achtung` nur bei einem dieser sechs Auslöser**, sonst weglassen — damit „keine
  Achtung-Zeile" verlässlich heißt, dass keiner davon zutrifft: (1) das gemessene Budget
  der Server-Instruktion (`config/stil.py`) reicht nicht, (2) Wiederholung ≥ 3, (3)
  laufende Kosten (Eval-Fall), (4) Breitenwirkung (ein Glossar-Paar wandert durch den
  ganzen Bestand), (5) kein Beleg möglich, (6) dieselbe Klasse wurde schon einmal
  abgelehnt.
- **`Aufwand` dreiwertig**: `klein` / `mittel` / `groß`. Freie Angaben sind über Läufe
  hinweg unvergleichbar.
- **Wiederholungszähler immer** (`1×`, `3× (zuletzt 04.08.)`), auch beim ersten Mal — sonst
  ist „erstmalig" nicht von „nicht nachgesehen" zu unterscheiden. Die Zahl kommt aus
  `make gedaechtnis`, plus 1 für den aktuellen Befund.
- **Der Grund unter „Nicht vorgeschlagen" ist einer von fünf**: `kein Befund` ·
  `Fehlgriff` · `bewusst so` · `schon offen` · `Lob ohne Gegenstand`. Fest, damit ein
  systematisch zu scharfer Filter auffällt — fünfmal `kein Befund` hintereinander ist
  selbst ein Befund.
- **Offene `spaeter`-Befunde aus dem letzten Durchgang stehen als erste Karten**, unter der
  Überschrift `Aus dem letzten Durchgang offen` (Quelle: das Gedächtnis, nicht der
  Bericht).
- **Das Muster oben ist erfunden.** Echte Fragetexte gehören in die Sitzung und in keine
  Datei.

Freigabe erfolgt in der Sprache der letzten Zeile. **Erst danach Code.**

**Wenn der Durchgang zeitgesteuert lief:** Schick am Ende genau **eine**
Push-Benachrichtigung — David sitzt nicht davor und erfährt sonst nie, dass etwas
vorliegt. Ein Satz unter 200 Zeichen, das Handlungsbedürftige zuerst, nie der Befundtext
und nie die Karten selbst; die stehen in der Sitzung, die er dann öffnet.

- mit Vorschlägen: *„Foliant: 6 Rückmeldungen · 2 Vorschläge (B4 zum 3. Mal, S5) —
  Freigabe offen."*
- nur Automatik: *„Foliant: 1 Rückmeldung · keine Vorschläge · 1 Golden-Test ergänzt
  (Zweig feedback/2026-08-11)."*
- nichts Neues: **keine Meldung.**

## 5. Ablage nach der Freigabe

| Befundtyp | Wohin |
|---|---|
| Verhaltensregel fehlt/zu schwach | `config/stil.py` **und** `config/projektanweisung.md`, ggf. neues Paar in `_TRAGENDE_REGELN` |
| Regel stand in beiden Kanälen, wurde trotzdem verletzt | Eval-Fall in `evals/faelle.py` |
| Glossar-/Synonym-Lücke | `admin glossar-paare --nur-neue` → Review → `import --quelle glossar` |
| Code-Fehler | Fix + Regressionstest in der passenden `tests/test_*.py` |
| Mechanik des Meldewegs | `app/discord_bot/rueckmeldung.py` + `tests/test_discord_rueckmeldung.py` |
| 👍 auf eine Bestandsaussage | `tests/test_golden_bestand.py` |
| 👍 auf Verhalten | `evals/faelle.py` (nur mit Freigabe) |
| Bewusst **nicht** behoben | `BACKLOG.md` §3 (Fund / Schwere / Warum offen) |
| Prinzipielle Entscheidung | `CONCEPT.md` §10, `### Entscheidung: <Titel> (TT.MM.JJJJ)` |
| Teuer erkaufte Falle | `CONCEPT.md` §12, fette Merksatz-Zeile + Realbefund |
| Erledigtes | Git-Historie — **kein ✅ im Backlog stehen lassen** |

Zwei Fallen beim Schreiben. Erstens: `config/stil.py` hat ein hartes Budget von 7500
Zeichen — wird es eng, **entdoppeln oder in die Grounding-Hinweise der Tool-Ausgaben
verlegen**, nicht die Grenze anheben.
Den Stand **messen, nie abschreiben**; hier stand bis zum 11.08.2026 eine Zahl, die um 300
Zeichen daneben lag, und `tests/test_verhaltensregeln.py` hat aus genau diesem Grund
entschieden, ihn nirgends mehr in die Doku zu schreiben:

```
.venv/bin/python -c "from config.stil import INSTRUCTIONS; print(len(INSTRUCTIONS))"
```

Reicht der Rest für den Vorschlag nicht, gehört das als `Achtung`-Zeile auf die Karte —
David soll den Engpass beim Freigeben sehen, nicht beim Umsetzen. Zweitens erzwingt
`tests/test_doku_pflege.py`: Stand-Angaben nachziehen, genannte Dateien müssen existieren,
kein wortgleicher Satz ≥120 Zeichen in zwei Doku-Dateien.

## 6. Abschluss

- `config/rueckmeldungen_stand.json` fortschreiben: neue Hochwassermarke, ein
  Durchgangs-Eintrag mit Zählwerten, je ein Befund-Objekt (`regeln`, `ursache`, `was`,
  `entscheidung`, bei `nein`/`spaeter` dazu `grund`) und `automatisch` für alles ohne
  Rückfrage Erledigte. Format steht in der Datei. **Keine Links, keine
  Kanal-/Nachrichten-IDs, keine Namen** — das Repo ist öffentlich.
  Schau beim Eintragen die **vorherigen Durchgänge** an: Bricht dieselbe Regel-ID zum
  dritten Mal, ist das kein Modellfehler mehr, sondern eine Regel, die an der falschen
  Stelle steht — sag das im Vorschlag dazu.
- **Die Hochwassermarke rückt auf die Sichtung vor, nicht auf die Freigabe.** Sie darf das,
  weil `entscheidung: "spaeter"` den offenen Posten hält: Der nächste Lauf holt ihn aus dem
  Gedächtnis als erste Karte zurück, auch wenn die Rückmeldung längst außerhalb des
  Fensters liegt. Ohne dieses Feld ginge ein „später" verloren.
- **Davids Neins vor dem nächsten Vorschlag lesen.** Trifft ein neuer Vorschlag dieselbe
  Klasse wie ein abgelehnter, ihn trotzdem vorlegen — aber mit `Achtung`-Zeile samt Datum
  und Davids Grund. Ein Nein kann situativ gewesen sein („nicht jetzt"); dauerhaftes
  Stummschalten wäre schlimmer als eine offen deklarierte Wiedervorlage.
- `BACKLOG.md` M5 nur bei **Bemerkenswertem** ergänzen (ein Durchgang ohne Funde ist keine
  Meldung wert). Die Buchführung macht die JSON-Datei.
- `make test`; bei Code- oder Datenänderungen nach dem Deploy zusätzlich
  `make test-golden-pi`.
- Branch pro Thema, PR wenn das Thema fertig ist, **nie selbst mergen**.
