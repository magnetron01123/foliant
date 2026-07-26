"""Gegenstands-Bruecke DE<->EN per Struktur-Abgleich aus dem Bestand (26.07.2026).

Befund (glossar-audit): 'gegenstand' traegt die groesste echte Deutsch-Luecke (~42 %
en_ohne), obwohl srd-de die Ausruestung vollstaendig deutsch fuehrt. Zwei Ursachen:
- Die Open5e-Namen tragen Preis-Suffixe ("Alchemist's Supplies (50 GP)") - das
  dnddeutsch-Seeding fragte damit an und fand nie etwas.
- Fuer 2024-neue Namen kennt dnddeutsch die Paare ohnehin nicht.

Abgleich (strukturelle Identitaet, KEIN Uebersetzungs-Raten - Datenprinzip wie
srd_klassenmerkmale/_finde_monster_paare):
- DE: srd-de-Gegenstaende mit Preis im NAMEN ("Rucksack (2 GM)").
- EN: Open5e-Gegenstaende mit Preis in Name oder Body ("**Cost:** 2.00 gp").
- Bucket = (Preis in GM, Grobkategorie Werkzeug/Waffe/Ruestung/Sonstiges) - beide
  Seiten bilden dieselbe SRD-Preisliste ab.
- Paarung nur bei (a) bereits belegtem exaktem Glossar-Paar der suffixfreien Namen
  oder (b) Ausschlussprinzip (genau EIN Rest je Seite im Bucket). Kein Gewichts-/
  Zahlenabgleich: srd-de rechnet metrisch um (30 pounds -> 15 Kilogramm), die
  Umrechnung ist keine belastbare Identitaet. Unaufloesbare Buckets werden verworfen
  und im Report genannt (lieber eine Luecke als ein falsches Paar).

Geseedet wird NUR die suffixfreie Kurzform ("Backpack" -> "Rucksack"): ein zweites
'offizielles' Paar mit vollem Namen ("Kerze (1 KM)") wuerde neben der dnddeutsch-Zeile
("Kerze") genau die EN->mehrere-offizielle-DE-Konflikte erzeugen, die glossar-audit als
'falsches Deutsch'-Risiko flaggt. Eintragsnamen MIT Suffix treffen die Bruecke trotzdem,
weil Dedupe und Anzeige den kanonischen Klammer-Suffix-Abzug anwenden
(glossar.KLAMMER_SUFFIX, SYN-P0-002)."""
from __future__ import annotations

import re
import sqlite3

from app import glossar

QUELLE = "SRD 5.2.1 (Strukturabgleich Gegenstaende)"

_PREIS_DE = re.compile(r"\((\d+(?:[.,]\d+)?)\s*(GM|SM|KM)\)")
_PREIS_EN_NAME = re.compile(r"\((\d+(?:\.\d+)?)\s*(GP|SP|CP)\)", re.I)
_PREIS_EN_BODY = re.compile(r"\*\*Cost:\*\*\s*(\d+(?:\.\d+)?)\s*(gp|sp|cp)", re.I)
_KATEGORIE_EN = re.compile(r"\*\*Category:\*\*\s*([^·\n]+)")
_KONTEXT = re.compile(r"^\*Kontext:\s*(.+?)\*\s*$", re.M)
_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")

# Muenzkurse relativ zur Goldmuenze - identisch in beiden Fassungen (SRD-Preisliste).
_KURS = {"gm": 1.0, "gp": 1.0, "sm": 0.1, "sp": 0.1, "km": 0.01, "cp": 0.01}


def _preis_cent(zahl: str, einheit: str, deutsch: bool) -> int:
    """Preis als GM-Cent (int) - vermeidet Float-Vergleiche ueber die Bucket-Schluessel.
    Deutsche Schreibweise: Punkt ist TAUSENDER-Trenner ('Fernrohr (1.000 GM)' = 1000 GM),
    Komma das Dezimalzeichen; englisch umgekehrt."""
    if deutsch:
        zahl = zahl.replace(".", "").replace(",", ".")
    return round(float(zahl) * _KURS[einheit.lower()] * 100)


def _preis_de(name: str | None) -> int | None:
    m = _PREIS_DE.search(name or "")
    return _preis_cent(m.group(1), m.group(2), deutsch=True) if m else None


def _preis_en(name: str | None, body: str | None) -> int | None:
    m = _PREIS_EN_NAME.search(name or "") or _PREIS_EN_BODY.search(body or "")
    return _preis_cent(m.group(1), m.group(2), deutsch=False) if m else None


def _grob_de(body: str | None) -> str:
    """Grobkategorie aus der srd-de-Kontextzeile. Segment-EXAKT vergleichen - ein
    Substring-Test wuerde jede 'Ausruestung > ...'-Zeile als 'ruestung' einordnen."""
    m = _KONTEXT.search(body or "")
    segmente = {s.strip().lower() for s in (m.group(1) if m else "").split(">")}
    if segmente & {"werkzeug", "handwerkszeug"}:
        return "werkzeug"
    if "waffen" in segmente:
        return "waffe"
    if "rüstung" in segmente:
        return "ruestung"
    return "sonstig"


def _grob_en(body: str | None) -> str:
    m = _KATEGORIE_EN.search(body or "")
    kategorie = (m.group(1) if m else "").strip().lower()
    if kategorie == "tools":
        return "werkzeug"
    if kategorie == "weapon":
        return "waffe"
    if kategorie == "armor":
        return "ruestung"
    return "sonstig"


def _kurz(name: str) -> str:
    return _SUFFIX.sub("", name).strip()


def _belegte_de(con: sqlite3.Connection, term_en: str) -> set[str]:
    """Bereits belegte deutsche Formen (nur EXAKTE Glossar-Zeilen, SYN-P0-001) -
    normalisiert, damit Gross-/Kleinschreibung nicht entscheidet."""
    return {glossar.norm_begriff(z["term_de"])
            for z in glossar.lookup(con, term_en, richtung="en_de")
            if z["match"] == "exakt"}


def finde_gegenstands_paare(con: sqlite3.Connection
                            ) -> tuple[list[tuple[str, str, str]], list[str]]:
    """[(term_en, term_de, beweisstufe), ...] + Verwerfungs-Report.
    beweisstufe: 'glossar-hop' | 'ausschluss'. Es werden nur VOLLE Eintragsnamen
    geliefert - die Kurzform-Ableitung macht der Seeder (alle Varianten gehoeren
    zum selben Beweis)."""
    de_rows = con.execute(
        "SELECT e.name_de, e.body_md FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
        "WHERE q.kuerzel = 'srd-de' AND e.kategorie = 'gegenstand' "
        "AND e.edition = '2024' AND e.name_de IS NOT NULL ORDER BY e.id").fetchall()
    en_rows = con.execute(
        "SELECT e.name_en, e.body_md FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
        "WHERE q.kuerzel = 'open5e-srd-2024' AND e.kategorie = 'gegenstand' "
        "AND e.name_en IS NOT NULL ORDER BY e.id").fetchall()

    # Bucket = NUR der Preis. Die Grobkategorie ist bewusst KEINE Bucket-Dimension:
    # die Quellen kategorisieren abweichend (Open5e fuehrt 'Torch' als Weapon, srd-de
    # die Fackel unter Abenteurerausruestung) - als harte Dimension wuerde sie echte
    # Paare trennen. Sie dient nur als Sub-Ausschluss-Ebene INNERHALB des Preis-Buckets.
    buckets: dict[int, tuple[list[tuple[str, str]], list[tuple[str, str]]]] = {}
    for name_de, body in de_rows:
        preis = _preis_de(name_de)
        if preis is None:
            continue                       # ohne Preis kein Bucket - keine Aussage
        buckets.setdefault(preis, ([], []))[0].append((name_de, _grob_de(body)))
    for name_en, body in en_rows:
        preis = _preis_en(name_en, body)
        if preis is None:
            continue
        buckets.setdefault(preis, ([], []))[1].append((name_en, _grob_en(body)))

    paare: list[tuple[str, str, str]] = []
    report: list[str] = []
    for preis, (de_liste, en_liste) in sorted(buckets.items()):
        offen_de = {glossar.norm_begriff(_kurz(n)): (n, g) for n, g in de_liste}
        offen_en = dict(enumerate(en_liste))

        def _fixiere(schluessel_de, j, stufe: str) -> None:
            paare.append((offen_en.pop(j)[0], offen_de.pop(schluessel_de)[0], stufe))

        # Gleichnamige (nach Suffix-/Diakritika-Normalisierung) brauchen keine Bruecke
        # ('Sack' == 'Sack (1 KM)') - aus dem Bucket nehmen, sonst blockieren sie den
        # Ausschluss fuer die echten Kandidaten.
        for j, (en, _g) in list(offen_en.items()):
            k = glossar.norm_begriff(_kurz(en))
            if k in offen_de:
                offen_de.pop(k)
                offen_en.pop(j)
        # (a) belegte exakte Glossar-Paare der suffixfreien Namen
        for j, (en, _g) in list(offen_en.items()):
            treffer = [k for k in offen_de if k in _belegte_de(con, _kurz(en))]
            if len(treffer) == 1:
                _fixiere(treffer[0], j, "glossar-hop")
        # (b) Sub-Ausschluss je uebereinstimmender Grobkategorie
        for grob in ("werkzeug", "waffe", "ruestung", "sonstig"):
            kd = [k for k, (_n, g) in offen_de.items() if g == grob]
            ke = [j for j, (_n, g) in offen_en.items() if g == grob]
            if len(kd) == 1 and len(ke) == 1:
                _fixiere(kd[0], ke[0], "ausschluss-kategorie")
        # (c) Gesamt-Ausschluss: genau EIN Rest je Seite, Kategorien nicht widerspruechlich
        if len(offen_de) == 1 and len(offen_en) == 1:
            (kd, (_nd, gd)), = offen_de.items()
            (ke, (_ne, ge)), = offen_en.items()
            if gd == ge or "sonstig" in (gd, ge):
                _fixiere(kd, ke, "ausschluss")
        if offen_de or offen_en:
            report.append(
                f"Preis {preis / 100:g} GM: {len(offen_de)} DE vs. "
                f"{len(offen_en)} EN nicht eindeutig - verworfen "
                f"({', '.join(sorted(n for n, _g in offen_de.values())[:3])} | "
                f"{', '.join(sorted(n for n, _g in offen_en.values())[:3])})")
    return paare, report


def seed_paar(term_en: str, term_de: str) -> tuple[str, str]:
    """Die zu seedende suffixfreie Form eines gefundenen Paars (Modul-Doku: volle Namen
    wuerden Glossar-Konflikte neben den dnddeutsch-Zeilen erzeugen)."""
    return _kurz(term_en) or term_en, _kurz(term_de) or term_de
