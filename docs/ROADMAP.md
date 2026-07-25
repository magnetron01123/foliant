# Foliant — Status & Roadmap

**Stand: 25.07.2026** · Was fehlt zwischen „läuft" und „meine Runde nutzt es im Spiel".
Abgleichbasis: `foliant-anforderungen.md` (Rev. 8).

## Kurzfazit

**Der MVP-Funktionsumfang ist erfüllt und live.** Alle funktionalen Anforderungen (F1–F7,
F5b), die Sprach-/Versionslogik und die Qualitäts-/Betriebsmechanik stehen; die Datenbank-QS
ist abgeschlossen. Zusätzlich läuft der **Charakterbogen-Übersetzer** als eigene Website
(`docs/CHARAKTERBOGEN-MVP.md`).

Offen sind noch **vier** Punkte, alle klein bis mittel:

1. **M2 Schicht 3** — Davids 3-Fragen-Checkliste im Chat (`ABNAHME-UND-EVAL.md`).
2. **M3 Betrieb** — Uptime-Monitoring; Off-Site-Spiegel der Backups einrichten.
3. **M4 Onboarding** — spielerfeste Kurzanleitung für den **MCP-Connector**
   (die Website hat mit `CHARAKTERBOGEN-ANLEITUNG-RUNDE.md` bereits eine).
4. **M1 Immersion** — deutsche 2024-Grundregelwerke importieren, sobald PDFs vorliegen.

---

## 1. Anforderungen → Ist-Stand (nur was nicht ✅ ist)

**Erfüllt und nicht weiter aufgeführt:** F1–F7 + F5b (Funktion), S1–S9/S11 (Sprache),
V1–V6/V8 (Version), NF1–NF3/NF5–NF7 (nicht-funktional), B1–B8 (Verhalten),
T1–T9/T11 (Abnahme automatisiert), O1–O3/O5 (Betrieb).

| Anf. | Inhalt | Status | Anmerkung |
|---|---|---|---|
| **S10** | Deutscher Regeltext primär (dt. 2024-Grundregelwerke als PDF) | ⬜ | **größte inhaltliche Lücke:** nur dt. SRD ist da; DDB-Zusatzinhalt ist englisch + `*`. Immersions-Hebel #1 → M1 |
| V7 | Erweiterbares Versionsschema | 🟡 | `edition` ist ein Textfeld (2024/2014) — reicht heute; feinere Granularität (Errata/Druck) ohne Migration nachrüstbar |
| NF4 | Legale Quellen; DDB nur privat | 🟡 | SRD/Open5e frei; DDB bewusst akzeptiert. „Mit der Runde teilen" ist ein Schritt über „privat" hinaus — protokollierte Eigentümer-Entscheidung (`ATTRIBUTION.md`) |
| NF8 | Einfache Ersteinrichtung | 🟡 | technisch ja; **spielerfeste Connector-Anleitung fehlt** → M4 |
| B9 | Schnell & verfügbar im Spielbetrieb | 🟡 | Antwortzeiten/Uptime unter Sessionlast **noch nicht formal gemessen** → M3 |
| B10 | Spielerfeste Einrichtung + Fallback | ⬜ | → M4 |
| T2/T10/T12 | Verhaltenstests (Grounding, Umfang, Bau-Reihenfolge) | 🟡 | Schicht 1+2 ✅; Schicht 3 = Checkliste → M2 |
| O4 | Feedback-/Korrekturschleife | ⬜ | kein Meldeweg für schlechte Treffer → M5 |

---

## 2. Roadmap (mit Gates)

> Jede Phase hat ein **Gate** = nachweisbares Ergebnis. Die Phasen sind weitgehend
> unabhängig; Reihenfolge nach Wirkung auf echte Nutzer.

### M2 — Formale MVP-Abnahme · *Schicht 1+2 ✅ (11.07.2026) · Schicht 3 offen*
T2/T10/T12 als manuelle Checkliste im Connector durchspielen (`ABNAHME-UND-EVAL.md`,
Schicht 3). Voraussetzung: Claude-Projekt eingerichtet (`CLAUDE-PROJEKT-ANWEISUNG.md`).
**Gate:** alle T1–T12 nachweislich erfüllt, Ergebnisse im Protokoll eingetragen.

### M3 — Zugang & Betrieb für die Gruppe · *Zugang ✅ (11.07.2026) · Betrieb teilweise*
- **Zugang ✅:** Geheimpfad (`/<token>/mcp`) + IP-Allowlist auf Anthropics Egress-Ranges
  (`app/zugriff.py`, geprüft an `CF-Connecting-IP`). Von außen verifiziert: Fremd-IPs
  bekommen für jeden Pfad außer `/health` einheitlich 403 (kein Pfad-Orakel). Eine
  geleakte URL wäre nur noch **über Claude** nutzbar. *(Cloudflare Access mit Service-Token
  schied aus: Claude-Connectors können keine Custom-Header senden.)*
- **Backup ✅ (Werkzeug):** `admin backup` erstellt ein konsistentes, verifiziertes
  Online-Backup mit Rotation (`RUNBOOK.md` §6).
- **Offen:** Cron + **Off-Site-Spiegel** einrichten (das Spiegeln ist die eigentliche
  Sicherung); externes **Uptime-Monitoring** auf `/health`; Antwortzeiten unter Last messen (B9).

**Gate:** Backup liegt außerhalb des Pi, Dienst übersteht Neustart, Monitoring meldet Ausfälle.

### M4 — Onboarding & Pilot-Session · *Aufwand: klein*
Spielerfeste Kurzanleitung für den **MCP-Connector** (URL eintragen, aktivieren,
Beispielfragen, Fallback-Hinweis — Custom Connectors sind Beta). Muster und Tonfall:
`CHARAKTERBOGEN-ANLEITUNG-RUNDE.md`. Danach eine Pilot-Session mit 1–2 Spielern.
**Gate:** ein nicht-technischer Mitspieler verbindet sich eigenständig und nutzt es im Spiel.

### M1 — Inhaltliche Reife / Immersion · *Hebel #1, wartet auf PDFs*
Offizielle dt. PHB/DMG/MM 2024 importieren: gleiche Pipeline wie der dt. SRD, Editions-Tag
2024, Präzedenz vor DDB-Englisch/Open5e. Sind die PDFs gescannt, läuft je Buch
Triage → OCR → Import → Stichprobe → Chunking-Justage (`DEPLOY-raspberry-pi.md`).
Qualitätserwartung ehrlich: gut für Fließtext, Statblöcke/Tabellen brauchen Nacharbeit.
**Entscheidungsbedarf:** Liegen die PDFs vor? Wenn nein, bleibt DDB-Englisch der Stand
(legitimer S10-Fallback) und M1 ruht.
**Gate:** dt. Kernbegriffe/Optionen (z. B. Aasimar) kommen **deutsch** aus dem Bestand;
deutsche Quelle rankt vor DDB-Englisch.

### M5 — Feedback & Iteration · *laufend*
Einfacher Meldeweg für schlechte Treffer (O4), daraus iterativ Synonyme/Chunking/
Korrekturen. Die Rest-Posten unten hier mitziehen. **Kein hartes Gate.**

---

## 3. Bekannte Rest-Posten (bewusst niedrig priorisiert)

Aus der abgeschlossenen Datenbank-QS (11.07.2026) und dem Tiefen-Audit der DDB-Druck-Bücher.
Alles dokumentiert, nichts davon blockiert die Runde.

| Fund | Schwere | Warum offen gelassen |
|---|---|---|
| `Aasimar Traits` u. Ä. erscheinen als eigene **Such**treffer (die Detail-Auskunft ist vollständig) | niedrig | echter, suchbarer Inhalt; die Option rankt zuerst — Ausblenden verschlechterte die Suche |
| srd-de Drop-Cap-Namen (`wAffen`, `zAuber`) | niedrig | rein kosmetisch (Inhalt korrekt); Case-Heuristik an der Hauptquelle wäre risiko-unverhältnismäßig |
| 2014-Sub-Fragmente in DDB-Kategorien (z. B. „X Traits") | niedrig | erreichen die strikt-2024-Listen nie; Suche rankt echte Optionen zuerst |
| ~30 kosmetische Inline-Kapitälchen-Reste + vereinzelte OCR-Garbles in den Druck-Büchern | niedrig | Inhalt korrekt; Kreuz-Audit bestätigte Würfelwerte 65/65 und GP-Preise 86/87 |
| Body-Dubletten (Kampfstile je Klasse) | keine | **kein Fehler** — legitime klassenspezifische Instanzen |

---

## 4. Nach dem MVP (nur vorgemerkt)

DDB-**Charakter**-Abruf (A1) · Kampagnenspezifik (A2) · Rollen SL/Spieler + strukturelle
Spoiler-Isolation (A3, SYN-P3-001) · Hausregeln-Overlay (A4, SYN-P3-004) ·
Regelbeziehungsgraph (SYN-P3-002) · Errata-Tracking (SYN-P3-003). Alle bewusst außerhalb
dieses Plans; sie docken laut Schema/Architektur ohne Neuaufbau an (NF7).
