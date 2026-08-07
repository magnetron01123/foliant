"""Charaktererstellungs-Werkzeuge (F3/B7). Namensschema foliant_<verb>_<nomen> (BP #2).

Listen = KNAPPE Kataloge der waehlbaren Optionen (BP #1); Details laufen ueber die
_hole_detail-Maschine von nachschlagen. Die Build-Pruefung (Q4) validiert NUR gegen den
2024-Bestand, nennt ihre Datenbasis und weist offen aus, was sie nicht pruefen kann -
sie ist Hilfe, keine letzte Instanz.

Options-Erkennung je Quelle (Justage-Stelle fuer neue Quellen):
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
import sqlite3
from typing import Literal

from app import db as _db
from app import glossar as _glossar
from app.tools import ausgabe as _aus
from app.tools import nachschlagen as _ns

STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]
POINT_BUY_KOSTEN = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
POINT_BUY_BUDGET = 27

_SUBCLASS = re.compile(r"^\*Subclass of:\s*(.+?)\*", re.MULTILINE)
_UNTERKLASSE_DE = _glossar.UNTERKLASSE_SCHEMA   # kanonisch in app/glossar.py
# Kapitel-Header der Klassen-/Unterklassen-Gruppen, am LETZTEN Kontext-Segment geprueft -
# dieselbe Mechanik wie _OPTION_KONTEXT, nur fuer die Kategorie 'klasse', die Klassen UND
# Unterklassen in einem Topf fuehrt. Befund 30.07.2026: Die Weiche kannte vorher nur
# kontext == 'Klassen' und das deutsche Namensschema; damit fielen 13 Unterklassen aus den
# englischen Druckquellen lautlos aus BEIDEN Listen ('ALCHEMIST' & Co. unter
# 'THE ARTIFICER > ARTIFICER SUBCLASSES', 'BLADESINGER (WIZARD)' & Co. unter 'SUBCLASSES') -
# obwohl foliant_hol_eintrag sie sehr wohl liefert. IGNORECASE, weil Druck-PDFs ihre
# Kapitel-Header in Grossbuchstaben liefern. Fuer neue Quellen hier ergaenzen.
_KLASSEN_KONTEXT = re.compile(r"^(?:Klassen|Classes)$", re.IGNORECASE)
_UNTERKLASSEN_KONTEXT = re.compile(r"^(?:\S+\s+)*(?:Unterklassen|Subclasses)$", re.IGNORECASE)
_UNTERKLASSE_KLAMMER = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")
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
# 'Kampfstil-Talente'-Heading (Spalten-Verschraenkung, s. importer/import_markdown.py).
# Die Typzeile steht IM Eintrag und stimmt.
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
# Rund 55 % aller 'kurz'-Zeilen stammen aus englischen Quellen (gemessen 07.08.2026:
# klasse 55/110, talent 44/62, hintergrund 33/43, spezies 20/34). Bis dahin sagte KEIN
# Kanal, was mit ihnen zu tun ist - Folge war eine Unterklassen-Liste, deren
# Beschreibungen roh englisch dastanden ("Bargain with Whimsical Fey"), mitten in einer
# deutschen Antwort. Der Hinweis haengt an JEDER Optionsliste, nicht nur an den Klassen.
_HINWEIS_KURZ = ("Das Feld 'kurz' ist die BELEGTE Kurzcharakterisierung der Option aus "
                 "ihrer Quelle - oft eine englische Schlagzeile. Gib sie wie jeden anderen "
                 "Text auf DEUTSCH wieder (S3/S4: offizieller Begriff, sonst deutsche "
                 "Wiedergabe mit * und Original in Klammern); reiche sie NIE englisch "
                 "durch und erfinde nichts dazu (B1).")
# Discord-Befund 01.08.2026: auf "Welche Unterklassen hat X?" kam eine Inventurliste, nach
# Datenlage gegliedert ("Namens-Treffer ohne verknuepfte Klassendaten") - fuer die fragende
# Person unbrauchbar. Der Hinweis steht in der TOOL-AUSGABE, weil sie der zuverlaessigste
# der drei Verhaltenskanaele ist (SPEC par. 7) und das Instruktions-Budget
# (test_instruktion_bleibt_kompakt) knapp ist. Seit 07.08.2026 eine benannte Konstante:
# als Dict-Literal war der Text der einzige tragende Grounding-Hinweis, den
# tests/test_verhaltensregeln.py nicht verankern konnte.
_HINWEIS_KLASSENMENUE = (
    "Bei der Frage nach Klassen/Unterklassen: als MENUE antworten - je Option EINE "
    "Kurzzeile aus dem Feld 'kurz' (steht dort keines, per foliant_hol_eintrag "
    "nachladen); NIE aus dem Gedaechtnis charakterisieren, auch nicht 'nur grob' (B1). "
    "Sprachstatus ist eine Fussnote je Option (englische Namen mit * wiedergeben), NIE "
    "das Ordnungsprinzip. Ein Kampagnen-Band fuer die Runde heisst: ob die Option am "
    "Tisch erlaubt ist, entscheidet die SL. Belegzeile aus dem Feld 'zitat' der "
    "gezeigten Option. Mit der Rueckfrage enden, welche Option im Detail gewuenscht ist.")


def _norm(text: str | None) -> str:
    """Kleinschreibung OHNE Diakritika-Faltung - bewusst NICHT `glossar.norm_begriff`.

    Am 31.07.2026 gemessen, weil hier drei Funktionen namens `_norm` mit zwei Bedeutungen
    nebeneinander lebten und nirgends stand, warum. Ergebnis: Der Unterschied traegt an
    GENAU EINER Stelle Gewicht, und zwar in beide Richtungen.

    Faltung waere hier FALSCH: `_ATTRIBUTE` und die Werte von `_ATTR_ALIAS` sind die
    deutschen Attributsnamen MIT Umlaut ('stärke'). Gefaltet ergaebe die Nutzereingabe
    'stärke' den Schluessel 'starke', der in beiden Tabellen fehlt - die Build-Pruefung
    lehnte das Attribut als unbekannt ab und meldete `nicht_pruefbar` statt zu pruefen.
    Genau das brach beim Umstellen drei Tests (A4/A5/T9).

    Faltung waere dort RICHTIG, wo Eintragsnamen SORTIERT werden - deshalb steht dort
    ausdruecklich `_glossar.norm_begriff` (s. `_liste`)."""
    return (text or "").strip().lower()


def _kontext(e: dict | str | None) -> str:
    """Breadcrumb eines Eintrags. Nimmt den Eintrag (dann gilt die Spalte) oder - fuer
    Aufrufer, die nur den Text haben - den blanken Body. Liefert '' statt None: die
    Aufrufer teilen das Ergebnis direkt an ' > ' auf."""
    if isinstance(e, dict):
        if e.get("kontext"):
            return e["kontext"]
        e = e.get("body_md")
    return _db.kontext_aus_body(e) or ""


_EDITION = "2024"   # Charakterlisten und Build-Pruefung sind STRIKT 2024 (A4/Q4)


def _eintraege(con, kategorie: str) -> list[dict]:
    """Eintraege einer Kategorie, NUR Edition 2024 (A4: Listen liefern ausschliesslich
    2024-Optionen; aeltere Staende mischen nie mit), prioritaets-sortiert (Q2).

    OHNE Errata und Regelauslegung: Diese Listen beantworten "was kann ich WAEHLEN" - ein
    Erratum ist keine waehlbare Option, sondern eine Aussage ueber eine. Der Filter sitzt
    hier und nicht in der Ausgabe, weil die Optionslisten eine EIGENE Zusammenfuehrung
    haben (`_varianten`), nicht die Dubletten-Logik aus app/db.py: ein Erratum zu 'Alert'
    hiesse 'Alert' und wuerde dort als Namensvariante mit dem echten Talent verschmelzen -
    unsichtbar, solange sein Prioritaetsband (70) hinter jedem Regelwerk liegt, und ein
    Korrektur-Fragment als Option, sobald das einmal nicht gilt. Wer die Korrektur sucht,
    findet sie ueber die Suche und den Detailabruf, wo sie gekennzeichnet danebensteht.

    Defensiv gegen Bestands-DBs ohne die Spalte: der Serving-Pfad migriert nicht."""
    sql = """SELECT e.id, e.kategorie, e.name_de, e.name_en, e.sprache, e.edition, e.seite,
                    e.body_md, q.titel AS quelle_titel, q.kuerzel AS quelle_kuerzel,
                    q.prioritaet
             FROM eintraege e JOIN quellen q ON q.id = e.quelle_id
             WHERE e.kategorie = ? AND e.edition = ?{filter}
             ORDER BY q.prioritaet, e.id"""
    try:
        return [dict(r) for r in con.execute(
            sql.format(filter=" AND q.inhaltsart NOT IN ('errata','regelauslegung')"),
            (kategorie, _EDITION))]
    except sqlite3.OperationalError:
        return [dict(r) for r in con.execute(sql.format(filter=""),
                                             (kategorie, _EDITION))]


def _ist_option(e: dict, kategorie: str) -> bool:
    """Waehlbare Option vs. Struktur-/Unterabschnitt (Modul-Doku). Entscheidend ist das
    LETZTE Kontext-Segment: steht der Eintrag DIREKT unter einem Kapitel-/Gruppen-Header,
    ist er eine Option; nistet er unter einem konkreten Optionsnamen ('... > Aasimar'),
    ist er ein Unterabschnitt (Merkmale/Abstammung) und keine eigene Option."""
    kontext = _kontext(e)
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
        exakte = [z for z in _glossar.nachschlagen(con, name, richtung=richtung)
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


# Eine Optionsliste ohne Kurzzeile ist eine Liste blanker Namen - und genau da hat das
# Modell im Simulationslauf vom 01.08.2026 aus dem Gedaechtnis ergaenzt ("Fokus auf
# Heilung/Licht", "kaempft mit Ki-Energie"). Sauber formuliert, nirgends belegt: B1.
# Der Bestand traegt die Zeile laengst - die Quellen stellen jeder Unterklasse eine
# Schlagzeile voran ("Bargain with Whimsical Fey", "_Lindere die Leiden der Welt_").
# Klassen-Steckbriefe haben keine, dort steht das Hauptattribut in der Merkmalstabelle -
# fuer die Klassenwahl ohnehin die nuetzlichere Angabe.
_ZIER = re.compile(r"[*_`]+")
_HAUPTATTRIBUT = re.compile(
    r"\|\s*\*\*(?:Hauptattribut|Primary Ability)\*\*\s*\|\s*([^|]+?)\s*\|", re.IGNORECASE)
# Die Huerden stammen aus einem Probelauf gegen den VOLLBESTAND (01.08.2026) - am
# Fixture war keine davon zu sehen. Die Druckquellen streuen Bildnachweise als eigene
# Zeile in den Text: 'ERION MAKUO', 'Ignatius Budi', 'Helge C. Balzer',
# 'ARTIST: KEVIN GNUTZMANS'. Ohne die Huerden stand 'Helge C. Balzer' als
# Charakteristik der Spezies Dhampir in der Liste.
#   - Schlagzeile: mindestens VIER Woerter (faengt dreiteilige Namen), kein Punkt am
#     Ende, keine Tabellen-/Ueberschriftenzeile.
#   - Fliesstext-Rueckfall: nur ein ganzer SATZ (Punkt am Ende, mindestens fuenf
#     Woerter). Das schliesst Datenzeilen wie 'Groesse: Mittelgross (150-210 cm)' aus.
# Lieber kein Feld als ein falsches - der Darstellungs-Hinweis sagt dem Modell, dann
# nachzuladen.
_BILDNACHWEIS = re.compile(r"^\s*(artist|kuenstler|künstler|illustration)\b", re.IGNORECASE)
# Derselbe Nachweis MITTEN in der Zeile: manche Baende setzen ihn ohne Umbruch zwischen
# Schlagzeile und Fliesstext ('Command a Construct Guardian ARTIST: MICHAEL BROUSSARD A
# Battle Smith is a combination of...'). `_BILDNACHWEIS` ist auf '^' verankert und greift
# dort nicht - der Credit stand deshalb bis zum 07.08.2026 in der Kurzzeile des Battle
# Smith. Ersetzt wird durch einen ZEILENUMBRUCH, nicht durch nichts: so zerfaellt die
# Doppelzeile in ihre zwei echten Teile und die Schlagzeile bleibt als Kurzzeile uebrig.
# Der Marker ist schreibungsunabhaengig, der Namenslauf bewusst NUR versal - sonst frisst
# er den folgenden Satz mit. Mindestens zwei Zeichen je Namensteil laesst das einzelne
# 'A' von 'A Battle Smith' stehen.
_BILDNACHWEIS_INLINE = re.compile(
    r"\s*(?i:artist|illustrator|kuenstler|künstler|illustration)\s*:\s*"
    r"(?:[A-ZÄÖÜ][A-ZÄÖÜßÉ'’.\-]+\s+){0,3}[A-ZÄÖÜ][A-ZÄÖÜßÉ'’.\-]+\s*")
# Die Typzeile eines Talents ('General Feat (Prerequisite: ...)', 'Allgemeines Talent
# (Voraussetzung: ...)') steht schon als eigene Felder `kategorie`/`voraussetzung` in
# der Zeile - als Kurzcharakteristik waere sie eine Dopplung und verdraengt den Satz,
# der WIRKLICH sagt, was das Talent tut.
_TYPZEILE = re.compile(r"^[\w äöüÄÖÜß.-]{0,40}\b(Feat|Talent)\b[^(]*\(.*\)\s*$",
                       re.IGNORECASE)
# Markdown-Escapes der Druckquellen ('AH\-sih\-mar', 'Level 4\+') - im Fliesstext einer
# Antwort sind die Schraegstriche schlicht Muell.
_ESCAPE = re.compile(r"\\([-+*_.()\[\]#])")
# Ueberleitungssaetze, die nichts ueber die Option aussagen ("Du erhaeltst folgende
# Vorzuege."). Sie stehen in vielen Talenten vor der eigentlichen Aufzaehlung und
# waeren als Kurzcharakteristik eine leere Zeile im Menue.
_FLOSKEL = re.compile(r"^(you gain the following"
                      r"|du erh(ä|ae)ltst (die )?folgenden?)", re.IGNORECASE)
_KURZ_MIN_WOERTER = 4
_KURZ_SATZ_MIN_WOERTER = 5
_KURZ_MAX_ZEICHEN = 160


def _kurzzeile(body: str | None) -> str | None:
    """Eine BELEGTE Kurzcharakteristik aus dem Eintragstext; None, wenn keine da ist.

    Lieber kein Feld als ein schlechtes: fehlt die Zeile, sagt der Darstellungs-Hinweis
    dem Modell, den Eintrag nachzuladen - raten darf es in keinem der beiden Faelle."""
    def sauber(text: str) -> str:
        return _ESCAPE.sub(r"\1", _ZIER.sub("", text)).strip()

    zeilen = [z.strip() for z in _BILDNACHWEIS_INLINE.sub("\n", body or "").split("\n")]
    zeilen = [z for z in zeilen if z and not z.startswith("*Kontext:")
              and not _BILDNACHWEIS.match(sauber(z))
              and not _TYPZEILE.match(sauber(z))
              and not _FLOSKEL.match(sauber(z))]
    if not zeilen:
        return None
    schlagzeile = sauber(zeilen[0])
    if (not zeilen[0].startswith("#") and "|" not in zeilen[0]
            and not schlagzeile.endswith(".")
            and len(schlagzeile) <= 120
            and len(schlagzeile.split()) >= _KURZ_MIN_WOERTER):
        return schlagzeile
    m = _HAUPTATTRIBUT.search(body or "")
    if m:
        return f"Hauptattribut: {sauber(m.group(1))}"
    for zeile in zeilen:                      # sonst der erste ganze Fliesstext-SATZ
        if zeile.startswith("#") or "|" in zeile:
            continue
        satz = sauber(zeile)
        punkt = satz.find(". ")
        if punkt > 0:
            satz = satz[:punkt + 1]
        if not satz.endswith(".") or len(satz.split()) < _KURZ_SATZ_MIN_WOERTER:
            continue
        return (satz[:_KURZ_MAX_ZEICHEN].rstrip() + "…"
                if len(satz) > _KURZ_MAX_ZEICHEN else satz)
    return None


def _zeile(con, g: dict, **extra) -> dict:
    """Knappe Listen-Zeile einer Options-Gruppe: Anzeige Deutsch-first (S3/S4)."""
    name_de = next((e["name_de"] for e in g["eintraege"] if e["name_de"]), None)
    name_en = next((e["name_en"] for e in g["eintraege"] if e["name_en"]), None)
    fuehrend = g["eintraege"][0]
    # Die Anzeige baut die Ausgabe-Schicht, nicht dieses Modul. Die beiden Sonderzweige,
    # die hier bis zum 31.07.2026 standen ('Champion (Champion)' vermeiden, sonst
    # markiere()), sind genau das, was `_anzeige_name` fuer eine deutsche Quelle ohnehin
    # tut - am Bestand mit sechs Sonden zeichengleich nachgemessen. Zwei Kopien einer
    # Deutsch-first-Regel sind eine zu viel: S4 steht in ausgabe.py.
    anzeige = _aus._anzeige_name(con, {"name_de": name_de, "name_en": name_en,
                                       "sprache": "de" if name_de else "en"})
    # eintrag_id/quelle_kuerzel (Review 30.07.2026): Die Listen brachen zwei Zusagen,
    # die der Suchpfad einhaelt. Ohne eintrag_id war der Rundlauf Liste->Detail nicht
    # moeglich (SYN-P1-002 sichert genau das zu, _knapp setzt es seit jeher). Ohne
    # quelle_kuerzel konnte _markiere_inhaltsart nicht greifen - die Optionslisten
    # lieferten Abenteuer-/Setting-Inhalte voellig unmarkiert aus, obwohl der
    # Spoiler-Schutz die OBERSTE Regel ist (belegt: 'Aberrantes Drachenmal' aus
    # Eberron stand ununterscheidbar zwischen den SRD-Talenten).
    # Das Kuerzel stammt vom FUEHRENDEN Eintrag der Gruppe, wie bei _knapp. Bei
    # gemischten Gruppen fuehrt wegen ORDER BY q.prioritaet die Regelwerksquelle - dann
    # ist die Option auch wirklich im Regelwerk enthalten und keine Spoilergefahr;
    # 'quellen' zeigt die uebrigen Baende weiterhin an.
    # `zitat` wie beim Suchtreffer (_knapp): stil.py verlangt, die Belegzeile WOERTLICH
    # auszugeben - ohne das Feld baute das Modell sie selbst und mischte im Test drei
    # Quellen zu einer erfundenen Zeile zusammen ("Player's Handbook / SRD 5.2.1").
    z = {"eintrag_id": fuehrend["id"], "anzeige": anzeige,
         "name_de": name_de, "name_en": name_en,
         "edition": fuehrend["edition"], "quelle_kuerzel": fuehrend["quelle_kuerzel"],
         "quellen": sorted({e["quelle_titel"] for e in g["eintraege"]}),
         "zitat": _aus._zitat(fuehrend)}
    kurz = _kurzzeile(fuehrend["body_md"])
    if kurz:
        z["kurz"] = kurz
    z.update({k: v for k, v in extra.items() if v is not None})
    return z


def _liste(kategorie: str, schluessel: str, schritt_hinweis: str) -> dict:
    """Gemeinsame Listen-Maschine fuer Spezies/Hintergruende/Talente."""
    con = _aus._verbinde()
    if con is None:
        return {schluessel: [], "hinweis": _aus.HINWEIS_DB_FEHLT}
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
                                   if (seg := _kontext(e).split(" > ")[-1].strip())
                                   .title() in _DDB_TALENT_GRUPPE), None)
                    if gruppe:
                        extra["kategorie"] = gruppe
            zeilen.append(_zeile(con, g, **extra))
        # Deutsche Alphabetisierung (DIN 5007-1: ä = a), nicht Codepoint-Ordnung:
        # ohne Faltung sortiert 'ä' (U+00E4) hinter 'z', und "Kämpfer" stand in der
        # Klassenliste hinter "Kleriker". Ein Spieler liest diese Liste.
        zeilen.sort(key=lambda z: _glossar.norm_begriff(z["name_de"] or z["name_en"]))
        antwort = {schluessel: zeilen, "hinweis_reihenfolge": schritt_hinweis,
                   "hinweis": _HINWEIS_BESTAND, "hinweis_kurz": _HINWEIS_KURZ}
        _aus._markiere_inhaltsart(con, antwort, zeilen)
        if not zeilen:
            antwort["hinweis"] = _aus.HINWEIS_LEER
        return antwort
    finally:
        con.close()


def foliant_liste_optionen(
        kategorie: Literal["klasse", "hintergrund", "spezies", "talent"],
        talent_kategorie: Literal["herkunft", "allgemein", "kampfstil",
                                  "epische_gabe"] | None = None) -> dict:
    """Waehlbare Optionen einer Kategorie im Bestand, KNAPP - Details per
    foliant_hol_eintrag. Zeigt NUR waehlbare Optionen, nicht die Unterabschnitte
    (Klassenmerkmale, Zauberlisten, Merkmalsbeschreibungen).

    BEI 'HILF MIR, EINEN CHARAKTER ZU ERSTELLEN' ist der erste Aufruf
    kategorie='klasse' - SOFORT, ohne vorher zu fragen, ob der Nutzer schon eine
    Klasse im Kopf hat. Zeig die Auswahl, dann kann er waehlen. Nenne NIE
    Beispielklassen aus dem Gedaechtnis: welche es gibt, sagt der Bestand, und
    fehlende Optionen heissen fehlendes Buch (B1/B2).

    kategorie in der Reihenfolge der 2024-Charaktererstellung (B7):
      klasse       Schritt 1 - inkl. der Unterklassen je Klasse
      hintergrund  Schritt 2 - liefert Attributserhoehungen und das Ursprungstalent
      spezies      Schritt 3
      talent       weitere Talente ueber Stufenaufstiege
    talent_kategorie filtert NUR bei kategorie='talent' (herkunft | allgemein |
    kampfstil | epische_gabe); ungueltige Werte werden mit 'fehler' abgelehnt, was
    NICHT 'nichts im Bestand' bedeutet.
    Jede Zeile traegt 'zitat' (Belegzeile woertlich) und - wo der Bestand eine
    hergibt - 'kurz': die BELEGTE Kurzcharakteristik der Option. Charakterisiere
    Optionen nur daraus oder aus foliant_hol_eintrag, nie aus dem Gedaechtnis.
    KERNREGELN: nur aus dem Bestand nennen, nichts aus Allgemeinwissen ergaenzen
    (fehlende Optionen = fehlendes Buch, B2); Quelle und Regelversion nennen;
    Deutsch-first (englisches Original in Klammern)."""
    if talent_kategorie is not None and kategorie != "talent":
        return {"fehler": f"talent_kategorie gilt nur fuer kategorie='talent', nicht "
                          f"fuer {kategorie!r}.",
                "hinweis": "Ungueltige PARAMETER-Kombination - das ist KEIN 'nichts im "
                           "Bestand'; Aufruf ohne talent_kategorie wiederholen."}
    # Spezies und Hintergrund brauchen nur die Listen-Maschine plus ihren Schritt-Hinweis.
    # Bis zum 31.07.2026 stand dafuer je eine eigene Funktion - Reste der zwoelf am
    # 30.07.2026 abgeschafften foliant_liste_<typ>-Werkzeuge, samt vollstaendiger
    # Tool-Beschreibung im Docstring, obwohl sie keine Werkzeuge mehr sind.
    if kategorie == "klasse":
        return _liste_klassen()
    if kategorie == "talent":
        return _liste_talente(talent_kategorie)
    if kategorie == "hintergrund":
        return _liste("hintergrund", "hintergruende",
                      "Hintergrund ist SCHRITT 2 von 4 (nach der Klasse). "
                      + _HINWEIS_REIHENFOLGE)
    return _liste("spezies", "spezies",
                  "Spezies ist SCHRITT 3 von 4 (nach Klasse und Hintergrund). "
                  + _HINWEIS_REIHENFOLGE)


def _liste_talente(kategorie: Literal["herkunft", "allgemein",
        "kampfstil", "epische_gabe"] | None = None) -> dict:
    """Talente, optional auf eine Talent-Kategorie gefiltert. Eigene Funktion statt eines
    _liste-Aufrufs, weil der Filter NACH der Gruppierung greifen muss: die Kategorie steht
    je Eintrag in der Typzeile bzw. der DDB-Feat-Gruppe, nicht in der Abfrage."""
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
                                  + _aus.HINWEIS_LEER)
    return antwort


def _liste_klassen() -> dict:
    """Klassen mit ihren Unterklassen. Eigene Maschine statt _liste, weil die Kategorie
    'klasse' BEIDES fuehrt und die Zuordnung ueber drei Quellen-Schreibweisen laeuft."""
    con = _aus._verbinde()
    if con is None:
        return {"klassen": [], "hinweis": _aus.HINWEIS_DB_FEHLT}
    try:
        alle = _eintraege(con, "klasse")
        klassen_eintraege, unterklassen_eintraege = [], []
        for e in alle:
            kontext = _kontext(e)
            if kontext:
                letztes_segment = kontext.split(" > ")[-1].strip()
                if _KLASSEN_KONTEXT.match(letztes_segment):
                    klassen_eintraege.append(e)
                elif (_UNTERKLASSEN_KONTEXT.match(letztes_segment)
                      or _UNTERKLASSE_DE.match(e["name_de"] or "")):
                    unterklassen_eintraege.append(e)
                # Alles Uebrige ist Unterabschnitt (Klassenmerkmale, Zauberliste,
                # 'Ein Barde werden ...') und gehoert bewusst in keine der Listen -
                # foliant_hol_eintrag weist sie als 'verwandte_abschnitte' aus.
            else:
                (unterklassen_eintraege if _SUBCLASS.search(e["body_md"] or "")
                 else klassen_eintraege).append(e)

        gruppen = _gruppiere(con, klassen_eintraege)
        zeilen = [(g, _zeile(con, g, unterklassen=[])) for g in gruppen]

        gruppen_u = _gruppiere(con, unterklassen_eintraege)
        # Flaches Chunking der Druckquellen: unter 'Paladin > Paladin Subclasses' steht
        # neben 'Oath of the Ancients' auch dessen Abschnitt 'Oath of the Ancients
        # Spells' - gleicher Kontext, fuer die Weiche oben nicht zu unterscheiden.
        # Erkennbar am NAMEN: er fuehrt den Namen einer Geschwister-Unterklasse fort.
        # Solche Fortsetzungen sind Unterabschnitte, keine waehlbaren Optionen - in der
        # Liste stand die Zauberliste sonst als eigene Unterklasse neben ihrem Schwur.
        def _u_name(g: dict) -> str:
            e = g["eintraege"][0]
            return _norm(e["name_de"] or e["name_en"] or "")
        namen_je_kontext: dict[str, set[str]] = {}
        for g in gruppen_u:
            namen_je_kontext.setdefault(_kontext(g["eintraege"][0]), set()).add(_u_name(g))
        gruppen_u = [g for g in gruppen_u
                     if not any(n != _u_name(g) and _u_name(g).startswith(n + " ")
                                for n in namen_je_kontext[_kontext(g["eintraege"][0])])]

        # Unterklassen ihren Klassen zuordnen - gegen die Namensvarianten der Klasse,
        # ueber die VIER Schreibweisen der Quellen (jede fehlte einmal wirklich):
        # srd-de im Kontext ('Klassen > X'), Open5e im Body ('*Subclass of: X*'),
        # Druckquellen als Klammer-Suffix am Namen ('BLADESINGER (WIZARD)') und
        # DDB-PHB-2024 im Kontext-PFAD ('Warlock > Warlock Subclasses'). Ohne die
        # vierte standen alle 48 PHB-Unterklassen als Waisen mit dem falschen Hinweis
        # 'Klasse nicht im Bestand' in der Liste - der Discord-Bot hat diese Diagnose
        # am 01.08.2026 woertlich an die Runde weitergereicht.
        for ug in gruppen_u:
            referenzen: set[str] = set()
            for e in ug["eintraege"]:
                kontext = _kontext(e)
                if kontext.startswith("Klassen > "):
                    referenzen.add(_norm(kontext.split(" > ", 1)[1]))
                segmente = [s.strip() for s in kontext.split(" > ")] if kontext else []
                if segmente and _UNTERKLASSEN_KONTEXT.match(segmente[-1]):
                    # 'Warlock > Warlock Subclasses': die Klasse steht davor im Pfad
                    # UND im Segment selbst ('Warlock Subclasses'). Beide nutzen -
                    # manche Quellen haben nur eines von beiden. 'THE ARTIFICER'
                    # traegt einen Artikel, den kein Klassenname fuehrt.
                    if len(segmente) >= 2:
                        referenzen.add(_norm(re.sub(r"^the\s+", "", segmente[-2],
                                                    flags=re.IGNORECASE)))
                    im_segment = re.match(r"^(.+?)\s+(?:Unterklassen|Subclasses)$",
                                          segmente[-1], re.IGNORECASE)
                    if im_segment:
                        referenzen.add(_norm(re.sub(r"^the\s+", "", im_segment.group(1),
                                                    flags=re.IGNORECASE)))
                m = _SUBCLASS.search(e["body_md"] or "")
                if m:
                    referenzen.add(_norm(m.group(1)))
                km = _UNTERKLASSE_KLAMMER.match(e["name_de"] or e["name_en"] or "")
                if km:
                    referenzen.add(_norm(km.group(2)))
            uz = _zeile(con, ug)
            # Anzeige-/Abrufname der Unterklasse ohne das 'X-Unterklasse:'-Praefix:
            m = _UNTERKLASSE_DE.match(uz["name_de"] or "")
            if m:
                uz["name_de"] = m.group(2).strip()
                en = f" ({uz['name_en']})" if uz.get("name_en") else ""
                uz["anzeige"] = f"{uz['name_de']}{en}"
            elif not uz.get("name_de") and (km := _UNTERKLASSE_KLAMMER.match(
                    uz.get("name_en") or "")):
                # Ohne diese Kuerzung liest sich 'BLADESINGER (WIZARD)' wie das
                # Deutsch-first-Format 'Deutsch (English)' - der Klassenname saehe aus
                # wie die englische Entsprechung der Unterklasse (S3/S4).
                uz["name_en"] = km.group(1).strip()
                uz["anzeige"] = uz["name_en"]
            ziel = next((z for g, z in zeilen if g["varianten"] & referenzen), None)
            if ziel is not None:
                # setdefault: eine Waisen-Zeile (unten, ohne 'unterklassen') kann selbst
                # zum Ziel einer spaeteren Unterklasse werden - das war ein KeyError.
                ziel.setdefault("unterklassen", []).append(uz)
            else:
                # Handlungsanweisung statt Datenbank-Diagnose: die Unterklasse SELBST ist
                # vollstaendig im Bestand und waehlbar - nur der Grundeintrag ihrer
                # Klasse fehlt. Der alte Text ('Zugehoerige Klasse nicht im Bestand.')
                # las sich wie ein Mangel der Unterklasse; der Discord-Bot hat daraus
                # 'kann keinen Steckbrief liefern' gemacht, obwohl der Steckbrief da war.
                zeilen.append(({"varianten": referenzen},
                               {**uz, "hinweis": "Waehlbare Unterklasse - nur der "
                                "Grundeintrag ihrer Klasse ist nicht im Bestand. Als "
                                "Option anbieten, nicht als Mangel ausgeben; Details "
                                "liefert foliant_hol_eintrag."}))

        # Deutsche Alphabetisierung wie in `_liste` (s. dort).
        klassen = sorted((z for _g, z in zeilen),
                         key=lambda z: _glossar.norm_begriff(z["name_de"] or z["name_en"]))
        antwort = {"klassen": klassen,
                   "hinweis_reihenfolge": "Klasse ist SCHRITT 1 von 4. " + _HINWEIS_REIHENFOLGE,
                   "hinweis": _HINWEIS_BESTAND, "hinweis_kurz": _HINWEIS_KURZ,
                   "hinweis_darstellung": _HINWEIS_KLASSENMENUE}
        # Auch die geschachtelten Unterklassen kennzeichnen - sie tragen dieselbe
        # Herkunft und sind fuer den Spoiler-Schutz kein Sonderfall.
        _aus._markiere_inhaltsart(con, antwort, klassen,
                                *[k.get("unterklassen") or [] for k in klassen])
        if not klassen:
            antwort["hinweis"] = _aus.HINWEIS_LEER
        return antwort
    finally:
        con.close()


def foliant_hol_attributswerte(attributsmethode: Literal["standard_array",
        "point_buy"] = "standard_array") -> dict:
    """Regeln zur Attributswert-Vergabe nach 2024: 'standard_array' (Standardsatz) oder
    'point_buy' (Punktkosten). Die Werte werden am BESTAND belegt ('Schritt 3:
    Attributswerte') - fehlt die importierte Regelquelle, gibt es KEINE Werte aus
    Allgemeinwissen (B1/A5). Die Zuteilung auf Attribute macht Claude im Gespraech;
    danach foliant_pruefe_build aufrufen.
    KERNREGELN: nur aus dem Bestand; Quelle + Regelversion nennen; Deutsch-first."""
    if attributsmethode not in ("standard_array", "point_buy"):
        return {"fehler": f"Unbekannte attributsmethode {attributsmethode!r} - gueltig: "
                          f"'standard_array', 'point_buy'.",
                "hinweis": _aus._HINWEIS_PARAMETER}
    beleg, kosten_geprueft = _attributsregel_beleg(attributsmethode)
    if beleg is None:
        return {"verfuegbar": False, "methode": attributsmethode,
                "hinweis": ("Keine importierte 2024-Attributsregel im Bestand ('Schritt 3: "
                            "Attributswerte') - ich gebe keine Werte aus Allgemeinwissen "
                            "aus (B1/A5). Erst die Regelquelle importieren.")}
    if attributsmethode == "standard_array":
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


def _fehlbefund(detail: dict, was: str, name: str) -> str:
    """Warum eine Option nicht verwertbar ist. 'Nicht im Bestand' ist nur EINER der
    moeglichen Gruende - der andere ist MEHRDEUTIGKEIT (Befund 30.07.2026).

    Die Pruefung wertete nur `gefunden` aus. Lieferte der Detailabruf eine
    Mehrdeutigkeits-Absage ('Schild' = Zauber ODER Ruestung), behandelte sie das wie
    'gar nicht vorhanden' und meldete woertlich "ist nicht im 2024-Bestand - evtl. fehlt
    ein Buch". Der Inhalt IST da, nur die Angabe war unscharf: genau die Antwortklasse,
    gegen die SYN-P0-006 angetreten ist, und fuer den Nutzer nicht von einer echten
    Bestandsluecke zu unterscheiden."""
    if detail.get("mehrdeutig"):
        namen = [k.get("anzeige_name") or k.get("name_de") or k.get("name_en") or "?"
                 for k in (detail.get("kandidaten") or [])][:5]
        return (f"{was} '{name}' ist im Bestand MEHRDEUTIG"
                + (f" ({', '.join(namen)})" if namen else "")
                + " - das ist KEINE Fehlanzeige, sondern eine unscharfe Angabe. "
                  "Bitte praezisieren und erneut pruefen (B4).")
    return f"{was} '{name}' ist nicht im 2024-Bestand - evtl. fehlt ein Buch (B2)."


def _entsprechungen(*namen: str | None) -> set[str]:
    """Normalisierte Namen plus deren EXAKTE Glossar-Entsprechungen (A4: eine deutsch
    gewaehlte Klasse muss eine nur englisch vorhandene Unterklasse matchen)."""
    menge = {_glossar.norm_begriff(n) for n in namen if n} - {""}
    con = _aus._verbinde()
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
    {stufe: {spaltenname_normalisiert: zellwert}}. Leeres dict, wenn keine gefunden wird
    (dann: nicht_pruefbar, Q4).

    Erkennung ueber die DATENFORM, nicht (nur) den Kopf: der PDF-Import verklebt bei den
    Zauberklassen die mehrzeiligen Tabellenkoepfe ('Stufe'+'Uebungsbonus' -> 'Stufebonus',
    Befund 17.07.2026 - Barde/Druide/Magier/Paladin/Waldlaeufer waren dadurch still
    'nicht_pruefbar', beim Druiden griff sogar die Tiergestalt-Tabelle). Eine
    Klassentabelle ist die Pipe-Tabelle, deren erste Spalte aufsteigende Stufen AB 1
    liefert; bei mehreren Kandidaten gewinnt die mit den meisten Stufenzeilen (die echte
    fuehrt 1-20). Die (ggf. verklebten) Koepfe bleiben als Schluessel erhalten - die
    Abnehmer suchen Substrings ('unterklasse' in den WERTEN, 'waffenbeherrschung' im
    Kopf) und bleiben davon unberuehrt."""
    zeilen = (body or "").splitlines()
    beste: dict[int, dict[str, str]] = {}
    i = 0
    while i < len(zeilen):
        z = zeilen[i]
        if not z.strip().startswith("|"):
            i += 1
            continue
        # Koepfe: Markdown-Reste, Soft-Hyphens UND Leerzeichen raus ('waffenbe herrschung'
        # aus dem PDF-Zeilenumbruch -> 'waffenbeherrschung'); leere/doppelte Koepfe
        # eindeutig machen, sonst verschluckt dict(zip(...)) ganze Spalten (der Magier-
        # Kopf beginnt mit Leerspalten - 'MagierUnterklasse' ging so verloren).
        roh_koepfe = [re.sub(r"\*+|<br>|­|-|\s+", "", teil).strip().lower()
                      for teil in z.strip().strip("|").split("|")]
        koepfe: list[str] = []
        for n, kopf in enumerate(roh_koepfe):
            if not kopf or kopf in koepfe:
                kopf = f"{kopf}#{n}" if kopf else f"spalte{n}"
            koepfe.append(kopf)
        tabelle: dict[int, dict[str, str]] = {}
        j = i + 1
        while j < len(zeilen) and zeilen[j].strip().startswith("|"):
            zellen = [teil.strip() for teil in zeilen[j].strip().strip("|").split("|")]
            j += 1
            if not zellen or set(zellen[0]) <= {"-", ":", " "}:
                continue
            try:
                stufe = int(zellen[0])
            except ValueError:
                continue
            tabelle[stufe] = dict(zip(koepfe, zellen))
        ist_stufentabelle = tabelle and (
            "stufe" in koepfe
            or (min(tabelle) == 1 and sorted(tabelle) == list(range(1, max(tabelle) + 1))
                and len(tabelle) >= 5))
        if ist_stufentabelle and len(tabelle) > len(beste):
            beste = tabelle
        i = j
    return beste


def _klassenmerkmale_body(name_de: str) -> str | None:
    """Body des Klassen-Eintrags MIT Stufentabelle (srd-de), ohne Genitiv-Raterei ueber
    den Kontext 'Klassen > <Klasse>' aufgeloest. NUR 2024 und in Quellen-Praezedenz
    (A4: die Tabelle muss zum kanonischen 2024-Inhalt gehoeren, nie zu einem Altstand).

    Bewusst KEIN Namensfilter ('Klassenmerkmale des X'): srd-de chunkt nicht jede Klasse
    gleich - beim Schurken steht die Stufentabelle im Abschnitt 'Ein Schurke werden ...'
    (Befund 17.07.2026: unterklasse_stufe war dort faelschlich 'nicht_pruefbar'). Das
    tragfaehige Kriterium ist der Kontext plus eine tatsaechlich parsebare Tabelle."""
    con = _aus._verbinde()
    if con is None:
        return None
    try:
        bedingung, params = _db.kontext_bedingung(con, f"Klassen > {name_de}", praefix="e.")
        rows = con.execute(
            "SELECT e.body_md FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
            f"WHERE e.kategorie='klasse' AND e.edition=? AND {bedingung} "
            "ORDER BY q.prioritaet, e.id",
            [_EDITION, *params]).fetchall()
        for (body,) in rows:
            if _stufentabelle(body):
                return body
        return rows[0][0] if rows else None
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
            mehrdeutig = bool(klasse_detail.get("mehrdeutig"))
            fehlende_angaben.append(
                f"klasse ({'mehrdeutig' if mehrdeutig else 'nicht im 2024-Bestand'})")
            _befund(pruefungen, "klasse", "nicht_pruefbar",
                    _fehlbefund(klasse_detail, "Klasse", klasse)
                    + " Alle klassenabhaengigen Pruefungen entfallen.")
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
                        _fehlbefund(u_detail, "Unterklasse", unterklasse))
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
                    _fehlbefund(s_detail, "Spezies", spezies))
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
                        _fehlbefund(h_detail, "Hintergrund", hintergrund))
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
                    _fehlbefund(t_detail, "Talent", talent))
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
