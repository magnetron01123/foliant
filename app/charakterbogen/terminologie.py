"""In-Prozess-Terminologie: löst feste D&D-Begriffe über die BESTEHENDE Foliant-Glossar-
Logik auf (app.glossar) - KEIN zweites Glossar (AUFTRAG §8.1, KONZEPT §6).

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
    de, offiziell = glossar.term_de(con, en)
    if de == en:  # term_de gibt bei fehlendem exaktem Treffer die Eingabe unverändert zurück
        return None
    return glossar.markiere(de, en, offiziell)


def markiere_fallback(term_en: str, de_wiedergabe: str) -> str:
    """§5-Fallback: unbelegte, sinngemäße deutsche Wiedergabe -> 'de* (English)'."""
    return glossar.markiere((de_wiedergabe or "").strip() or term_en, term_en, False)
