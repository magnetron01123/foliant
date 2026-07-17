# Charakterbogen-Übersetzer (DDB EN → deutscher WotC-Bogen)

Feature neben dem Foliant-MCP: Ein englischer D&D-Beyond-PDF-Export wird ausgelesen, ins
Deutsche übersetzt und auf den **offiziellen deutschen WotC-Charakterbogen (2024)** übertragen —
als druckbares PDF. Verbindliche Spec: `KONZEPT_charakterbogen-uebersetzer.md` (führt bei
Konflikten vor dem älteren `docs/CLAUDE-CODE-AUFTRAG-CHARAKTERBOGEN-MVP.md`). Eigentümer-Entscheid
14.07.2026: **KONZEPT führt, Fortsetzungsseiten sind erlaubt.**

## Übersetzung: zwei LLM-Stufen (16.07.2026)

1. **Belegte Begriffe** kommen deterministisch aus dem Glossar (kein LLM).
2. **Stufe 1 – unbelegte Begriffe/Eigennamen** („Warrior of Shadow"): eigener, kurzer Aufruf.
   Ergebnis → §5-Form mit `*` **und** als bindende Vorgabe für Stufe 2.
3. **Stufe 2 – Fließtexte/Listen**: mit allen Namen (Glossar + Stufe 1) als Vorgabe.

Ohne diese Trennung übersetzte ein einziger Aufruf Feld und Fließtext unabhängig — derselbe
Name hieß im Feld „Krieger des Schattens" und im Fließtext „Kämpfer des Schattens".
**Gemessen** (Sorin Vale, Sonnet): Stufe 1 = 37 Felder / 449 Zeichen / **6 s**;
Stufe 2 = 54 Felder / 6731 Zeichen / **37 s**; gesamt ~44 s (Läufe schwanken API-bedingt
zwischen ~42 s und ~80 s; `web.ZEITLIMIT_S` = 100 s).

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
  nennt die Fortsetzung das Merkmal („… (Fortsetzung):", fett); Vorlagen-Kopien tragen den
  Namen im Kopf (s. Review-Runde 3: Klasse/Stufe wieder entfernt). Spaltenfluss innerhalb
  einer Box bekommt keinen Kopf.
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

## Review-Runde 3 (17.07.2026) — umgesetzt

David-Befund: Der Kopf einer Fortsetzungsseite füllte fälschlich auch **Klasse** (das Feld
oben links neben dem Namen) - obwohl die Kopie nur ein einzelnes übergelaufenes Merkmal
fortsetzt und die restlichen Felder der kopierten Vorlagenseite bewusst leer bleiben.

- `_KOPIE_KOPF` trägt jetzt nur noch **`identitaet.name`** - Klasse/Stufe sind auf der Kopie
  nicht relevant und blieben trotzdem befüllt (`app/charakterbogen/de_bogen.py`).
- **Seitenzahlen** (`_seitenzahlen`, "Seite N von M" rechts unten) - NUR wenn Fortsetzungs-
  seiten eingefügt wurden, damit lose Blätter beim Ausdrucken sortierbar bleiben. Der
  unveränderte 2-Seiten-Bogen ohne Überlauf bleibt am Fuß frei.
- Tests: `test_fortsetzungs_kopie_befuellt_nur_den_namen`, `test_seitenzahlen_nur_bei_fortsetzung`
  (`tests/test_charakterbogen_pdf.py`).

## Kurzfassung ohne Merkmalstexte (17.07.2026) — ZURÜCKGENOMMEN

Zwischenzeitlich lieferte `POST /bogen` eine ZIP mit zwei Bögen (vollständig + Kurzfassung,
in der Klassenmerkmale/Spezies-Merkmale/Talente nur als Namensliste erschienen). Nach zwei
Nachbesserungsrunden (Gruppenkopf-Gliederung, Spezies-Wert-Sätze) Eigentümer-Entscheid
17.07.2026: **Feature komplett entfernt** — die reine Namensliste trägt zu wenig Information,
`POST /bogen` liefert wieder EINE vollständige PDF. Der im Zuge der Kurzfassung entstandene
Struktur- und Glossar-Feinschliff (nächste Abschnitte) bleibt.

## Merkmal-Struktur wie im DDB-Original (17.07.2026) — umgesetzt

David-Befund: „hier wird die ursprüngliche Struktur nicht mehr eingehalten … das ist die
Überschrift und darunter fallen Benefits". Der Vergleich mit dem englischen DDB-Original
(`vorlagen/charakterboegen/ddb-beispiele/`) belegte **drei** Strukturverluste — am
deutlichsten beim Nebelwanderer, weil dort nur Überschrift + EIN Benefit steht:

| | Original | vorher |
|---|---|---|
| Kopf | `* Mist Wanderer Ability Score Increase • RtHW 27` (eigene Zeile) | inline mit dem Body verklebt |
| Benefit | `   \| Increase two scores (+2 / +1)` (eigene Zeile) | `[Erhöhe zwei Werte (+2 / +1)]` ans Ende geklebt |
| Sub-Features | eigener Absatz je Benefit | zu einem Fließtext-Brei verschmolzen |

Ursachen und Fixes (alle mit Test):

1. **`ddb_pdf.py::_parse_merkmale`** verwarf Leerzeilen (`elif … and gestrippt:`) — genau die
   Absatzgrenzen des Originals. Sie werden jetzt mitgeführt, Ränder/Mehrfach-Leerzeilen
   normiert `_saeubere_beschreibung`. → `test_absatzgrenzen_im_merkmal_bleiben_erhalten`
2. **`ddb_pdf.py::_verbinde_fragmente`** klebte an JEDER Box-Grenze ein Leerzeichen. DDB füllt
   seine 6 `FeaturesTraits`-Boxen randvoll und schneidet mal mitten im Satz (`…the target has`
   + `the Stunned condition…` → Leerzeichen korrekt), mal exakt an einer Absatzgrenze
   (`…only once per turn.` + `Attack Advantage. You have…` → Absatz!). Neu entscheidet
   `_ist_absatzwechsel` das anhand von Satzende links + Sub-Feature-Kopf rechts (mit
   Stoppwortliste, im Zweifel Leerzeichen — nie Text zerreißen). Das räumt auch dem
   Sprachmodell die Struktur auf, bevor es übersetzt. → `test_smart_join_erkennt_absatzwechsel_an_der_box_grenze`
3. **`de_bogen.py::_merkmal_text`** baut den Kopf jetzt als eigene fette Zeile, darunter die
   Beschreibungsabsätze und zuletzt die Aktionsökonomie als `· …`-Zeilen (`_oekonomie_zeile`
   entfernt DDBs Trenn-Bullet am abgeschnittenen Zeilenende). → `test_merkmalskopf_steht_auf_eigener_zeile`

**Der Gruppenkopf-Filter von vorhin ist damit zurückgenommen**: `Core Monk Traits` steht im
Original ebenfalls (als Überschrift der folgenden Kern-Merkmale) und ist mit dem
Zeilenumbruch auch hier als solche lesbar — Wegfiltern war die falsche Antwort auf
„nicht erkennbar". → `test_leeres_merkmal_bleibt_als_ueberschrift_sichtbar`

Am echten Bogen verifiziert: Der volle Bogen wächst durch die Absätze von 3 auf **4 Seiten**
(erwartet und akzeptiert — Strukturtreue geht vor Kompaktheit).

## Review-Runde 4 (17.07.2026) — Nutzertest-Befunde, umgesetzt

Selbsttest als Spieler (Bogen in der Hand, Foliant-MCP daneben) deckte diese Punkte auf:

1. **Amtliche 2024-Klassenmerkmalsnamen aus dem BESTAND** (größter Hebel): Der Bogen sagte
   „Angriffe abwehren\* (Deflect Attacks)", der Foliant amtlich „**Angriffe umleiten**"
   (SRD 5.2.1 de, S. 70) — Glossar und dnddeutsch kannten die 2024-Namen nicht, obwohl der
   eigene Bestand sie führt. Neues Modul `importer/srd_klassenmerkmale.py`: Struktur-Abgleich
   srd-de (`###### N. Stufe: Name` + `**_Sub:_**`) ↔ ddb-br-2024-en (`Level N: Name`-Einträge
   + `***Sub.***`), Klassenbrücke über das Glossar. NUR beweisbare Zuordnungen — srd-de
   sortiert je Stufe alphabetisch DEUTSCH, DDB alphabetisch ENGLISCH, reine Positions-Paarung
   erzeugte real `Extra Attack → Betäubender Schlag`: (1) Anker `<K> Subclass` ↔
   `…-Unterklasse`, (2) belegte Glossar-Paare, (3) belegte SUB-Features identifizieren ihr
   Eltern-Merkmal (Schlaghagel → Mönchsfokus), (4) Ausschlussprinzip bei genau 1 Rest; alles
   andere wird verworfen (Report). **182 offizielle Paare** auf dem Pi geseedet
   (`seed_klassenmerkmale_aus_bestand`, in der admin-glossar-Orchestrierung; Selbst-
   bereinigung per LIKE-Präfix, weil `kanonisiere_konflikte` demotete Quellen umbenennt).
   Bekannte Lücken (ehrlich verworfen): Barbar St. 7, Druide St. 1, Zauberwirken-Sub-Blöcke.
2. **Fortsetzungskopf-Regression**: Umbruch an Sub-Feature-Absatzgrenze → kopflose
   Fortsetzung. Merkmalsgrenze jetzt am **ganzzeiligen** Fett-Lauf erkannt
   (`_ist_ueberschrift`; ein reiner `\x01`-Start-Check hielt fette Sub-Köpfe wie
   „Wappne dich." für Überschriften).
3. **Keep-with-next**: eine Überschrift bleibt nie als letzte Zeile vor dem Umbruch zurück.
4. **`make glossar-vom-pi`** repariert (sqlite3-CLI fehlt auf dem Pi-Host → Download + ATTACH).

E2E am echten Bogen (echter Anthropic-Lauf): alle 13 Klassenmerkmale amtlich und **ohne
Stern** (einzig „Core Monk Traits" ehrlich mit `*`), Bogen und Foliant nennen dieselben
Namen. Golden-Suite 16/16 am vollen Pi-Bestand, `admin check` sauber, `glossar_web.sqlite`
neu exportiert, web-Container neu gestartet.

### `*`-Sterne: nachfragegetriebenes Nachschlagen (16.07.2026)

**Die Korpus-Lücke ist strukturell gelöst.** Ursprünglicher Befund: Auf der Mac-DB trugen
PHB-Klassenmerkmale einen `*` („Kampfkunst\*", „Schlagserie\*"), obwohl offizielle Begriffe
existieren (**Kampfkünste**, **Schlaghagel**, **Betäubender Schlag** — bei dnddeutsch mit
`PHB(de)` belegt). Ursache: Das Glossar-Seeding ist *bestandsgetrieben* (fragt nur
Eintragsnamen ab) — der Bogen braucht aber Begriffe aus dem *hochgeladenen Charakter*.

Drei Bausteine schließen die Lücke:

1. **`DnddeutschNachschlager`** (`uebersetzer.py`): Unbelegte Begriffe werden VOR der
   LLM-Stufe bei dnddeutsch nachgeschlagen — mit dem Datei-Cache/der Drossel des Importers
   (`app/dnddeutsch.py`, gemeinsames Modul). Treffer → ohne Stern + Best-Effort-Upsert ins
   Glossar (selbstheilend; die read-only-Web-DB nutzt das Direktergebnis). Offline, kein
   Treffer oder Zeitbudget (30 s) erschöpft → wie bisher LLM + ehrlicher Stern. Nur
   Cache-MISSES kosten (0,5 s Drossel); ab dem zweiten Bogen sind die Begriffe gratis.
   Aktiv im Web-Produktionspfad; Tests und Bibliotheksnutzung bleiben netzfrei (Opt-in).
   **Deploy-Hinweis:** `data/cache/dnddeutsch` im Web-Container als Volume mounten,
   sonst zahlt jeder Neustart den Erstkontakt erneut.
2. **Klammer-Lemma-Regel** (`app/dnddeutsch.zeilen_aus_antwort`): „Oil (flask)" belegt
   zusätzlich das nackte Lemma „Oil → Öl" — deterministisch, nur bei eindeutigem Kern
   (keine Kollision, keine invertierte Kommaform; „Rope, hempen (50 feet)" bleibt außen vor).
   Gilt für Seeding UND Nachschlagen.
3. **`make glossar-vom-pi PI=pi@<host>`**: übernimmt die Glossar-Tabelle des vollen
   Pi-Bestands in die lokale Dev-DB — lokale `*`-Urteile werden damit belastbar.

Ehrliche Sterne bleiben: Buch-Eigennamen ohne deutsche Ausgabe („Mist Wanderer",
„Warrior of Shadow", „Living Shadow" aus RtHW) und echt mehrdeutige Lemmata
(„Rope": dnddeutsch kennt nur Hanf-/Seidenseil, kein generisches Seil).

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
