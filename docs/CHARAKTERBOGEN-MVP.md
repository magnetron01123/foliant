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
  statt LLM+`*`); eingebettete Fachbegriffe in Beschreibungen in §5-Klammerform; Feinjustage
  einzelner `layout_map`-Rects (lange Reichweite-Strings in der Zauber-Spalte).

## Deployment (Phase 6) — Runbook

Architektur: **Caddy-Gateway** vor `foliant` (MCP) + `web` (Website). Der Cloudflare-Tunnel
zeigt nach dem Umschalten auf `gateway:8080`; Caddy routet `/mcp` → `foliant`, sonst → `web`.
Der bestehende Connector-Pfad, IP-Filter, Streaming und die 16 Tools bleiben **unverändert**.

### 0. Vorher (nur der Eigentümer)
1. **PR #3 mergen** (GitHub — Agent-Self-Merge ist geblockt).
2. Auf dem Pi in `~/foliant/.env` ergänzen: `ANTHROPIC_API_KEY=sk-ant-…` und
   `ANTHROPIC_MODEL=claude-sonnet-5`.

### 1. Code + glossar-nur-DB auf den Pi
```sh
# vom Mac: NUR geänderte Dateien, KEIN --delete (sonst verschwinden gitignorierte Privatmodule!)
rsync -av --exclude '.git' --exclude '.venv*' --exclude 'data' --exclude 'quellen' \
  --exclude '.env' --exclude 'config/foliant.toml' --exclude '.claude' \
  ./ pi@<pi-host>:~/foliant/

# auf dem Pi: glossar-nur-DB erzeugen (kein privater Buchinhalt landet im Web-Container)
ssh pi@<pi-host>
cd ~/foliant
docker compose exec foliant python -m app.charakterbogen.glossar_export \
  /app/data/foliant.sqlite /app/data/glossar_web.sqlite   # MUSS vor 'up web' existieren
```

### 2. web + gateway bauen und starten (foliant/cloudflared laufen unberührt weiter)
```sh
docker compose up -d --build web gateway
docker compose ps                    # web + gateway "up"; foliant weiter healthy
```

### 3. Lokale Abnahme über den Gateway (Tunnel zeigt noch auf foliant!)
```sh
curl -s http://127.0.0.1:8080/health                         # Foliant-JSON (MCP-Seite lebt)
curl -s http://127.0.0.1:8080/ | grep "Deutschen Charakterbogen erstellen"   # Website lebt
curl -f -F "datei=@/pfad/zum/DDB-Export.pdf" http://127.0.0.1:8080/bogen -o /tmp/test.pdf
```
Zusätzlich den bestehenden Claude-Connector durch den Gateway testen (initialize + `tools/list`
= 16 Tools, `foliant_uebersetze_begriff`), bevor umgeschaltet wird.

### 4. Cloudflare-Dashboard (nur der Eigentümer — zwei Entscheidungen)
- **WAF eingrenzen:** die bestehende Regel `(http.host eq "dnd.magnetron.me" and not ip.src in
  {160.79.104.0/21 2607:6bc0::/48})` um eine Pfad-Bedingung ergänzen, damit die Anthropic-IP-Sperre
  **nur die MCP-Pfade** trifft, nicht die Website:
  `(http.host eq "dnd.magnetron.me" and http.request.uri.path contains "/mcp" and not ip.src in {…})`.
  Die `http.host`-Bedingung **behalten** (sonst trifft es den Smarthome-Tunnel).
- **Website-Zugriff (Kosten-/Missbrauchsschutz!):** die Website ist authlos und jede Konvertierung
  kostet API-Geld. Für den privaten MVP die Nicht-MCP-Pfade auf die eigene Heim-IP beschränken
  (zweite WAF-Regel) **oder** Cloudflare Access (PIN). Nicht offen ins Netz stellen.
- **Tunnel-Origin umschalten:** Public-Hostname `dnd.magnetron.me` von `http://foliant:8000` auf
  `http://gateway:8080` ändern.

### 5. Sofort testen — und Rollback
- Claude-Connector: initialize + 16 Tools. Website: `https://dnd.magnetron.me/` → PDF hochladen.
- **Bei Fehler:** Tunnel-Origin zurück auf `http://foliant:8000` (sofort rückrollbar, keine
  Datenänderung). `docker compose stop web gateway` entfernt die neuen Container wieder.

> Der Code ändert das Cloudflare-Dashboard nicht — Schritt 4 ist manuell. Erst nach grüner
> lokaler Abnahme (Schritt 3) umschalten.
