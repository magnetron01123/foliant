# Import-Durchgang

Führe einen Quellen-Import: neue PDFs, die David geliefert hat, oder den Abgleich mit
D&D Beyond. **Gleiche Arbeitsteilung wie beim Rückmeldungs-Durchgang:** Du prüfst und
schlägst vor, David entscheidet — bei der Edition, bei der Import-Freigabe und beim Deploy.

Frag zuerst, welcher Fall vorliegt, wenn es nicht aus dem Auftrag hervorgeht.

## Die Regel, die über allem steht

**Editionen werden NIE geraten. Unklar heißt: nicht importieren.** (SPEC V1/Q3, Kernregel
2. `edition` ist NOT NULL.) Wenn Copyright-Jahr, Terminologie („Volk" vs. „Spezies") und
2024-Marker kein eindeutiges Bild geben: **stopp und David fragen.** Ein falsch getaggter
Band vergiftet jede Auskunft daraus, und niemand sieht es der Antwort an.

## A — Neue PDFs

1. **Triage:** `admin pdf-triage --datei <pfad>` — hat das PDF eine Textschicht?
2. **Nur wenn Scan:** `admin ocr-pdf --datei <pfad>` (deu+eng). Rechnet lange; vorher sagen.
3. **Quelle registrieren** in `config/foliant.toml`: Kürzel, Titel, Sprache, **Edition**
   (siehe Regel oben), Herkunft, Lizenz, `inhaltsart`, `prioritaet` aus dem passenden
   **Prioritätsband** (`importer/quellen.py` nennt die Bänder; `admin check` meldet
   Quellen, die aus ihrem Band fallen).
   `inhaltsart` ist keine Formalie: `abenteuer_setting` schaltet den Spoiler-Schutz für
   diese Quelle — ein Abenteuerband, der als `regelwerk` einläuft, hebelt die oberste
   Verhaltensregel aus.
4. **Importieren:** `admin import --quelle <kuerzel>`
5. **Stichprobe** (O3): Zahlen korrekt, Leserichtung, keine zerrissenen Statblöcke.
   Bei OCR-Scans zusätzlich auf zerrissene Namen und Würfel-Ausdrücke achten.
6. **Gates:** `make test`, nach dem Deploy `make test-golden-pi` und `make check-pi`.

## B — DDB-Abgleich

1. **Was ist da?** `admin status` gegen die Liste der gekauften Bücher.
2. **Artefakte prüfen:** `admin ddb-pruefe --artefakt <pfad>` (ohne DB-Zugriff).
3. **Trockenlauf:** `admin ddb-import-all --dry-run` — zeigt, was einliefe.
4. **Vorlegen, dann importieren.** Kein DDB-Import ohne Freigabe: die Endpunkte sind
   undokumentiert, und ein Buch, das falsch einläuft, ist im Bestand schwerer zu
   entfernen als gar nicht erst aufzunehmen (`admin ddb-remove` existiert, aber der
   Weg zurück ist teurer als das Nachfragen).
5. **Gates** wie oben.

**Abgelaufener Cobalt-Cookie:** Das ist eine Meldung an David, kein Wiederholungsversuch.
401/403 werden im Client bewusst nie wiederholt (O5: Token erneuern ist Nutzersache).

## Fallen, die dieses Projekt teuer bezahlt hat

- **Nach jeder Code-Änderung auf dem Pi:** `docker compose up -d --build --no-deps <dienst>`
  — der Code ist ins Image gebacken. Ohne Rebuild läuft still der alte Stand weiter und
  meldet „Erfolg". Ohne `--no-deps` startet `depends_on` den Live-MCP durch.
- **Facetten nie über einen Re-Import nachziehen**, sondern
  `admin import --quelle facetten`. Ein Re-Import spielt die rohen OCR-Namen wieder ein
  und macht die Namensreparatur der 2014-Scans zunichte.
- **`rsync` aufs Pi nie mit `--delete` und nie mit `data/`** — die Mac-DB würde den vollen
  Bestand überschreiben, gitignorierte Privatmodule verschwänden.
- **Die privaten Druck-Reparatur-Module haben nirgends einen Git-Stand**
  (`importer/frhof_reparatur.py`, `importer/reparatur_ddb_privat.py`). Jede Änderung daran
  ist unwiderruflich — **vorher sichern.**
- **Davids Smarthome-Tunnel auf dem Pi nie anfassen.**
- **`body_md` niemals von Hand korrigieren**, auch wenn die Quelle sich nachweislich irrt
  — bekannte Quellfehler werden gekennzeichnet (`config/quellfehler.py`), nicht repariert.

## Ablage

Neue Quelle → `config/foliant.toml` und die Bestandszahlen dort, wo sie schon stehen.
Entscheidung über Edition/Priorität, die nicht selbsterklärend ist → `CONCEPT.md` §10.
Bekannter Datenmangel, der bleibt → `config/qualitaet_basis.json` (mit Begründung im
Commit) und ggf. `BACKLOG.md` §3.
