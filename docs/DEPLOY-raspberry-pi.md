# Deployment: Foliant auf Raspberry Pi 4 (headless, via SSH)

Ziel: Foliant als Container-Dienst auf einem frisch aufgesetzten Pi 4 — dauerhaft laufend,
öffentlich erreichbar über einen Cloudflare Named Tunnel. Später 1:1 auf einen Mac mini
(Apple Silicon, ebenfalls ARM64) umziehbar.

## Warum Container?
- **Isolation:** weitere KI-Projekte auf demselben Gerät stören Foliants Abhängigkeiten nicht.
- **Portabilität:** Pi 4 und Apple-Silicon-Mac mini sind beide ARM64 → gleiches `Dockerfile`/`compose`.
- **Reproduzierbar:** Neuaufsetzen/Umzug = `docker compose up -d --build`, kein manuelles Gefrickel.

*Alternative ohne Docker:* Python-venv + `systemd`-Service — einfacher für **ein** Projekt, aber
keine saubere Mehrprojekt-Isolation und nicht auf den Mac portierbar (`systemd` ist Linux-only).
Deshalb hier Docker.

## 0. Pi vorbereiten
- **64-bit Raspberry Pi OS Lite** flashen (64-bit ist Pflicht für ARM64-Images; Lite = headless).
  Im Raspberry Pi Imager beim Flashen SSH aktivieren + Nutzer/WLAN setzen.
- Per SSH einloggen: `ssh <nutzer>@<pi-ip>`
- Aktualisieren: `sudo apt update && sudo apt full-upgrade -y`

## 1. Docker installieren
```
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
sudo systemctl enable docker      # startet Docker beim Boot (wichtig fuer Auto-Restart)
```
Danach einmal aus- und wieder einloggen (Gruppen-Update greift). Test: `docker run --rm hello-world`.

## 2. Projekt + Daten aufs Pi bringen
- Repo kopieren (von deinem Rechner): `scp -r foliant <nutzer>@<pi-ip>:~/`  (oder `git clone`).
- **Alles auf dem Pi (dein Setup):** Der Import läuft im Container mit. Quell-PDFs nach `quellen/`
  legen, dann im Container:
  `docker compose exec foliant python db/init_db.py data/foliant.sqlite`, danach die Importer
  (bzw. `docker compose exec foliant python -m app.admin import --quelle …`).
  **PyMuPDF4LLM läuft auf ARM problemlos** (nur langsamer; der Import ist einmalig, z. B. über Nacht).
  Einziger Wermutstropfen: **Docling** (ML-Fallback für schwierige Statblöcke) ist auf ARM zäh und
  speicherhungrig — nur bei Bedarf in `requirements.txt` aktivieren; sonst reicht PyMuPDF4LLM.
  *(Optional, falls dir das Pi zu langsam wird: Import auf einem stärkeren Rechner und nur die fertige
  `data/foliant.sqlite` per `scp` rüberkopieren — beides funktioniert.)*
- `.env` anlegen: `cp .env.example .env` und ausfüllen (siehe Schritt 3).

## 3. Cloudflare Named Tunnel einrichten
- Zero-Trust-Dashboard → Networks → Tunnels → **Create tunnel** (Typ: Cloudflared).
- **Token kopieren** → auf dem Pi in `.env` als `CLOUDFLARE_TUNNEL_TOKEN=` eintragen.
- Im Tunnel eine **Public Hostname**-Route anlegen: `dnd.magnetron.me` → Service
  `http://foliant:8000` (der Container-Name im selben Compose-Netz).
  *Voraussetzung:* `magnetron.me` läuft über Cloudflare-DNS.

## 4. Starten
```
cd foliant
docker compose up -d --build
docker compose ps                     # foliant + cloudflared "up/healthy"?
curl http://localhost:8000/health     # {"status":"ok","name":"Foliant"}
```
Läuft jetzt dauerhaft (`restart: unless-stopped`) und startet nach Reboot automatisch.

## 5. In Claude verbinden
Custom Connector mit der **vollen URL inkl. Geheimpfad** hinzufügen (siehe „Zugang absichern"):
`https://dnd.magnetron.me/<FOLIANT_PFAD_TOKEN>/mcp` — **kein OAuth**.
(Einrichten nur am Desktop; benutzen geht danach auch aus der Claude-Mobile-App.)

## 5b. Zugang absichern (M3: Geheimpfad + IP-Allowlist)
Seit dem DDB-Import serviert der Tunnel **private Buchinhalte** → der Endpoint ist nicht mehr
offen (NF3/NF4). Zwei Schichten, beide ohne Nutzer-Management (Details: `app/zugriff.py`):

1. **Geheimpfad** — die URL ist der Schlüssel. Einrichten:
   ```
   python3 -c "import secrets; print(secrets.token_urlsafe(18))"   # Token erzeugen
   # auf dem Pi in ~/foliant/.env:  FOLIANT_PFAD_TOKEN=<wert>
   docker compose up -d --build foliant
   ```
   Connector-URL = `https://dnd.magnetron.me/<wert>/mcp`. Der alte `/mcp` liefert 404.
   **Rotation bei Leak:** neuen Token setzen → rebuild → neue URL an die Runde schicken.
   (Geheimer **Pfad**, nicht geheime Subdomain — Subdomains leaken über
   Zertifikats-Transparenz-Logs.)
2. **IP-Allowlist** — nur Anthropics veröffentlichte Egress-Ranges (`160.79.104.0/21`,
   `2607:6bc0::/48` — Quelle: platform.claude.com/docs/en/api/ip-addresses) erreichen den
   MCP-Pfad; geprüft wird die von der Cloudflare-Edge gesetzte `CF-Connecting-IP`. Eine
   geleakte URL ist damit **nur über Claude** nutzbar, nie per curl/Scanner/Browser.
   Lokale Aufrufe ohne Edge-Header (Container-curl, compose-Healthcheck, LAN) bleiben
   möglich; `/health` bleibt immer offen (nur Status, keine Inhalte — trägt Monitoring).
   Schalter in `.env`: `FOLIANT_IP_FILTER=aus` (Debug), `FOLIANT_ERLAUBTE_IPS=<cidr,cidr>`
   (z. B. Heim-IP für Direkt-Tests). Blockierte Zugriffe stehen in `docker compose logs foliant`.

**Verhaltensregeln für die Runde (gehören in die Spieler-Anleitung):** URL nicht
weitergeben, Inhalte nicht weiterverbreiten (privat erworbene Bücher).

**Optionales Upgrade (blockt schon an der Cloudflare-Kante statt erst am Pi):** im
Cloudflare-Dashboard → Security → WAF → Custom Rules, Aktion **Block**:
```
(http.host eq "dnd.magnetron.me" and not ip.src in {160.79.104.0/21 2607:6bc0::/48})
```
Wichtig: `http.host`-Bedingung beibehalten, sonst trifft die Regel andere Hostnames der
Zone (Smarthome-Tunnel!). Funktional ändert das nichts — Scanner erreichen dann nur nicht
mal mehr den Pi.

## Betriebsmodell: Pi betreibt, Mac entwickelt/administriert
**Alles, was den laufenden MCP betrifft, lebt auf dem Pi** — Server UND Importe (SRD-PDF,
Open5e, Glossar, DDB). Der Mac mini ist nur für **Entwicklung** (Code schreiben) und
**Administration** (Code aufs Pi schieben, Importe per SSH auslösen). So gibt es genau
einen operativen Bestand, und der Pi überlebt einen Mac-Ausfall.

- **Code aufs Pi** (vom Mac): `rsync -a --exclude '.git' --exclude 'data' --exclude 'quellen'
  --exclude 'config/foliant.toml' --exclude '.env' ./ pi@<pi-ip>:~/foliant/`
  danach bei Code-/Dependency-Änderung `docker compose up -d --build foliant`.
- **Importe laufen im Container auf dem Pi**, z. B.:
  - `docker compose exec foliant python -m app.admin import --quelle srd-de`
  - `docker compose exec foliant python -m app.admin import --quelle open5e-srd-2024`
  - `docker compose exec foliant python -m app.admin import --quelle glossar`
  - `docker compose exec foliant python -m app.admin check`
  Quell-PDFs dazu nach `~/foliant/quellen/` legen (PyMuPDF4LLM läuft auf arm, nur langsamer).
- **DDB-Bücher auf dem Pi** (getrennter Kurzlebig-Container, Details unten „DDB").

*(Der frühere Weg „DB am Mac bauen und rüberkopieren" bleibt als Notnagel möglich, ist
aber nicht mehr das Betriebsmodell.)*

## DDB-Buchimport auf dem Pi
Vollständig auf dem Pi, in zwei Schritten (Export mit Secret, Import offline). Der
Exporter läuft als **kurzlebiger, gehärteter Container** (`--profile ddb`, `read_only`,
`cap_drop: ALL`, ohne DB-Mount).

1. **Einmalig:** Exporter-Image bauen: `docker compose --profile ddb build ddb-exporter`
   (installiert `apsw-sqlite3mc` für arm64 — auf dem Pi verifiziert).
2. **Cobalt bereitstellen** (nur für den Export, danach löschen): den `CobaltSession`-Wert
   aus einer angemeldeten dndbeyond.com-Sitzung in eine Datei im Pi-Home legen, z. B.
   `~/.ddb-cobalt` (der Wert ist wie ein Passwort). Wegen `cap_drop: ALL` muss die Datei
   für den Container lesbar sein — kurzzeitig `chmod 644`, nach dem Lauf **löschen**.
3. **Export** (alle eigenen Regelbücher, auto-erkannt):
   ```
   docker compose --profile ddb run --rm \
     -v /home/pi/.ddb-cobalt:/run/secrets/ddb_cobalt:ro ddb-exporter sync
   rm -f ~/.ddb-cobalt        # Secret sofort entfernen
   ```
4. **Import** in die bediente DB (offline; seit SYN-P1-005 sieht der laufende
   Serve-Container `data/private` NICHT mehr — der Import läuft als Einmal-Container
   mit explizitem Privat-Mount):
   ```
   docker compose run --rm -v ./data/private:/app/data/private \
     foliant python -m app.admin ddb-import-all
   docker compose restart foliant
   ```
   Voraussetzung: `config/foliant.toml` enthält `[ddb] ins_hauptbestand = true` — dann
   mergt der Import die DDB-Bücher in `data/foliant.sqlite` (weiter atomar, mit Backup +
   Integritätsprüfung). Ohne diese Zeile landen sie in einer separaten privaten DB.

> **Bereitstellung privater Inhalte:** Der Tunnel ist authless — mit `ins_hauptbestand`
> werden gekaufte Bücher öffentlich abfragbar. Wer das absichern will, legt auf
> **Cloudflare-Ebene** eine Access-Regel/IP-Allowlist über `dnd.magnetron.me` (kein
> selbstgebauter OAuth-Provider). Bewusste Eigentümer-Entscheidung.

## Gescannte PDFs importieren (OCR-Vorstufe)
Viele Buch-PDFs sind Scans ohne Textschicht — der Import würde daraus nichts gewinnen
(und bricht dank Guardrail bewusst ab, statt eine Rumpf-Quelle zu schreiben). Ablauf:

```
# 1. Scan aufs Pi legen (vom Mac):  scp Buch.pdf pi@<pi-host>:~/foliant/quellen/
# 2. Befund: welche PDFs brauchen OCR?
docker compose exec foliant python -m app.admin pdf-triage
# 3. OCR (einmalig, ~15-45 min/Buch auf dem Pi; deu+eng; Ausgabe nach data/ocr/):
docker compose exec foliant python -m app.admin ocr-pdf --datei quellen/Buch.pdf
#    Hat der Scan schon eine (schlechte) Alt-OCR-Textschicht: zusätzlich --redo
# 4. Quelle registrieren (config/foliant.toml, edition PFLICHT - nie raten):
#    [[quelle]]  kuerzel/titel/sprache/edition/prioritaet + dateipfad = "data/ocr/Buch.ocr.pdf"
# 5. Import + Stichprobe (O3):
docker compose exec foliant python -m app.admin import --quelle <kuerzel>
docker compose exec foliant python -m app.admin check
```

Erwartung ehrlich: OCR-Text ist fehleranfälliger als born-digital (v. a. Statblöcke/
Tabellen/Zahlen) → Stichprobe vor Freigabe; Scans unter ~300 dpi werden deutlich
schlechter (bei eigenen Scans: 300 dpi, Graustufen). Das Original in `quellen/` bleibt
unangetastet; `data/ocr/` hält die OCR-Fassung (vom Backup mit abgedeckt).

**Sonderfall Browser-Druck-PDFs (z. B. DDB-Ausdrucke):** Je nach Schaden der Textschicht
(Kerning-Risse, Mojibake-Fonts, fi/fl-Ligaturverlust) läuft der Import über die reparierte
Original-Schicht (efota) oder die Voll-OCR-Fassung (`ocr-pdf --voll`, frhof) — je mit
kuratierter `BEREINIGUNG` + `SPLIT_REGELN` pro Buch (`importer/import_markdown.py`).
Die **Konvertierung nach Markdown passiert am Mac** (Admin-Aufgabe), das Markdown ist das
Import-Artefakt (`quellen/md/<kuerzel>.md` auf dem Pi, `dateipfad` zeigt darauf) — die
pymupdf4llm-Heading-Erkennung ist für diese PDFs umgebungsempfindlich. Zwei Leitplanken
dazu sind fest verdrahtet: `use_ocr=False` (pymupdf4llm OCRt sonst STILL, sobald Tesseract
im Image ist) und der Scan-Guardrail. Neues Buch dieser Art → mit Claude Code die
Bereinigungs-/Split-Regeln am echten Markdown justieren (Pilot-Muster: efota/frhof).

## Betrieb
- **Readiness statt Health (SYN-P1-011):** `curl http://localhost:8000/ready` prüft
  DB + FTS (503 bei kaputtem/leerem Bestand); `/health` bleibt der reine Prozess-Ping
  für externes Uptime-Monitoring (z. B. UptimeRobot auf `https://<host>/health`).
- **Off-Site-Backup (O1, nächtlich per Cron auf dem Pi):**
  ```
  sqlite3 data/foliant.sqlite ".backup data/backup-foliant.sqlite" && \
    rsync -a data/backup-foliant.sqlite <nutzer>@<mac>:~/foliant-backups/$(date +%F).sqlite
  ```
  Restore-Probe: Kopie zurückspielen → `admin check` + `make test-daten` müssen bestehen.
- Logs: `docker compose logs -f foliant`  ·  Neustart: `docker compose restart foliant`
- **Admin/DB-Inspektion:** siehe Abschnitt „Admin“ unten.
- **Neue Inhalte einspielen:** aktualisierte `foliant.sqlite` nach `data/` kopieren →
  `docker compose restart foliant`. (Kein Rebuild nötig, nur bei Code-/Dependency-Änderung.)
- DB-Journal steht bewusst auf **DELETE** (Bind-Mount-kompatibel) — nicht auf WAL umstellen.
- **Ressourcen:** Foliant selbst ist leichtgewichtig (< ~200 MB). Bei mehreren KI-Projekten auf
  einem Pi 4 auf RAM achten (8-GB-Modell empfohlen); jedes Projekt bekommt seinen eigenen
  Ordner + `compose` + Container.

## Admin (bewusst kein öffentliches Web-Panel)
Foliant hat **keine** öffentliche Admin-UI — das wäre auf dem getunnelten Pi unnötige Angriffsfläche.
Stattdessen zwei **lokale** Wege:

**1. Admin-CLI (Aktionen + Status), im Terminal:**
```
docker compose exec foliant python -m app.admin status        # Bestand je Quelle/Edition/Kategorie + Glossar
docker compose exec foliant python -m app.admin import --quelle srd-de
docker compose exec foliant python -m app.admin reindex-fts
docker compose exec foliant python -m app.admin check
```
`status` läuft sofort; `import`/`reindex-fts`/`check` verdrahtet Claude Code in Phase 1 mit den Importern.

**2. Datasette (grafischer read-only Blick) — nur localhost:**
```
docker compose --profile admin up -d datasette
```
Läuft an `127.0.0.1:8001` auf dem Pi — **nicht** über den Tunnel erreichbar. Zugriff von deinem
Rechner per SSH-Tunnel:
```
ssh -L 8001:localhost:8001 <nutzer>@<pi-ip>
# dann im Browser: http://localhost:8001
```
Ideal für die Import-Kontrolle (O3): sehen, was geparst wurde, und schlechte Einträge finden.

## Umzug auf Mac mini (später)
Gleiches Repo, gleiches `compose`. Auf macOS Docker via **Docker Desktop** oder **colima**
installieren, dann identisch `docker compose up -d --build`. Der Tunnel-Token in `.env` bleibt
gleich, die öffentliche URL ändert sich nicht — der Connector in Claude läuft ohne Änderung weiter.
