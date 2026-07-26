"""Die Verhaltensregeln laufen ueber drei Kanaele (SPEC.md §7). Zwei davon sind
Freitext und driften deshalb lautlos auseinander: die Server-Instruktion in
`config/stil.py` und die Copy-Paste-Projektanweisung in `config/projektanweisung.md`.
CLAUDE.md
verlangt seit jeher, beide synchron zu halten - bisher war das eine Bitte an den
Menschen, hier wird es geprueft.

Der Test prueft NICHT auf Wortgleichheit (die Kanaele haben unterschiedliche
Adressaten und duerfen anders formulieren), sondern darauf, dass jede tragende
Regel in beiden vorkommt. Faellt eine raus, faellt der Test.
"""
from __future__ import annotations

import pathlib

import pytest

from config import stil
from config.stil import INSTRUCTIONS


@pytest.fixture(scope="module")
def projektanweisung() -> str:
    """Der Text aus config/projektanweisung.md - genau das, was in ein Claude-Projekt
    eingefuegt wird und was die Website ausliefert (EINE Quelle, keine Kopie)."""
    text = stil.projektanweisung()
    assert text, "config/projektanweisung.md fehlt oder ist leer"
    return text


# Je Regel ein Kennzeichen, das in BEIDEN Kanaelen vorkommen muss. Bewusst kurze,
# stabile Fragmente - keine ganzen Saetze, sonst bricht der Test bei jeder Umformulierung.
_TRAGENDE_REGELN = [
    ("Spoiler-Ablehnung", "🚫"),
    ("Leerbefund-Kennzeichnung", "❌"),
    ("Web-Kennzeichnung", "🌐"),
    ("Bestand ist einzige Quelle", "Trainingswissen"),
    ("Belegzeile", "📖"),
    ("Altstand-Warnung", "⚠️"),
    ("SL-Verweis bei Regelluecke", "⚖️"),
    ("Stern-Regel", "*"),
    ("amtliche Begriffe aus dem Tool", "begriffe_deutsch"),
    ("2024-Baureihenfolge", "Hintergrund"),
    ("Pflichtwahl Sprachen", "SPRACHEN"),
    ("Parameterfehler ist kein Leerbefund", "fehler"),
    ("Gegenprobe vor dem Leerbefund", "foliant_suche_bestand"),
    ("gekuerzte Trefferliste", "hinweis_gekuerzt"),
    ("Spoiler-Kennzeichnung der Quelle", "abenteuer_setting"),
    # Eval-Volllauf 26.07.2026 (Fall D3): der Server wies die abweichende englische
    # Vampir-Fassung als 'fremdsprachige_fassungen' aus, aber KEIN Kanal sagte dem
    # Modell, was es damit tun soll - es gab still nur die deutsche Fassung aus.
    ("abweichende Fassung offenlegen", "fremdsprachige_fassungen"),
]


@pytest.mark.parametrize("name,kennzeichen", _TRAGENDE_REGELN,
                         ids=[n for n, _ in _TRAGENDE_REGELN])
def test_regel_steht_in_beiden_kanaelen(name, kennzeichen, projektanweisung):
    assert kennzeichen in INSTRUCTIONS, f"{name}: fehlt in config/stil.py"
    assert kennzeichen in projektanweisung, f"{name}: fehlt in config/projektanweisung.md"


def test_spoilerschutz_steht_ganz_oben():
    """Reihenfolge ist Wirkung: der Spoiler-Schutz ist die oberste Verhaltensregel
    (SPEC.md §7) und muss vor allen Wissensquellen-Regeln stehen."""
    assert INSTRUCTIONS.index("KEINE SPOILER") < INSTRUCTIONS.index("PRIORITÄTSLEITER")


def test_instruktion_bleibt_kompakt():
    """Die Instruktion liegt bei JEDER Verbindung im Kontext. Waechst sie unbegrenzt,
    verduennt sie sich selbst: je mehr Regeln, desto weniger Gewicht je Regel.

    7500 ist ein Budget mit Luft, keine Klippe - der Stand liegt bei ~6000. Loest der
    Test aus, ist die Frage nicht "Grenze anheben", sondern welche Regel dafuer raus
    kann oder in die Tool-Ausgabe gehoert (der zuverlaessigere Kanal, SPEC.md §7)."""
    assert len(INSTRUCTIONS) < 7500, (
        f"stil.py INSTRUCTIONS: {len(INSTRUCTIONS)} Zeichen - erst kuerzen, dann anheben")


def test_projektanweisung_liegt_als_eigene_datei_vor():
    """Die Datei IST die Quelle - fuer die Website, den Eval-Harness, das Kopier-Skript
    und diesen Test. Faellt sie weg oder wird sie leer, muss das hier auffallen und nicht
    erst als leerer Abschnitt auf der Seite der Runde."""
    datei = pathlib.Path(__file__).resolve().parents[1] / "config" / "projektanweisung.md"
    assert datei.exists(), "config/projektanweisung.md fehlt"
    text = datei.read_text(encoding="utf-8").strip()
    assert text.startswith("Du hilfst unserer D&D-Runde")
    assert len(text) > 3000, "verdaechtig kurz - versehentlich gekuerzt?"
    assert stil.projektanweisung() == text          # eine Quelle, kein Abschreiben
