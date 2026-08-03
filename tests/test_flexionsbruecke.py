"""Singular/Plural-Brücke im Glossar (Suchbericht 28.07.2026, M5-Kurationsschleife).

Befund aus dem echten Betrieb: `Gelegenheitsangriff` — eine Kernregel, in 30 Tagen 5x
gefragt — landete jedes Mal in der Mehrdeutigkeit statt in der Antwort. Ursache: Das
Glossar führt beide Formen, aber als zwei GETRENNTE Inseln
(`Opportunity Attack`/`Gelegenheitsangriff` aus dem Kernwortschatz,
`Opportunity Attacks`/`Gelegenheitsangriffe` aus dem Spielerhandbuch). Der Zwei-Hop kommt
von der einen nie zur anderen; der Bestand führt den Eintrag im Plural, der Nutzer tippt
den Singular.

Die zwei Zusicherungen, an denen die Brücke hängt:
  1. BELEGT, nicht geraten — gepaart wird nur, wenn BEIDE Sprachen dieselbe
     Flexionsrichtung zeigen. Einseitig wäre es Stemming.
  2. Sie verschiebt NICHTS, was schon steht — die Zeilen sind Suchvarianten
     (`offiziell=0`), also unsichtbar für Anzeige und Konflikt-Gate.
"""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app import glossar as gl
from app.tools import nachschlagen as ns
from importer.import_glossar import (FLEXION_QUELLE, _ist_flexion,
                                     seed_flexionsbruecke_aus_bestand)
from tests.hilfen import SCHEMA

_SCHEMA = SCHEMA
@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    """Der reale Fall: zwei Glossar-Inseln, der Eintrag im Bestand im PLURAL."""
    pfad = tmp_path / "flexion.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
                "VALUES ('srd-de','SRD 5.2.1 (Deutsch)','de','2024','pdf',10)")
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
                "VALUES ('ddb-br-2024-en','Basic Rules (DDB)','en','2024','ddb',40)")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?, '2024',?,?)",
        [(1, "regel", "Gelegenheitsangriffe", None, "de", "208",
          "Wenn eine Kreatur deine Reichweite verlässt, kannst du reagieren."),
         # Zwei gleichnamige Abschnitte DERSELBEN Quelle - der Fall, der die
         # Mehrdeutigkeit erzeugte (SYN-P0-003).
         (2, "regel", None, "Gelegenheitsangriffe", "en", "195",
          "To make the Opportunity Attack, take a Reaction."),
         (2, "regel", None, "Gelegenheitsangriffe", "en", "196",
          "You do not provoke an Opportunity Attack when you teleport.")])
    con.executemany(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
        "VALUES (?,?,?,?,?)",
        [("Opportunity Attack", "Gelegenheitsangriff", 1, "Kernbegriff", "2024"),
         ("Opportunity Attacks", "Gelegenheitsangriffe", 1, "Spielerhandbuch", "2014")])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


@pytest.mark.parametrize("kurz,lang,erwartet", [
    ("gelegenheitsangriff", "gelegenheitsangriffe", True),
    ("opportunity attack", "opportunity attacks", True),
    ("talent", "talente", True),
    ("zombie", "zombies", True),
    ("vampir", "vampire", True),
    ("gelegenheitsangriff", "gelegenheitsangriff", False),   # identisch
    ("aktion", "reaktion", False),                            # kein Praefix
    ("hand", "handschuh", False),                             # Endung nicht flexionstypisch
])
def test_flexion_erkennt_nur_reine_verlaengerung(kurz, lang, erwartet):
    assert _ist_flexion(kurz, lang) is erwartet


def test_der_kernfall_wird_eindeutig(bestand):
    """DER Fall aus dem Suchbericht: vorher 3 Kandidaten, nachher die srd-de-Regel."""
    vorher = ns.foliant_hol_eintrag("regel", "Gelegenheitsangriff")
    assert vorher["gefunden"] is False and vorher.get("mehrdeutig") is True

    con = adb.connect(str(bestand))
    try:
        with con:
            assert seed_flexionsbruecke_aus_bestand(con) == 2      # beide Richtungen
    finally:
        con.close()

    nachher = ns.foliant_hol_eintrag("regel", "Gelegenheitsangriff")
    assert nachher["gefunden"] is True, nachher
    assert nachher["quelle_kuerzel"] == "srd-de"                   # Deutsch-first (Q2/S10)
    assert nachher["seite"] == "208"


def test_auch_die_gegenrichtung_traegt(bestand):
    """Der Nutzer kann auch den Plural tippen, wenn der Bestand den Singular fuehrt."""
    con = adb.connect(str(bestand))
    try:
        with con:
            seed_flexionsbruecke_aus_bestand(con)
        paare = {(r[0], r[1]) for r in con.execute(
            "SELECT term_en, term_de FROM glossar WHERE quelle = ?", (FLEXION_QUELLE,))}
        assert ("Opportunity Attack", "Gelegenheitsangriffe") in paare
        assert ("Opportunity Attacks", "Gelegenheitsangriff") in paare
    finally:
        con.close()


def test_nur_wenn_beide_sprachen_flektieren(tmp_path):
    """Die Beweisregel: einseitige Flexion ist Stemming und wird NICHT gepaart."""
    pfad = tmp_path / "einseitig.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle) VALUES (?,?,1,'test')",
        [("Shield", "Schild"),
         # EN flektiert (+s), DE aber nicht - verschiedene Begriffe, keine Bruecke.
         ("Shields", "Rüstung")])
    con.commit()
    con.close()
    c = adb.connect(str(pfad))
    try:
        with c:
            assert seed_flexionsbruecke_aus_bestand(c) == 0
    finally:
        c.close()


def test_bruecke_ist_suchvariante_und_veraendert_die_anzeige_nicht(bestand):
    """offiziell=0: die Suche findet, aber die ANZEIGE waehlt weiter die offizielle Form -
    sonst stuende ploetzlich der Plural als amtliche Uebersetzung da."""
    con = adb.connect(str(bestand))
    try:
        with con:
            seed_flexionsbruecke_aus_bestand(con)
        assert all(r[0] == 0 for r in con.execute(
            "SELECT offiziell FROM glossar WHERE quelle = ?", (FLEXION_QUELLE,)))
        assert gl.term_de(con, "Opportunity Attack") == ("Gelegenheitsangriff", True)
        assert gl.term_de(con, "Opportunity Attacks") == ("Gelegenheitsangriffe", True)
    finally:
        con.close()


def test_bestehende_zeilen_werden_nie_ueberschrieben(bestand):
    """_upsert wuerde `offiziell` mitschreiben - eine bestehende amtliche Zeile darf die
    Bruecke deshalb nicht anfassen."""
    con = adb.connect(str(bestand))
    try:
        vorher = {(r[0], r[1]): r[2] for r in con.execute(
            "SELECT term_en, term_de, offiziell FROM glossar")}
        with con:
            seed_flexionsbruecke_aus_bestand(con)
        for (en, de), off in vorher.items():
            jetzt = con.execute("SELECT offiziell FROM glossar WHERE term_en=? AND term_de=?",
                                (en, de)).fetchone()[0]
            assert jetzt == off, f"{en}/{de} demotiert"
    finally:
        con.close()


def test_seeder_ist_selbstbereinigend_und_idempotent(bestand):
    con = adb.connect(str(bestand))
    try:
        with con:
            erst = seed_flexionsbruecke_aus_bestand(con)
        with con:
            zweit = seed_flexionsbruecke_aus_bestand(con)
        assert erst == zweit
        assert con.execute("SELECT count(*) FROM glossar WHERE quelle = ?",
                           (FLEXION_QUELLE,)).fetchone()[0] == erst
    finally:
        con.close()


# ---------------------------------------------------------------------------------------
# Umgangssprachliche Suchvarianten (Suchbericht 03.08.2026)
#
# Die vier Bruecken-Seeder darueber beweisen ihre Paare aus der STRUKTUR. Umgangssprache
# hat keine - 'Rennen' ist dem Bestand nach nichts, es ist das Wort, das ein Spieler
# benutzt. Deshalb eine kuratierte Liste, und deshalb eine harte Schranke: eine Bruecke
# entsteht NUR, wenn die offizielle deutsche Form als Eintragsname im Bestand steht.
# ---------------------------------------------------------------------------------------

def test_umgangssprache_braucht_die_offizielle_form_im_bestand(tmp_path):
    """Die Schranke gegen Raterei: Fuehrt der Bestand das Ziel nicht, entsteht keine
    Bruecke. Sonst schickte die Suche jemanden auf eine Regel, die es hier nicht gibt -
    ein falscher Treffer ist schlimmer als ein ehrlicher Nulltreffer (B1/B2)."""
    import sqlite3

    from importer.import_glossar import seed_umgangssprache
    from tests.hilfen import SCHEMA

    pfad = tmp_path / "umgang.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
                "VALUES ('srd-de','SRD','de','2024','pdf',20)")
    # NUR 'Spurt (Aktion)' ist im Bestand - 'Gepackt' fehlt bewusst.
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,body_md) "
                "VALUES (1,'regel','Spurt (Aktion)','de','2024','Du bewegst dich.')")
    con.commit()
    n = seed_umgangssprache(con)
    zeilen = {(r[0], r[1]): r[2] for r in con.execute(
        "SELECT term_en, term_de, offiziell FROM glossar")}
    con.close()
    assert ("Dash", "Rennen") in zeilen and ("Dash", "Sprinten") in zeilen
    assert ("Grappled", "Umklammern") not in zeilen, \
        "Bruecke ohne Ziel im Bestand angelegt - genau das soll die Schranke verhindern"
    assert n == 2
    assert all(off == 0 for off in zeilen.values()), \
        "Umgangssprache muss offiziell=0 sein, sonst konkurriert sie mit der Buchform"


def test_umgangssprache_ueberschreibt_keine_offizielle_zeile(tmp_path):
    """Ein Upsert auf eine bestehende Zeile wuerde ihre Offizialitaet kippen - dieselbe
    Zusage wie bei der Flexions-Bruecke."""
    import sqlite3

    from importer.import_glossar import seed_umgangssprache
    from tests.hilfen import SCHEMA

    pfad = tmp_path / "umgang2.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
                "VALUES ('srd-de','SRD','de','2024','pdf',20)")
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,body_md) "
                "VALUES (1,'regel','Spurt (Aktion)','de','2024','Du bewegst dich.')")
    con.execute("INSERT INTO glossar (term_en,term_de,offiziell) VALUES ('Dash','Rennen',1)")
    con.commit()
    seed_umgangssprache(con)
    off = con.execute("SELECT offiziell FROM glossar WHERE term_de='Rennen'").fetchone()[0]
    con.close()
    assert off == 1, "bestehende Zeile wurde ueberschrieben"


def test_umgangssprache_ist_wiederholbar(tmp_path):
    """Zweimal laufen darf keine Dubletten erzeugen - die Kette laeuft bei jedem Import."""
    import sqlite3

    from importer.import_glossar import seed_umgangssprache
    from tests.hilfen import SCHEMA

    pfad = tmp_path / "umgang3.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
                "VALUES ('srd-de','SRD','de','2024','pdf',20)")
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,body_md) "
                "VALUES (1,'regel','Gepackt (Zustand)','de','2024','Deine Bewegungsrate ist 0.')")
    con.commit()
    seed_umgangssprache(con)
    seed_umgangssprache(con)
    n = con.execute("SELECT count(*) FROM glossar WHERE term_de='Umklammern'").fetchone()[0]
    con.close()
    assert n == 1, f"{n} Zeilen statt einer"
