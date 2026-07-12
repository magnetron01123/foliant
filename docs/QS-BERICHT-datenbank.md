# QS-Bericht: Datenbank (Herzstück)

**Datum:** 2026-07-11 · **Prüfling:** bediente DB auf dem Raspberry Pi
(`data/foliant.sqlite`, **9025 Einträge**, 10 Quellen) · **Umfang:** Inhalte, Struktur, Prozesse.

Grundsatz dieser QS: **nichts schönreden.** Prüfungen melden echte Mängel, statt durch
Verstecken ein grüneres Bild zu zeichnen. Was sicher behebbar war, wurde behoben **und auf dem
Pi verifiziert**; der Rest ist präzise dokumentiert und als Folgeaufgabe eingeplant. Kein echter
Regeltext wurde gelöscht.

**Endstand:** `python -m tests.smoke_test` → **OK** (alle 16 Tools) · `python -m app.admin check`
→ **OK** (integrity/FK/FTS/Editionen sauber, 1 kosmetische Warnung).

---

## 1. Struktur — sauber ✅

| Prüfung | Ergebnis |
|---|---|
| `PRAGMA integrity_check` | ok |
| `PRAGMA foreign_key_check` | 0 Verstöße |
| Einträge ↔ FTS-Zeilen | 9025 = 9025 (keine Waisen, keine Leichen) |
| FTS-Suchprobe (echtes `MATCH`) | 3349 Treffer — Index ist durchsuchbar |
| Einträge ohne Version/Quelle (Q3) | **0** |
| Einträge mit anderer Edition als ihre Quelle (A8) | **0** |
| Kategorien im Whitelist | alle gültig |

**Editionen — der „fahrlässig"-Punkt ist geschlossen.** Jede der 10 Quellen trägt eine
**explizite, korrekte** Regelversion; keine wird geraten oder auf 2024 defaultet. Beim DDB-Import
wird die Edition **autoritativ aus der Buch-DB** gelesen (`RPGSourceCategory.Name` bzw.
`RPGSource.ReleaseDate`), nicht aus Dateinamen; unklare Bücher werden übersprungen.

| Quelle | Edition | Einträge | | Quelle | Edition | Einträge |
|---|---|---|---|---|---|---|
| ddb-basic-rules-2014-en | 2014 | 1559 | | ddb-rthw-en | 2024 | 793 |
| ddb-br-2024-en | 2024 | 2216 | | ddb-wa-en | 2014 | 116 |
| ddb-cosco-en | 2014 | 3 | | open5e-srd-2024 | 2024 | 982 |
| ddb-ee-en | 2014 | 96 | | srd-de | 2024 | 1639 |
| ddb-mcv1-en | 2014 | 40 | | ddb-phb-2024-en | 2024 | 1581 |

---

## 2. Inhalte

### Behoben & verifiziert ✅

- **HTML-Müll `<br>` in 176 srd-de-Einträgen → 0.** Aus PDF-Tabellenzellen stammende
  `<br>`-Tags standen im Plain-Text-Body der deutschen **Hauptquelle**. Der Chunker ersetzt
  `<br>` jetzt durch Leerzeichen; srd-de neu importiert. `admin check`: **0 HTML-Reste**.

- **~109 inhaltsleere DDB-Kapitel-/Gruppentitel verworfen.** Generische TOC-Landeseiten leckten
  als eigene Einträge in Options-Kategorien und verschmutzten die Charaktererstellungs-Listen
  (ein Spieler sah „Species Descriptions" wie eine spielbare Spezies, „Equipment" 13× als Klasse,
  „General Feats" als Talent). Verworfen wird nur, was **nie eine Option ist UND reinen Vorspann
  trägt**: bloße Kategorietitel (Species/Feats/Equipment/Magic Items …), `Chapter N:`/`Ch. N:`-
  Überschriften und die Talent-Gruppen-Header (~47 B Boilerplate). Ergebnis: `foliant_liste_*`
  müllfrei, **kein Talent mehr ohne Kategorie**, Smoke **OK**.

  > **Bewusst NICHT gelöscht** (echter Regeltext, nur header-ähnlicher Name): `Aasimar Traits`
  > (Rassenmerkmale ~1300 B), `Level 3 Wizard Spells` (Zauberliste, 128×), `Barbarian Class
  > Features`. Ein Test sichert, dass diese den Filter passieren — **kein Inhaltsverlust**.
  > Ihre saubere Umformung/Kategorisierung ist die Folgeaufgabe „DDB-Kategorisierung".

### Die zwei Folgeaufgaben — erledigt & auf dem Pi verifiziert ✅ (11.07.2026)

- **srd-de-Chunker (Statblock-/Tabellen-Fragmente).** Kreatur-Statblocks IN Beschwörungs­zaubern
  (die `Merkmale`/`Aktionen`/`Bonusaktionen` des herbeigerufenen Wesens) und Tabellen-/Statblock-
  Reste (`RK 15`, `1W8 Strahl`, `Treffer-`, Material-Tabellen) mergen jetzt in ihren Elternzauber
  (`MERGE_REGELN` name-/strukturbasiert). Nach Re-Import: **0 solcher Fragmente** in `srd-de`
  (18 gemergt). **Sicherheit:** fehl-geheadete ECHTE Zauber (Shillelagh/Windwall/Göttliche Gunst,
  deren PDF-Text nur verschoben ist) bleiben erhalten — ein Body-Signal-Merge hätte sie still
  gelöscht; deshalb name-/strukturbasiert. Regressionstest deckt beides ab.
  *Klarstellung:* Die im vorigen Bericht als „miskategorisiert" gezählten `Aktionen`/`Sinne`/
  `Bewegungsrate` unter Regel-/Gegenstands-/Spezies-Kontext sind **keine Bugs**, sondern echte
  Regel-Unterabschnitte — sie bleiben.
- **Listen ↔ Build konsistent (Aasimar-Lücke).** `_ist_option` entscheidet jetzt am **letzten
  Kontext-Segment**: eine Option steht direkt unter einem Kapitel-/Gruppen-Header (Deutsch UND
  DDB: `Species Descriptions`/`Backgrounds`/`Origin Feats`/…), ein Unterabschnitt nistet unter
  einem Optionsnamen (`… > Aasimar` = Traits → keine Option). Ergebnis auf dem Pi: **Aasimar &
  Ravenloft-Spezies erscheinen in `foliant_liste_spezies`** (14 statt 9), Talente 86 statt 17
  (DDB-Feats, alle kategorisiert), Ravenloft-Hintergründe in der Liste — **konsistent zur
  Build-Prüfung**. srd-de/Open5e unverändert. Reine Laufzeitänderung, kein Re-Import.

### Detail-Vollständigkeit (DDB-Optionen) — erledigt & verifiziert ✅

`hol_spezies("Aasimar")` lieferte nur die Intro; die Werte standen im separaten `Aasimar Traits`.
Jetzt führt `_hole_detail(aggregiere_kinder=True)` die **direkten** Unterabschnitte (Kontext exakt
`<Eltern-Kontext> > <Eltern-Name>`) in den Regeltext zusammen — quellen-/editionsrein und **nur
direkte Kinder**. Bewusst **kein** Einsaugen ganzer Kapitelbäume: eine flache Parent-Child-Fusion
hätte 2807 verschachtelte DDB-Abschnitte kollabiert (789 Klassen-, 1274 Regel-Kinder → unbrauchbare
Blobs). Auf dem Pi: `hol_spezies("Aasimar")` 703 → 2927 Zeichen inkl. Werte; Ravenloft-Spezies
(Dhampir) komplett; `hol_talent("Crafter")` inkl. Fast Crafting. Für Spezies mit vollständigem
deutschem srd-de-Eintrag (Elf/Tiefling) ist es korrekt ein **No-op** (Deutsch-first bleibt).

### Bewusste Rest-Posten (niedrige Priorität, dokumentiert)

| Fund | Schwere | Warum offen gelassen |
|---|---|---|
| `Aasimar Traits` u. Ä. erscheinen als eigene **Such**treffer (die Detail-Auskunft ist vollständig) | niedrig | sind echter, suchbarer Inhalt; die Option rankt zuerst — Ausblenden verschlechterte die Suche |
| srd-de Drop-Cap-Namen (`wAffen`, `zAuber`) | niedrig | rein kosmetisch (Inhalt korrekt); Case-Heuristik an der Hauptquelle wäre risiko-unverhältnismäßig |
| Nackter `ddb://`-Link (Basic Rules 2024) | niedrig | Code-Fix deployt; verschwindet beim nächsten Re-Export |
| 2014-Sub-Fragmente in DDB-Kategorien (z. B. EE „X Traits") | niedrig | erreichen die strikt-2024-Listen NIE; Suche rankt echte Optionen zuerst |
| Body-Dubletten (Kampfstile je Klasse) | keine | **kein Fehler** — legitime klassenspezifische Instanzen |

---

## 3. Prozesse

- **`admin check` erweitert** (`app/admin.py`): zusätzlich `integrity_check`,
  `foreign_key_check`, **FTS-Suchbarkeit** (echtes `MATCH`), Kategorie-/Editions-Whitelist und
  **Textqualität** (HTML-Reste, `ddb://`-Links, HTML-Entities). Meldet Mängel als WARNUNG statt
  sie zu verschweigen — die verbliebene 1 `ddb://`-Warnung ist echt und sichtbar.
- **Smoke-Test** (`tests/smoke_test.py`): deckt jetzt **alle 16 Tools** ab (vorher 12) und prüft
  **aktiv auf Header-Müll** in den Listen. Robust gegen den Mehrquellen-Bestand: Teilmengen-
  Präsenz der SRD-Optionen statt starrer SRD-only-Zahlen. Fand die Header-Stubs überhaupt erst.
- **Backup-Rotation** (`importer/import_ddb.py`): Jede DDB-Aktivierung legte eine ~19-MB-Sicherung
  an, ohne je zu löschen (ein `sync` = 8 Sicherungen/Lauf → ~150 MB Altbestand auf der Pi-SD).
  Neu: `_rotiere_backups` behält die 3 jüngsten, schont die einmalige Pre-DDB-Sicherung. **In
  Produktion verifiziert: 11 → 3 Sicherungen**, Pre-DDB-Kopie intakt.
- **Re-Import**: atomar (Kandidat → Prüfung → `os.replace`, A7), idempotent, mit Schrumpf-Schutz
  und autoritativer Edition. FTS wird nach jedem Import neu aufgebaut.

### ⚠️ Deploy-Lehre (wichtig für den Betrieb)
Das Pi-Image **backt den Code ein** (`COPY`). Ein reines `rsync` aufs Pi aktualisiert die Dateien,
**nicht den laufenden Container** — ein Import lief dann still mit ALTEM Code weiter und meldete
„erfolgreich" bei unveränderten Daten (echter Footgun). **Nach jeder Code-Änderung Pflicht:**
`docker compose up -d --build foliant` (steht bereits in `docs/DEPLOY-raspberry-pi.md`, wurde hier
zur harten Regel). `data/` bleibt gemountet; nur der Code muss neu gebacken werden.

### Testlage
`pytest`: **81 bestanden, 4 übersprungen.** Neu u. a.: Header-Filter (inkl. Nachweis, dass echter
Regeltext bleibt), Backup-Rotation, `<br>`-Chunking, nackte-`ddb://`-Bereinigung, Zauber-Statblock-
Merge (kein Zauberverlust), Options-Erkennung am letzten Kontext-Segment, Detail-Aggregation
(nur direkte Kinder, quellen-/editionsrein).

---

## Fazit

Die **Struktur** ist einwandfrei und zukunftsfähig (ein internes Schema für alle Quellen,
Editionen korrekt und explizit, FTS konsistent und durchsuchbar). Die **Inhalte** sind deutlich
sauberer: die deutsche Hauptquelle ist HTML-frei, die Charakter-Listen sind müllfrei, und es wurde
**kein echter Regeltext gelöscht**. Die **Prozesse** prüfen jetzt ehrlich und breiter, decken alle
Tools ab, halten die Pi-SD im Zaum und der Deploy-Footgun ist als harte Regel dokumentiert.

**Beide Folgeaufgaben + die Detail-Vollständigkeit sind erledigt und auf dem Pi verifiziert** (§2):
srd-de-Statblock-/Tabellen-Fragmente mergen in ihren Elternzauber (0 verbleibend, kein Zauber
verloren), die Charakter-Listen zeigen DDB-Optionen (Aasimar & Co.) konsistent zur Build-Prüfung,
und die Detail-Auskunft für DDB-Optionen ist vollständig (Intro + Werte zusammengeführt). Der
Retrieval-Spot-Check (Suche, Deutsch-first-Glossar, Kern-Detailabrufe, Grounding bei Leersuche) ist
sauber. Übrig bleiben nur bewusst niedrig priorisierte Rest-Posten (Tabelle in §2).


---

## Nachtrag 11.07.2026 (spät): Tiefen-Audit der zwei DDB-Druck-Bücher

Auf Davids Auftrag („Inhalte müssen korrekt ankommen") wurden beide Neuimporte per
**Kreuz-Audit** geprüft: die zwei unabhängigen Textfassungen (Original-Schicht vs.
Voll-OCR) wurden seitenweise gegeneinander gediffed (Würfelwerte, Zahlen, Preise) —
plus **Sichtprüfung** von ~40 gerenderten Seiten für alle nicht eindeutig auflösbaren
Überschriften.

**Befund & Konsequenz (frhof):** Die zunächst verwendete OCR-Basis verlor ganze
Preistabellen (S. 146: 12 Items) und verschmolz Kasten-Wörter zu unsuchbaren Ketten;
das Original hat Zahlen/Tabellen korrekt, aber kaputte Fonts. → Umbau auf
**Original-Basis mit generierter, sichtgeprüfter Reparatur** (`importer/frhof_reparatur.py`):
484 Mojibake-Überschriften seitenbewusst rekonstruiert, 30 hashlose Abschnittszeilen zu
Überschriften befördert — darunter **7 zuvor verlorene Hintergründe** (Genie Touched,
Ice Fisher, Lords' Alliance Vassal, Mulhorandi Tomb Raider, Purple Dragon Squire,
Shadowmasters Exile, Zhentarim Mercenary) —, 264 fi/fl-Ligaturen repariert, die
Realms-Timeline (S. 59, nur im OCR) als Seiten-Patch übernommen.

**Audit-Endstand (auf dem Pi verifiziert):**
- Würfelwerte: **65/65 vollständig** (die OCR-Basis hatte sie teils verloren)
- GP-Preise: **86/87** (1 in entfernter Junk-Zeile)
- 10 Spezies ganz · 8 Unterklassen · **18 Hintergründe** (vorher 8) · 18 Zauber · 20 Gegenstände
- **0 Mojibake-Namen in der gesamten DB**; ~30 kosmetische Inline-Reste in Bodies
- efota: Drop-Audit der 8 „textlosen" Seiten → alle vollständig enthalten (war ein
  Artefakt der Pi-Konvertierung, siehe `use_ocr=False`-Fix)

Verbleibende Kosmetik (niedrig): vereinzelte OCR-Garbles in transplantierten
Zielnamen, ALL-CAPS-Namen (Quelltreue), ~30 Inline-Kapitälchen-Reste.
