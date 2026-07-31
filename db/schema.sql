-- Foliant — SQLite-Schema (MVP)
-- Setzt um: §5 (Datenmodell), §6/V1 (Version Pflicht), Q1–Q3 (Suche/Dubletten/keine
-- verwaisten Inhalte), S3/S9/S11 (Glossar, Herkunft, Konsistenz). Journal-Mode: init_db.py.
--
-- SCHEMA-VERSION (codex TECH-019): init_db.py setzt PRAGMA user_version = 2. Version 2
-- fuegte gegenueber v1 die Spalte quellen.inhaltsart (SYN-P0-007) plus die CHECK-
-- Constraints unten hinzu. CHECK gilt nur fuer NEU angelegte DBs; Bestands-DBs auf dem
-- Pi ruesten die Importer die Spalte defensiv per ALTER nach (die CHECKs fehlen dort,
-- deshalb bleibt die Laufzeit-/admin-check-Validierung die zweite Leitplanke).
-- edition bewusst NUR non-empty (nicht auf 2024/2014 fixiert) - V7 verlangt ein
-- erweiterbares Versionsschema (kuenftige Editionen ohne Migration).

CREATE TABLE IF NOT EXISTS quellen (
    id         INTEGER PRIMARY KEY,
    kuerzel    TEXT UNIQUE NOT NULL,        -- 'srd-de', 'phb-2024-de', 'srd-en', ...
    titel      TEXT NOT NULL,
    sprache    TEXT NOT NULL CHECK (sprache IN ('de','en')),
    edition    TEXT NOT NULL CHECK (length(edition) > 0),  -- Pflicht V1/Q3; V7: erweiterbar
    herkunft   TEXT NOT NULL,               -- 'pdf' | 'ddb' | 'srd-md' | 'open5e' | 'manuell'
    lizenz     TEXT,                        -- 'CC-BY-4.0' | 'privat'
    prioritaet INTEGER NOT NULL DEFAULT 100,-- Dubletten-Präzedenz (Q2); kleiner = Vorrang
    -- SYN-P0-007: Abenteuer-/Setting-Inhalt PERSISTENT kennzeichnen (nicht nur als
    -- Konsolen-Print beim Export) — 'regelwerk' | 'abenteuer_setting'. Playtest wird
    -- gar nicht erst importiert. Bestands-DBs ohne Spalte rüsten die Importer defensiv
    -- per ALTER TABLE nach (import_ddb.py / admin.py).
    inhaltsart TEXT NOT NULL DEFAULT 'regelwerk'
               CHECK (inhaltsart IN ('regelwerk','abenteuer_setting')),
    dateipfad  TEXT
);

-- Inhalts-Chunks. edition NOT NULL erzwingt "keine verwaisten Inhalte" (Q3/V1).
CREATE TABLE IF NOT EXISTS eintraege (
    id         INTEGER PRIMARY KEY,
    quelle_id  INTEGER NOT NULL REFERENCES quellen(id) ON DELETE CASCADE,
    -- kategorie = geschlossener Tool-Vertrag (die 8 foliant_hol_*-Kategorien).
    kategorie  TEXT NOT NULL CHECK (kategorie IN
                 ('regel','zauber','monster','gegenstand','spezies','klasse',
                  'hintergrund','talent')),
    name_de    TEXT,
    name_en    TEXT,
    sprache    TEXT NOT NULL CHECK (sprache IN ('de','en')),
    edition    TEXT NOT NULL CHECK (length(edition) > 0),  -- Default-Filter: '2024'
    seite      TEXT,                        -- Seitenangabe (F7)
    -- Breadcrumb ('Zauber > Beschreibungen der Zauber') als eigenes Feld. Der Wert steht
    -- ZUSÄTZLICH weiter als '*Kontext: ...*'-Zeile im body_md — der Body bleibt bewusst
    -- unangetastet, sonst änderte sich der inhalts_hash und der gesamte Bestand bräuchte
    -- einen Re-Import. Die Spalte macht den Breadcrumb abfragbar, statt ihn per
    -- `body_md LIKE '*Kontext: Klassen > X*%'` zu suchen.
    -- Ehrlich zur Wirkung: Der Gewinn ist KLEIN. Die beiden echten Abfragen (charakter.py)
    -- filtern schon auf `kategorie` + `edition` vor und liefen damit nie über einen Full
    -- Scan — gemessen 0,049 → 0,030 ms, Faktor 1,7. Der eigentliche Ertrag ist, dass der
    -- Breadcrumb ein Feld ist statt eines in ein LIKE-Muster interpolierten Strings.
    kontext    TEXT,
    body_md    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eintraege_kat_ed ON eintraege(kategorie, edition);
-- Die realen Zugriffe jenseits von (kategorie, edition), alle mit EXPLAIN QUERY PLAN
-- belegt (28.07.2026, Mac-Subset 3084 Eintraege): vorher SCAN, nachher SEARCH USING
-- COVERING INDEX. quelle_id ist der Re-Import-Pfad (DELETE ... WHERE quelle_id, 36x),
-- die Namensspalten der Exakt-Zugriff der Bruecken-/Struktur-Seeder (je ~128x).
-- Bestands-DBs ruestet db.stelle_schema_sicher() nach.
CREATE INDEX IF NOT EXISTS idx_eintraege_quelle ON eintraege(quelle_id);
CREATE INDEX IF NOT EXISTS idx_eintraege_sprache_kat ON eintraege(sprache, kategorie);
CREATE INDEX IF NOT EXISTS idx_eintraege_name_de ON eintraege(name_de);
CREATE INDEX IF NOT EXISTS idx_eintraege_name_en ON eintraege(name_en);

-- Facetten-Seitenwagen: strukturierte Werte, die ABLEITBAR im body_md stehen. Befuellt
-- ausschliesslich von importer/facetten_seeder.py (EINE Senke, EIN Wertraum) - vorher
-- schrieb nur der Open5e-Import, und zwar in einem ZWEITEN Wertraum ('10.0' statt '10',
-- 'Evocation' statt 'hervorrufung'). Werte sind die kanonischen Schluessel aus
-- app/facetten.py, damit Filter und Anzeige nie auseinanderlaufen. Alt-DBs ruestet
-- db.stelle_schema_sicher() per ALTER TABLE nach (wie bei quellen.inhaltsart).
CREATE TABLE IF NOT EXISTS zauber_meta (
    eintrag_id INTEGER PRIMARY KEY REFERENCES eintraege(id) ON DELETE CASCADE,
    grad INTEGER, schule TEXT, klassen TEXT,
    reichweite_m  TEXT,     -- Meter als Zahl-String ODER 'beruehrung'/'selbst'/'sicht'
    komponenten   TEXT,     -- 'VSM' sortiert; dt. G(este) ist engl. S(omatic)
    dauer_min     INTEGER,  -- Minuten; 0 = unmittelbar, -1 = bis aufgeloest, -2 = Sonderfall
    konzentration INTEGER,  -- 0/1; NULL = im Text nicht erkennbar (kein Raten)
    ritual        INTEGER); -- 0/1; NULL = im Text nicht erkennbar
CREATE TABLE IF NOT EXISTS monster_meta (
    eintrag_id INTEGER PRIMARY KEY REFERENCES eintraege(id) ON DELETE CASCADE,
    hg TEXT, typ TEXT,
    rk INTEGER,             -- Ruestungsklasse
    tp INTEGER);            -- Trefferpunkte
CREATE TABLE IF NOT EXISTS gegenstand_meta (
    eintrag_id INTEGER PRIMARY KEY REFERENCES eintraege(id) ON DELETE CASCADE,
    seltenheit TEXT,
    preis_cent INTEGER);    -- Preis in GM-Cent (int) - vermeidet Float-Vergleiche

-- Glossar DE<->EN: S3-Leiter, S9-Herkunft, S11-Konsistenz, *-Logik
CREATE TABLE IF NOT EXISTS glossar (
    id             INTEGER PRIMARY KEY,
    term_en        TEXT NOT NULL,
    term_de        TEXT NOT NULL,           -- kanonische deutsche Fassung (S11)
    offiziell      INTEGER NOT NULL CHECK (offiziell IN (0,1)),  -- 1 offiziell (kein '*')
    quelle         TEXT,                    -- Herkunft des Begriffs (S9)
    edition_quelle TEXT,                    -- aus welcher Edition der Begriff stammt (S8)
    seite          TEXT
);
CREATE INDEX IF NOT EXISTS idx_glossar_en ON glossar(term_en);
CREATE INDEX IF NOT EXISTS idx_glossar_de ON glossar(term_de);

-- FTS5 über die Chunks (external content); remove_diacritics hilft bei Umlaut-Varianten.
-- KEIN prefix='2 3': am 28.07.2026 gemessen und VERWORFEN. Die Präfixsuchen der Tools
-- ('zauber*', 'feuer*', 'drach*') laufen ohne den Index bei 0,015–0,20 ms; MIT ihm wurden
-- drei von vier LANGSAMER (Faktor 0,53–1,02), und die Datei wuchs um 65 % (7,9 → 13,1 MB).
-- Ein Index, der bremst und Platz kostet, ist kein Index.
CREATE VIRTUAL TABLE IF NOT EXISTS eintraege_fts USING fts5(
    name_de, name_en, body_md,
    content='eintraege', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2');

-- Pflicht: alle drei Trigger, damit FTS synchron bleibt.
CREATE TRIGGER IF NOT EXISTS eintraege_ai AFTER INSERT ON eintraege BEGIN
    INSERT INTO eintraege_fts(rowid, name_de, name_en, body_md)
    VALUES (new.id, new.name_de, new.name_en, new.body_md);
END;
CREATE TRIGGER IF NOT EXISTS eintraege_ad AFTER DELETE ON eintraege BEGIN
    INSERT INTO eintraege_fts(eintraege_fts, rowid, name_de, name_en, body_md)
    VALUES ('delete', old.id, old.name_de, old.name_en, old.body_md);
END;
CREATE TRIGGER IF NOT EXISTS eintraege_au AFTER UPDATE ON eintraege BEGIN
    INSERT INTO eintraege_fts(eintraege_fts, rowid, name_de, name_en, body_md)
    VALUES ('delete', old.id, old.name_de, old.name_en, old.body_md);
    INSERT INTO eintraege_fts(rowid, name_de, name_en, body_md)
    VALUES (new.id, new.name_de, new.name_en, new.body_md);
END;

-- Review-Fund: Re-Seeding des Glossars idempotent machen (Duplikate verhindern).
-- Importer nutzt Upsert: INSERT ... ON CONFLICT(term_en, term_de) DO UPDATE ...
CREATE UNIQUE INDEX IF NOT EXISTS idx_glossar_unique ON glossar(term_en, term_de);
