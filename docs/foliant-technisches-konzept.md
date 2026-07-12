# Foliant — Technisches Konzept (Architektur & Umsetzung)

**D&D-5e-Regelassistent (Fassung 2024), Deutsch-first · self-hosted MCP-Server · Stand: 08.07.2026**

> **Rolle im Dokumentensatz:** Dies ist die **technische Sicht** auf Foliant (Architektur,
> Datenmodell, Pipeline, Deployment, Entscheidungen). Die **fachliche Sicht** (was Foliant können
> muss) steht in `foliant-anforderungen.md`; die **Bauanleitung für Claude Code** in `CLAUDE.md`.

---

## 1. Überblick
Foliant ist ein privat betriebener MCP-Server (Model Context Protocol), der Claude zum
deutschsprachigen **Regel-Nachschlagewerk für D&D 5e (Fassung 2024)** macht: Regeln nachschlagen
(Kampf + außerhalb), Steckbriefe (Zauber/Monster/Gegenstände) und Unterstützung bei der
Charaktererstellung. Antworten in korrektem Spieldeutsch, **geerdet auf importierte Quellen**, mit
Quelle und Regelversion (Seite, wenn die Quelle eine hat). **Kein Netz zur Laufzeit** — alles lokal.

---

## 2. Architektur

```
IMPORT (einmalig/gelegentlich)                         LAUFZEIT (dauerhaft)
────────────────────────────────                       ─────────────────────────────
Dt. SRD 5.2.1 (PDF) ─┐                                  Claude (Client, Mobile/Desktop)
Engl. SRD (Markdown) ─┤  PyMuPDF4LLM/Docling                     │  https://…/<geheimpfad>/mcp
Eigene dt. PDFs ──────┤────────────────► Markdown                ▼
Open5e (API) ─────────┤  Transform      ─► Chunks       Cloudflare Tunnel + IP-Filter/Pfad
DDB-Bücher (Exporter) ─┘                     │                    │
dnddeutsch-API ─────────────► Glossar       ▼                    ▼
                                       SQLite + FTS5  ◄──── FastMCP-Tools (uvicorn ASGI)
                                            ▲                    (nur lokale Abfragen)
                        Admin-CLI ──────────┤
                        Datasette (127.0.0.1, read-only, SSH-Tunnel)
```

Zwei klar getrennte Ebenen:
- **Import:** Quellen → Markdown/JSON → Chunks → SQLite. Netz nur hier. Läuft im Container auf dem
  Pi (oder bei Bedarf auf einem stärkeren Rechner, dann nur die fertige DB rüberkopieren).
- **Laufzeit:** FastMCP serviert die Werkzeuge über HTTP (uvicorn) hinter einem Cloudflare Named
  Tunnel. Nur lokale SQLite-Abfragen — **offline, schnell, geerdet**.

---

## 3. Tech-Stack

| Baustein | Wahl | Rolle |
|---|---|---|
| MCP-Framework | **FastMCP** 2.14.7 | Tools + `http_app(path="/mcp", stateless_http=True)` |
| ASGI-Server | **uvicorn** | serviert `app.server:app` |
| Datenbasis/Suche | **SQLite + FTS5** | Volltext, bm25, eine Datei |
| PDF→Markdown | **PyMuPDF4LLM** (Standard), **Docling** (Fallback) | Ingestion |
| Deutsch-Glossar | **dnddeutsch.de-API** | offizielle Begriffe (Ulisses) |
| Weitere Quelle | **Open5e-API** (v2) | engl. Sofort-Basis (Zauber/Monster/Hintergründe) |
| Container | **Docker + docker compose** | Isolation + ARM64-Portabilität |
| Erreichbarkeit | **cloudflared** (Named Tunnel) | Geheimpfad + IP-Allowlist (`app/zugriff.py`) |
| Daten-Inspektion | **Datasette** (optional, lokal) | read-only Admin-Blick |

---

## 4. Datenmodell
Schema: `db/schema.sql` (getestet). Kernprinzip: **Datenshape über alle Quellen vereinheitlichen,
Provenienz (Quelle/Edition/Seite) sichtbar behalten.**

- **`quellen`** — Register aller Quellen: `edition` (2024/2014, **NOT NULL**), `sprache`, `herkunft`
  (pdf/ddb/srd-md/open5e/manuell), `lizenz`, `prioritaet` (Dubletten-Präzedenz; kleiner = Vorrang).
- **`eintraege`** — Inhalts-Chunks (Rückgrat): `kategorie`, `name_de`/`name_en`, `edition`
  (**NOT NULL** → kein verwaister Inhalt), `seite` (optional), `body_md`. FK-Cascade von `quellen`.
- **`zauber_meta`/`monster_meta`/`gegenstand_meta`** — strukturierte Filterfelder. **In Phase 1
  nicht befüllt** (Suche läuft über FTS + Kategorie); erst nachrüsten, wenn ein Filter-Tool sie braucht.
- **`glossar`** — DE↔EN: `term_de` (kanonisch), `offiziell` (1 → kein `*`, 0 → `*`), `quelle`,
  `edition_quelle`. Grundlage für Begriffswahl und `*`-Kennzeichnung.
- **`eintraege_fts`** — FTS5 (external-content) über `name_de, name_en, body_md`, Tokenizer
  `unicode61 remove_diacritics 2`, plus **drei Trigger** (INSERT/UPDATE/DELETE) für Synchronität.

**Getestet:** Trigger feuern, bm25 rankt, `edition NOT NULL` greift, Cascade-Delete lässt die FTS
sauber. Als Vorsichtsmaßnahme wird nach jedem Import `rebuild` ausgeführt (siehe §11).

---

## 5. Ingestion-Pipeline („alles wird zu Markdown")
Jede Quelle wird zuerst nach Markdown normalisiert, danach **eine** Pipeline (Chunker → SQLite).

- **Quellen:** dt. SRD-PDF (Primär Deutsch), engl. SRD-Markdown, eigene dt. PDFs, **Open5e** (API,
  engl., CC/OGL), DDB-Bücher (Exporter). Alle **einmalige** Importe — kein Laufzeit-API-Aufruf.
- **PDF → Markdown:** PyMuPDF4LLM (Standard, ARM-tauglich), Docling (Fallback für Tabellen/Statblöcke,
  auf ARM zäh). **OCR-Vorstufe für gescannte PDFs** (umgesetzt 11.07.2026): `admin pdf-triage`
  erkennt Scans (Textschicht-Zählung pro Seite), `admin ocr-pdf` (OCRmyPDF/Tesseract, deu+eng)
  legt die Textschicht nach `data/ocr/`, danach normale Pipeline; ein Guardrail lehnt mehrheitlich
  textlose PDFs beim Import ab (Q3/O3), statt eine Rumpf-Quelle zu schreiben.
- **Chunking:** **ein logischer Eintrag pro Zeile** (ein Zauber / ein Monster / ein Regelabschnitt),
  heading-basiert. Der zentrale Qualitätshebel — iterativ an echten PDFs justieren.
- **Versionierung:** `edition` ist Pflicht (Schema erzwingt es). Quelle/Seite als First-Class-Felder.
- **Glossar:** aus dnddeutsch-API (offiziell = `name_de_ulisses`; Wildcard nur hinten; >30 Treffer = Fehler).
- **Dubletten/Präzedenz:** über `quellen.prioritaet` (deutsche Quellen vor Open5e).
- **Nach Import:** FTS neu aufbauen (`rebuild`).

---

## 6. Suche & Deutsch-Logik
- **FTS5 + bm25**, mit **Exact-Name-Boost vor Substring** („Feuerball" vor „Verzögerter Feuerball").
- **Zweisprachig fast geschenkt:** `name_de` und `name_en` sind beide indexiert → deutsche und
  englische Begriffe treffen denselben Eintrag. Das Glossar überbrückt nur den *Suchbegriff*, wenn er
  im Eintrag nicht vorkommt.
- **Edition-Default 2024;** ältere Stände nur als klar markierter Zusatz (keine stille Mischung).
- **Begriffs-Leiter (Deutsch):** aktuelles offizielles Deutsch 2024 (dt. SRD, dt. Grundregelwerke)
  → offizielles Deutsch aus Altbüchern + Ulisses-Glossar → inoffiziell (`*`) → keins (`*`).
  Englisches Original **immer** in Klammern; `*` bei fehlendem offiziellen Begriff.
- **Immersion:** deutscher Regeltext hat Vorrang (deutsche Quellen importieren); Englisch +
  Begriffs-Annotation nur als Fallback für rein englische Inhalte.

---

## 7. MCP-Tools
Namensschema `foliant_<verb>_<nomen>` (kollisionsfrei neben anderen Connectoren). Suche liefert
**knappe** Treffer, Detail-Tools die volle Ausgabe.

- **Nachschlagen:** `foliant_suche_regeln`, `foliant_hol_regel`, `foliant_hol_zauber`,
  `foliant_hol_monster`, `foliant_hol_gegenstand`, `foliant_uebersetze_begriff`.
- **Charaktererstellung:** `foliant_liste_klassen|spezies|hintergruende|talente`,
  `foliant_hol_klasse|spezies|hintergrund|talent`, `foliant_hol_attributswerte`,
  `foliant_pruefe_build`.
- **Status:** `/health`.

**Arbeitsteilung:** Der Server liefert Daten, Suche und Validierung; **Claude führt das Gespräch**.
Die Verhaltensregeln (Grounding, Deutsch-first, `*`-Regel, Umfangs-Ablehnung, 2024-Bau-Reihenfolge)
liegen als Instruktionstext in `config/stil.py`.

---

## 8. Deployment
- **Raspberry Pi 4 (64-bit)**, containerisiert (Docker + compose). uvicorn serviert `app.server:app`.
- **Cloudflare Named Tunnel** → `dnd.magnetron.me/<geheimpfad>/mcp`. **Kein OAuth** (Claude-
  Connectors können keine Custom-Header senden); Zugang seit 11.07.2026 über **Geheimpfad**
  (URL = Schlüssel, Token in der Pi-`.env`) **+ IP-Allowlist** auf Anthropics Egress-Ranges
  (`app/zugriff.py`, geprüft an `CF-Connecting-IP`) — nötig, seit private DDB-Inhalte
  serviert werden. Fremd-IPs erhalten für jeden Pfad außer `/health` einheitlich 403.
- **Alles auf dem Pi:** Import läuft im Container mit (PyMuPDF4LLM ok auf ARM; Docling nur bei Bedarf).
- **Umzug auf Apple-Silicon-Mac mini** 1:1 (beide ARM64, gleiches `Dockerfile`/`compose`).
- **DB-Journal DELETE** (Bind-Mount-kompatibel). `.dockerignore` hält Daten/PDFs aus dem Image.

---

## 9. Admin & Betrieb
Bewusst **kein öffentliches Web-Panel** (Angriffsfläche auf dem getunnelten Pi). Zwei **lokale** Wege:
- **Admin-CLI** (`app/admin.py`): `status` (fertig & getestet), `import`, `reindex-fts`, `check`
  — via `docker compose exec foliant python -m app.admin …`.
- **Datasette** (read-only, an `127.0.0.1`, Zugriff per SSH-Tunnel) für die Import-Kontrolle.
- **Backup:** SQLite-Datei sichern; Wiederherstellung ohne Re-Import. Aktualisierte DB einspielen =
  Datei kopieren + `restart`.

---

## 10. Sicherheit
- Laufzeit **offline**, read-only auf öffentlichen/legal erworbenen Daten.
- Admin-Funktionen **nie** über den Tunnel — nur lokal/SSH.
- Secrets (Cobalt-Cookie, Tunnel-Token) **nur server-seitig** via `.env` (gitignored).
- DDB-Inhalte **nur privat** (ToS-Grauzone), nie weitergeben. SRD-Attribution (CC-BY) mitführen.

---

## 11. Qualität & Robustheit
- **Anti-Halluzination (B1):** nur aus dem Bestand antworten, sonst „nicht gefunden" — nicht 100 %
  technisch erzwingbar (Claude formuliert die Prosa), daher stehender Test **T2**.
- **Version immer sichtbar;** keine stille 2014/2024-Mischung.
- **Import-Qualitätsprüfung** (Stichproben, O3) vor Freigabe; **FTS `rebuild`** nach jedem Import.
- **Abnahmekriterien T1–T12** + Smoke-Test (inkl. Deutsch-Term-Check).
- **Getestet:** FTS-Trigger, bm25-Ranking, `edition NOT NULL`, Cascade-Delete-Konsistenz,
  `markiere`-`*`-Regel, 2024-Point-Buy, Admin-`status`.

---

## 12. Wichtige technische Entscheidungen (Kurz-Log)

| Entscheidung | Warum |
|---|---|
| **Geheimpfad + IP-Allowlist statt OAuth** | Claude-Connectors können keine Header senden; Server-seitiger Filter ist versioniert/testbar; OAuth wäre für <5 Nutzer überdimensioniert |
| **Ein internes Schema für alle Quellen** | einheitlicher Tool-Output; Provenienz bleibt sichtbar |
| **meta-Tabellen Phase 1 nicht befüllen** | spart Importer-Aufwand, streicht kein Feature |
| **Build-Prüfung minimal** | wenige klare Checks statt vollständiger Regel-Engine |
| **DELETE-Journal** | Kompatibilität mit Bind-Mount-Volumes (Container) |
| **Alles auf dem Pi (Auslagern optional)** | Ein-Geräte-Wunsch; PyMuPDF4LLM ist ARM-tauglich |
| **Docker** | Mehrprojekt-Isolation + ARM64-Portabilität (Pi → Mac mini) |
| **Kein Runtime-Cache** | lokales FTS5 ist schneller als jeder Cache-Layer |
| **Seite optional, Quelle Pflicht** | API-Quellen (Open5e) haben keine Seiten; entlastet auch das PDF-Parsing |

---

## 13. Iterative Stellen (nicht „one-shot" mit Claude Code)
Datenabhängig, an echten PDFs mit Claude Code zu justieren: **Chunking**, **deutsches Such-Tuning**
(Komposita/Umlaute), **PDF-Parse-Kontrolle**. Der Rest (Server, Config, DB-Schicht, Tools, Importer,
Docker, Admin) ist Standardarbeit.

---

## 14. Ausbaustufen (nach dem MVP)
DDB-Charakterabruf · Kampagnenspezifik · Rollen Spielleiter/Spieler + strukturelle Spoiler-Isolation
· Hausregeln-Overlay · universelle Quersuche · DM-Term-Override · OCR (bei gescannten PDFs).

---

## 15. Zugehörige Dokumente
`foliant-anforderungen.md` (fachlich, Rev. 8) · `CLAUDE.md` (Bauanleitung + Leitplanken) ·
`db/schema.sql` (Schema) · `docs/DEPLOY-raspberry-pi.md` (Deployment) ·
`docs/foliant-mcp-best-practices.md` (Best Practices) · `docs/ATTRIBUTION.md` (Lizenzen) ·
`README.md` (Kurzüberblick). Wegweiser: `PROJEKT-UEBERSICHT.md`.
