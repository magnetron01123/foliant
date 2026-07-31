"""Das Register der offiziellen DEUTSCHEN Abkuerzungen - EINE Definition fuer alle.

Warum es das braucht: Abkuerzungen sind der Ort, an dem eine deutsche Auskunft am
leisesten ins Englische kippt. "AC 15", "8d6", "DC 14" liest sich in einer deutschen
Antwort unauffaellig - und ist trotzdem falsch, weil am Tisch ein deutsches Buch liegt,
in dem RK, 8W6 und SG steht. Der ausgeschriebene Begriff war ueber das Glossar laengst
abgesichert (S3/S4), seine ABKUERZUNG nicht.

Bis zum 31.07.2026 lag das Wissen an drei Stellen, die nichts voneinander wussten:
  * `importer/import_glossar.ABKUERZUNGEN` - englische Kuerzel als SUCHhilfe (AoO -> …),
    plus drei deutsche (RK, SG, TP)
  * `app/charakterbogen/uebersetzer.py` - eine verbindliche Vorgabe im Prompt
    (STAE/GES/KON/INT/WEI/CHA, SG/RK/TP), die nur fuer den Charakterbogen galt
  * `config/stil.py` - der Halbsatz "die Suche versteht … gaengige Abkuerzungen"
Der MCP-Server, also der Dienst, der die Regelauskuenfte gibt, hatte damit KEINE Regel,
deutsch abzukuerzen. Genau das schliesst dieses Register.

HERKUNFT DER EINTRAEGE - alles ausgezaehlt, nichts gesetzt (Regel 1): Die Kuerzel unten
stammen aus dem deutschen SRD 5.2.1 (Bestandsquelle `srd-de`, Edition 2024) und sind dort
mit der angegebenen Haeufigkeit belegt. `tests/test_abkuerzungen.py` prueft das gegen den
echten Bestand, damit hier nie eine Abkuerzung steht, die das offizielle Buch nicht kennt.

NICHT aufgenommen, obwohl naheliegend:
  * Die ATTRIBUTS-Kuerzel (STAE, GES, KON, INT, WEI, CHA) stehen im srd-de-Fliesstext nur
    in den Statblock-Tabellen, und dort verstuemmelt sie die PDF-Konvertierung zu
    'Stae'/'GeS'/'Kon' (dasselbe Drop-Cap-Artefakt wie bei 'wAffen'/'zAuber', BACKLOG §3).
    Aus diesem Text ihre Schreibweise abzuleiten waere Raten. Ihr Beleg ist der offizielle
    deutsche Charakterbogen, und dort stehen sie bereits verbindlich
    (`app/charakterbogen/uebersetzer.py`) - deshalb hier mit dem Vermerk, woher sie kommen.
  * 'MOD' (Modifikator) und 'RW' (Rettungswurf) sind mit je ~1000 Treffern die haeufigsten
    Kuerzel ueberhaupt - aber ausschliesslich als SPALTENKOEPFE der Statblock-Tabelle. Im
    Fliesstext schreibt das SRD beides aus. Eine Antwort, die "RW +4" statt
    "Rettungswurf +4" schreibt, waere also nicht deutscher, sondern nur knapper - und in
    einem Satz schwerer zu lesen. Sie stehen deshalb als Such-Aliasse drin, nicht als
    Empfehlung.
"""
from __future__ import annotations

# (deutsche Abkuerzung, ausgeschriebener deutscher Begriff, englisches Pendant, Belege)
# `englisch` ist das Kuerzel, das eine Antwort NICHT verwenden soll - und zugleich das,
# unter dem ein englischsprachiger Nutzer sucht. Beides braucht dieselbe Zeile.
EMPFOHLEN: list[tuple[str, str, str | None, int]] = [
    # Kernwerte - die vier, die in fast jeder Regelauskunft vorkommen
    ("RK",  "Rüstungsklasse",       "AC",  421),
    ("TP",  "Trefferpunkte",        "HP",  354),
    ("SG",  "Schwierigkeitsgrad",   "DC",  654),
    ("HG",  "Herausforderungsgrad", "CR",  356),
    ("EP",  "Erfahrungspunkte",     "XP",  388),
    ("ÜB",  "Übungsbonus",          "PB",  341),
    # Rollen am Tisch. 'Spielleiter' ist die Form, die das deutsche SRD verwendet (11x);
    # 'Spielleitung' kommt dort KEIN einziges Mal vor - hier steht das Buch, nicht der
    # eigene Sprachgeschmack.
    ("SL",  "Spielleiter",           "DM",  168),
    ("NSC", "Nichtspielercharakter", "NPC",  19),
    # Muenzen - jede mit ihrer Langform im Text belegt ('Goldmünze (GM)' usw.).
    # Die englischen Pendants sind SUCH-Aliasse, keine Belege: 'gp' steht 456x im
    # englischen Bestand, 'cp'/'pp' je einmal, 'sp' KEIN einziges Mal. Es bleibt trotzdem
    # drin - ein Alias, der nie gesucht wird, kostet nichts; ein fehlender laesst eine
    # Suche ins Leere laufen. Fuer die AUSGABE gilt ohnehin nur die deutsche Spalte.
    ("GM",  "Goldmünze",     "GP", 334),
    ("SM",  "Silbermünze",   "SP",  33),
    ("KM",  "Kupfermünze",   "CP",  21),
    ("EM",  "Elektrummünze", None,   2),   # engl. 'ep' kollidiert mit dt. EP - s. u.
    ("PM",  "Platinmünze",   "PP",   2),
]

# Wuerfel: die eine Abkuerzung, die in JEDER Schadenszeile steht. 'W' statt 'd' ist die
# sichtbarste Stelle, an der eine deutsche Antwort englisch klingt ("8d6 Feuerschaden").
WUERFEL: list[tuple[str, str, int]] = [
    ("W4", "d4", 1), ("W6", "d6", 9), ("W8", "d8", 19),
    ("W10", "d10", 14), ("W12", "d12", 9), ("W20", "d20", 79),
]

# Nur als SUCH-Alias, nicht als Empfehlung fuer die Antwort (Begruendung im Modul-Kopf).
NUR_SUCHE: list[tuple[str, str, str | None]] = [
    ("MOD", "Modifikator", None),
    ("RW", "Rettungswurf", None),
]

# Attributs-Kuerzel des offiziellen deutschen Charakterbogens. Ihr Beleg ist der gedruckte
# Bogen, nicht der srd-de-Fliesstext (dort zerlegt sie die PDF-Konvertierung) - dieselbe
# Beweisführung wie bei 'Heldische Inspiration' (CONCEPT.md §7: die Vordruck-Labels des
# offiziellen Bogens gelten selbst als offizielle Quelle).
ATTRIBUTE: list[tuple[str, str, str]] = [
    ("STÄ", "Stärke",        "STR"),
    ("GES", "Geschicklichkeit", "DEX"),
    ("KON", "Konstitution",  "CON"),
    ("INT", "Intelligenz",   "INT"),
    ("WEI", "Weisheit",      "WIS"),
    ("CHA", "Charisma",      "CHA"),
]


def empfohlene_paare() -> list[tuple[str, str]]:
    """(deutsche Abkuerzung, ausgeschriebener Begriff) - alles, was eine Antwort
    verwenden SOLL, wenn sie abkuerzt."""
    return ([(k, lang) for k, lang, _en, _n in EMPFOHLEN]
            + [(k, lang) for k, lang, _en in ATTRIBUTE])


def englische_kuerzel() -> list[tuple[str, str]]:
    """(englisches Kuerzel, deutscher Begriff) - damit eine englische Anfrage ('AC', 'DC')
    den deutschen Eintrag findet. Das ist die SUCH-Richtung; fuer die AUSGABE gilt die
    deutsche Form.

    'EP' ist der eine Fall, in dem beide Sprachen dasselbe Kuerzel anders belegen: deutsch
    Erfahrungspunkte, englisch Electrum Pieces. Die englische Lesart bleibt bewusst
    draussen (deshalb `None` bei der Elektrummuenze) - sie wuerde die haeufige deutsche
    ueberschreiben, und 'ep' kommt im englischen Bestand kein einziges Mal vor."""
    paare = [(en, lang) for _k, lang, en, _n in EMPFOHLEN if en]
    paare += [(en, lang) for _k, lang, en in ATTRIBUTE]
    return paare


def alle_such_aliasse() -> list[tuple[str, str]]:
    """Jede Abkuerzung, unter der jemand suchen koennte -> ausgeschriebener Begriff."""
    return (empfohlene_paare() + englische_kuerzel()
            + [(k, lang) for k, lang, _en in NUR_SUCHE])
