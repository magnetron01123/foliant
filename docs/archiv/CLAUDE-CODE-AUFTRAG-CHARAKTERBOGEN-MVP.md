# Claude Code – Implementierungsauftrag: DDB-PDF auf offiziellen deutschen Charakterbogen übertragen

> **ARCHIVIERT / ÜBERHOLT (Stand 17.07.2026).** David hat am 14.07.2026 entschieden: Wo dieser
> Auftrag und `KONZEPT_charakterbogen-uebersetzer.md` sich widersprechen, **führt das KONZEPT**
> (z. B. Fortsetzungsseiten bei Überlauf — hier noch als harter Abbruch beschrieben, im KONZEPT
> erlaubt). Diese Datei dient nur noch der historischen Nachvollziehbarkeit des Auftrags in
> seiner ursprünglichen Fassung. Aktueller Stand: `docs/CHARAKTERBOGEN-MVP.md`.

> **Verbindlicher Umsetzungsauftrag für einen schmalen MVP.**
>
> Dieser Auftrag ergänzt Foliant um eine kleine Website. Er ersetzt oder verändert den bestehenden
> MCP-Connector nicht. Vorhandene Projektanforderungen gelten weiter, soweit diese Datei nicht für
> die PDF-Ausgabe ausdrücklich eine engere Darstellungsregel festlegt.

## 1. Ziel in einem Satz

Unter `https://dnd.magnetron.me/` kann genau ein von D&D Beyond exportierter Charakterbogen als
PDF hochgeladen werden; die Anwendung liest ihn aus, überträgt seine Inhalte vollständig auf
Deutsch und gibt **ausschließlich den offiziellen deutschen WotC-Charakterbogen** ausgefüllt als
PDF zurück.

Der bestehende Claude-Connector muss gleichzeitig unter seiner **bereits verwendeten, unveränderten
URL** weiter funktionieren:

`https://dnd.magnetron.me/<FOLIANT_PFAD_TOKEN>/mcp`

## 2. Eigentümerentscheidungen – nicht neu verhandeln

1. **Einzige Zielvorlage ist der offizielle deutsche WotC-Bogen.**
   - Kein selbst gestalteter Bogen.
   - Kein D&D-Beyond-Layout als Ziel.
   - Keine alternative Vorlage.
   - Keine Zusatz- oder Fortsetzungsseite.
2. Der offizielle deutsche Bogen ist statisch. Er wird unverändert als Hintergrund verwendet und
   ausschließlich mit Text, Zahlen und Markierungen überlagert.
3. Feststehende D&D-Begriffe kommen aus derselben Foliant-Terminologielogik wie das bestehende
   MCP-Tool `foliant_uebersetze_begriff`. Es darf kein zweites Glossar entstehen.
4. Sonstige Beschreibungen, Flavourtext und freie Texte aus dem DDB-PDF werden sinngenau ins
   Deutsche übersetzt. Sie werden nicht durch zusätzliche Buchtexte aus Foliant ersetzt.
5. Die Ausgabe ist **Deutsch-first nach der vollständigen MCP-Sprachlogik**:
   - alle Erklärungen, Aktionsbeschreibungen, Regel- und Flavourtexte stehen auf Deutsch,
   - jeder durch Foliant aufgelöste Spielbegriff trägt bei jeder Nennung das englische Original
     in Klammern,
   - offizieller Treffer: `Mönch (Monk)`,
   - Community-/Modellfallback: `Nebelwanderer* (Mist Wanderer)`,
   - anderes unübersetztes Englisch darf nicht im erzeugten Inhalt verbleiben,
   - Charakter- und Eigennamen sowie unveränderte Bestandteile der offiziellen Hintergrund-PDF
     sind ausgenommen.
6. Die statischen Beschriftungen des offiziellen deutschen WotC-Bogens bleiben unverändert und
   werden nicht nachträglich mit englischen Klammerbegriffen ergänzt. Die MCP-Darstellung gilt für
   alle aus dem DDB-Inhalt eingesetzten Spielbegriffe. Die bestehende MCP-Ausgabe selbst bleibt
   unverändert.
7. Die Website ist ein möglichst schmaler MVP:
   - eine Seite,
   - eine PDF-Dateiauswahl,
   - eine Hauptschaltfläche,
   - ein kurzer Status oder eine konkrete Fehlermeldung,
   - fertige PDF als Download.
8. Keine Optionen, Navigation, Vorschau, Konten, Historie, Charakterbibliothek, manuelle
   Korrekturansicht, Impressums-/Datenschutzseiten, Marketingseite oder alternative Ausgabe.
9. Kein D&D-Beyond-Login, kein Character-API-Abruf, kein Scraping und kein Cobalt. Der Nutzer
   liefert selbst den DDB-PDF-Export.
10. Nicht committen, pushen oder auf dem Pi beziehungsweise im Cloudflare-Dashboard umschalten,
    solange der Eigentümer dies nicht ausdrücklich verlangt.

## 3. Vor jedem Code-Schritt

1. Lies vollständig:
   - `CLAUDE.md`
   - `PROJEKT-UEBERSICHT.md`
   - `docs/foliant-anforderungen.md`, besonders §§ 2, 5, 6, 7 und 8
   - `docs/foliant-technisches-konzept.md`
   - `docs/DEPLOY-raspberry-pi.md`
   - `docs/RUNBOOK.md`
   - `SECURITY.md`
   - `app/server.py`
   - `app/zugriff.py`
   - `app/glossar.py`
   - `app/tools/nachschlagen.py`, besonders `foliant_uebersetze_begriff`
   - `docker-compose.yml`
   - `Dockerfile`
   - `requirements.txt`
   - `.env.example`, `.gitignore` und `.dockerignore`
   - `tests/test_zugriff.py`
   - `tests/test_tool_vertrag.py`
2. Prüfe `git status --short` und bewahre alle vorhandenen Nutzeränderungen. Verändere keine
   unzusammenhängenden Dateien.
3. Führe die bestehende Test-Baseline aus und notiere das Ergebnis. Falls sie bereits rot ist,
   unterscheide bestehende Fehler von neuen Fehlern und frage, bevor du fremde Fehler reparierst.
4. Untersuche beide vom Eigentümer bereitgestellten PDFs strukturell **und visuell**. Verlasse dich
   nie allein auf Textextraktion oder `pdfinfo`.
5. Lege vor Änderungen einen kurzen, dateikonkreten Plan vor. Arbeite danach in kleinen,
   getesteten Phasen.

## 4. Verbindliche private Eingabedateien

Diese Dateien werden lokal bereitgestellt und dürfen nicht ins öffentliche Git:

### 4.1 DDB-Beispiel

`/Users/davidtrogemann/Downloads/Magnetron44523_168310785.pdf`

Bekannter Prüfstand:

- SHA-256: `d492ebaea3791364aae99bb33013d4746cb8bb8f610897f9d33c1bfe1f1b5e88`
- PDF 1.7, fünf Seiten US Letter (`612 × 792 pt`)
- Producer/Creator: PDFsharp 6.1.1
- kein Catalog-`/AcroForm`, aber 874 direkte Seiten-Widgets, davon 169 befüllt
- charakteristische Felder unter anderem `CharacterName`, `CLASS  LEVEL`, `RACE`,
  `BACKGROUND`, `STR`, `DEX`, `CON`, `INT`, `WIS`, `CHA`, `FeaturesTraits1`

Die Datei ist eine private Integrationsprobe, keine commitbare Test-Fixture.

### 4.2 Offizielle Charakterbögen

Beide offiziellen Bögen liegen lokal im privaten, gitignorierten Projektordner:

`vorlagen/charakterboegen/offiziell/`

Verbindliche Dateinamen:

- deutsche Zielvorlage:
  `vorlagen/charakterboegen/offiziell/Charakterbogen_2024_DE.pdf`
- englische offizielle Referenz:
  `vorlagen/charakterboegen/offiziell/Character_Sheet_2024_EN.pdf`

Für die Ausgabe wird ausschließlich die deutsche Zielvorlage verwendet. Die englische Datei dient
nur der lokalen strukturellen Gegenprüfung und ist keine alternative Ausgabevorlage.

Bekannter Prüfstand:

- SHA-256: `0f77e7d4ee0d206c230160c096f25fd82c5d5ec129c3bec4bae1d09515d468fc`
- PDF 1.7, zwei Seiten, jeweils `603 × 774 pt`
- Creator: Adobe InDesign 19.5
- kein AcroForm, keine Widgets und kein JavaScript

Die Vorlagen werden **nicht** beim Docker-Build aus dem Netz geladen und nicht ins Git aufgenommen.
Sie werden auf dem Pi aus `vorlagen/charakterboegen/offiziell/` read-only eingebunden. Dieser
Ordner ist ausdrücklich kein Bestandteil des MCP-Quellenimports.
Bei einer abweichenden Prüfsumme darf die bekannte Feldkarte nicht still weiterverwendet werden:
stoppen, Version untersuchen, neu vermessen und die Feldkarte bewusst versionieren.

## 5. Zielarchitektur

Der bestehende Foliant-Prozess mit privaten Regelbeständen soll nicht zugleich der öffentlich
erreichbare PDF-Upload-Prozess werden. Verwende deshalb einen kleinen Gateway vor zwei getrennten
Diensten:

```text
Cloudflare Tunnel
       |
       v
gateway:8080
  |-- /health, /ready ------------------------------> foliant:8000
  |-- /mcp und /<genau ein Segment>/mcp[/...] ------> foliant:8000
  `-- alles andere ---------------------------------> web:8080
```

### 5.1 Warum diese Trennung verbindlich ist

- Der aktuelle `ZugriffsFilter` schützt jeden Foliant-Pfad außer `/health` über die
  Anthropic-IP-Allowlist. Er soll für den öffentlichen Connector nicht aufgeweicht werden.
- PDF-Parsing und Upload-Verarbeitung gehören nicht in denselben Prozess wie der private
  Foliant-Bestand.
- Der Connector-Pfad, das Token, die Domain, die 16 Tools und der öffentliche Toolvertrag bleiben
  unverändert.
- Der Cloudflare-Tunnel braucht nur einmalig vom Origin `http://foliant:8000` auf
  `http://gateway:8080` umgestellt zu werden. Die URL des bestehenden Connectors ändert sich nicht.
- Der Umschaltpunkt ist leicht rückrollbar: Origin wieder auf `http://foliant:8000` setzen.

### 5.2 Gateway-Anforderungen

- Kleiner Caddy-Container mit versionierter Konfiguration, Admin-API deaktiviert.
- Keine Access-Logs: Der MCP-Pfad enthält das geheime Token.
- `CF-Connecting-IP`, Methoden, Body, Accept-Header und Streaming unverändert an Foliant
  weiterreichen.
- Kein Proxy-Buffering, das MCP-Streaming beeinträchtigt.
- Der Gateway kennt das tatsächliche Token nicht. Er erkennt nur `/mcp` sowie
  `/<ein Pfadsegment>/mcp` und deren technisch notwendige Unterpfade.
- Ein falscher Tokenpfad muss bei Foliant landen und dort wie bisher 403/404 liefern, niemals
  Website-HTML.
- Gateway höchstens auf `127.0.0.1` für lokale Abnahme veröffentlichen; Webdienst und Foliant
  erhalten keine neuen öffentlichen Host-Ports.

### 5.3 Interne Foliant-Terminologie

Die Website darf weder ein eigenes Glossar aufbauen noch den öffentlichen Connector über
`dnd.magnetron.me` aufrufen.

Bevorzugte Lösung:

- eine schmale **interne**, nicht vom Gateway veröffentlichte Terminologie-Schnittstelle im
  Foliant-Prozess,
- sie ruft exakt dieselbe bestehende Resolver-Logik auf wie `foliant_uebersetze_begriff` und
  `app.glossar.begriffe_im_text`,
- sie liefert nur die für die PDF nötigen strukturierten Termdaten, niemals beliebige Buchtexte,
- sie ist mit einem separaten starken `FOLIANT_INTERN_TOKEN` geschützt,
- sie akzeptiert nur interne/private Peers ohne `CF-Connecting-IP`,
- der öffentliche MCP-Toolvertrag und die Toolzahl 16 bleiben unverändert.

Der Webdienst erhält **nicht** den öffentlichen `FOLIANT_PFAD_TOKEN`. Browser, HTML, Jobdaten,
Fehler und Logs erhalten überhaupt kein Foliant-Secret.

## 6. Website – exakt der schmale MVP

### 6.1 Sichtbarer Inhalt

Maximale Inhaltsbreite etwa 440–520 Pixel. Eine ruhige, einspaltige Karte im klassischen
Charakterbogen-Stil:

- warmer Papiergrund,
- dunkle Tinte,
- dünner Doppelrahmen,
- ein gedämpft roter Hauptbutton,
- systemeigene Serif-/Sans-Schriften,
- keine externen Fonts, Bilder, CDNs oder D&D-/WotC-Logos.

Textvorschlag:

- Überschrift: `Charakterbogen auf Deutsch`
- Unterzeile: `D&D-Beyond-PDF auswählen und als offiziellen deutschen Charakterbogen erhalten.`
- Dateifeld: `D&D-Beyond-PDF`
- Hauptbutton: `Deutschen Charakterbogen erstellen`
- Arbeitsstatus: `Bogen wird geprüft, übersetzt und ausgefüllt …`
- Erfolg: Download startet direkt; alternativ bleibt genau ein Button `PDF herunterladen`.

Keine Navigation und kein sichtbarer Footer. Keine Optionen, Hilfetexte, Akkordeons, Vorschau oder
weiteren Links. Die DDB-Prüfung geschieht automatisch nach dem Upload.

### 6.2 Technisches Verhalten

- `GET /` liefert genau diese eine Seite.
- `POST /bogen` akzeptiert genau ein Multipart-Feld `datei`.
- HTML-Formular funktioniert grundsätzlich ohne JavaScript; minimales lokales JavaScript darf den
  Button sperren und den Arbeitsstatus anzeigen.
- Verarbeitung synchron als eine Antwort, mit genau einem gebündelten Übersetzungsaufruf, damit
  der Vorgang sicher unter dem Cloudflare-Origin-Timeout bleibt. Setze zusätzlich ein klares
  serverseitiges Gesamtzeitlimit.
- Eine globale Semaphore erlaubt genau eine gleichzeitige Konvertierung. Weitere Anfragen erhalten
  eine kurze deutsche 429-Meldung; keine Queue und keine persistente Jobverwaltung.
- Erfolg liefert `application/pdf` als Attachment, sinnvoll benannt nach dem bereinigten
  Charaktername plus `-deutsch.pdf`.
- Fehlerseiten bleiben in derselben schmalen Gestaltung und enthalten nur die konkrete Meldung und
  die Möglichkeit, eine andere Datei zu wählen.
- `Cache-Control: no-store`, `X-Robots-Tag: noindex, nofollow`, strikte CSP, keine Analytics und
  keine Cookies.

### 6.3 Öffentliche Fehlertexte

- Nicht-PDF: `Bitte wähle eine PDF-Datei aus.`
- Gültige PDF, aber kein unterstützter DDB-Export:
  `Kein unterstützter D&D-Beyond-Charakterbogen.`
- Verschlüsselt oder aktiv: `Dieser PDF-Bogen kann nicht sicher verarbeitet werden.`
- Übersetzungsdienst fehlt/fehlschlägt:
  `Die Übersetzung ist momentan nicht verfügbar. Bitte versuche es später erneut.`
- Inhalt passt nicht:
  `Der vollständige Inhalt passt nicht auf den offiziellen deutschen Charakterbogen. Es wurde keine unvollständige PDF erzeugt.`
- Konverter belegt: `Gerade wird bereits ein Charakterbogen verarbeitet. Bitte versuche es gleich noch einmal.`

Keine Stacktraces, Feldwerte, Charakterdaten, Modellantworten oder Secrets in Browserantworten.

## 7. DDB-PDF-Prüfung und Extraktion

### 7.1 Sicherheitsgrenzen vor dem Parsen

- Maximalgröße konfigurierbar, Standard 15 MB.
- PDF-Magic prüfen; `Content-Type` und Dateiendung allein sind nicht vertrauenswürdig.
- Unverschlüsselt, kein JavaScript, keine eingebetteten Dateien.
- Plausibles Seiten- und Objektlimit; Dekompressions- und Ressourcenlimits.
- Kein Folgen externer Links und kein Netzwerkzugriff aus dem PDF-Parser.
- Keine Speicherung außerhalb eines pro Request angelegten temporären Verzeichnisses oder
  `BytesIO`; Aufräumen in `finally` auf Erfolgs- und Fehlerpfaden.
- Uploadnamen nie als Dateisystempfad verwenden.

### 7.2 MVP-Fingerprint

Unterstütze zunächst bewusst nur die Exportfamilie des übergebenen PDFsharp-6.1.1-Beispiels.
Erkennung nicht über Dateinamen oder einen einzelnen Metadatenwert, sondern kombiniert:

1. erwartete fünf Letter-Seiten,
2. DDB/PDFsharp-Metadaten als Hinweis,
3. direkte `/Widget`-Annotationen auf den Seiten,
4. Pflichtfeldmenge mindestens:
   `CharacterName`, `CLASS  LEVEL`, `RACE`, `BACKGROUND`, `STR`, `DEX`, `CON`, `INT`,
   `WIS`, `CHA`, `FeaturesTraits1`,
5. versionierter Fingerprint aus der sortierten Widget-Namensliste je Seite,
6. charakteristische statische DDB-Texte als zusätzliche Bestätigung.

Unbekannte Versionen werden abgelehnt; niemals Feldnamen oder Edition raten. Der Fingerprint darf
nicht einfach die komplette Beispieldatei hashen, weil andere Charaktere derselben Exportfamilie
andere Werte besitzen.

### 7.3 Neutrales Charaktermodell

Extrahiere zuerst in ein typisiertes, rendererunabhängiges Modell. Mindestens:

- Identität: Charaktername, Klasse, Unterklasse, Stufe, Spezies, Hintergrund, EP
- sechs Attribute und Modifikatoren
- Rettungswürfe, Fertigkeiten und Übungsmarkierungen
- RK, TP, temporäre TP, Trefferwürfel, Initiative, Bewegungsrate, Größe, passive Wahrnehmung,
  Übungsbonus, Inspiration, Todesrettungswürfe
- Waffen/Schadenszaubertricks mit Bonus/SG, Schaden/Art und Notiz
- Rüstungs-, Waffen- und Werkzeugvertrautheit, Sprachen
- Klassen-, Spezies- und Talentmerkmale
- Zauberattribut, Zauberwurf-SG, Zauberangriffsbonus, Plätze und Zauberliste
- Aussehen, Geschichte/Persönlichkeit, Gesinnung
- Ausrüstung, Münzen und eingestimmte Gegenstände

Zahlen, Vorzeichen, Würfelnotation, Ressourcen und Checkboxzustände bleiben strukturiert; sie dürfen
nicht als beliebiger Fließtext durch das Sprachmodell laufen.

### 7.4 Wesentliche Feldzuordnung

#### Offizielle Seite 1

- `CharacterName` → Charaktername
- `CLASS  LEVEL` → Klasse und Stufe getrennt
- Unterklasse → nur aus eindeutigem DDB-Inhalt; sonst leer, niemals raten
- `RACE` → Spezies
- `BACKGROUND` → Hintergrund
- `EXPERIENCE POINTS` → EP
- `AC` → Rüstungsklasse
- `MaxHP`, `CurrentHP`, `TempHP` → Trefferpunkte
- Trefferwürfel-Gesamt/Verbrauch → Trefferwürfel
- Todesrettungswurf-Widgets → Erfolge/Misserfolge
- `ProfBonus` → Übungsbonus
- `Init` → Initiative
- `Speed` → Bewegungsrate
- DDB-Größe → Größe
- `Passive1` → passive Wahrnehmung
- Attribute/Modifikatoren → sechs Attributsfelder
- `ST …` und zugehörige Prof-Felder → Rettungswürfe und Übungsmarkierungen
- Fertigkeitswerte und Prof-Felder → Fertigkeiten und Übungsmarkierungen
- Inspiration → Heldische Inspiration
- Waffenfelder → Waffen und Schadenszaubertricks
- `ProficienciesLang` strukturiert nach Rüstung/Waffen/Werkzeug/Sprachen aufteilen
- `FeaturesTraits1…6` strukturiert nach Klassen-, Spezies- und Talentmerkmalen aufteilen

#### Offizielle Seite 2

- Zauberattribut, Zauberwurf-SG und Zauberangriffsbonus → Kopf der Zauberseite
- Zauberplätze nur bei eindeutigem Gesamt-/Verbrauchtwert; niemals raten
- Zaubernamen und eindeutige Marker → passende Gradzeilen
- Konzentration, Ritual und erforderliche Materialien nur bei eindeutigem DDB-Wert
- Aussehen und zugehörige freie Angaben → Aussehen
- Persönlichkeit, Ideale, Bindungen, Makel, Hintergrundgeschichte → Geschichte & Persönlichkeit
- Gesinnung → Gesinnung
- Sprachen → Sprachen
- Ausrüstung und Mengen → Ausrüstung
- eingestimmte Gegenstände → Einstimmung
- CP/SP/EP/GP/PP → KM/SM/EM/GM/PM

`PLAYER NAME` und ein Charakterportrait haben in dieser MVP-Feldkarte kein Ziel und werden nicht
ausgegeben. Jedes weitere DDB-Feld ohne semantisch entsprechendes Feld im offiziellen deutschen
Bogen bleibt außerhalb des MVP; dokumentiere die vollständige Liste, statt heimlich neue Bereiche
zu erfinden.

### 7.5 Fragmentierte Merkmalsfelder

`FeaturesTraits1` bis `FeaturesTraits6` müssen zuerst in numerischer Reihenfolge und ohne
Zeichenverlust zusammengesetzt werden. Im Beispiel trennen die Seiten Sätze mitten im Wort oder
Satz. Erst nach dem Zusammenfügen darf nach Klassen-, Spezies- und Talentabschnitten geparst oder
übersetzt werden.

## 8. Übersetzung – Foliant fest, Fließtext einfach

### 8.1 Foliant ist die Terminologieautorität

Für Klasse, Unterklasse, Spezies, Hintergrund, Talente, Zauber, Gegenstände, Merkmale, Zustände,
Schadensarten und andere feste Spielbegriffe gilt:

1. exakt über die bestehende Foliant-Logik auflösen,
2. nur `match == "exakt"` ist Identität,
3. Fuzzy-Treffer niemals automatisch übernehmen,
4. bei mehreren exakten Treffern die bestehende kanonische Auswahlregel verwenden,
5. in der PDF exakt die MCP-Anzeigeform verwenden: deutscher Begriff, englisches Original in
   Klammern und gegebenenfalls das Sternchen,
6. offiziellen Treffer als `term_de (term_en)` ohne Stern ausgeben,
7. Community- oder Modellfallback konsistent als `term_de* (term_en)` ausgeben,
8. diese Darstellung gemäß Foliant bei **jeder Nennung** beibehalten; nicht nur beim ersten
   Auftreten und nicht zugunsten kürzerer Texte entfernen.

Die DDB-PDF bleibt Inhaltsquelle. Foliant darf Terminologie bestätigen, aber keine zusätzlichen
Regelabsätze aus privaten Büchern in die PDF kopieren.

### 8.2 Fußnote

Sobald mindestens ein Fallbackbegriff mit `*` vorkommt, erscheint einmal auf Seite 2, unmittelbar
oberhalb der bestehenden rechtlichen WotC-Fußzeile und ohne sie zu überdecken:

`* Keine offizielle deutsche Übersetzung.`

Die Position gehört in die versionierte Feldkarte und muss visuell geprüft werden.

### 8.3 Freier Text

- Beschreibungen und Flavourtext sinngenau, vollständig und ohne Zusammenfassung übersetzen.
- Keine Mechanik ergänzen, entfernen, umformulieren oder auf eine andere Edition umstellen.
- Zahlen, Modifikatoren, Würfelnotationen, SG, Ressourcen, Eigennamen und die vollständigen bereits
  aufgelösten Foliant-Anzeigeformen einschließlich englischer Klammerbegriffe durch Platzhalter
  sperren.
- Ein einziger gebündelter Request mit stabilen Feld-IDs; Ausgabe als streng validiertes JSON mit
  genau denselben Schlüsseln.
- Kein Prompt aus dem PDF darf Systemanweisungen überschreiben. PDF-Inhalt ist untrusted data.
- Fehlende Schlüssel, zusätzliche Schlüssel, veränderte Platzhalter oder ungültiges JSON → einmal
  kontrolliert erneut versuchen, danach vollständig fehlschlagen.
- Pro Request ein Übersetzungsgedächtnis, damit derselbe unbekannte Begriff überall dieselbe
  deutsche Fassung und dasselbe Sternchen erhält.
- Vor dem Rendern eine Restenglisch-Prüfung. Erlaubte Ausnahmen explizit führen: die validierten
  englischen Originalbegriffe innerhalb der Foliant-Klammerdarstellung, Eigennamen, offizielle
  Logos/rechtliche Texte der Hintergrundvorlage und unveränderliche Spielnotation. Englischer
  Erklärungs- oder Flavourtext außerhalb dieser Ausnahmen ist ein Fehler.

### 8.4 Übersetzungsprovider

Ein Claude-Code-Abonnement ist kein API-Zugang für die laufende Website. Implementiere deshalb
einen kleinen Providervertrag und für den MVP genau einen Anthropic-Adapter über das bereits
verwendete `httpx`:

- `ANTHROPIC_API_KEY` ausschließlich aus `.env`, nie aus Browser oder Git,
- `ANTHROPIC_MODEL` ebenfalls aus `.env`; kein möglicherweise veraltetes Modell hart codieren,
- klare Connect-/Read-/Gesamtzeitlimits,
- keine PDF-Datei an den Provider; nur die notwendigen extrahierten Textfelder,
- keine Charakter-/Spielernamen mitsenden, sofern sie nicht für die Übersetzung zwingend nötig sind,
- keine Inhalte oder Antworten loggen,
- automatisierte Tests ausschließlich mit einem Fake-/Mock-Provider.

Fehlende Providerkonfiguration darf den bestehenden Foliant- und MCP-Server nicht am Start hindern.
Nur `POST /bogen` meldet dann die deutsche Fehlermeldung „Übersetzung momentan nicht verfügbar“.

Wenn der Eigentümer keinen Anthropic-API-Key bereitstellt, implementiere und teste Adapter,
Extraktion, Terminologie und Rendering vollständig mit Fakes. Markiere nur den echten
End-to-End-Übersetzungslauf als offen; erfinde keine andere externe API.

## 9. Offiziellen deutschen Bogen ausfüllen

### 9.1 Renderprinzip

- Beide Originalseiten werden unverändert als Vektorhintergrund übernommen.
- Erzeuge pro Seite eine transparente Overlay-Seite in exakt derselben MediaBox.
- Zeichne nur Werte, Texte und Markierungen in die vorgesehenen Bereiche.
- Füge Overlay und Hintergrund zusammen und flache das Ergebnis ab.
- Ergebnis: exakt zwei Seiten, jeweils exakt `603 × 774 pt`.
- Keine Formularfelder, keine zusätzliche Seite, kein alternatives Design und keine
  selbst erfundene Fläche.
- D&D-Logo, Illustrationen und rechtliche WotC-Fußzeile bleiben sichtbar und unverändert.

### 9.2 Versionierte Feldkarten

Lege keine Koordinaten ungeordnet im Renderer ab. Verwende mindestens zwei explizit versionierte
Feldkarten:

- DDB-Quellfingerprint/Feldnamen für die PDFsharp-6.1.1-Exportfamilie,
- Koordinaten, Boxen, Ausrichtung und Schriftgrößen für genau die geprüfte deutsche WotC-Vorlage.

Jede Box kennt mindestens Seite, Rechteck, Standardgröße, Mindestgröße, Zeilenabstand,
Ausrichtung, Ein-/Mehrspaltigkeit und Feldtyp.

### 9.3 Textfluss und harte Overflow-Regel

1. Text passend umbrechen.
2. Bei vorgesehenen großen Merkmalsboxen die vorhandene Mehrspaltigkeit nutzen.
3. Deterministische Schriftgrößenleiter verwenden, beispielsweise
   `8 → 7 → 6.5 → 6 → 5.5 pt`.
4. Unter 5.5 pt nicht weiter verkleinern.
5. Niemals abschneiden, mit Auslassungspunkten kürzen, zusammenfassen oder außerhalb der Box
   zeichnen.
6. Niemals eine dritte Seite oder einen anderen Bogen erzeugen.
7. Passt der vollständige, einem vorhandenen Zielfeld zugeordnete Inhalt nicht, bricht die gesamte
   Konvertierung mit der definierten Overflow-Meldung ab. Es wird keine unvollständige PDF erzeugt.

Das ist die einzige ehrliche Auflösung des Zielkonflikts „beliebig viel DDB-Text“, „nur der
offizielle zweitseitige Bogen“ und „keine Kürzung“.

### 9.4 Einheiten und Mechanik

- Keine Zahlen oder Regeln durch das Sprachmodell umrechnen lassen.
- Offizielle deutsche Maßeinheiten nur über eine kleine, deterministische und getestete Tabelle
  konvertieren, die gegen vorhandene deutsche Foliant-/SRD-Belege geprüft wurde.
- Ist eine Umrechnung nicht belegt, nicht raten; strukturierten Fehler ausgeben oder den Wert als
  unveränderliche Spielnotation behandeln.
- D&D-Regelversion niemals aus dem PDF-Layout ableiten und niemals 2014-Mechanik automatisch in
  2024 umwandeln.

## 10. Datenschutz und Härtung

- Webcontainer erhält keinen Mount auf `data/`, keine Foliant-DB und keine gekauften Quellen.
- Nur die offizielle Vorlage wird read-only gemountet.
- Webcontainer: read-only Root-Dateisystem, `cap_drop: ALL`, `no-new-privileges`, begrenztes
  `tmpfs` für `/tmp`, keine Host-Ports.
- Upload und Ergebnis niemals persistent speichern. Jede temporäre Datei auf jedem Exitpfad löschen.
- Weder Dateiname noch PDF-Inhalt, Charakter-/Spielername, Übersetzung oder Modellantwort loggen.
- Gateway und Uvicorn-Webdienst ohne pfadhaltige Access-Logs betreiben.
- Rate-/Ressourcenschutz: Dateigröße, Seitenzahl, Objektanzahl, PDF-Parsezeit,
  Übersetzungszeit, Renderzeit und eine globale Konvertierungs-Semaphore.
- Ausgabeheader gegen Caching und MIME-Sniffing setzen.
- Private PDFs, Vorlage, echte Übersetzungsantworten, `.env`, Token und Datenbank bleiben aus Git.
- Keine neuen Admin-Webrouten.

Die Website ist laut Projektkontext zunächst ein privater MVP. Diese Umsetzung ist keine
Freigabe für einen anonymen öffentlichen Dienst. Vor öffentlicher Bereitstellung sind Zugriff,
Missbrauchsschutz und rechtliche Pflichten gesondert zu prüfen; füge dafür jetzt keine zusätzlichen
Website-Seiten hinzu.

## 11. Cloudflare- und Connector-Leitplanken

1. Bestehende Domain und Connector-URL bleiben exakt gleich.
2. Keine zweite Subdomain und kein neues Connector-Onboarding.
3. Kein hostname-weites Cloudflare Access: Der Claude-Connector könnte den Browser-Login nicht
   erfüllen.
4. Prüfe vor einem späteren Deploy, ob die in `docs/DEPLOY-raspberry-pi.md` dokumentierte
   hostname-weite WAF-Regel aktiv ist. Sie würde die Website blockieren.
5. Falls aktiv, muss der Eigentümer sie deaktivieren oder nach validierter aktueller
   Cloudflare-Syntax ausschließlich auf MCP-Pfade begrenzen. Niemals den echten geheimen Token in
   eine versionierte Datei schreiben.
6. Der Code kann das Cloudflare-Dashboard nicht ändern. Dokumentiere den manuellen Schritt und
   stoppe vor der tatsächlichen Umschaltung.
7. Umschaltreihenfolge später:
   - Web + Gateway bauen,
   - lokal über Gateway testen,
   - bestehenden Connector durch Gateway vollständig testen,
   - erst dann Tunnel-Origin auf `http://gateway:8080` setzen,
   - sofort Website und bestehenden Claude-Connector testen,
   - bei Fehler Origin auf `http://foliant:8000` zurücksetzen.

## 12. Erwartete Dateien

Die konkrete Aufteilung darf nach dem Vorabplan leicht abweichen, aber Verantwortlichkeiten müssen
getrennt bleiben.

### Neu

- `app/charakterbogen/__init__.py`
- `app/charakterbogen/modelle.py`
- `app/charakterbogen/ddb_pdf.py`
- `app/charakterbogen/merkmale.py`
- `app/charakterbogen/terminologie.py`
- `app/charakterbogen/uebersetzer.py`
- `app/charakterbogen/de_bogen.py`
- `app/charakterbogen/web.py`
- `app/charakterbogen/intern.py` – schmale Foliant-interne Terminologie-Route
- `app/charakterbogen/feldkarten/ddb_pdfsharp_6_1.json`
- `app/charakterbogen/feldkarten/de_wotc_2025.json`
- `app/charakterbogen/templates/index.html`
- `app/charakterbogen/static/site.css`
- `deploy/Caddyfile`
- `tests/test_charakterbogen_ddb.py`
- `tests/test_charakterbogen_uebersetzung.py`
- `tests/test_charakterbogen_pdf.py`
- `tests/test_charakterbogen_web.py`
- `tests/test_gateway_routing.py`
- `docs/CHARAKTERBOGEN-MVP.md`

### Voraussichtlich ändern

- `app/server.py` – nur Registrierung der schmalen internen Terminologie-Route; MCP-Pfad und Tools
  unverändert
- `docker-compose.yml` – Web- und Gateway-Service, private Netze/Mounts/Härtung
- `requirements.txt` – direkt verwendete PDF-/Multipart-Pakete exakt pinnen
- `.env.example` – leere Provider-/interne Tokenvariablen
- `tests/test_zugriff.py` und `tests/test_tool_vertrag.py` nur additiv zur Absicherung, nie
  abschwächen
- `Makefile` – neue Tests im bestehenden Gate, sofern nicht ohnehin automatisch enthalten
- `CLAUDE.md`
- `README.md`
- `PROJEKT-UEBERSICHT.md`
- `SECURITY.md`
- `docs/DEPLOY-raspberry-pi.md`
- `docs/RUNBOOK.md`

### Voraussichtlich nicht ändern

- `db/schema.sql`
- `app/glossar.py` – vorhandene Logik nur wiederverwenden
- öffentliche MCP-Tools und ihre Schemas
- `config/stil.py`
- `docs/CLAUDE-PROJEKT-ANWEISUNG.md`
- bestehende Importer
- `FOLIANT_PFAD_TOKEN` oder dessen öffentlicher Pfad

Direkt importierte Pakete dürfen nicht nur zufällig transitiv vorhanden sein. Ermittle kompatible
Versionen, pinne sie exakt und dokumentiere den bewussten Pin. Verwende bevorzugt `pypdf` für
Struktur/Merge, `reportlab` für das Overlay und die vorhandene Poppler-Werkzeugkette für visuelle
Abnahme. Führe keine schwere Browser-/Chromium-Abhängigkeit ein.

## 13. Tests

### 13.1 Automatisch, nur synthetische Fixtures

1. Nicht-PDF → 400.
2. Gültige Nicht-DDB-PDF → 422.
3. Verschlüsselte, aktive oder übergroße PDF → sichere Ablehnung.
4. Synthetische direkte DDB-Widgets werden auch ohne Catalog-AcroForm gelesen.
5. Fehlende Pflichtwidgets oder veränderter Fingerprint → Ablehnung statt Raten.
6. Alle modellierten Feldwerte, Häkchen, Zahlen und Vorzeichen bleiben erhalten.
7. `FeaturesTraits1…6` werden ohne Zeichenverlust und in richtiger Reihenfolge verbunden.
8. Nur exakte Foliant-Treffer gelten; fuzzy Treffer werden nie automatisch übernommen.
9. Offizieller Begriff erscheint als `Mönch (Monk)` ohne `*`; Fallback erscheint als
   `Nebelwanderer* (Mist Wanderer)` mit `*`.
10. Die vollständige MCP-Anzeigeform steht bei jeder Nennung; die englische Klammer wird weder
    entfernt noch nur auf die erste Nennung beschränkt.
11. Fake-Übersetzer beweist: gleiche Keys, gesperrte Zahlen/Würfel/Begriffe unverändert,
    ungültiges JSON und veränderte Platzhalter werden abgelehnt.
12. Ergebnis hat exakt zwei Seiten und beide MediaBoxen `603 × 774 pt`.
13. Hintergrundinhalte und WotC-Fußzeile bleiben vorhanden.
14. Kein Text überschreitet seine Box; Overflow erzeugt Fehler und keine PDF.
15. Sternchen erzeugt genau einmal die Fußnote, ohne WotC-Text zu überdecken.
16. `GET /` enthält genau Dateifeld, Hauptbutton und Statusbereich; keine Optionen/Navigation.
17. Semaphore, Zeitlimit und `no-store`-Header greifen.
18. Temporäre Dateien werden auch bei Parser-, Provider- und Renderfehlern entfernt.
19. Gateway-Vertrag: Root → Web; `/health`, `/ready`, `/mcp`, `/<segment>/mcp` → Foliant.
20. Gateway leakt/ändert keinen `CF-Connecting-IP` und puffert MCP nicht.
21. Bestehender Geheimpfadtest, IP-Allowlisttest und 16-Tool-Vertrag bleiben unverändert grün.

Keine privaten Binärdateien, echten Charakterdaten oder Modellantworten in automatischen Tests.
Erzeuge kleine synthetische PDFs beziehungsweise Widget-Fixtures im Testlauf.

### 13.2 Private lokale End-to-End-Abnahme

Mit den zwei übergebenen privaten PDFs:

1. DDB-Beispiel wird sicher erkannt.
2. Extraktionsbericht lokal prüfen: Werte, Fertigkeiten, Merkmale, Zauber, Ausrüstung.
3. Mit Fake-Provider deterministischen vollständigen Rundlauf erzeugen.
4. Mit echtem Provider nur nach gesetztem API-Key übersetzen.
5. Ergebnis per `pdfinfo` prüfen.
6. Beide Seiten mit Poppler mindestens bei 144 dpi rendern.
7. Jede Seite visuell prüfen: Ausrichtung, Umlaute, Häkchen, Lesbarkeit, kein Überlauf, keine
   Überdeckung der rechtlichen Fußzeile.
8. Pixel-/Rastervergleich außerhalb der deklarierten Overlay-Rechtecke: Hintergrund unverändert.
9. Private Testausgaben anschließend löschen.

### 13.3 Connector-End-to-End

Vor jeder Cloudflare-Umschaltung lokal durch den Gateway:

1. vorhandene geheime Connector-URL: initialize erfolgreich,
2. tools/list liefert weiterhin genau 16 Tools,
3. `foliant_uebersetze_begriff` funktioniert,
4. gültiger MCP-Pfad + fremde `CF-Connecting-IP` → 403,
5. gültiger Pfad + Anthropic-Egress → Erfolg,
6. falscher Token + fremde IP → 403,
7. falscher Token + erlaubte IP → 404, niemals Website-HTML,
8. `/mcp` ist im Produktionsmodus kein offener Connector,
9. `/health` liefert weiterhin das bisherige Foliant-JSON,
10. `/ready` bleibt echte DB-Readiness.

## 14. Abnahmekriterien

Der Auftrag ist erst fertig, wenn alle folgenden Aussagen belegt sind:

- `GET /` zeigt eine schmale deutsche Uploadseite mit genau einem Dateifeld und einer
  Hauptschaltfläche.
- Nur die unterstützte DDB-Exportfamilie wird angenommen.
- Die Ausgabe verwendet nachweislich die lokal bereitgestellte offizielle deutsche WotC-PDF als
  Hintergrund.
- Ausgabe: exakt zwei Seiten, exakt dieselben MediaBoxen, keine Zusatzseite, kein alternatives oder
  selbst gestaltetes Layout.
- Alle Erklärungen, Aktionen, Regeln, Feldinhalte und Beschreibungen sind auf Deutsch. Englisch
  bleibt nur als validiertes Original in der Klammerdarstellung eines Foliant-Begriffs, als
  definierter Eigenname oder als unveränderter offizieller Hintergrundbestandteil sichtbar.
- Feststehende Begriffe folgen einschließlich englischem Original in Klammern exakt Foliant und
  erscheinen so bei jeder Nennung; kein fuzzy Begriff wird still übernommen.
- Stufen ohne offiziellen deutschen Begriff sind konsistent mit `*` markiert und die Fußnote ist
  vorhanden.
- Zahlen, Würfelwerte, Modifikatoren, SG, Ressourcen und Checkboxzustände stimmen mit dem DDB-PDF
  überein.
- Kein Feld wird abgeschnitten, zusammengefasst oder unter die Mindestschriftgröße gedrückt.
- Bei Overflow wird keine PDF erzeugt.
- Upload und Ergebnis landen nicht auf persistentem Speicher und erscheinen nicht in Logs.
- Webcontainer hat keinen DB-/Kaufbuch-Mount und kennt den öffentlichen MCP-Pfadtoken nicht.
- Bestehende Connector-URL, Geheimpfad, IP-Filter, Toolzahl und Toolschemas bleiben unverändert.
- Vollständiges bestehendes `make test` sowie alle neuen Tests sind grün.
- `docker compose config` ist gültig; neue Dienste haben keine öffentlichen `0.0.0.0`-Ports.
- Git-Diff enthält keine PDF, keine Charakterdaten, keine privaten Buchtexte und kein Secret.
- Reale Cloudflare- und Pi-Umschaltung ist entweder mit ausdrücklicher Erlaubnis erfolgreich
  abgenommen oder im Abschlussbericht klar als manuell offen markiert.

## 15. Verifikation

Mindestens ausführen und Ergebnisse exakt berichten:

```sh
.venv/bin/python -m pytest -q \
  tests/test_charakterbogen_ddb.py \
  tests/test_charakterbogen_uebersetzung.py \
  tests/test_charakterbogen_pdf.py \
  tests/test_charakterbogen_web.py \
  tests/test_gateway_routing.py \
  tests/test_zugriff.py \
  tests/test_tool_vertrag.py
```

```sh
make test
```

```sh
docker compose config
docker compose build foliant web gateway
docker compose up -d foliant web gateway
docker compose ps
```

Lokaler Gateway-Rundlauf, Port gemäß finalem Compose:

```sh
curl -fsS http://127.0.0.1:8080/ -o /tmp/charakterbogen-start.html
curl -f -F "datei=@/Users/davidtrogemann/Downloads/Magnetron44523_168310785.pdf" \
  http://127.0.0.1:8080/bogen \
  -o /tmp/Magnetron-deutsch.pdf
pdfinfo /tmp/Magnetron-deutsch.pdf
pdftoppm -png -r 144 /tmp/Magnetron-deutsch.pdf /tmp/Magnetron-deutsch
```

Abschließend:

```sh
git diff --check
git status --short
```

## 16. Stop-Bedingungen

Stoppe, ändere nichts weiter und berichte konkret, wenn:

- der offizielle deutsche Bogen nicht vorliegt oder seine Prüfsumme abweicht,
- der DDB-Beispielbogen nicht zur dokumentierten Exportfamilie passt,
- DDB-Inhalte oder Editionen nur durch Raten zugeordnet werden könnten,
- der vollständige zugeordnete Text selbst bei Mindestschriftgröße nicht in die offiziellen
  Zielfelder passt,
- eine Lösung den bestehenden Connector-Pfad, IP-Filter, Streamingvertrag oder die 16 Tools
  verändern würde,
- eine Lösung den Webcontainer an die private Foliant-DB oder gekaufte Quellen mounten müsste,
- der öffentliche MCP-Token an Browser, Weblogs oder PDF-Verarbeitung weitergereicht werden müsste,
- der einzige verbleibende Weg Zusatzseiten, ein anderes Layout, Kürzung oder stillen Textverlust
  erfordern würde,
- ein echter Übersetzungslauf nötig ist, aber kein API-Key/Modell bereitgestellt wurde,
- Cloudflare-/Pi-Änderungen nötig werden, aber noch keine ausdrückliche Deploy-Erlaubnis vorliegt.

## 17. Abschlussbericht

Liefere:

- neue und geänderte Dateien mit Zweck,
- Architektur und tatsächliche Container-/Routingstruktur,
- DDB-Fingerprint und Feldabdeckung,
- bewusst nicht zugeordnete DDB-Felder,
- Terminologie- und Fallbacknachweis,
- tatsächlich ausgeführte Tests samt Ergebnis,
- visuelle PDF-Abnahme mit Seitenzahl/MediaBox/Overflow-Befund,
- Connector-End-to-End-Befund,
- Secret-/Temp-/Git-Prüfung,
- noch offene echte Provider-, Pi- oder Cloudflare-Abnahme,
- keine Behauptung, ein nicht durchgeführter Live-Test sei erledigt.

## 18. Copy-&-Paste-Startprompt

```text
Arbeite im vorhandenen Foliant-Repository. Lies zuerst CLAUDE.md,
PROJEKT-UEBERSICHT.md und
docs/CLAUDE-CODE-AUFTRAG-CHARAKTERBOGEN-MVP.md vollständig. Der Auftrag in dieser
Datei ist verbindlich; insbesondere darf ausschließlich der offizielle deutsche
WotC-Charakterbogen ausgefüllt werden. Kein anderer Bogen, keine Zusatzseite und
keine Kürzung.

Die beiden unveränderten offiziellen PDF-Dateien liegen ausschließlich hier:
- deutsche Zielvorlage:
  vorlagen/charakterboegen/offiziell/Charakterbogen_2024_DE.pdf
- englische strukturelle Referenz:
  vorlagen/charakterboegen/offiziell/Character_Sheet_2024_EN.pdf
Für die Ausgabe darf nur die deutsche Zielvorlage verwendet werden. Die englische
PDF dient ausschließlich zum strukturellen Abgleich. Der Ordner vorlagen/ ist vom
MCP-Quellenbestand getrennt: Importiere diese PDFs nicht in den MCP und lege keine
Charakterbogen-Vorlage unter quellen/ ab.

Prüfe vor Änderungen git status und die bestehende Test-Baseline. Untersuche danach
den privaten DDB-Beispielbogen, die deutsche Zielvorlage und die englische Referenz
strukturell und visuell. Lege einen dateikonkreten Plan vor und implementiere in
kleinen, getesteten Phasen.

Die Website bleibt ein schmaler MVP mit genau einer Uploadseite und einem
Konvertierungsendpunkt. Feststehende Begriffe müssen aus derselben Foliant-Logik wie
das bestehende MCP stammen; freie Beschreibungen werden vollständig und sinngenau
übersetzt. Jeder Foliant-Begriff erscheint bei jeder Nennung in der vollständigen
MCP-Darstellung: deutscher Begriff, gegebenenfalls *, danach das englische Original
in Klammern. Englischer Erklärungs- oder Flavourtext bleibt nicht stehen. Der bestehende Connector
unter https://dnd.magnetron.me/<FOLIANT_PFAD_TOKEN>/mcp, sein IP-Filter, Streaming,
seine 16 Tools und seine URL müssen unverändert funktionieren.

Nimm keine Pi- oder Cloudflare-Umschaltung vor, committe und pushe nichts ohne meine
ausdrückliche Erlaubnis. Stoppe bei jeder in Kapitel 16 genannten Bedingung und
berichte den konkreten Konflikt, statt Anforderungen still zu umgehen.
```
