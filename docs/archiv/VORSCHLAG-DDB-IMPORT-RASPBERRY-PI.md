# VORSCHLAG: D&D-Beyond-Buchimport vollständig auf dem Raspberry Pi

> **Status: technischer Umsetzungsvorschlag – nicht implementiert, nicht verbindlich.**
>
> **Stand:** 10.07.2026  
> **Zweck:** Entscheidungs- und Umsetzungsgrundlage für einen späteren, getrennten Claude-Code-Auftrag.  
> **Wichtig:** Dieses Dokument ändert weder die verbindlichen Anforderungen noch erteilt es eine
> Freigabe, private DDB-Inhalte über den derzeit authlosen öffentlichen MCP-Endpunkt auszuliefern.

## 1. Annahmen und Abgrenzung

Dieser Vorschlag geht von folgenden Annahmen aus:

- Es liegt eine Zustimmung vor, die den automatisierten **lokalen** Abruf und die private Verarbeitung
  der selbst erworbenen D&D-Beyond-Bücher umfasst.
- Importiert werden ausschließlich Bücher, die der verwendete DDB-Account selbst besitzt
  (`isOwned == true`). Geteilte Bücher, Abenteuer, Charaktere und Kampagnendaten sind ausgeschlossen.
- Der Raspberry Pi läuft mit einem 64-Bit-Betriebssystem auf ARM64.
- Der Nutzer beschafft den kurzlebigen Cobalt-Wert aus seiner eigenen angemeldeten Browsersitzung und
  gibt ihn über eine SSH-Terminalsitzung verdeckt ein. Sämtlicher Abruf, die Entschlüsselung, die
  Konvertierung und der Datenbankimport laufen danach auf dem Pi.
- Die verwendeten DDB-Endpunkte sind nicht öffentlich dokumentiert. Der Import ist daher technisch
  wartbar zu kapseln, kann aber durch Änderungen bei D&D Beyond ausfallen.

Nicht Bestandteil dieses Vorschlags sind:

- ein DDB-Login-Flow oder automatisiertes Auslesen des Browsers,
- DDB-Charaktere, Kampagnen, Encounter oder Content-Sharing,
- Foundry VTT, Electron oder die vollständige Adventure-Muncher-Anwendung,
- ein dauerhaft laufender `ddb-proxy`,
- Bilder und Karten in Version 1,
- ein neuer OAuth-Provider oder eine andere spontan entworfene öffentliche Zugriffslösung.

## 2. Kurzentscheidung

Empfohlen wird eine zweistufige, vollständig auf dem Pi laufende Pipeline:

1. Ein **kurzlebiger Python-Importcontainer** lädt genau ein eigenes Buch, entschlüsselt dessen mobile
   Buchdatenbank und erzeugt ein unveränderliches, geprüftes Artefakt aus `manifest.json` und
   `entries.jsonl`. Dieser Container besitzt **keinen Zugriff auf die Foliant-Datenbank**.
2. Ein davon getrennter, vollständig offline laufender Python-Import übernimmt das Artefakt in eine
   **private Kandidatenkopie** der Foliant-Datenbank, prüft sie und aktiviert sie atomar als private
   Datenbank. Die gegenwärtig öffentlich/authlos bereitgestellte Datenbank bleibt unverändert.

Die bevorzugte technische Basis ist Python 3.12 mit
[`apsw-sqlite3mc`](https://pypi.org/project/apsw-sqlite3mc/). Das Paket stellt ARM64-Wheels bereit und
bündelt SQLite3 Multiple Ciphers. Vor der eigentlichen Implementierung ist dennoch ein verbindlicher
Machbarkeitstest mit einem echten eigenen DDB-Buch auf dem Pi erforderlich.

Nur wenn dieser Test trotz korrekter SQLCipher-v3-Parameter scheitert, ist ein kleiner Node-22-Helfer
mit `better-sqlite3-multiple-ciphers` der Fallback. Es sollen nicht dauerhaft zwei Implementierungen
gepflegt werden.

## 3. Warum nicht direkt in die Live-Datenbank importieren?

Die Trennung ist absichtlich:

- Der Prozess mit DDB-Netzzugriff und Cobalt-Geheimnis kann die Foliant-Datenbank nicht verändern.
- Ein abgelaufener Token, eine geänderte API, ein unvollständiger Download oder ein falscher
  Entschlüsselungsschlüssel gefährdet den vorhandenen Bestand nicht.
- Das geprüfte Artefakt erlaubt spätere Re-Imports ohne erneuten DDB-Abruf.
- Download/Entschlüsselung und fachliches Chunking lassen sich unabhängig testen.
- Private Buchdaten gelangen nicht versehentlich in die aktuell öffentlich verwendete DB-Datei.

Der vorhandene DDB-Stub in `importer/import_ddb.py` und der konfigurierte `ddb-proxy` werden für diese
Architektur ersetzt, nicht erweitert.

## 4. Zielarchitektur

```text
Nutzer über SSH
  │
  │ Cobalt verdeckt über TTY/stdin (nie argv, .env oder Compose-Environment)
  ▼
ddb-importer (Compose-Profil "ddb", kurzlebig, ausgehend ins Internet)
  │
  ├─ list-owned: nur EntityTypeID 496802664 UND isOwned == true
  ├─ signierte Buch-URL + Buchschlüssel abrufen
  ├─ ZIP gestreamt laden, nur DB3/Versionsinfo sicher extrahieren
  ├─ DB3 readonly entschlüsseln, Content zeilenweise lesen
  └─ HTML → Markdown → geprüftes Artefakt
       │
       ▼
data/private/ddb-artifacts/<quellenkuerzel>/<export-id>/
  ├─ manifest.json
  └─ entries.jsonl
       │
       │ kein Netz, kein Cobalt
       ▼
Foliant-Admin-Import (kurzlebiger Python-Prozess)
  ├─ Artefakt vollständig validieren
  ├─ private DB-Kandidatenkopie erzeugen
  ├─ Quelle atomar ersetzen + FTS rebuild
  ├─ Integritäts-, Mengen- und Stichprobenchecks
  └─ private Kandidaten-DB atomar aktivieren

Öffentlicher/authloser Foliant ──► data/foliant.sqlite
                                  (weiterhin ohne DDB-Privatinhalte)

Privater Kandidatenbestand ──────► data/private/foliant-private.sqlite
                                  (noch nicht öffentlich bereitstellen)
```

## 5. Technische Referenz für den DDB-Abruf

Der aktuelle Adventure Muncher zeigt folgenden funktionierenden Ablauf:

1. `POST /mobile/api/v6/user-data` – Token prüfen.
2. `POST /mobile/api/v6/available-user-content` – Berechtigungen lesen.
3. Strikt auf `EntityTypeID == 496802664` und `isOwned == true` filtern.
4. `POST /mobile/api/v6/get-book-url/{bookId}` – signierte Download-URL anfordern.
5. Bucharchiv gestreamt herunterladen.
6. `POST /mobile/api/v6/book-codes` – Schlüssel für genau die gewählte Source-ID anfordern.
7. Base64-Wert dekodieren und die enthaltene `.db3` readonly öffnen.
8. Die Buchinhalte aus folgender Struktur lesen:

```sql
SELECT
    ID           AS id,
    CobaltID     AS cobalt_id,
    ParentID     AS parent_id,
    Slug         AS slug,
    Title        AS title,
    RenderedHTML AS html
FROM Content;
```

Referenzen:

- [Adventure Muncher](https://github.com/MrPrimate/ddb-adventure-muncher)
- [DDB-Aufrufe in `ddb.js`](https://github.com/MrPrimate/ddb-adventure-muncher/blob/main/munch/data/ddb.js)
- [DB-Zugriff in `Database.js`](https://github.com/MrPrimate/ddb-adventure-muncher/blob/main/munch/adventure/Database.js)
- [SQLCipher-v3-Parameter von SQLite3 Multiple Ciphers](https://utelle.github.io/SQLite3MultipleCiphers/docs/ciphers/cipher_sqlcipher/)

Diese Quellen sind eine technische Referenz, keine öffentliche DDB-API-Garantie. Alle Endpunkte
müssen in genau einem kleinen Adaptermodul liegen. Kein anderer Projektteil darf DDB-URLs kennen.

## 6. Verbindliche Phase 0: Machbarkeit auf ARM64 beweisen

Vor der vollständigen Implementierung muss Claude Code einen isolierten Spike bauen. Er verändert
weder die Foliant-Datenbank noch bestehende Quellen.

### 6.1 Python-First-Test

Vorgeschlagene Basis:

- `python:3.12-slim`
- separat gepinnte DDB-Abhängigkeiten, insbesondere `apsw-sqlite3mc==3.53.2.0`
- keine Aufnahme von SQLite3MC in die dauerhaften Runtime-Abhängigkeiten

Pflichtprüfungen auf dem tatsächlichen Raspberry Pi:

1. Image baut als `linux/arm64`.
2. `platform.machine()` meldet `aarch64`.
3. `apsw` und die SQLite3MC-Erweiterung sind verfügbar.
4. Eine synthetische SQLCipher-v3-Testdatenbank lässt sich erstellen und readonly wieder öffnen.
5. Ein manueller `--dry-run` mit einem eigenen Buch erreicht mindestens:
   - Cobalt-Authentifizierung erfolgreich,
   - ausschließlich eigene Bücher aufgelistet,
   - ZIP vollständig und gültig,
   - Schlüssel passend zur angeforderten Buch-ID,
   - genau die erwartete `.db3` gefunden,
   - `Content` und die erwarteten Spalten vorhanden,
   - mindestens ein nicht leerer `RenderedHTML`-Datensatz lesbar,
   - keine Projekt-DB verändert,
   - kein Token, Schlüssel oder signierter URL-Querystring in Log oder Datei.

Die DB wird readonly geöffnet. Die Parameterreihenfolge ist sinngemäß:

```text
cipher = sqlcipher
legacy = 3
key = <nur im Speicher>
erste echte Leseabfrage zur Entschlüsselungsprüfung
```

`legacy=3` entspricht 1.024-Byte-Seiten, 64.000 KDF-Iterationen sowie SHA-1 für KDF/HMAC. Die
Implementierung soll die effektiven Annahmen in einem Test dokumentieren und nicht auf stillen
Bibliotheksdefaults beruhen.

### 6.2 Exakte Fallback-Regel

Node.js ist nur zulässig, wenn mindestens einer dieser Punkte belegt ist:

- Das ARM64-Wheel ist auf dem tatsächlichen Pi/Image nicht installierbar.
- APSW/SQLite3MC kann dieselbe echte DDB-DB mit den nachweislich richtigen Parametern nicht öffnen,
  während der aktuelle Adventure Muncher sie öffnen kann.

Kein Node-Fallback bei 401/403, abgelaufenem Token, DDB-JSON-Änderungen oder Netzfehlern – diese
Probleme wären in beiden Implementierungen identisch.

Fallback-Basis:

- offizielles `node:22-bookworm-slim`-ARM64-Image,
- gepinntes `better-sqlite3-multiple-ciphers`,
- nur kleiner CLI-Helfer, kein Electron, kein Foundry, kein vollständiger Adventure Muncher.

Der Fallback erzeugt exakt dasselbe Artefakt. Der offline Python-Import bleibt unverändert.

## 7. Vorgeschlagene Projektstruktur

### Neue Dateien

```text
Dockerfile.ddb-import
requirements-ddb.txt
importer/ddb_exporter/
  __init__.py
  __main__.py
  cli.py
  ddb_client.py
  book_archive.py
  html_to_markdown.py
  artifact.py
tests/fixtures/ddb/
  manifest-v1.json
  entries-v1.jsonl
tests/test_ddb_client.py
tests/test_ddb_artifact.py
tests/test_import_ddb.py
```

Ein separates `scripts/ddb-import-pi` kann später die zwei stabilen Befehle komfortabel verbinden.
Es ist kein Ersatz für klare Einzelkommandos und darf kein Secret in Argumente oder Umgebung kopieren.

### Zu ändernde Dateien

- `docker-compose.yml`
  - einmaligen Service im Profil `ddb` ergänzen,
  - `FOLIANT_COBALT` aus dem dauerhaft laufenden `foliant`-Service entfernen,
  - dem DDB-Exporter nur sein Arbeits-/Artefaktverzeichnis, niemals die DB mounten.
- `importer/import_ddb.py`
  - Artefaktprüfung, Normalisierung und privaten Kandidatenimport implementieren,
  - keinen HTTP- oder Cobalt-Code enthalten.
- `app/admin.py`
  - explizite Befehle für Artefaktprüfung und DDB-Import ergänzen.
- `config/foliant.example.toml`
  - `proxy_url` entfernen,
  - secret-freie Buchmetadaten und sichere private Zielpfade dokumentieren.
- `.env.example`
  - `FOLIANT_COBALT` entfernen; der Wert darf nicht dauerhaft in `.env` stehen.
- `.gitignore` und `.dockerignore`
  - private Artefakte, Arbeitsverzeichnisse, Kandidaten-DBs und Secret-Dateien ausschließen.
- `docs/ATTRIBUTION.md`
  - nur falls Code oder wesentliche Teile aus einer MIT-Quelle übernommen werden.
- `CLAUDE.md`, `README.md`, `docs/foliant-technisches-konzept.md` und
  `docs/DEPLOY-raspberry-pi.md`
  - erst nach erfolgreicher Implementierung die überholten Desktop-/Proxy-Aussagen aktualisieren.

Nicht ändern:

- echte `config/foliant.toml`,
- `.env`,
- bestehende SQLite-Dateien,
- private Quell- oder Buchdateien,
- der öffentliche Tunnel beziehungsweise seine Zugriffskonfiguration.

## 8. Konfigurationsvorschlag

Die Konfiguration enthält ausschließlich nicht geheime Metadaten. Beispiel:

```toml
[ddb]
artifact_dir = "data/private/ddb-artifacts"
work_dir = "data/private/ddb-work"
private_db = "data/private/foliant-private.sqlite"
min_reimport_ratio = 0.70

[[ddb.buch]]
id = 123
kuerzel = "ddb-phb-2024-en"
titel = "Player's Handbook (D&D Beyond)"
sprache = "en"
edition = "2024"
lizenz = "privat"
prioritaet = 40
```

Die `id = 123` ist bewusst nur ein Platzhalter. Keine Buch-ID, Edition oder Sprache wird erraten.
Der Export wird abgelehnt, wenn das konfigurierte Buch nicht als `isOwned == true` gemeldet wird.

Ein Buch entspricht genau einer Zeile in `quellen`:

- `herkunft = "ddb"`
- `lizenz = "privat"`
- Edition, Sprache und Priorität explizit aus der Konfiguration
- `dateipfad` zeigt auf das geprüfte Artefakt
- `seite = NULL`, sofern keine belastbare physische Seitenzahl vorliegt

Englischer offizieller DDB-Text erhält eine niedrigere Priorität als vorhandene deutsche offizielle
Quellen, aber eine höhere als ein gewünschter Open5e-Fallback. Die konkrete Zahl bleibt konfigurierbar.

## 9. Secret-Lebenszyklus

### Standardweg

Der Nutzer startet den One-shot-Container interaktiv über SSH:

```text
docker compose --profile ddb run --rm ddb-importer list-owned
docker compose --profile ddb run --rm ddb-importer export --quelle ddb-phb-2024-en --dry-run
docker compose --profile ddb run --rm ddb-importer export --quelle ddb-phb-2024-en
```

Der Prozess fragt Cobalt mit einer verdeckten TTY-Eingabe (`getpass`) ab. Der Wert erscheint nicht:

- in der Shell-History,
- in `docker inspect`,
- in `argv` oder `/proc/.../cmdline`,
- in `.env` oder Compose,
- in Logs, Exceptions, Artefakten oder Test-Fixtures.

Optional darf ein ausdrücklich gemountetes kurzlebiges Secret unter
`/run/secrets/ddb_cobalt` unterstützt werden. Es darf keine automatische persistente Secret-Datei im
Repo erzeugt werden.

Auch Buchschlüssel und signierte Download-URLs gelten als geheim. URL-Logs enthalten höchstens
Schema, Host und redigierten Pfad; POST-Bodies werden niemals geloggt.

Der DDB-Container hat:

- keine Ports,
- `restart: "no"`,
- read-only Root-Dateisystem,
- `cap_drop: [ALL]`,
- `no-new-privileges`,
- nur ein beschreibbares privates Work-/Artefakt-Mount,
- keinen Mount von `data/foliant.sqlite` oder `data/private/foliant-private.sqlite`.

## 10. Download- und Archivsicherheit

Der Adapter muss:

- Downloads auf Platte streamen und nicht vollständig in den RAM laden,
- zunächst nach `*.part` schreiben und erst nach vollständiger Prüfung atomar umbenennen,
- Connect-/Read-/Gesamttimeouts verwenden,
- 429 und vorübergehende 5xx begrenzt mit Backoff wiederholen,
- 401/403 nicht automatisch wiederholen,
- Antwortstatus, Inhaltstyp, plausible Größe und ZIP-Signatur prüfen,
- ein konfiguriertes Größenlimit und freien Speicher vorab prüfen,
- ZIP-Slip, absolute Pfade, `..`, Symlinks und Zip-Bombs ablehnen,
- nur die benötigte `.db3` und vorhandene Versionsinformation extrahieren,
- bei fehlender oder mehrdeutiger DB abbrechen,
- ZIP, DB3 und Schlüssel nach erfolgreichem Export sowie nach Fehlern bereinigen,
- Rohdateien nur mit einer ausdrücklichen lokalen Debug-Option behalten.

Ein Import-Lock verhindert parallele Exporte beziehungsweise Imports desselben Buchs.

## 11. HTML, Hierarchie und Kategorien

Jede nicht leere `Content`-Zeile wird zunächst als eigenständiger logischer Datensatz behandelt.

- Hierarchie über `ID`, `CobaltID` und `ParentID` auflösen.
- Parent-Zyklen und doppelte IDs als Fehler behandeln.
- Fehlende Parents zählen und im Manifest ausweisen; nicht still raten.
- HTML vor der Konvertierung von `script`, `style`, `iframe`, Formularen und Eventhandlern bereinigen.
- Tabellen als GFM-Markdown erhalten.
- Bilddateien in Version 1 nicht herunterladen; Alt-Text beziehungsweise Bildbeschreibung erhalten.
- Linktexte erhalten, DDB-Links normalisieren und als Provenienz im Artefakt speichern.
- Exakte doppelte IDs ablehnen. Identische Body-Hashes nur berichten, nicht ohne belegte Regel löschen.
- Leere Containerzeilen zählen und überspringen; ein insgesamt leeres Buch ist ein Fehler.

Kategoriezuordnung aus dem vollständigen Breadcrumb, mindestens:

| Breadcrumb-Signal | Foliant-Kategorie |
|---|---|
| Spells | `zauber` |
| Monsters, Bestiary | `monster` |
| Equipment, Magic Items | `gegenstand` |
| Classes | `klasse` |
| Species, Races | `spezies` |
| Backgrounds | `hintergrund` |
| Feats | `talent` |
| alles andere | `regel` |

Die Regeln müssen zentral, deterministisch und mit Fixtures getestet sein. Unbekannte Pfade werden
als `regel` importiert und im Abdeckungsbericht gezählt.

### Vollständigkeitsgrenze von Version 1

`Content.RenderedHTML` deckt den gerenderten Buchtext ab. Manche strukturierten Monster- oder
Detaildaten können zusätzlich in Tabellen wie `RPGMonster` oder `ContentDetail` liegen. Deshalb heißt
Version 1 ausdrücklich **Buchtext-MVP**, nicht „vollständig semantischer Import aller DDB-Entitäten“.

Jeder Dry-run erzeugt einen Abdeckungsbericht mit:

- Tabellenliste der DB,
- Gesamtzahl `Content`-Zeilen,
- Anzahl nicht leerer und übersprungener Zeilen,
- Kategorien und unbekannte Breadcrumbs,
- fehlende Parents und Body-Duplikate,
- Vorhandensein relevanter `RPG*`-/Detailtabellen.

Sondertabellen werden erst in einer späteren Phase integriert, wenn Stichproben einen konkreten
Textverlust belegen.

## 12. Artefaktvertrag Version 1

### Verzeichnis

```text
data/private/ddb-artifacts/<quellenkuerzel>/<export-id>/
  manifest.json
  entries.jsonl
```

Es wird zuerst in ein `.partial-<uuid>`-Verzeichnis geschrieben. Erst nach vollständiger Validierung,
Hashbildung und `fsync` wird es atomar auf den endgültigen Namen gesetzt.

### `manifest.json`

Mindestens:

```json
{
  "schema_version": 1,
  "status": "complete",
  "source_key": "ddb-phb-2024-en",
  "ddb_source_id": 123,
  "title": "Player's Handbook (D&D Beyond)",
  "language": "en",
  "edition": "2024",
  "license": "privat",
  "exported_at": "2026-07-10T12:00:00Z",
  "exporter_version": "1.0.0",
  "book_version": null,
  "entry_count": 1,
  "empty_content_count": 0,
  "unknown_category_count": 0,
  "entries_sha256": "...",
  "archive_sha256": "..."
}
```

### Eine Zeile in `entries.jsonl`

```json
{
  "ddb_id": "1",
  "cobalt_id": "chapter-1",
  "parent_id": null,
  "slug": "chapter-1",
  "title": "Chapter 1",
  "breadcrumb": ["Player's Handbook", "Chapter 1"],
  "category": "regel",
  "source_url": "https://www.dndbeyond.com/sources/...",
  "body_md": "...",
  "body_sha256": "..."
}
```

Der Vertrag wird vor dem DB-Code festgelegt und mit lokalen, vollständig synthetischen Fixtures
getestet. Private Texte, echte Schlüssel und echte API-Antworten werden nie committed.

## 13. Offline-Import und Aktivierung

### Voraussetzung A7

Der DDB-Import beginnt erst, wenn A7 aus `CLAUDE-CODE-KORREKTURAUFTRAG.md` umgesetzt und durch Tests
belegt ist. Der aktuelle `importiere_markdown`-Pfad löscht den Altbestand vor einer Nullprüfung und
committet selbst; daran darf der DDB-Import nicht angebunden werden.

### Empfohlener Ablauf

1. Manifest, JSONL-Hash, Schema-Version und alle Pflichtfelder prüfen.
2. Edition, Sprache, DDB-ID und Quellenkürzel exakt gegen die secret-freie Konfiguration prüfen.
3. Alle JSONL-Zeilen vollständig in eine temporäre Staging-Tabelle laden und plausibilisieren.
4. Null Einträge, leere Bodies, doppelte IDs, unbekannte Kategorien außerhalb der erlaubten Menge
   oder ein unplausibler Mengenrückgang brechen ab.
5. Als Basis die bestehende private DB verwenden; falls sie nicht existiert, per SQLite-Backup-API
   eine Kandidatenkopie aus der öffentlichen DB erzeugen.
6. Vor jeder Änderung ein wiederherstellbares Backup der bisherigen privaten DB anlegen.
7. In genau einer Transaktion:
   - vollständigen Quellen-Upsert ausführen,
   - vorhandene Einträge genau dieser Quelle löschen,
   - Staging-Zeilen einfügen,
   - FTS neu aufbauen,
   - Quellen-/Eintragsedition und Mengen prüfen.
8. Vor Commit beziehungsweise Aktivierung ausführen:
   - `PRAGMA foreign_key_check`,
   - `PRAGMA integrity_check`,
   - Einträge-vs.-FTS-Zählung,
   - Kategorieverteilung,
   - definierte Stichprobenabfragen.
9. Bei jedem Fehler Rollback; die bisherige private DB bleibt unverändert.
10. Erfolgreiche Kandidaten-DB per `os.replace` atomar als
    `data/private/foliant-private.sqlite` aktivieren.

Der Schwellwert für ungewöhnliche Rückgänge ist standardmäßig 70 Prozent des bisherigen
Quellenbestands. Eine Unterschreitung erfordert einen expliziten, auffälligen Force-Schalter und wird
nicht durch normalen Re-Import akzeptiert.

## 14. Private Bereitstellung bleibt ein eigener Go-live-Blocker

Der bestehende Cloudflare-/MCP-Endpunkt ist laut aktueller Projektdokumentation authlos, weil er nur
frei redistribuierbare Daten enthalten soll. Nach einem DDB-Import gilt diese Begründung nicht mehr.

Deshalb muss die Implementierung standardmäßig sicherstellen:

- DDB wird ausschließlich nach `data/private/foliant-private.sqlite` importiert.
- Der bestehende `foliant`-Service verwendet weiterhin `data/foliant.sqlite`.
- Die private DB wird nicht in den Tunnel eingebunden.
- Ein Dry-run oder Test darf nicht still die Runtime-Konfiguration umschalten.
- Der DDB-Auftrag gilt als technisch abgeschlossen, wenn Export und lokaler Privatimport auf dem Pi
  funktionieren; er gilt **nicht** als öffentlich ausgerollt.

Vor Nutzung der privaten DB durch einen Cloud-Connector ist eine gesonderte, mit dem verwendeten
Connector kompatible Zugriffslösung zu entscheiden. Dieser Vorschlag baut nicht nebenbei einen
OAuth-Provider und akzeptiert keinen geheimen URL-Pfad als Authentifizierung.

## 15. Compose-Vorschlag

Der neue Service wird nur mit `--profile ddb` gestartet und beendet sich immer:

```yaml
# Nur schematischer VORSCHLAG – nicht direkt übernehmen.
ddb-importer:
  profiles: ["ddb"]
  build:
    context: .
    dockerfile: Dockerfile.ddb-import
  restart: "no"
  read_only: true
  tmpfs:
    - /tmp:size=128m,noexec,nosuid,nodev
  volumes:
    - ./config:/app/config:ro
    - ./data/private/ddb-work:/work
    - ./data/private/ddb-artifacts:/artifacts
  cap_drop: ["ALL"]
  security_opt:
    - no-new-privileges:true
```

Kein `ports`, kein DB-Mount, kein `FOLIANT_COBALT`-Environment und kein permanenter Neustart.

## 16. Tests und Abnahmekriterien

### Vollautomatisch, ohne Netz und ohne echte Secrets

- DDB-Client mit gemocktem Transport:
  - Auth-Erfolg und Auth-Fehler,
  - nur `EntityTypeID == 496802664` und `isOwned == true`,
  - geteilte/nicht eigene Bücher werden abgelehnt,
  - kein `noCheck`-/Bypass-Pfad,
  - 401/403 ohne Retry, begrenzter Retry für 429/5xx,
  - ungültiges/leeres JSON und falsche Source-ID.
- Archivtests:
  - gültiges ZIP,
  - defektes ZIP, ZIP-Slip, Symlink, Zip-Bomb-Limit,
  - fehlende oder mehrere DB3-Dateien,
  - falscher Schlüssel und fehlende `Content`-Tabelle.
- Konvertierung:
  - Überschriften, Links, Listen, Tabellen und Asides,
  - Entfernung aktiver HTML-Inhalte,
  - Hierarchie, Zyklus, fehlender Parent,
  - alle Kategoriezuordnungen und unbekannter Fallback.
- Artefakt:
  - deterministische JSONL-Ausgabe,
  - Hashprüfung und atomare Fertigstellung,
  - unvollständiges `.partial` niemals importierbar.
- DB-Import:
  - leerer Import erhält Altbestand und FTS,
  - Parse-/Insertfehler erhält Altbestand und FTS,
  - Hash-/Metadatenfehler erhält Altbestand,
  - großer Mengenrückgang wird blockiert,
  - erfolgreicher Re-Import ist idempotent,
  - Quelle, Edition, Sprache, Lizenz und Kategorien stimmen,
  - `integrity_check`, `foreign_key_check` und FTS-Zählung sind sauber,
  - öffentliche DB bleibt byteweise beziehungsweise logisch unverändert.
- Secret-Tests:
  - Token nicht in argv, Env, Logs, Exceptions, Artefakten oder Tempdateien,
  - Schlüssel und signierte URL redigiert,
  - Roh-ZIP/DB3/Schlüssel nach Erfolg und Fehler entfernt,
  - dauerhafter `foliant`-Container enthält kein Cobalt.

### Manuelle Abnahme auf dem echten Pi

1. ARM64-DDB-Image baut ohne Emulation.
2. `--dry-run` mit einem eigenen Buch erfüllt Phase 0.
3. Export eines einzelnen kleinen/überschaubaren Regelbuchs erzeugt ein vollständiges Artefakt.
4. Abdeckungsbericht und mindestens zehn bekannte Stellen werden manuell geprüft.
5. Private Kandidaten-DB enthält erwartete Quelle/Kategorien und beantwortet lokale Stichproben.
6. Re-Import desselben Buchs erzeugt keine Dubletten.
7. Absichtlich abgebrochener Download und falscher Token verändern keine DB.
8. Öffentliche DB und öffentlicher MCP-Bestand enthalten weiterhin keine DDB-Inhalte.

## 17. Empfohlene Umsetzungsreihenfolge

1. **Voraussetzungen prüfen:** A7 vollständig umgesetzt; Baseline-Tests grün.
2. **Phase-0-Spike:** Python/SQLite3MC auf ARM64 plus echter readonly Dry-run.
3. **Artefaktvertrag festlegen:** Fixtures und Validator zuerst.
4. **DDB-Exporter:** Client, Ownership-Filter, Download, Entschlüsselung, Konvertierung.
5. **Offline-Import:** private Kandidaten-DB, Backup, Transaktion, Checks, atomare Aktivierung.
6. **Compose/Admin-CLI:** sichere One-shot-Bedienung über SSH.
7. **Automatische Tests:** ausschließlich Fixtures/Mocks.
8. **Ein-Buch-Pilot:** Dry-run, Export, lokale Qualitätsprüfung, Re-Import.
9. **Dokumentation aktualisieren:** erst nach nachgewiesener Funktion.
10. **Separater Auftrag:** Zugriffsschutz und private MCP-Bereitstellung entscheiden.

## 18. Definition of Done dieses Vorschlags

Der vorgeschlagene Import gilt als umgesetzt, wenn:

- ein selbst besessenes DDB-Buch vollständig auf dem Raspberry Pi exportiert werden kann,
- kein DDB-Secret den kurzlebigen Prozess überlebt,
- Exporter und DB-Schreiber technisch getrennt sind,
- ein validiertes, reproduzierbares Artefakt entsteht,
- der offline Import atomar, idempotent und verlustsicher ist,
- die private Kandidaten-DB alle Integritätsprüfungen besteht,
- alle automatischen Tests ohne Netz und ohne echte Zugangsdaten laufen,
- ein echter ARM64-Dry-run und Ein-Buch-Pilot dokumentiert sind,
- die öffentliche/authlose Datenbank garantiert keine privaten DDB-Texte enthält,
- Dokumentation und tatsächliche Befehle übereinstimmen.

Die Definition of Done umfasst ausdrücklich **nicht** die Freischaltung privater Inhalte über den
öffentlichen Claude-Connector. Das bleibt eine getrennte Betriebs- und Sicherheitsentscheidung.

