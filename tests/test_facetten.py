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


def test_monster_stats_de_en_und_dezimal_cr():
    de = "**RK** 15 **Initiative** +2 **TP** 10 (3d6) ... **HG** 1/4 (50 EP)"
    en = "**Type:** Small Fey · **CR:** 0.125 (25 XP)\n**AC:** 12 (natural) · **HP:** 7 (2d6)"
    assert f.monster_rk(de) == "15" and f.monster_tp(de) == "10"
    assert f.monster_rk(en) == "12" and f.monster_tp(en) == "7"      # Doppelpunkt-Format
    assert f.monster_hg(en) == "1/8"                                 # Dezimal-CR -> Bruch
    # Attributswerte (uebersetzungsinvariant), engl. 'STR 8' und srd-de '**Stä**8':
    en_ab = en + "\n**Abilities:** STR 8 (-1), DEX 15 (+2), CON 10, INT 10, WIS 8, CHA 8"
    de_ab = de + "\n**Stä**8 −1 **GeS**15 +2 **Kon**10 +0 **Int**10 **Wei**8 **Cha**8"
    assert f.monster_attribute(en_ab) == (8, 15, 10, 10, 8, 8)
    assert f.monster_attribute(de_ab) == (8, 15, 10, 10, 8, 8)       # gleiche Zahlen, andere Sprache
    assert f.monster_attribute("keine werte") is None
    assert f.monster_statschluessel(en_ab) == ("feenwesen", "1/8", "12", "7", (8, 15, 10, 10, 8, 8))
    assert f.monster_statschluessel("nur prosa") == (None, None, None, None, None)


def test_name_sauber_filtert_kurzfragmente_nicht_komposita():
    from importer import import_glossar as ig
    assert ig._name_sauber("Menschenaffe") and ig._name_sauber("Goblin-Scherge")
    assert not ig._name_sauber("Gar l gy")                 # Kurz-Fragment 'l'
    assert not ig._name_sauber("Atterko pp")               # Kurz-Fragment 'pp'
    # KEINE Bigramm-Heuristik mehr: legitime dt. Komposita mit dk/tk/kr an der Wortfuge
    # duerfen NICHT als korrupt gelten (waren vorher Falsch-Positive):
    for gut in ("Koboldkrieger", "Drachenschildkröte", "Grottenschratkrieger"):
        assert ig._name_sauber(gut), gut


def test_srd_de_name_reparatur_map_autoritativ():
    from importer import import_glossar as ig
    # Alle Ziele sind sauber; die aus der srd-PDF bekannten Zerlege-Faelle (7 Monster +
    # 2 Regelnamen) sind abgedeckt:
    assert len(ig.SRD_DE_NAME_REPARATUR) == 9
    assert all(ig._name_sauber(k) for k in ig.SRD_DE_NAME_REPARATUR.values())
    assert ig.SRD_DE_NAME_REPARATUR["Gar l gy"] == "Gargyl"
    assert ig.SRD_DE_NAME_REPARATUR["Kreaturent yp"] == "Kreaturentyp"
    assert ig.SRD_DE_NAME_REPARATUR["Bewegungund Positionierung"] == "Bewegung und Positionierung"


def test_kanon_schreibvariante_sicher():
    from importer import import_glossar as ig
    # ß vor ss; bekanntes Adjektiv klein:
    assert ig._kanon_schreibvariante({"Junger Weisser Drache", "Junger weißer Drache"}) \
        == "Junger weißer Drache"
    assert ig._kanon_schreibvariante({"Riesentausendfüssler", "Riesentausendfüßler"}) \
        == "Riesentausendfüßler"
    # Substantiv-Fall ('Sehen') NICHT anfassen -> None (Review):
    assert ig._kanon_schreibvariante({"Unsichtbares Sehen", "Unsichtbares sehen"}) is None
    # Unterschiedliche Wortzahl / echte Uebersetzung -> None:
    assert ig._kanon_schreibvariante({"Streitross", "Schlachtroß"}) is None


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
