"""Allgemeiner fi/fl-Ligatur-Resolver fuer Druck-PDF-Textschichten.

Browser-Druck-PDFs (DDB-Ausdrucke) verlieren die f-Ligaturen (fi/fl/ff/ffi/ffl) als U+FFFD.
ALGORITHMISCH statt per corrupt->korrekt-Liste: fuer jedes Wort mit GENAU EINEM � werden die
Ligatur-Einsetzungen generiert und gegen ein VOKABULAR geprueft. Genau eine gueltige
Einsetzung -> aufgeloest. Das Vokabular ist Pi-nativ (kein Mac-/Systemabhaengigkeit): eine
gebuendelte gemeinfreie englische Wortliste (Webster's web2, public domain) plus der eigene
Korpus (data/ligatur_vokabular.txt.gz, reproduzierbar aus den Quellen). Nicht im Vokabular
gefuehrte Eigennamen bekommt der Aufrufer ueber `zusatzvokabular` beigesteuert; echte
fi/fl-Doppeldeutigkeiten (flat/fiat) ueber `override`. Gilt fuer JEDE Quelle - Quellen ohne
� sind ein No-op. Ersetzt die frueheren per-Buch-Korrekturlisten (Prinzip: Logik statt
Einzelkorrektur; Kuratierung nur als Notfall-Vokabular/-Override)."""
from __future__ import annotations

import gzip
import re
from functools import lru_cache
from pathlib import Path

_LIGATUREN = ("fi", "fl", "ff", "ffi", "ffl")
_SUFFIXE = ("s", "es", "ed", "ing", "ly", "er", "ers", "ings", "ied", "ies", "est",
            "ic", "ical", "ically", "ation", "ations", "ement", "ements", "ely", "ness")
_TOKEN = re.compile(r"[A-Za-z]*�[A-Za-z]*")


@lru_cache(maxsize=1)
def _vokabular() -> frozenset:
    pfad = Path(__file__).with_name("wortlisten") / "ligatur_vokabular.txt.gz"
    with gzip.open(pfad, "rt", encoding="utf-8") as f:
        return frozenset(w.strip() for w in f if w.strip())


def _staerke(wort: str, vokab: frozenset) -> int | None:
    """Wie sicher ist `wort` ein echtes englisches Wort? 0 = DIREKT im Vokabular, 1 =
    lemmatisiert/Kompositum, None = unbekannt. Die Staerke trennt einen echten Treffer
    ('signifies' direkt) vom abgeleiteten Kauderwelsch ('signifles' nur ueber Fragmente) -
    so bleibt nur ein echtes fi/fl-Duell (beide DIREKT, z. B. flat/fiat) unentschieden."""
    w = wort.lower()
    if w in vokab:
        return 0
    for suf in _SUFFIXE:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            st = w[: -len(suf)]
            if st in vokab or st + "e" in vokab or st + "y" in vokab:
                return 1
            if len(st) >= 2 and st[-1] == st[-2] and st[:-1] in vokab:   # fitted -> fit
                return 1
    for i in range(3, len(w) - 2):                                       # seafloor, snowfields
        if w[:i] in vokab and (w[i:] in vokab or (w[i:].endswith("s") and w[i:-1] in vokab)):
            return 1
    return None


def _token_aufloesen(tok: str, vokab: frozenset) -> str | None:
    kand = [(lg, _staerke(tok.replace("�", lg), vokab)) for lg in _LIGATUREN]
    kand = [(lg, s) for lg, s in kand if s is not None]
    if not kand:
        return None
    beste = min(s for _lg, s in kand)
    top = [lg for lg, s in kand if s == beste]
    if len(top) == 1:
        return tok.replace("�", top[0])
    if not set(top) <= {"fi", "fl"}:               # ff-Familie eindeutiger als fi/fl-Duell
        for lg in ("ffi", "ffl", "ff", "fl", "fi"):
            if lg in top:
                return tok.replace("�", lg)
    return None                                    # echtes fi/fl-Duell (beide direkt) -> Aufrufer


def aufloesen(markdown: str, zusatzvokabular=frozenset(), override: dict | None = None) -> str:
    """Loest fi/fl-Ligaturen (U+FFFD) im Markdown auf. `zusatzvokabular`: korrekte Woerter,
    die das Vokabular (noch) nicht kennt (z. B. Setting-Eigennamen) - der Algorithmus loest
    ihre Ligaturen selbst. `override`: {korruptes_token: korrektes_wort} nur fuer echte
    Doppeldeutigkeiten, die kein Algorithmus entscheiden kann (Notfall)."""
    if "�" not in markdown:
        return markdown                            # No-op fuer saubere Quellen
    vokab = _vokabular() | frozenset(w.lower() for w in zusatzvokabular)
    override = override or {}

    def ersetze(m: re.Match) -> str:
        tok = m.group(0)
        if tok in override:
            return override[tok]
        if tok.count("�") != 1 or not re.search(r"[a-z]", tok):
            return tok                             # Deko-Runs / reine Grossbuchstaben: nicht anfassen
        return _token_aufloesen(tok, vokab) or tok

    return _TOKEN.sub(ersetze, markdown)
