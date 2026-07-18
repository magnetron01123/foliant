"""Struktur-Abgleich srd-de <-> ddb-br-2024-en fuer Klassenmerkmalsnamen (synthetische DB).

Die echten Quellen liegen nur auf dem Pi (die Mac-DB ist ein Subset ohne ddb-br-2024-en);
die Fixtures bilden die verifizierten Formate nach: srd-de '###### **N. Stufe: Name**' +
'**_Sub:_**', ddb-br 'Level N: Name'-Eintraege mit '*Kontext: X > X Features*' + '***Sub.***'.
"""
from __future__ import annotations

import sqlite3

import pytest

from importer.srd_klassenmerkmale import QUELLE, apostroph_varianten, finde_paare


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE quellen (id INTEGER PRIMARY KEY, kuerzel TEXT)")
    con.execute("CREATE TABLE eintraege (id INTEGER PRIMARY KEY, quelle_id INT, "
                "kategorie TEXT, name_de TEXT, name_en TEXT, body_md TEXT, "
                "edition TEXT DEFAULT '2024')")
    con.execute("CREATE TABLE glossar (id INTEGER PRIMARY KEY, term_en TEXT, term_de TEXT, "
                "offiziell INT, quelle TEXT, edition_quelle TEXT, seite TEXT)")
    con.execute("INSERT INTO quellen VALUES (1, 'srd-de'), (2, 'ddb-br-2024-en')")
    con.execute("INSERT INTO glossar (term_en, term_de, offiziell) VALUES ('Monk', 'Mönch', 1)")
    return con


_DE_BODY = """*Kontext: Klassen > Mönch*

Einleitung.

###### **2. Stufe: Mönchsfokus**

Text mit Sub-Features:

**_Schlaghagel:_** Zwei waffenlose Angriffe.

**_Windschritt:_** Spurt als Bonusaktion.

###### **3. Stufe: Angriffe umleiten**

Reaktion gegen Angriffe.

###### **3. Stufe: Mönch-Unterklasse**

Du erhältst eine Unterklasse.

###### **5. Stufe: Betäubender Schlag**

Einmal pro Zug.
"""

_EN_FOKUS = ("*Kontext: Monk > Monk Features*\n\nIntro text.\n\n"
             "***Flurry of Blows.*** Two Unarmed Strikes.\n\n"
             "***Step of the Wind.*** Dash as a Bonus Action.")
_EN_DEFLECT = "*Kontext: Monk > Monk Features*\n\nTake a Reaction."
_EN_SUBCLASS = "*Kontext: Monk > Monk Features*\n\nYou gain a subclass."
_EN_STUN = "*Kontext: Monk > Monk Features*\n\nOnce per turn."


def _fuelle(con, en_eintraege):
    con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_de, body_md) "
                "VALUES (1, 'klasse', 'Klassenmerkmale des Mönchs', ?)", (_DE_BODY,))
    for name_en, body in en_eintraege:
        con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_en, body_md) "
                    "VALUES (2, 'klasse', ?, ?)", (name_en, body))


def test_paart_merkmale_und_subfeatures_ueber_stufe_und_position():
    con = _db()
    _fuelle(con, [("Level 2: Monk’s Focus", _EN_FOKUS),
                  ("Level 3: Deflect Attacks", _EN_DEFLECT),
                  ("Level 3: Monk Subclass", _EN_SUBCLASS),
                  ("Level 5: Stunning Strike", _EN_STUN)])
    paare, report = finde_paare(con)
    assert ("Monk’s Focus", "Mönchsfokus") in paare
    assert ("Deflect Attacks", "Angriffe umleiten") in paare
    assert ("Monk Subclass", "Mönch-Unterklasse") in paare
    assert ("Stunning Strike", "Betäubender Schlag") in paare
    # Sub-Features des gepaarten Merkmals (Reihenfolge-zip)
    assert ("Flurry of Blows", "Schlaghagel") in paare
    assert ("Step of the Wind", "Windschritt") in paare
    assert report == []


def test_mehrere_merkmale_je_stufe_keine_kreuzpaarung():
    """srd-de sortiert je Stufe alphabetisch DEUTSCH, DDB alphabetisch ENGLISCH - reine
    Positions-Paarung erzeugte real 'Extra Attack -> Betäubender Schlag' (Pi-Lauf
    17.07.2026). Ein belegtes Glossar-Paar fixiert die Zuordnung, der Rest folgt per
    Ausschlussprinzip."""
    from app import glossar as g
    con = _db()
    # Stufe 5 im DE-Body: alphabetisch deutsch (Betäubender vor Zusätzlicher);
    # EN-Eintraege: alphabetisch englisch (Extra Attack vor Stunning Strike).
    de_body = ("*Kontext: Klassen > Mönch*\n\n"
               "###### **5. Stufe: Betäubender Schlag**\n\nText.\n\n"
               "###### **5. Stufe: Zusätzlicher Angriff**\n\nText.\n")
    con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_de, body_md) "
                "VALUES (1, 'klasse', 'Klassenmerkmale des Mönchs', ?)", (de_body,))
    for name_en in ("Level 5: Extra Attack", "Level 5: Stunning Strike"):
        con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_en, body_md) "
                    "VALUES (2, 'klasse', ?, ?)", (name_en, _EN_STUN))
    # Belegtes Paar (wie real via 'Prinzen der Apokalypse'):
    con.execute("INSERT INTO glossar (term_en, term_de, offiziell) "
                "VALUES ('Stunning Strike', 'Betäubender Schlag', 1)")
    g._GLOSSAR_CACHE.clear()
    try:
        paare, report = finde_paare(con)
    finally:
        g._GLOSSAR_CACHE.clear()
    assert ("Stunning Strike", "Betäubender Schlag") in paare
    assert ("Extra Attack", "Zusätzlicher Angriff") in paare       # Ausschlussprinzip
    assert not any(en == "Extra Attack" and de == "Betäubender Schlag" for en, de in paare)


def test_mehrdeutige_stufe_ohne_beleg_wird_verworfen():
    """>=3 Merkmale je Stufe ohne belegte Glossar-Paare: keine eindeutige Zuordnung
    moeglich -> verwerfen statt raten."""
    from app import glossar as g
    con = _db()
    de_body = ("*Kontext: Klassen > Mönch*\n\n"
               "###### **2. Stufe: Alpha**\n\nText.\n\n"
               "###### **2. Stufe: Beta**\n\nText.\n\n"
               "###### **2. Stufe: Gamma**\n\nText.\n")
    con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_de, body_md) "
                "VALUES (1, 'klasse', 'Klassenmerkmale des Mönchs', ?)", (de_body,))
    for name_en in ("Level 2: One", "Level 2: Two", "Level 2: Three"):
        con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_en, body_md) "
                    "VALUES (2, 'klasse', ?, ?)", (name_en, _EN_STUN))
    g._GLOSSAR_CACHE.clear()
    try:
        paare, report = finde_paare(con)
    finally:
        g._GLOSSAR_CACHE.clear()
    assert paare == []
    assert any("nicht eindeutig" in z for z in report)


def test_klassenbruecke_prueft_existenz_der_en_klasse():
    """'Magier' hat die Glossar-Kandidaten 'Mage' UND 'Wizard' - nur der Kandidat mit
    echten Level-Eintraegen zaehlt (real: 'Mage' gewann und der Magier fiel aus)."""
    from app import glossar as g
    con = _db()
    con.execute("DELETE FROM glossar")
    con.execute("INSERT INTO glossar (term_en, term_de, offiziell) VALUES "
                "('Mage', 'Magier', 1), ('Wizard', 'Magier', 1)")
    de_body = ("*Kontext: Klassen > Magier*\n\n"
               "###### **1. Stufe: Zauberbuch**\n\nText.\n")
    con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_de, body_md) "
                "VALUES (1, 'klasse', 'Klassenmerkmale des Magiers', ?)", (de_body,))
    con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_en, body_md) VALUES "
                "(2, 'klasse', 'Level 1: Spellbook', '*Kontext: Wizard > Wizard Features*\n\nText.')")
    g._GLOSSAR_CACHE.clear()
    try:
        paare, report = finde_paare(con)
    finally:
        g._GLOSSAR_CACHE.clear()
    assert ("Spellbook", "Zauberbuch") in paare


def test_belegtes_subfeature_identifiziert_eltern_merkmal():
    """Mönch Stufe 2 (real): 3 Merkmale, nur 'Unarmored Movement' direkt belegt. Das
    belegte SUB-Paar Schlaghagel<->Flurry of Blows identifiziert 'Mönchsfokus' <->
    'Monk's Focus'; der Rest ('Unglaublicher Stoffwechsel') folgt per Ausschluss."""
    from app import glossar as g
    con = _db()
    de_body = ("*Kontext: Klassen > Mönch*\n\n"
               "###### **2. Stufe: Mönchsfokus**\n\nText.\n\n"
               "**_Schlaghagel:_** Zwei Angriffe.\n\n"
               "###### **2. Stufe: Ungerüstete Bewegung**\n\nText.\n\n"
               "###### **2. Stufe: Unglaublicher Stoffwechsel**\n\nText.\n")
    con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_de, body_md) "
                "VALUES (1, 'klasse', 'Klassenmerkmale des Mönchs', ?)", (de_body,))
    fokus_body = ("*Kontext: Monk > Monk Features*\n\nText.\n\n"
                  "***Flurry of Blows.*** Two strikes.")
    for name_en, body in (("Level 2: Monk’s Focus", fokus_body),
                          ("Level 2: Unarmored Movement", _EN_STUN),
                          ("Level 2: Uncanny Metabolism", _EN_STUN)):
        con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_en, body_md) "
                    "VALUES (2, 'klasse', ?, ?)", (name_en, body))
    con.execute("INSERT INTO glossar (term_en, term_de, offiziell) VALUES "
                "('Flurry of Blows', 'Schlaghagel', 1), "
                "('Unarmored Movement', 'Ungerüstete Bewegung', 1)")
    g._GLOSSAR_CACHE.clear()
    try:
        paare, report = finde_paare(con)
    finally:
        g._GLOSSAR_CACHE.clear()
    assert ("Monk’s Focus", "Mönchsfokus") in paare
    assert ("Unarmored Movement", "Ungerüstete Bewegung") in paare
    assert ("Uncanny Metabolism", "Unglaublicher Stoffwechsel") in paare   # Ausschluss
    assert report == []


def test_teilfixierung_bleibt_bei_unaufloesbarem_rest():
    """Ein sicheres (Subclass-Anker-)Paar bleibt erhalten, auch wenn der Rest der Stufe
    nicht aufloesbar ist - verworfen wird nur der Rest. Genitiv-Stamm inklusive
    ('Barbaren-Unterklasse' bei klasse_de 'Barbar')."""
    from app import glossar as g
    con = _db()
    con.execute("INSERT INTO glossar (term_en, term_de, offiziell) VALUES "
                "('Barbarian', 'Barbar', 1)")
    de_body = ("*Kontext: Klassen > Barbar*\n\n"
               "###### **3. Stufe: Barbaren-Unterklasse**\n\nText.\n\n"
               "###### **3. Stufe: Alpha**\n\nText.\n\n"
               "###### **3. Stufe: Beta**\n\nText.\n")
    con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_de, body_md) "
                "VALUES (1, 'klasse', 'Klassenmerkmale des Barbaren', ?)", (de_body,))
    for name_en in ("Level 3: Barbarian Subclass", "Level 3: One", "Level 3: Two"):
        con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_en, body_md) VALUES "
                    "(2, 'klasse', ?, '*Kontext: Barbarian > Barbarian Features*\n\nText.')",
                    (name_en,))
    g._GLOSSAR_CACHE.clear()
    try:
        paare, report = finde_paare(con)
    finally:
        g._GLOSSAR_CACHE.clear()
    assert ("Barbarian Subclass", "Barbaren-Unterklasse") in paare
    assert len(paare) == 1                                   # Alpha/Beta nicht geraten
    assert any("nicht eindeutig" in z for z in report)


def test_ungleiche_anzahl_je_stufe_wird_verworfen():
    con = _db()
    _fuelle(con, [("Level 2: Monk’s Focus", _EN_FOKUS),
                  ("Level 3: Deflect Attacks", _EN_DEFLECT),   # DE hat ZWEI Stufe-3-Merkmale
                  ("Level 5: Stunning Strike", _EN_STUN)])
    paare, report = finde_paare(con)
    assert not any(de == "Angriffe umleiten" for _, de in paare)   # Stufe 3 verworfen
    assert ("Stunning Strike", "Betäubender Schlag") in paare      # andere Stufen unberuehrt
    assert any("Stufe 3" in z for z in report)


def test_subclass_feature_verweise_zaehlen_nicht():
    """EN-Eintraege 'Level N: Subclass Feature' sind reine Verweise - sie duerfen die
    Anzahl-Pruefung nicht kippen und nie als Begriff geseedet werden."""
    con = _db()
    _fuelle(con, [("Level 2: Monk’s Focus", _EN_FOKUS),
                  ("Level 3: Deflect Attacks", _EN_DEFLECT),
                  ("Level 3: Monk Subclass", _EN_SUBCLASS),
                  ("Level 3: Subclass Feature", _EN_SUBCLASS),
                  ("Level 5: Stunning Strike", _EN_STUN)])
    paare, report = finde_paare(con)
    assert ("Deflect Attacks", "Angriffe umleiten") in paare
    assert not any(en == "Subclass Feature" for en, _ in paare)


def test_ohne_klassenbruecke_wird_klasse_verworfen():
    con = _db()
    con.execute("DELETE FROM glossar")
    from app import glossar as g
    g._GLOSSAR_CACHE.clear()
    try:
        _fuelle(con, [("Level 5: Stunning Strike", _EN_STUN)])
        paare, report = finde_paare(con)
        assert paare == []
        assert any("keine EN-Klasse" in z for z in report)
    finally:
        g._GLOSSAR_CACHE.clear()


def test_spezies_subfeatures_ohne_reihenfolge_annahme():
    """Elf: 4 von 5 Subs belegt -> das fuenfte per Ausschluss. Zwerg: alphabetische
    UMSORTIERUNG der Uebersetzung ('Steingespür' Pos 2 <-> 'Stonecunning' Pos 4) darf
    keine Kreuzpaare erzeugen - Unbelegtes wird verworfen, nie positionsgeraten."""
    from app import glossar as g
    from importer.srd_klassenmerkmale import finde_container_sub_paare

    con = _db()
    con.execute("INSERT INTO glossar (term_en, term_de, offiziell) VALUES "
                "('Elf', 'Elf', 1), ('Dwarf', 'Zwerg', 1), "
                "('Darkvision', 'Dunkelsicht', 1), ('Trance', 'Trance', 1), "
                "('Keen Senses', 'Scharfe Sinne', 1), ('Fey Ancestry', 'Feenblut', 1)")
    elf_de = ("*Kontext: Spezies*\n\n**_Dunkelsicht:_** X. **_Elfische Abstammung:_** X. "
              "**_Feenblut:_** X. **_Scharfe Sinne:_** X. **_Trance:_** X.")
    # DDB chunkt Intro und Merkmale getrennt: die ***Sub.***-Koepfe stehen im
    # SEPARATEN '<Name> Traits'-Eintrag, der Haupteintrag ist nur Fluff.
    elf_en_intro = "*Kontext: Species*\n\nElves are magical people."
    elf_en_traits = ("*Kontext: Species > Elf*\n\n***Darkvision.*** X. "
                     "***Elven Lineage.*** X. ***Fey Ancestry.*** X. "
                     "***Keen Senses.*** X. ***Trance.*** X.")
    # Zwerg: nur Dunkelsicht belegt; die drei uebrigen sind je Sprache anders sortiert.
    zwerg_de = ("*Kontext: Spezies*\n\n**_Dunkelsicht:_** X. **_Steingespür:_** X. "
                "**_Zwergische Unverwüstlichkeit:_** X. **_Zwergische Zähigkeit:_** X.")
    zwerg_en = ("*Kontext: Species*\n\n***Darkvision.*** X. ***Dwarven Resilience.*** X. "
                "***Dwarven Toughness.*** X. ***Stonecunning.*** X.")
    con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_de, body_md) VALUES "
                "(1, 'spezies', 'Elf', ?), (1, 'spezies', 'Zwerg', ?)", (elf_de, zwerg_de))
    con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_en, body_md) VALUES "
                "(2, 'spezies', 'Elf', ?), (2, 'spezies', 'Elf Traits', ?), "
                "(2, 'spezies', 'Dwarf', ?)", (elf_en_intro, elf_en_traits, zwerg_en))
    g._GLOSSAR_CACHE.clear()
    try:
        paare, report = finde_container_sub_paare(con, "spezies")
    finally:
        g._GLOSSAR_CACHE.clear()
    assert ("Fey Ancestry", "Feenblut") in paare
    assert ("Elven Lineage", "Elfische Abstammung") in paare       # Ausschlussprinzip
    assert ("Darkvision", "Dunkelsicht") in paare
    # Zwerg: KEIN Kreuzpaar - die drei unbelegten werden verworfen
    assert not any(en == "Dwarven Resilience" for en, _ in paare)
    assert not any(de == "Steingespür" for _, de in paare)
    assert any("Zwerg" in z for z in report)


def test_apostroph_varianten():
    assert apostroph_varianten("Monk’s Focus") == ["Monk's Focus", "Monk’s Focus"]
    assert apostroph_varianten("Deflect Attacks") == ["Deflect Attacks"]


def test_seed_schreibt_offizielle_zeilen_selbstbereinigend():
    from importer.import_glossar import seed_klassenmerkmale_aus_bestand
    con = _db()
    _fuelle(con, [("Level 2: Monk’s Focus", _EN_FOKUS),
                  ("Level 5: Stunning Strike", _EN_STUN)])
    con.execute("CREATE UNIQUE INDEX gidx ON glossar(term_en, term_de)")
    n = seed_klassenmerkmale_aus_bestand(con)
    assert n >= 4   # Fokus (2 Apostroph-Formen) + Schlaghagel + Windschritt + Stunning Strike
    z = con.execute("SELECT offiziell, quelle FROM glossar WHERE term_en = 'Stunning Strike'").fetchone()
    assert z["offiziell"] == 1 and z["quelle"] == QUELLE
    beide = {r[0] for r in con.execute(
        "SELECT term_en FROM glossar WHERE term_de = 'Mönchsfokus'")}
    assert beide == {"Monk's Focus", "Monk’s Focus"}
    # Selbst-bereinigend: zweiter Lauf verdoppelt nichts
    n2 = seed_klassenmerkmale_aus_bestand(con)
    assert n2 == n
    anz = con.execute("SELECT count(*) FROM glossar WHERE quelle = ?", (QUELLE,)).fetchone()[0]
    assert anz == len({r for r in con.execute("SELECT term_en, term_de FROM glossar WHERE quelle = ?", (QUELLE,))})
