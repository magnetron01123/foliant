"""Unit-Tests fuer die Facetten-Ableitung aus dem body_md (app/facetten.py).

Reine Funktionen, keine DB - deshalb immer lauffaehig (anders als die Golden-Suite).
Deckt beide Kopf-Formate ab: srd-de ('_Hervorrufungszauber 3. Grades (Magier, Zauberer)_')
und Open5e ('**Level:** 0 · **School:** Evocation · **Classes:** Warlock')."""
from app import facetten as f

_DE_FEUERBALL = "_Hervorrufungszauber 3. Grades (Magier, Zauberer)_ \n**Zeitaufwand:** Aktion"
_DE_CANTRIP = "_Zaubertrick der Hervorrufung (Hexenmeister)_ \nDu schleuderst ..."
_EN_OPEN5E = "**Level:** 0 · **School:** Evocation · **Classes:** Warlock\n\n**Casting Time:**"
_EN_DDB = "*Kontext: F Spells*\n\n3rd-level evocation\n\nCasting Time: 1 action"


def test_zauber_grad_deutsch_und_zaubertrick():
    assert f.zauber_grad(_DE_FEUERBALL) == 3
    assert f.zauber_grad(_DE_CANTRIP) == 0             # Zaubertrick trotz Italic-Unterstrich
    assert f.zauber_kurz(_DE_FEUERBALL) == "Grad 3"
    assert f.zauber_kurz(_DE_CANTRIP) == "Zaubertrick"


def test_zauber_grad_open5e_und_ddb():
    assert f.zauber_grad(_EN_OPEN5E) == 0              # '**Level:** 0'
    assert f.zauber_grad(_EN_DDB) == 3                 # '3rd-level'


def test_zauber_grad_ohne_muster_ist_none():
    assert f.zauber_grad("Ein Textfragment ohne Kopf.") is None
    assert f.zauber_grad("") is None
    assert f.zauber_grad(None) is None


def test_zauber_schule_de_und_en():
    assert f.zauber_schule(_DE_FEUERBALL) == "hervorrufung"
    assert f.zauber_schule(_EN_OPEN5E) == "hervorrufung"
    assert f.zauber_schule("_Nekromantiezauber 5. Grades (Kleriker)_") == "nekromantie"
    assert f.zauber_schule("kein Schulwort hier") is None


def test_schule_schluessel_synonyme():
    assert f.schule_schluessel("Evocation") == "hervorrufung"
    assert f.schule_schluessel("Hervorrufung") == "hervorrufung"
    assert f.schule_schluessel("Necromancy") == "nekromantie"
    assert f.schule_schluessel("Quatsch") is None
    assert f.schule_anzeige("hervorrufung") == "Hervorrufung"


def test_zauber_klassen_beide_formate():
    assert f.zauber_klassen(_DE_FEUERBALL) == ["Magier", "Zauberer"]
    assert f.zauber_klassen(_EN_OPEN5E) == ["Warlock"]
    assert f.zauber_klassen("kein Klassenfeld") == []


def test_klasse_passt_de_en_tolerant():
    klassen = ["Magier", "Zauberer"]
    assert f.klasse_passt(klassen, "Wizard")           # EN -> Magier
    assert f.klasse_passt(klassen, "magier")
    assert not f.klasse_passt(klassen, "Hexenmeister")
    assert f.klasse_passt(["Hexenmeister"], "Warlock")


def test_schadensart_schluessel_und_treffer():
    assert f.schadensart_schluessel("fire") == "feuer"
    assert f.schadensart_schluessel("Feuer") == "feuer"
    assert f.schadensart_schluessel("Kaelte") == "kaelte"
    assert f.schadensart_schluessel("erfunden") is None
    assert f.hat_schadensart("... erleidet 8W6 Feuerschaden, anderenfalls ...", "feuer")
    assert not f.hat_schadensart("... erleidet 8W6 Kälteschaden ...", "feuer")


def test_monster_hg_de_en():
    assert f.monster_hg("**RK** 17 ... **HG** 1 ...") == "1"
    assert f.monster_hg("... **HG** 1/4 ...") == "1/4"
    assert f.monster_hg("... Challenge 5 (1,800 XP) ...") == "5"
    assert f.hg_kurz("... **HG** 1/8 ...") == "HG 1/8"
    assert f.monster_hg("kein HG-Wert hier") is None
    assert f.hg_passt("... **HG** 1/4 ...", "1/4")
    assert not f.hg_passt("... **HG** 1/4 ...", "1")


def test_monster_typ_de_en_wortgrenze():
    goblin = "*Kontext*\n\n_Kleines Feenwesen (Goblinoide), chaotisch neutral_ **RK** 15"
    assert f.monster_typ(goblin) == "feenwesen"
    assert f.monster_typ("_Mittelgroßer Untoter, rechtschaffen böse_") == "untoter"
    assert f.monster_typ("Medium Undead, Lawful Evil") == "untoter"
    assert f.monster_typ("kein Typwort") is None
    assert f.typ_schluessel("Undead") == "untoter"
    assert f.typ_schluessel("Feenwesen") == "feenwesen"
    assert f.typ_schluessel("Quatschwesen") is None
    assert f.typ_anzeige("untoter") == "Untoter"
