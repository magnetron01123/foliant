# Rückmeldungs-Durchgang (O4/M5)

Werte die Rückmeldungen der Runde aus, prüfe sie gegen die Doku und lege David eine
**Vorschlagstabelle** vor. Setze **nichts** um, bevor er freigegeben hat.

## Die eine Regel, die alles trägt

**Analyse automatisch, Änderung nur nach Freigabe.** Kein Branch, keine vorbereiteten
Edits, kein „ich hab's schon mal gemacht". Der Grund ist strukturell: In dieser Schleife
bewertest du Antworten und änderst danach die Regeln, die dein eigenes Verhalten steuern.
Ohne menschliches Gate driftet das, und ein falsches „offiziell"-Glossar-Paar wandert
durch den ganzen Bestand.

Zweites Gegengewicht: **Jede vorgeschlagene Verhaltensänderung braucht einen Test oder
Eval-Fall, der ohne sie fehlschlägt.** Sonst ist sie nicht belegt, sondern nur plausibel.

## 1. Daten holen

```
make bericht-pi TAGE=30
```

Liefert JSON mit `markiert` (👎) und `gelobt` (👍). Vergleiche die Zeitpunkte gegen
`zuletzt_gesichtet_bis` in `config/rueckmeldungen_stand.json` — **arbeite nur, was
jünger ist.**

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
   verletzt, hilft keine weitere Prompt-Regel — dann weiter bei Kanal 1 (Grounding-Hinweise
   in den Tool-Ausgaben, laut SPEC §7 der zuverlässigste) oder bei den Daten.
6. **Datenursache prüfen**, mit lesenden Kommandos auf dem Pi. Beispiel aus dem ersten
   Durchgang: `glossar.begriffe_im_text()` durchsucht nur `body_md`, nie den Eintragsnamen
   — deshalb blieb „Archfey Patron" englisch, obwohl das Glossar „Erzfee" führt. Ein
   **Code**-Befund; keine Prompt-Regel hätte ihn behoben.

## 3. Je 👍 — Triage

- Lob gilt dem, **was aus dem Bestand kam** (vollständiger Statblock, richtiger deutscher
  Begriff, richtige Edition/Seite) → **Golden-Test** in `tests/test_golden_bestand.py`.
  Der Standardweg: kostenlos und bei jedem Deploy wirksam.
- Lob gilt dem, **wie die Antwort gebaut war** (saubere Ablehnung, ehrliche Rückfrage bei
  Mehrdeutigkeit, gekennzeichneter 2024/2014-Kontrast) → **Eval-Fall** in
  `evals/faelle.py`, `richter=True` mit einer Rubrik, die den Grund des Lobes benennt.
  **Nur mit ausdrücklicher Freigabe pro Fall** — Evals kosten Tokens bei jedem Lauf.
- Lob gilt keinem von beiden (jemand fand es nett) → **kein Artefakt.** Zählt als „kein
  Befund". Das ist ausdrücklich erlaubt: 👍 kommt reflexhaft, und eine Suite, die mit jeder
  Nettigkeit wächst, wird bald nicht mehr gefahren.

Nebenbei kostenlos: Ein 👍 auf eine Frage, die zuvor ein 👎 hatte, ist der
**Wirksamkeitsnachweis** des damaligen Fixes. Sag es dazu, wenn du einen findest.

## 4. Vorschlagstabelle

| # | Art | Frage (gekürzt) | Regel-ID | Ursache in einem Satz | Maßnahme | Ablageort | Aufwand |

Darunter je Zeile ein Absatz: **welche Datei, welche Funktion, was sich ändert** — und was
der Regressionsschutz sein soll. Am Ende eine Zeile **„Nicht vorgeschlagen: … (Grund)"**
für alles Aussortierte; sonst sieht David nur, was übrig blieb, nie was verworfen wurde.

Freigabe erfolgt per Nummern („1, 3 — 2 nicht"). **Erst danach Code.**

**Wenn der Durchgang zeitgesteuert lief:** Schick am Ende genau **eine**
Push-Benachrichtigung — David sitzt nicht davor und erfährt sonst nie, dass etwas
vorliegt. Ein Satz, das Handlungsbedürftige zuerst: *„3 Rückmeldungen ausgewertet, 2
Befunde (S3 Deutsch-first, B4) — Vorschläge liegen zur Freigabe bereit."* Nicht der
Befundtext, nicht die Tabelle: die steht in der Sitzung, die er dann öffnet.

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

Zwei Fallen beim Schreiben: `config/stil.py` hat ein hartes Budget von 7500 Zeichen (Stand
~7154) — wird es eng, **entdoppeln oder in Kanal 1 verlegen**, nicht die Grenze anheben.
Und `tests/test_doku_pflege.py` erzwingt: Stand-Angaben nachziehen, genannte Dateien müssen
existieren, kein wortgleicher Satz ≥120 Zeichen in zwei Doku-Dateien.

## 6. Abschluss

- `config/rueckmeldungen_stand.json` fortschreiben: neue Hochwassermarke, ein
  Durchgangs-Eintrag mit Zählwerten und je einem Befund-Objekt (`regeln`, `ursache`,
  `was` — Format steht in der Datei). **Keine Links, keine Kanal-/Nachrichten-IDs, keine
  Namen** — das Repo ist öffentlich.
  Schau beim Eintragen die **vorherigen Durchgänge** an: Bricht dieselbe Regel-ID zum
  dritten Mal, ist das kein Modellfehler mehr, sondern eine Regel, die an der falschen
  Stelle steht — sag das im Vorschlag dazu.
- `BACKLOG.md` M5 nur bei **Bemerkenswertem** ergänzen (ein Durchgang ohne Funde ist keine
  Meldung wert). Die Buchführung macht die JSON-Datei.
- `make test`; bei Code- oder Datenänderungen nach dem Deploy zusätzlich
  `make test-golden-pi`.
- Branch pro Thema, PR wenn das Thema fertig ist, **nie selbst mergen**.
