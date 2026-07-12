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

_FUZZY_CUTOFF = 88.0


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

# SYN-P2-004 (codex TECH-013): jeder Glossarpfad (lookup, exakte_entsprechungen,
# _brueckennamen) las bisher die KOMPLETTE Tabelle pro Aufruf - eine Suche loest 5-8
# Voll-Scans aus, die mit dem Vollseeding (~1.400 Zeilen) linear teurer werden. Cache
# je (DB-Datei, mtime, Zeilenzahl): unveraenderte DB -> ein Scan, danach RAM. Der
# Schluessel invalidiert automatisch nach jedem Import (mtime + count aendern sich).
_GLOSSAR_CACHE: dict[tuple, list[dict]] = {}


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
        _GLOSSAR_CACHE[sig] = cached
    return cached


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
    exakt = [{**z, "match": "exakt"} for z in alle if _norm(z[spalte]) == n]
    # S11: Flexions-/Schreibvarianten IMMER dazunehmen ("Gelegenheitsangriff" muss auch die
    # Plural-Zeile "Gelegenheitsangriffe" treffen, selbst wenn eine Abkuerzungszeile exakt
    # passt). Exakte Treffer bleiben vorn.
    namen: dict[str, list[dict]] = {}
    for z in alle:
        if z[spalte]:
            namen.setdefault(z[spalte], []).append(z)
    # fuzz.ratio (voller Levenshtein), NICHT WRatio: dessen Substring-Komponente wuerde
    # 'Feuer' auf 'Feuerball' mappen und vage Begriffe faelschlich 'exakt' machen (B4!).
    # ratio toleriert genau das Gewollte: Flexion/kleine Varianten (Wurf<->Wuerfe ~97).
    passend = process.extract(begriff, list(namen.keys()), scorer=fuzz.ratio,
                              processor=_norm, score_cutoff=_FUZZY_CUTOFF, limit=5)
    fuzzy = [{**z, "match": "fuzzy", "score": round(score, 1)}
             for name, score, _i in passend for z in namen[name]
             if _norm(z[spalte]) != n]

    def sortschluessel(z: dict) -> tuple:
        # A9 - dokumentierte KANONISCHE AUSWAHLREGEL (S3/S8), in dieser Reihenfolge:
        #   1. offizielle Begriffe vor inoffiziellen (S6),
        #   2. neuere belegte Edition vor aelterer, UNBEKANNTE Edition ganz hinten
        #      (S8: der neuere offizielle Begriff gewinnt; nichts wird als 2024 geraten),
        #   3. Begriffe mit konkretem Buch-/Glossar-Beleg vor blossen Community-Zeilen,
        #   4. alphabetisch NUR als letzter Determinismus-Anker.
        quelle = z.get("quelle") or ""
        belegt = 0 if ("Ulisses" in quelle or "buch" in quelle.lower()
                       or (quelle and "Community" not in quelle
                           and quelle != "abkuerzung")) else 1
        return (-int(z["offiziell"] or 0),
                0 if z["edition_quelle"] else 1,          # unbekannte Edition nach hinten
                -(int(z["edition_quelle"]) if str(z["edition_quelle"] or "").isdigit() else 0),
                belegt, z["term_de"] or "")

    return sorted(exakt, key=sortschluessel) + sorted(fuzzy, key=sortschluessel)


def term_de(con: sqlite3.Connection, term_en: str) -> tuple[str, bool]:
    """Liefert (deutscher_begriff, offiziell). offiziell=False -> Aufrufer setzt '*' (S5).
    Kein EXAKTER Glossar-Treffer -> (term_en, False): es gibt (noch) keine belegte deutsche
    Entsprechung; der Aufrufer nutzt dann eine markierte deutsche Wiedergabe (S3 Stufe 4).
    Fuzzy-Zeilen zaehlen hier NIE (SYN-P0-001: sonst wird ein aehnlicher FREMDER Begriff
    zur 'offiziellen' Uebersetzung - Aktionen -> Reaktionen)."""
    zeilen = [z for z in lookup(con, term_en, richtung="en_de") if z["match"] == "exakt"]
    if not zeilen:
        return (term_en, False)
    beste = zeilen[0]
    return (beste["term_de"], bool(beste["offiziell"]))


def markiere(begriff_de: str, term_en: str, offiziell: bool) -> str:
    """Darstellung: 'Begriff (English)' bzw. 'Begriff* (English)' wenn nicht offiziell (S4/S5)."""
    stern = "" if offiziell else "*"
    return f"{begriff_de}{stern} ({term_en})"
