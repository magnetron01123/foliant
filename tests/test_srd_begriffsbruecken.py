"""Gegenstands-/Monster-Bruecken per Struktur-Abgleich: Preisparsing (deutsche
Tausenderpunkte!), Beweisstufen, Verwerfung ununterscheidbarer Kandidaten, kein
Kapern fremder Glossar-Zeilen - und die HG-Normalisierung, ohne die dieselbe
Kreatur in Open5e ('4.0') und srd-de ('4') zwei verschiedene waere."""
import sqlite3
from pathlib import Path

import pytest

from app import facetten as f
from importer import srd_begriffsbruecken as bb
from importer.import_glossar import (_finde_monster_paare,
                                     seed_gegenstands_bruecke_aus_bestand)

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def _db(tmp_path):
    pfad = tmp_path / "bruecken.sqlite"
    con = sqlite3.connect(pfad)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
        "VALUES (?,?,?,?,?,?,?)",
        [("srd-de", "SRD 5.2.1 (Deutsch)", "de", "2024", "pdf", "CC-BY-4.0", 10),
         ("open5e-srd-2024", "SRD 5.2 (Open5e)", "en", "2024", "open5e", "CC-BY-4.0", 60)])
    return con


def _item(con, quelle_id, name, body, sprache):
    spalte_de = name if sprache == "de" else None
    spalte_en = name if sprache == "en" else None
    con.execute(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,"
        "body_md) VALUES (?,?,?,?,?,?,?)",
        (quelle_id, "gegenstand", spalte_de, spalte_en, sprache, "2024", body))


def _de_item(con, name, kontext="Ausrüstung > Abenteurerausrüstung"):
    _item(con, 1, name, f"*Kontext: {kontext}*\n\nBeschreibung.", "de")


def _en_item(con, name, preis_gp, kategorie="Adventuring Gear"):
    _item(con, 2, name,
          f"**Category:** {kategorie} · **Cost:** {preis_gp:.2f} gp · "
          f"**Weight:** 1.000 lb\n\nDescription.", "en")


def test_preisparsing_deutsche_tausenderpunkte():
    assert bb._preis_de("Fernrohr (1.000 GM)") == 100_000     # Punkt = Tausender!
    assert bb._preis_de("Seil (1 GM)") == 100
    assert bb._preis_de("Fackel (1 KM)") == 1
    assert bb._preis_de("Leiter (1 SM)") == 10
    assert bb._preis_en("Cartographer's Tools (15 GP)", "") == 1_500
    assert bb._preis_en(None, "**Cost:** 1000.00 gp") == 100_000
    assert bb._preis_de("Ohne Preis") is None


def test_seed_paar_strippt_suffixe():
    assert bb.seed_paar("Carpenter's Tools (8 GP)", "Schreinerwerkzeug (8 GM)") == \
        ("Carpenter's Tools", "Schreinerwerkzeug")


def test_glossar_hop_und_ausschluss(tmp_path):
    con = _db(tmp_path)
    _de_item(con, "Giftmischerausrüstung (50 GM)", "Ausrüstung > Werkzeug > Handwerkszeug")
    _de_item(con, "Alchemistenfeuer (50 GM)")
    _en_item(con, "Poisoner's Kit", 50.0, "Tools")
    _en_item(con, "Alchemist's Fire", 50.0)
    con.execute("INSERT INTO glossar (term_en,term_de,offiziell,quelle) "
                "VALUES ('Poisoner''s Kit','Giftmischerausrüstung',1,'dnddeutsch')")
    con.commit()
    paare, report = bb.finde_gegenstands_paare(con)
    stufen = {en: stufe for en, _de, stufe in paare}
    assert stufen["Poisoner's Kit"] == "glossar-hop"
    # Nach dem Hop bleibt je Seite genau EIN Rest -> Ausschlussprinzip (hier bereits
    # auf der Kategorie-Ebene, beide 'sonstig'):
    assert stufen["Alchemist's Fire"].startswith("ausschluss")
    assert not report


def test_kategorie_widerspruch_verhindert_ausschluss(tmp_path):
    """1:1 im Preis-Bucket reicht NICHT, wenn die Grobkategorien einander widersprechen
    (Werkzeug wird nie eine Waffe) - lieber Luecke als falsches Paar."""
    con = _db(tmp_path)
    _de_item(con, "Schmiedewerkzeug (20 GM)", "Ausrüstung > Werkzeug > Handwerkszeug")
    _en_item(con, "Halberd", 20.0, "Weapon")
    con.commit()
    paare, report = bb.finde_gegenstands_paare(con)
    assert not paare
    assert report and "20 GM" in report[0]


def test_ununterscheidbare_kandidaten_werden_verworfen(tmp_path):
    con = _db(tmp_path)
    _de_item(con, "Flasche (2 KM)")
    _de_item(con, "Krug (2 KM)")
    _en_item(con, "Flask", 0.02)
    _en_item(con, "Jug", 0.02)
    con.commit()
    paare, report = bb.finde_gegenstands_paare(con)
    assert not paare
    assert report and "2 DE vs. 2 EN" in report[0]


def test_gleichnamige_blockieren_den_ausschluss_nicht(tmp_path):
    """'Sack' == 'Sack (1 KM)' braucht keine Bruecke - und darf den Ausschluss fuer
    die echten Kandidaten im selben Bucket nicht blockieren."""
    con = _db(tmp_path)
    _de_item(con, "Sack (1 KM)")
    _de_item(con, "Kerze (1 KM)")
    _en_item(con, "Sack", 0.01)
    _en_item(con, "Candle", 0.01)
    con.commit()
    paare, _report = bb.finde_gegenstands_paare(con)
    assert [(en, de) for en, de, _s in paare] == [("Candle", "Kerze (1 KM)")]


def test_seeder_kapert_keine_fremden_zeilen(tmp_path):
    con = _db(tmp_path)
    _de_item(con, "Kerze (1 KM)")
    _en_item(con, "Candle", 0.01)
    _de_item(con, "Eimer (5 KM)")
    _en_item(con, "Bucket", 0.05)
    con.execute("INSERT INTO glossar (term_en,term_de,offiziell,quelle) "
                "VALUES ('Candle','Kerze',1,'dnddeutsch')")
    con.commit()
    n = seed_gegenstands_bruecke_aus_bestand(con)
    zeilen = {r[0]: r[1] for r in con.execute(
        "SELECT term_en, quelle FROM glossar")}
    assert zeilen["Candle"] == "dnddeutsch"          # nicht gekapert
    assert zeilen["Bucket"] == bb.QUELLE             # echte Luecke geseedet
    assert n == 1


# --- Monster: HG-Normalisierung + Teil-Schluessel-Ausschluss --------------------------

_DE_STATBLOCK_OHNE_ATTR = ("*Kontext: Monster von A–Z*\n\n_Kleines Tier, gesinnungslos_\n\n"
                           "**RK** 14 **TP** 7\n\n**HG** 1/8 (EP 25)")
_EN_STATBLOCK = ("*Kontext: Monsters*\n\n_Small Beast, unaligned_\n\nAC 14 HP 7\n\n"
                 "STR 7 DEX 15 CON 9 INT 8 WIS 7 CHA 8\n\nCR 0.125")


def _monster(con, quelle_id, name, body, sprache):
    con.execute(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,"
        "body_md) VALUES (?,?,?,?,?,?,?)",
        (quelle_id, "monster", name if sprache == "de" else None,
         name if sprache == "en" else None, sprache, "2024", body))


def test_hg_ganzzahl_dezimal_wird_normalisiert():
    assert f.monster_hg("... CR 4.0 ...") == "4"
    assert f.monster_hg("... CR 0.25 ...") == "1/4"
    assert f.monster_hg("... **HG** 4 ...") == "4"


def test_monster_teilschluessel_paart_bei_unlesbarer_attributstabelle(tmp_path):
    con = _db(tmp_path)
    _monster(con, 1, "Koboldkrieger", _DE_STATBLOCK_OHNE_ATTR, "de")
    _monster(con, 2, "Kobold Warrior", _EN_STATBLOCK, "en")
    con.commit()
    assert f.monster_attribute(_DE_STATBLOCK_OHNE_ATTR) is None    # Vorbedingung
    paare = _finde_monster_paare(con)
    assert [(en, de) for en, de, _k in paare] == [("Kobold Warrior", "Koboldkrieger")]


def test_monster_attributwiderspruch_verhindert_teilschluessel_paar(tmp_path):
    """Beidseitig LESBARE, abweichende Attributstabellen = verschiedene Kreaturen -
    der Teil-Schluessel darf sie nicht zusammenzwingen."""
    con = _db(tmp_path)
    de = _DE_STATBLOCK_OHNE_ATTR.replace(
        "**HG** 1/8 (EP 25)", "**Stä**3 **Ges**18 **Kon**10 **Int**14 **Wei**13 "
                              "**Cha**11\n\n**HG** 1/8 (EP 25)")
    _monster(con, 1, "Feengeist", de, "de")
    _monster(con, 2, "Kobold Warrior", _EN_STATBLOCK, "en")
    con.commit()
    assert f.monster_attribute(de) is not None                     # Vorbedingung
    assert _finde_monster_paare(con) == []
