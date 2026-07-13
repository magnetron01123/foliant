"""Facetten-Ableitung aus dem verbatim body_md (Zauber-Grad/Schule/Klassen, Monster-HG).

Warum aus dem Text und nicht aus zauber_meta/monster_meta: die Meta-Tabellen sind auf dem
bedienten Bestand LEER (nur der Open5e-Import befuellt sie, und der DE-gewinnende Dedup
zeigt sie nicht). Die Werte stehen aber zuverlaessig im Kopf des Regeltexts -
"_Hervorrufungszauber 3. Grades (Magier, Zauberer)_", "_Zaubertrick der Hervorrufung
(Hexenmeister)_", "**HG** 1". Das ist REINE Ableitung aus vorhandenem Text (kein Raten):
ohne erkennbares Muster -> None/leere Liste (B1). Deutsch-first, mit englischem Fallback.
"""
from __future__ import annotations

import re

from app.glossar import norm_begriff as _n

# --- Zauber-Grad -------------------------------------------------------------
# Ohne \b: der Markdown-Italic-Unterstrich ('_Zaubertrick') ist ein Wortzeichen und
# haette die Wortgrenze verschluckt. 'zaubertrick'/'cantrip' sind als Substring eindeutig.
_ZAUBERTRICK = re.compile(r"zaubertrick|cantrip", re.IGNORECASE)
_GRAD_DE = re.compile(r"(\d+)\.\s*Grad")                       # srd-de: "3. Grades"
_LEVEL_FELD = re.compile(r"level:?\**\s*(\d+)", re.IGNORECASE)  # Open5e: "**Level:** 3"
_GRAD_EN = re.compile(r"(\d+)\s*(?:st|nd|rd|th)[-\s]*level", re.IGNORECASE)  # DDB: "3rd-level"


def zauber_grad(body: str | None) -> int | None:
    """Grad eines Zaubers aus dem Textkopf. 0 = Zaubertrick (Cantrip). None ohne Muster.
    Deckt srd-de ('3. Grades'/'Zaubertrick'), Open5e ('**Level:** 3') und DDB
    ('3rd-level') ab."""
    if not body:
        return None
    kopf = body[:200]
    m = _GRAD_DE.search(kopf) or _LEVEL_FELD.search(kopf) or _GRAD_EN.search(kopf)
    if m:
        g = int(m.group(1))
        return g if 0 <= g <= 9 else None
    if _ZAUBERTRICK.search(kopf):
        return 0
    return None


def zauber_kurz(body: str | None) -> str | None:
    """Kompakte Grad-Anzeige fuer knappe Treffer ('Zaubertrick' / 'Grad 3')."""
    g = zauber_grad(body)
    if g is None:
        return None
    return "Zaubertrick" if g == 0 else f"Grad {g}"


# --- Zauber-Schule (kanonischer Schluessel <- DE/EN-Synonyme) ----------------
_SCHULEN: dict[str, set[str]] = {
    "bannzauber":   {"bannzauber", "abjuration"},
    "beschwoerung": {"beschworung", "conjuration"},          # norm entfernt Diakritika
    "erkenntnis":   {"erkenntnis", "erkenntnismagie", "divination"},
    "verzauberung": {"verzauberung", "enchantment"},
    "hervorrufung": {"hervorrufung", "evocation"},
    "illusion":     {"illusion"},
    "nekromantie":  {"nekromantie", "necromancy"},
    "verwandlung":  {"verwandlung", "transmutation"},
}
_SCHULE_ANZEIGE = {
    "bannzauber": "Bannzauber", "beschwoerung": "Beschwörung",
    "erkenntnis": "Erkenntnis", "verzauberung": "Verzauberung",
    "hervorrufung": "Hervorrufung", "illusion": "Illusion",
    "nekromantie": "Nekromantie", "verwandlung": "Verwandlung",
}


def schule_schluessel(eingabe: str | None) -> str | None:
    """Nutzereingabe ('Hervorrufung', 'Evocation') -> kanonischer Schluessel; None unbekannt."""
    if not eingabe:
        return None
    n = _n(eingabe)
    for key, syns in _SCHULEN.items():
        if n == key or n in syns or any(n in s or s in n for s in syns):
            return key
    return None


def schulen_anzeige() -> list[str]:
    """Waehlbare Schulen (deutsche Anzeigenamen) - fuer Fehlermeldungen/Discovery."""
    return [_SCHULE_ANZEIGE[k] for k in _SCHULEN]


def zauber_schule(body: str | None) -> str | None:
    """Kanonischer Schul-Schluessel aus dem Textkopf; None ohne Muster."""
    if not body:
        return None
    kopf = _n(body[:200])
    for key, syns in _SCHULEN.items():
        if any(s in kopf for s in syns):
            return key
    return None


def schule_anzeige(schluessel: str | None) -> str | None:
    return _SCHULE_ANZEIGE.get(schluessel) if schluessel else None


# --- Zauber-Klassen (srd-de: Klammern im Kopf; Open5e: 'Classes:'-Feld) -------
_KLASSEN_PARENS = re.compile(r"\(([^)]{2,70})\)")
_KLASSEN_FELD = re.compile(r"classes?:?\**\s*([A-Za-z ,/&]+)", re.IGNORECASE)
_KLASSEN_SYN: dict[str, str] = {}
for _kanon, _formen in {
    "barbar": ("barbar", "barbarian"), "barde": ("barde", "bard"),
    "kleriker": ("kleriker", "cleric"), "druide": ("druide", "druid"),
    "kaempfer": ("kampfer", "fighter"), "moench": ("monch", "monk"),
    "paladin": ("paladin",), "waldlaeufer": ("waldlaufer", "ranger"),
    "schurke": ("schurke", "rogue"), "zauberer": ("zauberer", "sorcerer"),
    "hexenmeister": ("hexenmeister", "warlock"), "magier": ("magier", "wizard"),
}.items():
    for _f in _formen:
        _KLASSEN_SYN[_f] = _kanon


def _klasse_kanon(begriff: str) -> str:
    return _KLASSEN_SYN.get(_n(begriff), _n(begriff))


def zauber_klassen(body: str | None) -> list[str]:
    """Klassenliste aus dem Kopf: srd-de aus der Klammer ('(Magier, Zauberer)'),
    Open5e aus dem Feld ('**Classes:** Warlock')."""
    if not body:
        return []
    kopf = body[:200]
    m = _KLASSEN_PARENS.search(kopf) or _KLASSEN_FELD.search(kopf)
    if not m:
        return []
    roh = re.split(r"[,/&]| und ", m.group(1))
    return [t.strip() for t in roh if t.strip()]


def klasse_passt(klassen: list[str], eingabe: str) -> bool:
    """Trifft die (deutsche) Klassen-Eingabe eine der geparsten Klassen? EN/DE-tolerant."""
    ziel = _klasse_kanon(eingabe)
    return any(_klasse_kanon(k) == ziel for k in klassen)


# --- Schadensart (Substring im ganzen Body, DE/EN) ---------------------------
_SCHADEN_SYN: dict[str, tuple[str, ...]] = {
    "feuer": ("feuerschaden", "fire damage"),
    "kaelte": ("kalteschaden", "cold damage"),
    "blitz": ("blitzschaden", "lightning damage"),
    "saeure": ("saureschaden", "acid damage"),
    "gift": ("giftschaden", "poison damage"),
    "nekrotisch": ("nekrotischer schaden", "nekrotischen schaden", "necrotic damage"),
    "gleissend": ("gleissender schaden", "gleissenden schaden", "radiant damage"),
    "psychisch": ("psychischer schaden", "psychischen schaden", "psychic damage"),
    "donner": ("donnerschaden", "thunder damage"),
    "kraft": ("kraftschaden", "wuchtschaden der kraft", "force damage"),
    "wucht": ("wuchtschaden", "bludgeoning damage"),
    "stich": ("stichschaden", "piercing damage"),
    "hieb": ("hiebschaden", "slashing damage"),
}


def schadensart_schluessel(eingabe: str | None) -> str | None:
    if not eingabe:
        return None
    n = _n(eingabe)
    for key, formen in _SCHADEN_SYN.items():
        if n == key or any(n in f or f.split()[0] == n for f in formen):
            return key
    return None


def schadensarten_anzeige() -> list[str]:
    return list(_SCHADEN_SYN)


def hat_schadensart(body: str | None, schluessel: str) -> bool:
    if not body:
        return False
    n = _n(body)
    return any(f in n for f in _SCHADEN_SYN.get(schluessel, ()))


# --- Monster-HG --------------------------------------------------------------
# Wert kann Bruch ('1/4'), Dezimal (Open5e: '0.125') oder ganzzahlig sein.
_HG = (
    re.compile(r"\bHG\b[^0-9]{0,4}(\d+(?:[./]\d+)?)"),
    re.compile(r"Herausforderung(?:sgrad)?\D{0,6}(\d+(?:[./]\d+)?)", re.IGNORECASE),
    re.compile(r"\bCR\b[^0-9]{0,4}(\d+(?:[./]\d+)?)"),
    re.compile(r"Challenge\D{0,6}(\d+(?:[./]\d+)?)", re.IGNORECASE),
)
# Open5e fuehrt HG als Dezimalzahl; kanonisch ist die Bruchform (srd-de) -> vereinheitlichen,
# damit dieselbe Kreatur ueber beide Fassungen denselben HG traegt.
_HG_DEZIMAL = {"0.125": "1/8", "0.25": "1/4", "0.5": "1/2"}


def monster_hg(body: str | None) -> str | None:
    """Herausforderungsgrad (HG/CR) aus dem Statblock, z. B. '1' oder '1/4'. Dezimal-CR
    (Open5e '0.125') wird zur Bruchform normalisiert. None ohne Muster."""
    if not body:
        return None
    kopf = body[:900]
    for pat in _HG:
        m = pat.search(kopf)
        if m:
            return _HG_DEZIMAL.get(m.group(1), m.group(1))
    return None


def hg_kurz(body: str | None) -> str | None:
    hg = monster_hg(body)
    return f"HG {hg}" if hg else None


def hg_passt(body: str | None, wunsch: str) -> bool:
    """Trifft der geparste HG den Wunschwert ('1', '1/4', '0')? Exakter String-Vergleich."""
    h = monster_hg(body)
    return h is not None and h == wunsch.strip()


# --- Monster-Typ (aus der Statblock-Kopfzeile '_Kleines Feenwesen (...), ...') ------
_TYPEN: dict[str, set[str]] = {
    "aberration":    {"aberration"},
    "tier":          {"tier", "beast"},
    "himmelswesen":  {"himmelswesen", "celestial"},
    "konstrukt":     {"konstrukt", "construct"},
    "drache":        {"drache", "dragon"},
    "elementar":     {"elementar", "elemental"},
    "feenwesen":     {"feenwesen", "fey"},
    "unhold":        {"unhold", "fiend"},
    "riese":         {"riese", "giant"},
    "humanoider":    {"humanoide", "humanoider", "humanoid"},
    "monstrositaet": {"monstrositat", "monstrosity"},
    "schlick":       {"schlick", "ooze"},
    "pflanzenwesen": {"pflanzenwesen", "plant"},
    "untoter":       {"untoter", "untote", "undead"},
}
_TYP_ANZEIGE = {
    "aberration": "Aberration", "tier": "Tier", "himmelswesen": "Himmelswesen",
    "konstrukt": "Konstrukt", "drache": "Drache", "elementar": "Elementar",
    "feenwesen": "Feenwesen", "unhold": "Unhold", "riese": "Riese",
    "humanoider": "Humanoider", "monstrositaet": "Monstrosität", "schlick": "Schlick",
    "pflanzenwesen": "Pflanzenwesen", "untoter": "Untoter",
}


def typ_schluessel(eingabe: str | None) -> str | None:
    if not eingabe:
        return None
    n = _n(eingabe)
    for key, syns in _TYPEN.items():
        if n == key or n in syns:
            return key
    return None


def typen_anzeige() -> list[str]:
    return [_TYP_ANZEIGE[k] for k in _TYPEN]


def typ_anzeige(schluessel: str | None) -> str | None:
    return _TYP_ANZEIGE.get(schluessel) if schluessel else None


def monster_typ(body: str | None) -> str | None:
    """Kreaturentyp aus der Statblock-Kopfzeile; None ohne Muster. Wortgrenzen, damit
    'Tier' nicht in einem laengeren Wort faelschlich anschlaegt."""
    if not body:
        return None
    kopf = _n(body[:150])
    for key, syns in _TYPEN.items():
        if any(re.search(r"\b" + s + r"\b", kopf) for s in syns):
            return key
    return None


# Ruestungsklasse/Trefferpunkte aus dem Statblock-Kopf - fuer den Struktur-Abgleich
# derselben Kreatur ueber die srd-de-/Open5e-Fassung hinweg (RK=AC, TP=HP). Doppelpunkt/
# Sterne/Leerzeichen zwischen Label und Zahl tolerieren ('**RK** 12', '**AC:** 12').
_RK = re.compile(r"\b(?:RK|AC)\b[:*\s]{0,6}(\d+)")
_TP = re.compile(r"\b(?:TP|HP)\b[:*\s]{0,6}(\d+)")


def monster_rk(body: str | None) -> str | None:
    if not body:
        return None
    m = _RK.search(body[:900])
    return m.group(1) if m else None


def monster_tp(body: str | None) -> str | None:
    if not body:
        return None
    m = _TP.search(body[:900])
    return m.group(1) if m else None


def monster_statschluessel(body: str | None) -> tuple:
    """Struktur-Fingerabdruck eines Statblocks (typ, hg, rk, tp) - identisch fuer dieselbe
    Kreatur in der deutschen und englischen SRD-Fassung. None-Anteile heissen 'unvollstaendig
    -> nicht fuer den Abgleich geeignet'."""
    return (monster_typ(body), monster_hg(body), monster_rk(body), monster_tp(body))
