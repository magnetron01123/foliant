"""Generische Reparatur zerlegter Eintragsnamen (Druck-/PDF-Textschicht-Schaeden) gegen die
AUTORITATIVE Namensliste der Quelle - das Inhaltsverzeichnis der PDF plus die bereits sauberen
Namen des Bestands. Kein festes corrupt->korrekt mehr: ein korrupter Name wird per Zeichen-
Multiset (Anagramm - die typischen Zerlege-Schaeden sind Umsortierung/Leerzeichen: 'Gar l gy'
-> 'Gargyl') ODER hoher rapidfuzz-Aehnlichkeit (verlorene Buchstaben: 'Belebtesgfie endes
Schwert' -> 'Belebtes fliegendes Schwert') einem Referenznamen zugeordnet - aber NUR bei
EINDEUTIGER, sicherer Zuordnung, sonst unberuehrt (nicht raten, B4). Skaliert auf jede neue
PDF-Quelle; die Quelle selbst ist die Autoritaet."""
from __future__ import annotations

import re
import unicodedata

_TOC_ZEILE = re.compile(r"^\s*(.+?)\s*\.{3,}\s*\d{1,4}\s*$")


def _fold(s: str | None) -> str:
    # Whitespace vereinheitlichen (geschuetztes Leerzeichen \xa0 u. a. -> normales, Mehrfach
    # kollabieren): sonst gilt dieselbe Bezeichnung mit anderem Leerzeichen faelschlich als
    # abweichend.
    s = re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip().lower()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _multiset(s: str | None) -> str:
    """Sortierte Buchstaben (ohne Leer-/Sonderzeichen, diakritika-gefaltet) - invariant gegen
    die Umsortierung/Leerzeichen der Zerlege-Schaeden."""
    return "".join(sorted(re.sub(r"[^a-z]", "", _fold(s))))


def toc_namen(pdf_pfad: str, seiten: int = 12) -> list[str]:
    """Namen aus dem Inhaltsverzeichnis einer PDF (Zeilen 'Name .... Seite') - die
    autoritative, saubere Namensliste der Quelle. Leere Liste, wenn fitz/Datei fehlt."""
    try:
        import fitz
    except ImportError:
        return []
    namen = []
    try:
        doc = fitz.open(pdf_pfad)
    except Exception:
        return []
    try:
        for p in range(min(seiten, len(doc))):
            for zeile in doc[p].get_text().split("\n"):
                m = _TOC_ZEILE.match(zeile)
                if m:
                    nm = m.group(1).strip()
                    if 2 <= len(nm) <= 60 and not nm.isdigit():
                        namen.append(nm)
    finally:
        doc.close()
    return sorted(set(namen))


def _entspacet(s: str) -> str:
    return _fold(s).replace(" ", "").replace("-", "")


def finde_korrektur(name: str, referenz: list[str], name_sauber,
                    toc_fold: frozenset = frozenset()) -> str | None:
    """Korrekter Referenzname fuer einen korrupten `name` ODER None - mit PRAEZISEN Signalen
    (KEIN blindes Fuzzy, das saubere aehnliche Namen wie 'Barbaren'/'Barden' verwechselt):

    1. Glyph-Zerlegung (Buchstaben umsortiert, hat Kurzfragmente wie 'l'/'pp' -> name_sauber
       schlaegt fehl): EINDEUTIGES Anagramm (gleiches Zeichen-Multiset). Saubere Komposita
       (Waechterschild/Schildwaechter) tragen KEINE Kurzfragmente und fallen hier nicht rein.
    2. Leerzeichen-Anomalie (name_sauber ok): gleiche ZEICHENSEQUENZ, nur Spaces/Bindestriche
       anders ('Kreischer pilz' -> 'Kreischerpilz'), UND das Ziel steht autoritativ im
       Inhaltsverzeichnis (toc_fold) - so bleibt die Richtung eindeutig und bloss unterschiedlich
       kodierte Leerzeichen/Singular-Plural-Paare aussen vor.
    Mehrdeutig/unsicher -> None (nicht raten, B4)."""
    if not name:
        return None
    if not name_sauber(name):
        ms = _multiset(name)
        ana = {r for r in referenz if r != name and _multiset(r) == ms}
        return next(iter(ana)) if len(ana) == 1 else None
    seq = _entspacet(name)
    if _fold(name) in toc_fold:
        return None                                   # bereits die autoritative Form
    # Ziel: gleiche Zeichensequenz (nur Leerzeichen anders), autoritativ im TOC, UND nach
    # Normalisierung ECHT verschieden - sonst waere es bloss ein anders kodiertes Leerzeichen
    # (regulaeres vs. geschuetztes '\xa0'), keine Korruption.
    kand = {r for r in referenz if r != name and _entspacet(r) == seq
            and _fold(r) in toc_fold and _fold(r) != _fold(name)}
    return next(iter(kand)) if len(kand) == 1 else None


def repariere(namen: list[str], referenz: list[str], name_sauber,
              toc_namen: list[str] | None = None) -> dict[str, str]:
    """{korrupt: korrekt} fuer alle sicher zuordenbaren Namen (Rest bleibt unberuehrt).
    `name_sauber(name)->bool`; `toc_namen`: die autoritativen Namen aus dem Inhaltsverzeichnis
    (Detektor 2 korrigiert nur AUF eine TOC-Form)."""
    toc_fold = frozenset(_fold(t) for t in (toc_namen or referenz))
    out: dict[str, str] = {}
    for nm in namen:
        ziel = finde_korrektur(nm, referenz, name_sauber, toc_fold)
        if ziel and ziel != nm:
            out[nm] = ziel
    return out
