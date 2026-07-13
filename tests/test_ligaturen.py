"""Tests fuer den allgemeinen fi/fl-Ligatur-Resolver (importer/ligaturen.py).

Prueft die ALGORITHMISCHE Aufloesung gegen das gebuendelte Vokabular - unabhaengig von den
(privaten) Buch-Reparaturmodulen; laeuft daher auch im oeffentlichen CI."""
from importer import ligaturen

R = "�"   # U+FFFD (das verlorene Ligatur-Zeichen)


def test_aufloesen_gaengige_ligaturen():
    txt = f"di{R}cult con{R}ict in{R}uence pro{R}ciency bene{R}t {R}eeing"
    erg = ligaturen.aufloesen(txt)
    assert erg == "difficult conflict influence proficiency benefit fleeing", erg


def test_kompositum_und_flexion():
    # Kompositum (sea+floor) und Flexion (-ies -> -y):
    assert ligaturen.aufloesen(f"sea{R}oor") == "seafloor"
    assert ligaturen.aufloesen(f"signi{R}es") == "signifies"


def test_grossschreibung_erhalten():
    assert ligaturen.aufloesen(f"Con{R}ict") == "Conflict"


def test_echte_doppeldeutigkeit_bleibt_ohne_override():
    # 'flat' UND 'fiat' sind Woerter -> der Algorithmus entscheidet NICHT (bleibt als �):
    assert ligaturen.aufloesen(f"{R}at") == f"{R}at"
    # ... mit Override wird es aufgeloest:
    assert ligaturen.aufloesen(f"{R}at", override={f"{R}at": "flat"}) == "flat"


def test_zusatzvokabular_eigenname():
    # Ein Eigenname, den kein Woerterbuch kennt, wird ueber Zusatzvokabular aufloesbar:
    assert ligaturen.aufloesen(f"Spell{R}re") == "Spellfire"          # Kompositum spell+fire
    assert ligaturen.aufloesen(f"Tel{R}amm") == f"Tel{R}amm"          # unbekannt -> bleibt
    assert ligaturen.aufloesen(f"Tel{R}amm", zusatzvokabular={"telflamm"}) == "Telflamm"


def test_no_op_ohne_ligatur():
    assert ligaturen.aufloesen("saubere Prosa ohne Sonderzeichen") == "saubere Prosa ohne Sonderzeichen"


def test_deko_grossbuchstaben_unangetastet():
    # Reine Grossbuchstaben-/Deko-Fragmente (kein Kleinbuchstabe) fasst der Resolver NICHT an
    # (die entfernt die Buch-Pipeline separat), damit keine Titel zerschossen werden:
    assert ligaturen.aufloesen(f"W{R}{R}{R}") == f"W{R}{R}{R}"
