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


# Fuellwoerter, die als kurzes Token legitim sind - sonst hielte `name_sauber` jeden
# Namen mit 'der'/'im'/'zu' fuer zerlegt.
_NAME_WL = {"der", "die", "das", "des", "dem", "den", "im", "am", "zu", "zum", "zur",
            "vom", "von", "und", "mit", "auf", "aus"}


def name_sauber(name: str | None) -> bool:
    """True, wenn der deutsche Name keine PDF-Zerlege-Kurzfragmente traegt ('Gar l gy' -> 'l',
    'Atterko pp' -> 'pp'). Sicherheitsnetz fuer die Bruecke; die bekannten korrupten Namen
    werden ohnehin vorher korrigiert. BEWUSST OHNE Bigramm-Heuristik: 'dk'/'tk' u. ae. stehen
    in echten deutschen Komposita an der Wortfuge (Schild-kroete, Kobold-krieger,
    Grottenschrat-krieger) und wurden faelschlich als korrupt aussortiert.

    Stand bis zum 31.07.2026 in importer/import_glossar.py und wurde von dort als Parameter
    in `finde_korrektur`/`repariere` HINEINGEREICHT - obwohl es nie einen anderen Wert gab.
    Das Praedikat ist reine Namensqualitaet, genau wie dieses Modul: es gehoert hierher,
    und der Parameter konnte entfallen."""
    if not name:
        return False
    for tok in name.replace("-", " ").split():
        t = tok.strip(".,;:()\'\u2019`").lower()
        # Ziffern/Zahlen sind legitime kurze Tokens ('Auf 0 Trefferpunkte', '1W10 Effekt') -
        # nur BUCHSTABEN-Kurzfragmente ('l', 'gy', 'pp') sind Zerlege-Artefakte.
        if t and len(t) <= 2 and t not in _NAME_WL and not any(c.isdigit() for c in t):
            return False
    return True


def _entspacet(s: str) -> str:
    return _fold(s).replace(" ", "").replace("-", "")


def finde_korrektur(name: str, referenz: list[str],
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


def repariere(namen: list[str], referenz: list[str],
              toc_namen: list[str] | None = None) -> dict[str, str]:
    """{korrupt: korrekt} fuer alle sicher zuordenbaren Namen (Rest bleibt unberuehrt).
    `toc_namen`: die autoritativen Namen aus dem Inhaltsverzeichnis
    (Detektor 2 korrigiert nur AUF eine TOC-Form)."""
    toc_fold = frozenset(_fold(t) for t in (toc_namen or referenz))
    out: dict[str, str] = {}
    for nm in namen:
        ziel = finde_korrektur(nm, referenz, toc_fold)
        if ziel and ziel != nm:
            out[nm] = ziel
    return out


# --- Kuratierte Kapitel-/Abschnittstitel -------------------------------------------
# Die generische Reparatur oben braucht eine REFERENZ: das PDF-Inhaltsverzeichnis oder
# einen sauberen Bestandsnamen. Fuer Kapitel- und Abschnittstitel gibt es beides nicht -
# sie stehen in keinem Glossar (es sind keine Spielbegriffe) und im TOC der Scans oft
# ebenso zerrissen wie im Text. Genau deshalb blieben 49 davon offen.
#
# WARUM VON HAND UND NICHT PER HEURISTIK (gemessen am 01.08.2026, zwei Anlaeufe):
# Ein Algorithmus, der Einzelbuchstaben an den Nachbarn zieht, schaffte 22 von 49 - und
# produzierte dabei FALSCHE Namen: 'HEIMATLÄ N DER' -> 'HEIMATLÄ NDER',
# 'MAGISCHE GEGE N STÄNDE' -> 'MAGISCHE GEGEN STÄNDE'. Ein segmentierender Zweitversuch
# kam auf 26, verklebte aber 'DIE S PIELWERTE' zu 'DIES PIELWERTE'. Der Grund ist
# grundsaetzlich: Welches Leerzeichen echt ist und welches ein Riss, steht nicht im Namen -
# 'GEGEN STÄNDE' und 'GEGENSTÄNDE' sind beide deutsche Wortfolgen. Und ein FALSCHER
# Eintragsname ist schlimmer als ein zerrissener: Der zerrissene faellt auf, der falsche
# sieht richtig aus.
#
# BELEGLAGE (am Pi-Vollbestand geprueft): 41 der 46 Zuordnungen bestehen aus Woertern, die
# im deutschen Bestand vorkommen. Die uebrigen fuenf sind sprachlich eindeutig, aber dort
# nicht nachweisbar - 'SELBSTVERSORGUNG' kommt im Fliesstext schlicht nicht vor, die
# Ortsnamen von Upper Tavick's Landing sind englisch. Sie stehen unten mit dem Vermerk.
#
# NICHT aufgenommen, weil hier wirklich geraten waere: 'AURA D' (abgeschnitten, Ziel
# unbekannt), 'MAGISCH R N' (zu wenig Substanz), 'IJ ER K.A1~v1 PFA BLAU F' (vermutlich
# 'DER KAMPFABLAUF', aber die Zeichen tragen die Lesart nicht). Sie bleiben zerrissen und
# in der Warnung - das ist der ehrlichere Zustand.
KURATIERTE_TITEL: dict[str, str] = {
    # --- bestandsbelegt: jedes Wort der Zielform kommt im deutschen Bestand vor ---
    ", E INLEITUNG": "EINLEITUNG",
    "ABERGLAUB E": "ABERGLAUBE",
    "ARKANE S BOGENSCHÜTZENWISSEN": "ARKANES BOGENSCHÜTZENWISSEN",
    "AUF EINE LANGE RAST VER ZIC H TEN": "AUF EINE LANGE RAST VERZICHTEN",
    "B EZIEHUNGEN VON MONSTERN": "BEZIEHUNGEN VON MONSTERN",
    "D 0 GGE": "DOGGE",                       # OCR las die Null statt des O
    "D ER KAMPF UM DIE FREIHEIT": "DER KAMPF UM DIE FREIHEIT",
    "D NKELSICHT": "DUNKELSICHT",             # das U ging verloren
    "DAS HALBLI N GS-PANTH EO N": "DAS HALBLINGS-PANTHEON",
    "DIE F LUCHKLINGE": "DIE FLUCHKLINGE",
    "DIE GÖTTER VON F AERUN": "DIE GÖTTER VON FAERUN",
    "DIE S PIELWERTE DER C H ARAKTERE": "DIE SPIELWERTE DER CHARAKTERE",
    "E NTSPSPANNUNG": "ENTSPANNUNG",          # 'SP' doppelt gelesen
    "F AERUNISCHE GÖTTER": "FAERUNISCHE GÖTTER",
    "F AERUNISCHE ÜÖTIER": "FAERUNISCHE GÖTTER",   # 'ÜÖTIER' ist die OCR von 'GÖTTER'
    "GAB E DER TIEFEN": "GABE DER TIEFEN",
    "GEGENSTÄNDE STUFE FÜR STUFE AUSWÄHLE N": "GEGENSTÄNDE STUFE FÜR STUFE AUSWÄHLEN",
    "GLÜ CKSSPIE L": "GLÜCKSSPIEL",
    "HEIMATLÄ N DER": "HEIMATLÄNDER",
    "INDIVIDUELL E SCHÄTZE": "INDIVIDUELLE SCHÄTZE",
    "J ENSEITS DER UNBEFAHRENEN S EE ----": "JENSEITS DER UNBEFAHRENEN SEE",
    "KIN DH EITSERIN N ERU NGEN": "KINDHEITSERINNERUNGEN",
    "KLI N GENGESANG·STILE": "KLINGENGESANG-STILE",
    "M ERKMALE: SCHATTENMAGIE": "MERKMALE: SCHATTENMAGIE",
    "MAGISCHE GEGE N STÄNDE": "MAGISCHE GEGENSTÄNDE",
    "ME RKMALE: PFAD DES ÄHN ENWÄC HTER S": "MERKMALE: PFAD DES AHNENWÄCHTERS",
    "MENSCHLICH E ETHNIEN IN F AERUN": "MENSCHLICHE ETHNIEN IN FAERUN",
    "P ERSÖNLICHE ENTSCHEIDUNGEN": "PERSÖNLICHE ENTSCHEIDUNGEN",
    "PERLE DER E RFRISCHUNG": "PERLE DER ERFRISCHUNG",
    "R A SCHER ANGRIFF": "RASCHER ANGRIFF",
    "SCHAU 5 Pl E LE R": "SCHAUSPIELER",      # '5'->'S', 'Pl'->'PI'
    "SCHRECKLICHER H I NTERHALT": "SCHRECKLICHER HINTERHALT",
    "So Z TALE INTERAKTION": "SOZIALE INTERAKTION",   # 'Z TALE' ist die OCR von 'ZIALE'
    "TABELLEN FÜR MAGISCHE G EGENSTÄNDE": "TABELLEN FÜR MAGISCHE GEGENSTÄNDE",
    "U NDERDARK-ßEGEG NU NGEN (STUFE 5-10)": "UNDERDARK-BEGEGNUNGEN (STUFE 5-10)",
    "UNBEIRRTE R BLICK": "UNBEIRRTER BLICK",
    "V ERTEILU NG NACH SELTENHEIT": "VERTEILUNG NACH SELTENHEIT",
    "VERSENGENDE R LICHTBOGENSCHLAG": "VERSENGENDER LICHTBOGENSCHLAG",
    "WACHSAMER V ERTEIDIGER": "WACHSAMER VERTEIDIGER",
    "j ERGAL": "JERGAL",                      # Gottheit; das kleine j ist ein Scan-Artefakt
    "Ü BE RNATÜRLICH E SCHWINGEN": "ÜBERNATÜRLICHE SCHWINGEN",
    # --- sprachlich eindeutig, im deutschen Fliesstext aber nicht nachweisbar ---
    "P EINLICHE AUS RUT SCHER": "PEINLICHE AUSRUTSCHER",
    "SCHMIEDEVATER UND VEREHRTE M UTIER": "SCHMIEDEVATER UND VEREHRTE MUTTER",
    "SEI.BSTVERSO RG U N G": "SELBSTVERSORGUNG",   # '.' statt 'L' gelesen
    "TOPF DES ERWACH E NS": "TOPF DES ERWACHENS",
    "’ UPPER TAVICK S LANDING": "UPPER TAVICK'S LANDING",   # englischer Ortsname (efota-en)
}


# --- Belegte Leerzeichen-Reparatur (23.09.2026) --------------------------------------
# Die Kuratierung oben verwirft zwei Heuristiken, weil sie FALSCHE Namen erzeugten
# ('DIES PIELWERTE'). Beide entschieden aus dem Namen allein. Dieser Schritt entscheidet
# aus dem BUCH: Ein Leerzeichen wird nur geschlossen, wenn danach jedes Wort des Namens
# im Fliesstext derselben Quelle mindestens zweimal vorkommt - und wenn genau EINE
# Schliessung das leistet. 'DIE S PIELWERTE' hat dann nur eine belegte Lesart ('DIE
# SPIELWERTE'; 'pielwerte' steht in keinem Text), 'GEGE N STÄNDE' zwei ('GEGENSTÄNDE',
# 'GEGEN STÄNDE') und bleibt deshalb zerrissen.
#
# Gegen die Kuratierung gemessen (Pi-Vollbestand, 23.09.2026): 15 der 46 kuratierten
# Titel entscheidet der Schritt selbst, alle 15 mit derselben Zerlegung wie von Hand; den
# Rest laesst er offen. Er laeuft NACH der Kuratierung, damit deren zusaetzliche
# Zeichenkorrekturen ('j ERGAL' -> 'JERGAL', nicht 'jERGAL') Vorrang behalten.
_BUCHSTABEN = "A-Za-zÄÖÜäöüß"
_BUCHSTABEN_TOKEN = re.compile(rf"[{_BUCHSTABEN}]+(?:-[{_BUCHSTABEN}]+)*")
_WORT = re.compile(rf"[{_BUCHSTABEN}]+")
_MIN_BELEGE = 2
# Kurze Tokens belegt der Fliesstext nicht: 'h', 'th', 'es' stehen dort als Rissreste
# ebenso wie als Woerter, und der zweite Lauf am Pi-Bestand liess deshalb 'H IT POINTS'
# und 'CAN TR I P' stehen. Bis zwei Buchstaben zaehlt nur, was als Wort bekannt ist.
_KURZWOERTER = frozenset((
    "a i am an as at be by do go he if in is it me my no of on or so to up us we "
    "ab da du er es im ja ob um wo zu").split())
_MAX_TOKENS = 12          # 2^11 Schliessungen - darueber ist ein Name kein Titel mehr


_KONTEXTZEILE = re.compile(r"^\*Kontext:.*$", re.M)
_BINNENMAJUSKEL = re.compile(r"[a-zäöüß][A-ZÄÖÜ]")


def wortschatz(texte) -> dict[str, int]:
    """Wortzaehlung (kleingeschrieben) ueber die Fliesstexte einer Quelle.

    Ohne die '*Kontext: …*'-Zeilen: Sie wiederholen die Eltern-Ueberschriften - samt
    ihrer Risse - in jedem Kind-Eintrag, und ein Fragment wie 'athhouse' galte sonst
    allein durch diese Wiederholung als belegt.

    Ohne VERSALIEN-Woerter: Die Scans verkleben in Grossbuchstaben auch im Fliesstext
    ('FIRENEWTS', 'AURADESWÄCHTERS'), und der erste Lauf am Pi-Bestand machte daraus fuenf
    falsche Namen. Im Fliesstext in normaler Schreibung steht 'fire newts' getrennt -
    dort ist die OCR verlaesslich, und nur das zaehlt als Beleg.

    Zaehlt auch WORTPAARE ('fire newts', Schluessel mit Leerzeichen): steht ein Paar im
    Fliesstext getrennt, ist sein Leerzeichen echt (siehe `belegte_schliessung`)."""
    zaehler: dict[str, int] = {}
    for text in texte:
        vorher = None
        for w in _WORT.findall(_KONTEXTZEILE.sub("", text or "")):
            # Versalien und Binnenmajuskeln ('IrisShape') sind die zwei Formen, in denen die
            # Scans Woerter verkleben - beides zaehlt nicht als Beleg.
            if (w.isupper() and len(w) > 1) or _BINNENMAJUSKEL.search(w):
                vorher = None
                continue
            w = w.lower()
            zaehler[w] = zaehler.get(w, 0) + 1
            if vorher:
                paar = f"{vorher} {w}"
                zaehler[paar] = zaehler.get(paar, 0) + 1
            vorher = w
    return zaehler


def belegte_schliessung(name: str, wortschatz: dict[str, int]) -> str | None:
    """Der Name mit geschlossenen Riss-Leerzeichen - oder None, wenn nichts zerrissen ist
    oder keine EINDEUTIGE belegte Lesart existiert.

    Nur reine Buchstaben-Tokens werden verbunden. Ein Token mit Ziffer, Apostroph oder
    Satzzeichen ('K71.', "L'S", 'Q,UARTIERE') bleibt, wie er ist, und verbindet sich mit
    nichts: sonst entstand 'WIE DU 8TRAHDSPIELST'."""
    tokens = name.split(" ")
    if not 2 <= len(tokens) <= _MAX_TOKENS:
        return None

    def belegt(t: str) -> bool:
        return all(teil.lower() in _KURZWOERTER if len(teil) <= 2
                   else wortschatz.get(teil.lower(), 0) >= _MIN_BELEGE
                   for teil in t.split("-"))

    def getrennt_belegt(links: str, rechts: str) -> bool:
        return wortschatz.get(f"{links.split('-')[-1].lower()} "
                              f"{rechts.split('-')[0].lower()}", 0) > 0

    fest = [not _BUCHSTABEN_TOKEN.fullmatch(t) for t in tokens]
    riss = [not f and not belegt(t) for t, f in zip(tokens, fest)]
    if not any(riss):
        return None                                   # nichts zerrissen
    lesarten: set[str] = set()
    for maske in range(1 << (len(tokens) - 1)):       # Bit i gesetzt = Leerzeichen i zu
        # Geschlossen wird nur, was an ein UNBELEGTES Stueck grenzt: zwei belegte Woerter
        # ('AURA' 'DES') trennt ein echtes Leerzeichen, auch wenn ihr Verbund zufaellig
        # ebenfalls irgendwo steht.
        # Ebenso nie ein Paar, das der Fliesstext GETRENNT fuehrt ('fire newts'): die OCR
        # verklebt auch dort gelegentlich, aber die getrennte Schreibung ist der Beleg.
        if any(maske >> i & 1 and (fest[i] or fest[i + 1] or not (riss[i] or riss[i + 1])
                                   or getrennt_belegt(tokens[i], tokens[i + 1]))
               for i in range(len(tokens) - 1)):
            continue
        teile = [tokens[0]]
        for i, t in enumerate(tokens[1:]):
            if maske >> i & 1:
                teile[-1] += t
            else:
                teile.append(t)
        if all(not _BUCHSTABEN_TOKEN.fullmatch(t) or belegt(t) for t in teile):
            lesarten.add(" ".join(teile))
            if len(lesarten) > 1:
                return None
    return next(iter(lesarten)) if lesarten else None
