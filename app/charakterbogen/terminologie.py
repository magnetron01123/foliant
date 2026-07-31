"""In-Prozess-Terminologie: löst feste D&D-Begriffe über die BESTEHENDE Foliant-Glossar-
Logik auf (app.glossar) - KEIN zweites Glossar (SPEC.md §14, CONCEPT.md §7).

Liefert die EINE §5-Anzeigeform:  'Deutsch (English)'  bzw.  'Deutsch* (English)'.
Nur EXAKTE Glossar-Treffer gelten (Fuzzy zählt nie, SYN-P0-001) - genau wie
`foliant_uebersetze_begriff`. Ohne exakten Treffer -> None: der Aufrufer lässt den
deutschen Begriff (durch das Sprachmodell) bilden und markiert ihn mit '*'.
"""
from __future__ import annotations

import sqlite3

from app import glossar


def aufloesen(con: sqlite3.Connection, term_en: str) -> str | None:
    """§5-Anzeige für einen festen Begriff bei exaktem, belegtem Glossar-Treffer.
    None = kein belegter deutscher Begriff -> Fallback über das Sprachmodell + `markiere_fallback`."""
    en = (term_en or "").strip()
    if not en:
        return None
    treffer = glossar.term_de(con, en)
    if treffer is None:          # kein belegter deutscher Begriff -> Aufrufer + LLM + '*'
        return None
    de, offiziell = treffer
    if de == en:
        # Deutsch und Englisch sind gleich (Aasimar, Aboleth, Alarm, Paladin, Charisma -
        # im Bestand 110 OFFIZIELLE Zeilen). Das ist ein BELEGTER Begriff, also weder
        # Stern noch Klammer: "Aasimar (Aasimar)" wäre albern, "Aasimar*" schlicht falsch.
        # Bis zum 31.07.2026 verwechselte diese Stelle die Gleichheit mit "kein Beleg"
        # und lieferte None - der Bogen druckte dann "Aasimar* (Aasimar)" und behauptete
        # damit, es gebe keine offizielle deutsche Fassung (Verstoß gegen SPEC.md T3/C1).
        return de if offiziell else glossar.markiere(de, en, offiziell)
    return glossar.markiere(de, en, offiziell)


def markiere_fallback(term_en: str, de_wiedergabe: str) -> str:
    """§5-Fallback: unbelegte, sinngemäße deutsche Wiedergabe -> 'de* (English)'."""
    return glossar.markiere((de_wiedergabe or "").strip() or term_en, term_en, False)
