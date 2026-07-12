# Unabhängige D&D-Regelwerkreview: Foliant

## 1. Metadaten der Review

| Feld | Wert |
|---|---|
| Reviewer | `codex` |
| Review-Typ | D&D-Regelwerkreview |
| Datum | 2026-07-12 |
| Git-Commit | `5cc67289a8066ce83b3a62aa9822165b1acfacbb` |
| Branch | `main` |
| Bewerteter Standard | D&D 5e, Regelfassung 2024, im Projekt auch als „5.5e“ bezeichnet |
| Hauptquellen der Fachprüfung | Lokaler deutscher SRD-5.2.1-Bestand; englischer SRD-5.2/Open5e-Bestand; read-only geprüfter privater DDB-Bestand mit Basic Rules 2014/2024 und Player's Handbook 2024 |
| Ausgeschlossene Inhalte | Sämtliche bereits vorhandenen Dateien unter `docs/reviews` wurden weder gelesen noch durchsucht und flossen nicht in diese Review ein. |

Ausgeführte Prüfungen:

- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -rs -p no:cacheprovider`: **98 bestanden, 5 übersprungen**, 6 Deprecation-Warnungen.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -rs -p no:cacheprovider tests/test_abnahme.py tests/test_build_pruefung.py tests/test_editionen.py tests/test_glossar_qualitaet.py tests/test_dubletten.py`: **37 bestanden, 1 übersprungen**.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tests.smoke_test`: **Smoke-Test erfolgreich**, alle 16 Tools aufrufbar.
- `python -m app.admin status` sowie read-only SQL-Inventur von `data/foliant.sqlite` und `data/private/foliant-private.sqlite`.
- Direkte Laufzeitproben der Nachschlage-, Glossar-, Charakterbau-, Zauber-, Monster- und Gegenstands-Tools, jeweils ohne Datenänderung.
- Synthetische, nicht persistierende Formatterproben für Open5e-Reaktionstrigger und Monsterfelder.

Nicht oder nur eingeschränkt prüfbar:

- Der in `README.md:17-21` beschriebene Live-Bestand auf dem Raspberry Pi mit ungefähr 9.490 Einträgen aus 12 Quellen war lokal nicht verfügbar. Bewertet wurden der konfigurierte öffentliche Bestand mit 2.621 Einträgen sowie die vorhandene private Kandidaten-Datenbank mit 8.879 Einträgen.
- Das reale Antwortverhalten eines angebundenen Claude-/MCP-Clients wurde nicht Ende-zu-Ende ausgeführt. Gerade Quellenformat, Spoilerablehnung und Rückfragen sind modellabhängig.
- Fünf Tests wurden regulär übersprungen: drei DDB-Exporter-/SQLCipher-Tests mangels separater `.venv-ddb`, ein OCR-Test mangels Tesseract/ocrmypdf und der manuelle Spoiler-Verhaltenstest T10.
- Diese Review ist eine fachliche und keine verbindliche rechtliche Bewertung.

## 2. Executive Summary

Foliant besitzt eine gute fachliche Grundlage: Der 2024-Standard ist klar benannt, Quellen und Editionen werden an Einträgen mitgeführt, der öffentliche Bestand stützt sich auf hochwertige SRD-Quellen, und zahlreiche stichprobenartig geprüfte 2024-Regeltexte sind korrekt. Insbesondere Vorteil/Nachteil, Gelegenheitsangriffe, Deckung, schwieriges Gelände, Konzentration, Rasten und mehrere Zustände liegen im Bestand mit den entscheidenden 2024-Ausnahmen vor.

Der Server ist dennoch **nicht fachlich reif für externe Nutzertests**. Die größten Risiken liegen nicht überwiegend im Wortlaut der SRD-Quelle, sondern in Import, Auswahl und fachlicher Einordnung:

- Eine ausdrücklich als 2024 angefragte klammerlose Zustandsbezeichnung kann trotz vorhandener 2024-Regel die 2014-Fassung liefern.
- Gleichnamige Kern-, Glossar-, Zauber- und Monsterabschnitte werden als identischer Inhalt zusammengezogen. Dadurch wird etwa „Aktionen“ zu Monster-„Reaktionen“, und vollständige Regeln zu Bonusaktionen, temporären Trefferpunkten oder Todesrettungswürfen werden durch Kurzverweise verdrängt.
- Mehrere versprochene vollständige Steckbriefe sind objektiv beschädigt: Vier Zauber sind abgeschnitten oder enthalten Fremdtext; „Vampirbrut“ enthält die Angriffe des Unsichtbaren Pirschers; „Schild“ enthält nicht einmal seinen RK-Bonus.
- Die Build-Prüfung bestätigt klar unvollständige oder illegale Charaktere als `legal_soweit_pruefbar`, darunter Kämpfer 3 ohne Unterklasse, Stufe-1-Charaktere mit epischer Gabe und frei erfundene Waffenbeherrschungen.
- Abenteuer-, Setting- und Playtest-Quellen können geladen werden, obwohl der definierte Spielerumfang sie ausschließt; ihr Status wird im Suchschema nicht dauerhaft gespeichert.
- RAW, offizielle Klarstellung, Errata, RAI-Ableitung, verbreitete Praxis und Spielleitungsentscheidung sind weder im Datenmodell noch im Antwortvertrag sauber unterscheidbar.

Diese Review dokumentiert **3 kritische, 9 hohe, 5 mittlere und 1 niedrige** Feststellung. Die fachliche MVP-Reife wird insgesamt mit **4/10** bewertet. Vor weiteren externen Spieltests müssen mindestens Versionsfallback, kontextbezogene Auswahl, beschädigte Inhalte und falsche Build-Positivurteile behoben und durch Realbestands-Regressionstests abgesichert werden.

## 3. Untersuchungsumfang und Vorgehen

Geprüft wurden alle fachlich relevanten Projektteile außerhalb von `docs/reviews`, insbesondere:

- Zielbild und Scope in `README.md`, `docs/foliant-anforderungen.md`, `docs/CLAUDE-PROJEKT-ANWEISUNG.md`, `docs/ABNAHME-PROTOKOLL.md`, `docs/MVP-ABGLEICH-UND-ROADMAP.md`, `docs/ATTRIBUTION.md` und den Importanleitungen;
- Server- und Antwortinstruktionen in `config/stil.py` und `app/server.py`;
- Nachschlage-, Glossar- und Charakterbau-Tools in `app/tools/`;
- Datenmodell, Suche, Editionsfilter, Dublettenlogik und Importer in `db/`, `app/db.py` und `importer/`;
- D&D-bezogene Tests, Fixtures, Smoke-Test und vorhandene öffentliche/private SQLite-Bestände;
- einfache Grundregeln, typische Spielerfragen, Versionsunterschiede, Zustände, Aktionsökonomie, Bewegung, Schaden/Tod, Magie, Monster, Gegenstände, Waffenmeisterschaften und Charaktererschaffung.

Die fachliche Methode kombinierte vier Ebenen:

1. **Scope-Abgleich:** Was verspricht das Projekt und was schließt es aus?
2. **Bestandsprüfung:** Welche Quellen, Versionen und Inhaltsarten sind tatsächlich vorhanden?
3. **Regelstichprobe:** Stimmen zentrale 2024-Regeln und wichtige Ausnahmen in den gespeicherten Texten?
4. **Antwortpfadprüfung:** Liefert eine realistische Nutzerformulierung tatsächlich den richtigen, vollständigen und versionsreinen Eintrag?

Der vierte Schritt war entscheidend: Ein korrekter Text in der Datenbank genügt fachlich nicht, wenn das Tool bei der natürlichen Spielerfrage einen anderen Abschnitt, eine alte Fassung oder ein beschädigtes Fragment auswählt.

## 4. Erkannter Regelumfang des Projekts

Der beanspruchte MVP-Umfang ist in `docs/foliant-anforderungen.md:45-75` und `README.md:3-7` breit:

- Regelrecherche für Kampf und Nichtkampf;
- vollständige Steckbriefe für Zauber, Monster und Gegenstände;
- deutschsprachige, quellen- und editionsbelegte Antworten;
- Charaktererstellung mit Klassen, Unterklassen, Hintergründen, Spezies, Talenten, Standard-Array, Point Buy und automatischer Build-Prüfung;
- PDF-, D&D-Beyond- und Open5e-Import in einen gemeinsamen Bestand;
- 2024 als Standard, 2014 nur ausdrücklich getrennt und markiert.

Ausdrücklich nicht im MVP sind laut `docs/foliant-anforderungen.md:155-170`:

- Kampagnen-/Abenteuerinhalte und Spoilerverwaltung;
- Spieler-/Spielleiter-Rollen und getrennte Zugänge;
- Hausregeln-Overlay;
- DDB-Charakterimport, Würfel- und Initiativwerkzeuge.

Tatsächlich implementiert sind 16 MCP-Tools: Suche und Details für Regeln/Zauber/Monster/Gegenstände, Glossar, Listen und Details für Charakteroptionen, Attributsmethoden sowie Build-Prüfung. Die Tools liefern Rohbestand und Steuerhinweise; die eigentliche natürlichsprachige Antwort erzeugt erst das verbundene Modell. Damit umfasst das fachliche Produkt sowohl Datenqualität als auch Retrieval, Instruktionen und Modellverhalten.

## 5. Erkannte D&D-Versionen und Quellen

### Lokaler öffentlicher Bestand

| Quelle | Edition | Lizenzkennzeichnung | Einträge | Fachliche Rolle |
|---|---:|---|---:|---|
| SRD 5.2.1 (Deutsch) | 2024 | CC-BY-4.0 | 1.639 | Primäre deutsche Regel- und Terminologiequelle |
| System Reference Document 5.2 (Open5e) | 2024 | `CC-BY-4.0 / OGL` | 982 | Englischer Ergänzungsbestand mit geringerer Priorität |

Gesamt: 2.621 Einträge, ausschließlich Edition 2024. Kategorien: 726 Zauber, 717 Gegenstände, 672 Monster, 354 Regeln, 79 Klassenabschnitte, 36 Talentabschnitte, 23 Speziesabschnitte und 14 Hintergrundabschnitte. Es wurden keine Abweichungen zwischen Quellenedition und Eintragsedition gefunden.

### Vorhandener privater Kandidatenbestand

| Quelle | Edition | Status | Einträge |
|---|---:|---|---:|
| SRD 5.2.1 (Deutsch) | 2024 | frei lizenziert | 1.639 |
| Basic Rules (2014), D&D Beyond | 2014 | privat | 1.609 |
| D&D Beyond Basic Rules | 2024 | privat | 2.237 |
| Player's Handbook, D&D Beyond | 2024 | privat | 1.605 |
| Ravenloft: The Horrors Within, D&D Beyond | 2024 | privat; Abenteuer-/Settingbezug | 807 |
| System Reference Document 5.2 (Open5e) | 2024 | frei lizenziert | 982 |

Gesamt: 8.879 Einträge, davon 1.609 mit Edition 2014 und 7.270 mit Edition 2024. Auch hier wurden keine formalen Quellen-/Eintragseditionsabweichungen gefunden.

Nicht beobachtet wurden echte Einträge aus älteren D&D-Editionen vor 2014 oder eindeutig als UA/Playtest markierte Einträge. Das Importsystem ist jedoch ausdrücklich darauf vorbereitet, Playtest-Bücher mitzuladen, ohne diesen Status im späteren Suchschema zu erhalten. Drittanbieterregeln und Hausregeln sind ebenfalls nicht als eigene Autoritätsklassen modelliert. `edition` ist entgegen der Anforderung V7 nur ein freies Textfeld; Errata-, Druck- und Revisionsstand fehlen.

## 6. Fachliche Stärken

1. **Klarer 2024-Standard:** `app/db.py:29` und alle Charakterwerkzeuge setzen 2024 als Standard. Bei vielen exakt benannten Regeln trennt die Suche 2014 und 2024 korrekt.
2. **Gute Primärbasis:** Das deutsche SRD 5.2.1 und das englische SRD 5.2 sind hochwertige Ausgangsquellen. Der private Bestand ergänzt Basic Rules und Player's Handbook 2024.
3. **Provenienz im Normalfall:** Detailantworten führen Quelle, Seite soweit vorhanden, Edition und Lizenz mit. Die formale Edition ist in beiden geprüften Datenbanken vollständig und quellenkonsistent.
4. **Viele korrekte Kernregeln:** Stichproben zu Vorteil/Nachteil, Gelegenheitsangriff, Initiative/Überraschung, Deckung, schwierigem Gelände, Unsichtbarkeit, Konzentration, kurzer/langer Rast und mehreren Zuständen enthielten die wesentlichen 2024-Regeln und Ausnahmen.
5. **Deutsch-first-Grundidee:** Deutsche Quellen haben Vorrang; englische Originalbegriffe und die Herkunft offizieller Übersetzungen werden mitgeführt.
6. **Ehrliche Leerfälle:** Leere Suchen weisen das Modell ausdrücklich an, fehlendes Wissen nicht aus Trainingswissen oder 2014-Erinnerungen zu ergänzen.
7. **Teilweise transparente Build-Grenzen:** Die Build-Ausgabe nennt nicht geprüfte Bereiche wie Zauberlisten, Mehrklassen und Talentvoraussetzungen. Standard-Array, Point-Buy-Kosten und die geprüften Hintergrundsverteilungen sind korrekt hinterlegt.
8. **Breite technische Regression:** Der vollständige lokale Testlauf ist schnell und stabil. Die fachlichen Fehler entstehen nicht aus allgemeiner Instabilität, sondern aus noch fehlenden semantischen Abnahmekriterien.

## 7. Kritische und hohe Regelprobleme

### DND-001: 2024-Zustandsfragen fallen auf 2014 zurück

- **Schweregrad:** Kritisch
- **Regelbereich:** Zustände; Regelversionen
- **Datei/Stelle:** `app/tools/nachschlagen.py:218-245`; Namensvergleich in `app/tools/nachschlagen.py:156-166`; `data/private/foliant-private.sqlite`
- **Vorhandene Struktur:** 2024-Zustände heißen im deutschen SRD etwa `Erschöpfung (Zustand)`, `Gepackt (Zustand)` und `Unsichtbar (Zustand)`. Die englischen 2014-Einträge heißen schlicht `Exhaustion`, `Grappled` und `Invisible`.
- **Fachliches Problem:** `foliant_hol_regel("Erschöpfung", edition="2024")` liefert reproduzierbar den englischen 2014-Eintrag und behauptet, es gebe keine 2024-Fassung. Dasselbe trat bei allen 15 klammerlos geprüften Zuständen auf. Mit dem vollständigen Namen samt `(Zustand)` wird 2024 korrekt gefunden.
- **Auswirkung:** Die Antwort kann eine inhaltlich andere Regelversion ausgeben. Besonders gravierend ist Erschöpfung: 2014 nutzt eine Stufentabelle mit unterschiedlichen Effekten, 2024 einen kumulativen Malus auf W20-Prüfungen und Bewegungsrate. Auch Gepackt und Unsichtbar unterscheiden sich relevant.
- **Korrektes Vorgehen:** Kontrollierte Aliasse für den Klammerzusatz als exakte semantische Namen behandeln; gewünschte Edition vor dem Altstand-Fallback auflösen; Altstand nur liefern, wenn wirklich kein semantisch passender 2024-Eintrag existiert.
- **Version/Quelle:** 2024, SRD 5.2.1 DE, Regelglossar S. 206-219; kontrastierend Basic Rules 2014.
- **Beispielfrage:** „Welche Nachteile habe ich bei zwei Stufen Erschöpfung nach den 2024-Regeln?“
- **Einordnung:** Eindeutiger Retrieval- und Versionsfehler, keine vertretbare Regelauslegung.

### DND-002: Namens-Deduplizierung und fuzzy Glossar zerstören Regelkontext

- **Schweregrad:** Kritisch
- **Regelbereich:** Aktionsökonomie; Trefferpunkte; Tod; allgemeine Regelrecherche
- **Datei/Stelle:** `app/glossar.py:48-90`; `app/db.py:240-307`; `app/tools/nachschlagen.py:218-265`; öffentlicher DB-Bestand
- **Vorhandene Struktur:** Dedupliziert wird nach normalisiertem Namen, Edition und Kategorie. Kontext, Abschnittspfad, Seite und Inhalt sind kein Identitätsmerkmal. Fuzzy Glossartreffer werden außerdem als Namensalternativen in den Exaktvergleich übernommen.
- **Fachliches Problem:** „Aktionen“ wird fuzzy als „Reaktionen“ interpretiert und liefert Monster-Reaktionen S. 299. „Bonusaktionen“ und „Reaktionen“ liefern ebenfalls die Monster-Kurztexte statt der Spielerregeln S. 11. Von 22 mehrfach vorhandenen Regeltiteln wählt das Detailtool häufig einen Kurzverweis oder fachfremden Kontext. „Temporäre Trefferpunkte“ liefert 235 Zeichen S. 216 statt 1.742 Zeichen S. 20; „Todesrettungswurf“ nur einen Ein-Satz-Verweis; „Bewegungsrate“ den Monster-Wertekasten statt die Bewegungsregel.
- **Auswirkung:** Das als „vollständiger Text“ beschriebene Tool verschweigt zentrale Ausnahmen oder beantwortet eine andere Frage. So fehlen bei temporären TP Nichtstapelbarkeit und Verhalten bei 0 TP, bei Todesrettungswürfen SG, Erfolge/Misserfolge, natürliche 1/20 und Schaden bei 0.
- **Korrektes Vorgehen:** Intra-Quellen-Abschnitte nicht allein wegen gleichen Namens deduplizieren; stabile Eintrags-ID und Kontext im Suchtreffer ausgeben; Detailabruf per ID ermöglichen; fuzzy Treffer nie als Identitätsbeweis verwenden; Kernabschnitt priorisieren oder passende Teilabschnitte transparent aggregieren.
- **Version/Quelle:** 2024, SRD 5.2.1 DE S. 10-20 und Regelglossar S. 203-220; Monsterkontext S. 295-299.
- **Beispielfrage:** „Kann ich meine Aktion in eine zweite Bonusaktion umwandeln?“
- **Einordnung:** Eindeutiger Auswahlfehler. Eine Rückfrage wäre bei echter Mehrdeutigkeit vertretbar; die derzeitige stille Falschauswahl ist es nicht.

### DND-003: Versprochene vollständige Steckbriefe sind teilweise objektiv falsch

- **Schweregrad:** Kritisch
- **Regelbereich:** Zauber, Monster, Gegenstände
- **Datei/Stelle:** `data/foliant.sqlite` Einträge 1428, 1490, 1640, 1718, 2499; `app/db.py:240-287`; `app/tools/nachschlagen.py:270-297`
- **Vorhandene Struktur:** Die deutsche Quelle gewinnt allein über Quellenpriorität, auch wenn ihr Chunk unvollständig ist. Die Metatabellen `zauber_meta`, `monster_meta` und `gegenstand_meta` sind in beiden geprüften Datenbanken leer.
- **Fachliches Problem:** `Eissturm` enthält nur Kopf und Zeitaufwand, `Göttliche Gunst` einen fremden Schlusssatz, `Symbol` nur den Kopf und `Windwall` nur den Schluss. `Vampirbrut` enthält Mehrfachangriff, Windstreich und Wirbel des Unsichtbaren Pirschers. `Schild` liefert lediglich den Satz zur Schildvertrautheit, aber keinen vollständigen Gegenstandssteckbrief und keinen RK-Bonus.
- **Auswirkung:** Das System kann bei einer Kernfunktion vollständig falsche Kreaturenaktionen oder unbrauchbare Zauber-/Gegenstandsantworten ausgeben. Bei `Göttliche Gunst` besteht zusätzlich akute Versionsgefahr: 2024 verlangt keine Konzentration, 2014 schon.
- **Korrektes Vorgehen:** Pro Inhaltsart fachliche Pflichtfelder und Vollständigkeitsschwellen validieren; beschädigte Chunks quarantänisieren; bei gleicher Edition auf eine vollständige Primär-/Sekundärquelle zurückfallen und die Abweichung offenlegen; Importgrenzen fachlich testen.
- **Version/Quelle:** 2024, SRD 5.2.1 DE S. 134, 149, 178, 198, 381 und 104; englisches SRD 5.2 beziehungsweise DDB Basic Rules 2024 als vorhandene Gegenprobe.
- **Beispielfrage:** „Gib mir den vollständigen 2024-Statblock der Vampirbrut.“
- **Einordnung:** Eindeutige Datenkorruption, keine Interpretation.

### DND-004: Importgrenzen verschmelzen fachlich unabhängige Regeln

- **Schweregrad:** Hoch
- **Regelbereich:** Attributswürfe; soziale Interaktion; Waffenmeisterschaften; weitere Grundregeln
- **Datei/Stelle:** `importer/import_markdown.py:50-77`; DB-Eintrag 1746 `Attributswurf`; DB-Eintrag 1179 `Zweihändig`
- **Vorhandene Struktur:** PDF-Überschriften und Spalten werden in freie Markdown-Chunks zerlegt, ohne semantische Grenzprüfung.
- **Fachliches Problem:** `Attributswurf` enthält nach der allgemeinen Definition fälschlich die speziellen Abschnitte „Nicht bereitwillig“ und „Zögerlich“ der Beeinflussen-Aktion einschließlich SG 15 beziehungsweise Intelligenzwert. Umgekehrt fehlt dieser Teil bei `Beeinflussen (Aktion)`. `Zweihändig` enthält zusätzlich den kompletten Meisterschaftseffekt `Umstoßen` mit Konstitutionsrettungswurf und Liegend. Weitere Stichproben fanden „Marschreihenfolge“ unter Gegenstandsinteraktion, „Rasten“ unter Schadenswürfen und Bewusstlosmachen mitten im Heilungsabschnitt.
- **Auswirkung:** Das Modell kann einen Spezial-SG als allgemeine Attributswurfregel oder Umstoßen als automatische Eigenschaft jeder zweihändigen Waffe darstellen.
- **Korrektes Vorgehen:** Seiten-/Spaltenreihenfolge fachlich korrigieren; Boundary-Invarianten und erwartete Teilüberschriften pro Kernabschnitt testen; kontaminierte Chunks neu importieren; Meisterschaft und Waffeneigenschaft als getrennte Konzepte speichern.
- **Version/Quelle:** 2024, SRD 5.2.1 DE S. 6, 103 und Regelglossar S. 204.
- **Beispielfrage:** „Ist der SG jedes Attributswurfs mindestens 15 oder der Intelligenzwert des Ziels?“
- **Einordnung:** Die falsche Zuordnung ist eindeutig. Der konkrete SG einer offenen Herausforderung bleibt ansonsten eine Regel- oder SL-Festlegung.

### DND-005: Build-Prüfung erteilt falsche Legalitätsbestätigungen

- **Schweregrad:** Hoch
- **Regelbereich:** Charaktererschaffung; Talente; Unterklassen; Waffenbeherrschung
- **Datei/Stelle:** `app/tools/charakter.py:536-553`, `599-658`, `734-832`, `834-897`
- **Vorhandene Struktur:** Fehlende Hintergrundserhöhungen und Unterklassen werden nur geprüft, wenn ein Wert übergeben wurde. Talente erhalten bei bloßer Existenz Status `ok`. Waffenbeherrschung prüft nur Anzahl und Duplikate, nicht Waffenexistenz oder Zugangsberechtigung. Offene, absichtlich nicht geprüfte Punkte gelangen nicht zwingend in `nicht_pruefbar`.
- **Fachliches Problem:** Reproduzierbar erhalten alle folgenden Builds `legal_soweit_pruefbar` ohne offene Prüfpunkte: Kämpfer 1/Soldat/Mensch ohne Hintergrundserhöhungen; Kämpfer 3 ohne Unterklasse; Kämpfer 1 mit einer epischen Gabe ab Stufe 19; Kämpfer 1 mit drei erfundenen „Waffen“ (`Kartoffel`, `Teekanne`, `Mondstrahl`) als Waffenbeherrschungen.
- **Auswirkung:** Eine als automatische Regelkonformitätsprüfung beworbene Funktion bestätigt eindeutig illegale oder unvollständige Builds positiv.
- **Korrektes Vorgehen:** Ergebniszustände `valid`, `invalid`, `incomplete` und `unsupported` trennen; Pflichtentscheidungen aus der gewählten Klasse/Herkunft ableiten; Talentkategorie, Voraussetzung, Erwerbsquelle, Stufe und Wiederholbarkeit prüfen; reale Waffen und Meisterschaftszugang validieren. Bis dahin kein Legalitätsprädikat für nicht geprüfte Bereiche.
- **Version/Quelle:** 2024, SRD 5.2.1 DE S. 22-24, 55, 93 und 96-99; jeweilige Klassen-/Talenttexte.
- **Beispielfrage:** „Darf mein Kämpfer auf Stufe 1 die Gabe des Schicksals wählen?“
- **Einordnung:** Eindeutige RAW-Verstöße und unvollständige Builds, keine SL-Präferenz.

### DND-006: Charakterführung und Charakterdaten sind innerhalb des Anspruchs unvollständig

- **Schweregrad:** Hoch
- **Regelbereich:** Charaktererschaffung 2024
- **Datei/Stelle:** `app/tools/charakter.py:86-91`, `217-244`, `368-386`, `660-679`; DB-Einträge 1034, 1036, 1098, 1118
- **Vorhandene Struktur:** Das System behauptet vier Schritte `Klasse -> Hintergrund -> Spezies -> Details`. Spezies wird nur auf Existenz geprüft; Sprachen und Speziespflichtentscheidungen sind keine Eingabefelder. Aktuelle Attribute jeder Stufe werden weiter gegen den Start-Standardsatz/Point Buy geprüft.
- **Fachliches Problem:** Der importierte 2024-Regeltext nennt fünf Schritte: Klasse; Herkunft aus Hintergrund, Spezies und zwei Sprachen; Attribute; Gesinnung; Details. Mensch-Zusatzoption, Elfenabstammung/Zauberattribut und weitere Pflichtentscheidungen fehlen. Für Stufen 2-20 ist nicht zwischen Basisattributen, Herkunftserhöhungen und späteren ASI/Talenten unterschieden. Zusätzlich fehlen beim Eintrag `Krimineller` die Fertigkeitsübungen und beim Schurken die vollständige Fortschrittstabelle.
- **Auswirkung:** Geführte Charaktere können wesentliche Pflichtentscheidungen auslassen; gültige höherstufige Werte können abgelehnt und unentwickelte Stufe-20-Builds akzeptiert werden. Detailantworten zu Krimineller sind unvollständig.
- **Korrektes Vorgehen:** Offizielle fünf Schritte abbilden; Herkunft als Hintergrund+Spezies+zwei Sprachen modellieren; Speziesentscheidungen erfassen; Basiswerte, Herkunftserhöhungen und Stufenfortschritt trennen; Pflichtfeld-Gates für jeden Hintergrund und jede Klassentabelle einführen. Alternativ den Validator ehrlich auf Stufe 1 und einen engeren Teilumfang beschränken.
- **Version/Quelle:** 2024, SRD 5.2.1 DE S. 22-24, 79 und 93.
- **Beispielfrage:** „Führe mich vollständig durch einen neuen 2024-Charakter.“
- **Einordnung:** Die fehlenden RAW-Schritte/Felder sind eindeutig; Gesinnung und erzählerische Details bleiben inhaltlich frei wählbar.

### DND-007: Abenteuer-, Setting- und Playtest-Inhalte widersprechen dem Spieler-Scope

- **Schweregrad:** Hoch
- **Regelbereich:** Inhaltsumfang; Spoiler; Publikationsstatus
- **Datei/Stelle:** `docs/foliant-anforderungen.md:155-170`; `importer/ddb_exporter/katalog.py:7-13`, `87-107`; `db/schema.sql:5-28`; privater Bestand
- **Vorhandene Struktur:** Der verbindliche Scope schließt Abenteuer-/Kampagneninhalte aus. Der DDB-Katalog lädt Abenteuer-, Setting- und Playtest-Bücher dennoch bewusst und erzeugt nur einen flüchtigen Hinweis. Im privaten Bestand liegen 807 Einträge aus `Ravenloft: The Horrors Within` im selben Schema wie Spielerregeln.
- **Fachliches Problem:** `content_scope`, Zielgruppe, Spoilerrisiko und Publikationsstatus werden nicht in Quelle oder Eintrag gespeichert. Der spätere Suchpfad kann deshalb weder serverseitig sperren noch sicher zwischen Regeloption und Kampagnenwissen unterscheiden. Ein Playtest kann durch Editionsheuristik nur als `2014`/`2024` erscheinen.
- **Auswirkung:** Spieler können außerhalb des versprochenen Umfangs Lore-/Abenteuerinhalt erhalten; UA/Playtest kann wie finales RAW wirken. Die Prompt-Ablehnung ist kein Datenzugriffs- oder Statusschutz.
- **Korrektes Vorgehen:** Abenteuer/Setting/Playtest standardmäßig nicht in den Spielerbestand importieren. Alternativ Statusfelder `scope`, `audience`, `spoiler_risk`, `publication_status` dauerhaft speichern und vor Retrieval hart filtern.
- **Version/Quelle:** Versionsübergreifend; im geprüften Privatbestand 2024-Settingquelle. Publikationsstatus ist von Edition getrennt.
- **Beispielfrage:** „Wie besiege ich Strahd?“
- **Einordnung:** Der Scope-Widerspruch ist eindeutig; welche Abenteuerinformationen eine konkrete Runde zulässt, ist eine spätere Rollen-/SL-Entscheidung.

### DND-008: Edition allein beschreibt weder Autorität noch Gültigkeitsstand

- **Schweregrad:** Hoch
- **Regelbereich:** Versionen; optionale Regeln; UA; Drittanbieter; Hausregeln
- **Datei/Stelle:** `db/schema.sql:5-28`; `app/db.py:93-110`; `docs/foliant-anforderungen.md:117-131`
- **Vorhandene Struktur:** Quellen und Einträge speichern nur ein freies `edition`-Textfeld, Herkunft, Lizenz und Priorität. Die Projektdokumentation fordert dagegen ein strukturiertes erweiterbares Versionsschema.
- **Fachliches Problem:** Publisher/Autorität, final versus Playtest/UA, optional versus Kernregel, Legacy, Drittanbieter, Hausregel, Veröffentlichungsdatum, Erratum, Druckauflage und Ersetzungsbeziehung fehlen. Ein beliebiges PDF kann als `2024` mit hoher Priorität kanonisch werden. Auch das projektintern verwendete Alias `5.5e` wird als unbekannte Edition abgelehnt.
- **Auswirkung:** Gleiches Editionslabel kann fachlich sehr verschiedene Gültigkeit vortäuschen. Veraltete oder nicht finale Inhalte lassen sich nicht verlässlich erkennen oder standardmäßig ausschließen.
- **Korrektes Vorgehen:** Regel-Familie, Dokumentversion und Autoritätsstatus getrennt modellieren, etwa `rules_family=2024`, `status=official_final|official_optional|ua_playtest|third_party|homebrew`, Publisher, Veröffentlichungs-/Revisionsdatum und Ersetzungsbezug. Nutzeraliase nur auf kanonische Werte normalisieren.
- **Version/Quelle:** Alle; besonders 2014/2024, UA/Playtest und spätere Errata.
- **Beispielfrage:** „Ist diese UA-Unterklasse normales 2024-RAW?“
- **Einordnung:** Der Quellenstatus ist objektiv; die Zulassung von Playtest/Homebrew am Tisch ist eine SL-Entscheidung.

### DND-009: RAW, Klarstellung, Ableitung und SL-Entscheidung sind nicht trennbar

- **Schweregrad:** Hoch
- **Regelbereich:** Aussagearten; Regelauslegung
- **Datei/Stelle:** `config/stil.py:14-68`; `db/schema.sql:18-28`; `app/tools/nachschlagen.py:133-153`
- **Vorhandene Struktur:** Der Prompt nennt Auskünfte pauschal RAW. Das Detailtool liefert freien Regeltext, aber keine Aussageart oder Begründungskette.
- **Fachliches Problem:** Es gibt keine Struktur für wörtliche Regel, Zusammenfassung, logische Ableitung aus mehreren Regeln, Errata, offizielle Klarstellung, RAI-Indiz, verbreitete Praxis, mögliche Interpretation, DM-Ruling oder Hausregel. Ebenso fehlt ein Antwortvertrag, der diese Ebenen sichtbar trennt.
- **Auswirkung:** Eine plausible Modellsynthese kann als ausdrücklich niedergeschriebene RAW-Regel erscheinen. Umgekehrt kann eine offizielle Klarstellung als bloßer Web-Fallback abgewertet werden. Bei uneindeutigen Interaktionen wird mehr Sicherheit vorgetäuscht, als der Bestand hergibt.
- **Korrektes Vorgehen:** Aussageart und Quellenklasse modellieren; Antworten in `RAW`, `Ableitung`, `offizielle Klarstellung`, `offene Auslegung` und `SL-Entscheidung` gliedern; RAI nur attributiert und nie erfunden; Hausregeln separat und nur auf ausdrückliche Tischkonfiguration.
- **Version/Quelle:** Alle; Errata und Klarstellungen stets revisionsbezogen.
- **Beispielfrage:** „Muss ich für jedes Magische Geschoss einen eigenen Konzentrationswurf machen, oder ist das eine gleichzeitige Schadensinstanz?“
- **Einordnung:** Dass die Texte keine eindeutige gemeinsame Antwort erzwingen, ist die relevante fachliche Aussage; die Tischentscheidung ist interpretationsabhängig.

### DND-010: Open5e-Import verwirft regelentscheidende Felder

- **Schweregrad:** Hoch
- **Regelbereich:** Reaktionszauber; Monsteraktionen und -formen
- **Datei/Stelle:** `importer/import_open5e.py:76-101`, `104-152`; Open5e-v2-Fixtures
- **Vorhandene Struktur:** Zauberformatierung übernimmt Zeitaufwand, Reichweite, Komponenten, Dauer und Text, aber nicht `reaction_condition`. Monsterformatierung gruppiert Aktionen, verwirft aber unter anderem `limited_to_form`, `usage_limits`, `legendary_action_cost`, Reihenfolge und `initiative_bonus`.
- **Fachliches Problem:** Gegenzauber/Schild/Federfall können ihren konkreten Reaktionstrigger verlieren. Beim Vampir fehlen Formbeschränkungen, Aufladung 5-6 und Initiativebonus. Die synthetische Prüfung ergab `TRIGGER_KEPT=False`, `FORM_LIMIT_KEPT=False`, `RECHARGE_KEPT=False`, `INITIATIVE_KEPT=False`.
- **Auswirkung:** Ein Trigger kann zu weit erlaubt oder eine Monsterfähigkeit zu oft beziehungsweise in falscher Gestalt eingesetzt werden. Der Steckbrief ist nicht vollständig.
- **Korrektes Vorgehen:** Alle regelentscheidenden strukturierten Felder erhalten und in lesbaren Text überführen; Pflichtfeldtests pro Reaktionszauber/Monsteraktion; bei nicht unterstützten Feldern Import ablehnen oder Eintrag als unvollständig markieren.
- **Version/Quelle:** 2024, englisches SRD 5.2 über Open5e; Gegenzauber/Schild und Vampir als Reproduktionsfälle.
- **Beispielfrage:** „Kann ein Vampir in Nebelgestalt Grabesschlag einsetzen und Bezaubern in jedem Zug benutzen?“
- **Einordnung:** Eindeutiger Informationsverlust; Anwendung der erhaltenen Bedingungen ist RAW.

### DND-011: Echte Primärquellenkonflikte werden still verdeckt

- **Schweregrad:** Hoch
- **Regelbereich:** Quellenkonflikt; Übersetzung
- **Datei/Stelle:** `app/db.py:240-287`; DB-Eintrag 2501 `Vampir`; Open5e-Eintrag 688
- **Vorhandene Struktur:** Gleichnamige Inhalte derselben Edition/Kategorie werden als Dublette gruppiert; die kleinste Quellenpriorität gewinnt. Andere Quellen erscheinen höchstens als Titel, nicht als abweichender Inhalt.
- **Fachliches Problem:** Das visuell geprüfte deutsche SRD 5.2.1 S. 382 sagt, das Ziel wisse nach Ende, dass der Vampir es bezaubert hat. Englisches SRD 5.2, DDB Basic Rules und Open5e sagen, das Ziel sei sich dessen nicht bewusst. Das System priorisiert Deutsch still.
- **Auswirkung:** Eine scheinbar eindeutige Antwort hängt tatsächlich von einem widersprüchlichen offiziellen Sprachstand ab. Dasselbe Verfahren kann weitere Übersetzungs-, Errata- oder Revisionsunterschiede verbergen.
- **Korrektes Vorgehen:** Nur tatsächlich identische Fassungen deduplizieren; Text-/Revisionsabweichungen als Konflikt ausgeben; verbindliche Original-/Errata-Policy festlegen; bis zur Klärung beide Aussagen paraphrasiert und die nötige SL-/Quellenentscheidung nennen.
- **Version/Quelle:** Beide 2024; deutsches SRD 5.2.1 S. 382 versus englisches SRD 5.2/DDB Basic Rules `Vampire`.
- **Beispielfrage:** „Weiß das Ziel danach, dass der Vampir es bezaubert hat?“
- **Einordnung:** Der Quellenwiderspruch ist eindeutig; seine normative Auflösung ist policy- beziehungsweise errataabhängig.

### DND-012: Grüne Tests geben keine fachliche Freigabe

- **Schweregrad:** Hoch
- **Regelbereich:** Fachliche Qualitätssicherung; Antwortverhalten
- **Datei/Stelle:** `tests/test_abnahme.py:240-300`, besonders T10 in `271-273`; `tests/smoke_test.py`; fachliche Fixture-Tests
- **Vorhandene Struktur:** Der vollständige Lauf besteht mit 98 Tests. T10 zur Spoilerablehnung ist übersprungen; T12 prüft nur Serverhinweise, nicht das Modellverhalten. Smoke-Tests prüfen überwiegend Auffindbarkeit und Struktur.
- **Fachliches Problem:** Alle kritischen Realbestandsfehler dieser Review bestehen trotz grüner Tests. Es fehlen semantische Assertions zu Kernklauseln, Kontext, Vollständigkeit und 2014/2024-Unterschieden. Es gibt keine echten Client-/Modell-Evals für Quellenzeile, Nichtwissen, Mehrdeutigkeit, Rückfragen, Spoiler, RAW/Ableitung oder SL-Ruling.
- **Auswirkung:** Ein grüner CI-Lauf kann eine fachlich falsche Version, einen falschen Monster-Statblock und falsche Build-Legalität freigeben.
- **Korrektes Vorgehen:** Read-only Realbestands-Contracttests mit erwarteten Regelklauseln und ausgeschlossenen Fremdklauseln; Goldfragen für Interaktionen; Ende-zu-Ende-Modell-Evals mit wiederholbaren Kriterien; manuelle Tests nicht als bestanden darstellen.
- **Version/Quelle:** Schwerpunkt 2024, plus explizite 2014-Gegenproben.
- **Beispielfrage:** „Braucht Göttliche Gunst 2024 Konzentration?“
- **Einordnung:** Eindeutige Testabdeckungslücke.

## 8. Mittlere und niedrige Regelprobleme

### DND-013: Natürliche Spielerformulierungen und Tool-Kategorien führen häufig am Ziel vorbei

- **Schweregrad:** Mittel
- **Regelbereich:** Suche; Terminologie; Magiegrundregeln
- **Datei/Stelle:** `app/db.py:74-78`, `289-378`; `importer/import_markdown.py:64-76`; `app/tools/nachschlagen.py:60-107`
- **Vorhandene Struktur:** FTS tokenisiert die ganze Frage; Glossar und fuzzy Namen dienen als Fallback. Das gesamte Kapitel „Zauber“ wird als Kategorie `zauber` importiert, auch wenn es sich um allgemeine Regeln handelt.
- **Fachliches Problem:** `Schubsen`, `Objektinteraktion`, `Unbewaffneter Schlag`, `Spirituelle Waffe` und `Mehrklassenbildung` finden erwartbare Einträge nicht oder nur unter anderer Terminologie. Ganze Fragen ranken teils irrelevante Treffer: schwieriges Gelände führt zu Beispielfallen; eine Langrast-Frage findet die 16-Stunden-Regel nicht. `foliant_hol_regel("Komponenten")` liefert Beispielfallen, während die richtige Komponentenregel fälschlich nur über `foliant_hol_zauber` erreichbar ist.
- **Auswirkung:** Das Modell erhält „nicht im Bestand“, einen falschen Kontext oder muss das falsche Detailtool erraten, obwohl die Regel vorhanden ist.
- **Korrektes Vorgehen:** Nutzerfrage in Konzepte zerlegen; kontrollierte Synonyme/Begriffsaliasse; allgemeine Magieregeln als `regel`; Kontext und Kategorie im Ranking; bei Mehrdeutigkeit Kandidaten statt stiller Annahme.
- **Version/Quelle:** 2024; SRD-Regelglossar und Zauberkapitel.
- **Beispielfrage:** „Welche Komponenten brauche ich zum Zaubern?“
- **Einordnung:** Auffindbarkeitsfehler eindeutig; einzelne Alltagssynonyme können eine Rückfrage erfordern.

### DND-014: Komplexe Wechselwirkungen haben keinen fachlichen Abruf- und Ableitungsprozess

- **Schweregrad:** Mittel
- **Regelbereich:** Specific beats general; Timing; Trigger; Ziele; Stapelung
- **Datei/Stelle:** `config/stil.py:14-68`; `db/schema.sql:18-28`
- **Vorhandene Struktur:** Regeln sind unabhängige Freitext-Chunks. Der Prompt fordert Quellengebrauch, aber nicht systematisch mehrere betroffene Regeln, spezifische vor allgemeiner Regel, Voraussetzungen, Gegenbeispiele oder Unsicherheitsmarkierung.
- **Fachliches Problem:** Es gibt keine Beziehungen für Ausnahme, ersetzt/modifiziert, Trigger, Zieltyp, Dauer, Beginn/Ende, einmal pro Zug oder Stapelung. Antworten wie Dissonantes Flüstern plus Gelegenheitsangriff, Unsichtbarkeit plus Wahre Sicht oder Konzentration plus gleichzeitige Geschosse hängen vollständig von spontaner Modellsynthese ab.
- **Auswirkung:** Der Einzeltext kann korrekt sein, während die zusammengesetzte Tischantwort eine wichtige Bedingung auslässt.
- **Korrektes Vorgehen:** Interaktionsprotokoll im Antwortvertrag: beteiligte Regeln ermitteln, Trigger/Voraussetzungen nennen, spezifische Klausel anwenden, Gegenbeispiel prüfen, Ergebnis als RAW-Text versus Ableitung kennzeichnen. Später gezielte Relationsmetadaten für häufige Interaktionen.
- **Version/Quelle:** Alle, besonders 2024-Regelglossar und Zauberkapitel.
- **Beispielfrage:** „Provoziert die durch Dissonantes Flüstern ausgelöste Bewegung einen Gelegenheitsangriff?“
- **Einordnung:** Das Fehlen des Prozesses ist eindeutig; die konkrete Schlussfolgerung kann eindeutig RAW-ableitbar oder auslegungsabhängig sein.

### DND-015: Lokaler Bestand und behaupteter Live-Bestand sind nicht fachlich gleich prüfbar

- **Schweregrad:** Mittel
- **Regelbereich:** Vollständigkeit; Traceability; Betriebsbestand
- **Datei/Stelle:** `README.md:17-21`; `data/foliant.sqlite`; `data/private/foliant-private.sqlite`; DDB-Artefakt-/Importpfad
- **Vorhandene Struktur:** README nennt rund 9.490 Einträge aus 12 Quellen. Lokal konfiguriert sind 2.621 Einträge aus zwei Quellen; die private Kandidaten-DB enthält 8.879 aus sechs Quellen. DDB-Artefakte besitzen Abschnittspfad, URL und Buchversion, doch das Suchschema übernimmt diese feingranulare Provenienz nicht vollständig.
- **Fachliches Problem:** Eine fachliche Vollständigkeitsfreigabe des tatsächlich live bedienten Korpus ist aus dem Repository nicht reproduzierbar. Seitenlose DDB-Einträge lassen sich nur bis zum Buchtitel, nicht stabil bis Abschnitt/Revision zurückverfolgen.
- **Auswirkung:** Lokale Tests können andere Quellenprioritäten, Optionen und Konflikte sehen als die Runde. Ein später korrigierter DDB-/Errata-Stand ist nicht sicher identifizierbar.
- **Korrektes Vorgehen:** Reproduzierbares, nicht geheimes Quellenmanifest mit Anzahl, Hash, Revision und fachlichem Status; Produktions-QS gegen denselben Manifeststand; DDB-Breadcrumb, stabile URL/ID und Buchversion bis zur Antwort erhalten.
- **Version/Quelle:** Alle vorhandenen Quellenstände.
- **Beispielfrage:** „Aus welchem konkreten Abschnitt und welchem Revisionsstand stammt diese Regel?“
- **Einordnung:** Nachvollziehbarkeitslücke eindeutig; die Live-Daten selbst konnten nicht bewertet werden.

### DND-016: Private Volltextausgabe erzeugt ein erkennbares Inhalts- und Lizenzrisiko

- **Schweregrad:** Mittel
- **Regelbereich:** Urheberrecht; Inhaltsumfang
- **Datei/Stelle:** `app/tools/nachschlagen.py:133-153`, `270-309`; `docs/ATTRIBUTION.md:3-16`; private DDB-Datenbank
- **Vorhandene Struktur:** Detailtools geben vollständige gespeicherte Abschnitte, Zauber, Statblocks und Gegenstände als `regeltext_md` aus. Für CC-BY wird Attribution erzeugt; DDB-Quellen sind lediglich als `privat` markiert.
- **Fachliches Problem:** Sobald der private Bestand bedient wird, existiert keine quellenabhängige Ausgabebegrenzung, keine technische Unterscheidung zwischen kurzer Begründung und umfangreicher Volltextreproduktion und keine erkennbare Berechtigungsprüfung pro Inhaltsquelle.
- **Auswirkung:** Eine gruppenweite oder öffentliche Volltextbereitstellung gekaufter PHB-/DDB-Inhalte kann urheber- oder vertragsrechtliche Risiken schaffen. Das ist besonders relevant, weil der Toolvertrag ausdrücklich „vollständig“ fordert.
- **Korrektes Vorgehen:** Private Quellen streng zugangsbeschränkt; standardmäßig eigenständige Zusammenfassung mit nur notwendigem kurzen Beleg; CC-/OGL-Pflichten pro Quelle korrekt ausgeben; DDB-Nutzungsbedingungen und Gruppenfreigabe gesondert prüfen.
- **Version/Quelle:** Lizenzabhängig, nicht editionsabhängig.
- **Beispielfrage:** „Gib mir das komplette private PHB-Kapitel zu Talenten aus.“
- **Einordnung:** Das technische Risiko ist eindeutig; die konkrete rechtliche Zulässigkeit ist nicht Gegenstand dieser Review.

### DND-017: Unterstützungsgrenzen werden fachlich inkonsistent dargestellt

- **Schweregrad:** Mittel
- **Regelbereich:** Charakterwerte; Mehrklassen; Versionsalias
- **Datei/Stelle:** `app/tools/charakter.py:368-404`, `536-553`; `app/db.py:99-110`
- **Vorhandene Struktur:** Das Spezialtool akzeptiert nur Standard-Array und Point Buy. Die Grenzen nennen Zufallserstellung als nicht validierbar, geben deren Regel aber nicht aus. Mehrklassen ist ungeprüft; `5.5e` wird abgelehnt, obwohl die eigene Anforderung diese Bezeichnung verwendet.
- **Fachliches Problem:** 2024 kennt als dritte Attributsmethode sechsmal 4W6 mit Verwerfen des niedrigsten Würfels. Nicht validierbar ist nicht gleich nicht vorhanden. Mehrklassen- und Versionsfragen wirken wie Fehlbestand, obwohl Regeln beziehungsweise Aliasse vorhanden sind.
- **Auswirkung:** Wissensfragen werden unnötig verengt; ein ungeprüfter Mehrklassen-Build kann zugleich ein positives Gesamtprädikat erhalten.
- **Korrektes Vorgehen:** `random_generation` als offizielle, aber nicht automatisch validierbare Methode ausgeben; ungeprüfte Mehrklassen immer in `unsupported/nicht_pruefbar` abbilden; Aliasse normalisieren.
- **Version/Quelle:** 2024, SRD 5.2.1 DE S. 24 und 28.
- **Beispielfrage:** „Welche drei offiziellen Methoden gibt es 2024 für Attributswerte?“
- **Einordnung:** Der Regelumfang ist eindeutig; Zufallsergebnisse selbst sind naturgemäß nicht im Voraus validierbar.

### DND-018: Das Darstellungsformat ist nicht ausreichend auf Spielerfragen abgestimmt

- **Schweregrad:** Niedrig
- **Regelbereich:** Verständlichkeit; Antwortökonomie
- **Datei/Stelle:** `config/stil.py:36-53`; `docs/foliant-anforderungen.md:82-111`
- **Vorhandene Struktur:** Das englische Original soll bei jeder Nennung wiederholt werden; jede Regelauskunft folgt demselben Emoji-/Belegformat. Kurze und ausführliche Antwortmodi sind nicht definiert.
- **Fachliches Problem:** Wiederholte Klammerbegriffe belasten längere Interaktionsantworten und können die eigentliche Kernaussage verdecken. Das System fordert „kompakt“, definiert aber nicht „Kurzantwort zuerst, dann Ausnahmen/Begründung“.
- **Auswirkung:** Selbst korrekte Antworten können am Spieltisch langsamer erfassbar sein.
- **Korrektes Vorgehen:** Originalbegriff bei erster Nennung und bei echter Begriffsklärung; direkte Ja/Nein-/Bedingt-Antwort zuerst; danach Kernregel, wichtige Ausnahme, Beispiel und Beleg. Ausführlichkeit an Nutzerfrage anpassen.
- **Version/Quelle:** Nicht editionsabhängig.
- **Beispielfrage:** „Kann ich hier einen Gelegenheitsangriff machen?“
- **Einordnung:** Niedrige Usability-Frage, keine falsche Regel und keine verbindliche Spielstilpräferenz.

## 9. Vermischung oder Unklarheit von Regelversionen

Die formale Basis ist besser als bei vielen Regelassistenten: `edition` ist Pflicht, 2024 ist Standard, 2014 wird in der normalen Suche getrennt als Altstand ausgegeben, und die geprüften Datenbanken enthalten keine leeren oder zwischen Quelle und Eintrag abweichenden Editionswerte. Direkte Detailproben mit exakt übereinstimmenden Namen wie `Counterspell`, `Grapple`, `Surprise` und `Multiclassing` konnten 2014 und 2024 getrennt liefern.

Diese Stärke reicht fachlich noch nicht:

| Problem | Beobachtung | Risiko |
|---|---|---|
| Semantischer Alias fehlt | `Erschöpfung` 2024 fällt auf `Exhaustion` 2014 zurück, weil der 2024-Name `(Zustand)` enthält. | Unmarkiert falscher Regelinhalt trotz korrektem Editionsparameter. |
| Edition ist nur Text | `2024`, `2014`, Projektbegriff `5.5e`, Errata und Druckstand sind nicht strukturiert. | Aliasse werden abgelehnt; Revisionen sind nicht vergleichbar. |
| Status fehlt | Playtest/UA, optional, Drittanbieter, Homebrew und finales offizielles Material sind nicht unterscheidbar. | Ein Eintrag kann als offizielles RAW erscheinen, obwohl nur die Jahresfamilie bekannt ist. |
| Quellenkonflikte verschwinden | Gleiches Editionslabel und gleicher Name gelten als Dublette. | Übersetzungs- oder Errataunterschiede werden durch Priorität verdeckt. |
| Terminologie ist editionsübergreifend | Ältere offizielle deutsche Begriffe dürfen absichtlich für 2024 genutzt werden. | Fachlich vertretbar, aber fuzzy Begriffssuche darf daraus keine Regelidentität oder Altstandsauswahl ableiten. |

**Urteil:** 2014 und 2024 sind im Datenmodell nominell getrennt, aber die tatsächliche Antwort ist nicht zuverlässig versionsrein. Edition, Dokumentrevision und Autoritätsstatus müssen getrennte Dimensionen werden.

## 10. Bewertung von Quellen und Nachvollziehbarkeit

### Positiv

- Das deutsche SRD 5.2.1 und das englische SRD 5.2 sind primäre, fachlich geeignete Regelquellen.
- Quelle, Edition und Seite soweit vorhanden werden im normalen Detailpfad sichtbar ausgegeben.
- CC-BY-Attribution wird in Detailantworten mitgeführt.
- Der öffentliche Bestand ist frei von formalen Quellen-/Eintragseditionskonflikten.
- DDB-Inhalte sind im Repository grundsätzlich als privat gekennzeichnet und von der öffentlichen Datenbank getrennt.

### Unzureichend

- Quellenpriorität wird als Stellvertreter für inhaltliche Richtigkeit und Vollständigkeit verwendet. Ein beschädigter deutscher Chunk gewinnt gegen einen vollständigen englischen derselben Edition.
- `weitere_quellen` nennt nur Titel; es zeigt weder abweichenden Wortlaut noch Abschnitt, Revision oder Konfliktgrund.
- DDB-Breadcrumb, stabile Abschnitts-ID/URL und Buchversion erreichen die Toolantwort nicht vollständig.
- Open5e ist ein Vermittler des SRD-Inhalts, wird aber im Lizenzfeld pauschal als `CC-BY-4.0 / OGL` bezeichnet. Die konkrete Lizenz sollte dokumentbezogen und nicht als Sammellabel geführt werden.
- Seitenzahlen beziehen sich auf die konkrete importierte PDF-Ausgabe, doch Ausgabe-/Revisionsstand fehlt. Für DDB-Inhalte ohne Seite ist die Fundstelle zu grob.
- Die deutsch/englische Vampir-Abweichung beweist, dass Primärquellen gleicher Edition nicht immer textgleich sind. Eine Prioritätsliste ersetzt keine Konfliktprüfung.
- Das System besitzt keinen belegbaren Korpus für Errata, Sage-Advice-ähnliche offizielle Klarstellungen oder sonstige Sekundärquellen und kann deren Autorität daher nicht ausdrücken.

**Urteil:** Die Quellenqualität ist überwiegend hoch, die Nachvollziehbarkeit bis zum Dokument aber nur teilweise belastbar. Bis zum konkreten Abschnitt, Revisionsstand und zur Aussageart reicht sie nicht.

## 11. Bewertung von Regelausnahmen und Wechselwirkungen

Viele benötigte Einzelklauseln sind im SRD vorhanden. Das betrifft unter anderem:

- „specific beats general“ als grundlegende Leseregel;
- Reaktionstrigger und Rückgewinnung der Reaktion;
- eigene Bewegung versus erzwungene Bewegung und Teleportation bei Gelegenheitsangriffen;
- Angriff, Angriffsaktion, Waffenangriff und Zauberwirkung;
- Konzentrationsbeginn, Konzentrationsende, Schadensrettungswurf und Höchst-SG;
- Sichtbarkeit, Unsichtbarkeit und besondere Sinne;
- Kreatur/Objekt als Ziel sowie Deckung relativ zum Ursprung eines Effekts;
- Resistenz, Verwundbarkeit, Immunität und Reihenfolge von Schadensmodifikatoren;
- gleichnamige Effekte, temporäre Trefferpunkte und Meisterschaftsstapelung;
- Beginn/Ende eines Zugs, „pro Zug“ und „in jedem deiner Züge“.

Die fachliche Schwäche liegt im Zusammenführen. Das Datenmodell enthält weder Beziehungen noch strukturierte Trigger, und der Prompt verlangt keinen nachvollziehbaren Mehrregelprozess. Daraus folgen drei Risikoklassen:

1. **Eindeutig beantwortbare Interaktion, aber mehrere Texte nötig:** Dissonantes Flüstern plus Gelegenheitsangriff. Der korrekte 2024-Schluss ist unter Bedingungen ableitbar, wird aber nicht technisch abgesichert.
2. **Versionsabhängige Interaktion:** Göttliche Gunst/Konzentration, Erschöpfung, Unsichtbarkeit und 2024-Slot-pro-Zug. Eine 2014-Erinnerung ändert das Ergebnis.
3. **Nicht eindeutig aufgelöste Interaktion:** Gleichzeitige Magische Geschosse und Zahl der Konzentrationswürfe. Hier muss Foliant vertretbare Lesarten und die nötige SL-Entscheidung kennzeichnen statt ein absolutes RAW zu erfinden.

Ein fachlich geeigneter Antwortprozess sollte stets lauten:

1. Beteiligte Regeln und Version identifizieren.
2. Fehlende Tatsachen wie Sicht, Reichweite, Zieltyp, Form oder freie Reaktion erfragen.
3. Allgemeine Regel nennen.
4. Spezifische Modifikation/Ausnahme anwenden.
5. Ergebnis als direkten Regeltext, logische Ableitung oder offene SL-Entscheidung kennzeichnen.
6. Quelle jeder tragenden Regel nennen, nicht nur die erste gefundene.

## 12. Bewertung der Antwortqualität für Spielende

### Was bereits hilft

- Deutsch-first, offizielle Begriffe und Quellenzeile erleichtern die Nutzung am deutschen Spieltisch.
- Leere Bestände sollen ehrlich benannt werden.
- Altstände erhalten grundsätzlich eine Warnung.
- Die vorgesehenen kompakten Markdown-Antworten sind für schnelle Tischfragen geeignet.
- Die Hinweise, fehlende Bücher nicht aus Modellwissen zu ergänzen, reduzieren Halluzinationen.

### Was reale Spielerantworten derzeit gefährdet

- Der falsche Eintrag kann mit einer überzeugenden Quelle und Seitenzahl erscheinen. Dadurch wirkt die Falschantwort besonders glaubwürdig.
- „Vollständiger Text“ ermutigt das Modell, ein Kurzfragment als abschließende Regel zu behandeln.
- Natürliche Formulierungen und geläufige Synonyme funktionieren unzuverlässig.
- Die Instruktionen definieren keine klare Reihenfolge `direkte Antwort -> Bedingung -> Ausnahme -> Beispiel -> Beleg`.
- Fehlende Informationen führen nicht systematisch zu Rückfragen.
- RAW/Ableitung/SL-Entscheidung sind nicht sichtbar getrennt.
- Build-Grenzen stehen zwar in einer Liste, aber das positive Label `legal_soweit_pruefbar` dominiert die Wahrnehmung und kann eindeutig ungeprüfte Illegalität verschleiern.
- Das wiederholte englische Original bei jeder Nennung macht komplexe Antworten unnötig schwer lesbar.

**Urteil:** Ein sorgfältiges Modell kann aus guten Treffern brauchbare Antworten erstellen. Die Toolausgabe selbst bietet jedoch noch keine verlässliche Grundlage für reale Spielerfragen, weil falsche oder unvollständige Treffer zu selbstsicher präsentiert werden.

## 13. Eignung für eine spätere Nutzung durch Spielleitende

Für eine spätere SL-Nutzung sind bereits wertvolle Bausteine vorhanden: Monsterstatblocks, Gegenstände, allgemeine Regeln, soziale Interaktion, Reise-/Erkundungsabschnitte und ein quellenübergreifender Suchbestand. Die freie Quellenerweiterung könnte Umweltregeln, Fallen, Belohnungen und optionale Module aufnehmen.

Die heutige Struktur ist trotzdem nur **bedingt erweiterbar**:

- Es gibt keine Trennung von Spielerwissen, SL-Wissen, Geheimnis und Abenteuer-Lore.
- Monsteraktionen verlieren in Open5e wichtige Nutzungs- und Formbedingungen.
- Abenteuerinhalte liegen im gleichen Suchraum, obwohl der Spielerzugang sie nicht sehen soll.
- Optionale Regeln, Varianten und SL-Entscheidungen haben keinen Status.
- Hausregeln und Kampagnenkontext sind bewusst nicht modelliert.
- Das System bietet keine Unterstützung für Adjudikation: Schwierigkeit setzen, Konsequenzen abwägen, improvisierte Handlungen und dokumentierte Tischentscheidungen.
- Begegnungsleitung benötigt Initiative, Ressourcen-/Recharge-Zustand, Gelände und mehrere Kreaturen; das MVP ist nur stateless Nachschlagewerk.

Vor einem SL-Modus sollte daher nicht nur „mehr Inhalt“ importiert werden. Erforderlich sind getrennte Zielgruppen/Scopes, harte Spoilerfilter, optionale Regelpakete, sichtbare Adjudikationsart und ein eigener privater SL-Zugang. Erst danach sind Kampagnenwissen, NSC-Vorbereitung, Begegnungsbau und Belohnungen fachlich verantwortbar.

## 14. Mögliche urheberrechtliche oder quellenbezogene Risiken

Diese Einschätzung ist keine Rechtsberatung.

| Risiko | Beobachtung | Empfohlene Grenze |
|---|---|---|
| Vollständige Regeltexte | Detailtools geben `regeltext_md` vollständig aus. | Nutzerfrage eigenständig zusammenfassen; nur notwendige kurze Belege, sofern die Quelle nicht frei reproduzierbar ist. |
| Vollständige DDB-/PHB-Inhalte | Private Datenbank enthält umfangreiche gekaufte Inhalte und kann technisch als bedienter Bestand konfiguriert werden. | Strikt privat und zugangsbeschränkt; keine öffentliche oder unkontrollierte Gruppen-Volltextbibliothek. |
| Abenteuer-/Settingtexte | 807 private Einträge aus einer Ravenloft-Quelle liegen im allgemeinen Suchschema. | Spielerbestand ausschließen; SL-/Spoilerbereich technisch separieren. |
| Lizenzvermischung | CC-BY, OGL-Sammellabel und `privat` liegen im gleichen Ausgabeweg. | Lizenz- und Ausgaberegel pro Quelle erzwingen; Attribution dokumentbezogen. |
| Unklare Reproduktionstiefe | „Vollständiger Steckbrief“ kann bei geschützten Quellen große Textmengen bedeuten. | Strukturwerte und eigene Zusammenfassung bevorzugen; keine Kapitel- oder Tabellenreproduktion auf Zuruf. |
| DDB-Nutzungsbedingungen | Die Projektdokumentation nennt selbst eine bewusst akzeptierte ToS-Grauzone. | Vor Veröffentlichung oder Ausweitung auf weitere Nutzer gesondert prüfen. |

Positiv ist, dass das SRD 5.2.1 korrekt als CC-BY-4.0 gekennzeichnet und grundsätzlich attribuiert wird. Das mindert aber nicht automatisch die Risiken anderer Quellen im selben Antwortpfad.

## 15. Priorisierter fachlicher Maßnahmenplan

### Zwingend vor weiteren internen Tests

| Priorität | IDs | Ziel | Konkrete Umsetzung | Fachliches Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| P0 | DND-001 | Jede 2024-Zustandsfrage bleibt 2024. | Kontrollierte Zustandsaliasse; Edition vor Alt-Fallback; klammerlose Namen semantisch exakt auflösen. | Alle kanonischen und klammerlosen Namen der 2024-Zustände liefern 2024; 2014 erscheint nur bei expliziter 2014-Anfrage oder echtem Fehlen. | M |
| P0 | DND-002, DND-013 | Kontexttreue Auswahl statt namensbasierter Vernichtung. | Kontext/Seite/ID in Identität und Treffer aufnehmen; fuzzy nicht als Exaktheit; Detailabruf per ID; allgemeine Magieregeln korrekt kategorisieren. | Aktion, Bonusaktion, Reaktion, Bewegung, Temp-TP, Todesrettungswurf und Komponenten liefern jeweils den vollständigen passenden Kernabschnitt oder transparente Kandidaten. | L |
| P0 | DND-003, DND-004 | Beschädigte/vermischte Inhalte aus dem Antwortpfad entfernen. | Betroffene PDF-Seiten neu importieren; Pflichtfelder und verbotene Fremdklauseln prüfen; beschädigte Chunks quarantänisieren. | Eissturm, Göttliche Gunst, Symbol, Windwall, Vampirbrut, Schild, Attributswurf und Zweihändig bestehen die fachlichen Goldprüfungen. | L |
| P0 | DND-005 | Keine falschen Legalitätsbestätigungen. | Positive Labels bis zur Korrektur einschränken; fehlende Erhöhungen/Unterklasse als `incomplete`; ungeprüfte Talente/Meisterschaften als `unsupported`. | Keiner der vier reproduzierten illegalen/unvollständigen Builds erhält `legal_soweit_pruefbar`. | M |

### Vor externen Nutzertests

| Priorität | IDs | Ziel | Konkrete Umsetzung | Fachliches Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| P0 | DND-006 | Fachlich vollständige 2024-Charakterführung. | Fünf Schritte; Sprachen/Speziespflichtwahlen; Stufe-1-Scope oder getrennte Fortschrittsdaten; Krimineller- und Schurkeneinträge reparieren. | Ein vollständiger Stufe-1-Charakter enthält alle Pflichtwahlen; Stufe-3-Klasse benötigt Unterklasse; höherstufige Builds sind korrekt oder klar `unsupported`. | XL |
| P0 | DND-007, DND-008 | Nur finale, passende Spielerregeln im Standardpfad. | `publication_status`, `scope`, `audience`, `spoiler_risk`, Publisher und Revision speichern; Abenteuer/Playtest standardmäßig filtern. | Spielerabfragen können keine Abenteuer-/Playtesteinträge erreichen; UA wird nie als finales RAW ausgegeben. | L |
| P0 | DND-010 | Vollständige Open5e-Felder. | Reaktionstrigger, Formlimit, Recharge/Nutzung, Aktionskosten, Reihenfolge und Initiative erhalten. | Gegenzauber/Schild zeigen vollständige Trigger; Vampiraktionen zeigen Form und Recharge; Formatter-Goldtests bestehen. | M |
| P1 | DND-011 | Quellenabweichungen sichtbar machen. | Textidentität statt Namensidentität; Konfliktobjekt mit beiden Fundstellen; Original-/Errata-Policy. | Vampir-Bezaubern wird als 2024-Quellenkonflikt ausgegeben, nicht still entschieden. | L |
| P0 | DND-012 | Fachliche Regression statt bloßer Strukturtests. | Realbestands-Goldtests für alle P0-Fälle; erwartete und verbotene Klauseln; 2014/2024-Gegenproben. | Jeder kritische/hohe reproduzierte Fehler hat mindestens einen fehlschlagenden Vorher-/bestehenden Nachher-Test. | L |

### Vor Veröffentlichung des MVP

| Priorität | IDs | Ziel | Konkrete Umsetzung | Fachliches Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| P0 | DND-009, DND-014 | Aussagearten und komplexe Antworten fachlich ehrlich. | Antwortvertrag für RAW, Ableitung, offizielle Klarstellung, offene Auslegung und SL-Ruling; Mehrregel-Checkliste; Rückfragekriterien. | Goldfragen zu Dissonantem Flüstern, Magischem Geschoss und Unsichtbarkeit werden mit korrekter Aussageart, Bedingungen und mehreren Belegen beantwortet. | L |
| P0 | DND-012 | Modellverhalten Ende-zu-Ende prüfen. | Client-/Modell-Evals für Nichtwissen, Quelle/Version, Altstand, Mehrdeutigkeit, Rückfrage, Spoiler und Kurz-/Langantwort. | Definierte Erfolgsquote über wiederholte Läufe; T10 nicht mehr pauschal übersprungen; Fehlantworten werden sichtbar protokolliert. | L |
| P0 | DND-015 | Produktionsbestand reproduzierbar freigeben. | Quellenmanifest mit Hash, Version, Revision, Anzahl und Status; gleiche QS lokal und auf Pi. | Bedienter Bestand entspricht dem freigegebenen Manifest und besteht dieselben Fachtests. | M |
| P0 | DND-016 | Quellenabhängige Ausgabe- und Lizenzgrenzen. | Private/freie Quellen im Ausgabepfad unterscheiden; Zugriff und Reproduktionstiefe begrenzen; Attribution pro Lizenz. | Keine unberechtigte Volltext-/Abenteuerausgabe; CC-BY/OGL-Anforderungen dokumentiert und getestet; Eigentümerentscheidung zur Gruppenfreigabe protokolliert. | L |

### Nach dem MVP

| Priorität | IDs | Ziel | Konkrete Umsetzung | Fachliches Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| P2 | DND-017 | Ehrliche vollständige Charaktermethoden. | Zufallserstellung als nicht validierbare offizielle Methode; Mehrklassenstruktur oder expliziter Nicht-Support; Versionsaliasse. | Wissensfrage nennt drei Attributsmethoden; Mehrklassen-Build ist korrekt geprüft oder ausdrücklich unsupported. | M |
| P2 | DND-018 | Schnell erfassbare Tischantworten. | Originalbegriff bei erster Nennung; Kurzantwort zuerst; Detailmodus bei Bedarf. | Usability-Testende finden Ja/Nein/Bedingung und Quelle ohne unnötige Wiederholung. | S |
| P2 | DND-015 | Feingranulare Provenienz. | Abschnittspfad, stabile Quell-ID/URL, Buch-/Errata-Version und Importzeit erhalten. | Jede tragende Aussage lässt sich bis zu einem konkreten Dokumentabschnitt und Revisionsstand verfolgen. | M |

### Spätere fachliche Erweiterungen

| Priorität | IDs | Ziel | Konkrete Umsetzung | Fachliches Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| P3 | DND-014 | Strukturierte Regelinteraktionen. | Beziehungen für spezifisch/allgemein, ersetzt, modifiziert, Trigger, Ziel, Dauer und Stapelung bei häufigen Kernregeln. | Definierter Interaktionskatalog liefert nachvollziehbare Begründungsketten und erkennt fehlende Parameter. | XL |
| P3 | DND-007, DND-016 | Sicherer SL-Modus. | Getrennter SL-Zugang, Geheimnis-/Lore-Klassifikation, Kampagnenbereiche und Spoilerfilter. | Spielerzugang kann technisch keine SL-/Abenteuerinhalte abrufen; SL-Antworten sind als solche markiert. | XL |
| P3 | DND-008, DND-009 | Optionale Regeln und Hausregeln. | Regelpakete mit Autorität, Gültigkeitsbereich, Kampagne und sichtbarer Überlagerung. | Jede Antwort zeigt, ob sie Kernregel, optionale Regel oder konkrete Hausregel nutzt. | XL |

## 16. Empfohlene fachliche Testfragen

Die folgenden 44 Tests sind als Ende-zu-Ende-Fachtests gedacht. Erwartet wird nicht zwingend wortgleicher Text, sondern die genannte Kernaussage, die richtige Aussageart und eine belegte 2024-/2014-Trennung.

| Test-ID | Frage | Kategorie und Zweck | Erwartete Kernaussage | Wichtige Fallstricke | Version und Quelle | Verhalten bei fehlenden Informationen |
|---|---|---|---|---|---|---|
| DND-T-001 | „Bei einem SG-5-Attributswurf würfle ich eine natürliche 1 und habe +7. Scheitere ich automatisch?“ | Grundregel; Angriffswurf von W20-Prüfung trennen. | Gesamt 8 erreicht SG 5. Natürliche 1 ist bei allgemeinen Attributswürfen kein automatischer Misserfolg. | Natürliche 1 beim Angriff und Sonderregel beim Todesrettungswurf nicht verallgemeinern; spezifische Regel kann abweichen. | 2024; SRD 5.2.1 DE S. 6-7 und S. 20. | Fehlen SG oder Modifikator, nur Regel erklären und Werte erfragen. |
| DND-T-002 | „Zwei Effekte geben Vorteil, einer gibt Nachteil. Habe ich insgesamt Vorteil?“ | Häufige Spielerfrage; Stapelung. | Jede Kombination aus Vorteil und Nachteil hebt sich vollständig auf; ein W20. Mehrere Quellen derselben Art stapeln nicht. | Kein Nettozählen 2 gegen 1; Wiederholungswurf ist ein anderes Konzept. | 2024; SRD S. 8. | Nach Sonderregeln fragen, die den konkreten Wurf ersetzen. |
| DND-T-003 | „Darf ich einen Rettungswurf absichtlich misslingen lassen? Gilt das auch für Attributswürfe?“ | Ähnliche Begriffe; Regelausnahme. | 2024 erlaubt freiwilliges Scheitern eines Rettungswurfs. Es gibt keine gleichlautende allgemeine Erlaubnis für jeden Attributswurf. | Spezifischer Effekt kann Freiwilligkeit anders regeln. | 2024; SRD S. 7 und Glossar S. 213. | Konkreten Effekt anfordern, bevor die Ausnahme absolut angewendet wird. |
| DND-T-004 | „Kann ich meine Aktion in eine zweite Bonusaktion umwandeln?“ | Aktionsökonomie; falsche Annahme. | Keine allgemeine Umwandlung. Bonusaktion nur durch ausdrückliche Regel und höchstens eine im eigenen Zug. | Spezifisches Merkmal kann besondere Nutzung erlauben, begründet aber keinen allgemeinen Tausch. | 2024; SRD S. 10-11 und S. 205. | Nach Merkmal/Zauber fragen, auf den sich die Person beruft. |
| DND-T-005 | „Ich benutze meine Reaktion in meinem eigenen Zug. Wann bekomme ich sie zurück?“ | Timing. | Bis zum Beginn des nächsten eigenen Zugs steht keine weitere Reaktion zur Verfügung. | Nicht Rundenbeginn und nicht Ende des aktuellen Zugs. | 2024; SRD Glossar S. 213. | Nur bei spezifischer abweichender Fähigkeit deren Text anfordern. |
| DND-T-006 | „Ich habe Zusätzlicher Angriff. Darf ich bei einem Gelegenheitsangriff zweimal angreifen?“ | Angriff versus Angriffsaktion. | Nein. Der normale Gelegenheitsangriff ist eine Reaktion für genau einen Nahkampf-Waffen- oder waffenlosen Angriff, nicht die Angriffsaktion. | Konkrete Monster-/Klassenreaktion kann abweichen. | 2024; SRD S. 203 und 208 plus Merkmal. | Exakten Merkmaltext erfragen, falls nicht das Standardmerkmal gemeint ist. |
| DND-T-007 | „Das Ziel von Dissonantes Flüstern verlässt meine Reichweite mit seiner Reaktion. Provoziert es?“ | Mehrregel-Ableitung; specific beats general. | Ja, sofern sichtbar, eigene Reaktion frei und Reichweite verlassen wird: Das Ziel nutzt seine eigene Reaktion zur Bewegung, was der 2024-Trigger umfasst. | Keine Bewegung ohne verfügbare Reaktion; Rückzug und andere Sonderregeln beachten. | 2024; SRD Zauber S. 130 und Gelegenheitsangriff S. 208. | Sicht, Reichweite und Reaktionsverfügbarkeit erfragen; Ergebnis als RAW-Ableitung markieren. |
| DND-T-008 | „Eine Explosion schleudert den Gegner aus meiner Reichweite. Bekomme ich einen Gelegenheitsangriff? Und bei Teleportation?“ | Regelausnahme; erzwungene Bewegung. | Nein in beiden Fällen. Kein Gelegenheitsangriff bei Bewegung ohne eigene Bewegung/Aktion/Bonusaktion/Reaktion; Teleportation löst ihn nicht aus. | Dissonantes Flüstern ist anders, weil das Ziel seine Reaktion nutzt. | 2024; SRD S. 17, 208 und 216. | Art der Bewegung klären, wenn nur „wird bewegt“ gesagt wird. |
| DND-T-009 | „Ich bin gepackt. Gegen wen habe ich Nachteil, wie entkomme ich, und wie schnell kann mich der Gegner ziehen?“ | Versionsabhängiger Zustand; mehrere Teilregeln. | 2024: Bewegungsrate 0; Nachteil auf Angriffe gegen andere Ziele als den Packenden; Flucht als Aktion gegen Flucht-SG; Ziehen kostet zusätzliche Bewegung, mit Größen-Ausnahme. | Nicht den 2014-Zustand liefern; Reichweite, freie Hand und Größen beachten. | 2024; SRD S. 208-209 und Waffenloser Angriff S. 219. | Größen, Flucht-SG und konkrete Packquelle erfragen. |
| DND-T-010 | „Der Gegner ist unsichtbar, aber ich habe Wahre Sicht. Hat er trotzdem Vorteil gegen mich?“ | Sicht versus Zustand; versionssensitiv. | Nach 2024 entfallen die Angriffsvorteile gegenüber der Kreatur, die ihn sehen kann; ebenso deren Nachteil gegen ihn. | Sichtreichweite, Hindernisse und 2014-Debatte nicht vermischen. | 2024; SRD Unsichtbar S. 217 und Wahrer Blick S. 219. | Reichweite und tatsächliche Sichtlinie erfragen. |
| DND-T-011 | „Eine Kreatur steht zwischen mir und dem Ziel. Hat das Ziel Deckung, und stapelt das mit einem Baum?“ | Deckung; Geometrie. | Eine Kreatur kann Teildeckung geben, wenn sie mindestens die Hälfte verdeckt. Deckungsgrade stapeln nicht; nur der höchste passende Grad gilt. | Deckung wird vom Ursprung des Angriffs/Effekts beurteilt; volle Deckung verhindert direktes Anvisieren. | 2024; SRD S. 17 und 206. | Position und Verdeckungsgrad erfragen; keine Karte erfinden. |
| DND-T-012 | „Ich liege in schwierigem Gelände bei Bewegungsrate 9 m. Was kostet Aufstehen und danach 1,5 m Bewegung?“ | Bewegung plus Zustand. | Aufstehen kostet 4,5 m; das schwierige Gelände verdoppelt nicht die Aufstehkosten. Danach kosten 1,5 m Ortsbewegung 3 m. | Bei Bewegungsrate 0 kann man nicht aufstehen; weitere Kosten können hinzukommen. | 2024; SRD Liegend S. 212 und Schwieriges Gelände S. 214. | Aktuelle Bewegungsrate und andere Modifikatoren erfragen. |
| DND-T-013 | „Ich habe 8 temporäre TP und bekomme 12. Habe ich 20? Wache ich damit bei 0 TP auf?“ | Trefferpunkte; falsche Annahme. | Nicht stapelbar: 8 behalten oder 12 ersetzen. Temporäre TP sind keine Heilung und machen bei 0 TP nicht bewusst. | Ablauf vor normalen TP und Ende spätestens nach langer Rast nennen. | 2024; SRD S. 20-21 und 216. | Keine Zusatzinformation nötig, sofern kein spezifischer Effekt abweicht. |
| DND-T-014 | „Ich bin bei 0 TP bewusstlos und werde aus 1,5 m von einem Nahkampfangriff getroffen. Wie viele Todes-Misserfolge?“ | Tod, Zustand und kritischer Treffer. | Bei Treffer aus höchstens 1,5 m gegen Bewusstlosen ist es kritisch; Schaden bei 0 durch kritischen Treffer verursacht zwei Misserfolge. Massiver Schaden kann sofort töten. | Angriff muss treffen; Entfernung und Schadenshöhe sind entscheidend. | 2024; SRD S. 20 und Bewusstlos S. 205. | Entfernung, Angriffstyp, Schaden und TP-Maximum erfragen. |
| DND-T-015 | „Nach einem Modifikator bleiben 23 Feuerschaden. Ich habe zugleich Resistenz und Verwundbarkeit. Wie viel?“ | Reihenfolge von Schaden. | Resistenz halbiert abgerundet auf 11, danach Verwundbarkeit verdoppelt auf 22. Gleichnamige Resistenzen/Verwundbarkeiten stapeln nicht. | Modifikatoren kommen vor Resistenz/Verwundbarkeit; Immunität gesondert. | 2024; SRD S. 19. | Weitere Modifikatoren oder Immunität erfragen. |
| DND-T-016 | „Unterbricht ein Zaubertrick meine lange Rast? Was passiert nach einer Unterbrechung nach zwei Stunden?“ | Rast; Ausnahme. | Ein Zaubertrick allein steht nicht in der Unterbrechungsliste. Nach mindestens 1 Stunde gibt es bei Unterbrechung die Vorteile einer kurzen Rast; Fortsetzung kostet pro Unterbrechung zusätzliche Zeit. | Nicht-Zaubertrick, Initiative, Schaden und lange Anstrengung unterscheiden; 16-Stunden-Abstand beachten. | 2024; SRD Lange Rast S. 212. | Art des Zaubers und weitere Ereignisse erfragen. |
| DND-T-017 | „Ist der SG jedes Attributswurfs mindestens 15 oder der Intelligenzwert des Ziels?“ | Datenkontamination; soziale Aktion. | Nein. Dieser SG gehört nur zur spezifischen Beeinflussen-Aktion bei bestimmten Haltungen. Allgemeiner Attributswurf nutzt den SG der Regel oder SL-Festlegung. | Kontaminierten Chunk nicht als allgemeine Regel zusammenfassen. | 2024; SRD S. 6 und Beeinflussen S. 204. | Situation/konkrete Aktion erfragen, wenn ein SG bestimmt werden soll. |
| DND-T-018 | „Welche Nachteile habe ich bei zwei Stufen Erschöpfung nach 2024?“ | Versionsabhängige Kernregel. | Zweimal kumulativer 2024-Malus auf W20-Prüfungen und Bewegungsrate; nicht die 2014-Stufentabelle. | Klammerloser Zustandsname darf nicht auf 2014 fallen. | 2024; SRD Erschöpfung S. 206. | Anzahl der Stufen und gespielte Version bestätigen, wenn nicht genannt. |
| DND-T-019 | „Ein Feuerball trifft mich. Kann ich Schild wirken, um +5 RK gegen ihn zu bekommen?“ | Falsche Annahme; Zauberwirkung versus Angriff. | Nein. Feuerball verlangt einen Geschicklichkeitsrettungswurf. Schild reagiert auf einen treffenden Angriffswurf oder Magisches Geschoss. | „Von einem Zauber getroffen“ ist nicht automatisch Angriffswurf; RK hilft nicht beim Rettungswurf. | 2024; SRD Schild S. 169 und Feuerball S. 139. | Den auslösenden Effekt und Wurfart erfragen. |
| DND-T-020 | „Kann ich Gegenzauber wirken, wenn ich die Kreatur sehe, ihr Zauber aber ohne Komponenten gewirkt wird?“ | Reaktionstrigger; Komponenten. | Nein. 2024 reagiert Gegenzauber auf eine gesehene Kreatur in Reichweite, die einen Zauber mit V-, G- oder M-Komponente wirkt. | Komponentenloses Wirken; Reichweite allein reicht nicht. | 2024; SRD Gegenzauber S. 146. | Sicht, Abstand und vorhandene Komponenten erfragen. |
| DND-T-021 | „Ich wirke Nebelschritt mit Zauberplatz als Bonusaktion. Darf ich im selben Zug Gegenzauber mit Zauberplatz wirken?“ | 2024-Slot-pro-Zug; Timing. | Nein im selben Zug, wenn beide einen Zauberplatz verbrauchen. In einem späteren Zug derselben Runde ist die Reaktion grundsätzlich wieder nach dieser Regel möglich. | Nicht die 2014-Bonusaktionszauberregel nennen; Zug und Runde trennen; platzfreies Wirken separat. | 2024; SRD S. 119 und Reaktion S. 213. | Klären, ob beide Wirkungen Plätze verbrauchen und in wessen Zug reagiert wird. |
| DND-T-022 | „Ich erleide 100 Schaden in einer Instanz, während ich mich konzentriere. Wie hoch ist der SG?“ | Konzentration; 2024-Änderung. | SG 30: normalerweise 10 oder halber Schaden abgerundet, der höhere Wert, in 2024 auf 30 begrenzt. | Nicht SG 50 aus 2014; getrennte Schadensinstanzen getrennt prüfen. | 2024; SRD Konzentration S. 211. | Fragen, ob es wirklich eine oder mehrere Instanzen sind. |
| DND-T-023 | „Ich konzentriere mich auf Sonnenstrahl und beginne einen Zauber mit zehn Minuten Zeitaufwand ohne spätere Konzentration. Bleibt Sonnenstrahl?“ | Konzentrationsbeginn/-ende. | Nein. Zauber mit mindestens einer Minute Zeitaufwand erfordern während des Wirkens Konzentration; die alte Konzentration endet beim Beginn der neuen. | Zeitaufwand und Wirkungsdauer nicht verwechseln. | 2024; SRD S. 119, 211 und Sonnenstrahl S. 175. | Zeitaufwand und Sonderregeln des zweiten Zaubers erfragen. |
| DND-T-024 | „Zwei Kleriker wirken Segnen auf mich. Addiere ich beide W4?“ | Gleichnamige Zaubereffekte. | Nein. Derselbe Zauber stapelt während überlappender Dauer nicht; stärkster beziehungsweise bei Gleichstand neuester Effekt gilt. | Konzentration beider Wirker getrennt; andere benannte Effekte können kombinieren. | 2024; SRD Zaubereffekte kombinieren S. 121. | Klären, ob es wirklich derselbe Zauber ist. |
| DND-T-025 | „Alle drei Magischen Geschosse treffen dieselbe konzentrierende Kreatur gleichzeitig. Wie viele Konzentrationswürfe?“ | Umstrittene Interaktion; Aussageart. | Keine Scheineindeutigkeit. Regeltexte zusammenführen, vertretbare Lesarten benennen und mangels eindeutiger 2024-Auflösung SL-Entscheidung markieren. | Keine 2014-Klarstellung oder Designermeinung unmarkiert als 2024-RAW verwenden. | 2024; SRD Magisches Geschoss S. 159 und Konzentration S. 211. | Version und verwendete offizielle Klarstellungen/Hausregel erfragen. |
| DND-T-026 | „Braucht Göttliche Gunst Konzentration?“ | Versionsvergleich; beschädigter Treffer. | 2024: nein, 1 Minute ohne Konzentration. 2014: Konzentration bis 1 Minute. Versionen getrennt und beschädigten deutschen Treffer nicht ergänzen. | Vertraute 2014-Regel nicht als 2024 ausgeben. | 2024/2014; englisches SRD 5.2/DDB 2024 und 2014-Basic Rules. | Version erfragen; bei kaputtem Primärtreffer gleichversionierte vollständige Quelle offen nennen. |
| DND-T-027 | „Gib mir den vollständigen 2024-Zauber Eissturm.“ | Steckbrief; Datenintegrität. | Zeitaufwand, Reichweite, Komponenten, Dauer, Wirkungsbereich, Rettungswurf, Schaden, Gelände-/Dauereffekt und Hochstufung vollständig. | Der aktuelle deutsche 131-Zeichen-Kopf ist kein vollständiger Zauber. | 2024; SRD Eissturm S. 134 beziehungsweise vollständiges englisches SRD 5.2. | Bei unvollständigem Bestand ausdrücklich Datenfehler melden, nicht vervollständigen erfinden. |
| DND-T-028 | „Gib mir den vollständigen 2024-Statblock der Vampirbrut.“ | Monstersteckbrief; Datenintegrität. | Eigener Vampirbrut-Statblock, unter anderem RK 16, TP 90, HG 5 und eigene Merkmale/Aktionen; niemals Windstreich/Wirbel. | Keine Fragmente des Unsichtbaren Pirschers; Größe/Quelle korrekt. | 2024; SRD Vampirbrut S. 381 und englisches SRD 5.2. | Wenn kein vollständiger Statblock vorhanden ist, `unvollständig/nicht verlässlich` statt Vollständigkeitsbehauptung. |
| DND-T-029 | „Weiß das Ziel nach Ende von Bezaubern des 2024-Vampirs, dass es bezaubert wurde?“ | Widersprüchliche Primärquellen. | Konflikt offenlegen: deutsches SRD sagt „weiß“, englisches SRD/DDB sagt `unaware`. Keine stille Scheineindeutigkeit; Original-/Errata-Policy oder SL-Entscheidung. | Kein OCR-Fehler; Aussagen nicht verschmelzen. | Beide 2024; SRD DE S. 382 versus SRD EN/DDB `Vampire`. | Nach verwendeter Sprachfassung/Errata-Policy fragen und beide Fundstellen nennen. |
| DND-T-030 | „Kann ein Vampir in Nebelgestalt Grabesschlag einsetzen und Bezaubern in jedem Zug benutzen?“ | Monsterform; Recharge. | Nein. Nebelgestalt schränkt Aktionen ein; einzelne Angriffe haben Formlimits; Bezaubern ist Bonusaktion mit Aufladung 5-6. | Open5e-Formatter verliert derzeit genau diese Felder. | 2024; SRD Vampir S. 382. | Aktuelle Form und Aufladungsstatus erfragen; bei fehlenden Metadaten Datenlücke nennen. |
| DND-T-031 | „Jede zweihändige Waffe zwingt beim Treffer zu einem Konstitutionsrettungswurf, sonst liegt das Ziel, richtig?“ | Waffeneigenschaft versus Meisterschaft. | Falsch. Zweihändig verlangt nur zwei Hände. Der Rettungswurf gehört zur separaten Meisterschaft Umstoßen. | Eine Waffe kann beide Eigenschaften haben, sie sind aber nicht identisch; Meisterschaftszugang nötig. | 2024; SRD Waffen S. 102-104. | Konkrete Waffe und vorhandenes Meisterschaftsmerkmal erfragen. |
| DND-T-032 | „Mein Magier ist mit dem Kampfstab vertraut. Darf er automatisch Umstoßen verwenden?“ | Voraussetzung; Waffenbeherrschung. | Nein. Waffenvertrautheit allein gewährt keinen Zugriff auf die Meisterschaft; ein entsprechendes Merkmal und die konkrete Auswahl sind nötig. | Waffenwert hat eine Meisterschaft, aber nicht jede Figur darf sie nutzen. | 2024; SRD Meisterschaft S. 103 plus Klassen-/Talentmerkmal. | Klasse, Stufe, Talente und gewählte Waffen erfragen. |
| DND-T-033 | „Ist ein Schild schwere Rüstung und setzt meine RK auf 2?“ | Gegenstandssteckbrief; falsche Formatierung. | Nein. Schild ist eigene Kategorie und gibt +2 RK; Vertrautheit ist für den Vorteil nötig. Es setzt die RK nicht auf 2. | Open5e-Format `AC: 2` nicht als Basis-RK; schwere Rüstungsregeln nicht übertragen. | 2024; SRD Rüstung S. 104. | Für Gesamt-RK Rüstung, GE-Modifikator, Vertrautheit und weitere Boni erfragen. |
| DND-T-034 | „Ich ersetze mit Extra Attack einen Angriff durch ein Netz. Kann das Netz kritisch treffen?“ | Angriff versus Angriffsaktion; Gegenstand. | Nein. Das Netz ersetzt einen Angriff innerhalb der Angriffsaktion, verlangt aber einen Rettungswurf, keinen Angriffswurf; kein kritischer Treffer. | „Angriff ersetzen“ ist nicht „Angriffswurf ausführen“; Größen-/Sicht-/Reichweitenregeln. | 2024; SRD Netz S. 111 und Kritischer Treffer S. 211. | Größe, Sicht, Entfernung und verfügbare Angriffe erfragen. |
| DND-T-035 | „Führe mich vollständig durch die 2024-Charaktererschaffung.“ | Charakterworkflow. | Fünf Schritte: Klasse; Herkunft aus Hintergrund, Spezies und zwei Sprachen; Attribute; Gesinnung; Details. | Nicht die interne Vier-Schritt-Kurzfolge als vollständiges RAW ausgeben. | 2024; SRD S. 22-24. | Schrittweise nach jeder Entscheidung fortfahren; fehlende Pflichtwahl erfragen. |
| DND-T-036 | „Ist mein Soldat legal, wenn ich noch keine Hintergrundserhöhungen verteilt habe?“ | Unvollständiger Build. | Nein, noch unvollständig. Erforderlich ist +2/+1 auf zwei verschiedene erlaubte Attribute oder +1/+1/+1, maximal 20. | Fehlende Eingabe darf nicht still als legal gelten. | 2024; SRD S. 24 und 93. | Erlaubte Attribute und gewünschte Verteilung erfragen. |
| DND-T-037 | „Ist mein Kämpfer 3 ohne Unterklasse fertig?“ | Klassenpflichtentscheidung. | Nein. 2024 erhält/wählt der Kämpfer auf Klassenstufe 3 seine Unterklasse; Build ist unvollständig. | Nicht nur eine vorhandene Unterklasse auf Mindeststufe prüfen, sondern fehlende Auswahl erkennen. | 2024; SRD Kämpfer-Klassentabelle S. 55. | Gewünschte Quelle/Unterklassenoptionen aus Bestand anbieten. |
| DND-T-038 | „Darf mein Kämpfer auf Stufe 1 die Gabe des Schicksals wählen?“ | Talentvoraussetzung; falsche Annahme. | Nein. Epische Gabe erfordert mindestens Stufe 19 und eine passende Erwerbsquelle. Bloße Existenz im Bestand reicht nicht. | Mensch-/Hintergrundstalente sind andere Erwerbsquellen; nicht alle Talente frei wählbar. | 2024; SRD Talente S. 96-99. | Klasse, Stufe und Erwerbsquelle erfragen, wenn nicht genannt. |
| DND-T-039 | „Wie viele Herkunftstalente und Sprachen hat ein Mensch mit Hintergrund Soldat?“ | Herkunft; Speziesinteraktion. | Soldat gibt Wilder Angreifer; Mensch erhält über Vielseitig ein weiteres Herkunftstalent. Herkunft umfasst außerdem die vorgesehenen Sprachwahlen. | Hintergrundtalent nicht ersetzen; konkrete Sprachlisten/weitere Klassenmerkmale getrennt. | 2024; SRD Mensch und Soldat S. 93-95 sowie Herkunft S. 22. | Bereits bekannte Sprachen und gewähltes Zusatztalent erfragen. |
| DND-T-040 | „Welche drei offiziellen Methoden gibt es 2024 für Attributswerte?“ | Vollständigkeit innerhalb Charakterregeln. | Standard-Array; sechsmal 4W6 und niedrigsten Würfel verwerfen; 27-Punkte-Kauf. | „Nicht automatisch validierbar“ nicht mit „keine offizielle Methode“ verwechseln. | 2024; SRD S. 24. | Bei gewünschter Zufallsmethode Würfelergebnis nicht als vorhersehbar validieren. |
| DND-T-041 | „Kann mein Barbar mit Stärke 12 und Weisheit 14 zum Druiden mehrklassen?“ | Mehrklassen; Voraussetzungen. | Nein: Für die bestehende und neue Klasse müssen die jeweiligen Hauptattributsvoraussetzungen erfüllt sein; hier fehlt Stärke 13. | Mehrklassen ist ungeprüfter Build-Bereich; nicht positiv legalisieren. | 2024; SRD Klassenkombinationen S. 28. | Alle Klassenstufen und Hauptattribute erfragen; bei nicht implementierter Prüfung `unsupported`. |
| DND-T-042 | „Ist diese UA-Unterklasse normales 2024-RAW, und darf ich sie spielen?“ | Publikationsstatus; SL-Entscheidung. | UA/Playtest ist nicht finales offizielles RAW. Exaktes Dokument/Version kennzeichnen; Nutzung nur nach Zustimmung der Runde/SL. | Jahreszahl/Edition nicht mit Finalität verwechseln; keine Hausregel als offizielle Regel. | Exakte UA-Version; keine pauschale 2024-Quelle. | Dokumenttitel/Version erfragen; fehlt der Status im Bestand, keine Autorität raten. |
| DND-T-043 | „Was ist besser: der Zauber Schild oder der Gegenstand Schild?“ | Mehrdeutige Nutzerfrage; ähnliche Begriffe. | Zuerst klären, ob mechanischer Vergleich, Zauber oder Ausrüstungsgegenstand gemeint ist; dann Kategorien getrennt erklären. | Nicht einen Treffer allein wegen Rang auswählen; RK-Bonus und Reaktion sind verschiedene Mechaniken. | 2024; SRD Schild-Zauber S. 169 und Rüstung S. 104. | Ziel der Frage, Klasse, Ausrüstung und Situation erfragen. |
| DND-T-044 | „Wie besiege ich Strahd, und welche Geheimnisse hat das Abenteuer?“ | Nicht unterstützter Inhalt; Spoiler. | Ablehnen; keine Handlung, Geheimnisse oder Taktiken aus Bestand/Modell/Web. Optional nur spoilerfreie allgemeine Regelhilfe anbieten. | Vorhandener Abenteuerbestand darf nicht als Berechtigung gelten; keine indirekten Spoiler. | Außerhalb Spieler-MVP; Scope-Regel. | Keine Zusatzinformation anfordern, die Spoiler vertieft; sichere Alternative anbieten. |

## 17. Offene Fragen und Annahmen

1. **Welcher Bestand wird live bedient?** Die lokale öffentliche DB, die private Kandidaten-DB und der im README genannte Pi-Bestand haben unterschiedliche Quellen und Mengen. Die fachliche Freigabe muss den tatsächlichen Produktionshash nennen.
2. **Welche Quelle entscheidet bei offiziellen Sprachkonflikten?** Für den Vampir ist eine Original-/Errata-Policy nötig. „Deutsch immer zuerst“ ist bei inhaltlicher Abweichung nicht ausreichend.
3. **Soll die Build-Prüfung nur Stufe 1 oder Stufe 1-20 abdecken?** Die Signatur akzeptiert 1-20, das Datenmodell bildet aber keinen Stufenfortschritt ab.
4. **Welche Charakterpflichtfelder gehören zum MVP?** Die Anforderungen nennen Standard-Array/Point Buy und Build-Prüfung, während die 2024-Regel weitere Pflichtwahlen wie Sprachen, Speziesvarianten und Unterklasse enthält.
5. **Dürfen DDB-Volltexte mit der gesamten Runde geteilt werden?** Die Dokumentation nennt private Nutzung und eine offene Eigentümerentscheidung. Das ist vor Aktivierung der privaten DB zu klären.
6. **Sollen Abenteuer-/Settingquellen nur Terminologie liefern oder auch Regeln?** Der heutige Import lädt beide, obwohl der Spieler-Scope Abenteuer ausschließt.
7. **Welche offiziellen Klarstellungsquellen werden akzeptiert?** Errata, ein offizielles Compendium und öffentliche Designeräußerungen haben nicht dieselbe Autorität und brauchen getrennte Regeln.
8. **Welche optionalen Regeln gelten am Tisch?** Ohne Kampagnen-/Tischkonfiguration darf eine optionale Regel nicht als allgemeiner Standard erscheinen.
9. **Welcher Client und welches Modell sind Freigabegegenstand?** Die Serverinstruktion wird laut `app/server.py:6-12` nicht von jedem MCP-Client gleich zuverlässig weitergegeben.
10. **Wie viel Regeltext soll eine Spielerantwort enthalten?** Für frei lizenzierte und private Quellen braucht es unterschiedliche, explizite Ausgabegrenzen.

Annahmen dieser Review:

- Bewertet wird der dokumentierte Spieler-MVP mit 2024 als Standard, nicht ein geplanter SL-/Kampagnenmodus.
- Der deutsche SRD-5.2.1-PDF-Stand im Repository ist die lokale Referenz; bei einem sichtbaren Konflikt mit dem englischen 2024-Original wird keine stille normative Entscheidung erfunden.
- „Legalität“ bedeutet RAW innerhalb des ausdrücklich geprüften Quellenumfangs. Nicht unterstützte Bereiche dürfen deshalb nicht als positiv geprüft erscheinen.
- Open5e wird als Vermittler des SRD-Inhalts, nicht automatisch als gleichrangige unabhängige Regelautorität behandelt.
- Ein grüner technischer Test ist kein Beweis fachlicher Korrektheit, sofern keine Regelaussage geprüft wird.

## 18. Gesamturteil zur fachlichen MVP-Reife

| Kriterium | Bewertung | Kurzbegründung |
|---|---:|---|
| Fachliche Richtigkeit | **5/10** | Viele SRD-Kerntexte sind korrekt, aber Retrieval und Import liefern mehrere fundamental falsche Antworten und Steckbriefe. |
| Trennung der Regelversionen | **4/10** | Pflichtfeld und Standardfilter sind gut; der Zustandsfallback kann dennoch 2014 trotz vorhandener 2024-Regel liefern, Revisions-/Statusmodell fehlt. |
| Vollständigkeit im beanspruchten Umfang | **4/10** | Breite Kategorien sind vorhanden, aber zentrale Chunks, Charakterpflichtfelder und Steckbriefe sind unvollständig; Live-Korpus nicht reproduzierbar. |
| Umgang mit Regelausnahmen | **3/10** | Ausnahmen stehen oft im Quelltext, doch es gibt keinen verlässlichen Mehrregel-/Specific-beats-general-Prozess. |
| Quellenqualität | **7/10** | SRD 5.2.1/5.2 und PHB 2024 sind starke Quellen; Open5e-Feldverlust und nicht klassifizierte Abenteuer-/Playtestquellen mindern den Wert. |
| Nachvollziehbarkeit | **6/10** | Quelle, Seite und Edition sind meist sichtbar; Kontext, Abschnitts-ID, Revision, Aussageart und Konflikte fehlen. |
| Verständlichkeit für Spielende | **5/10** | Deutsch-first und Quellenformat helfen, aber falsche Vollständigkeitsbehauptung, fehlende Rückfragen und Wiederholungen erschweren die Nutzung. |
| Eignung für Spielleitende | **3/10** | Monster- und Regelbasis ist vorhanden, aber Rollen, Spoiler, optionale Regeln, Adjudikation und Kampagnenkontext sind nicht sicher strukturiert. |
| Fachliche Testabdeckung | **3/10** | 98 grüne Tests sichern Technik gut ab, erkennen aber die kritischen semantischen Realbestandsfehler nicht; E2E-Verhalten bleibt manuell. |
| Allgemeine fachliche MVP-Reife | **4/10** | Als internes Daten-/Tool-MVP brauchbar, für externe Spielerantworten bis zur Behebung der P0-Befunde nicht freigabefähig. |

### Freigabeentscheidung

**Nicht bereit für externe Nutzertests oder Veröffentlichung als verlässlicher D&D-Regelberater.** Interne fachliche Reparaturtests sind sinnvoll, sobald DND-001 bis DND-005 behoben oder hart aus dem Antwortpfad ausgeschlossen sind. Externe Tests sollten erst beginnen, wenn auch Scope-/Statusfilter, Open5e-Pflichtfelder und semantische Realbestands-Regressionen vorhanden sind.

### Änderungsbestätigung

Für diese Review wurden keine bestehenden Quellcode-, Wissens-, Test-, Konfigurations- oder Dokumentationsdateien verändert. Die einzige von `codex` neu angelegte Projektdatei in diesem Durchlauf ist:

`docs/reviews/2026-07-12-review-codex-dnd-regeln.md`

Vor Beginn waren bereits zwei andere, ungetrackte technische Reviewdateien im Git-Status sichtbar. Während dieser Prüfung erschien zusätzlich eine fremde `claude`-D&D-Review. Keine dieser Dateien wurde geöffnet oder verändert.

Abschließender Git-Status (`git status --short --untracked-files=all`):

```text
?? docs/reviews/2026-07-12-review-claude-dnd-regeln.md
?? docs/reviews/2026-07-12-review-claude-mcp-technik.md
?? docs/reviews/2026-07-12-review-codex-dnd-regeln.md
?? docs/reviews/2026-07-12-review-codex-mcp-technik.md
```

Damit ist bestätigt: **Codex hat in diesem D&D-Review-Durchlauf ausschließlich die angeforderte Datei `2026-07-12-review-codex-dnd-regeln.md` angelegt und keine andere Projektdatei verändert.** Die übrigen ungetrackten Dateien stammen nicht aus dieser Review-Arbeit.
