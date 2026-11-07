"""Schreibt constraints.txt aus dem `pip freeze` eines geprueften Pi-Images.

WARUM (M9): requirements.txt pinnt nur die direkten Abhaengigkeiten. Die rund 90
transitiven Pakete loeste pip bei jedem Rebuild neu auf - zwei Builds desselben Commits
konnten verschiedene Images ergeben. constraints.txt haelt sie auf dem Stand fest, der
Golden-Suite und check-pi auf dem Pi bestanden hat. Sie entsteht auf dem Pi, nicht auf
dem Mac: Ein Mac-Freeze fuer ein ARM64/py3.12-Image waere geraten.

Die direkten Pins bleiben allein in requirements.txt. Stuenden sie in beiden Dateien,
muesste jeder Bump zwei Stellen treffen; so blockiert ein veralteter Constraint nur
dann, wenn ein Bump auch eine transitive Abhaengigkeit anhebt - und dann laut beim
Build, nicht still.

Aufruf:  ssh <pi> 'docker exec foliant-mcp pip freeze' \
             | python deploy/constraints_schreiben.py > constraints.txt
Ueblicher Weg: `make constraints-pi` (laeuft nach `make deploy-pi FREI=1` von selbst).
"""

import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

KOPF = """\
# Foliant - transitive Abhaengigkeiten des Laufzeit-Images, festgehalten aus dem
# `pip freeze` eines Pi-Builds, der Golden-Suite und check-pi bestanden hat (M9).
# NICHT von Hand pflegen: `make constraints-pi` schreibt die Datei neu.
# Die direkten Pins stehen nur in requirements.txt.
"""


def normiert(name: str) -> str:
    """Paketname nach PEP 503 - `pymupdf_layout` und `PyMuPDF-Layout` sind dasselbe."""
    return re.sub(r"[-_.]+", "-", name).lower()


def paketname(zeile: str) -> str:
    """Name vor Extras, Versionsangabe oder Kommentar."""
    return normiert(re.split(r"[\[=<>!~;\s#]", zeile.strip(), maxsplit=1)[0])


def direkte_pakete(pfad: Path = WURZEL / "requirements.txt") -> set[str]:
    zeilen = pfad.read_text(encoding="utf-8").splitlines()
    return {paketname(z) for z in zeilen if z.strip() and not z.lstrip().startswith("#")}


def constraints(freeze: str, direkt: set[str]) -> str:
    zeilen = sorted(
        (z.strip() for z in freeze.splitlines()
         if "==" in z and paketname(z) not in direkt),
        key=paketname,
    )
    return KOPF + "\n".join(zeilen) + "\n"


if __name__ == "__main__":
    eingabe = sys.stdin.read()
    if "==" not in eingabe:
        sys.exit("FEHLER: keine `pip freeze`-Ausgabe auf stdin - constraints.txt bleibt.")
    sys.stdout.write(constraints(eingabe, direkte_pakete()))
