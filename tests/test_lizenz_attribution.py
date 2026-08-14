"""Die Attribution haengt an einer Rechtspflicht, nicht an einer Schreibweise.

Anlass (Review 14.08.2026, S-13/S-14): Die Attribution entstand aus
`str(lizenz).upper().startswith("CC-BY")`. Damit hing eine Lizenzpflicht an einem
ungepruefbaren Freitextfeld - eine Quelle, deren Lizenzstring anders getippt ist
("CC BY 4.0", "SRD 5.2.1 (CC-BY-4.0)"), lieferte still ohne Attribution aus. Still ist
hier das Problem: Ein fehlender Hinweis faellt niemandem auf, weil nichts fehlt, was man
sehen wuerde. Zusaetzlich kam OGL im Code ueberhaupt nicht vor, obwohl README.md sie fuer
Open5e (srd-2014) zusagt.

Dieser Test prueft beide Richtungen - dass offene Lizenzen eine Attribution ausloesen UND
dass die bewusst nicht-offene Errata-Lizenz keine bekommt. Die zweite Haelfte ist die
wichtigere: Eine SRD-Attribution an einem WotC-Errata waere eine falsche Aussage ueber
den Rechteinhaber (CONCEPT.md par. 10, Entscheidung vom 31.07.2026).
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.tools.ausgabe import (ATTRIBUTION_CC_BY, ATTRIBUTION_OGL,
                               attribution_fuer)

_WURZEL = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("lizenz", [
    "CC-BY-4.0",
    "cc-by-4.0",
    "CC BY 4.0",                     # Leerzeichen statt Bindestrich
    "SRD 5.2.1 (CC-BY-4.0)",         # nicht am Zeilenanfang
    "CC-BY-4.0 / OGL",
])
def test_cc_by_loest_attribution_aus(lizenz):
    """Jede Schreibweise, die CC-BY meint, traegt die SRD-Attribution."""
    assert ATTRIBUTION_CC_BY in (attribution_fuer(lizenz) or "")


@pytest.mark.parametrize("lizenz", [
    "OGL 1.0a",
    "ogl",
    "Open Game License 1.0a",
    "CC-BY-4.0 / OGL",
])
def test_ogl_loest_attribution_aus(lizenz):
    """README.md sagt fuer Open5e (srd-2014) OGL-Attribution zu - bis 14.08.2026 lieferte
    der Code dafuer nichts."""
    assert ATTRIBUTION_OGL in (attribution_fuer(lizenz) or "")


def test_doppellizenz_traegt_beide():
    """Open5e fuehrt beide Lizenzen; eine davon zu verschweigen waere unvollstaendig."""
    ergebnis = attribution_fuer("CC-BY-4.0 / OGL")
    assert ATTRIBUTION_CC_BY in ergebnis and ATTRIBUTION_OGL in ergebnis


@pytest.mark.parametrize("lizenz", [
    None,
    "",
    "privat",
    "WotC (frei verteilt, keine offene Lizenz)",
])
def test_ohne_offene_lizenz_keine_attribution(lizenz):
    """Der teurere Fehler waere die Attribution zu VIEL: 'frei verteilt' ist keine offene
    Lizenz, und ein CC-BY-Hinweis daran behauptete etwas Falsches ueber den
    Rechteinhaber."""
    assert attribution_fuer(lizenz) is None


def test_lizenzstrings_der_beispielkonfig_sind_abgedeckt():
    """Der Gegentest gegen die echte Konfiguration: Jeder dort gefuehrte Lizenzstring
    muss eine BEWUSSTE Zuordnung haben - entweder eine Attribution oder die
    ausdrueckliche Nicht-Attribution. Ein neuer, unbekannter String faellt hier auf,
    statt still ohne Attribution live zu gehen.

    `config/foliant.toml` selbst ist gitignored (es gibt in CI keine), deshalb laeuft der
    Test gegen die mitgelieferte Vorlage.
    """
    vorlage = _WURZEL / "config" / "foliant.example.toml"
    strings = set(re.findall(r'^\s*lizenz\s*=\s*"([^"]+)"', vorlage.read_text("utf-8"),
                             flags=re.MULTILINE))
    assert strings, "keine Lizenzstrings in der Vorlage gefunden - Format geaendert?"

    # Bewusste Einordnung je Lizenzfamilie. Neue Familie -> hier eintragen, nachdem
    # geklaert ist, ob sie eine Attribution verlangt.
    ohne_attribution = {"privat", "WotC (frei verteilt, keine offene Lizenz)"}
    for lizenz in strings:
        if lizenz in ohne_attribution:
            assert attribution_fuer(lizenz) is None, (
                f"{lizenz!r} soll KEINE Attribution tragen, bekommt aber eine")
        else:
            assert attribution_fuer(lizenz), (
                f"{lizenz!r} bekommt keine Attribution - entweder fehlt die Erkennung, "
                f"oder die Lizenz gehoert bewusst nach `ohne_attribution`")
