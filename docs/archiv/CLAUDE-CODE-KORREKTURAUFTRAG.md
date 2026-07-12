# Korrekturauftrag für Claude Code: Foliant

Stand: 10.07.2026  
Ziel: Die fachlichen Fehler, Datenintegritätsfehler und tatsächlich fehlenden MVP-Funktionen aus dem Code-Review korrigieren, ohne das Projekt unnötig umzubauen.

## Auftrag

Lies vor der Arbeit vollständig:

1. diese Datei,
2. `docs/foliant-anforderungen.md`,
3. `CLAUDE.md`,
4. die jeweils betroffenen Implementierungs- und Testdateien.

Arbeite anschließend in den unten festgelegten Phasen. Bewahre bestehende Nutzeränderungen, führe keine destruktiven Git-Befehle aus und erweitere den Umfang nicht eigenmächtig. Vorhandene Tests sind keine ausreichende Spezifikation: Für jeden korrigierten Fehler ist zuerst oder zusammen mit dem Fix ein Regressionstest anzulegen.

Wichtig: Nicht alle Punkte des Reviews gehören in denselben Patch. Die Abschnitte „Jetzt zwingend korrigieren“, „Separater MVP-Auftrag“ und „Bewusst nicht Teil dieses Korrekturlaufs“ sind verbindlich.

## Leitentscheidungen

Diese Regeln gelten für alle Korrekturen:

- Für Regelinhalte ist 2024 der Standard. 2014 darf niemals still als 2024 behandelt oder mit 2024 zusammengeführt werden.
- Charakterlisten und Buildprüfung verwenden ausschließlich importierte 2024-Inhalte.
- Ein Ergebnis darf nur dann `legal_soweit_pruefbar` heißen, wenn alle für die behauptete Prüfung erforderlichen Eingaben vorhanden und die geprüften Regeln aus dem Bestand belegt sind.
- Ein fehlgeschlagener, leerer oder offensichtlich unvollständiger Import darf niemals einen vorhandenen, funktionierenden Quellenbestand ersetzen.
- Deutsche und englische Einträge desselben Inhalts in derselben Edition sind eine fachliche Dublette; die kanonische Quelle gewinnt, weitere Quellen dürfen als Provenienz erhalten bleiben.
- Bestehende öffentliche Tool-Namen nicht unnötig umbenennen oder entfernen. Neue Tools nur dort ergänzen, wo ein realer Abrufpfad fehlt.
- Keine Regeln aus Allgemeinwissen ergänzen. Hardcodierte Werte sind nur zulässig, wenn ihre zugehörige 2024-Quelle im importierten Bestand nachweisbar ist und der konkrete Beleg ausgegeben wird.

---

## A. Jetzt zwingend korrigieren

### A1. Editionslogik der Suche

Betroffene Hauptdateien:

- `app/db.py`
- `app/tools/nachschlagen.py`
- `tests/test_abnahme.py`

Probleme:

1. Die Rohsuche wendet `LIMIT` editionsübergreifend an und filtert erst danach. Viele 2014-Treffer können dadurch vorhandene 2024-Treffer verdrängen.
2. Bei einer expliziten Suche nach 2014 werden vorhandene 2024-Treffer fälschlich als `aeltere_staende` bezeichnet und mit dem Text „Keine 2024-Fassung“ versehen.
3. Detail-Tools können bei gleichem Namen keine gezielte ältere Fassung laden.

Erforderliches Verhalten:

- Der Editionsfilter muss vor dem Roh-Limit wirksam sein. Eine 2024-Suche darf vorhandene 2024-Treffer nicht wegen vieler 2014-Treffer verlieren.
- Im Standardmodus `edition="2024"` dürfen ältere Treffer getrennt als `aeltere_staende` erscheinen.
- Bei einer expliziten anderen Edition muss die angeforderte Edition unter `treffer` stehen. Andere Editionen heißen neutral `andere_fassungen` oder werden weggelassen; sie dürfen nicht pauschal als älter bezeichnet werden.
- Detail-Tools erhalten einen optionalen Editionsparameter mit Standard 2024. Ist nur 2014 vorhanden, darf das bestehende Verhalten mit klarer Altstand-Warnung erhalten bleiben. Ist 2024 vorhanden und ausdrücklich 2014 angefordert, muss der volle 2014-Eintrag geliefert werden.
- Ungültige Editionen werden strukturiert abgelehnt oder auf eine klar definierte Menge beschränkt; leere Strings dürfen nicht still editionsübergreifend suchen.

Pflicht-Regressionstests:

- Mehr als 40 gut rankende 2014-Treffer plus ein schwächerer 2024-Treffer: Die 2024-Suche findet den 2024-Treffer.
- Explizite 2014-Suche bei ausschließlich vorhandenem 2024-Inhalt: kein falscher „älterer Stand“-Hinweis.
- Gleichnamiger 2014-/2024-Eintrag: Beide Fassungen lassen sich gezielt vollständig abrufen.
- Ungültige und leere Editionsangaben liefern einen klaren Validierungsfehler.

### A2. Vollständiger Abruf allgemeiner Regeln

Betroffene Hauptdateien:

- `app/tools/nachschlagen.py`
- `app/server.py`
- `tests/test_abnahme.py`

Problem:

`foliant_suche_regeln` liefert absichtlich nur einen kurzen Auszug. Für Einträge der Kategorie `regel` existiert aber kein Detail-Tool; lange Regelabschnitte können daher nicht vollständig geladen werden.

Erforderliches Verhalten:

- Ergänze genau einen klaren Detailpfad für allgemeine Regeln.
- Bevorzugte Lösung: `foliant_hol_regel(name: str, edition: str = "2024")` analog zu den bestehenden Detail-Tools.
- Alternativ ist ein generischer Detailabruf per Treffer-ID zulässig, wenn Suchtreffer dafür eine ID liefern und der Ablauf für Claude eindeutig beschrieben wird.
- Die Antwort enthält vollständigen Regeltext, Quelle, Edition und gegebenenfalls Seite.
- Mehrdeutigkeit wird wie bei den bestehenden Detail-Tools behandelt; nicht raten.

Pflicht-Regressionstest:

- Ein Regel-Chunk, dessen relevante Aussage außerhalb des Such-Snippets liegt, lässt sich vollständig über das neue Detail-Tool abrufen.

### A3. Fachliche Dubletten DE/EN

Betroffene Hauptdateien:

- `app/db.py`
- `app/glossar.py`
- gegebenenfalls eine kleine interne Normalisierungsfunktion
- `tests/test_abnahme.py`

Problem:

„Feuerball“ aus der deutschen Quelle und „Fireball“ aus Open5e werden trotz Glossarzuordnung als zwei Treffer ausgegeben.

Erforderliches Verhalten:

- Dedupliziere nur innerhalb derselben Kategorie und Edition.
- Nutze Namen, normalisierte Namen und belastbare Glossarentsprechungen für einen kanonischen Identitätsschlüssel.
- Übermerge keine nur ungefähr ähnlichen Begriffe. Fuzzy-Matches allein dürfen keine Dublette begründen.
- Die Quelle mit der kleinsten `prioritaet` liefert den kanonischen Regeltext.
- Weitere tatsächlich übereinstimmende Quellen können optional als `weitere_quellen` ausgegeben werden.
- 2014 und 2024 bleiben immer getrennt.

Pflicht-Regressionstests:

- Suche nach `Fireball` und `Feuerball`: genau ein kanonischer Feuerball-Treffer je Edition.
- Ähnliche, aber unterschiedliche Zauber bleiben getrennt.
- Gleichnamige Inhalte verschiedener Kategorien bleiben getrennt.

### A4. Charakterlisten und Buildprüfung strikt 2024

Betroffene Hauptdateien:

- `app/tools/charakter.py`
- gegebenenfalls interne Detailfunktionen in `app/tools/nachschlagen.py`
- `tests/test_abnahme.py`

Probleme:

- `_eintraege`, `_finde`, verwandte Klassenabschnitte und Klassentabellen sind nicht verlässlich auf 2024 begrenzt.
- Eine ausschließlich als 2014 vorhandene Klasse kann als legaler 2024-Build akzeptiert werden.
- Gruppen können Quellen verschiedener Editionen still zusammenführen.
- Eine deutsch eingegebene Klasse kann bei einer nur englisch vorhandenen Unterklasse durch den einfachen Namensvergleich fälschlich als unpassend gelten.

Erforderliches Verhalten:

- Alle Charakterlisten liefern ausschließlich 2024-Optionen.
- Gruppierung und Quellenlisten dürfen nur Einträge derselben Edition zusammenführen.
- Die Buildprüfung sucht Klasse, Unterklasse, Spezies, Hintergrund und Talente ausschließlich in 2024.
- Ein nur als 2014 vorhandener Inhalt ist für den 2024-Build `nicht_pruefbar` beziehungsweise nicht verfügbar, niemals `ok`.
- Klassentabelle und verwandte Abschnitte müssen zur gewählten 2024-Quelle beziehungsweise zum kanonischen 2024-Inhalt gehören.
- Unterklassenzugehörigkeit muss deutsche und englische Namensvarianten über belastbare Glossarentsprechungen berücksichtigen.
- Die Ausgabeedition darf nicht hartcodiert etwas behaupten, das den verwendeten Belegen widerspricht.

Pflicht-Regressionstests:

- Nur-2014-Klasse erscheint nicht in 2024-Listen und wird im Build nicht als `ok` bewertet.
- Derselbe Inhalt 2014 und 2024 wird in Listen nicht editionsübergreifend gruppiert.
- Eine englische Unterklasse wird einer deutsch gewählten, glossarisch identischen Klasse korrekt zugeordnet.

### A5. Buildprüfung: Eingaben, Vollständigkeit und ehrliche Ergebnisse

Betroffene Hauptdateien:

- `app/tools/charakter.py`
- `tests/test_abnahme.py`

Erforderliche Korrekturen:

1. Attributswerte müssen echte Integer sein. Strings, Booleans und Floats dürfen weder still konvertiert noch abgeschnitten werden.
2. Doppelte Aliasangaben wie `str` und `stärke` müssen als Konflikt erkannt werden, nicht still überschrieben werden.
3. Die Obergrenze 20 darf nur bestätigt werden, wenn für alle erhöhten Attribute Basiswerte vorliegen. Sonst ist nur die Verteilung prüfbar; die Obergrenze ist `nicht_pruefbar`.
4. Fehlen für einen vollständigen Charakter erforderliche Angaben wie Hintergrund, Spezies oder Attributswerte, darf das Gesamtergebnis nicht wie ein vollständiger Legalitätsnachweis wirken. Verwende einen klaren Zustand wie `unvollstaendig` oder liefere eine ausdrückliche Liste `fehlende_angaben`.
5. Ein unbekannter oder leerer Klassenname darf nicht zu `legal_soweit_pruefbar` führen.
6. Doppelte Waffenmeisterschaften dürfen nicht als mehrere gültige Auswahlen zählen. Namen, die der Bestand nicht prüfen kann, müssen entsprechend ausgewiesen werden.
7. Teilprüfungen bleiben erlaubt, müssen aber als Teilprüfung erkennbar sein.

Regelquellen:

- `foliant_hol_attributswerte` und die Buildprüfung dürfen Standardsatz, Point-Buy-Kosten und Hintergrundregeln nur dann als aus dem Bestand belegt ausgeben, wenn ein passender importierter 2024-Regelinhalt vorhanden ist.
- Gib den tatsächlichen Datenbankbeleg aus. Eine hartcodierte Quellenzeile ohne vorhandenen Bestand reicht nicht.
- Wenn die Regelquelle fehlt, lautet das Ergebnis `nicht_pruefbar`; es darf kein Allgemeinwissen einspringen.

Pflicht-Regressionstests:

- `"hoch"`, `15.9`, `true` und widersprüchliche Attribut-Aliasse werden strukturiert abgelehnt.
- Hintergrundserhöhung ohne Basiswerte bestätigt nicht die Obergrenze 20.
- Leerer/unbekannter Klassenname ergibt kein Legalitätsprädikat.
- Fehlende Pflichtangaben erzeugen `unvollstaendig` beziehungsweise eine klare Fehlstellenliste.
- Ohne importierte Attributsregel liefert `foliant_hol_attributswerte` keinen erfundenen Bestandsbeleg.
- Doppelte Waffenmeisterschaften werden erkannt.

### A6. Fuzzy-Suche und Ranking

Betroffene Hauptdateien:

- `app/db.py`
- `app/glossar.py`
- `tests/test_abnahme.py`

Probleme:

- RapidFuzz-Scores werden nach der Kandidatenauswahl verworfen und für alle Treffer auf `0.0` gesetzt.
- Der bestehende Tippfehlertest prüft hauptsächlich FTS-Prefix-Verhalten und nicht zuverlässig den Fuzzy-Fallback.
- Scores aus verschiedenen FTS-MATCH-Läufen sind nicht direkt vergleichbar.

Erforderliches Verhalten:

- Bewahre den tatsächlichen Fuzzy-Score für die Sortierung.
- Quellenpriorität entscheidet erst nach der fachlichen Treffergüte beziehungsweise bei echten Dubletten.
- Ergänze reale Tippfehlerfälle, darunter Buchstabenvertauschungen und Fehler ohne Prefix-Match.
- Sortiere Ergebnisse aus verschiedenen Glossar-/FTS-Suchläufen deterministisch; vergleiche nicht blind unvergleichbare bm25-Scores.

### A7. Re-Import atomar und verlustsicher

Betroffene Hauptdateien:

- `importer/import_markdown.py`
- `importer/import_open5e.py`
- `app/admin.py`
- `app/db.py`
- Importtests, gegebenenfalls neue Datei `tests/test_import_safety.py`

Erforderliches Verhalten:

- Markdown/PDF vollständig parsen, bevor vorhandene Einträge gelöscht werden.
- Leeres Markdown, ein leeres Verzeichnis, null erzeugte Chunks oder ein Parsefehler lassen den alten Bestand unverändert.
- Abruf und Transformation der Open5e-Daten müssen abgeschlossen und plausibilisiert sein, bevor der alte Dokumentbestand ersetzt wird.
- 404, Netzwerkfehler, ungültiges JSON, Paginationfehler oder eine unerwartet leere Antwort ersetzen keine vorhandenen Daten.
- Löschung, Einfügen, notwendige Metadatenupdates und FTS-Konsistenz gehören in eine kontrollierte Transaktion. Keine unteren Hilfsfunktionen sollen vor Abschluss des Gesamtvorgangs unumkehrbar committen.
- Ein ungewöhnlich großer Rückgang gegenüber dem bestehenden Quellenbestand muss den Import abbrechen oder eine ausdrücklich gesetzte `--force`-/`--allow-empty`-Option verlangen.
- Erst nach erfolgreicher Validierung wird der neue Bestand freigeschaltet.

Pflicht-Regressionstests:

- Leerer Markdown-Re-Import erhält den alten Bestand.
- Leeres Markdown-Verzeichnis erhält den alten Bestand.
- Exception während Parsing/Insert erhält Bestand und FTS.
- Open5e-404, fehlerhafte Pagination und leere API-Antwort erhalten den alten Bestand.
- Erfolgreicher Re-Import ersetzt exakt einmal und hält FTS und `eintraege` synchron.

### A8. Quellenmetadaten und Konfiguration konsistent machen

Betroffene Hauptdateien:

- `app/admin.py`
- `app/server.py`
- `importer/import_glossar.py`
- `importer/import_open5e.py`
- `config/foliant.example.toml`

Erforderliches Verhalten:

- Bei Quellen-Upserts alle veränderbaren Felder konsistent aktualisieren: Titel, Sprache, Edition, Herkunft, Lizenz, Priorität und Dateipfad.
- Quellen- und Eintragsedition dürfen nicht voneinander abweichen.
- Relative Quellen- und Cachepfade werden konsistent relativ zum Projektroot aufgelöst, nicht abhängig vom aktuellen Arbeitsverzeichnis.
- Für aktuell in der Beispielkonfiguration angebotene Einstellungen gilt genau eine der folgenden Lösungen:
  - Einstellung tatsächlich verwenden, oder
  - Einstellung aus Vorlage und Dokumentation entfernen.
- Das betrifft insbesondere Servername/-pfad, Glossar-API-URL und Open5e-API-Basis.

### A9. Glossar: korrekte Edition und kanonische Auswahl

Betroffene Hauptdateien:

- `importer/import_glossar.py`
- `app/glossar.py`
- `db/schema.sql` nur falls für die minimale Lösung nötig
- Glossartests

Erforderliches Verhalten:

- `name_de_ulisses` bedeutet „offizieller Begriff“, aber nicht automatisch Edition 2024. Leite die Edition konservativ aus dem belegten Buch ab oder speichere sie als unbekannt, wenn sie nicht sicher bestimmbar ist.
- Alte Begriffe dürfen offiziell bleiben, aber nicht künstlich die Priorität eines 2024-Begriffs erhalten.
- Für einen englischen Begriff muss eine deterministische kanonische deutsche Fassung ausgewählt werden. Gleichrangige Konflikte dürfen nicht nur alphabetisch entschieden werden; dokumentiere beziehungsweise speichere die Auswahlregel.
- Bestehende falsche Seed-Daten müssen durch Re-Seeding oder eine kleine Datenkorrektur reproduzierbar bereinigt werden. Keine manuelle Einmaländerung nur an der lokalen SQLite-Datei.

Pflicht-Regressionstests:

- Ein Ulisses-Begriff aus `PHB(de)` wird nicht als 2024 markiert.
- Ein echter 2024-Begriff gewinnt gegen einen älteren offiziellen Begriff.
- Community-Begriff bleibt mit `*` markiert.

### A10. Open5e-Inhalte fachlich vollständig abbilden

Betroffene Hauptdateien:

- `importer/import_open5e.py`
- Open5e-Formattertests mit lokalen Fixtures, ohne Live-Netz

Erforderliches Verhalten:

- Monster-Steckbriefe übernehmen vorhandene strukturierte Felder für Resistenzen, Verwundbarkeiten, Schadens- und Zustandsimmunitäten sowie Sinne/Sichtweiten.
- Prüfe auch Zauber, Gegenstände, Waffen und Rüstungen darauf, ob für F2 relevante vorhandene API-Felder derzeit verworfen werden. Ergänze nur Felder, die tatsächlich aus der API-Fixture stammen; nichts erfinden.
- 2014- und 2024-Dokumente erhalten die jeweils korrekte Lizenzangabe, nicht pauschal `CC-BY-4.0 / OGL`.
- Pagination akzeptiert nur erwartete HTTPS-URLs des konfigurierten Open5e-Hosts, erkennt Zyklen und besitzt eine vernünftige Maximalzahl.

### A11. PDF-Fallback ohne Verlust guter Seiten

Betroffene Hauptdateien:

- `importer/pdf_nach_markdown.py`
- PDF-Konvertertests mit gemockten Konverterantworten

Problem:

Eine einzige leere Seite kann bei installiertem Docling die vollständige gute PyMuPDF-Ausgabe ersetzen und alle Seitenmarker entfernen.

Erforderliches Verhalten:

- Eine einzelne leere beziehungsweise rein grafische Seite darf nicht automatisch die gesamte Extraktion ersetzen.
- Behalte die guten PyMuPDF-Seiten und behandle Problemseiten separat oder verlange für einen vollständigen Docling-Ersatz eine ausdrückliche Option.
- Verlust von Seitenzitaten muss sichtbar und bewusst sein.

### A12. Attribution in Toolantworten

Betroffene Hauptdateien:

- `app/db.py`
- `app/tools/nachschlagen.py`
- `docs/ATTRIBUTION.md`

Erforderliches Verhalten:

- Die bereits geladene Quellenlizenz darf im Detailpfad nicht verworfen werden.
- Detailantworten führen mindestens Lizenz beziehungsweise einen knappen Attributionshinweis mit, wenn die Quelle dies verlangt.
- Formulierung und Umfang mit `docs/ATTRIBUTION.md` konsistent halten.

---

## B. Separater MVP-Auftrag, nicht in denselben Korrekturpatch mischen

### B1. DDB-Buchimport fertigstellen

`importer/import_ddb.py` ist noch ein Stub. F5 verlangt diesen Import, deshalb ist er vor einem vollständigen MVP notwendig. Er soll aber erst nach Abschluss und Stabilisierung von A7 bearbeitet werden, damit auch DDB-Importe die neue atomare Importpipeline verwenden.

Für diesen separaten Auftrag gelten mindestens:

- Cobalt-Cookie ausschließlich an einen kurzlebigen Importprozess geben, nicht an den laufenden MCP-Server.
- Kein DDB-Laufzeitzugriff.
- Edition und Quelle zwingend setzen.
- Keine Charakterdaten importieren.
- Fehler oder leere Antworten erhalten den alten Bestand.
- Lokale Fixture-/Mocktests; keine echten Zugangsdaten in Tests oder Logs.

### B2. Entscheidung zum privaten Deployment

Dies ist zuerst eine Produkt-/Betriebsentscheidung des Eigentümers, kein Auftrag an Claude, spontan einen OAuth-Provider zu bauen.

Bis zur Entscheidung gilt als sichere Standardannahme:

- Der authlose öffentliche Endpoint enthält nur frei redistribuierbare Quellen.
- Private PHB-/DDB-Inhalte werden nicht über diesen Endpoint bereitgestellt.
- Port 8000 wird nicht an alle Host-Schnittstellen veröffentlicht; Cloudflare-Regeln dürfen nicht über einen direkten Port umgangen werden.

Vor dem Deployment privater Inhalte muss eine mit dem verwendeten Claude-Connector kompatible Zugriffslösung oder eine getrennte private Bereitstellung festgelegt werden. Kein selbstgebautes OAuth-System ohne gesonderten Auftrag.

---

## C. Bewusst nicht Teil dieses Korrekturlaufs

Die folgenden Reviewpunkte sind sinnvolle Härtung oder Wartungsarbeit, aber keine Voraussetzung, um die oben genannten fachlichen Fehler korrekt zu beheben. Claude soll sie in diesem Lauf nicht nebenbei umsetzen:

- kein vollständiges OAuth-/Benutzer-/Rollensystem,
- kein allgemeines Kampagnen-, Abenteuer- oder Charakterverwaltungssystem,
- kein kompletter Umbau der SQLite-Architektur,
- kein großes Migrationsframework; minimale notwendige Datenintegritätsänderungen sind erlaubt,
- keine vorzeitige Optimierung des Glossars nur wegen des momentanen Volltabellenscans, solange Messungen kein relevantes Problem zeigen,
- kein Observability-Stack, keine Metrikplattform und kein umfangreiches Logging-System,
- keine automatische Backup-Infrastruktur und kein Feedback-Ticketsystem in diesem Patch,
- kein vollständiger Docker-Multi-Stage-/Supply-Chain-Umbau,
- keine Image-Digest-Pflicht und kein umfassendes Dependency-Lock-Projekt in diesem Patch,
- keine generelle Umstellung aller Funktionen auf async,
- keine vollständige Regel-Engine für Zauber, Multiclassing, Talente oder Ausrüstung,
- keine kosmetische Großbereinigung von Kommentaren, Namen oder Formatierung außerhalb berührter Dateien.

Diese kleinen, risikoarmen Punkte dürfen nach den fachlichen Fixes in einem getrennten Wartungspatch erledigt werden:

- `.dockerignore` um `.claude/`, `.pytest_cache/`, Archive und `config/foliant.toml` ergänzen,
- Healthcheck um DB-/Schema-Bereitschaft erweitern,
- frische `data/`-Volume-Rechte im Deployment sauber dokumentieren beziehungsweise erzeugen,
- Runtime-, Import- und Dev-Abhängigkeiten später trennen,
- CI für Python 3.12 und einen MCP-/ASGI-Integrationstest ergänzen,
- README, Projektübersicht und `CLAUDE.md` nach Abschluss auf den tatsächlichen Projektstand bringen.

---

## Empfohlene Arbeitsreihenfolge

Bearbeite nicht alles in einem unprüfbaren Großpatch.

1. **Baseline sichern:** Tests unverändert ausführen und Ergebnisse notieren.
2. **Such-/Editionskern:** A1, A2, A3 und A6 samt Regressionstests.
3. **Charakterlogik:** A4 und A5 samt Regressionstests.
4. **Importsicherheit:** A7 und A8 samt Fehler-/Rollbacktests.
5. **Datenqualität:** A9, A10, A11 und A12.
6. **Gesamttest:** formale Tests, realer Smoke-Test und DB-Integritätschecks.
7. **Dokumentation:** nur tatsächlich umgesetztes Verhalten aktualisieren.
8. **Erst danach:** separater Auftrag B1 und Eigentümerentscheidung B2.

Nach jeder Gruppe:

- die neuen gezielten Tests ausführen,
- danach die vollständige Testsuite ausführen,
- keine bereits grünen Tests durch Abschwächung „reparieren“,
- bei einer fachlichen Abweichung zuerst die Anforderungen klären, nicht still die Spezifikation ändern.

---

## Definition of Done für Korrekturlauf A

Der Korrekturlauf ist erst abgeschlossen, wenn alle folgenden Punkte erfüllt sind:

- Alle bestehenden nicht-manuellen Tests bestehen.
- Für jeden Punkt A1 bis A12 existiert mindestens ein aussagekräftiger Regressionstest oder eine begründete, überprüfbare Ausnahme.
- Der bisher übersprungene Verhaltenstest T10 bleibt als manueller Verhaltenstest kenntlich; er darf nicht als automatisiert bestanden ausgegeben werden.
- `python -m tests.smoke_test` läuft gegen die echte lokale DB erfolgreich.
- `PRAGMA integrity_check` ergibt `ok` und `PRAGMA foreign_key_check` meldet nichts.
- Eine 2024-Suche verliert keinen Treffer wegen alter Editionen.
- Explizite Editionsabfragen und Detailabrufe liefern die angeforderte Edition ohne falsche Altstand-Texte.
- Deutsche/englische Dubletten erscheinen kanonisch einmal, ohne verschiedene Inhalte zu verschmelzen.
- Charakterlisten und Buildprüfung verwenden ausschließlich 2024-Inhalte.
- Ungültige Build-Eingaben erzeugen strukturierte Befunde statt Exceptions oder stiller Konvertierung.
- Unvollständige Builds werden nicht als vollständiger Legalitätsnachweis dargestellt.
- Leere und fehlgeschlagene Importe lassen den vorherigen Bestand und FTS unverändert.
- Allgemeine Regel-Chunks können vollständig abgerufen werden.
- Open5e-Steckbriefe enthalten die in den Fixtures vorhandenen relevanten strukturierten Felder.
- Toolantworten führen Quellenedition und erforderliche Attribution konsistent mit.
- Keine echten Secrets, Cookies, privaten Inhalte oder lokale Cachedateien werden committed.

## Gewünschter Abschlussbericht von Claude Code

Am Ende kurz und überprüfbar berichten:

1. Welche Punkte A1–A12 wurden umgesetzt?
2. Welche Dateien wurden geändert?
3. Welche Regressionstests wurden neu hinzugefügt?
4. Welche Befehle wurden ausgeführt und mit welchem Ergebnis?
5. Welche Punkte sind noch offen und warum?
6. Wurde irgendeine Anforderung abweichend interpretiert? Falls ja: genaue Stelle und Entscheidung nennen.

Nicht behaupten, das Gesamt-MVP sei fertig, solange B1 oder die Entscheidung B2 noch offen sind.
