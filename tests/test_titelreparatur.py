"""Die kuratierten Kapitel-/Abschnittstitel (namensreparatur.KURATIERTE_TITEL).

Warum es diese Tabelle gibt: `repariere_2014_namen` belegt gegen das Glossar und
dnddeutsch — also gegen Spielbegriffe. Kapiteltitel wie 'KINDHEITSERINNERUNGEN' stehen
dort nicht und blieben deshalb zerrissen, obwohl ein Mensch sie sofort liest.

Warum von Hand und nicht per Heuristik (zwei Anläufe am 01.08.2026 gemessen): Ein
Algorithmus, der Einzelbuchstaben an den Nachbarn zieht, schaffte 22 von 49 und erzeugte
dabei falsche Namen ('HEIMATLÄ N DER' → 'HEIMATLÄ NDER'). Ein segmentierender Zweitversuch
kam auf 26 und verklebte 'DIE S PIELWERTE' zu 'DIES PIELWERTE'. Welches Leerzeichen echt
ist, steht nicht im Namen — und ein FALSCHER Eintragsname ist schlimmer als ein
zerrissener, weil er richtig aussieht.
"""
import re
import sqlite3

import pytest

from importer.namensreparatur import KURATIERTE_TITEL
from tests.hilfen import SCHEMA

_RISS = re.compile(r"(?:^|\s)[B-HJ-Zb-hj-zÄÖÜäöüß](?:\s|$)")


def test_jeder_schluessel_ist_wirklich_zerrissen():
    """Die Tabelle darf nur Namen anfassen, die der Wächter auch meldet - sonst
    korrigiert sie etwas, das niemand als kaputt erkannt hat."""
    ohne_riss = [k for k in KURATIERTE_TITEL if not _RISS.search(k)]
    assert not ohne_riss, f"kein Riss im Schluessel: {ohne_riss}"


def test_keine_zielform_ist_noch_zerrissen():
    """Das eigentliche Versprechen: Nach der Reparatur meldet der Wächter sie nicht mehr.
    Eine halbe Reparatur wäre die schlechteste Variante - sie sieht erledigt aus."""
    kaputt_geblieben = {a: z for a, z in KURATIERTE_TITEL.items() if _RISS.search(z)}
    assert not kaputt_geblieben, kaputt_geblieben


def test_zielform_ist_nie_leer_oder_gleich():
    for kaputt, korrekt in KURATIERTE_TITEL.items():
        assert korrekt.strip(), kaputt
        assert korrekt != kaputt, kaputt


def test_reparatur_greift_und_ist_idempotent(tmp_path):
    """Zweimal laufen darf nichts kaputtmachen: Die Kette läuft bei JEDEM Glossar-Import,
    und ein Re-Import spielt die rohen OCR-Namen wieder ein (CLAUDE.md) - genau dafür
    sitzt die Reparatur in der Kette und nicht in einem Einmal-UPDATE."""
    from importer.import_glossar import repariere_kuratierte_titel

    con = sqlite3.connect(tmp_path / "t.sqlite")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (id,kuerzel,titel,sprache,edition,herkunft,prioritaet)"
                " VALUES (1,'xgte-2014-de','Xanathar','de','2014','pdf',85)")
    proben = ["ABERGLAUB E", "KIN DH EITSERIN N ERU NGEN", "HEIMATLÄ N DER"]
    for name in proben:
        con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,"
                    "body_md) VALUES (1,'regel',?,'de','2014','Text.')", (name,))
    con.commit()

    erste = repariere_kuratierte_titel(con)
    con.commit()
    assert erste == len(proben), f"nur {erste} von {len(proben)} repariert"
    namen = {r[0] for r in con.execute("SELECT name_de FROM eintraege")}
    assert namen == {"ABERGLAUBE", "KINDHEITSERINNERUNGEN", "HEIMATLÄNDER"}, namen

    zweite = repariere_kuratierte_titel(con)      # idempotent
    con.close()
    assert zweite == 0, "zweiter Lauf darf nichts mehr aendern"


def test_reparatur_haengt_in_der_kette():
    """Nur in der Kette überlebt sie einen Re-Import. Hinge sie nur an einem
    Handaufruf, wäre sie beim nächsten Buch-Import wieder verloren."""
    from importer.import_glossar import _KETTE, repariere_kuratierte_titel

    assert any(f is repariere_kuratierte_titel for f, _b in _KETTE), (
        "repariere_kuratierte_titel fehlt in der Glossar-Kette")


@pytest.mark.parametrize("kaputt,korrekt", [
    ("ABERGLAUB E", "ABERGLAUBE"),
    ("KIN DH EITSERIN N ERU NGEN", "KINDHEITSERINNERUNGEN"),
    ("MAGISCHE GEGE N STÄNDE", "MAGISCHE GEGENSTÄNDE"),
    ("DIE S PIELWERTE DER C H ARAKTERE", "DIE SPIELWERTE DER CHARAKTERE"),
    ("D 0 GGE", "DOGGE"),
    ("SCHAU 5 Pl E LE R", "SCHAUSPIELER"),
])
def test_die_faelle_die_der_automatik_misslangen(kaputt, korrekt):
    """Genau die Zuordnungen, an denen beide Heuristik-Anläufe scheiterten - hier stehen
    sie als geprüfte Festlegung."""
    assert KURATIERTE_TITEL[kaputt] == korrekt
