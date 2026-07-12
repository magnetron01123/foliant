# DDB-Machbarkeits-Spike — Runbook + Protokoll

**Status 11.07.2026: SPIKE BESTANDEN am echten Account (Apple Silicon/arm64); Pi-Pilot
offen.** Auf ausdrückliche Anweisung des Eigentümers (David, „bin mir der Risiken bewusst,
bin nicht zuhause") wurde der komplette echte Durchlauf am Mac ausgeführt:

- **Auth:** angemeldet als „Magnetron44523". Zwei Korrekturen am Client waren nötig und
  sind an echten Antworten verifiziert: die Mobile-API nimmt den Cobalt als `token`-
  **Formfeld** (nicht als Cookie — mit Cookie kam nur anonymer Gratis-Inhalt), und
  `book-codes` liefert den Schlüssel **Base64-codiert**. `user-data` trägt `userId` oben.
- **SQLCipher v3** entschlüsselt echte DDB-Buch-DBs readonly auf arm64 (kein Node-Fallback).
- **Exportiert + offline in die PRIVATE DB importiert:** Player's Handbook 2024 (id 145)
  und Ravenloft: The Horrors Within (id 232) — beides gekaufte Bücher. Nach heading-
  basiertem Chunking: 1605 bzw. 807 Einzeleinträge; private DB `foliant-private.sqlite`
  = 5033 Einträge, Integrität ok, FTS synchron. Die **öffentliche `data/foliant.sqlite`
  enthält weiterhin 0 DDB-Inhalte** (Trennung bewiesen).
- **Secret-Hygiene:** Cobalt lag kurzzeitig in einer 0600-Datei außerhalb des Repos
  (`~/.foliant-ddb-cobalt`), gelesen über `FOLIANT_COBALT_DATEI`; nach der Arbeit gelöscht.
  Keine ZIP/DB3-Reste, kein Cobalt in Repo/Artefakten/DB/Logs (geprüft). **David wechselt
  den Cobalt-Wert per Logout.**

**Offen (echtes Gate):** derselbe Durchlauf auf dem Raspberry Pi (Compose-Profil `ddb`)
als ARM64-Pilot; und B2 — private Inhalte NIE über den authlosen Tunnel.

Der ursprüngliche Ablauf (für Wiederholung/Pi) steht unten.

## Was der Spike beweisen muss (aus dem Vorschlag, §6)

1. `apsw-sqlite3mc` (Python 3.12) installiert und lädt auf ARM64 — zuerst am Mac
   (Apple Silicon = arm64, schnelle Iteration), abschließend auf dem Pi (`aarch64`).
2. Eine synthetische SQLCipher-v3-Testdatenbank lässt sich erstellen und readonly öffnen
   (Parameter: `cipher=sqlcipher`, `legacy=3`; dokumentiert im Testcode, nicht als
   stiller Default).
3. Manueller `--dry-run` mit einem eigenen Buch: Cobalt-Auth ok → nur eigene Bücher
   gelistet (`EntityTypeID == 496802664`, `isOwned == true`) → signierte URL → ZIP
   vollständig → Schlüssel passt → genau eine `.db3` → `Content`-Tabelle mit erwarteten
   Spalten → mindestens ein nicht-leerer `RenderedHTML`-Datensatz — und dabei: keine
   Projekt-DB berührt, kein Token/Schlüssel/URL-Querystring in Logs oder Dateien.

## Ablauf für Schritt 3 (der eigentliche Dry-run — braucht dich)

1. Trage dein Buch in `config/foliant.toml` ein (`[[ddb.buch]]`; die echte `id` zeigt
   dir Schritt 3a). Vorlage: `config/foliant.example.toml`.
2. **3a — Bücherliste:** Melde dich im Browser bei dndbeyond.com an, öffne die
   Entwicklertools → Cookies → kopiere den Wert von `CobaltSession` (wie ein Passwort
   behandeln!). Dann am Mac im Projektordner:
   `.venv-ddb/bin/python -m importer.ddb_exporter list-owned`
   — der Cobalt wird **verdeckt** abgefragt (nie Argument, nie `.env`).
3. **3b — Dry-run:** `.venv-ddb/bin/python -m importer.ddb_exporter export
   --quelle <kuerzel> --dry-run` → prüft Besitz, lädt das Archiv, entschlüsselt readonly
   und druckt nur den Abdeckungsbericht (kein Artefakt, keine DB).
4. **3c — Export + Offline-Import:** ohne `--dry-run` entsteht das Artefakt; danach
   `python -m app.admin ddb-import --quelle <kuerzel> --artefakt <pfad> --dry-run`
   (öffentliche DB bleibt garantiert unberührt; aktiviert wird nur die private).
5. Danach Cobalt im Browser per Logout invalidieren, wenn gewünscht. Für den
   Pi-Abschluss: gleiche Schritte im `ddb`-Compose-Profil auf dem Pi
   (`docker compose --profile ddb run --rm ddb-exporter …`).

## Fallback-Regel (unverändert aus dem Vorschlag)

Node 22 + `better-sqlite3-multiple-ciphers` NUR, wenn das ARM64-Wheel nicht installierbar
ist oder APSW die echte Buch-DB trotz korrekter SQLCipher-v3-Parameter nicht öffnet.
HTTP-/Token-/Formatfehler rechtfertigen keinen Technologiewechsel. Scheitert der Weg
dauerhaft, bleibt die dokumentierte Rückfallebene: gekaufte deutsche Buch-PDFs über die
bestehende, gehärtete Pipeline (F5-Entscheidung dann beim Eigentümer).
