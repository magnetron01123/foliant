# Charakterbogen-Übersetzer (DDB EN → deutscher WotC-Bogen)

Feature neben dem Foliant-MCP: Ein englischer D&D-Beyond-PDF-Export wird ausgelesen, ins
Deutsche übersetzt und auf den **offiziellen deutschen WotC-Charakterbogen (2024)** übertragen —
als druckbares PDF. Verbindliche Spec: `KONZEPT_charakterbogen-uebersetzer.md` (führt bei
Konflikten vor dem älteren `docs/CLAUDE-CODE-AUFTRAG-CHARAKTERBOGEN-MVP.md`). Eigentümer-Entscheid
14.07.2026: **KONZEPT führt, Fortsetzungsseiten sind erlaubt.**

## Pipeline (3 Stufen, LLM klar isoliert)

```
DDB-PDF (EN) ──[1 Extractor]──► neutrales Modell (EN) ──[2 Übersetzer]──► Modell (DE) ──[3 Renderer]──► DE-Bogen-PDF
             deterministisch                          Claude + Foliant                 deterministisch
```

Parsen und Rendern sind reiner, testbarer Code; nur die Übersetzung ist LLM-basiert. Zahlen,
Würfel und Modifikatoren laufen NIE durch das Sprachmodell.

## Module (`app/charakterbogen/`)

| Datei | Rolle |
|---|---|
| `modelle.py` | Neutrales Charaktermodell. Übersetzbares als `UeText{en,de,art}`, Zahlen roh. `roh_felder` = verlustfreies Protokoll aller befüllten Widgets. |
| `ddb_pdf.py` | **Extractor**: liest verwaiste `/Widget`-Annotationen (kein AcroForm) via PyMuPDF, Smart-Join der `FeaturesTraits`/`Actions`-Fragmente, Fingerprint-Prüfung der Exportfamilie. |
| `feldkarten/ddb_pdfsharp_6_1.json` | `source_map`: DDB-Feld → Modellpfad + Fingerprint (§7.1/§7.2). |
| `feldkarten/de_wotc_2025.json` | `layout_map`: Modellpfad → Position auf dem DE-Bogen (aus Ankern + Vektor-Boxen abgeleitet; an DE-Version 670D…01 DE gebunden). |
| `feldkarten/code_map.json` | Feste Kürzel (`1A`→`1 Aktion`, `STÄ/GES…`, Münzen). |
| `terminologie.py` | Löst feste Begriffe **in-process über `app.glossar`** auf (kein zweites Glossar) → §5-Form `Deutsch (English)` / `Deutsch* (English)`. |
| `uebersetzer.py` | Provider-Vertrag + Anthropic-Adapter (httpx) + Fake. Feldweise Übersetzung, EIN gebündelter Aufruf, Übersetzungsgedächtnis, JSON-Vertrag mit 1× Retry. |
| `de_bogen.py` | **Renderer** (fitz-Overlay): zeichnet Werte auf eine Kopie der DE-Vorlage, Auto-Fit, Fortsetzungsseiten bei Überlauf, Kalibrier-Modus. |
| `web.py` | Schmale Starlette-App: `GET /` (Upload), `POST /bogen` (Konvertierung), `GET /health`. Sicherheitsgrenzen, Ein-Konvertierung-Semaphore, keine Persistenz, `no-store`/CSP. |
| `templates/`, `static/` | Einspaltige Upload-Karte im Bogen-Stil (keine externen Fonts/CDNs). |

## Regel §5 (die einzige Übersetzungsregel)

Ausgabe immer `Deutscher Begriff (English Original)`. `*` am deutschen Wort, wenn das Foliant-Glossar
keinen **exakten, belegten** Treffer hat (dann bildet das Sprachmodell die deutsche Wiedergabe).
Nie nur Englisch. Fuzzy-Treffer zählen nie (Identität nur bei `match == "exakt"`).

## Lokal ausführen

```sh
# Tests (committbar, nur synthetische Fixtures):
.venv/bin/python -m pytest -q tests/test_charakterbogen_*.py

# Web-App lokal (GET / funktioniert ohne API-Key; POST /bogen braucht den Provider):
.venv/bin/python -m uvicorn app.charakterbogen.web:app --host 127.0.0.1 --port 8099
```

Die echten Vorlagen liegen gitignored unter `vorlagen/charakterboegen/` (offizieller DE-Bogen +
private DDB-Beispiele). Die privaten Golden-Tests (`tests/test_charakterbogen_*_golden_privat.py`)
laufen gegen sie und sind ebenfalls gitignored.

## Konfiguration (`.env`)

| Variable | Zweck |
|---|---|
| `ANTHROPIC_API_KEY` | Übersetzungsprovider. Fehlt er → `POST /bogen` meldet „Übersetzung momentan nicht verfügbar“; der Rest läuft. |
| `ANTHROPIC_MODEL` | Modell-ID (nicht hart kodiert). |

Ohne Key sind Extraktion, Terminologie, Rendering und die Web-Fehlerpfade vollständig mit Fakes
getestet; nur der echte Freitext-Übersetzungslauf ist offen.

## Status (14.07.2026)

- **Phase 1–3 + 5 fertig und getestet** (62 committbare Tests grün, `make test` grün). Golden-Render
  „Sorin Vale“ visuell abgenommen: sieht aus wie ein sauber ausgefüllter Originalbogen; feste
  Begriffe aus dem echten Glossar (Mönch (Monk), Dunkelheit (Darkness) …).
- **Offen – braucht Eigentümer-Input:**
  - **Echter Übersetzungslauf:** `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL` setzen.
  - **Phase 6 Deploy (Pi):** Web-Container neben dem MCP; Reverse-Proxy-/Gateway-Route für
    `dnd.magnetron.me` (der bestehende MCP-Pfad `/<token>/mcp` + IP-Filter + 16 Tools bleiben
    unverändert); Zugriffsschutz (privater MVP). **Keine Cloudflare-/Pi-Umschaltung ohne
    ausdrückliche Freigabe.** Der aktuelle Stack nutzt cloudflared direkt (kein Caddy) — ob ein
    Gateway ergänzt oder über Cloudflare-Ingress geroutet wird, entscheidet der Eigentümer.
- **Kleinere Refinements:** Feature-/Zaubernamen zusätzlich über `foliant_hol_*` (offizielle Namen
  statt LLM+`*`).

## Review-Runde 2 (16.07.2026) — umgesetzt

Aus dem E2E-Befundbericht (`docs/CHARAKTERBOGEN-BEFUNDBERICHT-2026-07-16.md`):

- **Merkmalsköpfe + Sub-Features fett** (Misch-Font helv/hebo, D&D-Beyond-Optik); Fett-Marker
  `\x01…\x02` entstehen beim Textbau und erreichen nie das LLM oder die PDF-Ausgabe.
- **Eine Schriftgröße je Kasten** (2-Spalten-Boxen fitten gemeinsam) und **Fortsetzungsseiten
  erben die Größe** der Ursprungsbox (kein Schriftgrad-Sprung mehr).
- **Fortsetzungskopf immer**: Bricht ein Merkmal an Zeilen- ODER Satzgrenze über die Box,
  nennt die Fortsetzung das Merkmal („… (Fortsetzung):", fett); Vorlagen-Kopien tragen
  Name/Klasse/Stufe im Kopf. Spaltenfluss innerhalb einer Box bekommt keinen Kopf.
- **Einzeiler-Überlauf-Stufen**: Auto-Fit → §5-Klammer opfern → horizontal stauchen; nie
  über die Boxgrenze (Unterklasse vs. Stufe-Oval, Zauber-Reichweiten).
- **Deterministische Notation**: zentrale d→W-Wandlung in `_saeubere` (5d8→5W8); Zauber-
  Notizen V/S→V/G, S/M→G/M, `D:`→`WD:`; deutsche Anführungszeichen font-sicher; Streu-`·`
  entfernt.
- **`Crossbow, Hand` → `Hand Crossbow`** im Extractor normalisiert (invertierte SRD-Namen);
  Übersetzer-Guard: Listen behalten die Item-Anzahl, sonst Retry und danach ehrlich englisch.
- **Glossar-Vorgaben für Freitexte**: `glossar.begriffe_im_text()` erzwingt amtliche Begriffe
  im Fließtext (Gepackt statt „ergriffen"); 2024-Aktionsnamen (`seed_aktionen`, srd-de-
  verifiziert, Homonym-gestoppt) + „Heldische Inspiration" als Kernpaar.
- **Dunkelsicht** als zweite Zeile im Bewegungsrate-Feld; **Traglast** (kg) am Ende der
  Ausrüstungs-Box.

**Bewusste Auslassungen** (DDB-Export-Inhalte ohne Feld auf dem DE-WotC-Bogen, extrahiert
aber nicht gerendert — Entscheidung 16.07.2026): passive Einsicht/Untersuchung (aus den
Fertigkeiten ableitbar), Zauber-Herkunft/Seitenreferenzen, der statische ACTIONS/BONUS-
ACTIONS-Block (Regel-Boilerplate; Bonusaktions-Infos stehen in den Merkmalen), Spielername.

## Deployment (Phase 6) — Runbook

Architektur: **Caddy-Gateway** vor `foliant` (MCP) + `web` (Website). Der Cloudflare-Tunnel zeigt
nach dem Umschalten auf `gateway:8080`; Caddy routet `/mcp` → `foliant`, `/health`+`/ready` →
`foliant`, alles andere → `web` (hinter Basic-Auth). Connector-Pfad, IP-Filter, Streaming und die
16 Tools bleiben **unverändert** — am vollen Pi-Bestand verifiziert (14.07.2026).

### Stand: Container-Deploy ERLEDIGT (14.07.2026)
`web` + `gateway` laufen auf dem Pi, lokal abgenommen. Der Tunnel zeigt **weiterhin auf
`foliant:8000`** → die Website ist nur über `127.0.0.1:8080` erreichbar, der öffentliche MCP ist
unverändert. Offen sind nur noch die Eigentümer-Schritte (`.env` + zwei Cloudflare-Klicks).

### Stolperfallen (teuer gelernt)
- **`docker compose up --build web gateway` baut über `depends_on` AUCH `foliant` neu** und
  startet den Live-MCP neu. Immer **`--no-deps`** benutzen:
  `docker compose up -d --no-deps --build web gateway`.
- **rsync ohne `--delete`** und ohne `data/` — die Mac-DB ist nur ein Subset und würde den vollen
  Pi-Bestand überschreiben; gitignorierte Privatmodule würden verschwinden.
- Die **glossar-nur-DB muss existieren, BEVOR `web` startet** (sonst legt Docker ein Verzeichnis
  statt der Datei an).

### 1. Code + glossar-nur-DB auf den Pi
```sh
# vom Mac: NUR die betroffenen Pfade, KEIN --delete, KEIN data/
rsync -rltvR app/charakterbogen deploy/Caddyfile docker-compose.yml requirements.txt \
  vorlagen/charakterboegen/offiziell/Charakterbogen_2024_DE.pdf pi@<pi-host>:~/foliant/

# auf dem Pi: glossar-nur-DB erzeugen (kein privater Buchinhalt landet im Web-Container).
# Läuft mit dem Host-python3 — nur stdlib sqlite3, kein Container-Rebuild nötig.
ssh pi@<pi-host>
cd ~/foliant
python3 -m app.charakterbogen.glossar_export data/foliant.sqlite data/glossar_web.sqlite
```

### 2. Website-Kennwort setzen (EIN Kennwort, kein Benutzername)
Die Website ist authlos gebaut und **jede Konvertierung kostet Anthropic-API-Geld** — der Hostname
steht über Certificate-Transparency-Logs öffentlich, Scanner finden ihn in Tagen. Der Zugang ist
deshalb eine eigene **Kennwort-Seite in der App** (`web.py`), nicht HTTP-Basic-Auth: Basic-Auth
erzwingt im Browser immer ein Benutzerfeld — Eigentümer-Wunsch war *ein* Kennwort, sonst nichts.

```
# in der Pi-.env - frei wählbar, kein Hash-Kommando nötig:
WEB_PASSWORT=<kennwort-der-runde>
```
```sh
docker compose up -d --no-deps web
```
- **Fail-closed:** Fehlt `WEB_PASSWORT`, ist die Seite zu (503/401) — nie versehentlich offen.
- Signierter, `HttpOnly`-Keks (30 Tage, HMAC **mit dem Kennwort als Schlüssel** → Kennwort ändern
  entwertet alle alten Kekse sofort). `Secure` nur, wenn `X-Forwarded-Proto: https` ankommt, damit
  die lokale Abnahme über `http://127.0.0.1:8080` weiter funktioniert.
- **`POST /bogen` ist selbst gesperrt**, nicht nur die Seite versteckt — die teure Route ist zu.
- Bremse gegen Durchprobieren: 8 Fehlversuche je Absender-IP (`CF-Connecting-IP`) → 5 min Sperre,
  plus 1 s Verzögerung pro Fehlversuch.
- Der Gateway proxyt nur noch (keine Basic-Auth mehr im `Caddyfile`).

### 3. `.env`: Übersetzungsprovider
```
ANTHROPIC_API_KEY=sk-ant-…      # eigener Workspace mit Spend-Limit (harter Kostendeckel!)
ANTHROPIC_MODEL=claude-sonnet-5
```
Danach `docker compose up -d --no-deps web`. Ohne Key läuft alles außer `POST /bogen` (→ 503,
„Übersetzung momentan nicht verfügbar").

### 4. Lokale Abnahme (Tunnel zeigt noch auf foliant — alles hier ist gefahrlos)
```sh
curl -s http://127.0.0.1:8080/ready                                  # {"status":"bereit","eintraege":9485}
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/       # 401 ohne Passwort
curl -s -u runde:PW http://127.0.0.1:8080/ | grep Charakterbogen     # Website lebt
curl -s -o /dev/null -w '%{http_code}\n' -H 'CF-Connecting-IP: 8.8.8.8' \
     http://127.0.0.1:8080/<TOKEN>/mcp                               # 403  <- WICHTIGSTER TEST
```
**Der 403-Test ist Pflicht nach JEDER Caddyfile-Änderung.** Ginge `CF-Connecting-IP` hinter Caddy
verloren, wäre die IP-Allowlist des MCP *lautlos* aus (der Peer wäre dann Caddy = private IP =
durchgelassen). Zusätzlich der volle Handshake (initialize → `tools/list` = **16 Tools**) mit
`CF-Connecting-IP: 160.79.104.1`.

### 5. Cloudflare-Dashboard (nur der Eigentümer — zwei Klicks)
**a) WAF-Regel prüfen/eingrenzen** — `dash.cloudflare.com` → Zone `magnetron.me` → **Security
rules** (ältere Dashboards: **Security → WAF → Custom rules**). Existiert die in
`docs/DEPLOY-raspberry-pi.md` als *optional* dokumentierte Block-Regel überhaupt? Falls ja, blockt
sie nach dem Umschalten auch den eigenen Browser (keine Anthropic-IP) → Expression **komplett
ersetzen** (über **Edit expression**, nicht den grafischen Builder):
```
(http.host eq "dnd.magnetron.me" and http.request.uri.path contains "/mcp" and not ip.src in {160.79.104.0/21 2607:6bc0::/48})
```
`http.host` **niemals** weglassen (sonst trifft die Regel den Smarthome-Tunnel). `uri.path` statt
`uri` (sonst umgeht `?x=/mcp` die Regel). `contains "/mcp"` hält den Geheim-Token aus der
Cloudflare-Konfiguration heraus. `/health` bleibt offen. Regel **nie löschen und neu anlegen** —
im Löschfenster fehlt die Edge-Schicht. Existiert die Regel nicht: nichts tun (der MCP hängt an
Geheimpfad + App-IP-Allowlist, die hinter dem Gateway nachweislich weiterläuft).

**b) Tunnel-Origin umschalten** — `dash.cloudflare.com` → **Networking → Tunnels** (oder
`one.dash.cloudflare.com` → **Networks → Tunnels**; ältere UI: Reiter „Public Hostnames", neuere
„Routes"/„Published application routes") → Tunnel mit `dnd.magnetron.me` → Route bearbeiten →
Service-URL `http://foliant:8000` → **`http://gateway:8080`** → Save. Greift in Sekunden, kein
Container-Neustart, kein DNS-Eingriff. Unter *Additional application settings* **nichts** ändern —
insbesondere **„Disable Chunked Encoding" aus lassen** (zerstört SSE/MCP).

### 6. Sofort testen — und Rollback
- Claude-Connector im **frischen** Chat (alte Sessions kaschieren tote Verbindungen): 16 Tools.
- `https://dnd.magnetron.me/` → Passwort-Abfrage → PDF hochladen.
- **Rollback:** dieselbe Tunnel-Route zurück auf `http://foliant:8000`, Save. Sekunden, keine
  Datenänderung. Danach optional `docker compose stop web gateway`.
- Warum etwas blockiert wurde: **Security → Events** (Caddy loggt bewusst nichts — Token im Pfad).

### Bekannte Grenzen
- **Cloudflares Proxy-Read-Timeout: 120 s** (nur Enterprise änderbar). Die Konvertierung antwortet
  erst am Ende (kein Early-Header) → `ZEITLIMIT_S = 70.0` in `web.py` sorgt dafür, dass der Nutzer
  die *deutsche* Fehlermeldung sieht statt Cloudflares Error 524.
- `asyncio.Semaphore(1)` begrenzt Nebenläufigkeit, **nicht die Rate**. Der harte Kostendeckel ist
  ein API-Key in einem Workspace mit Spend-Limit (optional zusätzlich eine Cloudflare
  Rate-Limiting-Regel auf `POST /bogen`).
- Externes Uptime-Monitoring auf **`/health`** (immer offen). `/ready` unterliegt dem IP-Filter.
