# Foliant — MVP-Abgleich & Roadmap bis zu echten Nutzern

**Stand: 2026-07-11** · Abgleich des Ist-Stands mit `foliant-anforderungen.md` (Rev. 8) und
`foliant-technisches-konzept.md`, plus Plan bis zur Nutzung durch die eigene Spielrunde.

---

## Kurzfazit

**Der MVP-Funktionsumfang ist erfüllt** und läuft live auf dem Pi — für dich allein bereits
nutzbar. Alle funktionalen Anforderungen (F1–F7, F5b), die Sprach-/Versionslogik und die
Qualitäts-/Betriebsmechanik stehen; die Datenbank-QS ist abgeschlossen (siehe
[QS-Bericht](QS-BERICHT-datenbank.md)). Zwischen „läuft bei mir" und **„meine Runde nutzt es im
Spiel"** liegen aber **drei echte Lücken**, die genau aus dem Anforderungskatalog kommen:

1. **Immersion / Deutsch-first (S10):** Die englischen DDB-Bücher füllen die SRD-Lücken, aber der
   *primäre* Immersions-Hebel — die **offiziellen deutschen 2024-Grundregelwerke als PDF** — ist
   noch nicht importiert. Viel Inhalt (Aasimar, Unterklassen …) kommt derzeit **englisch** + `*`.
2. **Zugang & Recht (NF3/NF4): ✅ ERLEDIGT 11.07.2026** — Geheimpfad + Anthropic-IP-Allowlist
   (Details M3 unten). Der Endpoint ist faktisch privat; eine geleakte URL wäre nur noch über
   Claude nutzbar.
3. **Onboarding & Abnahme (B10/§14):** Es fehlt eine spielerfeste Kurzanleitung; die Abnahme ist
   zu 2/3 gefahren (Schicht 1+2 ✅, `docs/ABNAHME-PROTOKOLL.md`) — offen ist Davids
   3-Fragen-Checkliste (nach Einrichtung des Claude-Projekts).

Der Rest ist da. Die Roadmap unten schließt genau diese Lücken.

---

## 1. Abgleich Anforderung → Ist-Stand

**Legende:** ✅ erfüllt · 🟡 teilweise/zu verifizieren · ⬜ offen (Lücke bis echte Nutzer)

### Funktional (§4)
| Anf. | Inhalt | Status | Anmerkung |
|---|---|---|---|
| F1 | Regeln nachschlagen (Kampf + außerhalb) | ✅ | `foliant_suche_bestand`, FTS5 + bm25, Exact-Name-Boost |
| F2 | Steckbriefe Zauber/Monster/Gegenstand | ✅ | `foliant_hol_*`; Detail vollständig (inkl. DDB-Options-Aggregation) |
| F3 | Charaktererstellung + Build-Prüfung | ✅ | Listen/Details/`foliant_pruefe_build`; DDB-Optionen in Listen |
| F4 | Import eigener PDFs | ✅ | dt. SRD 5.2.1 live; PyMuPDF4LLM + Docling-Fallback |
| F5 | Import DDB-Bücher | ✅ | 8 Bücher live in der bedienten DB (2024 + 2014), Editionen autoritativ |
| F5b | Import Open5e (API, einmalig) | ✅ | srd-2024 als Sofort-Basis |
| F6 | Mischbetrieb der Quellen | ✅ | ein Schema, Präzedenz über `quellen.prioritaet` |
| F7 | Quellenangabe (Quelle immer, Seite wenn vorhanden) | ✅ | in jeder Detailantwort |

### Sprache & Übersetzung (§5)
| Anf. | Inhalt | Status | Anmerkung |
|---|---|---|---|
| S1–S9, S11 | Spieldeutsch, offizielle Begriffe, `*`-Regel, Glossar-Herkunft, robuste Erkennung | ✅ | dnddeutsch-Glossar, `markiere`, NFKD-Normalisierung |
| **S10** | **Deutscher Regeltext PRIMÄR — dt. 2024-Grundregelwerke (PHB/DMG/MM) als PDF** | ⬜ | **größte inhaltliche Lücke:** nur dt. SRD ist da; DDB-Zusatzinhalt ist englisch. Immersions-Hebel #1 |

### Regelversionierung (§6)
| Anf. | Inhalt | Status | Anmerkung |
|---|---|---|---|
| V1–V6, V8 | Version Pflicht, 2024-Standard, Altstand markiert, keine stille Mischung | ✅ | `edition NOT NULL`, 0 Editions-Abweichungen (QS) |
| V7 | Erweiterbares Versionsschema | 🟡 | `edition` ist ein Textfeld (2024/2014) — reicht heute, feinere Granularität (Errata/Druck) bei Bedarf nachrüstbar ohne Migration |

### Nicht-funktional (§7)
| Anf. | Inhalt | Status | Anmerkung |
|---|---|---|---|
| NF1 | Self-hosted | ✅ | Raspberry Pi 4, Docker |
| NF2 | Zugang über Claude-Connector (Free = 1 Connector) | ✅ | `https://dnd.magnetron.me/mcp` |
| **NF3** | **Privat, keine öffentliche Bereitstellung** | ✅ | Geheimpfad + IP-Allowlist (11.07.2026, verifiziert); Rest-Risiko = URL-Weitergabe, dokumentiert |
| **NF4** | Legale Quellen; DDB nur privat | 🟡 | SRD/Open5e frei; DDB bewusst akzeptiert — aber „mit der Runde teilen" ist ein Schritt über „privat" hinaus (Entscheidung, s. u.) |
| NF5–NF7 | Kosten nur Strom, einfach, erweiterbar | ✅ | Open Source, ein Schema, Ausbaustufen andockbar |
| NF8 | Einfache Ersteinrichtung | 🟡 | technisch ja; **spielerfeste Anleitung fehlt** (→ B10) |

### Verhalten aus Spielersicht (§13)
| Anf. | Inhalt | Status | Anmerkung |
|---|---|---|---|
| B1–B8 | Geerdet, Lücken ehrlich, zweisprachig, Mehrdeutigkeit, Altstand einordnen, Umfang ablehnen, 2024-Reihenfolge, Erwartungen setzen | ✅ | über `config/stil.py` (3 Kanäle) + Tool-Grounding + Build-Prüfung; Spot-Check sauber |
| **B9** | Schnell & verfügbar im Spielbetrieb | 🟡 | Antwortzeiten/Uptime im Sessionlast-Fall **noch nicht formal gemessen** |
| **B10** | Spielerfeste Einrichtung + Fallback | ⬜ | **Kurzanleitung + Fallback für Mitspieler fehlen** |

### Abnahme (§14) & Betrieb (§15)
| Anf. | Inhalt | Status | Anmerkung |
|---|---|---|---|
| T1,T3–T9,T11 | Automatisierte Abnahmetests | ✅ | pytest grün (81/4-skip) |
| **T2/T10/T12** | Verhaltenstests (Grounding, Umfang, Bau-Reihenfolge) | 🟡 | Schicht 1+2 ✅ (pytest + live); Schicht 3 = Davids 3-Fragen-Checkliste (`ABNAHME-PROTOKOLL.md`) |
| O1 | Backup & Wiederherstellung | ✅ | Backup-Rotation (11→3 verifiziert); Restore ohne Re-Import |
| O2 | Inhalte nachträglich importieren | ✅ | `admin import` / `ddb-import-all`, gleiche Pflicht-Versionierung |
| O3 | Import-Qualitätsprüfung vor Freigabe | ✅ | `admin check` erweitert + Smoke |
| **O4** | Feedback-/Korrekturschleife | ⬜ | **kein Meldeweg für schlechte Treffer** |
| O5 | Secrets sicher (Cobalt server-seitig, erneuerbar) | ✅ | nur server-seitig; Betrieb läuft ohne Cobalt |

**Technischer Abgleich (Konzept):** Architektur deckt sich (FastMCP, SQLite/FTS5, Cloudflare
Named Tunnel, Pi/Docker). Der DDB-Import (im Konzept „Phase 3") ist **umgesetzt**. **Eine
Konzept-Prämisse ist überholt:** „Authless ist ok, weil read-only auf *öffentlichen* Daten ohne
private Inhalte" galt für Phase 0–2 — mit den privaten DDB-Inhalten stimmt die Begründung nicht
mehr, deshalb die Zugangs-Entscheidung unten.

---

## 2. Die Lücken bis „echte User" (verdichtet)

1. **Immersion (S10):** deutsche 2024-Grundregelwerke als PDF importieren → Deutsch-first für den
   vollen Inhalt statt Englisch-Fallback.
2. ~~Zugangskontrolle~~ ✅ erledigt (Geheimpfad + IP-Allowlist).
3. **Onboarding (B10/NF8):** spielerfeste Connector-Anleitung + Fallback.
4. **Formale Abnahme (§14):** nur noch Schicht 3 (Davids 3 Chat-Fragen) offen.
5. **Betriebssicherheit (B9/O1):** Antwortzeit + Uptime für Sessions; Off-Site-Backup.
6. **Feedback (O4):** einfacher Meldeweg für schlechte Treffer.
7. **Rest-Politur:** DDB-Detail-Fragmente in der Suche, Drop-Cap-Namen (niedrig; QS-Bericht §2).

---

## 3. Roadmap in Phasen (mit Gates)

> Jede Phase hat ein **Gate** = nachweisbares Ergebnis, bevor die nächste beginnt. Die Phasen sind
> weitgehend unabhängig; Reihenfolge nach Wirkung auf „echte Nutzer".

### M1 — Inhaltliche Reife / Immersion  ·  *Hebel #1, Aufwand: mittel*
- **Ziel:** Deutsch-first für den vollen 2024-Inhalt (S10), nicht nur SRD.
- **Aufgaben:** offizielle **dt. PHB/DMG/MM 2024 als PDF** importieren (gleiche Pipeline wie dt.
  SRD: PyMuPDF4LLM + Chunker + Editions-Tag 2024 + Präzedenz vor DDB-Englisch/Open5e). Chunking an
  den echten Seiten justieren; `admin check` + Smoke; Stichprobe (O3).
- **Entscheidungsbedarf:** **Hast du diese PDFs?** Wenn nein, bleibt DDB-Englisch der Stand (S10-
  Fallback, legitim) — dann ist M1 optional und die Roadmap springt zu M2.
- **Update 11.07.2026 — Scans sind jetzt importierbar:** Die meisten vorhandenen PDFs sind
  gescannt (keine Textschicht). Dafür ist die **OCR-Vorstufe umgesetzt** (`admin pdf-triage` →
  `admin ocr-pdf`, OCRmyPDF/Tesseract deu+eng auf dem Pi; Guardrail verhindert Rumpf-Importe;
  Ablauf: `docs/DEPLOY-raspberry-pi.md` §„Gescannte PDFs"). M1 läuft damit pro Buch:
  Triage → OCR → Import → O3-Stichprobe → Chunking-Justage. Qualitätserwartung: gut für
  Fließtext, Statblöcke/Tabellen brauchen Nacharbeit.
- **Gate:** dt. Kernbegriffe/Optionen (z. B. Aasimar) kommen **deutsch** aus dem Bestand; deutsche
  Quelle rankt vor DDB-Englisch.

### M2 — Formale MVP-Abnahme  ·  *Schicht 1+2 ✅ bestanden 11.07.2026 · Schicht 3 (3 Chat-Fragen) offen*
- **Ziel:** „fertig" nach §14 nachgewiesen — gegen den *aktuellen* (DDB-geladenen) Bestand.
- **Aufgaben:** T2/T10/T12 als **manuelle Checkliste im Connector** durchspielen (Grounding bei
  Nicht-Bestand, Umfangs-Ablehnung „Wie besiege ich Strahd?", 2024-Bau-Reihenfolge). Automatisierte
  T1/T3–T9/T11 laufen ohnehin grün. Befunde → Fixes.
- **Gate:** alle T1–T12 nachweislich erfüllt (Kurzprotokoll im Repo).

### M3 — Zugang & Betrieb für die Gruppe  ·  *Zugang ✅ umgesetzt 11.07.2026 · Betrieb offen*
- **Ziel:** privat + erreichbar + verlässlich (NF3/NF4/B9/O1).
- **Zugang: ✅ UMGESETZT** — **Geheimpfad** (`/<token>/mcp`, die URL ist der Schlüssel;
  Rotation = Token in `.env` ändern + rebuild + neue URL teilen) **+ IP-Allowlist** der
  Anthropic-Egress-Ranges im Server (`app/zugriff.py`, geprüft an der Edge-gesetzten
  `CF-Connecting-IP`). Von außen verifiziert: Fremd-IPs bekommen für jeden Pfad außer
  `/health` einheitlich **403** (kein Pfad-Orakel); lokale Aufrufe/Healthcheck unberührt.
  Eine geleakte URL wäre nur noch **über Claude** nutzbar, nie direkt. Details + optionales
  Cloudflare-Edge-Upgrade: `docs/DEPLOY-raspberry-pi.md` §5b. *(Cloudflare Access mit
  Service-Token schied aus: Claude-Connectors können keine Custom-Header senden.)*
- **Betrieb:** Container-Autostart/Restart-Policy prüfen; **Health-Monitoring** (z. B. Uptime-Ping
  auf `/health`); **Off-Site-Backup** der SQLite-Datei (O1: Kopie außerhalb des Pi); Antwortzeiten
  unter Last messen (B9).
- **Gate:** Endpoint privat gemäß gewählter Variante; Dienst übersteht Neustart; Backup liegt
  außerhalb des Pi; Nachschlagen antwortet zügig.

### M4 — Onboarding & Pilot-Session  ·  *Aufwand: klein*
- **Ziel:** ein realer Mitspieler nutzt Foliant in einer echten Session (B10/NF8/B9).
- **Aufgaben:** **spielerfeste Kurzanleitung** (Connector-URL eintragen, aktivieren, Beispiel-
  fragen; Fallback-Hinweis, da Custom Connectors Beta) — als `docs/`-Seite und/oder 1-Pager.
  Eine **Pilot-Session** mit 1–2 Spielern; Bau eines Charakters + In-Game-Regelfragen live.
- **Gate:** ein nicht-technischer Mitspieler verbindet sich eigenständig und nutzt es im Spiel.

### M5 — Feedback & Iteration  ·  *laufend*
- **Ziel:** schlechte Treffer/Falschauskünfte einsammeln und nachziehen (O4).
- **Aufgaben:** einfacher Meldeweg (z. B. eine Notiz-Datei/`admin`-Kommando „merke schlechten
  Treffer" oder ein geteiltes Dokument); daraus iterativ Synonyme/Chunking/Korrekturen. Die aus der
  QS bekannten Rest-Posten (DDB-Detail-Suchrauschen, Drop-Cap-Namen) hier mitziehen.
- **Gate:** kein hartes Gate — Dauerbetrieb mit Rückkopplung.

---

## 4. Offene Entscheidungen für dich

Diese drei Punkte steuern die Roadmap und sind **deine** Entscheidungen:

1. **Deutsche 2024-Bücher (M1):** Hast du PHB/DMG/MM 2024 als PDF zum Import? → bestimmt, ob wir den
   Immersions-Hebel ziehen oder beim DDB-Englisch-Fallback bleiben.
2. **Zugangsmodell (M3):** Cloudflare Access (Token) · IP-Allowlist · bewusst authlos? → bestimmt
   die Absicherung, bevor die URL an Mitspieler geht.
3. **DDB-Inhalt teilen (NF4):** Mitspieler greifen dann auf deine DDB-Buchkopien zu (über „privat für
   dich" hinaus). Du hast das Serving bereits bewusst gewählt; für *mehrere* Nutzer ist es eine
   eigene, bewusst zu treffende ToS-/Recht-Entscheidung.

---

## 5. Nach dem MVP (§9 — nur vorgemerkt)

DDB-**Charakter**-Abruf (A1) · Kampagnenspezifik (A2) · Rollen SL/Spieler + Spoiler-Isolation (A3) ·
Hausregeln-Overlay (A4). Alle bewusst außerhalb dieses Plans; sie docken laut Schema/Architektur
ohne Neuaufbau an (NF7).

---

## Zusammengefasst

Der MVP **kann alles, was er laut Katalog können muss**. Bis „echte User" fehlen im Kern **drei
Dinge**: deutsche Bücher (Immersion), ein privater Zugang (Recht/Sicherheit) und spielerfestes
Onboarding — flankiert von formaler Abnahme, Betriebssicherheit und einer Feedback-Schleife.
Reihenfolge nach Wirkung: **M2 (Abnahme, klein)** und **M3 (Zugang, kritisch)** sind die schnellsten
Schritte Richtung Gruppennutzung; **M1 (deutsche Bücher)** ist der größte Qualitäts-Hebel, sobald
die PDFs vorliegen.
