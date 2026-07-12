# Best Practices aus bestehenden D&D-MCP-Servern

**Quellen:** `justinritchie/dnd-rules-mcp-server` und `heffrey78/dnd-mcp` (beide Open5e-basiert, TypeScript).
**Übersetzt auf Foliant:** FastMCP, lokales SQLite/FTS5, Deutsch-first, Quellen-/Seitenzitat.
Wo ein Muster bei uns *nicht* gilt, ist es explizit markiert — nicht blind übernehmen.

---

## Tool-Design

**1. `such_*` und `hol_*` pro Entitätstyp trennen.**
Je Typ (Zauber, Monster, Zustand, Regel, Klasse …) zwei Tools: ein Such-Tool (Filter → knappe Trefferliste) und ein Hol-Tool (ID/Name → volle Detailausgabe). Verhindert, dass Suchen riesige Payloads liefern, und hält die Kontextlast niedrig. Referenz: 14 Tools nach genau diesem Muster.

**2. Konsistente, geprefixte Namen: `foliant_<verb>_<nomen>`.**
Verb + Nomen, keine Sonderfälle. Hält die Tools im Client zusammen und kollisionsfrei.

**3. Exact-Match vor Substring.**
`Feuerball` darf nicht zuerst `Verzögerter Feuerball` liefern. Umsetzung bei uns: FTS5-bm25-Ranking **plus** expliziter Exact-Name-Boost, plus sauberer Umgang mit Umlauten und Groß-/Kleinschreibung. Retrieval-Qualität ist hier der halbe Anti-Halluzinations-Schutz — schlechte Treffer sind die häufigste Quelle für falsche Antworten.

**4. Universelle Quersuche als Komfort-Tool — aber erst später.**
Beide Referenzen planen/haben ein `search`-über-alles („ich hab von einem Zauber gehört, der …"). Für v1 nachrangig, guter Kandidat für Stufe 2.

## Edition & Quellen

**5. Edition ist Pflichtdimension — aber SICHTBAR, nicht versteckt.**
Übernehmen: jede Regelentität trägt einen Edition-Tag, Tools defaulten auf 2024, 2014 nur auf Abruf.
**NICHT übernehmen:** die Referenz normalisiert so, „dass die LLM den Unterschied nicht sieht". Für uns ist das ein Anti-Pattern. Edition + Quelle müssen im Output sichtbar bleiben (Zitatpflicht; stille 2014/2024-Mischung korrumpiert Antworten). Also: **Datenshape** normalisieren, **Provenienz** behalten.

**6. Quellen-Keying, pro Call überschreibbar.**
Default-Quelle je Edition, aber ein optionaler `quelle`-Parameter erlaubt die gezielte Abfrage einer bestimmten Quelle. Für uns ohnehin Pflicht: Buch + Seite hängen als First-Class-Felder am Entry, nicht als nachträgliche Fußnote.

**7. Eine interne Schema-Normalisierung über alle Import-Quellen.**
Die Referenz mappt Open5e v1 (flache Strings) und v2 (Objekte) auf *ein* internes Interface, bevor etwas die Formatter/LLM erreicht. Unser Analogon: PDF-Import (dt. Bücher), DDB-Import und SRD auf **ein** einheitliches internes Schema mappen — der Tool-Output sieht gleich aus, egal aus welcher Quelle das Entry stammt.

## Datenqualität & Robustheit

**8. Quellen-Macken an EINER Stelle kapseln und kommentieren.**
Die Referenz hält alle Open5e-Quirks zentral im Client und dokumentiert sie (inkonsistente Filternamen; kaputter `rarity`-Filter → breiter fetchen + client-seitig filtern; Conditions liegen in einer anderen Quelle). Unsere Quirks sind andere — PDF-Extraktionsfehler, Term-Mapping-Lücken, Statblock-Tabellen — aber dasselbe Prinzip: ein „bekannte Macken"-Modul mit Kommentaren, damit dieselbe Falle nicht zweimal gelöst wird.

**9. Smoke-Test über ALLE Tool-Kategorien, mit Sample-Output.**
Ein Skript, das jedes Tool gegen echte Daten feuert und Beispielausgaben druckt — die Referenz inkl. eines Cross-Edition-Vergleichs (Counterspell 2014 vs. 2024). Fügt sich bei uns in T1–T12; zusätzlich ein **Deutsch-Term-Smoke**: offizieller Term korrekt getroffen? `*`-Markierung bei inoffiziellen Termen gesetzt?

## Architektur & Scope

**10. Getrennte Server/Datenräume nach Verantwortung.**
Die Referenz trennt Regel-Lookup und Charakterdaten in zwei Server. Deckt sich exakt mit unserer strukturellen Spoiler-Isolation: Regeln, Kampagne und Abenteuer bleiben getrennt gemountet — nie ein Tool, das über die Grenze hinweg liest.

**11. Scope-Disziplin explizit festschreiben.**
Die Referenz schreibt DDB bewusst als „out of scope" fest (keine offene API, Reverse-Engineering-Wartung lohnt nicht) — deckt sich mit unserer Entscheidung: DDB nur als Einmal-Import, nicht als Runtime-Abhängigkeit. Solche Nicht-Ziele explizit in `CLAUDE.md`, sonst macht der Agent sie „hilfreich" wieder auf.

**12. Kein Runtime-Caching — bewusst weglassen.**
heffrey78 baut NodeCache, um API-Calls zu sparen. Für uns **nicht relevant**: lokales SQLite, kein Netz, kein Rate-Limit. FTS5 ist schneller als jeder Cache-Layer drumherum. Nur aufgreifen, falls später doch remote Quellen angefragt werden.

---

## Was diese Server NICHT beibringen

Beide sind reine **englische SRD**-Ausgaben **ohne Seitenzitat**. Deutsch-first-Terminologie und Quellen-/Seitenreferenz — Foliants eigentlicher Kern — kommen bei keinem vor. Die Referenzen taugen für **Tool-Ergonomie und Editionslogik**, nicht für unsere Differenzierung. Der Deutsch- und Zitat-Teil bleibt unser eigenes Terrain.
