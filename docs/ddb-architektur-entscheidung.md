# ADR: DDB-Buchimport — Architekturentscheidung (Phase 6)

**Datum: 10.07.2026 · Status: entschieden (Umsetzung bis zum Machbarkeits-Gate, s. u.)**

Verglichen wurden der **unabhängige Eigenentwurf** (`docs/ddb-architektur-eigenentwurf.md`,
vor dem Lesen der Entwürfe erstellt) und der vorhandene **Vorschlag**
(`docs/VORSCHLAG-DDB-IMPORT-RASPBERRY-PI.md`, präzisiert durch
`CLAUDE-CODE-AUFTRAG-DDB-IMPORT-RASPBERRY-PI.md`). Übereinstimmung war kein Kriterium;
entschieden wurde nach Evidenz.

## Entscheidung

**Die Architektur des Vorschlags wird umgesetzt** — mobile-API-Abruf des ganzen Buchs
(user-data → available-user-content → owned-Filter → get-book-url → ZIP → book-codes →
readonly SQLCipher-v3-Entschlüsselung → `Content.RenderedHTML` → Markdown), kurzlebiger
Export-Prozess ohne DB-Zugriff, **Artefaktvertrag v1** (manifest.json + entries.jsonl),
offline Import in eine **private Kandidaten-DB** (`data/private/foliant-private.sqlite`),
atomare Aktivierung; die öffentliche `data/foliant.sqlite` bleibt DDB-frei. Python 3.12 +
`apsw-sqlite3mc` zuerst, Node-22-Helfer nur bei nachgewiesener Fallback-Bedingung.

## Warum der Eigenentwurf (V1: ddb-proxy) verliert

Extern verifiziert (10.07.2026, [ddb-proxy](https://github.com/MrPrimate/ddb-proxy),
[ddb-importer-Doku](https://docs.ddb.mrprimate.co.uk/docs/faqs/ddb-importer)): Der
self-hosted `ddb-proxy` liefert **nur Charaktere, Zauber, Items, Monster** — keine
Klassen/Spezies/Hintergründe/Talente und keinen Buch-Fließtext; er ist ein „cut down MVP"
(letzte Release Feb 2024). **F5 („Bücher/Regelinhalte") wäre damit nicht erfüllbar.**
Der Vorschlag deckt F5 vollständig über den im aktiv gepflegten
[Adventure Muncher](https://github.com/MrPrimate/ddb-adventure-muncher) belegten
Mechanismus. Meine NF6-Bedenken (undokumentierte Endpunkte) adressiert der Vorschlag durch
Kapselung in genau ein Adaptermodul, einen **verbindlichen Phase-0-Machbarkeitstest** und
eine klare Exit-Strategie — das ist tragfähiger als ein dokumentierter, aber fachlich
unzureichender Proxy. Zusätzlich ist der Vorschlag in zwei Punkten strikt besser als der
Eigenentwurf: **Cobalt via verdeckter TTY-Eingabe statt Env** (der bisherige Stub-Weg
`FOLIANT_COBALT` in `.env` entfällt) und die **strukturelle Trennung öffentliche/private
DB** (B2 wird zur Architektur statt zur Fußnote).

## Was aus dem Eigenentwurf übernommen wird

1. **Spike-Iteration zuerst auf Apple Silicon (ebenfalls ARM64)** — schnellere Zyklen;
   der Nachweis auf dem echten Pi bleibt Pflicht vor „fertig" (unverändertes Gate).
2. **ddb-proxy wird ausdrücklich als verworfene Alternative dokumentiert** (dieses ADR),
   damit der Weg nicht später „hilfreich" wieder geöffnet wird; `[ddb].proxy_url` und
   `FOLIANT_COBALT` verschwinden aus den Vorlagen (wie auch der Vorschlag verlangt).
3. **Rückfallebene bleibt benannt:** Scheitert der Spike dauerhaft, erfüllen gekaufte
   deutsche Buch-PDFs (bestehende, gehärtete Pipeline) den Inhaltsbedarf; DDB bliebe dann
   unerschlossen (Eigentümer-Entscheidung zu F5 nötig).

## Konsequenzen / Umsetzungsstand

- **Jetzt (architektur-neutral, offline, fixture-getrieben):** Artefaktvertrag v1 mit
  Validator + synthetischen Fixtures; neuer Offline-Importer `importer/import_ddb.py`
  (ersetzt den Proxy-Stub; kein HTTP-/Cobalt-Code); Admin-Befehle; Tests. Diese Teile
  gelten für jedes Export-Backend (Python, Node-Fallback) und zementieren keinen
  unbewiesenen Weg.
- **Gate (manuell, Freigabe erforderlich):** Phase-0-Spike mit echtem Account/Cobalt und
  eigenem Buch (zuerst Mac, dann Pi) — Runbook: `docs/ddb-spike-runbook.md`. Erst danach:
  DDB-Client, Download/Entschlüsselung, Compose-Service.
- **Go-live privater Inhalte bleibt gesperrt** (authloser Tunnel), wie in beiden
  Dokumenten festgehalten — separater Auftrag B2.
