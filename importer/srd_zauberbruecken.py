"""Zauber-Bruecken DE<->EN ueber den ZAUBERKOPF - editionsuebergreifend (27.07.2026).

Anlass: Mit den deutschen 2014-Baenden (PHB/Xanathar/SCAG) liegen ~290 deutsche
Zaubernamen im Bestand, fuer die es kein Glossar-Paar gab - die dnddeutsch-Bruecke
kennt sie nicht, und die vorhandenen Matcher suchen nur in srd-de/Open5e bzw. ueber
Monster-Statbloecke. Uebersetzungen sind aber editionsuebergreifend (S7): der alte
offizielle Begriff gilt ohne '*', der neuere gewinnt, wo es ihn gibt (S8).

Beweisgrundlage ist der Zauberkopf, den ALLE Fassungen tragen - deutsch wie englisch,
2014 wie 2024:

    DE-2014  "Nekromantie des 3. Grades (Ritual) Zeitaufwand: 1 Aktion
              Reichweite: Beruehrung Komponenten: V, G, M Wirkungsdauer: 1 Stunde"
    EN       "3rd-level necromancy Casting Time: 1 action Range: Touch
              Components: V, S, M Duration: Instantaneous"

Jedes Feld ist deterministisch normalisierbar, nichts wird uebersetzt geraten:
Schule ueber eine feste 8er-Tabelle, Fuss->Meter ueber die D&D-Konvention (5 ft = 1,5 m),
G(este) = S(omatic), Dauer/Zeitaufwand als Minutenwerte. Gepaart wird nur, wenn ein
Fingerabdruck auf BEIDEN Seiten GENAU EINMAL vorkommt.

Warum der Fingerabdruck so breit ist: (Grad, Schule) allein kollidiert massiv (5-11
deutsche gegen 5-9 englische Zauber je Bucket). Ein erster Entwurf mit nur
(Grad, Schule, Reichweite) paarte 'TOTSTELLEN' (Feign Death, Wirkungsdauer 1 Stunde)
mit 'Revivify' (unmittelbar) - beide Nekromantie 3. Grades mit Beruehrung. Erst
Wirkungsdauer und Zeitaufwand trennen sie. Zusaetzlich verwirft die Widerspruchs-
pruefung jedes Paar, das einer bereits belegten exakten Glossar-Zeile widerspricht."""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict

from app import glossar

QUELLE = "Zauberkopf-Abgleich"

# Die acht Schulen - geschlossene Menge, feste Zuordnung (keine Uebersetzungsvermutung).
SCHULEN = {
    "bannmagie": "abjuration", "beschwörung": "conjuration", "beschwoerung": "conjuration",
    "erkenntnismagie": "divination", "weissagung": "divination",
    "verzauberung": "enchantment", "hervorrufung": "evocation", "illusion": "illusion",
    "nekromantie": "necromancy", "verwandlung": "transmutation",
}
_SCHULE_DE = "|".join(SCHULEN)
_SCHULE_EN = ("abjuration|conjuration|divination|enchantment|evocation|illusion|"
              "necromancy|transmutation")

_DE_GRAD = re.compile(rf"({_SCHULE_DE})\w*\s*(?:des\s*)?(\d)\.\s*Grades", re.I)
_DE_TRICK = re.compile(rf"({_SCHULE_DE})\w*[-\s]?Zaubertrick", re.I)
_EN_GRAD = re.compile(rf"(\d)(?:st|nd|rd|th)\\?-level\s+({_SCHULE_EN})", re.I)
_EN_TRICK = re.compile(rf"({_SCHULE_EN})\s+cantrip", re.I)

_DE_REICHWEITE = re.compile(r"Reichweite:?\s*([^\n]{0,40})", re.I)
_EN_REICHWEITE = re.compile(r"Range:?\s*([^\n]{0,40})", re.I)
_DE_KOMPONENTEN = re.compile(r"Komponenten:?\s*([VGM][VGM,\s]*)", re.I)
_EN_KOMPONENTEN = re.compile(r"Components:?\s*([VSM][VSM,\s]*)", re.I)
_DE_DAUER = re.compile(r"Wirkungsdauer:?\s*([^\n]{0,50})", re.I)
_EN_DAUER = re.compile(r"Duration:?\s*([^\n]{0,50})", re.I)
_DE_ZEIT = re.compile(r"Zeitaufwand:?\s*([^\n]{0,40})", re.I)
_EN_ZEIT = re.compile(r"Casting Time:?\s*([^\n]{0,40})", re.I)
_WUERFEL = re.compile(r"\b(\d+)[dDwW](\d+)\b")

_KOPF_ZEICHEN = 600          # der Kopf steht immer am Anfang; danach faengt Fliesstext an


def _kopf(body: str | None) -> str:
    return " ".join((body or "")[:_KOPF_ZEICHEN].split())


def _grad_schule(kopf: str, deutsch: bool) -> tuple[int, str] | None:
    if deutsch:
        m = _DE_GRAD.search(kopf)
        if m:
            return int(m.group(2)), SCHULEN[m.group(1).lower()]
        m = _DE_TRICK.search(kopf)
        return (0, SCHULEN[m.group(1).lower()]) if m else None
    m = _EN_GRAD.search(kopf)
    if m:
        return int(m.group(1)), m.group(2).lower()
    m = _EN_TRICK.search(kopf)
    return (0, m.group(1).lower()) if m else None


def _reichweite(kopf: str, deutsch: bool) -> str | int | None:
    """Meter (int), 'beruehrung', 'selbst' oder None. Fuss -> Meter nach der
    D&D-Konvention 5 ft = 1,5 m; gerundet, damit 150 ft und 45 m denselben Wert geben."""
    m = (_DE_REICHWEITE if deutsch else _EN_REICHWEITE).search(kopf)
    if not m:
        return None
    text = m.group(1).lower()
    if "berühr" in text or "beruehr" in text or "touch" in text:
        return "beruehrung"
    if text.startswith("selbst") or text.startswith("self"):
        return "selbst"
    if "sicht" in text or "sight" in text:
        return "sicht"
    if "unbegrenzt" in text or "unlimited" in text:
        return "unbegrenzt"
    zahl = re.search(r"(\d+)", text)
    if not zahl:
        return None
    wert = int(zahl.group(1))
    if deutsch:
        return wert if re.search(r"\b(m|meter)\b", text) else None
    if re.search(r"\b(feet|foot|ft)\b", text):
        return round(wert * 0.3)
    if re.search(r"\b(mile|miles)\b", text):
        return wert * 1600
    return None


def _komponenten(kopf: str, deutsch: bool) -> str | None:
    """'VSM' sortiert; deutsches G(este) ist das englische S(omatic)."""
    m = (_DE_KOMPONENTEN if deutsch else _EN_KOMPONENTEN).search(kopf)
    if not m:
        return None
    zeichen = set(re.findall(r"[VGSM]", m.group(1).upper()))
    if deutsch:
        zeichen = {"S" if z == "G" else z for z in zeichen}
    return "".join(sorted(zeichen)) or None


def _dauer(kopf: str, deutsch: bool) -> tuple[bool, int] | None:
    """(Konzentration?, Minuten). 'unmittelbar'/'Instantaneous' -> 0,
    'bis zur Aufloesung'/'until dispelled' -> -1 (Sonderwert, nie eine Minutenzahl)."""
    m = (_DE_DAUER if deutsch else _EN_DAUER).search(kopf)
    if not m:
        return None
    text = m.group(1).lower()
    konz = "konzentration" in text or "concentration" in text
    if "unmittelbar" in text or "instantaneous" in text:
        return (konz, 0)
    if "aufgelöst" in text or "aufloesung" in text or "dispelled" in text:
        return (konz, -1)
    zahl = re.search(r"(\d+)", text)
    if not zahl:
        return (konz, -2) if "sonderfall" in text or "special" in text else None
    wert = int(zahl.group(1))
    if re.search(r"\b(stunde|stunden|hour|hours)\b", text):
        return (konz, wert * 60)
    if re.search(r"\b(tag|tage|day|days)\b", text):
        return (konz, wert * 1440)
    if re.search(r"\b(runde|runden|round|rounds)\b", text):
        return (konz, 0)                       # < 1 Minute; Runden sind editionsgleich
    if re.search(r"\b(minute|minuten|minutes)\b", text):
        return (konz, wert)
    return None


def _zeitaufwand(kopf: str, deutsch: bool) -> str | None:
    """Normierte Wirkzeit: 'aktion' | 'bonusaktion' | 'reaktion' | '<n>min'."""
    m = (_DE_ZEIT if deutsch else _EN_ZEIT).search(kopf)
    if not m:
        return None
    text = m.group(1).lower()
    if "bonus" in text:
        return "bonusaktion"
    if "reaktion" in text or "reaction" in text:
        return "reaktion"
    if re.search(r"\b(aktion|action)\b", text):
        return "aktion"
    zahl = re.search(r"(\d+)", text)
    if not zahl:
        return None
    wert = int(zahl.group(1))
    if re.search(r"\b(stunde|stunden|hour|hours)\b", text):
        return f"{wert * 60}min"
    if re.search(r"\b(minute|minuten|minutes)\b", text):
        return f"{wert}min"
    return None


def _wuerfel(body: str | None) -> tuple:
    """Wuerfel-Multiset, sprachunabhaengig normalisiert (8W6 == 8d6)."""
    return tuple(sorted(f"{a}d{b}" for a, b in _WUERFEL.findall(body or "")))


def fingerabdruck(body: str | None, deutsch: bool) -> tuple | None:
    """Der vollstaendige Zauber-Fingerabdruck oder None (= kein Zauberkopf erkennbar).
    Ein Feld None macht den Abdruck NICHT ungueltig - fehlende Felder sind selbst ein
    Merkmal; gepaart wird ohnehin nur bei beidseitiger Eindeutigkeit."""
    kopf = _kopf(body)
    grad_schule = _grad_schule(kopf, deutsch)
    if grad_schule is None:
        return None
    ritual = bool(re.search(r"\(ritual\)", kopf, re.I))
    return (*grad_schule, _reichweite(kopf, deutsch), _komponenten(kopf, deutsch),
            _dauer(kopf, deutsch), _zeitaufwand(kopf, deutsch), ritual, _wuerfel(body))


def _belegte_gegenstuecke(con: sqlite3.Connection, term: str,
                          richtung: str) -> set[str]:
    """Bereits belegte EXAKTE Glossar-Gegenstuecke (normalisiert) - Grundlage der
    Widerspruchspruefung."""
    return {glossar.norm_begriff(z["term_en" if richtung == "de_en" else "term_de"])
            for z in glossar.lookup(con, term, richtung=richtung)
            if z["match"] == "exakt"}


def finde_zauber_paare(con: sqlite3.Connection
                       ) -> tuple[list[tuple[str, str, str]], list[str]]:
    """[(term_en, term_de, beweis), ...] + Verwerfungs-Report.

    Deutsche Seite: alle deutschsprachigen Eintraege mit Zauberkopf (jede Edition).
    Englische Seite: alle englischsprachigen ebenso. Gepaart wird ein Fingerabdruck
    nur, wenn er auf BEIDEN Seiten genau einmal vorkommt und keiner bereits belegten
    Glossar-Zeile widerspricht."""
    de: dict[tuple, list[str]] = defaultdict(list)
    en: dict[tuple, list[str]] = defaultdict(list)
    for zeile in con.execute(
            "SELECT e.name_de, e.body_md FROM eintraege e "
            "WHERE e.sprache='de' AND e.name_de IS NOT NULL"):
        abdruck = fingerabdruck(zeile[1], deutsch=True)
        if abdruck:
            de[abdruck].append(zeile[0].strip())
    for zeile in con.execute(
            "SELECT e.name_en, e.body_md FROM eintraege e "
            "WHERE e.sprache='en' AND e.name_en IS NOT NULL"):
        abdruck = fingerabdruck(zeile[1], deutsch=False)
        if abdruck:
            en[abdruck].append(zeile[0].strip())

    paare: list[tuple[str, str, str]] = []
    report: list[str] = []
    for abdruck in sorted(set(de) & set(en), key=str):
        de_namen = {n for n in de[abdruck]}
        en_namen = {n for n in en[abdruck]}
        if len(de_namen) != 1 or len(en_namen) != 1:
            report.append(f"Grad {abdruck[0]} {abdruck[1]}: {len(de_namen)} DE vs. "
                          f"{len(en_namen)} EN nicht eindeutig - verworfen "
                          f"({', '.join(sorted(de_namen)[:3])} | "
                          f"{', '.join(sorted(en_namen)[:3])})")
            continue
        term_de, term_en = next(iter(de_namen)), next(iter(en_namen))
        if glossar.norm_begriff(term_de) == glossar.norm_begriff(term_en):
            continue                                  # gleiches Wort - keine Bruecke noetig
        # Widerspruchspruefung: kennt das Glossar fuer eine der beiden Seiten bereits
        # ein ANDERES exaktes Gegenstueck, ist der Fingerabdruck-Treffer nicht belastbar.
        belegt_en = _belegte_gegenstuecke(con, term_de, "de_en")
        belegt_de = _belegte_gegenstuecke(con, term_en, "en_de")
        if belegt_en and glossar.norm_begriff(term_en) not in belegt_en:
            report.append(f"{term_de} -> {term_en}: widerspricht belegtem Paar "
                          f"({sorted(belegt_en)[:2]}) - verworfen")
            continue
        if belegt_de and glossar.norm_begriff(term_de) not in belegt_de:
            report.append(f"{term_en} -> {term_de}: widerspricht belegtem Paar "
                          f"({sorted(belegt_de)[:2]}) - verworfen")
            continue
        paare.append((term_en, term_de, "zauberkopf"))
    return paare, report
