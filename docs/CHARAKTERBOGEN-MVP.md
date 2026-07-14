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
