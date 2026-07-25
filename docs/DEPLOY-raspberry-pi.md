# Deployment & Betrieb: Foliant auf dem Raspberry Pi 4

Detailtiefe zum kanonischen Weg in `RUNBOOK.md`: Ersteinrichtung, Zugangsschutz,
Import-Wege (born-digital, OCR, DDB) und laufender Betrieb. Später 1:1 auf einen Mac mini
(Apple Silicon, ebenfalls ARM64) umziehbar.

**Betriebsmodell: der Pi betreibt, der Mac entwickelt.** Server **und** Importe laufen auf
dem Pi; der Mac ist nur für Entwicklung (Code schreiben) und Administration (Code aufs Pi
schieben, Importe per SSH auslösen). So gibt es genau einen operativen Bestand, und der Pi
überlebt einen Mac-Ausfall.

## Laufende Container

```
Cloudflare Named Tunnel ──► gateway (Caddy :8080) ──┬── /mcp, /<token>/mcp, /health, /ready ──► foliant:8000
                                                    └── alles andere ──────────────────────► web:8080 (Charakterbogen)
```

| Dienst | Rolle |
|---|---|
| `foliant` | MCP-Server (uvicorn), 16 Tools, read-only auf `data/foliant.sqlite` |
| `web` | Charakterbogen-Website (eigene Kennwort-Seite, gehärtet: `read_only`, `cap_drop: ALL`) |
| `gateway` | Caddy davor; routet nach Pfad. Keine Access-Logs (der MCP-Pfad enthält das Geheim-Token) |
| `cloudflared` | Named Tunnel → `dnd.magnetron.me`, Origin `http://gateway:8080` |
| `datasette` | optional (`--profile admin`), read-only Datenblick, nur `127.0.0.1` |
| `ddb-exporter` | optional (`--profile ddb`), kurzlebiger DDB-Export, ohne DB-Mount |

**Warum Container:** Isolation gegenüber anderen Projekten auf demselben Gerät,
ARM64-Portabilität (Pi 4 → Apple-Silicon-Mac mini, gleiches `Dockerfile`/`compose`) und
reproduzierbares Neuaufsetzen. *(Alternative wäre venv + `systemd` — einfacher für ein
einzelnes Projekt, aber ohne Mehrprojekt-Isolation und nicht auf den Mac portierbar.)*

---

## 1. Ersteinrichtung

### Pi vorbereiten
- **64-bit Raspberry Pi OS Lite** flashen (64-bit ist Pflicht für ARM64-Images; Lite =
  headless). Im Imager beim Flashen SSH aktivieren + Nutzer/WLAN setzen.
- `ssh <nutzer>@<pi-ip>` · `sudo apt update && sudo apt full-upgrade -y`

### Docker installieren
```
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
sudo systemctl enable docker      # startet Docker beim Boot (wichtig fuer Auto-Restart)
```
Danach einmal aus- und wieder einloggen (Gruppen-Update greift). Test: `docker run --rm hello-world`.

### Projekt aufs Pi bringen
```sh
# vom Mac; Excludes schuetzen den Pi-Bestand und die privaten Module
rsync -a --exclude '.git' --exclude '.venv*' --exclude 'data' --exclude 'quellen' \
      --exclude 'config/foliant.toml' --exclude '.env' --exclude '.claude' \
      ./ pi@<pi-host>:~/foliant/
```
Danach `.env` anlegen (`cp .env.example .env`) und ausfüllen (Tunnel-Token, Pfad-Token,
Website-Kennwort, Übersetzungsprovider — siehe unten).

> **Nie `--delete` und nie `data/` mitschicken.** Die Mac-DB ist nur ein Subset und würde
> den vollen Pi-Bestand überschreiben; gitignorierte Privatmodule würden verschwinden.

### Cloudflare Named Tunnel
- Zero-Trust-Dashboard → Networks → Tunnels → **Create tunnel** (Typ: Cloudflared).
- Token kopieren → auf dem Pi in `.env` als `CLOUDFLARE_TUNNEL_TOKEN=`.
- Public-Hostname-Route: `dnd.magnetron.me` → Service **`http://gateway:8080`**.
  *Voraussetzung:* `magnetron.me` läuft über Cloudflare-DNS.
  Unter *Additional application settings* **nichts** ändern — insbesondere
  **„Disable Chunked Encoding" aus lassen** (zerstört SSE/MCP).

### Starten
```
cd foliant
docker compose up -d --build
docker compose ps                     # foliant, web, gateway, cloudflared "up/healthy"?
curl http://localhost:8000/health     # {"status":"ok","name":"Foliant"}
```
Läuft dauerhaft (`restart: unless-stopped`) und startet nach Reboot automatisch.

> **Beim Bauen einzelner Dienste immer `--no-deps`:**
> `docker compose up -d --no-deps --build web gateway`. Ohne das baut Compose über
> `depends_on` **auch `foliant` neu** und startet den Live-MCP durch.

---

## 2. Zugang absichern (Geheimpfad + IP-Allowlist)

Seit dem DDB-Import serviert der Tunnel **private Buchinhalte** → der Endpoint ist nicht
offen (NF3/NF4). Zwei Schichten, beide ohne Nutzer-Management (Details: `app/zugriff.py`):

1. **Geheimpfad** — die URL ist der Schlüssel:
   ```
   python3 -c "import secrets; print(secrets.token_urlsafe(18))"   # Token erzeugen
   # auf dem Pi in ~/foliant/.env:  FOLIANT_PFAD_TOKEN=<wert>
   docker compose up -d --build foliant
   ```
   Connector-URL = `https://dnd.magnetron.me/<wert>/mcp`; der alte `/mcp` liefert 404.
   Der Token muss **≥ 16 Zeichen** haben, sonst bricht der Start ab (SYN-P1-004).
   Geheimer **Pfad**, nicht geheime Subdomain — Subdomains leaken über
   Zertifikats-Transparenz-Logs.
2. **IP-Allowlist** — nur Anthropics veröffentlichte Egress-Ranges (`160.79.104.0/21`,
   `2607:6bc0::/48`, Quelle: platform.claude.com/docs/en/api/ip-addresses) erreichen den
   MCP-Pfad; geprüft wird die von der Cloudflare-Edge gesetzte `CF-Connecting-IP`. Eine
   geleakte URL ist damit **nur über Claude** nutzbar, nie per curl/Scanner/Browser.
   Lokale Aufrufe ohne Edge-Header (Container-curl, Healthcheck, LAN) bleiben möglich;
   `/health` bleibt immer offen (nur Status, keine Inhalte — trägt das Monitoring).
   Schalter in `.env`: `FOLIANT_IP_FILTER=aus` (Debug), `FOLIANT_ERLAUBTE_IPS=<cidr,cidr>`.
   Blockierte Zugriffe stehen in `docker compose logs foliant`.

**Token-Rotation bei Leak:** neuen Token in `.env` → `docker compose up -d --build foliant`
→ neue URL an die Runde. **Alte Logs gelten als tokenbelastet** (der Pfad *war* das Secret);
Access-Logs sind per `--no-access-log` aus, Blockier-Logs werden redigiert.

**Der 403-Test ist Pflicht nach jeder Caddyfile-Änderung:**
```sh
curl -s -o /dev/null -w '%{http_code}\n' -H 'CF-Connecting-IP: 8.8.8.8' \
     http://127.0.0.1:8080/<TOKEN>/mcp     # muss 403 sein
```
Ginge `CF-Connecting-IP` hinter Caddy verloren, wäre die IP-Allowlist *lautlos* aus (der
Peer wäre dann Caddy = private IP = durchgelassen).

**Optionales Upgrade (blockt schon an der Cloudflare-Kante):** Dashboard → Security rules
(ältere UI: Security → WAF → Custom rules), Aktion **Block**:
```
(http.host eq "dnd.magnetron.me" and http.request.uri.path contains "/mcp" and not ip.src in {160.79.104.0/21 2607:6bc0::/48})
```
`http.host` **niemals** weglassen (sonst trifft die Regel Davids Smarthome-Tunnel).
`uri.path` statt `uri` (sonst umgeht `?x=/mcp` die Regel). `contains "/mcp"` hält den
Geheim-Token aus der Cloudflare-Konfiguration heraus. Regel **nie löschen und neu anlegen** —
im Löschfenster fehlt die Edge-Schicht.

**Verhaltensregeln für die Runde** (gehören in die Spieler-Anleitung): URL nicht
weitergeben, Inhalte nicht weiterverbreiten (privat erworbene Bücher).

---

## 3. Website (Charakterbogen-Übersetzer)

Die Website ist authlos gebaut und **jede Konvertierung kostet Anthropic-API-Geld** — der
Hostname steht über Certificate-Transparency-Logs öffentlich. Der Zugang ist deshalb eine
eigene **Kennwort-Seite in der App** (`web.py`), nicht HTTP-Basic-Auth (die erzwingt im
Browser immer ein Benutzerfeld; Eigentümer-Wunsch war *ein* Kennwort).

```
# Pi-.env:
WEB_PASSWORT=<kennwort-der-runde>
ANTHROPIC_API_KEY=sk-ant-…      # eigener Workspace mit Spend-Limit (harter Kostendeckel!)
ANTHROPIC_MODEL=claude-sonnet-5
```
```sh
# glossar-nur-DB erzeugen, BEVOR web startet (sonst legt Docker ein Verzeichnis statt der Datei an):
python3 -m app.charakterbogen.glossar_export data/foliant.sqlite data/glossar_web.sqlite
docker compose up -d --no-deps web
```
- **Fail-closed:** Fehlt `WEB_PASSWORT`, ist die Seite zu (503/401) — nie versehentlich offen.
- Signierter `HttpOnly`-Keks (30 Tage, HMAC **mit dem Kennwort als Schlüssel** → Kennwort
  ändern entwertet alle alten Kekse sofort).
- **`POST /bogen` ist selbst gesperrt**, nicht nur die Seite versteckt — die teure Route ist zu.
- Bremse gegen Durchprobieren: 8 Fehlversuche je Absender-IP → 5 min Sperre, plus 1 s
  Verzögerung pro Fehlversuch.
- Ohne `ANTHROPIC_API_KEY` läuft alles außer `POST /bogen` (→ 503, „Übersetzung momentan
  nicht verfügbar"). Pipeline und Details: `CHARAKTERBOGEN-MVP.md`.

---

## 4. Inhalte importieren

Alle Importe laufen **im Container auf dem Pi**. PyMuPDF4LLM funktioniert auf ARM (nur
langsamer; der Import ist einmalig, z. B. über Nacht). Docling (ML-Fallback für schwierige
Statblöcke) ist auf ARM zäh und speicherhungrig — nur bei Bedarf aktivieren.

```
docker compose exec foliant python db/init_db.py data/foliant.sqlite
docker compose exec foliant python -m app.admin import --quelle srd-de
docker compose exec foliant python -m app.admin import --quelle open5e-srd-2024
docker compose exec foliant python -m app.admin import --quelle glossar
docker compose exec foliant python -m app.admin check
```
Quell-PDFs dazu nach `~/foliant/quellen/` legen. **Edition ist in `config/foliant.toml`
Pflicht und wird nie geraten** — unklar heißt: nicht importieren.

### 4a. Gescannte PDFs (OCR-Vorstufe)
Viele Buch-PDFs sind Scans ohne Textschicht; ein Guardrail lehnt mehrheitlich textlose PDFs
beim Import bewusst ab, statt eine Rumpf-Quelle zu schreiben.
```
scp Buch.pdf pi@<pi-host>:~/foliant/quellen/                       # 1. Scan aufs Pi
docker compose exec foliant python -m app.admin pdf-triage         # 2. Befund
docker compose exec foliant python -m app.admin ocr-pdf --datei quellen/Buch.pdf   # 3. OCR
#    Alt-OCR-Textschicht vorhanden: zusaetzlich --redo  |  kompletter Neuaufbau: --voll
# 4. Quelle in config/foliant.toml registrieren (edition PFLICHT), dateipfad = data/ocr/Buch.ocr.pdf
docker compose exec foliant python -m app.admin import --quelle <kuerzel>   # 5. Import
docker compose exec foliant python -m app.admin check                       #    + Stichprobe (O3)
```
Dauer ~15–45 min/Buch auf dem Pi (deu+eng). Erwartung ehrlich: OCR-Text ist fehleranfälliger
als born-digital (v. a. Statblöcke/Tabellen/Zahlen) → Stichprobe vor Freigabe; Scans unter
~300 dpi werden deutlich schlechter. Das Original in `quellen/` bleibt unangetastet,
`data/ocr/` hält die OCR-Fassung (vom Backup abgedeckt).

**Sonderfall Browser-Druck-PDFs (DDB-Ausdrucke):** Je nach Schaden der Textschicht
(Kerning-Risse, Mojibake-Fonts, fi/fl-Ligaturverlust) läuft der Import über die reparierte
Original-Schicht (Muster `efota`) oder die Voll-OCR-Fassung (`ocr-pdf --voll`, Muster
`frhof`) — je mit kuratierter `BEREINIGUNG` + `SPLIT_REGELN` pro Buch
(`importer/import_markdown.py`). Die **Konvertierung nach Markdown passiert am Mac**, das
Markdown ist das Import-Artefakt (`quellen/md/<kuerzel>.md`, `dateipfad` zeigt darauf) — die
pymupdf4llm-Heading-Erkennung ist für diese PDFs umgebungsempfindlich. Zwei Leitplanken sind
fest verdrahtet: `use_ocr=False` (pymupdf4llm OCRt sonst **still**, sobald Tesseract im Image
ist) und der Scan-Guardrail.

### 4b. DDB-Bücher (Konto)
Zwei getrennte Schritte: **Export** braucht Netz + Cobalt, **Import** läuft offline.
Der Exporter ist ein kurzlebiger, gehärteter Container (`--profile ddb`, `read_only`,
`cap_drop: ALL`, **ohne DB-Mount**).

```sh
# einmalig: Exporter-Image bauen (installiert apsw-sqlite3mc fuer arm64)
docker compose --profile ddb build ddb-exporter

# 1. Cobalt bereitstellen: den CobaltSession-Wert aus einer angemeldeten dndbeyond.com-Sitzung
#    (Entwicklertools -> Application -> Cookies) in ~/.ddb-cobalt legen. Wie ein Passwort behandeln.
#    Wegen cap_drop: ALL muss die Datei lesbar sein - kurzzeitig chmod 644.
docker compose --profile ddb run --rm \
  -v /home/pi/.ddb-cobalt:/run/secrets/ddb_cobalt:ro ddb-exporter sync
rm -f ~/.ddb-cobalt        # Secret SOFORT entfernen

# 2. Import in die bediente DB (Einmal-Container mit explizitem Privat-Mount, SYN-P1-005:
#    der laufende Serve-Container sieht data/private nicht)
docker compose run --rm -v ./data/private:/app/data/private \
  foliant python -m app.admin ddb-import-all
docker compose restart foliant
```

**Was `sync` lädt:** alle eigenen Regelbücher, automatisch über das öffentliche
DDB-Verzeichnis aufgelöst; schon Exportiertes wird übersprungen.
- Ältere Bücher ohne Content-Text kommen aus den strukturierten Detailtabellen
  (Zauber/Monster/Talente/Spezies als Einzeleinträge) — im Bericht „Quelle: Detailtabellen".
- Abenteuer-/Setting-Bände werden geladen, aber als Spoiler-Inhalt **gekennzeichnet**
  (`inhaltsart=abenteuer_setting` → löst in jeder Antwort den Spoiler-Hinweis aus).
  **Playtest-Material wird gar nicht erst importiert** (SYN-P0-007).
- **Regelversion immer korrekt, nie geraten (V1/Q3):** Die Edition kommt autoritativ aus der
  Buch-DB (`RPGSourceCategory` bzw. `ReleaseDate`). Ist sie **nicht eindeutig** (z. B. „Sage
  Advice & Errata", laufende Errata über beide Editionen), wird das Buch **nicht geladen**,
  sondern gemeldet. Soll es trotzdem rein: `[[ddb.buch]]` mit explizitem `edition` in
  `config/foliant.toml` und `export --quelle <kuerzel>`.
- Bewusst ausgelassen: Premade-Character-Pakete. Nicht ladbar sind Bücher, die die
  DDB-Mobile-API mit `status=error` verweigert — sie werden im Bericht genannt.

**Nützliche Varianten:** `sync --dry-run` · `sync --force` (nach Errata) ·
`ddb-import-all --dry-run` · `admin ddb-remove --quelle <kuerzel>` (falsch geladene Quelle).

**Wohin die Bücher landen,** steuert `config/foliant.toml`:
`[ddb] ins_hauptbestand = true` → Merge in die **bediente** `data/foliant.sqlite`, damit über
den Connector durchsuchbar. **So läuft der Pi** (bewusste, protokollierte
Eigentümer-Entscheidung, `ATTRIBUTION.md`; abgesichert durch Geheimpfad + IP-Allowlist).
Ohne diese Zeile landen sie in `data/private/foliant-private.sqlite`, die der Endpoint nicht
serviert. Der Merge ist in beiden Fällen atomar, mit Backup und Integritätsprüfung; SRD und
Open5e bleiben erhalten.

**Lokale Entwickler-Variante** (Mac, ohne Container): Cobalt in den macOS-Keychain
(`security add-generic-password -U -a foliant -s foliant-ddb-cobalt -w`, verdeckte Eingabe —
so steht der Wert nie in der Befehlszeile), dann
`.venv-ddb/bin/python -m importer.ddb_exporter sync` und
`.venv/bin/python -m app.admin ddb-import-all`.

**Sicherheit:** Cobalt lebt nur im Keychain oder kurzlebig im TTY/Container-Secret — nie in
Git, `.env`, Befehlszeile oder Logs. Der Exporter berührt **keine** Foliant-Datenbank;
heruntergeladene Archive und entschlüsselte Buch-DBs werden nach jedem Lauf gelöscht.

---

## 5. Laufender Betrieb

- **Readiness statt Health (SYN-P1-011):** `curl http://localhost:8000/ready` prüft DB + FTS
  (503 bei kaputtem/leerem Bestand). `/health` ist der reine Prozess-Ping für externes
  Uptime-Monitoring (z. B. UptimeRobot auf `https://<host>/health`) und bleibt immer offen.
- **Backup:** `admin backup` (siehe `RUNBOOK.md` §6) — konsistentes Online-Backup über die
  SQLite-Backup-API, verifiziert und rotiert. **Nicht** `cp`/`rsync` auf die offene Datei.
- **Neue Inhalte einspielen:** aktualisierte `foliant.sqlite` nach `data/` kopieren →
  `docker compose restart foliant`. Rebuild nur bei Code-/Dependency-Änderung.
- **Nach jeder Code-Änderung Pflicht:** `docker compose up -d --build foliant`. Das Image
  **backt den Code ein** (`COPY`) — ein reines `rsync` aktualisiert die Dateien, **nicht den
  laufenden Container**. Ein Import lief dann still mit ALTEM Code weiter und meldete
  „erfolgreich" bei unveränderten Daten. `data/` bleibt gemountet; nur der Code muss neu
  gebacken werden.
- Logs: `docker compose logs -f foliant` · Neustart: `docker compose restart foliant`
- DB-Journal steht bewusst auf **DELETE** (Bind-Mount-kompatibel) — nicht auf WAL umstellen.
- **Ressourcen:** Foliant selbst ist leichtgewichtig (< ~200 MB). Bei mehreren Projekten auf
  einem Pi 4 auf RAM achten (8-GB-Modell empfohlen); jedes Projekt bekommt eigenen Ordner +
  `compose` + Container. Der `web`-Container hat einen eigenen Deckel (512 MB, 1 CPU), damit
  ein PDF-Parse den MCP nicht aushungert.

### Rollback nach einer Tunnel-Änderung
Tunnel-Route im Dashboard zurück auf `http://foliant:8000`, Save. Greift in Sekunden, keine
Datenänderung, kein Container-Neustart. Danach optional `docker compose stop web gateway`.
Warum etwas blockiert wurde: Cloudflare → **Security → Events** (Caddy loggt bewusst nichts).

### Bekannte Grenzen
- **Cloudflares Proxy-Read-Timeout: 120 s** (nur Enterprise änderbar). Die
  Bogen-Konvertierung antwortet erst am Ende → `ZEITLIMIT_S` in `web.py` sorgt dafür, dass
  der Nutzer die *deutsche* Fehlermeldung sieht statt Cloudflares Error 524.
- `asyncio.Semaphore(1)` begrenzt Nebenläufigkeit, **nicht die Rate**. Der harte Kostendeckel
  ist ein API-Key in einem Workspace mit Spend-Limit.

---

## 6. Admin (bewusst kein öffentliches Web-Panel)

Ein Admin-UI wäre auf dem getunnelten Pi unnötige Angriffsfläche. Stattdessen zwei **lokale** Wege:

**1. Admin-CLI:**
```
docker compose exec foliant python -m app.admin status     # Bestand je Quelle/Edition/Kategorie
docker compose exec foliant python -m app.admin manifest   # Korpus-Fingerabdruck
docker compose exec foliant python -m app.admin check      # Integritaet + Textqualitaet
```
Vollständige Befehlsliste: `RUNBOOK.md`.

**2. Datasette (grafischer read-only Blick) — nur localhost:**
```
docker compose --profile admin up -d datasette
ssh -L 8001:localhost:8001 <nutzer>@<pi-ip>    # dann http://localhost:8001 im Browser
```
Ideal für die Import-Kontrolle (O3): sehen, was geparst wurde, und schlechte Einträge finden.

---

## 7. Umzug auf Mac mini (später)

Gleiches Repo, gleiches `compose`. Auf macOS Docker via **Docker Desktop** oder **colima**
installieren, dann identisch `docker compose up -d --build`. Der Tunnel-Token in `.env`
bleibt gleich, die öffentliche URL ändert sich nicht — der Connector in Claude läuft ohne
Änderung weiter.
