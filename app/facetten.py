"""Facetten-Ableitung aus dem verbatim body_md (Zauber-Grad/Schule/Klassen, Monster-HG).

DER TEXT IST DIE AUTORITAET. Die Werte stehen zuverlaessig im Kopf des Regeltexts -
"_Hervorrufungszauber 3. Grades (Magier, Zauberer)_", "_Zaubertrick der Hervorrufung
(Hexenmeister)_", "**HG** 1". Das ist REINE Ableitung aus vorhandenem Text (kein Raten):
ohne erkennbares Muster -> None/leere Liste (B1). Deutsch-first, mit englischem Fallback.

Verhaeltnis zu den Meta-Tabellen: zauber_meta/monster_meta/gegenstand_meta sind aus GENAU
diesen Funktionen abgeleitet (importer/facetten_seeder.py ruft sie), nicht umgekehrt. Ein
gespeicherter Wert kann dem Text deshalb nie widersprechen - er ist eine Vorberechnung,
kein zweiter Wahrheitsanspruch. Wo Tempo zaehlt, filtert der Meta-Vorfilter damit vor
(app/tools/suche.py), und das Textpraedikat behaelt trotzdem das letzte Wort.
(Bis Phase 3 stand hier, die Tabellen seien auf dem bedienten Bestand leer - das war der
Befund C1 und ist seit dem 28.07.2026 behoben: Deckung 94/91/34 %.)

Die Zuordnung Kategorie -> Tabelle/Spalten steht unten in META_TABELLEN - EINE Definition
fuer Schreiber (facetten_seeder) und Leser (nachschlagen).
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
# 'bannmagie' und 'weissagung' ergaenzt (31.07.2026): Es gibt ein ZWEITES Schul-Register,
# `importer/srd_zauberbruecken.SCHULEN`, und die beiden fuehrten unterschiedliches deutsches
# Vokabular fuer dieselben acht Schulen. Am Bestand nachgemessen ist die Divergenz heute
# fast folgenlos ('Bannzauber' 48x gegen 'Bannmagie' 1x) - aber ein deutsches PHB 2024
# traefe genau hier auf.
#
# Ehrlich zur Wirkung: Von 727 Zaubereintraegen aendert sich GENAU EINER, und kein
# einziger bekommt eine Schule, der vorher keine hatte. Der eine ist "Die Schulen der
# Magie" - die TABELLE aller acht Schulen, einer der 24 bekannten Kapitelabschnitte mit
# kategorie='zauber' (BACKLOG.md par. 3). Sein Kopf nennt alle Schulen; welche zuerst
# trifft, ist Zufall der Reihenfolge. Er stand auf 'beschwoerung' und steht jetzt auf
# 'bannzauber' - beides gleich bedeutungslos fuer eine Uebersichtstabelle.
#
# Bewusst NUR additiv und nur auf DIESER Seite: `srd_zauberbruecken.SCHULEN` speist den
# Zauberkopf-Fingerabdruck, dessen Regexe laut CONCEPT.md par. 12 unberuehrt bleiben, weil
# jede Aenderung daran geseedete Glossar-Paare verschiebt.
_SCHULEN: dict[str, set[str]] = {
    "bannzauber":   {"bannzauber", "bannmagie", "abjuration"},
    "beschwoerung": {"beschworung", "conjuration"},          # norm entfernt Diakritika
    "erkenntnis":   {"erkenntnis", "erkenntnismagie", "weissagung", "divination"},
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
    """Nutzereingabe ('Hervorrufung', 'Evocation') -> kanonischer Schluessel; None unbekannt.

    ZWEI Runden, exakt vor tolerant (Befund 30.07.2026). Vorher lief beides in einer
    Schleife, und die enthielt mit `n in s` die Richtung 'Eingabe ist Teil eines Synonyms'.
    Damit gewann die DICT-Reihenfolge statt der Treffergenauigkeit: 'o' wurde zu
    'bannzauber' (steckt in 'abjuration'), 'ung' zu 'beschwoerung'. Eine ungueltige Facette
    wurde so still auf eine GUELTIGE umgebogen, und die Suche lieferte eine sauber
    zitierte Antwort auf eine nicht gestellte Frage - dieselbe Fehlerklasse, gegen die
    SYN-P0-006 angetreten ist, nur im Facetten-Pfad. None loest jetzt den strukturierten
    'fehler' mit der Liste der gueltigen Werte aus, wie bei jedem anderen Enum."""
    if not eingabe:
        return None
    n = _n(eingabe)
    for key, syns in _SCHULEN.items():
        if n == key or n in syns:
            return key
    # Tolerant nur in EINER Richtung: das Synonym steckt in einer laengeren Eingabe
    # ('Hervorrufungszauber' -> hervorrufung). Die Gegenrichtung war der Fehler.
    for key, syns in _SCHULEN.items():
        if any(s in n for s in syns):
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


_KANON_KLASSEN = set(_KLASSEN_SYN.values())      # die zwoelf Klassen, kanonisch


def klassen_anzeige() -> list[str]:
    """Die zwoelf kanonischen Klassen - fuer Fehlermeldungen/Discovery, wie
    schulen_anzeige() und schadensarten_anzeige()."""
    return sorted(_KANON_KLASSEN)


def _klasse_kanon(begriff: str) -> str:
    return _KLASSEN_SYN.get(_n(begriff), _n(begriff))


def zauber_klassen(body: str | None) -> list[str]:
    """Klassenliste aus dem Kopf: srd-de aus der Klammer ('(Magier, Zauberer)'),
    Open5e aus dem Feld ('**Classes:** Warlock').

    Das BESCHRIFTETE Feld hat Vorrang vor der Klammer. Umgekehrt (bis 28.07.2026) gewann
    bei Open5e die erste Klammer im Kopf - und das ist dort die Materialkomponente:
    'Alarm' lieferte ['a bell and silver wire'] statt ['Ranger', 'Wizard'], womit der
    klasse-Filter fuer den gesamten englischen Bestand ins Leere lief. srd-de aendert sich
    nicht: dort gibt es kein 'Classes:'-Feld, die Klammer greift weiter."""
    if not body:
        return []
    kopf = body[:200]
    feld = _KLASSEN_FELD.search(kopf)
    m = feld or _KLASSEN_PARENS.search(kopf)
    if not m:
        return []
    roh = re.split(r"[,/&]| und ", m.group(1))
    namen = [t.strip() for t in roh if t.strip()]
    # Die Klammer ist eine POSITIONS-Vermutung, kein beschriftetes Feld - sie darf nur
    # gelten, wenn wenigstens ein Eintrag eine der zwoelf Klassen ist. Sonst geben wir
    # dem Modell Beliebiges als Klassenliste aus: '(Ritual)' aus den dt. 2014-Koepfen
    # ergab ['Ritual'], die Materialkomponente '(ein Stueck Fell)' ihren Wortlaut.
    if not feld and not any(_klasse_kanon(n) in _KANON_KLASSEN for n in namen):
        return []
    return namen


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
    """Nutzereingabe ('Feuer', 'fire', 'Wuchtschaden') -> kanonischer Schluessel.

    Exakt vor tolerant, aus demselben Grund wie bei schule_schluessel - hier hatte die
    Reihenfolge sogar auf einer GUELTIGEN Eingabe Folgen: 'wucht' lieferte 'kraft',
    weil `n in f` gegen die Form 'wuchtschaden der kraft' anschlug und 'kraft' im Dict
    vor 'wucht' steht. Wer nach Wuchtschaden filterte, bekam Kraftschaden - sauber
    zitiert und ohne jeden Hinweis. 'schaden' und 'damage' wurden zu 'feuer'."""
    if not eingabe:
        return None
    n = _n(eingabe)
    for key, formen in _SCHADEN_SYN.items():
        if n == key or n in formen:
            return key
    # Tolerant: das erste Wort einer Form ('fire damage' -> 'fire').
    for key, formen in _SCHADEN_SYN.items():
        if any(f.split()[0] == n for f in formen):
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
    (Open5e '0.125') wird zur Bruchform normalisiert, ganzzahliges Dezimal ('4.0') zur
    Ganzzahl - sonst verfehlt hg_passt('4') die Open5e-Fassung und der Monster-
    Strukturabgleich haelt dieselbe Kreatur fuer zwei verschiedene. None ohne Muster."""
    if not body:
        return None
    kopf = body[:900]
    for pat in _HG:
        m = pat.search(kopf)
        if m:
            wert = _HG_DEZIMAL.get(m.group(1), m.group(1))
            if re.fullmatch(r"\d+\.0+", wert):
                wert = wert.split(".")[0]
            return wert
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


# Die sechs Attributswerte in fester D&D-Reihenfolge (STÄ, GES, KON, INT, WEI, CHA). Sie
# sind ZAHLEN und damit uebersetzungsinvariant - der belastbarste Diskriminator, um
# wertegleiche, aber verschiedene Kreaturen zu trennen (Goblinkrieger 8/15/10/10/8/8 vs.
# Feengeist 3/18/10/14/13/11). Groesse taugt NICHT: Open5e und srd-de widersprechen sich
# (Open5e fuehrt Sprite als 'Small', srd-de 'Feengeist' korrekt als 'Winzig').
# Labels je Attribut, diakritika-gefaltet + kleingeschrieben (srd-de kommt teils NFD-
# dekomponiert aus dem PDF: 'Stä' = 's','t','a','kombinierender Umlaut' - erst falten,
# dann matchen). 'str'/'sta' fuer STÄ, 'dex'/'ges' fuer GES usw.
_ATTR_LABELS = (
    ("str", "sta"), ("dex", "ges"), ("con", "kon"),
    ("int",), ("wis", "wei"), ("cha",),
)


# Frueher stand hier eine eigene Faltung (inline `__import__("unicodedata")`), obwohl
# dieses Modul `norm_begriff` oben schon importiert - und deren Docstring ausdruecklich
# sagt, sie sei da, "damit alle Vergleichspfade DIESELBE Semantik nutzen statt eigener
# .lower()-Kopien". Am Bestand nachgemessen (31.07.2026, 3084 Eintraege): die beiden
# unterscheiden sich nur im Randwhitespace, den `norm_begriff` zusaetzlich abschneidet;
# `monster_attribute` und `monster_statschluessel` liefern auf JEDEM Eintrag dasselbe.
_falte = _n


def monster_attribute(body: str | None) -> tuple | None:
    """(STÄ, GES, KON, INT, WEI, CHA) als 6-Tupel aus dem Statblock; None, wenn nicht alle
    sechs erkennbar sind. Deckt engl. ('STR 8') und srd-de ('**Stä**8') ab; Diakritika/Gross-
    Klein werden vor dem Matchen gefaltet."""
    if not body:
        return None
    kopf = _falte(body[:900])
    werte = []
    for labels in _ATTR_LABELS:
        wert = None
        for lab in labels:
            m = re.search(lab + r"[^0-9]{0,6}(\d+)", kopf)
            if m:
                wert = int(m.group(1))
                break
        if wert is None:
            return None
        werte.append(wert)
    return tuple(werte)


def monster_statschluessel(body: str | None) -> tuple:
    """Struktur-Fingerabdruck eines Statblocks (typ, hg, rk, tp, attribute) - identisch fuer
    dieselbe Kreatur in der deutschen und englischen SRD-Fassung, weil alle Bestandteile
    entweder Zahlen oder der (uebersetzte, aber deterministische) Typ sind. None-Anteile
    heissen 'unvollstaendig -> nicht fuer den Abgleich geeignet'."""
    return (monster_typ(body), monster_hg(body), monster_rk(body), monster_tp(body),
            monster_attribute(body))


# --- Der Meta-Seitenwagen: EINE Definition fuer Schreiber und Leser ------------------
# Welche Kategorie in welche Tabelle faellt und welche Felder dort stehen. Bis zum
# 29.07.2026 fuehrten Schreiber (importer/facetten_seeder.py) und Leser
# (app/tools/ausgabe.py) je eine eigene, byte-identische Kopie - eine neue Facette
# erschien deshalb nie in der Tool-Ausgabe, bis jemand die zweite Liste fand. Ein halb
# gelandetes Feature ohne Fehlermeldung.
#
# Sie steht hier, weil beide Seiten dieses Modul ohnehin importieren (es traegt die
# Parser) und die Schichtung dadurch erhalten bleibt: importer haengt an app, nie
# umgekehrt. Die Spalten selbst legt db/schema.sql an - tests/test_facetten_seeder.py
# haelt beide Seiten aneinander.
#
# gegenstand_meta.seltenheit fehlt bewusst: eine belastbare Seltenheits-Ableitung gibt es
# im Bestand nicht (magische Gegenstaende fuehren sie, Ausruestung nicht) - lieber NULL
# als geraten (Regel 1).
META_TABELLEN: dict[str, tuple[str, tuple[str, ...]]] = {
    "zauber": ("zauber_meta", ("grad", "schule", "klassen", "reichweite_m",
                               "komponenten", "dauer_min", "konzentration", "ritual")),
    "monster": ("monster_meta", ("hg", "typ", "rk", "tp")),
    "gegenstand": ("gegenstand_meta", ("preis_cent",)),
}

# Felder, die als Wahrheitswert gemeint sind - 0/1 in der DB, true/false in der Ausgabe.
META_BOOL = frozenset({"konzentration", "ritual"})
