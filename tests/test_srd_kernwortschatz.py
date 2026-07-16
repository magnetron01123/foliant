"""Tests fuer die SRD-Kernwortschatz-Bruecke (importer/srd_kernwortschatz.py).

Zwei Ebenen: (1) die reinen Parser gegen Statblock-/Tabellen-Schnipsel; (2) ein Integrationslauf
gegen eine winzige synthetische DB, der beweist, dass die Herleitung Fertigkeit/Groesse/Typ
strukturell UND ohne zu raten paart - inklusive der Fallen (kippende Reihenfolge bei
mehrgroessigen Kreaturen, Ligaturdefekt 'Pfanze', Ausschlussverfahren fuer Fertigkeiten ohne
eindeutigen Bonus)."""
from __future__ import annotations

import sqlite3

import pytest

from importer import srd_kernwortschatz as kw


# --- reine Parser ------------------------------------------------------------

def test_skills_mit_bonus_toleriert_markdown_escape():
    assert kw._skills_mit_bonus(r"History \+12, Perception \+10") == {"History": 12, "Perception": 10}
    assert kw._skills_mit_bonus("Stealth +6, Perception +4") == {"Stealth": 6, "Perception": 4}


def test_segment_schneidet_am_naechsten_feld():
    # srd-de: die Fertigkeitszeile laeuft in **Sinne**/**Sprachen** weiter - nicht mitnehmen
    zeile = "**Fertigkeiten** Geschichte +12, Wahrnehmung +10 **Sinne** Dunkelsicht 36 m"
    assert kw._segment(zeile, "Fertigkeiten").strip() == "Geschichte +12, Wahrnehmung +10"
    # open5e: '·'-getrennt
    z2 = "**Saves:** Str +5 · **Skills:** History +12, Perception +10 · **Senses:** Darkvision"
    assert kw._segment(z2, "Skills").strip() == "History +12, Perception +10"


def test_groesse_und_typ_beide_formate():
    assert kw._groesse_und_typ("_Mittelgroße Monstrosität, neutral böse_") == ("Mittelgroße", "Monstrosität")
    assert kw._groesse_und_typ("**Type:** Large Aberration · **CR:** 10") == ("Large", "Aberration")


def test_groesse_kippt_bei_mehrgroessigen_kreaturen():
    # EN 'Medium or Small' <-> DE 'Kleiner oder mittelgroßer': die Reihenfolge kippt zwischen den
    # Sprachen -> die GROESSE muss None sein (nur der Typ bleibt gueltig), sonst paart man falsch.
    assert kw._groesse_und_typ("Medium or Small Humanoid, Neutral") == (None, "Humanoid")
    assert kw._groesse_und_typ("_Kleiner oder mittelgroßer Humanoide, neutral_") == (None, "Humanoide")


def test_lemma_bindet_flexion_und_ligaturdefekt():
    assert kw._lemma_fuer("Mittelgroße", {"Mittelgroß", "Klein"}) == "Mittelgroß"
    assert kw._lemma_fuer("Kleines", {"Klein", "Groß"}) == "Klein"
    # Die srd-de-Typentabelle druckt real 'Pfanze' (fl-Ligaturverlust); der saubere Statblock
    # sagt 'Pflanze' - beide muessen sich finden:
    assert kw._lemma_fuer("Pflanze", {"Pfanze"}) == "Pfanze"


def test_ist_skillname_filtert_rausch():
    assert kw._ist_skillname("Performance")
    assert kw._ist_skillname("Animal Handling")
    assert not kw._ist_skillname("Arcana or Religion")   # Kombi
    assert not kw._ist_skillname("hill")                 # Kleinschreib-Rauschen (Riesen-Subtyp)


# --- Integrationslauf gegen eine synthetische DB -----------------------------

def _mini_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE quellen (id INTEGER PRIMARY KEY, kuerzel TEXT, prioritaet INT);
        CREATE TABLE eintraege (id INTEGER PRIMARY KEY, quelle_id INT, kategorie TEXT,
            name_de TEXT, name_en TEXT, sprache TEXT, edition TEXT, seite TEXT, body_md TEXT);
        CREATE TABLE glossar (id INTEGER PRIMARY KEY AUTOINCREMENT, term_en TEXT, term_de TEXT,
            offiziell INT, quelle TEXT, edition_quelle TEXT, seite TEXT,
            UNIQUE(term_en, term_de));
    """)
    con.execute("INSERT INTO quellen VALUES (1,'srd-de',10),(2,'open5e',50),(3,'ddb-phb-2024-en',60)")
    # Attributs-Bruecke (fuer das Ausschlussverfahren): die Attributsnamen als Glossarzeilen
    for en, de in [("Strength", "Stärke"), ("Dexterity", "Geschicklichkeit"),
                   ("Intelligence", "Intelligenz"), ("Wisdom", "Weisheit")]:
        con.execute("INSERT INTO glossar (term_en,term_de,offiziell,quelle) VALUES (?,?,1,'x')", (en, de))

    # Fertigkeiten-Tabelle (srd-de) - liefert die deutschen Grundformen + Attribut-Spalte
    fert_tab = ("###### **Fertigkeiten**\n"
                "|**Fertigkeit**|**Attribut**|**Beispielanwendungen**|\n|---|---|---|\n"
                "|Akrobatik|Geschicklichkeit|...|\n|Heimlichkeit|Geschicklichkeit|...|\n"
                "|Fingerfertigkeit|Geschicklichkeit|...|\n|Wahrnehmung|Weisheit|...|\n"
                "|Motiv erkennen|Weisheit|...|\n")
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,body_md) "
                "VALUES (1,'regel','Fertigkeiten','de',?)", (fert_tab,))

    # Groessen als GEORDNETE Aufzaehlung (beide Sprachen) - liefert die Groessen-Grundformen
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,body_md) VALUES "
                "(1,'regel','Groessen','de','... Winzig, Klein, Mittelgroß, Groß, Riesig oder Gigantisch ...')")
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_en,sprache,body_md) VALUES "
                "(3,'regel','Sizes','en','... Tiny, Small, Medium, Large, Huge, or Gargantuan ...')")
    # Kreaturentyp-Tabelle (srd-de) - liefert die deutschen Typ-Grundformen
    typ_tab = ("Das Spiel enthaelt die folgende Kreaturentypen im Spiel:\n"
               "|Aberration|Humanoide|Schlick|\n|---|---|---|\n"
               "|Celestisch|Konstrukt|Tier|\n|Drache|Monstrosität|Unhold|\n")
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,body_md) "
                "VALUES (1,'regel','Kreaturentyp','de',?)", (typ_tab,))

    # zwei strukturgleiche Monster (de + en), Boni eindeutig -> direkte Fertigkeitspaare
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_en,sprache,body_md) VALUES "
                "(2,'monster','Spy','en',?)",
                ("**Type:** Medium Humanoid · **CR:** 1\n**AC:** 12 **HP:** 27\n"
                 "**Abilities:** STR 10 (+0), DEX 15 (+2), CON 10 (+0), INT 12 (+1), WIS 14 (+2), CHA 16 (+3)\n"
                 "**Skills:** Perception +4, Stealth +6, Sleight of Hand +8",))
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,body_md) VALUES "
                "(1,'monster','Spion','de',?)",
                ("_Mittelgroßer Humanoide, neutral_\n**RK** 12 **TP** 27\n"
                 "**Attribute** STÄ 10 (+0), GES 15 (+2), KON 10 (+0), INT 12 (+1), WIS 14 (+2), CHA 16 (+3)\n"
                 "**Fertigkeiten** Wahrnehmung +4, Heimlichkeit +6, Fingerfertigkeit +8",))
    return con


@pytest.fixture()
def monster_bruecke(monkeypatch):
    """Die Monster-Struktur-Bruecke ist anderswo getestet; hier injizieren wir das Paar
    (Spy<->Spion) direkt, damit dieser Test die KERNWORTSCHATZ-Herleitung isoliert prueft."""
    import importer.import_glossar as ig
    monkeypatch.setattr(ig, "_finde_monster_paare", lambda con: [("Spy", "Spion", ())])


def test_integration_paart_strukturell(monster_bruecke):
    con = _mini_db()
    paare, _verworfen = kw.finde_kernbegriffe(con, min_belege=1)
    als_dict = {(en, kat): de for en, de, kat, _n in paare}

    # Direkt ueber eindeutige Boni:
    assert als_dict[("Perception", "fertigkeit")] == "Wahrnehmung"
    assert als_dict[("Stealth", "fertigkeit")] == "Heimlichkeit"
    # Sleight of Hand: Bonus +8 ist eindeutig -> ebenfalls direkt
    assert als_dict[("Sleight of Hand", "fertigkeit")] == "Fingerfertigkeit"
    # Groesse aus der Kopfzeile (Medium/Mittelgroßer):
    assert als_dict[("Medium", "groesse")] == "Mittelgroß"
    # Typ:
    assert als_dict[("Humanoid", "kreaturentyp")] == "Humanoide"


def test_integration_raet_bei_mehrdeutigem_bonus_nicht(monster_bruecke):
    con = _mini_db()
    # Zwei Fertigkeiten mit DEMSELBEN Bonus -> nicht zuordenbar, darf NICHT geraten werden.
    con.execute("UPDATE eintraege SET body_md=? WHERE name_en='Spy'",
                ("**Type:** Medium Humanoid\n**Skills:** Perception +5, Stealth +5",))
    con.execute("UPDATE eintraege SET body_md=? WHERE name_de='Spion'",
                ("_Mittelgroßer Humanoide_\n**Fertigkeiten** Wahrnehmung +5, Heimlichkeit +5",))
    paare, _ = kw.finde_kernbegriffe(con, min_belege=1)
    fert = {en: de for en, de, kat, _n in paare if kat == "fertigkeit"}
    # Kein Fertigkeitspaar aus diesem mehrdeutigen Statblock (Groesse/Typ bleiben aber gueltig):
    assert "Perception" not in fert and "Stealth" not in fert
    assert ("Medium", "groesse") in {(en, kat) for en, _de, kat, _n in paare}
