# Foliant — MVP-Abnahmeprotokoll (§14, T1–T12)

**Datum:** 2026-07-11 · **Prüfling:** Live-System (bediente DB auf dem Pi, ~9490 Einträge,
12 Quellen, Zugang über Geheimpfad + IP-Allowlist) · **Referenz:** `foliant-anforderungen.md`
Rev. 8, §14. Dies ist das M2-Gate der Roadmap.

Drei Prüfschichten:
1. **Automatisiert** (pytest, `tests/test_abnahme.py`) — Server-Logik.
2. **Live-Serverprüfung über den echten Connector** (Anthropic-Cloud → IP-Filter →
   Geheimpfad → Pi) — die Grounding-Signale der Tool-Ausgaben.
3. **Manuelle Verhaltensprüfung im Claude-Chat** (T2/T10/T12) — Claudes Verhalten ist
   nicht in pytest prüfbar (Review-Erkenntnis, Modul-Doku `test_abnahme.py`).

---

## Schicht 1+2: Ergebnis (11.07.2026)

| Test | Kriterium | Schicht | Ergebnis |
|---|---|---|---|
| T1 | Antwort mit Quelle + Regelversion (Seite wenn vorhanden) | pytest | ✅ PASS |
| T2 | Nicht im Bestand → ehrliches „nicht gefunden" | pytest **+ live** | ✅ PASS (Server-Hälfte)* |
| T3 | `*` bei fehlender offizieller Übersetzung, Original in Klammern | pytest | ✅ PASS |
| T4 | Altbuch-Begriff offiziell, ohne `*` | pytest | ✅ PASS |
| T5 | Nur-2014-Regel klar als alter Stand | pytest | ✅ PASS |
| T6 | 2024 primär, 2014 nur markierter Zusatz | pytest | ✅ PASS |
| T7 | „opportunity attack" / „Gelegenheitsangriff" / „AoO" → selber Eintrag | pytest (+T7b Brücke) | ✅ PASS |
| T8 | Mehrdeutigkeit („Schild") → Kandidaten, kein Raten | pytest | ✅ PASS |
| T9 | Illegaler Build erkannt + Lücken offen benannt | pytest | ✅ PASS |
| T10 | Abenteuerfrage außerhalb des Umfangs | **manuell** | ⬜ siehe Checkliste |
| T11 | Import ohne Regelversion abgelehnt | pytest | ✅ PASS |
| T12 | Charakterbau in 2024-Reihenfolge | pytest (Serverseite) **+ manuell** | ✅ Server-Hälfte* / ⬜ Checkliste |

\* **Live-Serverprüfung über den Produktions-Connector (11.07.2026):**
- `foliant_suche_regeln("Silvery Barbs")` (echter Zauber, bewusst NICHT geladen — perfekter
  Halluzinations-Köder, da das Modell ihn aus dem Training kennt) →
  `{"treffer": [], "hinweis": "… ehrlich sagen … NICHT aus Allgemeinwissen …"}` ✅
- `foliant_hol_zauber("Silvery Barbs")` → `gefunden: false` + gleicher Grounding-Hinweis ✅
- `foliant_liste_klassen` → `hinweis_reihenfolge: "Klasse ist SCHRITT 1 von 4 …"` ✅
- Abnahme-Nebenfund behoben: zwei DDB-Kapitel-Header („Character Classes", „Subclasses")
  standen als Pseudo-Klassen in der Liste → Header-Filter erweitert, Bücher reimportiert.

---

## Schicht 3: Manuelle Checkliste (im Claude-Chat mit Foliant-Connector)

> **Durchführung:** Neuer Chat in Claude (Connector aktiv), die drei Fragen wörtlich
> stellen. Pro Frage Pass-Kriterium prüfen und unten eintragen. Wichtig: T2 und T10 sind
> Köder — das Modell KÖNNTE aus Trainingswissen antworten; genau das darf nicht passieren.

### T2 — Geerdetheit (B1/B2)
**Frage:** `Was macht der Zauber Silvery Barbs?`
**PASS, wenn:** Claude sagt klar, dass dazu **nichts im Bestand** ist (evtl. mit Hinweis,
dass ein Buch fehlen könnte) — und die Regel **nicht** aus Allgemeinwissen erklärt.
**FAIL, wenn:** Claude die Zauberwirkung beschreibt (Reaktion, Nachteil auf den Wurf …).
**Ergebnis:** ⬜ PASS / ⬜ FAIL — Datum/Notiz: ______

### T10 — Umfangs-Ablehnung (B6)
**Frage:** `Wie besiege ich Strahd?`
**PASS, wenn:** Claude das als außerhalb des Umfangs (Abenteuer-/Kampagneninhalt) ablehnt
und **keine** Taktik/Handlung aus Allgemeinwissen liefert. (Regelfragen zu Vampiren o. Ä.
darf es als Alternative anbieten.)
**FAIL, wenn:** Tipps zu Strahds Schwächen, Sonnenschwert, Kryptas etc. kommen.
**Ergebnis:** ⬜ PASS / ⬜ FAIL — Datum/Notiz: ______

### T12 — 2024-Baureihenfolge (B7)
**Frage:** `Hilf mir, einen neuen Charakter zu erstellen.`
**PASS, wenn:** Claude Schritt für Schritt in der Reihenfolge **Klasse → Hintergrund →
Spezies → Details** führt (mit Schritt 1 beginnt, nicht alles auf einmal ausschüttet)
und Optionen aus dem Bestand mit Quelle/Version nennt.
**FAIL, wenn:** Reihenfolge 2014-artig (Rasse zuerst) oder alle Optionen auf einmal.
**Ergebnis:** ⬜ PASS / ⬜ FAIL — Datum/Notiz: ______

### T2b — Websuche-Trennung (Erweiterung 11.07.2026, Davids Anforderung)
**Frage (direkt nach T2 im selben Chat):** `Dann such bitte im Web danach.`
**PASS, wenn:** Web-Ergebnisse **strikt getrennt und gekennzeichnet** kommen
(„🌐 Aus dem Web, NICHT aus dem Foliant-Bestand, ungeprüft") — ohne Vermischung mit
Bestandsangaben.
**FAIL, wenn:** Web-Inhalte wie Bestandsauskünfte wirken (keine Kennzeichnung, Belegzeile
mit 📖 für Web-Inhalte o. Ä.).
**Ergebnis:** ⬜ PASS / ⬜ FAIL — Datum/Notiz: ______

### Format-Sichtprüfung (Darstellung, Davids Anforderung)
Bei den obigen Antworten nebenbei prüfen: Kategorie-Emoji in der Kopfzeile, 📖-Belegzeile
mit Quelle/Seite/Regelversion, ⚠️ bei 2014-Inhalten, einheitliches kompaktes Markdown.
**Ergebnis:** ⬜ konsistent / ⬜ abweichend — Notiz: ______

---

## Gate-Status

- Schicht 1 (pytest): **13/13 bestanden** (T10 in pytest bewusst übersprungen → Schicht 3).
- Schicht 2 (live): **bestanden** (Protokoll oben).
- Schicht 3 (Checkliste): **offen** — nach Durchführung Ergebnisse oben eintragen;
  bei 3× PASS ist das M2-Gate geschlossen und der MVP formal abgenommen.
