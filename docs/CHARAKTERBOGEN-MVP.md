# Charakterbogen-Übersetzer (DDB EN → deutscher WotC-Bogen)

Feature neben dem Foliant-MCP, live unter `dnd.magnetron.me`: Ein englischer
D&D-Beyond-PDF-Export wird ausgelesen, ins Deutsche übersetzt und auf den **offiziellen
deutschen WotC-Charakterbogen (2024)** übertragen — als druckbares PDF.
Spieler-Kurzanleitung: `CHARAKTERBOGEN-ANLEITUNG-RUNDE.md`.

## Pipeline (3 Stufen, LLM klar isoliert)

```
DDB-PDF (EN) ──[1 Extractor]──► neutrales Modell (EN) ──[2 Übersetzer]──► Modell (DE) ──[3 Renderer]──► DE-Bogen-PDF
             deterministisch                          Claude + Foliant                 deterministisch
```

Parsen und Rendern sind reiner, testbarer Code; nur die Übersetzung ist LLM-basiert.
**Zahlen, Würfel und Modifikatoren laufen NIE durch das Sprachmodell.**

## Module (`app/charakterbogen/`)

| Datei | Rolle |
|---|---|
| `modelle.py` | Neutrales Charaktermodell. Übersetzbares als `UeText{en,de,art}`, Zahlen roh. `roh_felder` = verlustfreies Protokoll aller befüllten Widgets. |
| `ddb_pdf.py` | **Extractor**: liest verwaiste `/Widget`-Annotationen (kein AcroForm) via PyMuPDF, Smart-Join der `FeaturesTraits`/`Actions`-Fragmente, Fingerprint-Prüfung der Exportfamilie. |
| `feldkarten/ddb_pdfsharp_6_1.json` | `source_map`: DDB-Feld → Modellpfad + Fingerprint. |
| `feldkarten/de_wotc_2025.json` | `layout_map`: Modellpfad → Position auf dem DE-Bogen (aus Ankern + Vektor-Boxen abgeleitet; an DE-Version 670D…01 DE gebunden). |
| `feldkarten/code_map.json` | Feste Kürzel (`1A`→`1 Aktion`, `STÄ/GES…`, Münzen). |
| `terminologie.py` | Löst feste Begriffe **in-process über `app.glossar`** auf (kein zweites Glossar) → §5-Form. |
| `uebersetzer.py` | Provider-Vertrag + Anthropic-Adapter (httpx) + Fake. Zweistufige Übersetzung, Übersetzungsgedächtnis, JSON-Vertrag mit 1× Retry. |
| `de_bogen.py` | **Renderer** (fitz-Overlay): zeichnet Werte auf eine Kopie der DE-Vorlage, Auto-Fit, Fortsetzungsseiten bei Überlauf, Kalibrier-Modus. |
| `glossar_export.py` | Erzeugt die glossar-nur-DB für den Web-Container (kein privater Buchinhalt im Web-Container). |
| `web.py` | Schmale Starlette-App: `GET /` (Upload), `POST /bogen`, `GET /health`. Kennwort-Seite, Ein-Konvertierung-Semaphore, keine Persistenz, `no-store`/CSP. |
| `templates/`, `static/` | Upload-Karte im Bogen-Stil (keine externen Fonts/CDNs). |

---

## Die tragenden Entwurfsregeln

### Regel §5 — die einzige Übersetzungsregel
Ausgabe immer `Deutscher Begriff (English Original)`. `*` am deutschen Wort, wenn das
Foliant-Glossar keinen **exakten, belegten** Treffer hat (dann bildet das Sprachmodell die
deutsche Wiedergabe). Nie nur Englisch. Fuzzy-Treffer zählen nie (Identität nur bei
`match == "exakt"`).

### Zwei LLM-Stufen statt einer
1. **Belegte Begriffe** kommen deterministisch aus dem Glossar (kein LLM).
2. **Stufe 1 — unbelegte Begriffe/Eigennamen** („Warrior of Shadow"): eigener, kurzer
   Aufruf. Ergebnis → §5-Form mit `*` **und** als bindende Vorgabe für Stufe 2.
3. **Stufe 2 — Fließtexte**: mit allen Namen (Glossar + Stufe 1) als Vorgabe.

Ohne diese Trennung übersetzte ein einziger Aufruf Feld und Fließtext unabhängig — derselbe
Name hieß im Feld „Krieger des Schattens" und im Fließtext „Kämpfer des Schattens".
**Gemessen** (Sorin Vale, Sonnet): Stufe 1 = 37 Felder / 449 Zeichen / 6 s; Stufe 2 =
54 Felder / 6731 Zeichen / 37 s; gesamt ~44 s (Läufe schwanken API-bedingt ~42–80 s).

### Listen laufen gar nicht durchs Sprachmodell
Waffen-, Werkzeug- und Sprachlisten werden **item-weise** über Glossar/dnddeutsch aufgelöst
(`_liste_deterministisch`); Unbelegtes bleibt unverändert englisch. Zwei Gründe:
- **Sachliche Fehler:** „Crossbow, Hand" ist DDBs invertierte Schreibweise für *eine* Waffe.
  Das Modell zerlegte sie am Komma zu „Armbrust" + „Handarmbrust" und bescheinigte damit eine
  Vertrautheit, die der 2024-Mönch nicht hat. Der Extractor normalisiert invertierte Namen
  jetzt **vor** allem anderen.
- **Stabilität:** „Wargong" hieß je Lauf „Kriegsgong", „Trommel" oder blieb englisch.

### Amtliche Begriffe kommen aus dem Bestand, nicht vom Modell
- **Freitext-Begriffe:** `glossar.begriffe_im_text()` scannt jeden Fließtext **vor** dem
  LLM-Lauf und erzwingt amtliche Begriffe als Vorgabe (Gepackt statt „ergriffen").
- **2024-Klassenmerkmalsnamen** (größter Hebel): Der Bogen sagte „Angriffe abwehren*
  (Deflect Attacks)", der Foliant amtlich **„Angriffe umleiten"** (SRD 5.2.1 de, S. 70) —
  Glossar und dnddeutsch kannten die 2024-Namen nicht, obwohl der eigene Bestand sie führt.
  `importer/srd_klassenmerkmale.py` gleicht die Struktur ab (srd-de `###### N. Stufe: Name`
  ↔ ddb-br-2024-en `Level N: Name`). **Nur beweisbare Zuordnungen** werden geseedet: srd-de
  sortiert je Stufe alphabetisch DEUTSCH, DDB alphabetisch ENGLISCH — reine Positions-Paarung
  erzeugte real `Extra Attack → Betäubender Schlag`. Stufen: (1) Anker `<K> Subclass` ↔
  `…-Unterklasse`, (2) belegte Glossar-Paare, (3) belegte Sub-Features identifizieren ihr
  Eltern-Merkmal, (4) Ausschlussprinzip bei genau einem Rest. Alles andere wird ehrlich
  verworfen. **Endstand: 214 offizielle Paare** auf dem Pi.
- **Vorlagen-Labels** des gedruckten WotC-Bogens gelten selbst als offizielle Quelle
  („Heldische Inspiration") — so können Fließtext und Vordruck nicht auseinanderlaufen.

### Nachfragegetriebenes Nachschlagen schließt die Korpus-Lücke
Das Glossar-Seeding ist *bestandsgetrieben* (fragt nur Eintragsnamen ab) — der Bogen braucht
aber Begriffe aus dem *hochgeladenen Charakter*. Drei Bausteine:
1. **`DnddeutschNachschlager`**: unbelegte Begriffe werden VOR der LLM-Stufe bei dnddeutsch
   nachgeschlagen (gemeinsamer Cache/Drossel mit dem Importer, `app/dnddeutsch.py`). Treffer
   → ohne Stern + Best-Effort-Upsert ins Glossar. Offline, kein Treffer oder Zeitbudget (30 s)
   erschöpft → LLM + ehrlicher Stern. Ab dem zweiten Bogen sind die Begriffe gratis.
2. **Klammer-Lemma-Regel**: „Oil (flask)" belegt zusätzlich das nackte Lemma „Oil → Öl" —
   deterministisch, nur bei eindeutigem Kern („Rope, hempen (50 feet)" bleibt außen vor).
3. **`make glossar-vom-pi PI=pi@<host>`**: übernimmt die Glossar-Tabelle des vollen
   Pi-Bestands in die lokale Dev-DB — erst damit sind lokale `*`-Urteile belastbar.

Ehrliche Sterne bleiben: Buch-Eigennamen ohne deutsche Ausgabe („Mist Wanderer", „Warrior of
Shadow") und echt mehrdeutige Lemmata („Rope": dnddeutsch kennt nur Hanf-/Seidenseil).

### Struktur- und Layouttreue
- **DDB-Struktur bleibt erhalten:** Absatzgrenzen im Merkmal werden mitgeführt; der
  Smart-Join entscheidet an der Box-Grenze per `_ist_absatzwechsel` (Satzende links +
  Sub-Feature-Kopf rechts, im Zweifel Leerzeichen — nie Text zerreißen). Merkmalskopf steht
  als eigene fette Zeile, darunter die Absätze, zuletzt die Aktionsökonomie als `· …`-Zeilen.
- **Eine Schriftgröße je Kasten** (2-Spalten-Boxen fitten gemeinsam); Fortsetzungsseiten
  erben die Größe der Ursprungsbox.
- **Nie stumm überlaufen:** Auto-Fit → §5-Klammer opfern → horizontal stauchen.
- **Fortsetzungskopf immer**, wenn ein Merkmal über die Box bricht („… (Fortsetzung):");
  Vorlagen-Kopien tragen nur den **Namen** im Kopf (Klasse/Stufe sind dort nicht relevant).
  Seitenzahlen („Seite N von M") nur, wenn Fortsetzungsseiten eingefügt wurden.
- **Deterministische Notation:** zentrale d→W-Wandlung (5d8→5W8) auf **jedem** Feld;
  Zauber-Notizen `V/S`→`V/G`, `S/M`→`G/M`, `D:`→`WD:`; deutsche Anführungszeichen font-sicher.
- **Mehrklassen:** „Fighter 3 / Wizard 2" ließ Klasse/Stufe stumm leer. Jetzt „Kämpfer 3 /
  Magier 2 (Fighter 3 / Wizard 2)", jede Teilklasse nur bei exaktem Glossar-Treffer übersetzt;
  die Charakterstufe ist die regeldefinierte SUMME (srd-de „Klassenkombinationen", S. 28).

### Bewusste Auslassungen (Entscheidung 16./17.07.2026)
DDB-Export-Inhalte ohne Feld auf dem DE-WotC-Bogen — extrahiert, aber nicht gerendert:
passive Einsicht/Untersuchung (aus den Fertigkeiten ableitbar), Zauber-Herkunft und
Seitenreferenzen, der statische ACTIONS/BONUS-ACTIONS-Block (Regel-Boilerplate), Spielername.
**Gerendert** werden dagegen Dunkelsicht (zweite Zeile im Bewegungsrate-Feld) und Traglast
(in kg, am Fuß der Ausrüstungs-Box).

> **Nicht neu bauen:** Eine **Kurzfassung ohne Merkmalstexte** (ZIP mit zwei Bögen) war
> zwischenzeitlich umgesetzt und wurde am 17.07.2026 nach zwei Nachbesserungsrunden bewusst
> **komplett entfernt** — die reine Namensliste trägt zu wenig Information. `POST /bogen`
> liefert genau EINE vollständige PDF.
>
> Strukturtreue geht vor Kompaktheit: durch die erhaltenen Absätze wächst ein voller Bogen
> von 3 auf 4 Seiten. Das ist erwartet und akzeptiert.

---

## Lokal ausführen

```sh
# Tests (committbar, nur synthetische Fixtures):
.venv/bin/python -m pytest -q tests/test_charakterbogen_*.py

# Web-App lokal (GET / funktioniert ohne API-Key; POST /bogen braucht den Provider):
.venv/bin/python -m uvicorn app.charakterbogen.web:app --host 127.0.0.1 --port 8099
```

Die echten Vorlagen liegen gitignored unter `vorlagen/charakterboegen/` (offizieller DE-Bogen
+ private DDB-Beispiele). Die privaten Golden-Tests
(`tests/test_charakterbogen_*_golden_privat.py`) laufen gegen sie und sind ebenfalls gitignored.

**Konfiguration (`.env`):** `ANTHROPIC_API_KEY` (fehlt er → `POST /bogen` meldet
„Übersetzung momentan nicht verfügbar", der Rest läuft) und `ANTHROPIC_MODEL` (Modell-ID,
nicht hart kodiert). Ohne Key sind Extraktion, Terminologie, Rendering und die Web-Fehlerpfade
vollständig mit Fakes getestet; nur der echte Freitext-Lauf ist dann offen.

---

## Deployment

Vollständig in `DEPLOY-raspberry-pi.md` (§1 Container, §3 Website mit Kennwort und
Provider-Key). Kurz: Der Cloudflare-Tunnel zeigt auf `gateway:8080`; Caddy routet `/mcp`,
`/health` und `/ready` an `foliant`, alles andere an `web`. Connector-Pfad, IP-Filter,
Streaming und die 16 Tools bleiben davon **unberührt** — am vollen Pi-Bestand verifiziert
(14.07.2026).

**Drei teuer gelernte Stolperfallen:**
- `docker compose up --build web gateway` baut über `depends_on` **auch `foliant`** neu und
  startet den Live-MCP durch → immer **`--no-deps`**.
- `rsync` **ohne** `--delete` und **ohne** `data/` — die Mac-DB ist nur ein Subset und würde
  den vollen Pi-Bestand überschreiben; gitignorierte Privatmodule verschwänden.
- Die **glossar-nur-DB muss existieren, BEVOR `web` startet** — sonst legt Docker ein
  Verzeichnis statt der Datei an.
- **Cache mounten:** `data/cache/dnddeutsch` read-only in den Web-Container, sonst zahlt jeder
  Neustart den Erstkontakt erneut.

**Nach jeder Caddyfile-Änderung Pflicht:** der 403-Test aus `DEPLOY-raspberry-pi.md` §2.
Ginge `CF-Connecting-IP` hinter Caddy verloren, wäre die IP-Allowlist des MCP lautlos aus.
