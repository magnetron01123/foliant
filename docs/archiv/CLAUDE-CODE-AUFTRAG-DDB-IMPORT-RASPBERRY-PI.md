# Claude Code – AUFTRAGSVORSCHLAG: DDB-Buchimport auf dem Raspberry Pi

> **VORSCHLAG – noch nicht implementiert und nicht automatisch freigegeben.**
>
> Dieser Auftrag ist bewusst von `CLAUDE-CODE-KORREKTURAUFTRAG.md` getrennt. Er darf erst nach
> Abschluss und Test von A7 (atomarer, verlustsicherer Re-Import) umgesetzt werden.

## Ziel

Implementiere den in `docs/VORSCHLAG-DDB-IMPORT-RASPBERRY-PI.md` beschriebenen Import für
ausschließlich selbst besessene D&D-Beyond-Bücher. Download, Entschlüsselung, Artefakterzeugung und
privater Datenbankimport laufen vollständig auf einem Raspberry Pi ARM64. Die laufende MCP-Anwendung
hat danach weiterhin keinen DDB-Netzzugriff und kein Cobalt-Secret.

Der Auftrag endet bei einer lokal auf dem Pi validierten privaten Datenbank. Private DDB-Inhalte
dürfen nicht über den aktuell authlosen öffentlichen Tunnel ausgeliefert werden. Zugriffsschutz und
private Connector-Bereitstellung sind ein eigener späterer Auftrag.

## Vor dem ersten Code-Änderungsschritt

1. Lies vollständig:
   - `CLAUDE.md`
   - `docs/foliant-anforderungen.md`
   - `docs/VORSCHLAG-DDB-IMPORT-RASPBERRY-PI.md`
   - `CLAUDE-CODE-KORREKTURAUFTRAG.md`, besonders A7, B1 und B2
   - `docs/foliant-technisches-konzept.md`
   - `docs/DEPLOY-raspberry-pi.md`
   - `importer/import_ddb.py`
   - `importer/import_markdown.py`
   - `app/admin.py`
   - `docker-compose.yml`
   - `Dockerfile`
   - `config/foliant.example.toml`
2. Prüfe `git status` und bewahre alle vorhandenen Nutzeränderungen. Verändere oder lösche keine
   fremden/unzusammenhängenden Änderungen.
3. Führe die bestehende Testsuite unverändert aus und notiere die Baseline.
4. Prüfe anhand von Tests und Code, ob A7 tatsächlich abgeschlossen ist. Falls nicht, **stoppe den
   DDB-Auftrag**, nenne die konkreten noch offenen A7-Punkte und ändere den DDB-Code nicht.
5. Lege vor der Implementierung einen kurzen, dateikonkreten Plan vor. Kein unprüfbarer Großpatch.

## Nicht verhandelbare Leitplanken

- Ausschließlich Bücher/Regelinhalte; keine Charakter-, Kampagnen- oder Encounter-Endpunkte.
- Nur Lizenzen mit `EntityTypeID == 496802664` und `isOwned == true`.
- Kein `noCheck`, kein Ownership-Bypass und kein Import geteilter Bücher in Version 1.
- Kein Foundry, Electron, Adventure-Muncher-Gesamtpaket oder dauerhafter `ddb-proxy`.
- Kein DDB-Zugriff durch den laufenden MCP-Service.
- Cobalt nie in argv, `.env`, Compose-Environment, Logs, Artefakten, Exceptions oder Git.
- Cobalt standardmäßig verdeckt über TTY/stdin einlesen; optional nur ein ausdrücklich gemountetes
  kurzlebiges `/run/secrets/ddb_cobalt` akzeptieren.
- `FOLIANT_COBALT` aus dem dauerhaften `foliant`-Service und aus `.env.example` entfernen.
- Der Netzwerk-/Secret-Prozess erhält keinen Mount auf eine Foliant-DB.
- Keine echten Secrets, privaten Texte oder echten API-Antworten in Tests/Fixtures.
- Öffentliche `data/foliant.sqlite` nicht mit DDB-Daten verändern.
- Ziel ist standardmäßig `data/private/foliant-private.sqlite` über eine geprüfte Kandidatenkopie.
- Keine öffentliche Aktivierung und kein selbstgebautes OAuth in diesem Auftrag.
- Keine Änderungen an echter `config/foliant.toml`, `.env`, Quellbüchern oder vorhandenen DB-Dateien.
- Nicht committen oder pushen, solange der Nutzer dies nicht ausdrücklich verlangt.

## Architektur, die umzusetzen ist

### 1. Kurzlebiger Exporter

Ergänze einen separaten Compose-Service im Profil `ddb`:

- eigenes `Dockerfile.ddb-import`,
- Python 3.12 ARM64,
- separate `requirements-ddb.txt`,
- `restart: "no"`, keine Ports,
- read-only Root-Dateisystem,
- `cap_drop: ALL`, `no-new-privileges`,
- nur private Work-/Artefaktverzeichnisse beschreibbar,
- Konfiguration read-only,
- keinerlei DB-Mount.

Bevorzuge `apsw-sqlite3mc==3.53.2.0`. Implementiere zuerst Phase 0 aus dem Vorschlagsdokument.
Wechsle nur dann zu einem minimalen Node-22-Helfer, wenn die dort definierte Fallback-Bedingung
nachweislich erfüllt ist. HTTP-/Token-/Formatfehler rechtfertigen keinen Technologiewechsel. Pflege
nicht beide Produktionswege parallel.

Der Exporter benötigt mindestens diese Befehle:

```text
list-owned
export --quelle <kuerzel> --dry-run
export --quelle <kuerzel>
```

Er implementiert den gekapselten DDB-Ablauf:

```text
user-data
available-user-content
strikter Owned-Books-Filter
get-book-url/{bookId}
gestreamter ZIP-Download
book-codes für genau diese ID
readonly DB3-Entschlüsselung
SELECT ID, CobaltID, ParentID, Slug, Title, RenderedHTML FROM Content
HTML-Bereinigung und Markdown-Konvertierung
manifest.json + entries.jsonl
```

Alle DDB-URLs liegen in genau einem Adaptermodul. Verwende Zeitlimits, begrenzten Retry für 429/5xx,
keinen Retry für 401/403, sichere ZIP-Verarbeitung, Größenlimits, `.part`-Dateien und atomare
Artefaktfertigstellung. Bereinige ZIP, DB3 und Schlüssel auf Erfolgs- und Fehlerpfaden.

### 2. Artefaktvertrag

Implementiere Version 1 exakt nach dem Vorschlagsdokument. Lege den Vertrag und synthetische Fixtures
vor dem DB-Import fest. Das Artefakt enthält stabile DDB-IDs, Parent-Bezüge, Slug, Titel, Breadcrumb,
Kategorie, Quell-URL, Markdown und Hashes.

Validiere mindestens:

- `status == complete`,
- bekannte `schema_version`,
- Manifest-/Konfigurationsmetadaten stimmen exakt,
- JSONL- und Body-Hashes stimmen,
- keine doppelten IDs oder Parent-Zyklen,
- mindestens ein nicht leerer Eintrag,
- nur erlaubte Kategorien,
- nachvollziehbare Anzahl leerer/unbekannter Datensätze.

Konvertiere Tabellen in GFM-Markdown. Entferne aktive HTML-Inhalte. Lade in Version 1 keine Bilder;
erhalte sinnvollen Alt-Text. Erzeuge einen Abdeckungsbericht und bezeichne die erste Version als
Buchtext-MVP, nicht als semantisch vollständigen Import aller `RPG*`-Tabellen.

### 3. Offline-Importer

`importer/import_ddb.py` liest ausschließlich geprüfte lokale Artefakte. Es enthält keinen HTTP-,
Cobalt- oder Entschlüsselungscode.

Implementiere:

1. vollständige Validierung vor jeder dauerhaften DB-Änderung,
2. Staging-Tabelle für den gesamten neuen Buchbestand,
3. private Kandidaten-DB auf Basis der bisherigen privaten DB oder initial per SQLite-Backup der
   öffentlichen DB,
4. Backup der bisherigen privaten DB,
5. genau eine kontrollierte Transaktion für Quellen-Upsert, Quellenaustausch und FTS-Rebuild,
6. Rollback bei jeder Exception,
7. Schutz gegen null Einträge und ungewöhnlich großen Rückgang; Standardgrenze 70 Prozent,
8. `foreign_key_check`, `integrity_check`, Einträge-/FTS-Zählung und Stichproben vor Aktivierung,
9. atomare Aktivierung der privaten Kandidaten-DB mit `os.replace`,
10. idempotenten Re-Import ohne Dubletten.

Ein Buch ist genau eine Quelle mit `herkunft="ddb"`, `lizenz="privat"`, expliziter Edition, Sprache
und Priorität. DDB-URLs sind keine Seitenzahlen; `seite` bleibt ohne belastbare Seitenangabe `NULL`.

Ergänze in `app/admin.py` eindeutige Befehle für Artefaktprüfung und privaten DDB-Import. Die Befehle
müssen ein Dry-run beziehungsweise reine Validierung erlauben und mit nicht-null Exitcode scheitern.

### 4. Konfiguration und Dokumentation

Ersetze die ungenutzte `[ddb].proxy_url`-Konfiguration durch secret-freie Pfade und `[[ddb.buch]]`-
Metadaten. Buch-ID, Quellenkürzel, Titel, Sprache, Edition, Lizenz und Priorität sind Pflicht und werden
nicht geraten.

Aktualisiere erst nach erfolgreicher Implementierung die widersprüchlichen Desktop-/Proxy-Aussagen in
`CLAUDE.md`, `README.md`, technischem Konzept und Pi-Deployment. Markiere weiterhin klar:

- Cobalt stammt manuell aus einer eigenen angemeldeten Browsersitzung,
- der eigentliche Import läuft vollständig auf dem Pi,
- DDB ist eine undokumentierte, gekapselte Import-Schnittstelle,
- private Inhalte sind noch nicht für den authlosen Tunnel freigegeben.

## Kategorie-Mindestumfang

Mappe zentral und getestet:

- Spells → `zauber`
- Monsters/Bestiary → `monster`
- Equipment/Magic Items → `gegenstand`
- Classes → `klasse`
- Species/Races → `spezies`
- Backgrounds → `hintergrund`
- Feats → `talent`
- unbekannt → `regel`, im Bericht gezählt

Die Zuordnung basiert auf dem vollständigen Breadcrumb, nicht nur auf dem Titel der einzelnen Zeile.

## Tests

Schreibe lokale Tests mit Mocks und synthetischen Fixtures für mindestens:

1. Owned-Books-Filter einschließlich Abweisung geteilter/nicht eigener Inhalte.
2. Auth-, HTTP-, Retry-, JSON- und Source-ID-Fehler.
3. ZIP-Slip, Symlinks, Zip-Bomb-Limit, defekte/fehlende/mehrdeutige DB3.
4. Falscher Schlüssel und fehlende `Content`-Struktur.
5. HTML-Bereinigung, Tabellen, Links, Hierarchie und alle Kategorien.
6. Deterministisches Artefakt, Hashfehler und unvollständiges `.partial`.
7. Leerer/fehlerhafter Import erhält Altbestand und FTS.
8. Großer Rückgang wird ohne explizite Freigabe blockiert.
9. Erfolgreicher Re-Import ist idempotent und FTS-konsistent.
10. Öffentliche DB bleibt unverändert; private Kandidatenaktivierung ist atomar.
11. Kein Secret in argv, Environment, Logs, Exceptions, Artefakten oder Tempdateien.
12. Dauerhafter MCP-Container enthält kein Cobalt und führt keine DDB-Requests aus.

Live-DDB-Aufrufe gehören nicht in pytest. Der echte Pi-Dry-run und Ein-Buch-Pilot sind eine getrennte
manuelle Abnahme. Wenn die Entwicklungsumgebung kein ARM64-Pi oder kein echtes eigenes Buch erreicht,
markiere diese Punkte ausdrücklich als **offen** und behaupte nicht, die Gesamtaufgabe sei fertig.

## Arbeitsreihenfolge

Arbeite in kleinen, prüfbaren Phasen und führe nach jeder Phase die relevanten Tests aus:

1. A7-/Baseline-Audit.
2. Python/SQLite3MC-Phase-0-Spike.
3. Artefaktvertrag + Fixtures + Validator.
4. Gekapselter DDB-Client + Owned-Books-Filter.
5. Sicherer Download, DB-Lesen und Markdown-Konvertierung.
6. Offline-Import in private Kandidaten-DB.
7. Compose-/Admin-Bedienung und Secret-Härtung.
8. Vollständige automatische Tests.
9. Dokumentation.
10. Manueller ARM64-Dry-run und Ein-Buch-Pilot mit Nutzerunterstützung.

Stoppe und berichte konkret, wenn:

- A7 nicht erfüllt ist,
- die Zustimmung den benötigten Abruf nicht umfasst,
- Python die echte DDB-DB nicht lesen kann und der Node-Fallback erwogen werden muss,
- DDB-Antwortformat oder Buchschema nicht dem belegten Format entspricht,
- die einzige verbleibende Lösung private Inhalte über den authlosen Endpoint exponieren würde.

Rate in diesen Fällen keine Endpunkte, Schlüssel, Editionen, Buch-IDs oder Zugriffslösungen.

## Abschlussbericht

Liefere am Ende:

- geänderte und neue Dateien mit Zweck,
- tatsächlich ausgeführte Tests und genaue Ergebnisse,
- tatsächliches Zielsystem/Architektur des Builds,
- Ergebnis des ARM64-Spikes,
- Ergebnis des echten Dry-runs/Piloten oder klar markierte offene manuelle Abnahme,
- Import-/Re-Import-Zahlen und Qualitätsbericht,
- Nachweis, dass die öffentliche DB unverändert blieb,
- Secret-/Tempdatei-Prüfung,
- verbleibende Risiken und ausdrücklich den separaten Go-live-Blocker für private Bereitstellung.

## Copy-&-Paste-Startprompt

```text
Lies CLAUDE.md, docs/foliant-anforderungen.md,
docs/VORSCHLAG-DDB-IMPORT-RASPBERRY-PI.md und
CLAUDE-CODE-AUFTRAG-DDB-IMPORT-RASPBERRY-PI.md vollständig. Dies ist ein
Umsetzungsvorschlag, keine Freigabe zur öffentlichen Bereitstellung privater Inhalte.

Prüfe zuerst den aktuellen Git-Status, die unveränderte Test-Baseline und insbesondere,
ob A7 aus CLAUDE-CODE-KORREKTURAUFTRAG.md vollständig umgesetzt und getestet ist. Ist A7
nicht erfüllt, ändere keinen DDB-Code, sondern berichte die konkreten Blocker.

Wenn die Voraussetzungen erfüllt sind, implementiere den DDB-Buchimport phasenweise genau
nach dem Auftrag: vollständig auf Raspberry Pi ARM64, Python/SQLite3MC zuerst, nur eigene
Bücher, Cobalt ausschließlich verdeckt im kurzlebigen Importprozess, validiertes Artefakt,
offline Import in eine private Kandidaten-DB, atomarer und verlustsicherer Re-Import. Die
öffentliche data/foliant.sqlite und der authlose Tunnel dürfen keine DDB-Privatinhalte
erhalten. Verwende nur synthetische Fixtures und Mocks in automatischen Tests; markiere einen
noch nicht auf echter ARM64-Hardware durchgeführten Dry-run ausdrücklich als offen.

Lege vor Änderungen einen dateikonkreten Plan vor, arbeite in kleinen getesteten Phasen,
bewahre vorhandene Nutzeränderungen und committe oder pushe nichts ohne meine ausdrückliche
Anweisung.
```

