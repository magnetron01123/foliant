"""Committbare Extractor-Tests mit SYNTHETISCHEN Fixtures (Auftrag §13.1).

Keine privaten Binaerdateien, keine echten Charakterdaten im Git: die DDB-artigen
Widget-PDFs werden pro Testlauf erzeugt - inklusive AcroForm-Entfernung, damit der
verwaiste-Widget-Pfad (kein Catalog-/AcroForm, wie beim echten DDB-Export) getestet wird.

Die Verlustfreiheit gegen das echte Golden-Sample prueft der (gitignorierte) private
Test tests/test_charakterbogen_ddb_golden_privat.py.
"""
from __future__ import annotations

import fitz
import pytest

from app.charakterbogen import ddb_pdf
from app.charakterbogen.ddb_pdf import DDBFormatFehler, _verbinde_fragmente, extrahiere


# --- Fixture-Bau -------------------------------------------------------------

def baue_ddb_pdf(seiten: dict[int, dict[str, str]], seitenzahl: int = 5,
                 contents_felder: dict[int, dict[str, str]] | None = None) -> bytes:
    """Erzeugt ein DDB-artiges PDF: benannte Text-Widgets, danach AcroForm entfernt
    (verwaiste Widgets wie beim echten Export). `contents_felder` legt den Wert NUR in
    /Contents (nicht /V) ab, um den KONZEPT-§4.1-Fallback zu ueben."""
    doc = fitz.open()
    for pno in range(seitenzahl):
        page = doc.new_page(width=612, height=792)
        y = 36.0
        for name, wert in seiten.get(pno, {}).items():
            w = fitz.Widget()
            w.field_name = name
            w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            w.field_value = wert
            w.rect = fitz.Rect(36, y, 336, y + 16)
            y += 18
            page.add_widget(w)
        for name, wert in (contents_felder or {}).get(pno, {}).items():
            w = fitz.Widget()
            w.field_name = name
            w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            w.field_value = ""
            w.rect = fitz.Rect(36, y, 336, y + 16)
            y += 18
            added = page.add_widget(w)
            doc.xref_set_key(added.xref, "Contents", f"({wert})")  # Wert nur in /Contents
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm", "null")  # -> verwaiste Widgets
    return doc.tobytes()


def _unabhaengig_lesen(doc: fitz.Document) -> set[tuple[int, str, str]]:
    """Unabhaengige Referenz-Lesung, die die Filter von lese_widgets (Contents-Fallback,
    'Off' nur bei Ankreuzwidgets) EXAKT spiegelt - sonst waere der Vergleich unfair."""
    s: set[tuple[int, str, str]] = set()
    for pno, page in enumerate(doc):
        for w in page.widgets() or []:
            wert = w.field_value
            if wert in (None, ""):
                t, v = doc.xref_get_key(w.xref, "Contents")
                if t == "string":
                    wert = v
            if wert in (None, ""):
                continue
            if wert == "Off" and (w.field_type_string or "").lower() in ("checkbox", "radiobutton", "button"):
                continue
            if w.field_name:
                s.add((pno, w.field_name, wert))
    return s


# Repraesentativer Beispielcharakter. FeaturesTraits brechen bewusst an Wortgrenzen um
# (D&D Beyond verschluckt dort das Leerzeichen) - der Smart-Join muss es rekonstruieren.
BEISPIEL: dict[int, dict[str, str]] = {
    0: {
        "CharacterName": "Testheld", "PLAYER NAME": "Spieler1",
        "CLASS  LEVEL": "Monk 5", "RACE": "Human", "BACKGROUND": "Mist Wanderer",
        "EXPERIENCE POINTS": "(Milestone)",
        "STR": "8", "STRmod": "-1", "ST Strength": "+2", "StrProf": "•",
        "DEX": "18", "DEXmod ": "+4", "ST Dexterity": "+7", "DexProf": "•",
        "CON": "14", "CONmod": "+2", "ST Constitution": "+2",
        "INT": "8", "INTmod": "-1", "ST Intelligence": "-1",
        "WIS": "16", "WISmod": "+3", "ST Wisdom": "+3",
        "CHA": "10", "CHamod": "+0", "ST Charisma": "+0",
        "Acrobatics": "+7", "AcrobaticsProf": "P", "AcrobaticsMod": "DEX",
        "Stealth ": "+7", "StealthProf": "P", "StealthMod": "DEX",
        "Arcana": "-1", "ArcanaMod": "INT",
        "AC": "17", "MaxHP": "38", "TempHP": "--", "Total": "5d8",
        "Init": "+4", "Speed": "40 ft. (Walking)", "ProfBonus": "+3",
        "Passive1": "16", "Passive2": "16", "Passive3": "9",
        "AdditionalSenses": "Darkvision 60 ft.",
        # Vier Kategorien inkl. zusammengesetztem 'Crossbow, Hand' (= Hand Crossbow) - darf
        # NICHT am Komma zerrissen werden.
        "ProficienciesLang": "=== ARMOR === \nLight Armor \n\n=== WEAPONS === \n"
                             "Crossbow, Hand, Scimitar, Shortsword \n\n=== TOOLS === \n"
                             "Thieves' Tools \n\n=== LANGUAGES === \nCommon, Elvish",
        "Actions1": "=== ACTIONS === \nStandard Actions \n     Attack, Dash, Dodge",
        "Actions2": "=== BONUS ACTIONS === \nFlurry of Blows",
        "Wpn Name": "Unarmed Strike", "Wpn1 AtkBonus": "+7", "Wpn1 Damage": "1d8+4 Bludgeoning",
        "Wpn Name 2": "Dagger", "Wpn2 AtkBonus": "+6", "Wpn2 Damage": "1d4+4 Piercing",
        "MysteryField": "unbekannter Wert",
    },
    1: {
        "CharacterName2": "Testheld", "CLASS  LEVEL2": "Monk 5",
        # Bruch an Wortgrenze: '... the same type' | 'dealt by ...'
        "FeaturesTraits1": "=== MONK FEATURES === \n\n* Martial Arts • PHB-2024 101 \nYou deal the same type",
        "FeaturesTraits2": "dealt by the attack. \n\n* Deflect Attacks • PHB-2024 102 \n   | 1 Reaction",
        "CP": "0", "SP": "0", "EP": "0", "GP": "80", "PP": "0",
        "Weight Carried": "17 lb.",
        "Eq Name0": "Rope", "Eq Qty0": "1", "Eq Weight0": "5 lb.",
    },
    2: {
        "CharacterName3": "Testheld",
        # '*Note:'-Zeile ohne '•' darf KEIN eigenes Merkmal werden.
        "FeaturesTraits3": "=== FEATS === \n\n* Grappler • PHB-2024 204 \nPunch and Grab. "
                           "\n*Note: reroll ones and twos \nMore grappler text.",
    },
    3: {
        "CharacterName4": "Testheld", "SIZE": "Medium",
        "PERSONALITY TRAITS": "Ich bin mutig.", "IDEALS": "Freiheit.",
        "BONDS": "Meine Heimat.", "FLAWS": "Zu stur.",
    },
    4: {
        "spellHeader0": "=== CANTRIPS ===", "spellName0": "Mage Hand", "spellPrepared0": "O",
        "spellCastingTime0": "1A", "spellComponents0": "V,S", "spellRange0": "30 ft.",
        "spellDuration0": "1 minute", "spellPage0": "PHB-2024 293",
        "spellHeader2": "=== 2nd LEVEL ===", "spellName2": "Darkness", "spellPrepared2": "O",
        "spellCastingTime2": "1A", "spellComponents2": "V,M",
        "spellDuration2": "Concentration, up to 10 minutes", "spellPage2": "PHB-2024 260",
    },
}


@pytest.fixture()
def charakter():
    return extrahiere(baue_ddb_pdf(BEISPIEL))


# --- Tests -------------------------------------------------------------------

def test_liest_verwaiste_widgets_ohne_acroform():
    """§13.1 Nr.4: Widgets werden auch ohne Catalog-/AcroForm gelesen."""
    data = baue_ddb_pdf(BEISPIEL)
    doc = fitz.open(stream=data, filetype="pdf")
    assert doc.xref_get_key(doc.pdf_catalog(), "AcroForm") == ("null", "null")
    roh, _ = ddb_pdf.lese_widgets(doc)
    assert any(r.name == "CharacterName" and r.wert == "Testheld" for r in roh)


def test_identitaet_und_zahlen(charakter):
    i = charakter.identitaet
    assert i.name == "Testheld"
    assert i.klasse.en == "Monk" and i.stufe == 5 and i.klasse_stufe_roh == "Monk 5"
    assert i.spezies.en == "Human" and i.hintergrund.en == "Mist Wanderer"
    assert i.ep == "(Milestone)" and i.groesse.en == "Medium"
    assert i.unterklasse is None  # nicht im Beispiel belegt -> nicht geraten
    k = charakter.kampf
    assert (k.rk, k.tp_max, k.trefferwuerfel, k.initiative, k.uebungsbonus) == (17, 38, "5d8", "+4", "+3")
    assert k.tp_temp == "--" and k.passiv_wahrnehmung == "16"
    assert k.bewegungsrate.en == "40 ft. (Walking)" and k.sinne.en == "Darkvision 60 ft."


def test_zahlen_bleiben_roh_kein_uetext(charakter):
    """Zahlen/Modifikatoren laufen NIE als UeText (§8.3): RK ist int, Mod ist roher str."""
    assert isinstance(charakter.kampf.rk, int)
    assert charakter.attribute["dex"].mod == "+4"  # roher String mit Vorzeichen
    assert charakter.ausruestung.muenzen == {"cp": 0, "sp": 0, "ep": 0, "gp": 80, "pp": 0}


def test_attribute_vollstaendig(charakter):
    a = charakter.attribute
    assert a["str"].wert == 8 and a["str"].mod == "-1" and a["str"].rettungswurf == "+2"
    assert a["str"].rettung_geuebt is True and a["dex"].rettung_geuebt is True
    assert a["con"].rettung_geuebt is False  # kein ConProf-Widget
    assert set(a.keys()) == {"str", "dex", "con", "int", "wis", "cha"}


def test_fertigkeiten_und_uebungsmarker(charakter):
    ferts = {f.schluessel: f for f in charakter.fertigkeiten}
    assert ferts["acrobatics"].mod == "+7" and ferts["acrobatics"].geuebt is True
    assert ferts["stealth"].mod == "+7" and ferts["stealth"].geuebt is True  # 'Stealth ' mit Space
    assert ferts["arcana"].geuebt is False


def test_proficiencies_alle_vier_kategorien_als_ganzes(charakter):
    """Kategorie wird als GANZES gehalten; DDBs invertiertes 'Crossbow, Hand' wird vorab zu
    'Hand Crossbow' normalisiert - EINE Waffe, kein Komma-Split kann mehr fehlzerlegen."""
    assert [u.en for u in charakter.uebungen.ruestung] == ["Light Armor"]
    assert [u.en for u in charakter.uebungen.waffen] == ["Hand Crossbow, Scimitar, Shortsword"]
    assert [u.en for u in charakter.uebungen.werkzeuge] == ["Thieves' Tools"]
    assert [u.en for u in charakter.uebungen.sprachen] == ["Common, Elvish"]


def test_mehrere_waffen(charakter):
    assert [(w.name.en, w.angriffsbonus) for w in charakter.angriffe] == \
        [("Unarmed Strike", "+7"), ("Dagger", "+6")]
    assert charakter.angriffe[0].schaden.en == "1d8+4 Bludgeoning"


def test_story_felder(charakter):
    p = charakter.persoenlichkeit
    assert p.wesenszuege.en == "Ich bin mutig." and p.ideale.en == "Freiheit."
    assert p.bindungen.en == "Meine Heimat." and p.makel.en == "Zu stur."
    assert p.wesenszuege.art == "text"


def test_features_verlustfrei_verbunden(charakter):
    """FeaturesTraits1..3 an Wortgrenzen gebrochen -> Smart-Join rekonstruiert (§7.5)."""
    merk = {m.name.en: m for m in charakter.merkmale}
    assert "Martial Arts" in merk and merk["Martial Arts"].herkunft == "klasse"
    assert "Deflect Attacks" in merk
    assert [x.en for x in merk["Deflect Attacks"].aktionsoekonomie] == ["1 Reaction"]
    assert "Grappler" in merk and merk["Grappler"].herkunft == "talent"
    # Der Fugen-Text 'the same type' + 'dealt by' darf nicht verklebt sein:
    assert "the same type dealt by the attack" in merk["Martial Arts"].beschreibung.en


def test_stern_zeile_wird_kein_spuk_merkmal(charakter):
    """Eine '*Note:'-Zeile OHNE '•' ist Beschreibung, kein neues Merkmal."""
    namen = [m.name.en for m in charakter.merkmale]
    assert not any(n.startswith("Note") for n in namen)
    grappler = next(m for m in charakter.merkmale if m.name.en == "Grappler")
    assert "reroll ones and twos" in grappler.beschreibung.en
    assert "More grappler text." in grappler.beschreibung.en


def test_zauber(charakter):
    z = charakter.zauberwirken.zauber
    assert len(z) == 2
    assert z[0].name.en == "Mage Hand" and z[0].grad == 0 and z[0].vorbereitet is True
    assert z[1].name.en == "Darkness" and z[1].grad == 2 and z[1].komponenten == "V,M"


def test_ausruestung(charakter):
    g = charakter.ausruestung.gegenstaende
    assert (g[0].name.en, g[0].menge, g[0].gewicht) == ("Rope", "1", "5 lb.")
    assert charakter.ausruestung.getragenes_gewicht == "17 lb."


def test_verlustfrei_alle_widgets_in_roh():
    """Unabhaengige (fallback-bewusste) Widget-Lesung == roh_felder (nichts faellt weg)."""
    data = baue_ddb_pdf(BEISPIEL)
    doc = fitz.open(stream=data, filetype="pdf")
    unabhaengig = _unabhaengig_lesen(doc)
    char = extrahiere(data)
    erfasst = {(r.seite, r.name, r.wert) for r in char.roh_felder}
    assert erfasst == unabhaengig
    assert len(char.roh_felder) == len(unabhaengig)


def test_wert_aus_contents_fallback():
    """KONZEPT §4.1: liegt der Wert in /Contents statt /V, wird er dennoch erfasst."""
    data = baue_ddb_pdf(BEISPIEL, contents_felder={0: {"CurrentHP": "25"}})
    char = extrahiere(data)
    assert "CurrentHP" in {r.name for r in char.roh_felder}
    assert char.kampf.tp_aktuell == 25  # ueber Skalar-Mapping + Contents-Fallback


def test_text_widget_wert_off_bleibt_erhalten():
    """Ein Text-Feld mit Wert exakt 'Off' ist ein echter Wert und darf nicht wegfallen."""
    variante = {p: dict(f) for p, f in BEISPIEL.items()}
    variante[0]["AdditionalSenses"] = "Off"  # unwahrscheinlich, aber gueltiger Textwert
    char = extrahiere(baue_ddb_pdf(variante))
    assert any(r.name == "AdditionalSenses" and r.wert == "Off" for r in char.roh_felder)


def test_kopf_duplikate_ignoriert_aber_in_roh(charakter):
    """CharacterName2/3/4 werden nicht doppelt gemappt, stehen aber verbatim in roh_felder."""
    assert charakter.identitaet.name == "Testheld"
    namen = {r.name for r in charakter.roh_felder}
    assert {"CharacterName2", "CharacterName3", "CharacterName4"} <= namen
    assert "CharacterName2" not in charakter.raw  # nicht als 'unerwartet' markiert


def test_unbekanntes_feld_landet_in_raw(charakter):
    assert charakter.raw.get("MysteryField") == "unbekannter Wert"


def test_multiclass_wird_nicht_geraten():
    """'Monk 3 / Rogue 2' ist nicht eindeutig zerlegbar -> klasse/stufe None, Rohwert bleibt (§7.4)."""
    variante = {p: dict(f) for p, f in BEISPIEL.items()}
    variante[0]["CLASS  LEVEL"] = "Monk 3 / Rogue 2"
    char = extrahiere(baue_ddb_pdf(variante))
    assert char.identitaet.klasse is None and char.identitaet.stufe is None
    assert char.identitaet.klasse_stufe_roh == "Monk 3 / Rogue 2"
    assert any("nicht eindeutig einklassig" in w for w in char.warnungen)


def test_falsche_seitenzahl_abgelehnt():
    with pytest.raises(DDBFormatFehler):
        extrahiere(baue_ddb_pdf(BEISPIEL, seitenzahl=3))


def test_fehlende_pflichtfelder_abgelehnt():
    verstuemmelt = {0: {"CharacterName": "X"}}  # ohne CLASS/RACE/Attribute/FeaturesTraits1
    with pytest.raises(DDBFormatFehler):
        extrahiere(baue_ddb_pdf(verstuemmelt))


def test_fingerprint_ist_werteunabhaengig():
    """Gleiche Feldnamen, andere Werte -> gleicher Fingerprint (§7.2: nie Werte hashen)."""
    a = extrahiere(baue_ddb_pdf(BEISPIEL))
    variante = {p: dict(felder) for p, felder in BEISPIEL.items()}
    variante[0]["CharacterName"] = "Ganz Anderer Name"
    variante[0]["AC"] = "12"
    b = extrahiere(baue_ddb_pdf(variante))
    assert a.quell_fingerprint == b.quell_fingerprint


def test_smart_join_regeln():
    # Wortgrenze ohne Whitespace -> genau EIN Leerzeichen einfuegen
    assert _verbinde_fragmente(["same type", "dealt"]) == "same type dealt"
    # Vorhandenen Whitespace nicht verdoppeln
    assert _verbinde_fragmente(["ende. ", "Start"]) == "ende. Start"
    assert _verbinde_fragmente(["ende.\n", "Start"]) == "ende.\nStart"
    # Fragmentinhalt bleibt zusammenhaengender Teilstring
    j = _verbinde_fragmente(["abc", "def", "ghi"])
    assert "abc" in j and "def" in j and "ghi" in j


def test_zaubermodifikator_wird_abgeleitet():
    """Zaubermodifikator = Attributsmodifikator des Zauberattributs (reine Querreferenz
    innerhalb desselben Bogens); unbekanntes Attribut -> nichts raten."""
    from app.charakterbogen.ddb_pdf import _leite_zaubermodifikator_ab
    from app.charakterbogen.modelle import Attribut, Charakter, UeText

    c = Charakter()
    c.attribute["wis"] = Attribut(wert=18, mod="+4")
    c.zauberwirken.attribut = UeText(en="Wisdom", art="term")
    _leite_zaubermodifikator_ab(c)
    assert c.zauberwirken.modifikator == "+4"

    c2 = Charakter()
    c2.attribute["wis"] = Attribut(wert=18, mod="+4")
    c2.zauberwirken.attribut = UeText(en="Ki", art="term")
    _leite_zaubermodifikator_ab(c2)
    assert c2.zauberwirken.modifikator is None


def test_invertierte_waffennamen_normalisiert():
    """'Crossbow, Hand' ist EINE Waffe -> 'Hand Crossbow' (Befund 16.07.2026: die
    Komma-Zerlegung des Sprachmodells erfand sonst eine generische Armbrust)."""
    from app.charakterbogen.ddb_pdf import _normalisiere_invertierte_namen

    assert _normalisiere_invertierte_namen(
        "Crossbow, Hand, Scimitar, Shortsword, Simple Weapons") == \
        "Hand Crossbow, Scimitar, Shortsword, Simple Weapons"
    assert _normalisiere_invertierte_namen("Crossbow, Light, Crossbow, Heavy") == \
        "Light Crossbow, Heavy Crossbow"
    assert _normalisiere_invertierte_namen("Wargong, Woodcarver's Tools") == \
        "Wargong, Woodcarver's Tools"
