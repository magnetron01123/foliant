"""Rechnerische Plausibilitaet von Regeltext - reine Funktionen, keine Datenbank.

WOFUER: Ein OCR-Riss oder ein Importfehler aendert fast immer eine ZAHL, und eine falsche
Zahl in einem Statblock sieht genauso aus wie eine richtige. Was sie verraet, ist der
WIDERSPRUCH zu einer anderen Zahl im selben Text: Trefferpunkte muessen zu ihrer
Wuerfelformel passen, ein Attributsmodifikator zu seinem Attributswert, eine Wuerfelgroesse
zu den Wuerfeln, die es gibt. Diese Pruefungen fanden im Datenbank-Audit vom 03.08.2026
genau die echten Fehler und kaum Rauschen - deshalb stehen sie jetzt dauerhaft in
`admin check` (mit Basiswert, siehe config/qualitaet_basis.json).

WAS SIE NICHT KANN: Sie prueft Konsistenz, nicht Wahrheit. Ein Statblock, dessen Zahlen
alle zueinander passen, kann trotzdem die falsche Kreatur beschreiben. Und sie sagt nie,
WELCHE der beiden Zahlen falsch ist - das entscheidet ein Mensch am Beleg (Regel 1).

VIER STATBLOCK-FORMATE, alle im Bestand belegt - wer hier ein Muster aendert, muss alle
vier gegenpruefen, sonst faellt still ein Viertel des Korpus aus der Pruefung:
  srd-de                  '**TP** 287 (23W12+161)'        '**Sta** 19 +4 +4 **GeS** ...'
  open5e-srd-2024         '**HP:** 3 (1d6)'               '**Abilities:** STR 4 (-3), ...'
  ddb-br-2024-en          '**HP** 150 (20d10 \\+ 40\\)'     '| Str | 21 | \\+5 | \\+5 |'
  ddb-basic-rules-2014-en 'Hit Points 135 (18d10 \\+ 36\\)' 'STR\\n21(\\+5\\)'
Die Backslash-Escapes sind der teuerste Fallstrick: ohne sie faellt ddb-br-2024-en stumm
aus der TP-Pruefung, und der Check meldet trotzdem OK.

ABDECKUNG EHRLICH (am Pi-Vollbestand gemessen, 03.08.2026): 1454 TP-Formeln, 8421
Attributswerte, 10307 Wuerfelausdruecke. NICHT erreicht werden Quellen, die gar keine
Statbloecke fuehren (die drei deutschen 2014-Buecher: reine Regelkapitel) und
ddb-mcv1-en, dessen Chunks ohne Statblock-Kopf ankommen. Beides sind richtige Nullen,
keine Luecken - aber wer ein Muster erweitert, sollte die Zahlen kennen, statt sie neu
zu erraten.
"""
from __future__ import annotations

import re
from typing import NamedTuple


class Befund(NamedTuple):
    """Ein rechnerischer Widerspruch. `fundstelle` ist der Rohausschnitt (damit ein Mensch
    ihn im Bestand wiederfindet), `erklaerung` sagt, welche zwei Zahlen sich widersprechen."""

    art: str            # 'tp_formel' | 'attribut' | 'wuerfel'
    fundstelle: str
    erklaerung: str


# Gueltige Wuerfelgroessen. 2 und 3 gehoeren dazu: 'W3' kommt im Bestand hundertfach
# offiziell vor (Schadenswuerfel kleiner Kreaturen), 'W2' als Muenzwurf-Ersatz. Eine
# Obergrenze fuer die WUERFELZAHL gibt es bewusst nicht - der Lich wirft echte 42W8.
WUERFEL_GROESSEN = frozenset({2, 3, 4, 6, 8, 10, 12, 20, 100})

# Ein Wuerfelausdruck in beiden Schreibweisen. Ohne \b vorne: im Markdown klebt regelmaessig
# eine Auszeichnung davor ('_2W6'), und ein zerrissenes '1 W8' soll gerade AUFFALLEN.
_WUERFEL = re.compile(r"(\d+)\s*[WwDd](\d+)")

# Die Trefferpunkte-Zeile. Der Backslash vor '+' und ')' ist DDB-Markdown-Escaping,
# das Minus kann '-', '−' (U+2212) oder '–' sein.
_TP_FORMEL = re.compile(
    r"(?:\*\*)?(?:TP|HP|Hit Points)(?:\*\*)?[:\s*]{0,6}"
    r"(\d+)\s*\(\s*(\d+)\s*[WwDd](\d+)\s*(?:\\?([+\-−–])\s*(\d+))?\s*\\?\)"
)

_ATTRIBUTE = ("STR", "DEX", "CON", "INT", "WIS", "CHA")
# open5e: '**Abilities:** STR 4 (-3), DEX 15 (+2), ...'
_ATTR_LISTE = re.compile(
    rf"\b({'|'.join(_ATTRIBUTE)})\b\s+(-?\d+)\s*\(\s*\\?([+\-−–])\s*(\d+)\s*\\?\)")
# ddb-basic-rules-2014: 'STR\n21(\+5\)'  |  ddb-br-2024: '| Str | 21 | \+5 | \+5 |'
# Gross- UND Kleinschreibung: beide Formen stehen im Bestand ('| STR |' 283-mal,
# '| Str |' 2711-mal). Ein Muster nur fuer die haeufigere liesse die andere stumm aus.
_ATTR_TABELLE = re.compile(
    rf"\|\s*({'|'.join(_ATTRIBUTE)})\s*\|\s*(\d+)\s*\|\s*\\?([+\-−–])\s*(\d+)\s*\|",
    re.IGNORECASE)
# srd-de, die deutsche Hauptquelle: '**Stä** 19 +4 +4 **GeS** 14 +2 +2 ...' - Wert,
# Modifikator, Rettungswurf ohne Klammern. Die Kuerzel kommen OCR-verschliffen aus dem
# PDF ('GeS', 'WeI'), deshalb die tolerante Zeichenklasse. Ohne dieses Muster blieben
# 339 Monster der wichtigsten deutschen Quelle ungeprueft (Review-Befund 03.08.2026).
_ATTR_SRD_DE = re.compile(
    r"\*\*(St[äa]|Ge[SsB]|Kon|Int|We[Il1]|Cha)\*\*\s+(\d{1,2})\s+([+\-−–])\s*(\d+)")

_VORZEICHEN = {"+": 1, "-": -1, "−": -1, "–": -1}


def _zahl(vorzeichen: str, betrag: str) -> int:
    return _VORZEICHEN.get(vorzeichen, 1) * int(betrag)


def pruefe_tp_formel(body: str) -> list[Befund]:
    """Trefferpunkte gegen ihre Wuerfelformel: n Wuerfel der Groesse d haben den
    Durchschnitt n*(d+1)/2, dazu der Bonus. Toleranz +-1, weil die Buecher mal auf-, mal
    abrunden ('84,5' steht als 84 oder 85).

    Zwei Beispiele aus dem Bestand: '287 (23W12+161)' ergibt 310,5 - ein Druckfehler des
    deutschen SRD (config/quellfehler.py). '105 (0W1|2+40)' ergibt 0,5 - ein Zellriss der
    PDF-Tabelle. Die Pruefung unterscheidet beide nicht; das tut der Mensch am Beleg."""
    funde = []
    for m in _TP_FORMEL.finditer(body):
        gesamt, anzahl, groesse = int(m.group(1)), int(m.group(2)), int(m.group(3))
        bonus = _zahl(m.group(4) or "+", m.group(5) or "0")
        if groesse not in WUERFEL_GROESSEN or anzahl < 1:
            continue                       # faengt schon pruefe_wuerfel - nicht doppelt melden
        schnitt = anzahl * (groesse + 1) / 2 + bonus
        if abs(schnitt - gesamt) > 1:
            funde.append(Befund(
                "tp_formel", m.group(0).strip(),
                f"Formel ergibt {schnitt:.1f}, angegeben sind {gesamt}"))
    return funde


def pruefe_wuerfel(body: str) -> list[Befund]:
    """Wuerfelgroessen gegen die Wuerfel, die es gibt. 'lW6' (OCR aus '1W6'), '1W1O'
    (Buchstabe O statt Null) und '2W1 2' (zerrissenes 2W12) fallen so auf."""
    return [Befund("wuerfel", m.group(0),
                   f"W{m.group(2)} ist keine Wuerfelgroesse")
            for m in _WUERFEL.finditer(body)
            if int(m.group(2)) not in WUERFEL_GROESSEN]


def pruefe_attribute(body: str) -> list[Befund]:
    """Attributswerte gegen ihren Modifikator und gegen den Wertebereich.

    ZWEI Pruefungen, und die zweite ist die wichtigere: Ein Modifikator, der zu einem
    unmoeglichen Wert PASST, ist immer noch unmoeglich. Der einzige echte Fund im Bestand
    (open5e 'Octopus': KON 0, CHA -3) ist formeltreu und faellt nur ueber den
    Wertebereich auf - wer nur die Formel prueft, haelt ihn faelschlich fuer geprueft."""
    funde = []
    for regex in (_ATTR_LISTE, _ATTR_TABELLE, _ATTR_SRD_DE):
        for m in regex.finditer(body):
            attribut, wert = m.group(1).upper(), int(m.group(2))
            mod = _zahl(m.group(3), m.group(4))
            if not 1 <= wert <= 30:
                funde.append(Befund(
                    "attribut", m.group(0).strip(),
                    f"{attribut} {wert} liegt ausserhalb des Wertebereichs 1-30"))
            elif (wert - 10) // 2 != mod:
                funde.append(Befund(
                    "attribut", m.group(0).strip(),
                    f"{attribut} {wert} hat Modifikator {(wert - 10) // 2:+d}, "
                    f"angegeben ist {mod:+d}"))
    return funde


def pruefe_text(body: str | None) -> list[Befund]:
    """Alle drei Textpruefungen in EINEM Durchgang - `admin check` laeuft ueber 12 500
    Bodys, und drei getrennte Schleifen waeren dreimal derselbe Speicherzugriff."""
    if not body:
        return []
    return pruefe_tp_formel(body) + pruefe_attribute(body) + pruefe_wuerfel(body)


def zaehle_geprueft(body: str | None) -> dict[str, int]:
    """Wie viele Ausdruecke die Pruefung ueberhaupt GESEHEN hat.

    Ohne diese Zahl ist ein 'OK' nicht interpretierbar: Ein Muster, das nach einem
    Formatwechsel ins Leere greift, meldet null Befunde - genau wie ein sauberer Bestand.
    `admin check` weist sie deshalb neben den Befunden aus."""
    if not body:
        return {"tp_formel": 0, "attribut": 0, "wuerfel": 0}
    return {"tp_formel": len(_TP_FORMEL.findall(body)),
            "attribut": (len(_ATTR_LISTE.findall(body))
                         + len(_ATTR_TABELLE.findall(body))
                         + len(_ATTR_SRD_DE.findall(body))),
            "wuerfel": len(_WUERFEL.findall(body))}
