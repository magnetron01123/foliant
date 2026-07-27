"""Die Glossar-Import-Kette in cmd_import ruft ein Dutzend Seeder auf, deren Importe
INNERHALB der Funktion stehen - ein fehlender Name faellt deshalb erst zur Laufzeit auf,
nach Minuten echter Arbeit (real passiert 27.07.2026: der Zauber-Seeder war eingereiht,
aber nicht importiert; der Lauf brach nach dem Gegenstands-Abgleich mit NameError ab).
Kein anderer Test beruehrt diesen Pfad - dieser schon, rein statisch."""
import ast
import pathlib

_ADMIN = pathlib.Path(__file__).resolve().parents[1] / "app" / "admin.py"


def _funktion(baum, name):
    return next(k for k in ast.walk(baum)
                if isinstance(k, ast.FunctionDef) and k.name == name)


def test_cmd_import_ruft_nur_importierte_seeder():
    baum = ast.parse(_ADMIN.read_text(encoding="utf-8"))
    fn = _funktion(baum, "cmd_import")

    importiert = {alias.asname or alias.name
                  for knoten in ast.walk(fn) if isinstance(knoten, ast.ImportFrom)
                  for alias in knoten.names}
    lokal = {z.id for k in ast.walk(fn) if isinstance(k, ast.Assign)
             for z in ast.walk(k.targets[0]) if isinstance(z, ast.Name)}

    aufgerufen = {k.func.id for k in ast.walk(fn)
                  if isinstance(k, ast.Call) and isinstance(k.func, ast.Name)
                  and (k.func.id.startswith(("seed_", "kanonisiere_", "repariere_")))}
    fehlend = aufgerufen - importiert - lokal
    assert not fehlend, f"in cmd_import aufgerufen, aber nicht importiert: {sorted(fehlend)}"
    assert "seed_zauber_bruecke_aus_bestand" in aufgerufen, "Zauber-Seeder nicht eingereiht"


def test_alle_importierten_seeder_existieren_wirklich():
    """Zweite Haelfte: der Name steht im Import - gibt es die Funktion auch?"""
    import importer.import_glossar as ig

    baum = ast.parse(_ADMIN.read_text(encoding="utf-8"))
    fn = _funktion(baum, "cmd_import")
    for knoten in ast.walk(fn):
        if isinstance(knoten, ast.ImportFrom) and knoten.module == "importer.import_glossar":
            for alias in knoten.names:
                assert hasattr(ig, alias.name), f"importer.import_glossar.{alias.name} fehlt"
