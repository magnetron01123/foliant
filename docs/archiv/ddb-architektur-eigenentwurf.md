# DDB-Buchimport — unabhängiger Architekturentwurf (Phase 5)

**Erstellt: 10.07.2026, VOR dem Lesen der vorhandenen DDB-Entwürfe** (`docs/VORSCHLAG-DDB-IMPORT-RASPBERRY-PI.md`, `CLAUDE-CODE-AUFTRAG-DDB-IMPORT-RASPBERRY-PI.md`) — bewusst nicht geankert. Der Vergleich mit diesen Dokumenten folgt in der Entscheidungsnotiz (ADR).

## 1. Faktenlage

### Im Projekt belegt
- **F5** verlangt den Import auf D&D Beyond gekaufter **Bücher/Regelinhalte** (keine Charaktere, K1); **Q7**: einmaliger Import, kein Laufzeit-DDB-Zugriff; **O5**: Cobalt-Cookie nur server-seitig, Ausfall trifft nur den Import.
- Die Import-Pipeline ist seit Korrekturlauf A7 **atomar und verlustsicher** (parse-vor-delete, Schrumpf-Schutz, Aufrufer-Transaktion) — jeder DDB-Weg muss über `importiere_markdown` bzw. dieselben Schutzregeln laufen.
- **S10 (Deutsch-first)**: deutsche Buch-PDFs sind die primäre Quelle (config sieht `phb-2024-de` bereits vor, Priorität 20); englische Quellen sind Lückenfüller mit niedriger Präzedenz. DDB-Inhalte sind englisch.
- Stub `importer/import_ddb.py`: Konvention `FOLIANT_COBALT` (Env), Proxy-Ansatz, `config [ddb].proxy_url = http://localhost:4000`.
- Betriebsmodell: Import am Mac, `data/foliant.sqlite` aufs Pi kopieren — das Pi serviert nur.

### Extern verifiziert (Abruf 10.07.2026)
- **ddb-proxy** ([github.com/MrPrimate/ddb-proxy](https://github.com/MrPrimate/ddb-proxy)): self-hosted, MIT, 100 % JavaScript (Node, `yarn install && node index.js`, Docker-Verzeichnis vorhanden). Ausdrücklich „cut down, MVP implementation", „no support". Letzte Release v0.0.25 (Feb 2024). **Liefert: Charaktere, Zauber, Items, Monster.** Klassen, Spezies, Hintergründe, Talente, Buch-Fließtext: **nicht enthalten**.
- **ddb-importer**-Doku ([github.com/MrPrimate/ddb-importer](https://github.com/MrPrimate/ddb-importer), [docs.ddb.mrprimate.co.uk](https://docs.ddb.mrprimate.co.uk/docs/faqs/ddb-importer)): Klassen-/Spezies-/Hintergrund-/Talent-Import läuft über MrPrimates **Patreon-Proxy** (Secret ginge an einen Drittserver); der eigene Proxy deckt nur die vier o. g. Typen. Adventure-Import geht nur über den separaten **adventure-muncher** (Foundry-Datenformat, Electron).
- **Cobalt-Cookie** = Session-Äquivalent eines Passworts ([ddb-importer-chrome](https://github.com/mrprimate/ddb-importer-chrome)): niemals teilen/loggen.

### Annahmen (zu prüfen)
- A-1: Der self-hosted Proxy liefert mit gültigem Cobalt die **freigeschalteten Nicht-SRD-Inhalte** der gekauften Bücher (Zauber/Monster/Items) inkl. Quellenbuch-Metadaten zum Filtern. *(Plausibel — genau dafür existiert er — aber erst mit echtem Account beweisbar → risikoreichste Annahme, Spike.)*
- A-2: Reines-JS-Node läuft auf ARM64 (Pi) — praktisch sicher, aber ungetestet; für den Entwurf irrelevant, weil der Export am Mac laufen soll.

### Offene Unbekannte
- Exaktes Antwortschema der Proxy-Endpunkte (Feldnamen, Quellbuch-Tagging) — bestimmt den Transformer; erst im Spike erhebbar.
- Ob DDB-seitige Änderungen (2024-Umstellung) den stagnierenden Proxy (Feb 2024) für einzelne Typen gebrochen haben.

## 2. Nutzerfälle und tatsächlich benötigte Daten

Foliant braucht aus gekauften DDB-Büchern das, was **weder dt. SRD noch Open5e noch deutsche Buch-PDFs** liefern. Realistisch: **Monster-Statblöcke, Zauber und magische Gegenstände aus englischen Zusatzbüchern**. Charakteroptionen (Klassen/Spezies/Talente) kommen Deutsch-first aus den Buch-PDFs — dieselben Bücher, die man auf DDB kaufen würde, besitzt David laut Konzept bevorzugt deutsch. Buch-Fließtext (Regelkapitel) ist über keinen self-hosted-Weg verfügbar.

## 3. Varianten

### V1 — „Kurzlebiger Proxy-Export + Offline-Import über Artefakte" (Empfehlung)
Zwei strikt getrennte Prozesse:

1. **Export (Netz + Secret, kurzlebig, am Mac):** `ddb-proxy` lokal starten (Docker, an `127.0.0.1` gebunden) → neues `importer/export_ddb.py` ruft die Proxy-Endpunkte (spells/items/monsters), Cobalt aus `FOLIANT_COBALT` nur im Prozess-Env → schreibt **Roh-JSON-Artefakte** nach `data/ddb-export/<buch>/…json` (gitignored) → Proxy stoppen. Der Prozess berührt **keine** Foliant-DB.
2. **Import (offline, ohne Secret):** `importer/import_ddb.py` liest NUR die lokalen Artefakte, filtert auf die gewünschten Quellbücher, transformiert nach Markdown (ein Eintrag pro Inhalt, Quelle/Edition Pflicht) und läuft durch die **bestehende A7-Pipeline** (`importiere_markdown`-Regeln: parse-vor-delete, Leer-/Schrumpf-Abbruch, Aufrufer-Transaktion) in eine **Kandidaten-Kopie** der DB; nach `admin check` + Smoke wird die Kandidaten-DB per Datei-Swap aktiv (identisch zum bestehenden Mac→Pi-Kopiermodell).

Eigenschaften: Secret-Lebensdauer = Minuten; Netzprozess und DB-Schreiber physisch getrennt (Artefakt-Grenze, auditierbar); idempotent (Artefakte versionierbar, Re-Import jederzeit offline); Tests komplett mit synthetischen Artefakt-Fixtures möglich; ehrliche Abdeckungsgrenze (keine Charakteroptionen/Fließtexte — B2-Hinweise bleiben korrekt, weil fehlende Optionen wirklich fehlen).

### V2 — „Kein eigener DDB-Pfad" (bewusste Minimal-Vergleichsbasis)
F5-Inhalte ausschließlich über gekaufte **deutsche PDF-Bücher** (Pipeline existiert und ist gehärtet); DDB-Import entfällt. Ehrlichste, wartungsfreie Lösung mit maximaler Deutsch-first-Qualität — **erfüllt aber F5 nicht** (Anforderungsänderung, Eigentümer-Entscheidung nötig) und lässt englische Zusatzbücher ohne PDF-Ausgabe unerschlossen.

### V3 — „Eigener Voll-Extraktor" (Buch-HTML direkt von DDB)
Maximale Abdeckung inkl. Fließtext, aber: undokumentierte Endpunkte selbst reverse-engineeren, hohe Bruchrate bei DDB-Änderungen, tiefer in der ToS-Grauzone, erheblicher Aufwand. Verstößt gegen NF6/P5 („nur so komplex wie nötig") — abgelehnt für v1.

## 4. Bewertung (Kriterien des Auftrags)

| Kriterium | V1 Proxy-Export | V2 kein DDB | V3 Voll-Extraktor |
|---|---|---|---|
| Fachliche Abdeckung (F5) | Zauber/Monster/Items ✔, Optionen/Fließtext ✘ (offen ausgewiesen) | ✘ (F5 unerfüllt) | ✔✔ |
| Datenverlustschutz/Fehlerisolation | ✔✔ (A7-Pipeline + Kandidaten-DB + Artefakte) | ✔✔ | ✔ (gleiche Pipeline möglich) |
| Secret-Sicherheit | ✔✔ (kurzlebig, nur Export-Prozess, localhost-Proxy) | ✔✔ (kein Secret) | ✔ (Secret im eigenen Code, mehr Fläche) |
| Schutz privater Inhalte | ✔ (Artefakte+DB lokal, gitignored; öffentl. Endpoint-Frage bleibt B2) | ✔✔ | ✔ |
| ARM64-Machbarkeit | ✔ (Export am Mac; Pi unberührt) | ✔✔ | ~ (Node ok, aber egal — gleiche Mac-Strategie) |
| Wartbarkeit bei DDB-Änderungen | ✔ (Bruch trifft nur Export; gekapselte Grenze) | ✔✔ | ✘✘ |
| Testbarkeit | ✔✔ (Artefakt-Fixtures, kein Netz in Tests) | ✔✔ | ✔ |
| Nutzer-/Betriebsaufwand | ✔ (Runbook: Proxy an → Export → Import → Swap) | ✔✔ | ✘ |
| Komplexität/Abhängigkeiten | ✔ (ein Node-Container, nur beim Export) | ✔✔ | ✘✘ |
| Reversibilität/Erweiterbarkeit | ✔✔ (Artefakt-Vertrag bleibt, Export-Backend austauschbar) | ✔✔ | ✔ |

## 5. Empfehlung

**V1**, mit ehrlich dokumentierter Abdeckungsgrenze und den nicht verhandelbaren Ergebnissen des Auftrags (kein Laufzeitzugriff, Secrets kurzlebig, Netz-/DB-Trennung, atomare Aktivierung, Mock-Tests). **Vertrauensgrad: mittel-hoch.** Restrisiken: (R1) Annahme A-1 — liefert der Proxy die gekauften Nicht-SRD-Inhalte vollständig? → **risikoreichster Punkt, zuerst per Spike mit echtem Account/Cobalt prüfen (manuelles Gate, Freigabe erforderlich)**; (R2) Antwortschema unbekannt → Transformer erst nach Spike final; (R3) Proxy stagniert seit Feb 2024 → Exit-Strategie: Artefakt-Vertrag hält, Export-Backend austauschbar (V2 bleibt Rückfallebene).
