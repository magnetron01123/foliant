"""Blocker-Regression SYN-P0-001 (Synthese 2026-07-12, verifiziert): Fuzzy-Glossartreffer
sind Suchvorschlaege, NIE fachliche Identitaet.

Der Realbestand-Fall: 'Aktionen' matcht die Glossarzeile 'Reaktionen' mit fuzz.ratio 88.9
(Cutoff 88). Vor dem Fix wurde daraus (a) die 'offizielle Uebersetzung'
'Reaktionen (Reactions)', (b) ein Exakt-Treffer im Detailabruf (hol_regel('Aktionen')
lieferte den Monster-Reaktionen-Eintrag S. 299 mit Beleg) und (c) ein falsches
Klammer-Original in der Anzeige. Fixture bildet genau diese Konstellation nach."""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app import glossar as gl
from app.tools import nachschlagen as ns
from app.tools import suche as su
from tests.hilfen import SCHEMA

_SCHEMA = SCHEMA
@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    pfad = tmp_path / "foliant-identitaet.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
        "VALUES ('srd-de','SRD 5.2.1 (Deutsch)','de','2024','pdf','CC-BY-4.0',10)")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (1,'regel',?,NULL,'de','2024',?,?)",
        [("Aktionen", "11",
          "*Kontext: Die Spielregeln > Kampf*\n\nWenn du etwas tust, fuehrst du eine "
          "Aktion aus: Angriff, Zauber wirken, Spurt, Rueckzug ..."),
         ("Reaktionen", "299",
          "*Kontext: Monster > Elemente von Wertekästen*\n\nWenn einem Monster Reaktionen "
          "zur Verfuegung stehen, sind sie in diesem Abschnitt aufgefuehrt.")])
    # Glossar kennt NUR 'Reaktionen' - fuzzy-nah zu 'Aktionen' (ratio 88.9 >= Cutoff 88):
    con.execute(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
        "VALUES ('Reactions','Reaktionen',1,'Spielerhandbuch 2024','2024')")
    # Zweites Paar fuer die term_de-Exakt-Disziplin: 'Restrained' liegt zu 'Retrained'
    # fuzzy-nah OBERHALB des Cutoffs (94.7 > 88) - anders als 'Actions'/'Reactions'.
    con.execute(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
        "VALUES ('Restrained','Festgehalten',1,'Spielerhandbuch 2024','2024')")
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def test_lookup_traegt_matchtyp(bestand):
    con = adb.connect(str(adb.standard_pfad()))
    try:
        zeilen = gl.nachschlagen(con, "Aktionen", richtung="de_en")
        assert zeilen and all(z["match"] == "fuzzy" for z in zeilen)
        exakt = gl.nachschlagen(con, "Reaktionen", richtung="de_en")
        assert exakt and exakt[0]["match"] == "exakt"
        # term_de nutzt nur exakte Zeilen: fuer 'Actions' gibt es keine -> None.
        # Seit 31.07.2026 None statt ("Actions", False): das In-Band-Signal war von einem
        # echten Treffer mit gleichlautendem Deutsch (Aasimar, Paladin, Charisma - 110
        # offizielle Zeilen im Bestand) nicht unterscheidbar, und der Charakterbogen
        # stempelte denen deshalb einen Stern auf.
        assert gl.term_de(con, "Actions") is None
        assert gl.term_de(con, "Reactions") == ("Reaktionen", True)
    finally:
        con.close()


def test_term_de_erfindet_keine_uebersetzung(bestand):
    """term_de darf NIE eine fuzzy-aehnliche FREMDE Zeile als Uebersetzung ausgeben
    (SYN-P0-001). Der Schutz sitzt in den beiden `nachschlagen_exakt`-Aufrufen; getestet war er
    bisher nur mit 'Actions', und dessen ratio zu 'Reactions' liegt mit 87.5 UNTER dem
    Cutoff 88 - eine Mutation von `nachschlagen_exakt` auf `nachschlagen` blieb damit gruen, weil gar
    keine Fuzzy-Zeile entstand. 'Retrained'/'Restrained' liegt mit 94.7 darueber und
    trifft die Invariante wirklich.

    Zwei Aufrufstellen, zwei Faelle (CONCEPT.md par. 12: die Gegenprobe muss jede einzeln
    treffen): der direkte Begriff und der Klammer-Suffix-Pfad."""
    con = adb.connect(str(adb.standard_pfad()))
    try:
        # 1. Aufrufstelle: direkter Nachschlag.
        assert gl.term_de(con, "Retrained") is None
        # 2. Aufrufstelle: nach Abzug des Klammer-Suffix ("Retrained (Special)" -> "Retrained").
        assert gl.term_de(con, "Retrained (Special)") is None
        # Der echte Treffer bleibt selbstverstaendlich einer:
        assert gl.term_de(con, "Restrained") == ("Festgehalten", True)
    finally:
        con.close()


def test_lookup_exakt_waehlt_genau_wie_lookup(bestand):
    """nachschlagen_exakt ist eine reine Beschleunigung (Index statt Voll-Scan + Fuzzy-Lauf,
    30 ms -> 0,07 ms bei 8 Suchtreffern). Es darf sich deshalb NICHTS an der Auswahl
    aendern - auch nicht die Reihenfolge, denn der erste Treffer ist die angezeigte
    Fassung. Homonyme mit mehreren offiziellen Zeilen sind hier der scharfe Fall."""
    con = adb.connect(str(adb.standard_pfad()))
    try:
        for richtung, begriffe in (("de_en", ("Aktionen", "Reaktionen", "Gibtsnicht")),
                                   ("en_de", ("Reactions", "Actions", "Gibtsnicht"))):
            for begriff in begriffe:
                alt = [z for z in gl.nachschlagen(con, begriff, richtung=richtung)
                       if z["match"] == "exakt"]
                neu = gl.nachschlagen_exakt(con, begriff, richtung=richtung)
                assert [(z["term_de"], z["term_en"]) for z in alt] == \
                       [(z["term_de"], z["term_en"]) for z in neu], f"{richtung}/{begriff}"
        # Und der Index darf keine FUZZY-Zeile durchlassen (SYN-P0-001):
        assert gl.nachschlagen_exakt(con, "Aktionen", richtung="de_en") == []
    finally:
        con.close()


def test_caches_invalidieren_bei_glossar_aenderung(bestand):
    """Die Beschleunigung haengt an drei abgeleiteten Caches (Exakt-Index, Namens-Index,
    Bruecken-Dict). Ein Cache, der eine Aenderung nicht mitbekommt, liefert stille
    Falschauskuenfte - das waere schlimmer als der eingesparte Aufwand."""
    from app import db as adb

    con = adb.connect(str(adb.standard_pfad()))
    try:
        assert gl.term_de(con, "Reactions") == ("Reaktionen", True)
        assert gl.nachschlagen_exakt(con, "Frischbegriff", richtung="en_de") == []
        con.execute("INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
                    "VALUES ('Frischbegriff','Frischwort',1,'Test','2024')")
        con.commit()
        # Ohne Invalidierung wuerde der Index den neuen Begriff nie sehen:
        assert gl.nachschlagen_exakt(con, "Frischbegriff", richtung="en_de")[0]["term_de"] \
            == "Frischwort"
        assert gl.term_de(con, "Frischbegriff") == ("Frischwort", True)
        assert "frischwort" in adb._brueckennamen(con).get("frischbegriff", set())
    finally:
        con.close()


def test_editionen_cache_sieht_eine_neue_edition(bestand):
    """Vierter abgeleiteter Cache (Audit 28.07.2026): _editionen war ein DISTINCT-Scan je
    Suchanfrage. Auch er muss eine Bestandsaenderung mitbekommen - sonst lehnt die
    Editions-Validierung eine gerade importierte Regelversion als unbekannt ab."""
    from app import db as adb

    con = adb.connect(str(adb.standard_pfad()))
    try:
        vorher = adb._editionen(con)
        assert "2014" not in vorher
        assert adb._editionen(con) is adb._editionen(con)      # zweiter Aufruf aus dem Cache
        con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,"
                    "edition,seite,body_md) SELECT quelle_id,kategorie,name_de,name_en,"
                    "sprache,'2014',seite,body_md FROM eintraege LIMIT 1")
        con.commit()
        assert "2014" in adb._editionen(con), "Cache verschlaeft die neue Edition"
    finally:
        con.close()


def test_uebersetzung_erfindet_keine_identitaet(bestand):
    """'Aktionen' darf NIE als 'Reaktionen (Reactions)' bestaetigt werden - hoechstens
    als ausdruecklich unbestaetigter Aehnlichkeits-Kandidat."""
    u = ns.foliant_uebersetze_begriff("Aktionen")
    assert u["gefunden"] is False and "begriffe" not in u
    assert any(a["term_de"] == "Reaktionen" for a in u.get("aehnliche_begriffe", []))
    assert "NICHT ungeprueft" in u["hinweis"]


def test_detailabruf_waehlt_keinen_fremden_eintrag(bestand):
    """hol_regel('Aktionen') liefert den Aktionen-Eintrag - nicht die Monster-Reaktionen."""
    d = ns.foliant_hol_eintrag("regel", "Aktionen")
    assert d["gefunden"] is True and d["name_de"] == "Aktionen", d
    assert "Reaktionen" not in (d.get("anzeige_name") or "")
    # Anzeige haengt kein fuzzy-fremdes Original an ('Aktionen (Reactions)' waere falsch):
    assert "(Reactions)" not in d["anzeige_name"]


def test_suche_boostet_fuzzy_nicht_als_exakt(bestand):
    """Suche 'Aktionen': der Aktionen-Eintrag steht vor dem fuzzy-nahen Reaktionen-Eintrag."""
    s = su.foliant_suche_bestand("Aktionen")
    assert s["treffer"] and s["treffer"][0]["name_de"] == "Aktionen"


# --------------------------------------------- Klammer-Zusatz und DDB-Suffix (08.08.2026)

@pytest.fixture()
def bestand_mit_zusatz(tmp_path, monkeypatch):
    """Die gemeldete Konstellation: ein deutscher Eintrag mit Klammer-Zusatz im Namen und
    ohne `name_en`, daneben das gleichnamige Erratum mit eckigem DDB-Suffix. Das Glossar
    fuehrt - wie im echten Bestand - nur das suffixfreie Paar."""
    pfad = tmp_path / "foliant-zusatz.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet,"
        "inhaltsart) VALUES (?,?,?,?,?,?,?,?)",
        [("srd-de", "SRD 5.2.1 (Deutsch)", "de", "2024", "pdf", "CC-BY-4.0", 10,
          "regelwerk"),
         ("errata-phb-2024-en", "Player's Handbook — Errata", "en", "2024", "pdf",
          "privat", 5, "errata")])
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [(1, "regel", "Verstecken (Aktion)", None, "de", "2024", "218",
          "*Kontext: Regelglossar*\n\nMit der Verstecken-Aktion verbirgst du dich."),
         (2, "regel", None, "Hide \\[Action]", "en", "2024", "1",
          "*Kontext: Errata*\n\nDer Zustand gilt, solange du versteckt bist."),
         # Gegenprobe: Klammer-Zusatz OHNE Glossarpaar bleibt unveraendert.
         (1, "gegenstand", "Alchemistenausrüstung (50 GM)", None, "de", "2024", "70",
          "*Kontext: Ausruestung*\n\nWerkzeug des Alchemisten.")])
    # Wie im Vollbestand: 'Hide' hat ZWEI offizielle deutsche Zeilen - das Tierfell und
    # die Aktion. Der Klammer-Zusatz im Eintragsnamen unterscheidet sie, das blanke
    # 'Hide' nicht mehr. Ohne diese zweite Zeile ginge der entscheidende Fall durch:
    # Am Mac-Subset (nur eine Zeile) sah die Anzeige richtig aus, am Pi wurde
    # 'Fell (Hide)' daraus.
    con.executemany(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
        "VALUES (?,?,1,?,?)",
        [("Hide", "Verstecken", "SRD 5.2.1", "2024"),
         ("Hide", "Fell", "Spielerhandbuch", "2014")])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def test_klammer_zusatz_verhindert_das_original_nicht(bestand_mit_zusatz):
    """Gemeldeter Discord-Befund 08.08.2026: Die Kopfzeile lautete
    'Verstecken (Aktion) (Hide [Action])'.

    Der Eintrag trug kein `name_en`, und die Glossarsuche nach dem VOLLEN Namen fand
    nichts - die Zeile heisst schlicht Hide/Verstecken. Also blieb die Anzeige ohne
    Original, und das Modell nahm sich das einzige Englisch im Payload: den Namen der
    Errata-Revision samt DDB-Klammer-Artefakt."""
    d = ns.foliant_hol_eintrag("regel", "Verstecken")
    assert d["gefunden"] is True
    assert d["anzeige_name"] == "Verstecken (Hide)", d["anzeige_name"]
    # Der Zusatz ist nicht weg - er steht nur nicht mehr im Namen (B12: Einordnung).
    assert d["namenszusatz"] == "Aktion"


def test_eckiges_ddb_suffix_erreicht_die_anzeige_nie(bestand_mit_zusatz):
    """'Hide [Action]' ist Buch-Layout, kein Name (B14) - und ohne das Suffix findet das
    Glossar den Begriff ueberhaupt erst."""
    d = ns.foliant_hol_eintrag("regel", "Verstecken")
    namen = [d["anzeige_name"]] + [r["anzeige_name"] for r in d.get("revisionen", [])]
    assert namen, "Vorbedingung: die Errata-Revision muss angehaengt sein"
    for name in namen:
        assert "[" not in name and "]" not in name, name


def test_kein_anzeigename_traegt_zwei_klammergruppen(bestand_mit_zusatz):
    """Zwei Klammerpaare hintereinander sind IMMER falsch - es gibt genau ein Original je
    Name (S4).

    Dieser Test faellt ohne den Fix NICHT durch, und das ist richtig so: Die gemeldete
    Doppelklammer hat das MODELL gebaut, nicht das Werkzeug. Er sichert die naheliegende
    Fehlimplementierung ab - den Zweitversuch einzubauen und den Qualifikator trotzdem im
    Namen zu lassen, was 'Verstecken (Aktion) (Hide)' ergaebe."""
    import re

    namen = []
    for kategorie, frage in (("regel", "Verstecken"), ("gegenstand", "Alchemistenausrüstung")):
        d = ns.foliant_hol_eintrag(kategorie, frage)
        namen += [d["anzeige_name"]] + [r["anzeige_name"] for r in d.get("revisionen", [])]
    namen += [t["anzeige_name"] for t in su.foliant_suche_bestand("Verstecken")["treffer"]]
    for name in namen:
        assert not re.search(r"\)\s*\(", name), f"zwei Klammergruppen: {name!r}"


def test_zusatz_ohne_glossarpaar_bleibt_im_namen(bestand_mit_zusatz):
    """Kein Original gefunden, kein Umbau: Sonst verloeren 156 Eintraege ihren
    Qualifikator, ohne dafuer ein englisches Original zu bekommen."""
    d = ns.foliant_hol_eintrag("gegenstand", "Alchemistenausrüstung")
    assert d["anzeige_name"] == "Alchemistenausrüstung (50 GM)"
    assert "namenszusatz" not in d


def test_detail_hinweis_verbietet_das_zweite_klammerpaar(bestand_mit_zusatz):
    """Kanal 3, der zuverlaessigste: Der Detailabruf muss dem Modell sagen, dass der Name
    woertlich aus 'anzeige_name' kommt. Ohne diese Ansage holte es sich das Englisch aus
    der Errata-Revision, obwohl es im Namen laengst stand."""
    d = ns.foliant_hol_eintrag("regel", "Verstecken")
    hinweis = d.get("hinweis_darstellung", "")
    assert "anzeige_name" in hinweis and "WOERTLICH" in hinweis, hinweis
    assert "revisionen" in hinweis, "die Namensquelle muss ausdruecklich ausgeschlossen sein"
    assert "namenszusatz" in hinweis


def test_gekuerztes_suffix_raet_keine_uebersetzung(bestand_mit_zusatz):
    """Der Beinahe-Unfall vom 08.08.2026: Das Abziehen von '[Action]' macht 'Hide'
    mehrdeutig - das Glossar fuehrt Fell (Tierfell) UND Verstecken (Aktion), beide
    offiziell. `term_de` nahm die erste Zeile, und aus dem Errata-Verweis wurde
    'Fell (Hide)': eine FALSCHE Uebersetzung, schlimmer als das Artefakt davor.

    Am Mac-Subset war der Fall unsichtbar (nur eine Hide-Zeile) - er fiel erst in der
    Direktprobe am Pi-Vollbestand auf. Deshalb steht die zweite Zeile jetzt in der
    Fixture."""
    d = ns.foliant_hol_eintrag("regel", "Verstecken")
    revisionen = [r["anzeige_name"] for r in d.get("revisionen", [])]
    assert revisionen, "Vorbedingung: die Errata-Revision muss angehaengt sein"
    for name in revisionen:
        assert "Fell" not in name, f"geratene Uebersetzung: {name!r}"
        assert name == "Hide", name          # blank statt geraten (Regel 1)
