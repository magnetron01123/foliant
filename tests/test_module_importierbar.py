"""Jedes Projektmodul laesst sich importieren - der billigste Waechter gegen halb
gelandete Umbauten.

Anlass (Befund 31.07.2026): `evals/lasttest.py` war seit dem Modul-Split vom 30.07.2026
syntaktisch kaputt - beim Nachziehen der Importe war `from app.tools import suche as su`
ohne Einrueckung in `_mix()` gelandet. Die Datei ist der in BACKLOG.md par. 1/M3 als
B9-Regressionswaechter gefuehrte Lasttest (`make lasttest-pi`); sie faellt nur auf, wenn
jemand den Lasttest faehrt - und wer ihn faehrt, sitzt am Pi.

Kein Test importierte sie, also fiel es niemandem auf. Genau diese Luecke schliesst dieser
Test fuer ALLE Module: Ein Modul, das keinen Aufrufer im Testbestand hat, ist trotzdem
Code, der laufen soll.

Bewusst nur der Import, keine Ausfuehrung: es geht um Syntax und aufloesbare Namen auf
Modulebene, nicht um Verhalten (das pruefen die Fachtests). Module mit Abhaengigkeiten,
die nur in .venv-ddb liegen, werden uebersprungen - genau wie ihre Fachtests.
"""
from __future__ import annotations

import importlib
import pathlib
import py_compile

import pytest

_WURZEL = pathlib.Path(__file__).resolve().parents[1]
_PAKETE = ("app", "importer", "config", "evals", "db", "deploy")

# Module, deren Abhaengigkeiten bewusst NICHT in der Laufzeit-Umgebung liegen
# (requirements-ddb.txt, s. CONCEPT.md par. 10 ADR: SQLite3MC gehoert nie in die
# dauerhafte Runtime). Sie werden nur kompiliert, nicht importiert.
_NUR_KOMPILIEREN = ("importer.ddb_exporter",)


def _module() -> list[str]:
    namen = []
    for paket in _PAKETE:
        for pfad in sorted((_WURZEL / paket).rglob("*.py")):
            rel = pfad.relative_to(_WURZEL)
            if "__pycache__" in rel.parts:
                continue
            teile = list(rel.with_suffix("").parts)
            if teile[-1] == "__init__":
                teile = teile[:-1]
            if teile:
                namen.append(".".join(teile))
    return namen


@pytest.mark.parametrize("modul", _module(), ids=lambda m: m)
def test_modul_ist_syntaktisch_heil(modul):
    """Syntaxfehler faellt hier auf, nicht erst beim naechsten Pi-Lauf."""
    pfad = _WURZEL / pathlib.Path(*modul.split(".")).with_suffix(".py")
    if not pfad.exists():                      # Paketverzeichnis -> __init__.py
        pfad = _WURZEL / pathlib.Path(*modul.split(".")) / "__init__.py"
    py_compile.compile(str(pfad), doraise=True)


@pytest.mark.parametrize("modul", _module(), ids=lambda m: m)
def test_modul_laesst_sich_importieren(modul):
    """Aufloesbare Namen auf Modulebene. `db.init_db` und die Bot-/Server-Module haben
    Seiteneffekte beim Import (Argumente, Prints) - die sind harmlos und gewollt."""
    if modul.startswith(_NUR_KOMPILIEREN):
        pytest.importorskip("markdownify", reason="DDB-Exporter nur in .venv-ddb")
    try:
        importlib.import_module(modul)
    except ImportError as fehler:
        # Uebersprungen wird NUR eine fehlende Fremdabhaengigkeit (z. B. discord.py,
        # docling) - eine bewusst nicht installierte Umgebung ist kein Projektfehler.
        #
        # Ein Projektmodul, das sich nicht aufloesen laesst, ist dagegen genau der Fall,
        # fuer den dieser Waechter existiert: `from app.tools import weg` wirft ebenfalls
        # ImportError, und ein pauschales skip haette den halb gelandeten Umbau
        # durchgewunken statt ihn zu melden. `fehler.name` ohne Wert heisst: die Ursache
        # ist unbekannt - dann faellt der Test lieber zu Unrecht auf als zu Unrecht aus.
        fehlend = getattr(fehler, "name", None)
        if fehlend is None or fehlend.split(".")[0] in _PAKETE:
            raise
        pytest.skip(f"optionale Abhaengigkeit fehlt: {fehler}")
