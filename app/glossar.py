"""Begriffsauflösung DE<->EN nach S3-Leiter, Konsistenz (S11), *-Kennzeichnung (S5).

Prioritaet bei mehreren Glossar-Zeilen zum selben Begriff (S3/S8): offizielle Begriffe vor
inoffiziellen, darin neuere Edition vor aelterer (S8: der neuere offizielle Begriff gewinnt).
Normalisierung (S11): Gross-/Kleinschreibung + Diakritika-Toleranz exakt, kleine
Flexions-/Schreibvarianten ueber rapidfuzz - damit ein vorhandener offizieller Begriff nicht
faelschlich als "fehlt" gilt und ein unnoetiges '*' kassiert."""
from __future__ import annotations

import re
import sqlite3
import unicodedata

from rapidfuzz import fuzz, process

# --- Die Fuzzy-Schwellen, an EINER Stelle mit Begruendung je Wert (Befund E5) ----------
# Vorher lagen sie in drei Modulen (glossar 88, db.py 86, nachschlagen 90), gewachsen statt
# abgestimmt - niemand konnte sagen, warum sie sich unterscheiden. Sie stehen jetzt hier,
# weil dieses Modul ohnehin die kanonische Namensvergleichs-Logik traegt (norm_begriff,
# KLAMMER_SUFFIX); db.py und nachschlagen.py importieren von hier.
#
# Die WERTE sind bewusst unveraendert uebernommen: Sie sind an echten Faellen justiert, und
# jede Verschiebung bewegt das Suchverhalten am gesamten Bestand. Die Aufgabe war, sie
# erklaerbar zu machen - nicht, sie zu vereinheitlichen. Dass sie auseinanderliegen, ist
# richtig: sie messen mit verschiedenen Scorern verschieden teure Fehler.

# Glossar-Aufloesung eines Begriffs (scorer: fuzz.ratio ueber normalisierte Begriffe).
# Der teuerste Fehlertyp im Projekt: ein Fuzzy-Treffer wird zur "offiziellen Uebersetzung".
# 88 laesst 'Aktionen'~'Reaktionen' (88.9) noch durch - deshalb ist der Treffer hier
# ausdruecklich ein VORSCHLAG (match='fuzzy'), nie eine Identitaet (SYN-P0-001).
FUZZY_GLOSSAR = 88.0

# Fuzzy-Fallback der Bestandssuche (scorer: fuzz.WRatio ueber Eintragsnamen). Am
# niedrigsten, weil hier nur die KANDIDATENMENGE erweitert wird: ein zu grosszuegiger
# Treffer kostet einen Listenplatz, kein falsches Faktum. WRatio ist zudem milder als
# ratio, ein direkter Zahlenvergleich mit den anderen beiden waere Unsinn.
FUZZY_SUCHE = 86

# Namensrelevanz eines Kandidaten (scorer: fuzz.ratio). Am hoechsten, weil das Ergebnis
# dem Modell als "der NAME passt zur Anfrage" verkauft wird: 'Aktionen'~'Reaktionen'
# (88.9) darf NIE als Namenstreffer zaehlen, kleine Tippfehler ('Missle'~'Missile', ~96)
# liegen klar darueber.
FUZZY_NAME = 90.0

# Textabweichung zweier gleichsprachiger Fassungen (scorer: fuzz.ratio ueber den
# normalisierten Body). Darunter gelten sie als inhaltlich verschieden und werden als
# `konflikt_quellen` ausgewiesen. Gleiche Hoehe wie FUZZY_NAME, aber aus anderem Grund:
# hier ist ein FALSCH-POSITIV teuer (das Modell soll nicht bei jeder Formatierungs-
# abweichung einen Quellkonflikt melden), nicht ein Falsch-Negativ.
FUZZY_ABWEICHUNG = 90.0

_FUZZY_CUTOFF = FUZZY_GLOSSAR       # modulinterner Altname


def norm_begriff(text: str | None) -> str:
    """Kanonische Begriffs-Normalisierung (S11): Kleinschreibung + Unicode-NFKD +
    Diakritika entfernen (ü->u, ß bleibt via NFKD-Kompatibilitaet erhalten) - analog zum
    FTS-Tokenizer. OEFFENTLICH, damit alle Vergleichspfade (Suche, Dubletten-Bruecke,
    Options-Gruppierung) DIESELBE Semantik nutzen statt eigener .lower()-Kopien (A3)."""
    s = (text or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


_norm = norm_begriff

# Klammer-Zusatz am NAMENSENDE ('Erschöpfung (Zustand)', 'Verstecken (Aktion)'): der
# Zusatz ist Qualifikator, nicht Name. EINE Definition fuer alle Vergleichspfade
# (Exakt-Auswahl, Such-Ranking) - SYN-P0-002: ohne die klammerlose Variante griff bei
# gemischtem Bestand der Altstand-Fallback ('Erschöpfung' -> 2014-'Exhaustion').
KLAMMER_SUFFIX = re.compile(r"\s*\([^()]{1,40}\)\s*$")

# Herkunfts-Label der 2024-Aktionszeilen (glossar.quelle). Es steht hier statt beim Seeder,
# weil es SCHREIBER und LESER verbindet: `importer/import_glossar.seed_aktionen` setzt es,
# der Charakterbogen-Uebersetzer holt genau diese Zeilen wieder heraus. Deren EN-Lemmata
# (Attack, Magic, Hide ...) sind Alltagswoerter und deshalb in _HOMONYM_STOP - der
# Inline-Annotator findet sie also NIE, der Bogen braucht sie aber (C4: amtliche Begriffe
# schlagen Modelluebersetzungen). Bis zum 29.07.2026 stand der String im Uebersetzer als
# Literal: haette der Seeder sein Label geaendert, waeren die 2024-Aktionsnamen dort still
# ausgefallen - ohne Fehler, nur mit schlechterem Deutsch auf dem gedruckten Bogen.
QUELLE_AKTIONEN = "SRD 5.2.1 (Aktionen)"

# SYN-P2-004 (codex TECH-013): jeder Glossarpfad (lookup, exakte_entsprechungen,
# _brueckennamen) las bisher die KOMPLETTE Tabelle pro Aufruf - eine Suche loest 5-8
# Voll-Scans aus, die mit dem Vollseeding (~1.400 Zeilen) linear teurer werden. Cache
# je (DB-Datei, mtime, Zeilenzahl): unveraenderte DB -> ein Scan, danach RAM. Der
# Schluessel invalidiert automatisch nach jedem Import (mtime + count aendern sich).
_GLOSSAR_CACHE: dict[tuple, list[dict]] = {}
# Exakt-Index ueber dieselben Zeilen (s. _exakt_index); gleiche Signatur, gleiche Lebensdauer.
_INDEX_CACHE: dict[tuple, dict[tuple[str, str], list[dict]]] = {}
# Namens-/Fuzzy-Schluessel je Spalte (s. _namen_index) - ebenfalls an die DB-Signatur gebunden.
_NAMEN_CACHE: dict[tuple, dict[str, tuple]] = {}


def leere_cache() -> None:
    """Alle drei Glossar-Caches verwerfen - nach einem SCHREIBZUGRIFF auf die Tabelle.

    Der Normalfall braucht das nicht: die Signatur (_db_signatur) enthaelt mtime und
    Zeilenzahl und faellt nach einem Import von selbst. INNERHALB einer offenen
    Schreibtransaktion greift das aber nicht zuverlaessig - die Datei-mtime steht noch,
    und ein Seeder, der nur bestehende Zeilen AENDERT, laesst auch die Zeilenzahl gleich.
    Genau dort ruft die Glossar-Kette diese Funktion (importer/import_glossar.py): ein
    Folge-Seeder muss sehen, was sein Vorgaenger geschrieben hat.

    Die Zusage steht hier, weil sie nur hier einloesbar ist: _INDEX_CACHE und _NAMEN_CACHE
    sind aus den Zeilen ABGELEITET und muessen mitfallen. Bis zum 29.07.2026 leerte
    import_glossar an zehn Stellen `_GLOSSAR_CACHE` direkt - das funktionierte, aber nur
    ueber den Umweg, dass _alle_zeilen die beiden anderen beim Neuaufbau mitleert."""
    _GLOSSAR_CACHE.clear()
    _INDEX_CACHE.clear()
    _NAMEN_CACHE.clear()


def _db_signatur(con: sqlite3.Connection) -> tuple:
    try:
        pfad = next((r[2] for r in con.execute("PRAGMA database_list") if r[1] == "main"),
                    None)
        n = con.execute("SELECT count(*) FROM glossar").fetchone()[0]
    except sqlite3.Error:
        return ("?", 0.0, 0)
    mtime = 0.0
    if pfad:
        try:
            mtime = __import__("os").stat(pfad).st_mtime
        except OSError:
            mtime = 0.0
    return (pfad or ":memory:", mtime, n)


def _alle_zeilen(con: sqlite3.Connection) -> list[dict]:
    """Alle Glossarzeilen, prozessweit gecacht (SYN-P2-004). In-Memory-DBs (Tests) haben
    keinen stabilen Pfad -> Signatur enthaelt die Zeilenzahl, damit Fixtures korrekt
    invalidieren."""
    sig = _db_signatur(con)
    cached = _GLOSSAR_CACHE.get(sig)
    if cached is None:
        cached = [dict(r) for r in con.execute(
            "SELECT term_de, term_en, offiziell, quelle, edition_quelle, seite "
            "FROM glossar")]
        _GLOSSAR_CACHE.clear()               # nur die aktuelle Signatur halten (klein)
        # Die abgeleiteten Caches hier mitleeren: sie sind aus GENAU diesen Zeilen gebaut.
        # So wirkt auch ein blosses `_GLOSSAR_CACHE.clear()` (Test-Isolation) auf alle drei -
        # sonst haetten Fixtures mit gleicher Signatur, aber anderem Inhalt einen stale Index.
        _INDEX_CACHE.clear()
        _NAMEN_CACHE.clear()
        _GLOSSAR_CACHE[sig] = cached
    return cached


def _namen_index(con: sqlite3.Connection, spalte: str) -> tuple[dict, list, list]:
    """(Rohname -> Zeilen, Rohnamen, VORNORMALISIERTE Rohnamen) je Spalte, gecacht.

    Messung 28.07.2026 (Pi, cProfile): norm_begriff lief 88 000-mal PRO Suchanfrage und
    kostete 11,4 von 13,1 s. Ursache war nicht die Menge der Daten, sondern die
    Wiederholung - lookup() baute dieses Dict bei JEDEM Aufruf neu ueber alle
    Glossarzeilen, und _glossar_alternativen ruft lookup() wegen der zwei Hops rund
    zwoelfmal je Anfrage auf. Auch die Normalisierung der Suchschluessel gehoert in den
    Cache: process.extract(processor=_norm) normalisierte sonst alle 3180 Namen erneut,
    einmal pro Aufruf."""
    sig = _db_signatur(con)
    cache = _NAMEN_CACHE.get(sig)
    if cache is None:
        cache = {}
        _NAMEN_CACHE.clear()                 # nur die aktuelle Signatur halten
        _NAMEN_CACHE[sig] = cache
    if spalte not in cache:
        namen: dict[str, list[dict]] = {}
        for z in _alle_zeilen(con):
            if z[spalte]:
                namen.setdefault(z[spalte], []).append(z)
        schluessel = list(namen.keys())
        cache[spalte] = (namen, schluessel, [_norm(k) for k in schluessel])
    return cache[spalte]


def _exakt_index(con: sqlite3.Connection) -> dict[tuple[str, str], list[dict]]:
    """Index (richtung, normalisierter Begriff) -> Zeilen, bestpassende zuerst; prozessweit
    gecacht mit derselben Signatur wie _alle_zeilen.

    Messung 28.07.2026: lookup() baut PRO AUFRUF ein Namens-Dict ueber alle Glossarzeilen
    und faehrt zusaetzlich einen rapidfuzz-Lauf. Alle Anzeige- und Uebersetzungspfade
    verwerfen die Fuzzy-Zeilen aber ohnehin (SYN-P0-001) - fuer sie war beides umsonst und
    kostete bei 8 Suchtreffern rund 30 ms. Sortierung identisch zu lookup(), damit
    lookup_exakt() dieselbe Zeile waehlt."""
    sig = _db_signatur(con)
    idx = _INDEX_CACHE.get(sig)
    if idx is None:
        idx = {}
        for z in _alle_zeilen(con):
            for richtung, spalte in (("en_de", "term_en"), ("de_en", "term_de")):
                n = _norm(z[spalte])
                if n:
                    idx.setdefault((richtung, n), []).append(z)
        for zeilen in idx.values():
            zeilen.sort(key=_auswahlschluessel)
        _INDEX_CACHE.clear()                 # nur die aktuelle Signatur halten
        _INDEX_CACHE[sig] = idx
    return idx


def lookup_exakt(con: sqlite3.Connection, begriff: str, richtung: str = "en_de") -> list[dict]:
    """Nur die EXAKTEN Glossarzeilen zum Begriff - O(1) statt Voll-Scan plus Fuzzy-Lauf.
    Fachlich identisch zu `[z for z in lookup(...) if z['match'] == 'exakt']`, nur ohne
    den Aufwand fuer Zeilen, die der Aufrufer sowieso wegwirft."""
    n = _norm(begriff)
    if not n:
        return []
    return [{**z, "match": "exakt"} for z in _exakt_index(con).get((richtung, n), [])]


def exakte_entsprechungen(con: sqlite3.Connection, begriff: str) -> set[str]:
    """Beidseitige EXAKTE Glossar-Entsprechungen (normalisiert) - die belastbare Bruecke
    fuer Identitaets- und Zugehoerigkeitsvergleiche (A3/A4). Bewusst OHNE Fuzzy:
    Aehnlichkeit allein macht zwei Begriffe nicht zum selben Konzept."""
    n = norm_begriff(begriff)
    if not n:
        return set()
    treffer: set[str] = set()
    for z in _alle_zeilen(con):
        nde, nen = norm_begriff(z["term_de"]), norm_begriff(z["term_en"])
        if n == nde and nen:
            treffer.add(nen)
        if n == nen and nde:
            treffer.add(nde)
    return treffer


def _auswahlschluessel(z: dict) -> tuple:
    """A9 - dokumentierte KANONISCHE AUSWAHLREGEL (S3/S8), in dieser Reihenfolge:
      1. offizielle Begriffe vor inoffiziellen (S6),
      2. neuere belegte Edition vor aelterer, UNBEKANNTE Edition ganz hinten
         (S8: der neuere offizielle Begriff gewinnt; nichts wird als 2024 geraten),
      3. Begriffe mit konkretem Buch-/Glossar-Beleg vor blossen Community-Zeilen,
      4. alphabetisch NUR als letzter Determinismus-Anker.
    Modulweit, damit lookup() und begriffe_im_text() DIESELBE Zeilenauswahl treffen."""
    quelle = z.get("quelle") or ""
    belegt = 0 if ("Ulisses" in quelle or "buch" in quelle.lower()
                   or (quelle and "Community" not in quelle
                       and quelle != "abkuerzung")) else 1
    return (-int(z["offiziell"] or 0),
            0 if z["edition_quelle"] else 1,          # unbekannte Edition nach hinten
            -(int(z["edition_quelle"]) if str(z["edition_quelle"] or "").isdigit() else 0),
            belegt, z["term_de"] or "")


def lookup(con: sqlite3.Connection, begriff: str, richtung: str = "en_de") -> list[dict]:
    """Alle Glossar-Zeilen zum Begriff, bestpassende zuerst.
    richtung 'en_de': begriff ist englisch; 'de_en': begriff ist deutsch.
    Stufen: exakt (case-/diakritika-insensitiv) -> fuzzy (S11). Jede Zeile:
    {term_de, term_en, offiziell, quelle, edition_quelle, seite, match, score}.

    SYN-P0-001 (Review-Fund, verifiziert): Fuzzy-Treffer sind NUR Suchvorschlaege, nie
    fachliche Identitaet - 'Aktionen' matcht 'Reaktionen' mit ratio 88.9 und wurde so
    zur 'offiziellen Uebersetzung'. Deshalb traegt jede Zeile ihren `match`-Typ
    ('exakt'|'fuzzy') und Fuzzy zusaetzlich den `score`; Identitaets-, Anzeige- und
    Uebersetzungspfade duerfen ausschliesslich 'exakt' verwenden."""
    spalte = "term_en" if richtung == "en_de" else "term_de"
    alle = _alle_zeilen(con)                  # SYN-P2-004: gecacht statt Voll-Scan
    if not alle:
        return []
    n = _norm(begriff)
    richtung_key = "en_de" if spalte == "term_en" else "de_en"
    exakt = [{**z, "match": "exakt"} for z in _exakt_index(con).get((richtung_key, n), [])]
    # S11: Flexions-/Schreibvarianten IMMER dazunehmen ("Gelegenheitsangriff" muss auch die
    # Plural-Zeile "Gelegenheitsangriffe" treffen, selbst wenn eine Abkuerzungszeile exakt
    # passt). Exakte Treffer bleiben vorn.
    namen, schluessel, schluessel_norm = _namen_index(con, spalte)
    # fuzz.ratio (voller Levenshtein), NICHT WRatio: dessen Substring-Komponente wuerde
    # 'Feuer' auf 'Feuerball' mappen und vage Begriffe faelschlich 'exakt' machen (B4!).
    # ratio toleriert genau das Gewollte: Flexion/kleine Varianten (Wurf<->Wuerfe ~97).
    # Query UND Schluessel sind hier bereits normalisiert - fachlich dasselbe wie
    # processor=_norm, nur ohne die Normalisierung aller Namen bei jedem Aufruf.
    passend = process.extract(n, schluessel_norm, scorer=fuzz.ratio,
                              score_cutoff=_FUZZY_CUTOFF, limit=5)
    fuzzy = [{**z, "match": "fuzzy", "score": round(score, 1)}
             for _n, score, i in passend for z in namen[schluessel[i]]
             if _norm(z[spalte]) != n]

    return (sorted(exakt, key=_auswahlschluessel)
            + sorted(fuzzy, key=_auswahlschluessel))


def term_de(con: sqlite3.Connection, term_en: str) -> tuple[str, bool]:
    """Liefert (deutscher_begriff, offiziell). offiziell=False -> Aufrufer setzt '*' (S5).
    Kein EXAKTER Glossar-Treffer -> (term_en, False): es gibt (noch) keine belegte deutsche
    Entsprechung; der Aufrufer nutzt dann eine markierte deutsche Wiedergabe (S3 Stufe 4).
    Fuzzy-Zeilen zaehlen hier NIE (SYN-P0-001: sonst wird ein aehnlicher FREMDER Begriff
    zur 'offiziellen' Uebersetzung - Aktionen -> Reaktionen)."""
    zeilen = lookup_exakt(con, term_en, richtung="en_de")
    if not zeilen:
        # Klammer-Suffix abziehen (SYN-P0-002 kanonisch): Eintragsnamen wie
        # "Alchemist's Supplies (50 GP)" tragen den Zusatz, die Bruecke fuehrt nur die
        # suffixfreie Form. Weiterhin NUR exakte Zeilen - kein Fuzzy-Schlupfloch.
        ohne = KLAMMER_SUFFIX.sub("", term_en).strip()
        if ohne and ohne != term_en:
            zeilen = lookup_exakt(con, ohne, richtung="en_de")
    if not zeilen:
        return (term_en, False)
    beste = zeilen[0]
    return (beste["term_de"], bool(beste["offiziell"]))


def markiere(begriff_de: str, term_en: str, offiziell: bool) -> str:
    """Darstellung: 'Begriff (English)' bzw. 'Begriff* (English)' wenn nicht offiziell (S4/S5)."""
    stern = "" if offiziell else "*"
    return f"{begriff_de}{stern} ({term_en})"


# Kurze englische Lemmata sind zu oft Alltagswoerter ("Aid", "Web") und wuerden im
# englischen Fliesstext falsch anschlagen; ab 4 Zeichen ueberwiegt der Nutzen (Bane,
# Cloudkill ...). Bewusst konservativ - lieber einen Begriff weniger vorschlagen als
# Rauschen erzeugen.
_MIN_LEMMA = 4

# Englische Lemmata, die als Alltagswort im Fliesstext viel haeufiger vorkommen als der
# gleichnamige Spielbegriff - kontextfreies Matching mappt sie sonst falsch (beobachtet:
# 'chest' [Brustkorb] -> 'Kiste'; 'ready' [bereit] -> 'Vorbereiten'). Als reines
# Hinweisfeld ist Weglassen sicherer als ein irrefuehrender Vorschlag (S5).
#
# ZWEITE GRUPPE (15.07.2026): der SRD-Kernwortschatz-Seed (Fertigkeiten/Groessen/Kreaturentypen,
# importer/srd_kernwortschatz.py) ist quellenbelegt und fuer die EXAKTE Suche
# (foliant_uebersetze_begriff, Charakterbogen-Uebersetzer, wo das Feld den Kontext liefert)
# voll gueltig - aber viele Lemmata sind generische englische Woerter, die der KONTEXTFREIE
# Inline-Annotator falsch faerben wuerde: "Medium armor" (mittelschwere Ruestung, NICHT
# mittelgross), "Giant" (auch die Sprache Riesisch), "respect for nature" (nicht die Fertigkeit).
# Deshalb hier gesperrt - NUR fuers Inline-Matching, die exakte Suche sieht diese Liste nie.
# Selbst-identische Paare (Religion, Aberration, Ooze ...) filtert begriffe_im_text ohnehin;
# die vom Bestands-Audit als unbedenklich belegten (Perception, Stealth, Athletics, Persuasion,
# Intimidation, Animal Handling, Sleight of Hand) bleiben inline nutzbar.
_HOMONYM_STOP = frozenset({
    "chest", "ready", "bear", "fell", "will", "arms", "wills",
    # Groessen (als Adjektiv allgegenwaertig)
    "tiny", "small", "medium", "large", "huge", "gargantuan",
    # Kreaturentypen mit generischer Alltagsbedeutung
    "beast", "celestial", "dragon", "elemental", "fey", "fiend", "giant", "humanoid", "plant",
    "undead",
    # Fertigkeiten mit generischer Alltagsbedeutung (EN != DE)
    "acrobatics", "arcana", "deception", "history", "insight", "investigation", "medicine",
    "nature", "performance", "survival",
    # 2024-Aktionsnamen (seed_aktionen): als Alltagswoerter allgegenwaertig - nur die EXAKTE
    # Suche darf sie nutzen, nie der kontextfreie Inline-Annotator
    "attack", "dash", "disengage", "dodge", "help", "hide", "influence", "magic", "search",
    "study", "utilize",
})


def begriffe_im_text(con: sqlite3.Connection, text: str, *,
                     nur_offiziell: bool = True, max_treffer: int = 40) -> list[dict]:
    """Finde Glossar-Begriffe, deren ENGLISCHES Lemma als ganzes Wort im (englischen)
    `text` vorkommt, und liefere je Begriff die kanonisch beste Zeile
    ({term_en, term_de, offiziell, ...}, alphabetisch nach term_en).

    Zweck (S3/S5): Bei nur englisch vorliegenden Regeltexten bekommt das Modell die
    AMTLICHEN deutschen Begriffe INLINE mitgeliefert (Todeswolke, Verderben ...), statt
    sie einzeln nachschlagen zu muessen - genau die Luecke, an der eine Antwort sonst
    englisch stehen bleibt. `nur_offiziell` (Default) haelt die Liste auf belegte
    Begriffe; alles andere markiert das Modell selbst mit * (S5).

    Bewusst NUR Substring- + Wortgrenzen-Treffer (kein Fuzzy, SYN-P0-001): Aehnlichkeit
    allein macht zwei Begriffe nicht zum selben Konzept."""
    if not text:
        return []
    text_low = text.lower()
    beste: dict[str, dict] = {}
    for z in _alle_zeilen(con):                      # SYN-P2-004: gecacht
        en = z["term_en"]
        if not en or len(en) < _MIN_LEMMA or en.lower() in _HOMONYM_STOP:
            continue
        if nur_offiziell and not z["offiziell"]:
            continue
        if not z["term_de"] or norm_begriff(en) == norm_begriff(z["term_de"]):
            continue                                  # keine echte Uebersetzung -> uninteressant
        enl = en.lower()
        if enl not in text_low:                       # schneller C-Vortest vor dem Regex
            continue
        vorher = beste.get(enl)
        if vorher is None or _auswahlschluessel(z) < _auswahlschluessel(vorher):
            beste[enl] = z
    treffer = [z for z in beste.values()
               if re.search(r"\b" + re.escape(z["term_en"]) + r"\b", text, re.IGNORECASE)]
    treffer.sort(key=lambda z: z["term_en"].lower())
    return treffer[:max_treffer]

# --- Namensrelevanz -------------------------------------------------------
# Am 30.07.2026 aus app/tools/nachschlagen.py hierher gezogen. Sie gehoert hierhin:
# ihre Schwelle IST FUZZY_NAME (eine Zeile tiefer), ihr Vergleich laeuft ueber
# norm_begriff und KLAMMER_SUFFIX, und sie war die EINZIGE Stelle, an der sich Such-
# und Detailpfad beruehrten - erst nach dem Umzug liessen die beiden sich trennen.

# Namensrelevanz eines Kandidaten (#1). Wert und Begruendung in app/glossar.py, wo alle
# vier Fuzzy-Schwellen des Projekts zusammen stehen (Befund E5).
_NAME_MIN = FUZZY_NAME

def _name_score(k: dict, ziele: set[str]) -> float:
    """Relevanz des Kandidatennamens zur Anfrage (0-100): exakt = 100, sonst der beste
    rapidfuzz.ratio gegen die (normalisierten) Anfrage-Varianten `ziele`. Trennt echte
    Namenstreffer von blossen Body-Erwaehnungen (deren Name gar nicht passt).

    KEIN Praefix-Kurzschluss (Befund 30.07.2026): 'n.startswith(z) or z.startswith(n)'
    gab JEDEM Praefix 100.0, ohne Mindestlaenge - 'Elf' war damit ein voller Namenstreffer
    auf 'Elfenruestung', und der Detailpfad lieferte den Fremdeintrag als belegte Antwort
    aus (Verstoss gegen B1, die Anti-Halluzinations-Regel). Die abgedeckten ECHTEN Faelle
    - Wortrisse und OCR-Verstuemmelungen um ein bis zwei Zeichen - traegt fuzz.ratio
    ohnehin: ein echter Praefix erreicht 2*len(kurz)/(len(kurz)+len(lang))*100, liegt also
    ab rund 82 % Namensdeckung ueber der Schwelle von 90. Genau die kurzen, unspezifischen
    Praefixe fallen heraus, und nur die."""
    namen = _eintrag_namen(k)
    if namen & ziele:
        return 100.0
    best = 0.0
    for n in namen:
        for z in ziele:
            if not n or not z:
                continue
            best = max(best, fuzz.ratio(n, z))
    return best

def _eintrag_namen(k: dict) -> set[str]:
    """Namensvarianten eines Eintrags fuer den Exakt-Vergleich, kanonisch normalisiert
    (glossar.norm_begriff: case-/diakritika-/NFD-fest - PDF-Namen kommen teils
    NFD-dekomponiert an, S11/A3). Das srd-de-Namensschema '<Klasse>-Unterklasse: <Name>'
    zaehlt auch mit dem blanken Unterklassen-Namen als exakt - sonst gewinnt bei
    foliant_hol_eintrag("klasse", 'Champion') der englische Open5e-Eintrag (S10). Klammer-Suffixe
    zaehlen zusaetzlich OHNE Zusatz (SYN-P0-002)."""
    namen = {norm_begriff(k["name_de"]), norm_begriff(k["name_en"])}
    m = re.match(r".+-unterklasse:\s*(.+)$", norm_begriff(k["name_de"]))
    if m:
        namen.add(m.group(1).strip())
    for n in list(namen):
        ohne_zusatz = KLAMMER_SUFFIX.sub("", n).strip()
        if ohne_zusatz:
            namen.add(ohne_zusatz)
    return namen - {""}
