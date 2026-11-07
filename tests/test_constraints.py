"""constraints.txt bleibt eine reine Liste transitiver Pins (M9, CONCEPT.md §2).

Steht ein direktes Paket auch dort, muss ein Bump zwei Dateien treffen - und wer nur
requirements.txt anhebt, bekommt einen Build-Abbruch, dessen Ursache nicht im Diff steht.
Eine Zeile ohne `==` waere kein Pin, sondern eine Rate-Erlaubnis fuer pip.
"""
from deploy.constraints_schreiben import WURZEL, constraints, direkte_pakete, paketname


def _pins() -> list[str]:
    text = (WURZEL / "constraints.txt").read_text(encoding="utf-8")
    return [z for z in text.splitlines() if z.strip() and not z.startswith("#")]


def test_constraints_enthalten_keine_direkten_pakete():
    doppelt = {paketname(z) for z in _pins()} & direkte_pakete()
    assert not doppelt, f"Direkt gepinnt UND in constraints.txt: {sorted(doppelt)}"


def test_jede_constraint_zeile_ist_ein_exakter_pin():
    lose = [z for z in _pins() if "==" not in z]
    assert not lose, f"Kein exakter Pin in constraints.txt: {lose}"


def test_generator_filtert_direkte_pakete_trotz_schreibweise():
    freeze = "PyMuPDF==2.0\npymupdf_layout==2.0\nfastmcp-slim==4.1.5\n"
    ergebnis = constraints(freeze, {"pymupdf"})
    assert "PyMuPDF==2.0" not in ergebnis
    assert "fastmcp-slim==4.1.5" in ergebnis
    assert "pymupdf_layout==2.0" in ergebnis
