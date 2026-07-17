# MCP- und Technikreview: Foliant

## 1. Metadaten der Review

| Feld | Wert |
|---|---|
| Reviewer | `codex` |
| Review-Typ | MCP- und Technikreview |
| Datum | 2026-07-12 |
| Git-Commit | `5cc67289a8066ce83b3a62aa9822165b1acfacbb` |
| Branch | `main` |
| Projektzustand zu Beginn | sauber (`git status --short --branch`: nur `## main`) |
| Sprache/Runtime | Python; lokal Python 3.13.5, Containerbasis Python 3.12 |
| MCP-Framework | FastMCP `2.14.7` |
| MCP-SDK | `mcp 1.28.1` (transitive Abhängigkeit) |
| Transport | Streamable HTTP über FastMCP/ASGI/Uvicorn; zusätzlich nicht dokumentierter FastMCP-Standardlauf bei direktem `app.server`-Start |
| Vorgesehener Client | Claude Custom Connector; lokale MCP-Clients sind technisch ebenfalls möglich |
| MCP-Oberfläche | 16 Tools, keine Resources, keine Resource Templates, keine Prompts |
| Ausgeschlossene Inhalte | sämtliche bestehenden Dateien unter `docs/reviews`; sie wurden weder gelesen noch durchsucht |

### Ausgeführte Prüfungen

- Repository-Inventar unter ausdrücklichem Ausschluss von `docs/reviews` sowie Sichtung von Code, Schemas, Konfiguration, Dokumentation, Tests und Importpfaden.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider`: **98 bestanden, 5 übersprungen**.
- Derselbe Lauf mit `-rs`: übersprungen wurden DDB-Module, ein manueller Verhaltenstest und die nicht lokal verfügbare OCR-Integration.
- `PYTHONDONTWRITEBYTECODE=1 .venv-ddb/bin/python -m pytest ...`: **24 bestanden, 1 fehlgeschlagen**.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tests.smoke_test`: **OK**, alle 16 Tools gegen die lokale Datenbank aufgerufen.
- `.venv/bin/python -m app.admin check`: SQLite-/FTS-/FK-Prüfungen bestanden; 176 Einträge mit als Warnung klassifizierten HTML-Resten; Exitcode dennoch 0.
- `.venv/bin/python -m app.admin status`: lokale Datenbank mit 2.621 Einträgen, 2 Quellen und ausschließlich Edition 2024.
- `.venv/bin/python -m pip check`: keine gebrochenen installierten Abhängigkeiten.
- AST-Parsing aller 46 versionierten Python-Dateien: erfolgreich.
- FastMCP-In-Process-Handshake: 16 Tools gelistet; strukturierter Tool-Aufruf erfolgreich.
- Introspektion sämtlicher generierter Ein- und Ausgabeschemas.
- Gezielte Negativ- und Rundlaufprüfungen für ungültige Parameter, Quellenfilter, Glossar, Mehrdeutigkeit und geteilte Statblöcke.
- Git-Status mehrfach geprüft.

### Fehlgeschlagene oder nicht mögliche Prüfungen

- Der erste Lauf mit dem unvorbereiteten System-Python scheiterte erwartbar bei der Collection an fehlendem `rapidfuzz` und `starlette`; bewertet wird deshalb der dokumentierte `.venv`-Lauf.
- Ein lokaler Uvicorn-Socket konnte wegen der Ausführungs-Sandbox nicht gebunden werden. Die MCP-Grenze wurde stattdessen mit FastMCP-In-Process-Client und vorhandenen ASGI-Tests geprüft; ein echter Streamable-HTTP-End-to-End-Test bleibt offen.
- Docker/Compose-Build, ARM64-Ausführung, Cloudflare Tunnel, Live-Pi und echter Claude-Connector wurden nicht ausgeführt.
- OCR-End-to-End war lokal mangels OCRmyPDF/Tesseract nicht möglich.
- Echte DDB- und Open5e-Netzaufrufe wurden nicht ausgeführt; die Importtests arbeiten offline bzw. mit Fakes.
- `ruff`, `mypy` und `pip-audit` sind nicht installiert; es wurde daher kein Lint-, statischer Typ- oder CVE-Scan ausgeführt.
- Die dokumentierte Produktionsdatenbank mit etwa 9.490 Einträgen aus 12 Quellen war nicht Teil des Workspace. Aussagen dazu konnten nicht verifiziert werden.

## 2. Executive Summary

Foliant besitzt für einen internen Prototyp eine bemerkenswert solide Basis: verständliche Tool-Namen, eine sinnvolle Trennung von Suche und Detailabruf, editionsgetrennte Retrieval-Pfade, parametrisierte SQL-Abfragen, eine offline arbeitende Laufzeit und sorgfältig abgesicherte Importoperationen. Der DDB-Exporter ist gegenüber ZIP-Slip, Zip-Bombs und Secret-Leaks deutlich besser gehärtet als für ein typisches MVP.

Das Projekt ist dennoch **noch nicht zuverlässig genug für externe Nutzertests**. Zwei reproduzierbare Retrieval-Fehler betreffen den Kernnutzen direkt: `Aktionen` wird über die fuzzy Glossar-Brücke als `Reaktionen (Reactions)` behandelt, und der Monsterabruf für `Solar` liefert nur einen gleichnamigen Teil-Chunk ohne RK/TP. Außerdem kann ein explizit nach Quelle gefilterter Suchtreffer nicht stabil in den Detailabruf übernommen werden. Das System kann dadurch eine formal belegte, aber sachlich falsche oder unvollständige Antwort liefern.

Der Spoilerschutz ist architektonisch nicht durchgesetzt: Der DDB-Katalog importiert Abenteuer-/Setting-/Playtest-Inhalte bewusst, überträgt die Warnklassifikation aber weder in Artefakt noch Datenbank. Das widerspricht dem verbindlichen MVP-Scope. Hinzu kommen eine fail-open konfigurierbare Zugangskontrolle, ein im URL-Pfad liegendes und protokolliertes Zugangstoken sowie ein Serving-Container, der den gesamten Datenbereich einschließlich privater Artefakte beschreibbar sieht.

**Gesamturteil:** guter funktionaler Solo-/Entwicklungsprototyp, aber kein freigabereifer Mehrnutzer-MVP. Vor dem nächsten internen Abnahmelauf sollten die Retrieval-Identität, Glossarlogik, stabilen Referenzen, Schemas und die rote DDB-Suite korrigiert werden. Vor externen Nutzertests müssen Spoiler-/Quellenscopes und die Serving-Isolation serverseitig erzwungen werden.

## 3. Untersuchungsumfang und Vorgehen

Die Review folgte dem Laufweg einer Nutzerfrage und dem Lebenszyklus einer Quelle:

1. MCP-Initialisierung, Tool-Registrierung und generierte Verträge.
2. Eingabevalidierung, Suchstufen, Ranking, Deduplizierung und Detailauswahl.
3. Herkunft, Version, Übersetzung und Darstellung der Tool-Ausgaben.
4. PDF-, Markdown-, Open5e-, Glossar- und DDB-Import bis zum SQLite-Bestand.
5. Zugriffsschutz, Containergrenzen, Secret-Verarbeitung und Betriebsdiagnose.
6. Unit-, Integrations-, Smoke- und Abnahmetests sowie deren tatsächliche Ausführbarkeit.
7. Abgleich von README, Anforderungen, Technikdokumentation und Code.

Die fachliche Richtigkeit einzelner D&D-Regeln wurde nicht bewertet. Reale Inhalte wurden nur benutzt, um technische Eigenschaften wie Identität, Vollständigkeit, Klassifikation und Rückverfolgbarkeit zu prüfen.

## 4. Überblick über die untersuchte Architektur

```text
Claude/anderer MCP-Client
        |
        | Streamable HTTP
        v
Cloudflare Tunnel -> ZugriffsFilter -> FastMCP -> 16 synchrone Tools
                                             |
                                             v
                                     SQLite + FTS5
                                             ^
                                             |
      PDF/OCR/Markdown  Open5e  Glossar  DDB-Artefakt-Importer
                                             ^
                                             |
                                  separater DDB-Exporter
```

- `app/server.py` erzeugt den FastMCP-Server, registriert 16 Tools und baut die HTTP-App.
- `app/tools/nachschlagen.py` stellt Suche, Detailabrufe und Glossarzugriff bereit.
- `app/tools/charakter.py` stellt Optionslisten und eine begrenzte Build-Prüfung bereit.
- `app/db.py` kapselt Verbindungen, FTS, Glossarbrücke, Ranking und Deduplizierung.
- `db/schema.sql` modelliert Quellen, flache Einträge, drei ungenutzte Metatabellen, Glossar und FTS.
- `importer/` enthält mehrere offline bzw. einmalig netzgebundene Importpfade.
- `docker-compose.yml` kombiniert Runtime, Cloudflare Tunnel, optionale Datasette und den kurzlebigen DDB-Exporter.

Tools sind für die aktiven Aktionen grundsätzlich die richtige MCP-Primitive. Ein Quellenkatalog, stabile Eintragsrepräsentationen und Attribution wären zusätzlich als Resources sinnvoll. Prompts sind optional; Sicherheits- oder Grounding-Garantien dürfen nicht von ihnen abhängen.

## 5. Stärken des Projekts

- **Gute Tool-Ergonomie:** konsistentes Präfix `foliant_`, klare Verben und eine grundsätzlich sinnvolle Search-/Detail-Trennung.
- **Editionsbewusstsein:** 2024 ist Standard; andere Editionen werden getrennt zurückgegeben statt still vermischt.
- **Nachvollziehbare Ausgaben:** Detailantworten enthalten Quelle, Edition, optionale Seite und Lizenz.
- **Sichere SQL-Basis:** FTS-Operatoren werden neutralisiert; dynamische Filter verwenden Parameterbindung.
- **Threading-tauglicher DB-Zugriff:** pro synchronem Tool-Aufruf wird eine eigene SQLite-Verbindung geöffnet und zuverlässig geschlossen.
- **Robuste Importtransaktionen:** vollständiges Vorbereiten vor dem Ersetzen, Schrumpfschutz, FTS-Rebuild, Integritätsprüfung und atomare Aktivierung reduzieren Datenverlustrisiken.
- **Starker DDB-Exporter:** getrennte Abhängigkeiten, kurzlebiger Container, kein DB-Mount, Secret nur im Speicher/TTY/Secret-File, Downloadlimits, ZIP-Slip-/Symlink-/Zip-Bomb-Schutz.
- **Offline Serving:** Regelabrufe benötigen zur Laufzeit weder DDB noch Open5e oder Glossar-API.
- **Ehrliche Build-Grenzen:** die Build-Prüfung dokumentiert nicht prüfbare Aspekte und trennt `unvollständig` von einem begrenzten Legalitätsurteil.
- **Gute Testbasis:** 98 grüne Standardtests plus ein echter Daten-Smoke; viele frühere Fehler sind als konkrete Regressionstests festgehalten.
- **Container-Grundlagen:** Runtime läuft als Nicht-Root; der Host-Port ist nur an Loopback gebunden.

## 6. Kritische und hohe Befunde

Es wurde kein Befund der Stufe **Kritisch** vergeben. Die folgenden hohen Befunde blockieren jedoch zuverlässige externe Nutzertests.

### TECH-001: Fuzzy Glossartreffer werden als exakte fachliche Identität behandelt

- **Schweregrad:** Hoch
- **Bereich:** Retrieval, Glossar, Halluzinationsschutz
- **Dateien/Stellen:** `app/glossar.py:48-90` (`lookup`), `app/db.py:138-168` (`_glossar_alternativen`), `app/tools/nachschlagen.py:223-246` (`_hole_detail`)
- **Status:** sicher nachgewiesen
- **Beobachtung:** `lookup` liefert fuzzy Treffer zusätzlich zu exakten Treffern, ohne Matchtyp oder Score im Ergebnis zu behalten. `_glossar_alternativen` übernimmt diese Vorschläge als Übersetzungsvarianten; `_hole_detail` behandelt sie anschließend als exakt. Reproduzierbar liefert `foliant_uebersetze_begriff("Aktionen")` den offiziellen Begriff `Reaktionen (Reactions)`, und `foliant_hol_regel("Aktionen")` gibt einen Reaktionen-Eintrag von Seite 299 zurück.
- **Auswirkung:** Das System erzeugt eine falsche, aber scheinbar offizielle und belegte Auskunft. Genau dieser Fehler ist gefährlicher als ein ehrliches `nicht gefunden`.
- **Empfehlung:** Exakte Glossarbeziehungen und fuzzy Suchvorschläge als verschiedene Typen modellieren. Identität, kanonische Anzeige und Deduplizierung dürfen ausschließlich exakte, kuratierte Beziehungen verwenden. Fuzzy darf nur Kandidaten mit Score liefern und nie ohne Rückfrage zum Detailtreffer werden.
- **Abnahmebeispiel:** `Aktionen`, `Action`, `Reaktionen` und `Reactions` müssen getrennte Konzepte bleiben; ein Tippfehler darf höchstens einen als fuzzy markierten Kandidaten erzeugen.

### TECH-002: Namensbasierte Deduplizierung verschluckt unterschiedliche Inhalte und Teil-Chunks

- **Schweregrad:** Hoch
- **Bereich:** Identität, Mehrdeutigkeit, Vollständigkeit
- **Dateien/Stellen:** `app/db.py:240-307` (`_dedupe_und_sortiere`), `app/tools/nachschlagen.py:200-265` (`_hole_detail`), `db/schema.sql:18-28`
- **Status:** sicher nachgewiesen
- **Beobachtung:** Identität besteht im Wesentlichen aus normalisiertem Namen, Edition und Kategorie. Kontext, Inhaltshash und externe ID fehlen. Unterschiedliche Treffer werden nach Quellenpriorität auf einen Text reduziert; weitere Varianten erscheinen höchstens als Quellentitel. Bei mehreren exakten Detailkandidaten wird der erste gewählt. Im lokalen Bestand existieren zahlreiche gleichnamige Einträge mit unterschiedlichen Bodies.
- **Konkrete Reproduktionen:** `foliant_hol_monster("Solar")` liefert einen 1.322 Zeichen langen Aktionsblock, aber weder `**RK** 21` noch `**TP** 297`; der Basisteil liegt in einem zweiten gleichnamigen Chunk. `foliant_hol_gegenstand("Rüstung")` wählt ohne Mehrdeutigkeitsmeldung den Abschnitt über magische Rüstungen, obwohl mehrere verschiedene gleichnamige Einträge existieren.
- **Auswirkung:** Vollständige Steckbriefe können unvollständig sein; echte Mehrdeutigkeit und Textkonflikte werden als eindeutige Antwort dargestellt. B4 und die zugesagte Steckbrief-Vollständigkeit sind damit nicht erfüllt.
- **Empfehlung:** Stabile `concept_id` und `entry_variant_id` einführen. Kontext und Quelle gehören zur Variante. Varianten nur bei gleichem normalisiertem Inhaltshash automatisch zusammenfassen; andernfalls `ambiguous` oder `conflict` zurückgeben. Geteilte Statblöcke beim Import deterministisch aggregieren und mit Pflichtfeldtests prüfen.

### TECH-003: Quellenfilter und Detailabruf bilden keinen reproduzierbaren Rundlauf

- **Schweregrad:** Hoch
- **Bereich:** MCP-Tool-Vertrag, Provenienz
- **Dateien/Stellen:** `app/db.py:121-134` (`_roh_suche`), `app/tools/nachschlagen.py:48-57` (`_knapp`), `app/tools/nachschlagen.py:200-265` (`_hole_detail`)
- **Status:** sicher nachgewiesen
- **Beobachtung:** Der Eingabeparameter `quelle` erwartet intern `q.kuerzel`; Suchtreffer geben aber nur `quelle_titel` aus. Der zurückgegebene Titel als erneuter Filter liefert null Treffer. Detailtools akzeptieren weder Quellenbindung noch ID. Eine Suche nach `Fireball` mit `quelle="open5e-srd-2024"` liefert Open5e, der anschließende Detailabruf per Name wechselt zurück zum deutschen SRD-Prioritätseintrag.
- **Auswirkung:** Ein Modell kann einen ausgewählten Treffer nicht zuverlässig nachladen. Explizite Nutzerwünsche nach einer Quelle können beim Detailabruf verletzt werden.
- **Empfehlung:** Suchtreffer müssen eine stabile `entry_ref`, `source_key`, `source_revision` und optional `resource_uri` liefern. Detailabruf primär per `entry_ref`; Name nur als Komfortpfad mit echter Ambiguitätsantwort. Zusätzlich ein Quellenkatalog mit zulässigen Keys.

### TECH-004: Abenteuer-/Spoilerinhalte werden entgegen dem MVP-Scope unisoliert importiert

- **Schweregrad:** Hoch
- **Bereich:** Scope, Datenschutz, Wissensklassifikation
- **Dateien/Stellen:** `docs/foliant-anforderungen.md:155-169,223-233`, `importer/ddb_exporter/katalog.py:87-103`, `importer/ddb_exporter/cli.py:251-265`, `importer/ddb_exporter/artifact.py:83-125`, `db/schema.sql:5-28`
- **Status:** sicher nachgewiesene Modell- und Pipeline-Lücke; tatsächliche Offenlegung hängt vom Produktionsbestand ab
- **Beobachtung:** Der verbindliche Scope schließt Abenteuer-/Kampagneninhalte aus. Der Katalog setzt solche Bücher bewusst auf `importieren=True` und erzeugt nur einen Konsolenhinweis. `cmd_sync` übernimmt diesen Hinweis nicht in `buch`; Manifest und Hauptschema kennen weder `content_scope`, `audience`, `spoiler` noch `access_class`. Unbekannte Breadcrumbs fallen zusätzlich pauschal auf Kategorie `regel` zurück.
- **Auswirkung:** Lore, SL-Informationen und Spoiler können wie normale Spielerregeln durchsucht werden. Die einzige verbleibende Schranke ist eine Modellinstruktion; sie ist nicht deterministisch und widerspricht der dokumentierten strukturellen Isolation.
- **Empfehlung:** Für den MVP Abenteuer/Setting/Playtest standardmäßig nicht importieren. Alternativ eigener Snapshot/Server mit separater Berechtigung. Klassifikation muss im Katalog beginnen, im Manifest signiert erhalten bleiben, in der DB gespeichert und serverseitig vor Retrieval gefiltert werden. Unsichere Klassifikation kommt in Quarantäne.

### TECH-005: Zugangskontrolle ist fail-open konfigurierbar und der URL-Schlüssel wird geloggt

- **Schweregrad:** Hoch
- **Bereich:** Authentisierung, Secrets, Logging
- **Dateien/Stellen:** `app/server.py:67-79`, `app/zugriff.py:75-103`, `docker-compose.yml:18-22`, `Dockerfile:29`, `.env.example:9-19`
- **Status:** sicher nachgewiesenes Konfigurationsrisiko; Uvicorn-Access-Log-Wirkung aus der Standardkonfiguration abgeleitet
- **Beobachtung:** Ein leerer oder schwacher `FOLIANT_PFAD_TOKEN` verhindert den Start nicht; Compose defaultet auf leer. Die IP-Allowlist authentisiert ein gemeinsames Egress-Netz, keinen Nutzer. Das Token ist Bestandteil jedes Pfads. Der eigene Filter loggt bei Blockaden den vollständigen Pfad; Uvicorn startet ohne Deaktivierung/Redaktion des Access-Logs.
- **Auswirkung:** Fehlkonfiguration reduziert den Schutz auf eine gemeinsame Egress-IP. Das Bearer-Äquivalent landet in Routine-Logs und ist weder pro Nutzer widerrufbar noch sauber auditierbar. Bei servierten privaten Büchern ist das ein erhebliches Weitergaberisiko.
- **Empfehlung:** Produktionsmodus explizit machen und ohne gültige starke Authentisierung hart abbrechen. Für die Veröffentlichung MCP-OAuth bzw. vorgelagerte Identität mit Scopes verwenden. Bis dahin Tokenlänge validieren, Pfade vollständig redigieren, Access-Logs anpassen, Logrotation setzen und Token nach Umstellung rotieren.

### TECH-006: Der öffentlich erreichbare Runtime-Container sieht private Daten beschreibbar

- **Schweregrad:** Hoch
- **Bereich:** Least Privilege, Datenisolation
- **Dateien/Stellen:** `docker-compose.yml:11-16`, `Dockerfile:4-29`, `app/db.py:60-67`
- **Status:** sicher nachgewiesen
- **Beobachtung:** `./data` wird vollständig und beschreibbar nach `/app/data` gemountet. Darunter liegen laut Projektarchitektur auch private DBs, Backups, Arbeitsdaten und DDB-Artefakte. Die Runtime öffnet SQLite schreibbar. Das Image enthält neben dem Server auch Admin-, Import-, OCR- und Build-Werkzeuge; Root-Dateisystem und Linux-Capabilities werden für den Serving-Dienst nicht weiter eingeschränkt.
- **Auswirkung:** Eine Kompromittierung der Runtime erhält mehr Daten und Schreibmöglichkeiten als für Retrieval nötig. Backups und private Rohdaten liegen in derselben Vertrauenszone wie der Internet-Endpunkt.
- **Empfehlung:** Eigenes minimales Serve-Image und eigener Compose-Dienst. Nur einen freigegebenen Korpus-Snapshot read-only mounten; `data/private` nie in den Serve-Container. SQLite per URI `mode=ro&immutable=1` und `PRAGMA query_only=ON`; `read_only`, `no-new-privileges`, `cap_drop: ALL` und begrenztes tmpfs setzen.

### TECH-007: Claude-Code-Berechtigungen können die eigenen Secret-Denies umgehen

- **Schweregrad:** Hoch
- **Bereich:** Prompt Injection, Entwicklerumgebung
- **Datei/Stelle:** `.claude/settings.json:3-123`
- **Status:** sicher nachgewiesene Konfigurationslücke; Ausnutzung erfordert eine fehlgeleitete oder manipulierte Agentensitzung
- **Beobachtung:** Secret-, `.env`- und Datenbankzugriffe werden für `Read/Edit/Write` untersagt, gleichzeitig sind unter anderem beliebige `python *`, `curl *`, `ssh *`, `scp *`, `rsync *`, `docker *`, `chmod *` und `git add *` automatisch erlaubt. Ein erlaubter Python- oder Shell-Aufruf kann die über Toolnamen formulierten Read-Denies technisch umgehen und Daten exfiltrieren.
- **Auswirkung:** Prompt Injection in Repository- oder Importinhalten kann in der Entwicklerumgebung weitreichende lokale und Netzwerkaktionen ohne erneute Bestätigung anstoßen. Die Deny-Liste vermittelt eine Schutzwirkung, die sie nicht durchsetzt.
- **Empfehlung:** Breite Interpreter-, Netzwerk-, Remote- und Docker-Freigaben entfernen oder auf konkrete harmlose Unterbefehle reduzieren. Netzwerk/SSH/Docker immer bestätigen lassen, Agent in einer Sandbox ohne Secrets betreiben und Datenbank-/Secret-Verzeichnisse betriebssystemseitig schützen.

## 7. Mittlere und niedrige Befunde

### TECH-008: MCP-Ein- und Ausgabeschemas sind offen und widersprechen teils dem Laufzeitverhalten

- **Schweregrad:** Mittel
- **Bereich:** MCP-Schemas, Fehlerverhalten
- **Stellen:** alle Tool-Signaturen in `app/tools/`; Registrierung `app/server.py:44-65`
- **Status:** sicher nachgewiesen
- **Beobachtung:** Alle 16 Output-Schemas sind nur `{"type":"object","additionalProperties":true}`. Kategorien, Editionen, Richtung und Methoden sind freie Strings; Dictionary-Werte und Listen sind kaum beschränkt. Input-Schemas verbieten zusätzliche Properties nicht, der Laufzeitvalidator lehnt sie dennoch ab. `kategorie="ungueltig"` wird als leerer Bestand beantwortet, eine ungültige Glossarrichtung still als `auto`; andere Fehler erscheinen als verschiedene Erfolgspayloads mit `fehler`.
- **Auswirkung:** Modelle und Clients können weder gültige Aufrufe zuverlässig konstruieren noch Fehlerzustände maschinenlesbar unterscheiden. Falsche Eingaben sehen wie Wissenslücken aus.
- **Empfehlung:** Geschlossene Pydantic-Modelle, `Literal`/Enums, Längen-/Werte-/Arraygrenzen und diskriminierte Ergebnisse `success|not_found|ambiguous|invalid_request|unavailable|internal_error`. Requestfehler als MCP-Fehler, fachliches Nichtfinden als reguläres Ergebnis.

### TECH-009: Provenienz, Revisionen, Beziehungen und Konflikte gehen im Hauptmodell verloren

- **Schweregrad:** Mittel
- **Bereich:** Wissensmodell
- **Dateien/Stellen:** `db/schema.sql:5-58`, `importer/ddb_exporter/artifact.py:83-95`, `importer/import_ddb.py:178-207`
- **Status:** sichere Modelllücke
- **Beobachtung:** Das DDB-Artefakt besitzt native ID, Parent-ID, Breadcrumb, URL und Body-Hash. Der Import reduziert diese Daten auf Kategorie, Name und Markdown. Es fehlen Quellrevision, Importlauf, externer Locator, Konzeptidentität und Relationen wie `requires`, `exception_to`, `overrides` oder `supersedes`. Kontext steckt als formatierte Zeile im Body und wird später per Regex rekonstruiert.
- **Auswirkung:** Eine Antwort ist nicht bis zu einem unveränderlichen Quellsnapshot reproduzierbar. Widersprüche, Errata, spezielle-vor-allgemeinen Regeln und echte Dubletten sind nicht technisch unterscheidbar.
- **Empfehlung:** `source_snapshot`, `ingest_run`, `concept`, `entry_variant` und `entry_relation` ergänzen. Externe IDs, Hashes, Locator und Klassifikationsstatus durch die gesamte Pipeline erhalten. SQLite bleibt dafür ausreichend.

### TECH-010: Point-Buy-Ausgabe ist nur teilweise aus dem Bestand belegt

- **Schweregrad:** Mittel
- **Bereich:** Build-Prüfung, Grounding
- **Dateien/Stellen:** `app/tools/charakter.py:28-30,368-386,478-485`
- **Status:** sicher nachgewiesen
- **Beobachtung:** Kostenmap, Wertebereich und Budget sind Konstanten. Der Bestandsbeleg prüft für Point Buy nur das Vorkommen von `27 Punkte`; eine synthetische Quelle ohne Kostentabelle führte trotzdem zur vollständigen hartcodierten Kostenmap mit Quellenbeleg.
- **Auswirkung:** Eine Ausgabe kann behaupten, vollständig am Bestand belegt zu sein, obwohl wesentliche Zahlen nicht aus dem belegten Text geprüft wurden.
- **Empfehlung:** Strukturierte Regelparameter beim Import extrahieren und mit Quellenlocator speichern oder die Tabelle zur Laufzeit streng parsen. Fehlt die vollständige Struktur, `nicht_pruefbar` statt Konstanten ausgeben.

### TECH-011: Editionsvalidierung verwechselt unterstützte mit aktuell vorhandenen Editionen

- **Schweregrad:** Mittel
- **Bereich:** Versionierung, Fehlersemantik
- **Datei/Stelle:** `app/db.py:93-110`
- **Status:** sicher nachgewiesen
- **Beobachtung:** Die gültige Editionsmenge wird aus vorhandenen Einträgen gebildet. Ein reiner 2014-Bestand lehnt daher den dokumentierten 2024-Default als ungültig ab, statt den Altstand-Fallback anzubieten. Ein vollständig leerer Bestand akzeptiert dagegen beliebige Editionsstrings.
- **Auswirkung:** Gültigkeit und Verfügbarkeit werden vertauscht; Verhalten hängt unlogisch vom aktuellen Datenbestand ab.
- **Empfehlung:** Unterstützte Editionen in Konfiguration/Schema definieren und getrennte Zustände `invalid_edition` und `valid_but_unavailable` zurückgeben.

### TECH-012: `/health` wird als Readiness benutzt, prüft aber nur den Prozess

- **Schweregrad:** Mittel
- **Bereich:** Betrieb, Verfügbarkeit
- **Dateien/Stellen:** `app/server.py:35-37`, `docker-compose.yml:23-27`, `tests/test_zugriff.py:68-70`
- **Status:** sicher nachgewiesen
- **Beobachtung:** `/health` liefert unabhängig von Datenbank, Schema, FTS und Bestand immer HTTP 200. Compose verwendet genau diese Route für den Healthcheck. Eine fehlende oder korrupte DB kann daher als healthy gelten, während Tools ausfallen.
- **Auswirkung:** Monitoring, Neustartlogik und Nutzer sehen einen grünen Dienst ohne funktionierendes Wissenssystem.
- **Empfehlung:** `/live` für Prozess-Liveness und `/ready` für read-only DB-Öffnung, Schema-Version, Kernabfrage, FTS und freigegebenen Snapshot. Compose auf `/ready` umstellen; bei Fehler 503 mit maschinenlesbarem, secret-freiem Grund.

### TECH-013: Eingaben, Arbeit und Ausgaben sind nicht wirksam begrenzt

- **Schweregrad:** Mittel
- **Bereich:** DoS, Kontextgröße, Skalierung
- **Dateien/Stellen:** `app/db.py:74-78,171-224,339-378`, `app/glossar.py:48-72`, `app/tools/nachschlagen.py:251-260`, `app/tools/charakter.py:106-114,823-870`
- **Status:** sicher nachgewiesenes Risiko; kein Belastungsangriff durchgeführt
- **Beobachtung:** Keine String-/Array-/Bodygrenzen in den Schemas, keine Tool-Timeouts, Rate Limits oder globale Concurrency-Grenzen. Glossar und Fuzzy-Suche laden große Namensmengen, Waffen-Duplikatprüfung ist quadratisch, Detailtools können vollständige Bodies und beliebig viele Kinder aggregieren, Listen laden ganze Kategorien. Im vorhandenen Datenbestand existieren Bodies bis über 50.000 Zeichen.
- **Auswirkung:** Ein berechtigter Nutzer oder fehlerhaftes Modell kann CPU, Threadpool, SQLite-Verbindungen, Logs und Modellkontext erschöpfen. Wachstum verschlechtert die Latenz überproportional.
- **Empfehlung:** ASGI-Bodylimit, Schema-Bounds, Pagination/Cursor, maximale Antwortgröße, Abschnittsabruf, Timeout, Semaphore und Edge-/Anwendungs-Rate-Limit. Glossarindex einmal pro Snapshot aufbauen statt pro Aufruf vollständig scannen.

### TECH-014: Die Qualitätssicherung zeigt grün, obwohl die DDB-Suite rot ist

- **Schweregrad:** Mittel
- **Bereich:** Tests, CI
- **Dateien/Stellen:** `tests/test_ddb_exporter.py:273-301`, `importer/import_ddb.py:39-47,178-181`, `requirements-ddb.txt`, fehlende `.github/workflows`
- **Status:** sicher nachgewiesen
- **Beobachtung:** Die Standardsuite überspringt die drei DDB-Module. In `.venv-ddb` bestehen 24 Tests, aber der Rundlauf erwartet zwei importierte Einträge inklusive `Spells`, während der Importer diesen generischen Header absichtlich filtert; Ergebnis 1 statt 2. `requirements-ddb.txt` enthält kein pytest, und es gibt keine CI-Matrix.
- **Auswirkung:** Der wichtigste private Importpfad kann hinter einem grünen Standardlauf rot bleiben. Aktuell spricht der Befund eher für einen veralteten Testvertrag als für einen bewiesenen Produktionsfehler.
- **Empfehlung:** Erwartung/Fixture fachlich entscheiden und synchronisieren; Headerfilter separat testen. Deklarative Testabhängigkeiten und verpflichtende CI-Jobs für Runtime, DDB und OCR/Docker einführen.

### TECH-015: Build und Artefakte sind nicht reproduzierbar fixiert

- **Schweregrad:** Mittel
- **Bereich:** Supply Chain, Deployment
- **Dateien/Stellen:** `requirements.txt`, `Dockerfile:2-19`, `docker-compose.yml:30,44`, `.dockerignore:1-12`, `importer/ddb_exporter/artifact.py:118`
- **Status:** sicher nachgewiesen
- **Beobachtung:** Bis auf FastMCP verwenden Runtime-Abhängigkeiten Untergrenzen. Basis-, Cloudflared- und Datasette-Images sind mutable Tags. Es fehlen Lock mit Hashes, Image-Digests, SBOM und Dependency-Audit. `.dockerignore` schließt `.venv-ddb` nicht aus; durch `COPY . .` können lokal 49 MB SQLCipher-Umgebung sowie weitere Entwicklungsartefakte in das Runtime-Image gelangen. Artefakte tragen konstant `exporter_version="1.0.0"` ohne Git-Commit.
- **Auswirkung:** Derselbe Commit kann zu unterschiedlichen Extraktionen, Images und Ergebnissen führen. Unnötige Werkzeuge und Dateien erhöhen Angriffsfläche und Imagegröße.
- **Empfehlung:** Getestete Constraints/Lockdatei mit Hashes, Image-Digests und Updateprozess. Nur benötigte Runtime-Verzeichnisse kopieren. Projektversion und Git-Commit als Pflichtfelder im Korpus-/DDB-Manifest.

### TECH-016: Betriebs- und Datenschutzdokumentation widerspricht sich

- **Schweregrad:** Mittel
- **Bereich:** Dokumentation, Installation, Datenschutz
- **Dateien/Stellen:** `README.md:23-31`, `docs/ATTRIBUTION.md:8-13`, `docs/DDB-IMPORT-anleitung.md:75-83`, `docs/DEPLOY-raspberry-pi.md:145-148`, `config/foliant.example.toml:1-3`, `app/admin.py:140-196`
- **Status:** sicher nachgewiesen
- **Beobachtung:** Attribution behauptet private-only DDB-Ablage, während Code und andere Dokumente `ins_hauptbestand=true` unterstützen bzw. als Produktionszustand beschreiben. Mehrere Texte nennen den Tunnel weiterhin authless und Absicherung optional, andere Geheimpfad plus IP-Allowlist. Admin-Ausgaben nennen das Ziel auch bei Hauptbestand irreführend `privat`. Die Beispielkonfiguration nennt das abgeschaffte `FOLIANT_COBALT`. Der README-Schnellstart endet ohne Test-, Serverstart-, MCP-URL- oder Python-3.11+-Anweisung.
- **Auswirkung:** Betreiber können falsche Entscheidungen über Veröffentlichung, Secretbehandlung und erfolgreichen Start treffen.
- **Empfehlung:** Eine verbindliche Betriebsvariante dokumentieren; private-only und bewusst freigegeben klar trennen. Aussagen automatisiert gegen Beispielkonfiguration prüfen. README um Voraussetzungen, Tests, Start, URL, Readiness und Client-Einbindung ergänzen.

### TECH-017: Abgerufener Quelltext wird nicht als potenziell unvertrauenswürdige Daten abgegrenzt

- **Schweregrad:** Mittel
- **Bereich:** Prompt Injection, Tool Poisoning
- **Dateien/Stellen:** `importer/import_open5e.py`, `importer/ddb_exporter/html_to_markdown.py`, `app/tools/nachschlagen.py:133-153`
- **Status:** mögliches Risiko; kein schädlicher Prompt im geprüften öffentlichen Bestand nachgewiesen
- **Beobachtung:** Importierter Klartext wird als `regeltext_md` unverändert an das Hostmodell geliefert. Aktive HTML-Bestandteile werden teilweise entfernt, Textanweisungen können aber nicht von Regeln unterschieden werden. Ausgaben enthalten keine maschinenlesbare Vertrauensklasse oder klare Datenkapsel.
- **Auswirkung:** Eine kompromittierte API, Quelle oder Datei kann versuchen, Modellinstruktionen zu überschreiben oder andere Clienttools auszulösen.
- **Empfehlung:** Inhalte explizit als unvertrauenswürdige Zitate/Evidence markieren; Trust-/Scope-Metadaten ausgeben; Links allowlisten; ungewöhnliche Instruktionsmuster bei Importen quarantänisieren. Echte Client-E2E-Tests müssen prüfen, dass Quelltext nie als Handlungsanweisung behandelt wird.

### TECH-018: Datenbank-QS ist keine reproduzierbare Freigabestufe

- **Schweregrad:** Mittel
- **Bereich:** Datenqualität, Releaseprozess
- **Dateien/Stellen:** `app/admin.py:280-348`, `tests/smoke_test.py`, `db/init_db.py`
- **Status:** sicher nachgewiesen
- **Beobachtung:** `admin check` meldet lokale HTML-Reste nur als Warnung und beendet mit `check: OK`; die Stichprobe nutzt `ORDER BY random()`. Der Smoke-Test ist ein separat aufzurufendes Skript und wird durch pytest nicht ausgeführt. Es gibt kein versioniertes Korpusmanifest mit Quellhashes, Importer-Commit, Schema-Version und bestandenem semantischem Gate.
- **Auswirkung:** Ein technisch konsistenter, aber semantisch beschädigter Bestand kann freigegeben werden. Der aktuelle `Aktionen`-/`Solar`-Fehler blieb trotz grüner Checks bestehen.
- **Empfehlung:** Deterministischen `admin check --strict` einführen, Golden Queries und Kategorie-Pflichtfelder prüfen und nur unveränderliche Korpusartefakte promoten, deren Manifest alle Gates nachweist.

### TECH-019: Das SQL-Schema erzwingt wesentliche Domäneninvarianten nicht selbst

- **Schweregrad:** Niedrig
- **Bereich:** Datenintegrität, Wartbarkeit
- **Datei/Stelle:** `db/schema.sql:5-78`
- **Status:** sicher nachgewiesen
- **Beobachtung:** Sprache, Kategorie, Edition, Herkunft und `offiziell` haben keine `CHECK`-Constraints. Quellen- und Eintragsedition sind redundant, aber nicht per Trigger/Modell gekoppelt. Eine Schema-Version und Migrationen fehlen. `zauber_meta`, `monster_meta` und `gegenstand_meta` sind außerhalb des Schemas ungenutzt.
- **Auswirkung:** Korrektheit hängt von jedem Importer und nachgelagerten Checks ab; spätere Schemaerweiterungen am Produktionsbestand werden riskant.
- **Empfehlung:** Schema-Version/Migrationen, überprüfbare Constraints und gezielte Trigger ergänzen. Ungenutzte Metatabellen entweder implementieren oder bis zur tatsächlichen Nutzung entfernen.

### TECH-020: Read-only- und MCP-Tool-Metadaten werden nicht genutzt

- **Schweregrad:** Niedrig
- **Bereich:** MCP-Konformität, Least Privilege
- **Dateien/Stellen:** `app/db.py:60-67`, Tool-Registrierung in `app/server.py:44-65`
- **Status:** sicher nachgewiesen
- **Beobachtung:** Serving-Verbindungen sind schreibbar. Alle ToolAnnotations fehlen, obwohl sämtliche MCP-Tools read-only und idempotent sind.
- **Auswirkung:** Clients erhalten weniger Planungshinweise; eine zusätzliche technische Schutzschicht fehlt.
- **Empfehlung:** `connect_readonly()` und ToolAnnotations wie `readOnlyHint`, `idempotentHint` sowie passende `openWorldHint`-Werte setzen.

### TECH-021: Verhaltensgarantien liegen überwiegend außerhalb des Servers

- **Schweregrad:** Hinweis
- **Bereich:** KI-Wissenssystem, Architekturgrenze
- **Dateien/Stellen:** `config/stil.py`, Docstrings der Tools, Grounding-Hinweise in Tool-Ausgaben
- **Status:** Architekturhinweis, kein einzelner Codefehler
- **Beobachtung:** Foliant liefert Evidence, formuliert aber nicht die finale Antwort. Keine-Halluzination, Webtrennung, Spoilerablehnung und englische Originalbegriffe bei jeder Nennung hängen vom Hostmodell und teilweise von optionalen Claude-Projektanweisungen ab. Der rohe Regeltext ist nicht begriffsweise annotiert.
- **Auswirkung:** Diese Eigenschaften können durch Server-Unit-Tests nicht bewiesen werden. Unterschiedliche Clients/Modelle können sich verschieden verhalten.
- **Empfehlung:** Garantierbare Eigenschaften serverseitig als Daten-, Scope- und Zugriffskontrollen implementieren. Für verbleibendes Modellverhalten eine versionierte Evalsuite mit echten Clients, Negativfragen und Akzeptanzschwellen betreiben.

## 8. Bewertung der MCP-Tools und Schemas

| Toolgruppe | Bewertung | Wesentliche Punkte |
|---|---|---|
| `foliant_suche_regeln` | konzeptionell gut, Vertrag unvollständig | knappe Treffer und Editionsseparation sind gut; stabile Referenzen, Quellenkatalog, strikte Enums und Cursor fehlen |
| `foliant_hol_regel/zauber/monster/gegenstand` | sinnvoll getrennt, derzeit nicht zuverlässig eindeutig | volle Details und Zitate sind gut; name-basierter Abruf kann Treffer wechseln, raten oder Teil-Chunks verlieren |
| `foliant_uebersetze_begriff` | nützlich, aber kanonische und fuzzy Ebene vermischt | Herkunft/Offiziell-Feld gut; falsche offizielle Zuordnung `Aktionen -> Reaktionen` blockiert Freigabe |
| Listen für Klassen/Hintergründe/Spezies/Talente | zweckmäßig für schrittweisen Charakterbau | 2024-Filter und knappe Ausgabe gut; Listen ohne Pagination und stark regex-/Kontext-abhängig |
| Charakter-Detailtools | gute Domänenaufteilung | erben Identitäts- und Provenienzprobleme der gemeinsamen Detailmaschine |
| `foliant_hol_attributswerte` | klare kleine Oberfläche | Point-Buy-Zahlen nicht vollständig aus dem angegebenen Beleg abgeleitet |
| `foliant_pruefe_build` | transparent begrenzt und testbar | gute Statusausgabe; Schema zu offen, einige Regelwerte/Parser fragil, keine vollständige Regel-Engine |

Die Toolanzahl ist für den MVP vertretbar. Eine Konsolidierung aller Detailtools zu einem einzigen breiten Namenstool wäre nicht automatisch besser. Entscheidend ist ein gemeinsamer stabiler `entry_ref`-Vertrag.

Empfohlene MCP-Ergänzungen:

- Resource `foliant://sources` mit verfügbaren Quellen, Editionen, Revisionen, Lizenzen und Scopes.
- Resource Template `foliant://entries/{entry_ref}` für unveränderliche Evidence.
- Resource `foliant://attribution` statt eines für Remote-Clients nutzlosen Verweises auf `docs/ATTRIBUTION.md`.
- Optionaler Prompt für den Charakterdialog; nicht für Sicherheit oder Zugriffskontrolle.

## 9. Bewertung des Wissens- und Datenmodells

Das aktuelle Modell ist ein brauchbarer FTS-Index über Quellen-Chunks, aber noch kein belastbares Regelwissensmodell. Seine Stärken sind geringe Komplexität, offline Betrieb und klare Quelle/Edition am Eintrag. Seine Grenzen zeigen sich bei Identität, Revision, Beziehungen und Scope.

Kurzfristig sollte SQLite beibehalten werden. Notwendig sind jedoch vier Ebenen:

1. **SourceSnapshot:** unveränderliche Ausgabe eines Buchs/Dokuments mit Lizenz, Edition, Ausgabe/Errata, Hash und Importzeitpunkt.
2. **EntryVariant:** exakter Quellabschnitt mit externer ID, Locator, Body-Hash, Sprache, Kontext und Klassifikation.
3. **Concept:** fachliche Identität, die nur kuratiert oder mit nachweisbaren exakten Mappings Varianten verbindet.
4. **Relation:** typisierte und belegte Beziehung, etwa `parent`, `requires`, `exception_to`, `overrides`, `supersedes`, `same_as`.

Konflikte dürfen nicht durch Priorität verschwinden. Priorität kann die bevorzugte Darstellung wählen, muss abweichende Varianten aber als `conflict` bzw. `other_variants` sichtbar lassen.

## 10. Bewertung von Sicherheit und Robustheit

Positiv sind parametrisierte SQL-Abfragen, FTS-Quoting, Nicht-Root-Ausführung, Loopback-Portbindung, Offline-Runtime und die starke Härtung des kurzlebigen DDB-Exporters.

Die Hauptlücken liegen an den Vertrauensgrenzen:

- Authentisierung identifiziert keinen Nutzer und kann leer starten.
- Das URL-Secret wird protokolliert.
- Serving und private Daten/Importer teilen Container und Mount.
- Spoiler-/Audience-Scope wird nicht serverseitig erzwungen.
- Quelltext ist für das Modell nicht technisch von Instruktionen getrennt.
- Request-, Arbeits- und Antwortmengen sind nicht begrenzt.
- Entwickler-Agentenrechte sind breiter als die Secret-Denies suggerieren.

Es wurden keine unsicheren Shell-Aufrufe mit `shell=True` gefunden. OCR verwendet eine Argumentliste; DDB-SQL ist kontrolliert; ZIP-Extraktion besitzt sinnvolle Schutzmaßnahmen. Pfade aus lokaler Konfiguration/CLI dürfen zwar absolut oder außerhalb des Projekts liegen, sind aber keine MCP-Nutzereingaben. Dafür sind Root-Grenzen und private Dateimodi als zusätzliche lokale Härtung dennoch sinnvoll.

## 11. Bewertung der Tests

Die Tests sind für ein MVP breit und häufig sehr konkret. Besonders gut sind synthetische SQLite-Fixtures, Import-Rollback, Editionsfälle, Deduplizierung, Zugriff, ZIP-Sicherheit, OCR-Vorstufe und Build-Grenzen.

Wesentliche Lücken:

- keine verpflichtende CI und kein geschlossener Testabhängigkeitssatz;
- DDB-Tests im Standardlauf vollständig übersprungen und separat rot;
- kein echter Streamable-HTTP-Handshake über den veröffentlichten ASGI-Pfad;
- keine Schema-Snapshots oder Contracttests für `tools/list`/`tools/call`;
- kein Search-to-Detail-Rundlauf mit stabiler Identität;
- keine semantischen Golden Queries gegen den freizugebenden Korpus;
- keine Tests für gleichnamige unterschiedliche Kontexte/Teil-Statblöcke;
- keine automatisierten Hostmodell-Evals für Toolauswahl, Grounding, Spoiler und Prompt Injection;
- keine Last-, Rate-Limit-, Backup-Restore- oder Korpus-Promotion-Tests;
- Smoke-Test wird nicht automatisch von pytest ausgeführt;
- T10 ist explizit manuell, T2/T12 sind nur serverseitig teilautomatisiert.

## 12. Bewertung der Dokumentation und Installation

Die Dokumentationsmenge und fachliche Struktur sind überdurchschnittlich. Anforderungen, Technik, Betrieb und bekannte Macken sind getrennt, und viele Entscheidungen sind begründet.

Problematisch ist die Statusdrift: `MVP komplett`, private-only DDB, authless Tunnel, aktueller Zugriffsschutz und offene Betriebsaufgaben werden je nach Dokument unterschiedlich dargestellt. Ein neuer Entwickler kann den Bestand initialisieren, erhält im README aber keinen vollständigen Weg bis zum laufenden MCP-Server und Testnachweis. Die Produktbehauptung von 12 Quellen ist mit der lokalen 2-Quellen-Datenbank nicht reproduzierbar.

Vor externer Nutzung sollte es einen kurzen kanonischen Betriebsweg geben, auf den andere Dokumente verweisen:

1. unterstützte Plattform/Python-/Docker-Versionen;
2. reproduzierbare Installation aus Lockdatei;
3. Testmatrix und Korpus-Build;
4. Serverstart und Readiness;
5. Authentisierung/Connector-Einrichtung;
6. Import, Promotion, Backup und getesteter Restore;
7. klare Aussage, welche privaten Inhalte tatsächlich serviert werden.

## 13. Empfohlene Zielarchitektur für die nächste Ausbaustufe

```text
Netzgebundene Importer/OCR/DDB-Exporter
              |
              v
      unveränderlicher SourceSnapshot
              |
      Validierung + Klassifikation
              |
      Concept/Variant/Relation in SQLite
              |
      semantische Gates + Manifest
              |
      atomare Promotion eines Korpus-Releases
              |
              v
  minimaler read-only MCP-Serve-Dienst
      |          |             |
   OAuth       Scopefilter    Readiness
      |
      v
Search -> stabile entry_ref -> Entry Resource/Detail
```

Kernentscheidungen:

- **SQLite und FTS5 behalten.** Die Probleme erfordern keinen Vektorstore und keine neue Datenbank.
- **Import und Serving strikt trennen.** Netz, OCR, Admin und private Rohdaten gehören nicht in den öffentlichen Prozess.
- **Unveränderliche Korpus-Releases.** Ein Release wird einmal geprüft und dann read-only serviert.
- **Evidence-first MCP.** Suche liefert kleine, stabile Referenzen; Details liefern begrenzte Evidence mit Hash/Locator/Revision.
- **Explizite Zustände.** `exact`, `fuzzy`, `ambiguous`, `conflict`, `not_found`, `unsupported`, `untrusted` und `unavailable` dürfen nicht vermischt werden.
- **Scope vor Retrieval.** Spieler-/SL-, Lizenz- und Spoilerfilter werden in SQL/Serving durchgesetzt, nicht im Prompt.
- **Prompts nur als UX.** Grounding und Sicherheit werden technisch soweit möglich erzwungen; Hostmodellverhalten wird evaluiert.

## 14. Priorisierter Maßnahmenplan

### Vor dem nächsten internen Test

| Priorität | Befunde | Ziel | Konkrete Umsetzung | Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| P0 | TECH-001 | falsche Glossaridentität stoppen | exact/fuzzy trennen; fuzzy nie in Identität oder kanonischer Übersetzung | `Aktionen` liefert weder `Reaktionen` noch einen Reaktionen-Detailtext | S |
| P0 | TECH-002, TECH-003 | stabiler Search-to-Detail-Rundlauf | `entry_ref` und `source_key` ausgeben; Detail per Referenz; echte Ambiguität erhalten | Open5e-Suchtreffer lädt exakt denselben Body/Hash; `Solar` enthält RK und TP | M |
| P0 | TECH-014 | glaubwürdiges Test-Gate | DDB-Erwartung entscheiden; Testabhängigkeiten deklarieren; separaten Job verpflichtend machen | Runtime- und DDB-Suite beide ohne Skip-Verdeckung grün | S |
| P1 | TECH-008 | verlässlicher MCP-Vertrag | geschlossene Input-/Outputmodelle, Enums, gemeinsame Fehlercodes | Schema-Snapshot zeigt Enums/Beschränkungen; ungültige Werte scheitern als Requestfehler | M |
| P1 | TECH-005 | keine Tokenleaks/Fehlstarts | Produktionsstart ohne starkes Token ablehnen; Pfade redigieren; Access-Logging anpassen | Start ohne Secret fehlschlägt; Test beweist, dass Logs keinen Token enthalten | S |
| P1 | TECH-010, TECH-011 | echte Grounding-/Editionssemantik | Point-Buy strukturiert belegen; unterstützte Editionen separat modellieren | unvollständiger Beleg liefert `nicht_pruefbar`; 2014-only/leer korrekt getestet | M |

### Vor externen Nutzertests

| Priorität | Befunde | Ziel | Konkrete Umsetzung | Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| P0 | TECH-004 | Spoiler technisch ausschließen | Abenteuer standardmäßig skippen oder separaten Snapshot; Scope im Manifest/DB/SQL | Spieler-Scope kann Test-Spoiler auch bei direktem Toolcall nicht abrufen | M |
| P0 | TECH-006 | Serving isolieren | minimales Serve-Image, nur freigegebene DB read-only, private Pfade nicht mounten | Container-Test zeigt: kein Zugriff auf `data/private`, keine Schreibtransaktion möglich | M |
| P1 | TECH-012, TECH-018 | nur geprüften Bestand servieren | `/ready`; versioniertes Korpusmanifest; deterministische semantische Gates | korrupte/ungeprüfte DB ergibt 503 und wird nicht promotet | M |
| P1 | TECH-017, TECH-021 | Hostmodellrisiken messen | echte Client-Evals für Grounding, Spoiler, unklare Fragen und Injection | definierte Evalfälle bestehen auf jedem unterstützten Client/Modell | M |
| P1 | TECH-013 | stabile Latenz und Kontextgröße | Bounds, Cursor, Antwortlimit, Timeout, Semaphore und Rate Limit | Grenztests bleiben innerhalb festgelegter Zeit-/Payloadbudgets | M |
| P2 | TECH-016 | eindeutiger Betrieb | kanonische Doku und spielerfeste Connector-Anleitung | frischer Nutzer startet und verbindet anhand eines einzigen Runbooks | S |

### Vor Veröffentlichung des MVP

| Priorität | Befunde | Ziel | Konkrete Umsetzung | Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| P0 | TECH-005 | identitätsbasierter Zugang | MCP-OAuth oder gleichwertige vorgelagerte Identität/Scopes, Widerruf und Audit | einzelne Nutzer lassen sich sperren; anonyme/andere Egress-Nutzer bleiben draußen | L |
| P1 | TECH-009, TECH-019 | reproduzierbare Provenienz | SourceSnapshot/EntryVariant-Migration, externe IDs/Hashes/Locator | jede Detailantwort verweist auf unveränderliche Revision und Hash | L |
| P1 | TECH-015 | reproduzierbarer Supply-Chain-Build | Lock/Hashes, Digests, SBOM, Audit und signierte Release-Metadaten | Build aus frischem Checkout erzeugt denselben getesteten Abhängigkeitsstand | M |
| P1 | TECH-018 | Wiederherstellbarkeit | Off-Site-Backup, Restore-Runbook und regelmäßiger Restore-Test | Restore auf leerem Host besteht Integritäts-, FTS- und Golden-Query-Gates | M |
| P2 | TECH-007 | sichere Agentenentwicklung | Berechtigungen minimieren und Sandbox ohne Secrets | definierter Injectiontest kann weder Secrets lesen noch Netzwerk/SSH ausführen | S |

### Nach dem MVP

| Priorität | Befunde | Ziel | Konkrete Umsetzung | Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| P2 | TECH-009 | Konflikte und Ausnahmen darstellen | Concept/Variant/Relation mit `conflict`, `exception_to`, `overrides` | synthetische allgemeine/spezielle Regel wird korrekt verknüpft und angezeigt | L |
| P2 | TECH-013 | Wachstum beherrschen | snapshotweiter Glossarindex, normalisierte Suchindizes, Messbudgets | Lasttest auf Zielhardware erfüllt dokumentierte SLOs | M |
| P2 | TECH-020 | bessere MCP-Planung | ToolAnnotations und Entry-/Source-Resources | MCP-Contracttest bestätigt Metadaten und Resource-Auflösung | S |

### Langfristige Weiterentwicklung

| Priorität | Befunde | Ziel | Konkrete Umsetzung | Abnahmekriterium | Größe |
|---|---|---|---|---|---|
| P3 | TECH-004, TECH-009 | Rollen-/Kampagnenfähigkeit | getrennte Korpora, Audience-Scopes und explizite Freigabeprozesse | SL-Inhalte sind physisch/logisch vom Spielerpfad isoliert | XL |
| P3 | TECH-009, TECH-021 | nachvollziehbare Regelerklärung | belegter Regelgraph und mehrteilige Evidence-Pakete | zusammengesetzte Antwort nennt jede verwendete Regelvariante/Relation | XL |
| P3 | TECH-018 | kontinuierliche Qualität | kuratierter Evalkatalog aus Nutzerfeedback mit Release-Trends | Regressionen blockieren automatisch die Korpus-/Serverfreigabe | L |

### Größter kurzfristiger Qualitätsgewinn

1. Glossar exact/fuzzy trennen und `Aktionen` als Blocker-Test aufnehmen.
2. Stabile Eintragsreferenzen vom Suchtreffer bis zum Detail einführen.
3. Abenteuer-/private Scopes vor Retrieval erzwingen und Serving read-only isolieren.
4. MCP-Verträge schließen und Runtime-/DDB-/Contracttests in CI verpflichtend machen.
5. Korpus als versioniertes, semantisch geprüftes Release statt als beliebige SQLite-Datei behandeln.

## 15. Empfohlene zusätzliche Tests

1. **Glossar-Kollision:** `Aktionen` darf nicht `Reaktionen`; `Action` und `Reaction` müssen getrennt bleiben. Matchtyp und Score explizit prüfen.
2. **Geteilter Statblock:** `Solar` muss mindestens Name, RK, TP, Bewegung und Aktionen aus derselben Revision enthalten oder als unvollständig abgelehnt werden.
3. **Gleichnamige Kontexte:** zwei `Aktionen`-Einträge derselben Kategorie/Edition, aber verschiedener Kontexte müssen `ambiguous` liefern.
4. **Quellen-Rundlauf:** Quelle/Revision/Hash eines Suchtreffers müssen nach Detailabruf unverändert sein.
5. **Textkonflikt:** gleiches Konzept und Edition mit abweichenden Bodies muss `conflict` und beide Varianten liefern.
6. **Schema-Contract:** alle Enums, Grenzen, `additionalProperties=false`, Output-Unionen und ToolAnnotations als Snapshot prüfen.
7. **Ungültige Eingaben:** falsche Kategorie, Richtung, Methode, Edition, Zusatzfeld, leere/überlange Strings und übergroße Arrays müssen konsistent scheitern.
8. **Editionszustände:** leerer Bestand, 2014-only, 2024-only, beide Editionen, unterstützte aber nicht importierte Edition.
9. **MCP-End-to-End:** `initialize`, `tools/list`, `tools/call` über echten Streamable-HTTP-Pfad inklusive Streaming, Geheimpfad, 403 und strukturierter Fehler.
10. **Authentisierung:** Produktionsstart ohne Secret/OAuth muss fehlschlagen; Nutzerwiderruf und Scopeprüfung testen.
11. **Log-Redaktion:** Token, signierte URL, Cobalt und private Pfade dürfen weder Erfolgs- noch Fehlerlogs erreichen.
12. **Spoiler-Scope:** Adventure-/GM-Fixture darf im Spieler-Snapshot weder Suche noch direkte Referenz passieren.
13. **Prompt Injection:** Quelltext mit `ignore previous instructions` bleibt zitiert und löst keine anderen Tools/Netzaktionen aus.
14. **Readiness:** fehlende, korrupte, gesperrte, falsche Schema- und ungeprüfte DB liefern 503; Liveness bleibt unabhängig.
15. **Payload/Last:** maximale Query, Glossar, Talent-/Waffenlisten, parallele Calls und größter Body gegen feste Budgets prüfen.
16. **DDB-Rundlauf:** Export -> Validator -> Import mit generischem Header, echter Option, leerem Body, unbekannter Kategorie und Quellrevision.
17. **Import-Promotion:** falscher Quellhash, Importer-Commit, Schema-Hash oder fehlgeschlagenes Golden Gate verhindert Aktivierung.
18. **Backup-Restore:** Wiederherstellung auf leerem Host; danach Integrity, FK, FTS, Quellenzahl und Golden Queries.
19. **Toolauswahl-Evals:** unklare Frage, mehrere relevante Regeln, falsche Nutzerannahme, nicht unterstützte Anfrage, Versionskonflikt und reine Übersetzungsfrage.
20. **Deutsch-first-Evals:** offizieller/inoffizieller Begriff, ältere Terminologie, englischer Body und mehrere Begriffe in einem Absatz.

## 16. Offene Fragen und Annahmen

- Ist der dokumentierte Produktionsbestand mit 12 Quellen identisch zum Code-Commit dieser Review? Lokal waren nur zwei Quellen vorhanden.
- Welche DDB-Bücher werden tatsächlich über den Connector serviert, und welche davon enthalten Abenteuer-/SL-Inhalte?
- Ist `ins_hauptbestand=true` eine dauerhafte Freigabeentscheidung oder nur ein temporärer Betriebszustand?
- Soll die Quelle gezielt auswählbar sein? Der Parameter und die Best-Practice-Doku sagen ja, der Rundlauf unterstützt es derzeit nicht.
- Welche Regel gilt bei gleichnamigen Abschnitten: aggregieren, als Varianten zeigen oder kontextbezogen unterscheiden? Das muss domänenseitig entschieden und dann technisch modelliert werden.
- Welche Clients und Modellversionen gelten als offiziell unterstützt? Bisher ist nur Claude beschrieben; echte Verhaltensgarantien sind clientabhängig.
- Welche Latenz-, Payload- und Parallelitätsziele gelten auf dem Raspberry Pi?
- Wo liegt das Off-Site-Backup, und wann wurde zuletzt ein vollständiger Restore getestet?
- Gibt es eine beabsichtigte Lizenz für den Projektcode selbst? `ATTRIBUTION.md` regelt primär Inhalte.

Annahmen dieser Review:

- Lokale Konfiguration, Secrets und Produktionsinfrastruktur sind vertrauenswürdige Betreiberinputs, aber keine ausreichende Grenze gegen eine kompromittierte Runtime.
- Modellinstruktionen sind nützliche UX-Leitplanken, aber keine technische Zugriffskontrolle.
- Der D&D-Regelinhalt selbst wird separat fachlich geprüft.
- Architekturpräferenz: SQLite/FTS5 soll erhalten bleiben; vorgeschlagene Tabellen dienen konkreten Nachweis- und Identitätsproblemen, nicht einem allgemeinen Wunsch nach mehr Komplexität.

## 17. Gesamturteil zur MVP-Reife

### Bewertungsmatrix

| Kriterium | Bewertung | Kurzbegründung |
|---|---:|---|
| MCP-Konformität | 6/10 | Handshake, strukturierte Inhalte und Toolregistrierung funktionieren; Verträge, Fehlersemantik, Annotations und Resources sind schwach. |
| Architektur | 5/10 | Gute Modul- und Importtrennung, aber Identität, Scope und Serving-Vertrauensgrenzen sind nicht ausreichend. |
| Codequalität | 7/10 | Lesbarer, gut kommentierter Python-Code mit vielen gezielten Schutzmaßnahmen; einzelne große/regexlastige Module und Dokumentationsdrift bleiben. |
| Zuverlässigkeit | 4/10 | Grüne Standardsuite, aber reproduzierbar falscher Detailtreffer, unvollständiger Statblock und instabiler Quellen-Rundlauf. |
| Sicherheit | 4/10 | Starker Exporter und SQL-Schutz; Auth, Tokenlogging, private Mounts, Promptgrenzen und Agentenrechte verhindern eine höhere Wertung. |
| Testabdeckung | 5/10 | Viele gute Unit-/Integrationstests; DDB verdeckt rot, keine CI, Contract-/HTTP-/Eval-/Restore-/Lastlücken. |
| Dokumentation | 6/10 | Umfangreich und gut gegliedert, aber zentrale Aussagen zu Privatheit, Auth und MVP-Status widersprechen sich. |
| Erweiterbarkeit | 5/10 | Neue Importer/Quellen sind gut andockbar; flaches Modell ohne Revisionen/Relationen/Migrationen begrenzt zuverlässiges Wachstum. |
| Allgemeine MVP-Reife | 4/10 | Für interne technische Versuche geeignet; externe Nutzertests erst nach den P0/P1-Maßnahmen. |

### Was bereits MVP-tauglich ist

- lokale, private Experimente mit kuratiertem SRD/Open5e-Bestand;
- Grundfunktion von Suche, Detailabruf, Quellen-/Editionsausgabe und Charakterlisten;
- offline Serving und die meisten Import-Sicherheitsmechanismen;
- Entwicklung auf Basis synthetischer Fixtures und echtem Daten-Smoke.

### Was externe Nutzertests blockiert

- falsche Glossaridentität und name-basierte Detailauswahl;
- unvollständige/verschluckte gleichnamige Einträge;
- nicht reproduzierbarer Quellen-Rundlauf;
- unisolierte Abenteuer-/Spoilerquellen;
- fail-open Authentisierung und Tokenlogging;
- fehlende read-only Isolation privater Daten;
- verdeckt rote DDB-Suite und fehlender MCP-Contract-/Korpus-Release-Gate.

### Was bewusst nach dem MVP bleiben kann

- vollständiger Regelgraph für alle Ausnahmen;
- Rollen-/Kampagnenfunktionen, sofern Abenteuer bis dahin strikt ausgeschlossen bleiben;
- Vektorsuche oder semantisches Retrieval, solange FTS-Qualität messbar genügt;
- vollständige Build-Regelengine über die transparent dokumentierten MVP-Prüfungen hinaus;
- universelle Hausregel- und Charakterpersistenz.

### Abschlussprüfung des Arbeitsbaums

Vor Erstellung dieser Datei war der Arbeitsbaum sauber. Meine einzige dauerhafte Änderung ist `docs/reviews/2026-07-12-review-codex-mcp-technik.md`; keine bestehende Quellcode-, Konfigurations-, Daten-, Test- oder Dokumentationsdatei wurde durch diese Review verändert. Beim abschließenden `git status --short --untracked-files=all` erschien zusätzlich eine fremde ungetrackte Review-Datei unter `docs/reviews`, die während des Laufs parallel entstanden ist. Sie wurde von diesem Review weder erstellt noch geöffnet oder verändert und floss nicht in die Bewertung ein.
