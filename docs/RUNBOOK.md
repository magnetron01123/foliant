# Foliant — Runbook (kanonischer Betriebsweg)

**Ein** verbindlicher Weg von Null bis „Runde nutzt es"; andere Dokumente vertiefen
Einzelschritte (`DEPLOY-raspberry-pi.md`, `DDB-IMPORT-anleitung.md`). Adressiert
SYN-P2-006 (Doku-Drift: bislang lag der Betriebsweg über mehrere Dokumente verteilt).

## Voraussetzungen
- Python **3.11+** (Container: 3.12); Docker + Docker Compose auf dem Pi (ARM64).
- Abhängigkeiten **exakt gepinnt** (`requirements.txt`, SYN-P1-012): `pip install -r requirements.txt`.
- Entwicklung am Mac, Betrieb + Importe auf dem Pi (`docker compose exec …`).

## 1. Bestand bauen (Mac oder Pi)
```
python db/init_db.py data/foliant.sqlite          # Schema v2 (CHECK-Constraints)
python -m app.admin import --quelle srd-de        # dt. SRD (Reparaturpaket greift)
python -m app.admin import --quelle open5e-srd-2024   # füllt zauber_meta/monster_meta (Facetten) mit
python -m app.admin import --quelle glossar       # inkl. Kern-Singulare (SYN-P1-006)
```
Hinweis: Der Open5e-Import befüllt zusätzlich `zauber_meta`(grad/schule/klassen) und
`monster_meta`(hg/typ) aus Open5es nativen Feldern — sie erscheinen additiv als `facetten`
in `foliant_hol_zauber`/`_monster`. Alt-DBs (v0/v1) heilt `app.db.connect()` beiläufig auf
Schema v2 (zieht `inhaltsart` nach, setzt `user_version=2`) — jeder Import/Admin-Aufruf genügt.

## 2. Freigeben = testen (Pflicht-Gate)
```
make test          # pytest (beide venvs) + admin check + smoke + GOLDEN-Suite am Bestand
python -m app.admin manifest > korpus-manifest.json   # Fingerabdruck festhalten
```
`make test` grün + Manifest festgehalten = der Bestand ist freigabefähig. Die
Golden-Suite (`tests/test_golden_bestand.py`) prüft Regel-**Semantik**, nicht nur Struktur.

## 3. Server starten
- **Lokal (Dev):** `.venv/bin/uvicorn app.server:app --port 8000` → `GET /ready` == 200,
  MCP unter `http://localhost:8000/mcp` (kein Geheimpfad).
- **Pi (Produktion):** `.env` mit `FOLIANT_PFAD_TOKEN` (≥16 Zeichen, sonst bricht der
  Start ab — SYN-P1-004), `FOLIANT_PRODUKTION=an`, `CLOUDFLARE_TUNNEL_TOKEN`. Dann
  `docker compose up -d --build foliant` (Rebuild ist Pflicht — der Code ist ins Image
  gebacken). Healthcheck zeigt auf `/ready`.

## 4. Connector eintragen
Volle URL inkl. Geheimpfad: `https://<host>/<FOLIANT_PFAD_TOKEN>/mcp` — kein OAuth.
Verhaltensschicht: das Claude-Projekt mit `docs/CLAUDE-PROJEKT-ANWEISUNG.md` einrichten.

## 5. Abnahme fahren
`docs/EVAL-CHECKLISTE.md` im Connector durchspielen (T2/T10/T12 + P0-Verifikation).

## 6. Betrieb
- **Readiness:** `curl http://localhost:8000/ready` (503 bei kaputtem/leerem Bestand).
- **Uptime:** externer Monitor auf `https://<host>/health` (immer offen, nur Status).
- **Off-Site-Backup (nächtlich, M3):** `python -m app.admin backup` erstellt ein
  **konsistentes** Online-Backup (SQLite-Backup-API — verträgt einen laufenden Import,
  anders als `cp`/`rsync` auf die offene Datei) unter `data/backups/`, **verifiziert** es
  (integrity_check + FTS-Zeilengleichheit; scheitert die Prüfung, wird die Datei verworfen)
  und hält die letzten `--behalten` Stände (Default 14). Cron auf dem Pi, danach das
  Verzeichnis auf ein zweites Gerät spiegeln — **der Spiegel-Schritt ist die eigentliche
  Off-Site-Sicherung** (David: Ziel/Zugang einrichten):
  `0 3 * * * docker compose exec -T foliant python -m app.admin backup && rsync -a <db-ordner>/backups/ <offsite>:foliant-backups/`
  Restore-Probe: ein Backup als `data/foliant.sqlite` zurückspielen → `make test-daten` muss bestehen.
- **Token-Rotation bei Leak:** neuen Token in `.env` → `docker compose up -d --build
  foliant` → neue URL an die Runde; **alte Logs gelten als tokenbelastet** (der Pfad war
  das Secret) — Access-Logs sind per `--no-access-log` aus, Blockier-Logs redigieren.

## 7. DDB-/Privatinhalte (bewusste Eigentümer-Entscheidung)
Der Serve-Container sieht `data/private` **nicht** (SYN-P1-005). DDB-Import als
Einmal-Container mit explizitem Mount (siehe `DEPLOY-raspberry-pi.md` §DDB). Abenteuer-/
Setting-Bände tragen `inhaltsart=abenteuer_setting` und lösen in jeder Antwort den
Spoiler-Hinweis aus; Playtest-Material wird gar nicht erst importiert (SYN-P0-007).

## Was bewusst offen bleibt (nach MVP / langfristig)
`concept/variant/relation`-Modell, SL-Rollen-Isolation, Regelbeziehungsgraph, Errata-
Tracking, OAuth-Identität — siehe Synthese Kap. 18 Stufen D/E. Nicht rundenblockierend.
