"""Tests fuer die generische, algorithmische Namensreparatur (importer/namensreparatur.py) -
reine Funktionen (kein PDF/DB), laeuft im CI. Kernanspruch: echte Zerlegungen werden gegen
die autoritative Namensliste korrigiert, aber saubere aehnliche/anagramm-gleiche Namen bleiben
garantiert unberuehrt (kein blindes Fuzzy)."""
from importer import namensreparatur as nr
from importer.import_glossar import _name_sauber

REF = ["Gargyl", "Harpyie", "Atterkopp", "Kreischerpilz", "Bewegung und Positionierung",
       "Feindlich gesinnt (Haltung)", "Freundlich gesinnt (Haltung)",
       "Wächterschild", "Schildwächter", "Kreaturentyp"]
TOC = ["Gargyl", "Harpyie", "Atterkopp", "Kreischerpilz", "Bewegung und Positionierung"]
_TOCF = frozenset(nr._fold(t) for t in TOC)


def test_detektor1_kurzfragment_anagramm():
    # Glyph-Zerlegung mit Kurzfragment ('l'/'ie') -> EINDEUTIGES Anagramm:
    assert nr.finde_korrektur("Gar l gy", REF, _name_sauber) == "Gargyl"
    assert nr.finde_korrektur("Har ie py", REF, _name_sauber) == "Harpyie"
    assert nr.finde_korrektur("Atterko pp", REF, _name_sauber) == "Atterkopp"


def test_detektor2_leerzeichen_nur_auf_toc_form():
    # Leerzeichen-Anomalie -> die autoritative TOC-Form:
    assert nr.finde_korrektur("Kreischer pilz", REF, _name_sauber, _TOCF) == "Kreischerpilz"
    assert nr.finde_korrektur("Bewegungund Positionierung", REF, _name_sauber, _TOCF) \
        == "Bewegung und Positionierung"


def test_keine_fuzzy_falschkorrektur():
    # Aehnliche, aber DISTINKTE saubere Namen bleiben unberuehrt (kein blindes Fuzzy):
    assert nr.finde_korrektur("Feindlich gesinnt (Haltung)", REF, _name_sauber, _TOCF) is None
    # Legitime Kompositum-Umstellung ist ein Anagramm, hat aber KEIN Kurzfragment -> Detektor 1
    # feuert nicht; Detektor 2 verlangt gleiche Sequenz -> auch nicht. Bleibt unberuehrt:
    assert nr.finde_korrektur("Wächterschild", REF, _name_sauber, _TOCF) is None
    assert nr.finde_korrektur("Schildwächter", REF, _name_sauber, _TOCF) is None


def test_repariere_gesamtlauf_nur_korrupte():
    eingabe = ["Gar l gy", "Kreischer pilz", "Feindlich gesinnt (Haltung)", "Wächterschild",
               "Gargyl"]   # Gargyl selbst ist schon sauber
    erg = nr.repariere(eingabe, REF, _name_sauber, toc_namen=TOC)
    assert erg == {"Gar l gy": "Gargyl", "Kreischer pilz": "Kreischerpilz"}


def test_fold_normalisiert_geschuetztes_leerzeichen():
    assert nr._fold("Auf 0\xa0Trefferpunkte") == nr._fold("Auf 0 Trefferpunkte")


def test_ziffer_token_ist_kein_zerlege_fragment():
    # Regression: ein sauberer Name mit Zahl ('Auf 0 Trefferpunkte sinken') darf NICHT als
    # korrupt gelten (die '0' ist ein legitimes kurzes Token, kein Glyph-Fragment wie 'l').
    # Sonst landet er in Detektor 1 (Anagramm) und wird faelschlich auf eine bloss anders
    # kodierte (geschuetztes '\xa0') Leerzeichen-Variante desselben Namens "korrigiert".
    name = "Auf 0 Trefferpunkte sinken"
    nbsp = "Auf 0\xa0Trefferpunkte sinken"          # gleiche Bezeichnung, nur \xa0 statt Space
    assert _name_sauber(name)
    tocf = frozenset(nr._fold(t) for t in [nbsp])   # TOC fuehrt die \xa0-Form
    assert nr.finde_korrektur(name, [name, nbsp], _name_sauber, tocf) is None
    assert nr.finde_korrektur(nbsp, [name, nbsp], _name_sauber, tocf) is None
    assert nr.repariere([name, nbsp], [name, nbsp], _name_sauber, toc_namen=[nbsp]) == {}
