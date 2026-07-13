# Sicherheitsrichtlinie

## Schwachstellen melden

Bitte melde Sicherheitslücken **nicht über öffentliche Issues**, sondern über die private
**"Report a vulnerability"**-Funktion von GitHub (Reiter *Security* → *Advisories* dieses
Repositorys). So bleibt die Meldung vertraulich, bis ein Fix bereitsteht.

Bitte gib an: betroffene Komponente, Reproduktionsschritte, mögliche Auswirkung und —
falls vorhanden — einen Vorschlag zur Behebung. Eine erste Rückmeldung erfolgt in der
Regel innerhalb weniger Tage.

## Unterstützte Versionen

Dies ist ein self-hosted Projekt ohne Release-Kadenz. Sicherheitsfixes fließen in den
`main`-Branch; betreibe die Instanz nah an `main`.

## Sicherheitsmodell des Servers

- **Kein Geheimnis liegt im Repository.** Zugangs-Token, Cloudflare-Tunnel-Token und
  Datenbank liegen ausschließlich in `.env` bzw. `data/` — beide sind `.gitignore`-t.
  Die Vorlage `/.env.example` zeigt die benötigten Variablen ohne Werte.
- **Zugang** (`app/zugriff.py`): Der MCP-Endpoint liegt unter einem geheimen Pfad-Token
  (`/<FOLIANT_PFAD_TOKEN>/mcp`) und ist zusätzlich per IP-Allowlist auf die Egress-Ranges
  des vorgesehenen Clients begrenzt (`CF-Connecting-IP`). `/health` bleibt offen.
  Token-Rotation: Wert in `.env` ändern → Image neu bauen → neue URL verteilen.
- **Read-only-Betrieb:** Der Server öffnet die SQLite-Datenbank schreibgeschützt
  (`mode=ro`, `query_only=ON`); alle 16 Tools sind als `readOnlyHint` deklariert.
- **Fail-fast:** Mit `FOLIANT_PRODUKTION=an` verweigert der Server den Start, wenn das
  Pfad-Token zu kurz (< 16 Zeichen) ist.
- **Eingabegrenzen:** Suchanfragen sind längenbegrenzt, `limit` wird gedeckelt (DoS-Schutz).

## Verantwortung des Betreibers

- Halte `.env`, die Datenbank und etwaige D&D-Beyond-Zugangsgeheimnisse (Cobalt) aus der
  Versionskontrolle heraus. Cobalt darf nie in `argv`, `.env` (dauerhaft), Logs oder Git
  landen.
- **Inhalte-Recht:** Dieses Repository enthält **keine** kommerziellen Regelinhalte. Die
  aus gekauften Druck-PDFs abgeleiteten Reparatur-Module (`importer/frhof_reparatur.py`,
  `importer/reparatur_ddb_privat.py`) sind bewusst **nicht** Teil des öffentlichen Codes
  (`.gitignore`-t). Wer den Server mit kommerziellen Büchern betreibt, nutzt eigene,
  rechtmäßig erworbene Quellen und ausschließlich zum privaten Eigenbedarf. Gib solche
  Inhalte nicht weiter und committe sie nicht.
