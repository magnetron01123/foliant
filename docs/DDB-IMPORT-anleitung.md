# DDB-Bücher importieren — Kurzanleitung (Automatik)

Für wiederkehrende Käufe: **drei Schritte, keine Konfiguration pro Buch.** Der Export
(mit Netz + Cobalt) und der Import (offline, in die private DB) sind bewusst getrennt.

## Einmalig einrichten

1. **Exporter-Umgebung** (getrennt von der Laufzeit, enthält SQLCipher):
   ```
   python3 -m venv .venv-ddb && .venv-ddb/bin/pip install -r requirements-ddb.txt
   ```
2. **Cobalt in den macOS-Keychain legen** (OS-verschlüsselt, kein Klartext im Dateisystem;
   der Wert wird verdeckt abgefragt und steht so nie in der Befehlszeile):
   ```
   security add-generic-password -U -a foliant -s foliant-ddb-cobalt -w
   ```
   Den `CobaltSession`-Wert aus einer angemeldeten dndbeyond.com-Browsersitzung einfügen
   (Entwicklertools → Application/Speicher → Cookies → `CobaltSession`). **Wie ein
   Passwort behandeln.** Läuft der Wert ab (Logout/Zeitablauf), denselben Befehl erneut.

## Bei jedem neuen Buch (bzw. jederzeit)

```
# 1. Alle EIGENEN Regelbücher exportieren (auto-erkannt; schon Exportiertes wird übersprungen)
.venv-ddb/bin/python -m importer.ddb_exporter sync

# 2. Alle Artefakte offline in die PRIVATE Datenbank importieren
.venv/bin/python -m app.admin ddb-import-all
```

Das war's. `sync` löst deine gekauften Bücher automatisch über das öffentliche
DDB-Verzeichnis auf (Titel + Edition), lädt jedes neue Buch und schreibt ein geprüftes
Artefakt. `ddb-import-all` übernimmt sie in `data/private/foliant-private.sqlite` —
die öffentliche `data/foliant.sqlite` bleibt unberührt.

Nützliche Varianten:
- `sync --dry-run` — nur anzeigen, was importiert/übersprungen würde (kein Schreiben).
- `sync --force` — bereits exportierte Bücher neu laden (z. B. nach Errata).
- `ddb-import-all --dry-run` — Import prüfen, ohne die private DB zu aktivieren.

## Was geladen und was übersprungen wird

`sync` lädt **alle eigenen Bücher** (wichtig für die Übersetzungsterminologie, gerade
ältere) und nennt zu jedem eine Einordnung:
- **Ältere Bücher ohne Content-Text** werden aus den strukturierten Detailtabellen
  gelesen (Zauber/Monster/Talente/Spezies als Einzeleinträge) — im Bericht „Quelle:
  Detailtabellen".
- **Abenteuer-/Setting-/Playtest-Bücher** werden geladen, aber als Kampagnen-/Spoiler-
  Inhalt **gekennzeichnet** (bewusste Eigentümer-Entscheidung).
- **Regelversion IMMER korrekt, nie geraten (V1/Q3):** Der Exporter liest die Edition
  autoritativ aus der Buch-Datenbank (`RPGSourceCategory` bzw. `ReleaseDate` — vor 2024
  ist sicher 2014). Lässt sie sich **nicht eindeutig** bestimmen (z. B. „Sage Advice &
  Errata", laufende Errata über beide Editionen), wird das Buch **NICHT geladen**, sondern
  gemeldet. Willst du so ein Buch dennoch, setze die Edition bewusst als `[[ddb.buch]]`
  mit `edition = "2014"`/`"2024"` in `config/foliant.toml` und ziehe es mit
  `export --quelle <kuerzel>`.

Eine falsch geladene Quelle entfernst du mit
`python -m app.admin ddb-remove --quelle <kuerzel>`.

Bewusst **ausgelassen**: nur **Premade-Character-Pakete** (Charakterdaten — Charakter-
Import ist eine spätere Stufe).

**Nicht ladbar** sind Bücher, die die DDB-Mobile-API mit `status=error` verweigert (bei
diesem Account u. a. Sage Advice Compendium 2014, Core Rules, Unearthed Arcana 2014) —
sie sind über diesen Weg technisch nicht verfügbar und werden im Bericht genannt.

## Betrieb auf dem Pi (Standard-Betriebsmodell)

Alle Importe laufen auf dem **Raspberry Pi**; der Mac mini dient nur Entwicklung und
Administration. Der Export läuft dort im gehärteten `ddb`-Container, der Import im
`foliant`-Container — Schritt-für-Schritt in `docs/DEPLOY-raspberry-pi.md` (Abschnitt
„DDB-Buchimport auf dem Pi"). Die obigen Befehle sind die lokale Entwickler-Variante.

## Bereitstellung: bediente vs. private DB

Wo die Bücher landen, steuert `config/foliant.toml`:
- **`[ddb] ins_hauptbestand = true`** → DDB-Bücher werden in die **bediente** DB
  (`data/foliant.sqlite`) gemergt und sind damit über den Connector durchsuchbar. So läuft
  der Pi (bewusste Eigentümer-Entscheidung; der Tunnel ist authless). Optional auf
  **Cloudflare-Ebene** mit Access/IP-Allowlist absichern.
- **ohne diese Zeile** → separate private DB (`data/private/foliant-private.sqlite`), die
  der öffentliche Endpoint NICHT serviert.

Der Merge bleibt in beiden Fällen atomar, mit Backup und Integritätsprüfung; SRD/Open5e
bleiben erhalten.

## Sicherheit

- Cobalt lebt nur im Keychain (oder kurzlebig im TTY/Container-Secret), nie in Git,
  `.env`, Befehlszeile oder Logs.
- Der Exporter berührt **keine** Foliant-Datenbank; heruntergeladene Archive und
  entschlüsselte Buch-DBs werden nach jedem Lauf gelöscht.
- Import läuft offline, atomar und verlustsicher (Backup + Integritätsprüfung vor
  Aktivierung); ein fehlerhaftes Buch lässt den vorhandenen Bestand unverändert.
