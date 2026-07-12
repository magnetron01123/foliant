"""Charaktererstellungs-Werkzeuge (F3/B7). Namensschema foliant_<verb>_<nomen> (BP #2).

Listen = KNAPPE Kataloge der waehlbaren Optionen (BP #1); Details laufen ueber die
_hole_detail-Maschine von nachschlagen. Die Build-Pruefung (Q4) validiert NUR gegen den
2024-Bestand, nennt ihre Datenbasis und weist offen aus, was sie nicht pruefen kann -
sie ist Hilfe, keine letzte Instanz.

Options-Erkennung je Quelle (Justage-Stelle fuer neue Quellen, vgl. bekannte_macken):
- Kapitel-Quellen (Body beginnt mit '*Kontext: ...*', z. B. srd-de): echte Optionen stehen
  unter 'Beschreibungen der ...'-Kontexten; Grundklassen haben Kontext exakt 'Klassen',
  Unterklassen das Namensschema '<Klasse>-Unterklasse: <Name>'.
- Katalog-Quellen (ohne Kontextzeile, z. B. Open5e): 1 Eintrag = 1 Option; Unterklassen
  tragen '*Subclass of: X*' im Body.
Deutsche und englische Eintraege desselben Inhalts werden ueber die Glossar-Bruecke
zusammengefuehrt (Fighter <-> Kaempfer); deutsche Quelle fuehrt (S10/Q2).

Die Regel-Konstanten (Standardsatz, Punktkosten) sind am Bestand verifiziert
(srd-de 'Schritt 3: Attributswerte', S. 9); alle weiteren Pruefwerte (Hintergrund-
Attribute, Unterklassen-Stufe, Waffenbeherrschungs-Anzahl) werden zur LAUFZEIT aus den
Bestandseintraegen geparst - nicht aus Allgemeinwissen (B1)."""
from __future__ import annotations

import re
from typing import Literal

from app import glossar as _glossar
from app.tools import nachschlagen as _ns

STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]
POINT_BUY_KOSTEN = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
POINT_BUY_BUDGET = 27

_KONTEXT = re.compile(r"^\*Kontext: (.+?)\*")
_SUBCLASS = re.compile(r"^\*Subclass of:\s*(.+?)\*", re.MULTILINE)
_UNTERKLASSE_DE = re.compile(r"^(.+)-Unterklasse:\s*(.+)$")
_HG_ATTRIBUTE = re.compile(r"\*\*Attributswerte:\*\*\s*([^\n*]+)")
_HG_TALENT = re.compile(r"\*\*Talent:\*\*\s*([^\n(]+)")

# Kapitel-/Gruppen-Header, unter denen echte Optionen DIREKT stehen - je Kategorie und ueber
# ALLE Quellen (dt. SRD + DDB-Buecher). Eine Option wird am LETZTEN Kontext-Segment erkannt:
# 'Aasimar' liegt unter 'Species Descriptions' (Header -> Option), 'Aasimar Traits' unter
# 'Species Descriptions > Aasimar' (Speziesname -> Unterabschnitt, KEINE Option). So erscheinen
# DDB-Optionen (Aasimar, Alert, Haunted One) konsistent zur Build-Pruefung in den Listen, ohne
# Merkmals-/Abstammungs-Unterabschnitte (QS-Folgeaufgabe 11.07.2026). Fuer neue Quellen hier
# den jeweiligen Kapitel-/Gruppentitel ergaenzen.
_OPTION_KONTEXT = {
    # IGNORECASE: DDB-Druck-PDFs liefern Kapitel-Header in GROSSBUCHSTABEN ('BACKGROUNDS').
    "spezies": re.compile(
        r"^(?:Beschreibungen der Spezies|Species Descriptions|Character Species|Species"
        r"|Races)$", re.IGNORECASE),
    "hintergrund": re.compile(
        r"^(?:Beschreibungen der Hintergründe|Backgrounds?|Background Descriptions)$",
        re.IGNORECASE),
    "talent": re.compile(
        r"^(?:(?:Origin|General|Fighting Style|Epic Boon|Dragonmark) Feats|Epic Boon Feat"
        r"|Dark Gifts|Herkunftstalente|Allgemeine Talente|Kampfstil-Talente"
        r"|Epische-Gabe-Talente)$", re.IGNORECASE),
}
# Talent-Kategorie aus der TYPZEILE des Eintrags ('_Epische-Gabe-Talent (Voraussetzung:
# min. 19. Stufe)_') - NICHT aus dem Kontext-Breadcrumb: die zweispaltige Talent-Seite des
# dt. SRD kommt in falscher Spalten-Lesereihenfolge an, drei Gaben stehen dadurch unterm
# 'Kampfstil-Talente'-Heading (bekannte_macken). Die Typzeile steht IM Eintrag und stimmt.
_TALENT_TYPZEILE = re.compile(
    r"_(Herkunftstalent|Allgemeines Talent|Kampfstil-Talent|Epische-Gabe-Talent)"
    r"(?:\s*\(Voraussetzung:\s*([^)]+)\))?_?")
_TALENT_KATEGORIEN = {"Herkunftstalent": "herkunft", "Allgemeines Talent": "allgemein",
                      "Kampfstil-Talent": "kampfstil",
                      "Epische-Gabe-Talent": "epische_gabe"}
# DDB-Feats tragen KEINE deutsche Typzeile - ihre Kategorie steht im letzten Kontext-Segment
# (der Feat-Gruppe). Fallback, damit auch DDB-Talente kategorisiert in der Liste erscheinen.
# Lookup case-normalisiert (.title()): DDB-Druck-PDFs liefern 'GENERAL FEATS'.
_DDB_TALENT_GRUPPE = {"Origin Feats": "herkunft", "General Feats": "allgemein",
                      "Fighting Style Feats": "kampfstil", "Epic Boon Feats": "epische_gabe",
                      "Epic Boon Feat": "epische_gabe", "Dark Gifts": "allgemein",
                      "Dragonmark Feats": "allgemein"}

_ATTRIBUTE = ("stärke", "geschicklichkeit", "konstitution", "intelligenz", "weisheit",
              "charisma")
_ATTR_ALIAS = {"str": "stärke", "strength": "stärke", "staerke": "stärke",
               "dex": "geschicklichkeit", "dexterity": "geschicklichkeit",
               "ges": "geschicklichkeit",
               "con": "konstitution", "constitution": "konstitution", "kon": "konstitution",
               "int": "intelligenz", "intelligence": "intelligenz",
               "wis": "weisheit", "wisdom": "weisheit", "wei": "weisheit",
               "cha": "charisma"}

_HINWEIS_REIHENFOLGE = ("2024-Reihenfolge der Charaktererstellung (B7): 1. Klasse -> "
                        "2. Hintergrund -> 3. Spezies -> 4. Details. Schritt fuer Schritt "
                        "fuehren, nicht alle Optionen auf einmal ausschuetten. WICHTIG "
                        "(SYN-P2-005): Zur Herkunft gehoeren laut Regeltext auch ZWEI "
                        "SPRACHEN und Spezies-Pflichtwahlen (z. B. Elfen-Abstammung, "
                        "Mensch-Zusatztalent) - abfragen, nicht ueberspringen; danach "
                        "Attributswerte und Gesinnung.")
_HINWEIS_BESTAND = ("Nur Optionen aus dem Bestand. Fehlt eine erwartete Option (z. B. "
                    "Aasimar im reinen SRD), das ehrlich sagen - evtl. fehlt ein Buch (B2). "
                    "Nichts aus Allgemeinwissen ergaenzen (B1).")


def _norm(text: str | None) -> str:
    return (text or "").strip().lower()


def _kontext(body: str | None) -> str:
    m = _KONTEXT.match(body or "")
    return m.group(1) if m else ""


_EDITION = "2024"   # Charakterlisten und Build-Pruefung sind STRIKT 2024 (A4/Q4)


def _eintraege(con, kategorie: str) -> list[dict]:
    """Eintraege einer Kategorie, NUR Edition 2024 (A4: Listen liefern ausschliesslich
    2024-Optionen; aeltere Staende mischen nie mit), prioritaets-sortiert (Q2)."""
    return [dict(r) for r in con.execute(
        """SELECT e.id, e.kategorie, e.name_de, e.name_en, e.sprache, e.edition, e.seite,
                  e.body_md, q.titel AS quelle_titel, q.prioritaet
           FROM eintraege e JOIN quellen q ON q.id = e.quelle_id
           WHERE e.kategorie = ? AND e.edition = ? ORDER BY q.prioritaet, e.id""",
        (kategorie, _EDITION))]


def _ist_option(e: dict, kategorie: str) -> bool:
    """Waehlbare Option vs. Struktur-/Unterabschnitt (Modul-Doku). Entscheidend ist das
    LETZTE Kontext-Segment: steht der Eintrag DIREKT unter einem Kapitel-/Gruppen-Header,
    ist er eine Option; nistet er unter einem konkreten Optionsnamen ('... > Aasimar'),
    ist er ein Unterabschnitt (Merkmale/Abstammung) und keine eigene Option."""
    kontext = _kontext(e["body_md"])
    if not kontext:
        return True                       # Katalog-Quelle (Open5e): 1 Eintrag = 1 Option
    muster = _OPTION_KONTEXT.get(kategorie)
    letztes_segment = kontext.split(" > ")[-1].strip()
    return bool(muster and muster.match(letztes_segment))


def _varianten(con, e: dict) -> set[str]:
    """Namensvarianten (inkl. Glossar-Uebersetzungen) fuer die DE<->EN-Zusammenfuehrung.
    Das srd-de-Unterklassenschema '<Klasse>-Unterklasse: <Name>' zaehlt auch mit dem
    blanken Namen (sonst findet 'College of Lore' die 'Schule des Wissens' nicht)."""
    namen: list[tuple[str, str]] = []
    for name, richtung in ((e.get("name_de"), "de_en"), (e.get("name_en"), "en_de")):
        if not name:
            continue
        namen.append((name, richtung))
        m = _UNTERKLASSE_DE.match(name)
        if m:
            namen.append((m.group(2).strip(), richtung))
    v: set[str] = set()
    for name, richtung in namen:
        v.add(_norm(name))
        # NUR exakte Glossarzeilen gruppieren (SYN-P0-001): Fuzzy-Naehe wuerde zwei
        # VERSCHIEDENE Optionen zu einer Listenzeile verschmelzen.
        exakte = [z for z in _glossar.lookup(con, name, richtung=richtung)
                  if z["match"] == "exakt"]
        for z in exakte[:3]:
            v |= {_norm(z["term_de"]), _norm(z["term_en"])}
    return v - {""}


def _gruppiere(con, eintraege: list[dict]) -> list[dict]:
    """Fuehrt DE- und EN-Eintraege derselben Option zusammen (Kaempfer + Fighter = eine
    Zeile). Eintraege sind prioritaets-sortiert -> die deutsche Quelle fuehrt (S10)."""
    gruppen: list[dict] = []
    for e in eintraege:
        v = _varianten(con, e)
        g = next((g for g in gruppen if g["varianten"] & v), None)
        if g is None:
            g = {"varianten": set(), "eintraege": []}
            gruppen.append(g)
        g["varianten"] |= v
        g["eintraege"].append(e)
    return gruppen


def _zeile(con, g: dict, **extra) -> dict:
    """Knappe Listen-Zeile einer Options-Gruppe: Anzeige Deutsch-first (S3/S4)."""
    name_de = next((e["name_de"] for e in g["eintraege"] if e["name_de"]), None)
    name_en = next((e["name_en"] for e in g["eintraege"] if e["name_en"]), None)
    fuehrend = g["eintraege"][0]
    if name_de and name_en and _norm(name_de) == _norm(name_en):
        anzeige = name_de                       # 'Champion (Champion)' vermeiden
    elif name_de and name_en:
        anzeige = _glossar.markiere(name_de, name_en, offiziell=True)
    else:
        anzeige = _ns._anzeige_name(con, {"name_de": name_de, "name_en": name_en,
                                          "sprache": "de" if name_de else "en"})
    z = {"anzeige": anzeige, "name_de": name_de, "name_en": name_en,
         "edition": fuehrend["edition"],
         "quellen": sorted({e["quelle_titel"] for e in g["eintraege"]})}
    z.update({k: v for k, v in extra.items() if v is not None})
    return z


def _liste(kategorie: str, schluessel: str, schritt_hinweis: str) -> dict:
    """Gemeinsame Listen-Maschine fuer Spezies/Hintergruende/Talente."""
    con = _ns._verbinde()
    if con is None:
        return {schluessel: [], "hinweis": _ns.HINWEIS_DB_FEHLT}
    try:
        optionen = [e for e in _eintraege(con, kategorie) if _ist_option(e, kategorie)]
        zeilen = []
        for g in _gruppiere(con, optionen):
            extra = {}
            if kategorie == "talent":
                m = next((m for e in g["eintraege"]
                          if (m := _TALENT_TYPZEILE.search(e["body_md"] or ""))), None)
                if m:                                    # dt. SRD: Kategorie aus der Typzeile
                    extra["kategorie"] = _TALENT_KATEGORIEN.get(m.group(1))
                    extra["voraussetzung"] = (m.group(2) or "").strip() or None
                else:                                    # DDB-Feat: aus der Kontext-Feat-Gruppe
                    gruppe = next((_DDB_TALENT_GRUPPE[seg.title()] for e in g["eintraege"]
                                   if (seg := _kontext(e["body_md"]).split(" > ")[-1].strip())
                                   .title() in _DDB_TALENT_GRUPPE), None)
                    if gruppe:
                        extra["kategorie"] = gruppe
            zeilen.append(_zeile(con, g, **extra))
        zeilen.sort(key=lambda z: _norm(z["name_de"] or z["name_en"]))
        antwort = {schluessel: zeilen, "hinweis_reihenfolge": schritt_hinweis,
                   "hinweis": _HINWEIS_BESTAND}
        if not zeilen:
            antwort["hinweis"] = _ns.HINWEIS_LEER
        return antwort
    finally:
        con.close()


def foliant_liste_spezies() -> dict:
    """Waehlbare Spezies im Bestand (KNAPPE Liste; Details per foliant_hol_spezies).
    Schritt 3 der 2024-Charaktererstellung - Klasse und Hintergrund kommen davor (B7).
    KERNREGELN: nur Bestand nennen, nichts aus Allgemeinwissen ergaenzen; Deutsch-first
    mit englischem Original in Klammern; Quelle und Regelversion nennen."""
    return _liste("spezies", "spezies",
                  "Spezies ist SCHRITT 3 von 4 (nach Klasse und Hintergrund). " +
                  _HINWEIS_REIHENFOLGE)


def foliant_liste_hintergruende() -> dict:
    """Waehlbare Hintergruende im Bestand (KNAPPE Liste; Details per
    foliant_hol_hintergrund). Schritt 2 der 2024-Charaktererstellung (B7). Ein Hintergrund
    liefert Attributserhoehungen, ein Ursprungstalent, Fertigkeiten und Ausruestung.
    KERNREGELN: nur Bestand; Deutsch-first (Original in Klammern); Quelle+Version nennen."""
    return _liste("hintergrund", "hintergruende",
                  "Hintergrund ist SCHRITT 2 von 4 (nach der Klasse). " +
                  _HINWEIS_REIHENFOLGE)


def foliant_liste_talente(kategorie: Literal["herkunft", "allgemein",
        "kampfstil", "epische_gabe"] | None = None) -> dict:
    """Talente (Feats) im Bestand, KNAPP (Details per foliant_hol_talent). kategorie
    optional, exakt: herkunft | allgemein | kampfstil | epische_gabe - andere Werte
    werden mit 'fehler' abgelehnt (kein 'nichts im Bestand'). Herkunftstalente kommen
    ueber den Hintergrund (Schritt 2), weitere Talente ueber Stufenaufstiege.
    KERNREGELN: nur Bestand; Deutsch-first (Original in Klammern); Quelle+Version nennen."""
    if kategorie and kategorie not in _TALENT_KATEGORIEN.values():
        # SYN-P0-006: Parameterfehler strukturiert statt leerer Liste + Leer-Hinweis.
        gueltig = ", ".join(sorted(set(_TALENT_KATEGORIEN.values())))
        return {"talente": [],
                "fehler": f"Unbekannte Talent-Kategorie {kategorie!r} - gueltig: {gueltig}.",
                "hinweis": "Ungueltiger PARAMETER - das ist KEIN 'keine Talente im "
                           "Bestand'; Aufruf mit gueltigem Wert wiederholen."}
    antwort = _liste("talent", "talente",
                     "Talente waehlt man ueber den Hintergrund (Ursprungstalent, Schritt 2) "
                     "und spaeter ueber Stufenaufstiege. " + _HINWEIS_REIHENFOLGE)
    if kategorie and antwort.get("talente"):
        gefiltert = [t for t in antwort["talente"] if t.get("kategorie") == kategorie]
        uebrig = [t for t in antwort["talente"] if t.get("kategorie") is None]
        antwort["talente"] = gefiltert
        if uebrig:
            antwort["ohne_kategorie"] = uebrig  # ehrlich: Kategorie unbekannt, nicht raten
        if not gefiltert:
            antwort["hinweis"] = (f"Keine Talente der Kategorie '{kategorie}' im Bestand. "
                                  + _ns.HINWEIS_LEER)
    return antwort


def foliant_liste_klassen() -> dict:
    """Waehlbare Klassen inkl. ihrer Unterklassen im Bestand (KNAPPE Liste; Details per
    foliant_hol_klasse). Klasse ist SCHRITT 1 der 2024-Charaktererstellung (B7).
    KERNREGELN: nur Bestand nennen (fehlende Unterklassen = fehlendes Buch, B2);
    Deutsch-first mit englischem Original in Klammern; Quelle und Regelversion nennen."""
    con = _ns._verbinde()
    if con is None:
        return {"klassen": [], "hinweis": _ns.HINWEIS_DB_FEHLT}
    try:
        alle = _eintraege(con, "klasse")
        klassen_eintraege, unterklassen_eintraege = [], []
        for e in alle:
            kontext = _kontext(e["body_md"])
            if kontext:
                if kontext == "Klassen":
                    klassen_eintraege.append(e)
                elif _UNTERKLASSE_DE.match(e["name_de"] or ""):
                    unterklassen_eintraege.append(e)
            else:
                (unterklassen_eintraege if _SUBCLASS.search(e["body_md"] or "")
                 else klassen_eintraege).append(e)

        gruppen = _gruppiere(con, klassen_eintraege)
        zeilen = [(g, _zeile(con, g, unterklassen=[])) for g in gruppen]

        # Unterklassen ihren Klassen zuordnen: srd-de ueber den Kontext ('Klassen > X'),
        # Open5e ueber '*Subclass of: X*' - beides gegen die Namensvarianten der Klasse.
        for ug in _gruppiere(con, unterklassen_eintraege):
            referenzen: set[str] = set()
            for e in ug["eintraege"]:
                kontext = _kontext(e["body_md"])
                if kontext.startswith("Klassen > "):
                    referenzen.add(_norm(kontext.split(" > ", 1)[1]))
                m = _SUBCLASS.search(e["body_md"] or "")
                if m:
                    referenzen.add(_norm(m.group(1)))
            uz = _zeile(con, ug)
            # Anzeige-/Abrufname der Unterklasse ohne das 'X-Unterklasse:'-Praefix:
            m = _UNTERKLASSE_DE.match(uz["name_de"] or "")
            if m:
                uz["name_de"] = m.group(2).strip()
                en = f" ({uz['name_en']})" if uz.get("name_en") else ""
                uz["anzeige"] = f"{uz['name_de']}{en}"
            ziel = next((z for g, z in zeilen if g["varianten"] & referenzen), None)
            if ziel is not None:
                ziel["unterklassen"].append(uz)
            else:
                zeilen.append(({"varianten": referenzen},
                               {**uz, "hinweis": "Zugehoerige Klasse nicht im Bestand."}))

        klassen = sorted((z for _g, z in zeilen), key=lambda z: _norm(z["name_de"] or z["name_en"]))
        antwort = {"klassen": klassen,
                   "hinweis_reihenfolge": "Klasse ist SCHRITT 1 von 4. " + _HINWEIS_REIHENFOLGE,
                   "hinweis": _HINWEIS_BESTAND}
        if not klassen:
            antwort["hinweis"] = _ns.HINWEIS_LEER
        return antwort
    finally:
        con.close()


def foliant_hol_spezies(name: str, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Vollstaendige Spezies-Beschreibung aus dem Bestand (Merkmale, Groesse, Bewegungsrate),
    mit Zitat (Quelle, ggf. Seite, Regelversion). Name deutsch oder englisch. Spezies ist
    Schritt 3 der 2024-Erstellung (B7). KERNREGELN: nur aus dem Bestand antworten; Quelle
    und Regelversion nennen; Deutsch-first, englisches Original in Klammern."""
    return _ns._hole_detail("spezies", name, edition, aggregiere_kinder=True, eintrag_id=eintrag_id)


def foliant_hol_hintergrund(name: str, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Vollstaendiger Hintergrund aus dem Bestand (Attributswerte, Ursprungstalent,
    Fertigkeiten, Ausruestung), mit Zitat (Quelle, ggf. Seite, Regelversion). Name deutsch
    oder englisch. Hintergrund ist Schritt 2 der 2024-Erstellung (B7). KERNREGELN: nur aus
    dem Bestand antworten; Quelle und Regelversion nennen; Deutsch-first."""
    return _ns._hole_detail("hintergrund", name, edition, eintrag_id=eintrag_id)


def foliant_hol_talent(name: str, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Vollstaendige Talent-Beschreibung (Feat) aus dem Bestand, mit Zitat (Quelle, ggf.
    Seite, Regelversion). Name deutsch oder englisch. KERNREGELN: nur aus dem Bestand
    antworten; Quelle und Regelversion nennen; Deutsch-first, Original in Klammern."""
    return _ns._hole_detail("talent", name, edition, aggregiere_kinder=True, eintrag_id=eintrag_id)


def foliant_hol_klasse(name: str, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Vollstaendige Klassen- oder Unterklassen-Beschreibung aus dem Bestand, mit Zitat
    (Quelle, ggf. Seite, Regelversion). Name deutsch oder englisch ('Kaempfer', 'Champion').
    Liefert bei Klassen zusaetzlich die verwandten Abschnitte (Klassenmerkmale, Zauberliste,
    Unterklassen) als Namen - bei Bedarf einzeln per foliant_hol_klasse nachladen (haelt die
    Antwort knapp). Klasse ist Schritt 1 der 2024-Erstellung (B7). KERNREGELN: nur aus dem
    Bestand antworten; Quelle und Regelversion nennen; Deutsch-first."""
    d = _ns._hole_detail("klasse", name, edition, eintrag_id=eintrag_id)
    if not d.get("gefunden") or not d.get("name_de"):
        return d
    con = _ns._verbinde()
    if con is None:
        return d
    try:
        verwandte = [r[0] for r in con.execute(
            "SELECT name_de FROM eintraege WHERE kategorie='klasse' AND name_de IS NOT NULL "
            "AND edition = ? AND body_md LIKE ? ORDER BY id",
            (d["edition"], f"*Kontext: Klassen > {d['name_de']}*%",))]
        if verwandte:
            d["verwandte_abschnitte"] = verwandte
            d["hinweis_abschnitte"] = ("Stufentabelle und Merkmale stehen in den verwandten "
                                       "Abschnitten (per foliant_hol_klasse abrufbar).")
        return d
    finally:
        con.close()


def foliant_hol_attributswerte(methode: Literal["standard_array",
        "point_buy"] = "standard_array") -> dict:
    """Regeln zur Attributswert-Vergabe nach 2024: 'standard_array' (Standardsatz) oder
    'point_buy' (Punktkosten). Die Werte werden am BESTAND belegt ('Schritt 3:
    Attributswerte') - fehlt die importierte Regelquelle, gibt es KEINE Werte aus
    Allgemeinwissen (B1/A5). Die Zuteilung auf Attribute macht Claude im Gespraech;
    danach foliant_pruefe_build aufrufen. KERNREGELN: nur Bestand; Deutsch-first."""
    if methode not in ("standard_array", "point_buy"):
        return {"fehler": "methode muss 'standard_array' oder 'point_buy' sein"}
    beleg, kosten_geprueft = _attributsregel_beleg(methode)
    if beleg is None:
        return {"verfuegbar": False, "methode": methode,
                "hinweis": ("Keine importierte 2024-Attributsregel im Bestand ('Schritt 3: "
                            "Attributswerte') - ich gebe keine Werte aus Allgemeinwissen "
                            "aus (B1/A5). Erst die Regelquelle importieren.")}
    if methode == "standard_array":
        return {"methode": "standard_array", "werte": STANDARD_ARRAY, "beleg": beleg}
    if kosten_geprueft is False:
        # SYN-P2-003: der Bestand widerspricht den Konstanten -> NIE die Konstanten
        # mit Beleg ausgeben (der Bestand ist die einzige Wahrheit, B1/A5).
        return {"verfuegbar": False, "methode": "point_buy",
                "hinweis": ("Die Punktkosten-Tabelle im Bestand weicht von den "
                            "erwarteten 2024-Kosten ab - keine Werte ausgeben, "
                            "Bestand/Import pruefen (Beleg: " + beleg + ").")}
    antwort = {"methode": "point_buy", "budget": POINT_BUY_BUDGET,
               "kosten": POINT_BUY_KOSTEN,
               "bereich": [min(POINT_BUY_KOSTEN), max(POINT_BUY_KOSTEN)], "beleg": beleg}
    antwort["beleg_umfang"] = (
        "Budget UND Kostentabelle am Bestand verifiziert" if kosten_geprueft
        else "Budget am Bestand belegt; Kostentabelle nicht maschinell lesbar - "
             "Kostenwerte stammen aus der verifizierten Konstante (SYN-P2-003, "
             "offen deklariert statt als Vollbeleg ausgegeben)")
    return antwort


# ---------------------------------------------------------------------------
# Build-Pruefung (F3/T9): streng, transparent, ehrlich ueber Luecken (Q4).

_GRENZEN = [
    "Geprueft wird NUR gegen den importierten 2024-Bestand; Optionen ausserhalb des "
    "Bestands (oder nur in aelteren Regelversionen) kann ich nicht beurteilen (B2/A4) - "
    "dort steht 'nicht_pruefbar'.",
    "NICHT geprueft: Zauberauswahl und -listen, Fertigkeiten- und Ausruestungswahl, "
    "Talent-ERWERBSQUELLE (Hintergrund vs. Stufenaufstieg), Mehrklassen (Multiclassing), "
    "Reihenfolge der Stufenaufstiege, Hausregeln.",
    "Talent-Voraussetzungen: der Stufen-Teil ('min. 19. Stufe') wird gegen die "
    "Build-Stufe geprueft; Attributs-/Merkmalsvoraussetzungen bleiben 'nicht_pruefbar'.",
    "Bei Waffenbeherrschungen pruefe ich Anzahl, Duplikate und ob der Name als "
    "Gegenstand im Bestand existiert - NICHT, ob die Waffe eine "
    "Meisterschaftseigenschaft besitzt.",
    "Ausgewuerfelte Attributswerte (Zufallserstellung 4W6) kann ich nicht validieren - "
    "nur Standardsatz und Punktkosten.",
    "Diese Pruefung ist eine Hilfe, keine letzte Instanz - der Spielleiter entscheidet.",
]


def _befund(pruefungen: list, pruefung: str, status: str, detail: str,
            beleg: str | None = None) -> None:
    b = {"pruefung": pruefung, "status": status, "detail": detail}
    if beleg:
        b["beleg"] = beleg
    pruefungen.append(b)


def _finde(kategorie: str, name: str) -> dict:
    """Detail-Abruf fuer die Pruefung - STRIKT 2024 (A4): der B5-Nachschlage-Fallback
    auf einen Altstand gilt hier nicht. Liegt ein Inhalt nur in einer aelteren Edition
    vor, kommt {'gefunden': False, 'nur_altstand': <edition>} zurueck - der Befund wird
    'nicht_pruefbar', niemals 'ok'."""
    d = _ns._hole_detail(kategorie, name)
    if d.get("gefunden") and d.get("edition") != _EDITION:
        return {"gefunden": False, "nur_altstand": d["edition"],
                "zitat_altstand": d.get("zitat")}
    return d


def _entsprechungen(*namen: str | None) -> set[str]:
    """Normalisierte Namen plus deren EXAKTE Glossar-Entsprechungen (A4: eine deutsch
    gewaehlte Klasse muss eine nur englisch vorhandene Unterklasse matchen)."""
    menge = {_glossar.norm_begriff(n) for n in namen if n} - {""}
    con = _ns._verbinde()
    if con is None:
        return menge
    try:
        for n in list(menge):
            menge |= _glossar.exakte_entsprechungen(con, n)
        return menge
    finally:
        con.close()


def _normalisiere_attribute(werte: dict) -> tuple[dict[str, int], list[str]]:
    """Attributs-Keys tolerant auf die sechs deutschen Namen abbilden - die WERTE aber
    strikt (A5): nur echte Integer; Strings/Floats/Booleans werden nicht still
    konvertiert, doppelte Aliasse ('str' + 'stärke') sind ein Konflikt."""
    sauber: dict[str, int] = {}
    probleme: list[str] = []
    for k, v in (werte or {}).items():
        schluessel = _ATTR_ALIAS.get(_norm(k), _norm(k))
        if schluessel not in _ATTRIBUTE:
            probleme.append(f"unbekanntes Attribut {k!r} - erwartet: {', '.join(_ATTRIBUTE)}")
            continue
        if isinstance(v, bool) or not isinstance(v, int):
            probleme.append(f"{k}={v!r} ist keine ganze Zahl - ich konvertiere nicht still")
            continue
        if schluessel in sauber:
            probleme.append(f"Attribut '{schluessel}' ist doppelt angegeben "
                            f"(Alias-Konflikt, z. B. 'str' UND 'stärke')")
            continue
        sauber[schluessel] = v
    return sauber, probleme


def _regel_beleg(kategorie: str, name: str, anker: list[str]) -> str | None:
    """A5: Regelwerte duerfen nur als belegt gelten, wenn der 2024-Bestand den passenden
    Eintrag ENTHAELT - gesucht wird der Eintrag, und die Anker-Textstellen verifizieren,
    dass er wirklich die erwartete Regel traegt. Rueckgabe: das echte DB-Zitat oder None
    (dann: nicht_pruefbar, kein Allgemeinwissen)."""
    d = _ns._hole_detail(kategorie, name)
    if not d.get("gefunden") or d.get("edition") != _EDITION:
        return None
    text = d.get("regeltext_md") or ""
    if any(a not in text for a in anker):
        return None
    return d["zitat"]


# Wert/Kosten-Paare aus der Punktkosten-Tabelle des Belegs ('|8|0|12|4|' - die
# srd-de-Tabelle ist zweispaltig gefaltet, daher paarweise ueber die ganze Zeile).
_PUNKTKOSTEN_ZEILE = re.compile(r"^\|(\d{1,2})\|(\d{1,2})(?:\|(\d{1,2})\|(\d{1,2}))?\|",
                                re.MULTILINE)


def _punktkosten_aus_text(text: str) -> dict[int, int]:
    kosten: dict[int, int] = {}
    for m in _PUNKTKOSTEN_ZEILE.finditer(text or ""):
        kosten[int(m.group(1))] = int(m.group(2))
        if m.group(3):
            kosten[int(m.group(3))] = int(m.group(4))
    return kosten


def _attributsregel_beleg(methode: str) -> tuple[str | None, bool | None]:
    """A5 + SYN-P2-003 (codex TECH-010): (beleg, kosten_geprueft). Der alte Anker-Check
    ('27 Punkte' kommt im Text vor) liess die komplette hartcodierte Kostentabelle als
    'belegt' erscheinen. Jetzt wird die Tabelle aus dem Belegtext GEPARST und gegen die
    Konstanten verifiziert: True = tabellarisch belegt, None = Tabelle nicht maschinell
    lesbar (Budget-Anker belegt, Kosten aus Konstante - offen deklarieren), False =
    Bestand widerspricht den Konstanten (dann gewinnt IMMER der Bestand: nichts ausgeben)."""
    anker = ["15, 14, 13, 12, 10, 8"] if methode == "standard_array" else ["27 Punkte"]
    d = _ns._hole_detail("regel", "Schritt 3: Attributswerte")
    if not d.get("gefunden") or d.get("edition") != _EDITION:
        return None, None
    text = d.get("regeltext_md") or ""
    if any(a not in text for a in anker):
        return None, None
    if methode == "standard_array":
        return d["zitat"], True                       # Anker IST die vollstaendige Regel
    geparst = _punktkosten_aus_text(text)
    if len(geparst) >= len(POINT_BUY_KOSTEN):
        return d["zitat"], geparst == POINT_BUY_KOSTEN
    return d["zitat"], None


def _hg_verteilungsregel_beleg() -> str | None:
    return _regel_beleg("hintergrund", "Attributswerte",
                        ["um 2", "alle drei um 1", "mehr als 20"])


def _stufentabelle(body: str) -> dict[int, dict[str, str]]:
    """Parst die Klassen-Stufentabelle ('Kaempfermerkmale') aus einem Bestandseintrag:
    {stufe: {spaltenname_normalisiert: zellwert}}. Leeres dict, wenn keine Tabelle mit
    'Stufe'-Kopf gefunden wird (dann: nicht_pruefbar, Q4)."""
    zeilen = (body or "").splitlines()
    for i, z in enumerate(zeilen):
        if not z.strip().startswith("|"):
            continue
        koepfe = [re.sub(r"\*+|<br>|­|-", "", teil).strip().lower()
                  for teil in z.strip().strip("|").split("|")]
        if "stufe" not in koepfe:
            continue
        tabelle: dict[int, dict[str, str]] = {}
        for zeile in zeilen[i + 1:]:
            if not zeile.strip().startswith("|"):
                break
            zellen = [teil.strip() for teil in zeile.strip().strip("|").split("|")]
            if not zellen or set(zellen[0]) <= {"-", ":", " "}:
                continue
            try:
                stufe = int(zellen[0])
            except ValueError:
                continue
            tabelle[stufe] = dict(zip(koepfe, zellen))
        if tabelle:
            return tabelle
    return {}


def _klassenmerkmale_body(name_de: str) -> str | None:
    """Body des 'Klassenmerkmale des X'-Eintrags zur Klasse (srd-de), ohne Genitiv-Raterei
    ueber den Kontext 'Klassen > <Klasse>' aufgeloest. NUR 2024 und in Quellen-Praezedenz
    (A4: die Tabelle muss zum kanonischen 2024-Inhalt gehoeren, nie zu einem Altstand)."""
    con = _ns._verbinde()
    if con is None:
        return None
    try:
        r = con.execute(
            "SELECT e.body_md FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
            "WHERE e.kategorie='klasse' AND e.edition=? "
            "AND e.name_de LIKE 'Klassenmerkmale%' AND e.body_md LIKE ? "
            "ORDER BY q.prioritaet LIMIT 1",
            (_EDITION, f"*Kontext: Klassen > {name_de}*%")).fetchone()
        return r[0] if r else None
    finally:
        con.close()


def foliant_pruefe_build(klasse: str, stufe: int = 1, unterklasse: str | None = None,
                         hintergrund: str | None = None, spezies: str | None = None,
                         attributswerte: dict | None = None,
                         attributsmethode: Literal["standard_array", "point_buy"] | None = None,
                         hintergrund_erhoehungen: dict | None = None,
                         talente: list[str] | None = None,
                         waffenmeisterschaften: list[str] | None = None) -> dict:
    """Automatische Build-Pruefung (F3) STRIKT gegen den 2024-Bestand (Q4/A4): prueft
    Existenz aller Optionen (nur 2024 - ein reiner 2014-Inhalt ist 'nicht_pruefbar',
    nie 'ok'), Unterklassen-Stufe, -Zugehoerigkeit UND -Pflicht (fehlt die Unterklasse
    ab der Tabellen-Stufe, ist der Build unvollstaendig), Attributswerte
    (attributsmethode 'standard_array'/'point_buy', am Bestand belegt),
    Hintergrund-Erhoehungen (PFLICHTWAHL: Verteilung +2/+1 bzw. +1/+1/+1 und - nur mit
    Basiswerten - Obergrenze 20), Talent-Stufenvoraussetzungen und Waffenbeherrschungen
    (Anzahl laut Klassentabelle, Duplikate, Existenz im Bestand). attributswerte/
    hintergrund_erhoehungen: {"stärke": 15, ...} - Werte muessen ganze Zahlen sein.
    Ergebnis: 'verstoesse_gefunden' | 'unvollstaendig' (fehlende_angaben sagt was fehlt)
    | 'keine_verstoesse_gefunden' (Angaben vollstaendig, aber offene Punkte in
    nicht_pruefbar - KEIN Legalitaetsnachweis!) | 'legal_soweit_pruefbar' (nur wenn
    nichts fehlt UND nichts offen ist). KERNREGELN: nichts aus Allgemeinwissen
    ergaenzen; Quelle und Regelversion nennen; Deutsch-first."""
    pruefungen: list[dict] = []
    datenbasis: set[str] = set()
    fehlende_angaben: list[str] = []

    # --- Stufe -------------------------------------------------------------
    if not isinstance(stufe, bool) and isinstance(stufe, int) and 1 <= stufe <= 20:
        _befund(pruefungen, "stufe", "ok", f"Stufe {stufe} liegt im Bereich 1-20.")
    else:
        _befund(pruefungen, "stufe", "verstoss",
                f"Stufe {stufe!r} liegt ausserhalb 1-20 (Klassentabellen fuehren die "
                f"Stufen 1-20).")

    # --- Klasse (Pflichtangabe; A5: leer/unbekannt ergibt nie ein Legalitaetspraedikat) --
    klasse_detail: dict = {}
    klassentabelle: dict[int, dict[str, str]] = {}
    if not isinstance(klasse, str) or not klasse.strip():
        fehlende_angaben.append("klasse (keine Angabe)")
        _befund(pruefungen, "klasse", "nicht_pruefbar",
                "Kein Klassenname angegeben - ohne Klasse ist kein Build pruefbar.")
    else:
        klasse_detail = _finde("klasse", klasse)
        if klasse_detail.get("gefunden"):
            datenbasis.add(klasse_detail["zitat"])
            _befund(pruefungen, "klasse", "ok",
                    f"Klasse {klasse_detail['anzeige_name']} ist im 2024-Bestand.",
                    klasse_detail["zitat"])
            merkmale = (_klassenmerkmale_body(klasse_detail.get("name_de") or "")
                        or klasse_detail.get("regeltext_md") or "")
            klassentabelle = _stufentabelle(merkmale)
        elif klasse_detail.get("nur_altstand"):
            fehlende_angaben.append(f"klasse (nur als {klasse_detail['nur_altstand']} "
                                    f"im Bestand)")
            _befund(pruefungen, "klasse", "nicht_pruefbar",
                    f"'{klasse}' liegt nur als Regelversion "
                    f"{klasse_detail['nur_altstand']} vor - fuer einen 2024-Build nicht "
                    f"pruefbar und nicht verfuegbar (A4/V5).",
                    klasse_detail.get("zitat_altstand"))
            klasse_detail = {}
        else:
            fehlende_angaben.append("klasse (nicht im 2024-Bestand)")
            _befund(pruefungen, "klasse", "nicht_pruefbar",
                    f"Klasse '{klasse}' ist nicht im 2024-Bestand - evtl. fehlt ein "
                    f"Buch (B2). Alle klassenabhaengigen Pruefungen entfallen.")
            klasse_detail = {}

    # --- Unterklasse ---------------------------------------------------------
    # Ab welcher Stufe die Klassentabelle die Unterklasse fuehrt - VOR der if-Weiche,
    # denn auch eine FEHLENDE Unterklasse ist ab dieser Stufe eine offene Pflichtwahl
    # (SYN-P0-005: 'Kämpfer Stufe 3 ohne Unterklasse' galt als legal_soweit_pruefbar).
    u_stufe = next((s for s in sorted(klassentabelle)
                    if "unterklasse" in _norm(" ".join(klassentabelle[s].values()))),
                   None)
    if not unterklasse and u_stufe is not None \
            and isinstance(stufe, int) and not isinstance(stufe, bool) \
            and stufe >= u_stufe:
        fehlende_angaben.append(f"unterklasse (laut Klassentabelle ab Stufe {u_stufe})")
        _befund(pruefungen, "unterklasse", "nicht_pruefbar",
                f"Ab Stufe {u_stufe} gehoert laut Klassentabelle eine Unterklasse zum "
                f"Build - es ist keine angegeben (Pflichtwahl).",
                klasse_detail.get("zitat"))
    if unterklasse:
        u_detail = _finde("klasse", unterklasse)
        u_name = (u_detail.get("name_de") or u_detail.get("name_en") or unterklasse
                  if u_detail.get("gefunden") else unterklasse)
        if not u_detail.get("gefunden"):
            if u_detail.get("nur_altstand"):
                _befund(pruefungen, "unterklasse", "nicht_pruefbar",
                        f"'{unterklasse}' liegt nur als Regelversion "
                        f"{u_detail['nur_altstand']} vor - fuer einen 2024-Build nicht "
                        f"pruefbar (A4/V5).", u_detail.get("zitat_altstand"))
            else:
                _befund(pruefungen, "unterklasse", "nicht_pruefbar",
                        f"Unterklasse '{unterklasse}' ist nicht im 2024-Bestand (B2).")
        else:
            datenbasis.add(u_detail["zitat"])
            # Zugehoerigkeit: srd-de-Name '<Klasse>...-Unterklasse: <Name>' bzw.
            # Open5e-Signal '*Subclass of: <Klasse>*' gegen die gewaehlte Klasse -
            # inkl. EXAKTER Glossar-Entsprechungen (A4: 'Subclass of: Fighter' muss
            # zur deutsch gewaehlten Klasse 'Kämpfer' passen).
            text = f"{u_detail.get('name_de') or ''}\n{u_detail.get('regeltext_md') or ''}"
            m_sub = _SUBCLASS.search(text)
            m_de = _UNTERKLASSE_DE.match(u_detail.get("name_de") or "")
            klassen_namen = _entsprechungen(klasse, klasse_detail.get("name_de"),
                                            klasse_detail.get("name_en"))
            gehoert_dazu = None
            if m_sub:
                gehoert_dazu = _glossar.norm_begriff(m_sub.group(1)) in klassen_namen
            elif m_de:
                # Genitiv-Praefix ('Barbaren-' zu 'Barbar') -> Praefix-Vergleich.
                praefix = _glossar.norm_begriff(m_de.group(1))
                gehoert_dazu = any(praefix.startswith(k[:4]) for k in klassen_namen if k)
            if gehoert_dazu is False:
                _befund(pruefungen, "unterklasse", "verstoss",
                        f"{u_name} gehoert laut Bestand nicht zur Klasse {klasse}.",
                        u_detail["zitat"])
            elif gehoert_dazu is None:
                _befund(pruefungen, "unterklasse", "nicht_pruefbar",
                        f"Zugehoerigkeit von {u_name} zu {klasse} ist im Bestand nicht "
                        f"maschinell erkennbar.")
            else:
                _befund(pruefungen, "unterklasse", "ok",
                        f"{u_name} gehoert zur Klasse {klasse}.", u_detail["zitat"])
        # Unterklassen-Stufe aus der Klassentabelle (oben ermittelt):
        if u_stufe is None:
            _befund(pruefungen, "unterklasse_stufe", "nicht_pruefbar",
                    "Keine Klassen-Stufentabelle im Bestand parsebar - ab welcher Stufe "
                    "die Unterklasse kommt, kann ich nicht pruefen.")
        elif isinstance(stufe, int) and stufe < u_stufe:
            _befund(pruefungen, "unterklasse_stufe", "verstoss",
                    f"Unterklassen gibt es laut Klassentabelle erst ab Stufe {u_stufe}; "
                    f"der Build ist Stufe {stufe}.",
                    klasse_detail.get("zitat"))
        else:
            _befund(pruefungen, "unterklasse_stufe", "ok",
                    f"Unterklasse ab Stufe {u_stufe} - passt zu Stufe {stufe}.",
                    klasse_detail.get("zitat"))

    # --- Spezies (Pflichtangabe fuer einen vollstaendigen Charakter) -----------
    if spezies:
        s_detail = _finde("spezies", spezies)
        if s_detail.get("gefunden"):
            datenbasis.add(s_detail["zitat"])
            _befund(pruefungen, "spezies", "ok",
                    f"Spezies {s_detail['anzeige_name']} ist im 2024-Bestand.",
                    s_detail["zitat"])
        elif s_detail.get("nur_altstand"):
            _befund(pruefungen, "spezies", "nicht_pruefbar",
                    f"'{spezies}' liegt nur als Regelversion {s_detail['nur_altstand']} "
                    f"vor - fuer einen 2024-Build nicht pruefbar (A4/V5).",
                    s_detail.get("zitat_altstand"))
        else:
            _befund(pruefungen, "spezies", "nicht_pruefbar",
                    f"Spezies '{spezies}' ist nicht im 2024-Bestand - evtl. fehlt ein "
                    f"Buch (B2).")
    else:
        fehlende_angaben.append("spezies")

    # --- Attributswerte --------------------------------------------------------
    werte, eingabe_probleme = _normalisiere_attribute(attributswerte or {})
    if not attributswerte:
        fehlende_angaben.append("attributswerte")
    elif eingabe_probleme:
        # A5: ungueltige Eingaben strukturiert benennen - nie still konvertieren.
        _befund(pruefungen, "attributswerte", "nicht_pruefbar",
                "Ungueltige Attributsangaben: " + "; ".join(eingabe_probleme) + ".")
    elif len(werte) < 6:
        fehlt = sorted(set(_ATTRIBUTE) - set(werte))
        fehlende_angaben.append(f"attributswerte ({', '.join(fehlt)})")
        _befund(pruefungen, "attributswerte", "nicht_pruefbar",
                f"Nur {len(werte)} von 6 Attributen angegeben; es fehlen: "
                f"{', '.join(fehlt)}.")
    elif attributsmethode not in ("standard_array", "point_buy"):
        fehlende_angaben.append("attributsmethode (standard_array/point_buy)")
        _befund(pruefungen, "attributswerte", "nicht_pruefbar",
                "Ohne attributsmethode ('standard_array'/'point_buy') pruefe ich die "
                "Werte nicht; ausgewuerfelte Werte (4W6) kann ich nie validieren.")
    else:
        beleg_attr, kosten_geprueft = _attributsregel_beleg(attributsmethode)
        if beleg_attr is not None and kosten_geprueft is False:
            beleg_attr = None                # Bestand widerspricht -> nicht pruefen (A5)
        if beleg_attr is None:
            _befund(pruefungen, "attributswerte", "nicht_pruefbar",
                    "Die 2024-Attributsregel ('Schritt 3: Attributswerte') ist nicht im "
                    "Bestand belegt - ich pruefe nicht gegen Allgemeinwissen (B1/A5).")
        elif attributsmethode == "standard_array":
            datenbasis.add(beleg_attr)
            if sorted(werte.values(), reverse=True) == sorted(STANDARD_ARRAY, reverse=True):
                _befund(pruefungen, "attributswerte", "ok",
                        "Werte entsprechen exakt dem Standardsatz 15/14/13/12/10/8.",
                        beleg_attr)
            else:
                _befund(pruefungen, "attributswerte", "verstoss",
                        f"Standardsatz ist 15/14/13/12/10/8; angegeben: "
                        f"{sorted(werte.values(), reverse=True)}.", beleg_attr)
        else:
            datenbasis.add(beleg_attr)
            ausserhalb = {k: v for k, v in werte.items()
                          if not min(POINT_BUY_KOSTEN) <= v <= max(POINT_BUY_KOSTEN)}
            if ausserhalb:
                _befund(pruefungen, "attributswerte", "verstoss",
                        f"Punktkosten erlauben nur Werte {min(POINT_BUY_KOSTEN)}-"
                        f"{max(POINT_BUY_KOSTEN)}; ausserhalb: {ausserhalb}.", beleg_attr)
            else:
                kosten = sum(POINT_BUY_KOSTEN[v] for v in werte.values())
                if kosten > POINT_BUY_BUDGET:
                    _befund(pruefungen, "attributswerte", "verstoss",
                            f"Punktkosten {kosten} ueberschreiten das Budget von "
                            f"{POINT_BUY_BUDGET}.", beleg_attr)
                else:
                    _befund(pruefungen, "attributswerte", "ok",
                            f"Punktkosten {kosten}/{POINT_BUY_BUDGET}, alle Werte im "
                            f"erlaubten Bereich.", beleg_attr)

    # --- Hintergrund + Erhoehungen (Pflichtangabe fuer vollstaendigen Charakter) --
    if hintergrund:
        h_detail = _finde("hintergrund", hintergrund)
        if not h_detail.get("gefunden"):
            if h_detail.get("nur_altstand"):
                _befund(pruefungen, "hintergrund", "nicht_pruefbar",
                        f"'{hintergrund}' liegt nur als Regelversion "
                        f"{h_detail['nur_altstand']} vor - fuer einen 2024-Build nicht "
                        f"pruefbar (A4/V5).", h_detail.get("zitat_altstand"))
            else:
                _befund(pruefungen, "hintergrund", "nicht_pruefbar",
                        f"Hintergrund '{hintergrund}' ist nicht im 2024-Bestand (B2).")
        else:
            datenbasis.add(h_detail["zitat"])
            _befund(pruefungen, "hintergrund", "ok",
                    f"Hintergrund {h_detail['anzeige_name']} ist im 2024-Bestand.",
                    h_detail["zitat"])
            body = h_detail.get("regeltext_md") or ""
            m_attr = _HG_ATTRIBUTE.search(body)
            m_talent = _HG_TALENT.search(body)
            if m_talent:
                _befund(pruefungen, "ursprungstalent", "ok",
                        f"Der Hintergrund liefert das Ursprungstalent "
                        f"'{m_talent.group(1).strip()}' (fest vorgegeben).",
                        h_detail["zitat"])
            hg_attribute = ([_norm(a) for a in m_attr.group(1).replace(" und ", ", ")
                            .split(",")] if m_attr else [])
            hg_attribute = [a for a in (x.strip() for x in hg_attribute) if a]
            if not hintergrund_erhoehungen:
                # SYN-P0-005: Die Erhoehungen sind eine PFLICHTWAHL des 2024-Hintergrunds
                # - ohne Angabe gab es frueher weder Befund noch fehlende_angaben, der
                # Build galt als 'legal_soweit_pruefbar'.
                fehlende_angaben.append(
                    "hintergrund_erhoehungen (+2/+1 oder +1/+1/+1 auf die "
                    "Hintergrund-Attribute)")
                _befund(pruefungen, "hintergrund_erhoehungen", "nicht_pruefbar",
                        "Keine Attributserhoehungen angegeben - der 2024-Hintergrund "
                        "verlangt eine Verteilung (+2/+1 oder +1/+1/+1); ohne Angabe "
                        "kein Legalitaetsnachweis.", h_detail["zitat"])
            if hintergrund_erhoehungen:
                erh, erh_probleme = _normalisiere_attribute(hintergrund_erhoehungen)
                beleg_erh = _hg_verteilungsregel_beleg()   # echter DB-Beleg oder None (A5)
                if erh_probleme:
                    _befund(pruefungen, "hintergrund_erhoehungen", "nicht_pruefbar",
                            "Ungueltige Erhoehungsangaben: " + "; ".join(erh_probleme) + ".")
                elif not hg_attribute:
                    _befund(pruefungen, "hintergrund_erhoehungen", "nicht_pruefbar",
                            "Die drei Hintergrund-Attribute sind aus dem Bestandseintrag "
                            "nicht maschinell lesbar - Verteilung bitte manuell pruefen.")
                else:
                    falsch = [a for a in erh if a not in hg_attribute]
                    verteilung = sorted(erh.values(), reverse=True)
                    if falsch:
                        _befund(pruefungen, "hintergrund_erhoehungen", "verstoss",
                                f"Erhoehung nur auf die drei Hintergrund-Attribute "
                                f"({', '.join(hg_attribute)}) erlaubt; nicht erlaubt: "
                                f"{', '.join(falsch)}.", h_detail["zitat"])
                    elif beleg_erh is None:
                        _befund(pruefungen, "hintergrund_erhoehungen", "nicht_pruefbar",
                                "Die 2024-Verteilungsregel (+2/+1 bzw. +1/+1/+1) ist "
                                "nicht im Bestand belegt - ich pruefe nicht gegen "
                                "Allgemeinwissen (B1/A5).")
                    elif verteilung not in ([2, 1], [1, 1, 1]):
                        datenbasis.add(beleg_erh)
                        _befund(pruefungen, "hintergrund_erhoehungen", "verstoss",
                                f"Erlaubt ist +2/+1 oder +1/+1/+1; angegeben: "
                                f"{verteilung}.", beleg_erh)
                    else:
                        datenbasis.add(beleg_erh)
                        _befund(pruefungen, "hintergrund_erhoehungen", "ok",
                                f"Verteilung {verteilung} auf Hintergrund-Attribute "
                                f"({', '.join(hg_attribute)}).", beleg_erh)
                        # Obergrenze 20 als GETRENNTE Teilpruefung (A5): nur bestaetigen,
                        # wenn fuer ALLE erhoehten Attribute Basiswerte vorliegen.
                        ohne_basis = sorted(a for a in erh if a not in werte)
                        if ohne_basis:
                            _befund(pruefungen, "hintergrund_erhoehungen_obergrenze",
                                    "nicht_pruefbar",
                                    f"Kein Basiswert fuer {', '.join(ohne_basis)} "
                                    f"angegeben - die Obergrenze 20 kann ich nicht "
                                    f"bestaetigen (nur die Verteilung war pruefbar).")
                        else:
                            zu_hoch = {a: werte[a] + erh[a] for a in erh
                                       if werte[a] + erh[a] > 20}
                            if zu_hoch:
                                _befund(pruefungen, "hintergrund_erhoehungen_obergrenze",
                                        "verstoss",
                                        f"Keine Erhoehung darf ueber 20 fuehren; zu "
                                        f"hoch: {zu_hoch}.", beleg_erh)
                            else:
                                _befund(pruefungen, "hintergrund_erhoehungen_obergrenze",
                                        "ok", "Obergrenze 20 gewahrt.", beleg_erh)
    else:
        fehlende_angaben.append("hintergrund")
        if hintergrund_erhoehungen:
            _befund(pruefungen, "hintergrund_erhoehungen", "nicht_pruefbar",
                    "Erhoehungen angegeben, aber kein Hintergrund - gegen was soll ich "
                    "pruefen?")

    # --- Talente ---------------------------------------------------------------
    # SYN-P0-005: blosse Existenz war frueher 'ok' - eine epische Gabe auf Stufe 1 galt
    # damit als legal. Jetzt wird die Typzeilen-Voraussetzung geprueft: der Stufen-Teil
    # ('min. 19. Stufe') maschinell, alles Uebrige bleibt ehrlich 'nicht_pruefbar'.
    for talent in talente or []:
        t_detail = _finde("talent", talent)
        if not t_detail.get("gefunden"):
            _befund(pruefungen, f"talent:{talent}", "nicht_pruefbar",
                    f"Talent '{talent}' ist nicht im Bestand (B2).")
            continue
        datenbasis.add(t_detail["zitat"])
        m_typ = _TALENT_TYPZEILE.search(t_detail.get("regeltext_md") or "")
        voraussetzung = (m_typ.group(2) or "").strip() if m_typ else ""
        m_stufe = re.search(r"(\d+)\.\s*Stufe", voraussetzung)
        if m_typ and not voraussetzung:
            _befund(pruefungen, f"talent:{talent}", "ok",
                    f"Talent {t_detail['anzeige_name']} ist im 2024-Bestand; die "
                    f"Typzeile nennt keine Voraussetzung. Erwerbsquelle (Hintergrund/"
                    f"Stufenaufstieg) pruefe ich nicht.", t_detail["zitat"])
        elif m_stufe and isinstance(stufe, int) and not isinstance(stufe, bool) \
                and stufe < int(m_stufe.group(1)):
            _befund(pruefungen, f"talent:{talent}", "verstoss",
                    f"Voraussetzung laut Bestand: '{voraussetzung}' - der Build ist "
                    f"Stufe {stufe}.", t_detail["zitat"])
        elif voraussetzung:
            geprueft = (f"Stufen-Teil erfuellt (Stufe {stufe}); " if m_stufe else "")
            _befund(pruefungen, f"talent:{talent}", "nicht_pruefbar",
                    f"Talent {t_detail['anzeige_name']} hat die Voraussetzung "
                    f"'{voraussetzung}'. {geprueft}die uebrigen Teile kann ich nicht "
                    f"maschinell pruefen - am Eintrag pruefen.", t_detail["zitat"])
        else:
            _befund(pruefungen, f"talent:{talent}", "nicht_pruefbar",
                    f"Talent {t_detail['anzeige_name']} ist im Bestand, traegt aber "
                    f"keine maschinell lesbare Typzeile - Voraussetzungen am Eintrag "
                    f"pruefen.", t_detail["zitat"])

    # --- Waffenbeherrschung (Weapon Mastery) -----------------------------------
    if waffenmeisterschaften:
        normiert = [_glossar.norm_begriff(w) for w in waffenmeisterschaften]
        doppelte = sorted({w for w in normiert if normiert.count(w) > 1})
        if doppelte:
            # A5: Duplikate zaehlen nicht als mehrere gueltige Auswahlen.
            _befund(pruefungen, "waffenbeherrschung", "verstoss",
                    f"Waffenbeherrschung doppelt gewaehlt: {', '.join(doppelte)} - "
                    f"jede Auswahl muss eine andere Waffe sein.")
        elif (unbekannte := [w for w in dict.fromkeys(waffenmeisterschaften)
                             if not _finde("gegenstand", w).get("gefunden")]):
            # SYN-P0-005: Fantasienamen ('Kartoffel') zaehlten frueher als gueltige
            # Auswahl. Existenz wird jetzt am Bestand geprueft; ob die Waffe eine
            # Meisterschaftseigenschaft HAT, bleibt bewusst ungeprueft (grenzen).
            _befund(pruefungen, "waffenbeherrschung", "nicht_pruefbar",
                    f"Nicht als Gegenstand im 2024-Bestand: {', '.join(unbekannte)} - "
                    f"ob das Waffen (mit Meisterschaftseigenschaft) sind, kann ich "
                    f"nicht beurteilen; evtl. fehlt ein Buch (B2).")
        else:
            eindeutig = len(set(normiert))
            spalte = next((k for s in klassentabelle.values() for k in s
                           if "waffenbeherrschung" in k), None)
            if not klassentabelle or spalte is None:
                _befund(pruefungen, "waffenbeherrschung", "nicht_pruefbar",
                        "Keine Waffenbeherrschungs-Spalte in der 2024-Klassentabelle des "
                        "Bestands - entweder hat die Klasse keine Waffenbeherrschung oder "
                        "die Tabelle ist nicht parsebar. Quellen ausserhalb der Klasse "
                        "(z. B. Talente) pruefe ich nicht.")
            else:
                zeile = klassentabelle.get(stufe if isinstance(stufe, int) else 1, {})
                try:
                    erlaubt = int(zeile.get(spalte, ""))
                except ValueError:
                    erlaubt = None
                if erlaubt is None:
                    _befund(pruefungen, "waffenbeherrschung", "nicht_pruefbar",
                            f"Tabellenwert fuer Stufe {stufe} nicht lesbar.")
                elif eindeutig > erlaubt:
                    _befund(pruefungen, "waffenbeherrschung", "verstoss",
                            f"Auf Stufe {stufe} erlaubt die Klassentabelle {erlaubt} "
                            f"Waffenbeherrschungen; angegeben: {eindeutig}.",
                            klasse_detail.get("zitat"))
                else:
                    _befund(pruefungen, "waffenbeherrschung", "ok",
                            f"{eindeutig} von {erlaubt} moeglichen Waffenbeherrschungen "
                            f"auf Stufe {stufe}.", klasse_detail.get("zitat"))

    # --- Gesamtergebnis (A5/SYN-P0-005): Verstoesse > unvollstaendig >
    # keine_verstoesse_gefunden (offene Punkte!) > legal_soweit_pruefbar.
    # 'unvollstaendig' und 'keine_verstoesse_gefunden' sind AUSDRUECKLICH keine
    # Legalitaetsnachweise: das positive Label gibt es nur noch, wenn ALLE Angaben da
    # sind UND nichts offen blieb - vorher kaschierte es ungepruefte Bereiche.
    verstoesse = [p for p in pruefungen if p["status"] == "verstoss"]
    offen = [p for p in pruefungen if p["status"] == "nicht_pruefbar"]
    if verstoesse:
        ergebnis = "verstoesse_gefunden"
    elif fehlende_angaben:
        ergebnis = "unvollstaendig"
    elif offen:
        ergebnis = "keine_verstoesse_gefunden"
    else:
        ergebnis = "legal_soweit_pruefbar"
    return {
        "ergebnis": ergebnis,
        "pruefungen": pruefungen,
        "fehlende_angaben": fehlende_angaben,
        "nicht_pruefbar": [p["pruefung"] for p in offen],
        "grenzen": _GRENZEN,
        "datenbasis": sorted(datenbasis) or ["(keine Bestandseintraege herangezogen)"],
        # Alle Belege sind oben 2024-verifiziert (A4) - die Angabe behauptet nichts,
        # was den verwendeten Quellen widerspricht.
        "edition": _EDITION,
        "hinweis": ("Befunde ehrlich wiedergeben: Verstoesse mit Beleg nennen; "
                    "'unvollstaendig' und 'keine_verstoesse_gefunden' NICHT als 'legal' "
                    "verkaufen - offene Punkte stehen in nicht_pruefbar (Q4/A5). "
                    "Kein Speichern: Charakterbogen fuehrt der Spieler anderswo (B8)."),
    }
