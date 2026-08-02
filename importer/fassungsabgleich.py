"""Facetten gegen die GESCHWISTERFASSUNGEN pruefen - der Bestand als eigener Zeuge.

Befund aus dem Nutzer-Simulationslauf (01.08.2026): Der deutsche Ghul-Statblock
enthaelt durch einen Chunking-Unfall den Kopf der Geisternaga, und weil
`monster_hg` den ERSTEN Treffer nimmt, stand der Ghul mit HG 8 statt 1 im Bestand -
eine HG-1-Suche fand ihn nicht, eine HG-8-Suche lieferte ihn falsch.

Der Ausweg ist NICHT, den Regeltext umzuschreiben: was in der Quelle steht, bleibt
stehen (B1 - der Bestand ist die Wahrheit, auch wenn er beschaedigt ist). Korrigiert
wird nur die abgeleitete FACETTE, und zwar mit bestandsinterner Evidenz: Dieselbe
Kreatur bzw. derselbe Zauber liegt fast immer in mehreren Fassungen vor - sie
entscheiden, WELCHER der im Text stehenden Werte der eigene ist.

Drei Regeln, alle bewusst streng:
  1. Korrigiert wird NUR eine Mehrdeutigkeit - wenn der eigene Text mehrere Werte
     hergibt. Die Geschwister WAEHLEN dann unter den vorhandenen Kandidaten aus; sie
     bringen nie einen fremden Wert ein.
  2. Nur EINSTIMMIGKEIT zaehlt. Uneinige Geschwister aendern nichts.
  3. Ohne Geschwister wird nichts geraten. Der verschmolzene Statblock bekommt dann
     gar keinen Wert: eine fehlende Facette ist ein fehlendes Feld, ein falscher Wert
     eine falsche Auskunft.

Regel 1 ist mit Absicht so eng, und der Trockenlauf hat gezeigt warum: Ein frueherer
Entwurf korrigierte auch den blossen WIDERSPRUCH (ein Text, ein Wert, andere Fassung
anderer Wert). Er haette 'Summon Celestial' im englischen PHB von Grad 5 auf 7
gezogen - Zeuge war der deutsche SRD-Eintrag 'Celestisches Wesen beschwoeren' (Grad 7),
verbunden ueber eine Glossarzeile aus einem 2014er Band. Ob dahinter ein Schaden, eine
Editionsdifferenz oder eine falsche Begriffszuordnung steckt, kann diese Regel nicht
entscheiden - also entscheidet sie es nicht. Solche Faelle meldet `widersprueche()`
zum Nachsehen, statt sie stillschweigend umzuschreiben (B4: nicht raten).

Gemessen am Pi-Vollbestand (01.08.2026): 9 Monster tragen zwei HG-Angaben, die
Geschwister loesen alle neun eindeutig auf - sie bestaetigen die sechs bereits
richtigen Werte und korrigieren drei (Junger Bronzedrache 15->8, Dschinni 1->11,
Ghul 8->1).
"""
from __future__ import annotations

import re
import sqlite3

from app.glossar import norm_begriff as _n

# Alle HG-Angaben eines Statblocks in Textreihenfolge. Mehr als eine heisst: in diesem
# Eintrag steckt ein zweiter Statblock (Seitenumbruch im Druck-PDF).
_HG_ALLE = re.compile(r"\*\*(?:HG|CR)\*\*\s*([0-9/]+)")

# Was verglichen wird: Kategorie -> (Meta-Tabelle, Spalte, Kandidaten-Leser).
_PRUEFUNGEN = {
    "monster": ("monster_meta", "hg", lambda body: _HG_ALLE.findall(body or "")),
    # Zauber tragen nur EINEN Kopfwert; hier faellt nur der Widerspruch auf, nicht eine
    # Mehrdeutigkeit. Kandidatenliste bleibt leer - der Vergleich laeuft ueber den
    # bereits abgeleiteten Wert.
    "zauber": ("zauber_meta", "grad", lambda body: []),
}


def _namensvarianten(con: sqlite3.Connection, name_de: str | None,
                     name_en: str | None) -> set[str]:
    """Normalisierte Namen, unter denen derselbe Eintrag in anderen Quellen steht.
    Die Glossar-Bruecke ist noetig, weil die deutschen Fassungen 'Ghul' heissen und
    die englischen 'Ghoul' - ohne sie faende ein srd-de-Eintrag nie ein Geschwister."""
    varianten = {_n(name_de), _n(name_en)} - {""}
    for spalte, gesucht in (("term_en", name_de), ("term_de", name_en)):
        if not gesucht:
            continue
        for zeile in con.execute(
                f"SELECT {spalte} AS treffer FROM glossar WHERE lower(?) IN "
                f"(lower(term_de), lower(term_en))", (gesucht,)):
            varianten.add(_n(zeile["treffer"] if isinstance(zeile, sqlite3.Row)
                             else zeile[0]))
    return varianten - {""}


def _geschwisterwerte(con: sqlite3.Connection, kategorie: str, tabelle: str,
                      spalte: str, eintrag: sqlite3.Row) -> set[str]:
    """Der Wert derselben Option in ANDEREN Quellen, gleiche Regelversion.

    Gleiche Edition ist Bedingung, nicht Kosmetik: 2014 und 2024 unterscheiden sich in
    Graden und Herausforderungsgraden legitim - ein Vergleich ueber die Editionsgrenze
    wuerde echte Regelunterschiede als Importfehler 'korrigieren' (A4)."""
    varianten = _namensvarianten(con, eintrag["name_de"], eintrag["name_en"])
    if not varianten:
        return set()
    werte = set()
    for zeile in con.execute(
            f"SELECT e.name_de, e.name_en, m.{spalte} AS wert FROM eintraege e "
            f"JOIN {tabelle} m ON m.eintrag_id = e.id "
            f"WHERE e.kategorie = ? AND e.edition = ? AND e.quelle_id <> ? "
            f"AND m.{spalte} IS NOT NULL",
            (kategorie, eintrag["edition"], eintrag["quelle_id"])):
        if _n(zeile["name_de"]) in varianten or _n(zeile["name_en"]) in varianten:
            werte.add(str(zeile["wert"]))
    return werte


def gleiche_facetten_ab(con: sqlite3.Connection) -> list[dict]:
    """Widersprueche und Mehrdeutigkeiten aufloesen; liefert das Protokoll der
    Aenderungen (leer = nichts zu tun). Laeuft NACH dem Seeder auf demselben Bestand.

    Jede Aenderung steht im Protokoll - eine stille Korrektur an Regeldaten waere
    genau das, was dieses Projekt sonst jedem Sprachmodell verbietet."""
    con.row_factory = sqlite3.Row
    protokoll: list[dict] = []
    for kategorie, (tabelle, spalte, kandidaten_aus) in _PRUEFUNGEN.items():
        eintraege = con.execute(
            f"SELECT e.id, e.name_de, e.name_en, e.edition, e.quelle_id, e.body_md, "
            f"m.{spalte} AS wert FROM eintraege e "
            f"JOIN {tabelle} m ON m.eintrag_id = e.id "
            f"WHERE e.kategorie = ? AND m.{spalte} IS NOT NULL", (kategorie,)).fetchall()
        for eintrag in eintraege:
            kandidaten = kandidaten_aus(eintrag["body_md"])
            if len(set(kandidaten)) < 2:
                continue                      # eindeutiger Text: nichts zu entscheiden
            geschwister = _geschwisterwerte(con, kategorie, tabelle, spalte, eintrag)
            eigener = str(eintrag["wert"])
            neu = next(iter(geschwister)) if len(geschwister) == 1 else None
            # Der Geschwisterwert muss auch WIRKLICH im eigenen Text stehen - sonst
            # waehlte der Abgleich nicht unter den Kandidaten aus, sondern brachte
            # einen fremden Wert ein (Regel 1).
            if neu is not None and neu not in kandidaten:
                neu = None
            if str(neu) == eigener:
                continue
            con.execute(f"UPDATE {tabelle} SET {spalte} = ? WHERE eintrag_id = ?",
                        (neu, eintrag["id"]))
            protokoll.append({"eintrag_id": eintrag["id"],
                              "name": eintrag["name_de"] or eintrag["name_en"],
                              "kategorie": kategorie, "feld": spalte,
                              "vorher": eigener, "nachher": neu,
                              "grund": "mehrdeutig",
                              "zeugen": sorted(geschwister)})
    return protokoll


def widersprueche(con: sqlite3.Connection) -> list[dict]:
    """NUR melden, nichts aendern: Eintraege, deren eindeutiger Textwert dem
    einstimmigen Wert ihrer Geschwisterfassungen widerspricht.

    Das ist die Halde der Faelle, die `gleiche_facetten_ab` bewusst NICHT anfasst -
    dahinter kann ein Importschaden stecken, eine Editionsdifferenz oder eine falsche
    Glossar-Zuordnung. Welches davon, entscheidet ein Mensch am Einzelfall."""
    con.row_factory = sqlite3.Row
    befunde: list[dict] = []
    for kategorie, (tabelle, spalte, kandidaten_aus) in _PRUEFUNGEN.items():
        for eintrag in con.execute(
                f"SELECT e.id, e.name_de, e.name_en, e.edition, e.quelle_id, e.body_md, "
                f"q.kuerzel, m.{spalte} AS wert FROM eintraege e "
                f"JOIN quellen q ON q.id = e.quelle_id "
                f"JOIN {tabelle} m ON m.eintrag_id = e.id "
                f"WHERE e.kategorie = ? AND m.{spalte} IS NOT NULL",
                (kategorie,)).fetchall():
            if len(set(kandidaten_aus(eintrag["body_md"]))) > 1:
                continue                      # Mehrdeutigkeit loest der Abgleich selbst
            geschwister = _geschwisterwerte(con, kategorie, tabelle, spalte, eintrag)
            if len(geschwister) == 1 and str(eintrag["wert"]) not in geschwister:
                befunde.append({"eintrag_id": eintrag["id"],
                                "name": eintrag["name_de"] or eintrag["name_en"],
                                "quelle": eintrag["kuerzel"], "kategorie": kategorie,
                                "feld": spalte, "eigener": str(eintrag["wert"]),
                                "fassungen": sorted(geschwister)})
    return befunde
