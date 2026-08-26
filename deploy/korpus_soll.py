"""Den Korpus-Sollstand aus einem Manifest erneuern - Eingabe auf STDIN, Ziel im Repo.

Gegenstueck zu `admin check --vollbestand`: Dort wird verglichen, hier wird der
Vergleichsmassstab nachgezogen, nachdem ein Import BEABSICHTIGT etwas veraendert hat.

Warum als Programm und nicht als Makefile-Einzeiler: Der Aufruf laeuft ueber eine
SSH-Pipe, und das Ergebnis ist eine Datei, die in den Commit gehoert. Beides in eine
Shell-Zeile mit verschachtelten Anfuehrungszeichen zu pressen, macht sie unlesbar - und
unlesbar heisst hier: niemand merkt, wenn sie das Falsche schreibt.

Buchtitel werden bewusst NICHT uebernommen. Ob DDB-Titel im oeffentlichen Repo stehen
duerfen, ist offen (BACKLOG M9); die Kuerzel stehen ohnehin schon darin.

    ssh $PI '... admin manifest' | .venv/bin/python deploy/korpus_soll.py
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

ZIEL = pathlib.Path(__file__).resolve().parents[1] / "config" / "korpus_soll.json"

FELDER = ("kuerzel", "edition", "sprache", "inhaltsart", "eintraege")


def erneuere(manifest: dict, ziel: pathlib.Path, heute: str) -> dict:
    """Schreibt den neuen Sollstand und gibt ihn zurueck.

    Die erklaerenden `_`-Felder der bestehenden Datei bleiben erhalten - sie sind der
    Grund, warum jemand die Datei ueberhaupt versteht, und werden hier nicht neu erfunden.
    """
    soll = json.loads(ziel.read_text("utf-8")) if ziel.exists() else {}
    soll.update({
        "erhoben_an": heute,
        "schema_version": manifest["schema_version"],
        "eintraege_gesamt": manifest["eintraege_gesamt"],
        "glossar_zeilen": manifest["glossar_zeilen"],
        "quellen": [
            {"kuerzel": q["kuerzel"], "edition": q["edition"], "sprache": q["sprache"],
             "inhaltsart": q.get("inhaltsart", "regelwerk"), "eintraege": q["n"]}
            for q in manifest["quellen"]
        ],
    })
    ziel.write_text(json.dumps(soll, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return soll


def main() -> int:
    roh = sys.stdin.read().strip()
    if not roh:
        print("FEHLER: kein Manifest auf STDIN (lief `admin manifest` durch?)", file=sys.stderr)
        return 1
    try:
        manifest = json.loads(roh)
    except json.JSONDecodeError as fehler:
        print(f"FEHLER: STDIN ist kein JSON ({fehler}). Erste Zeile: {roh.splitlines()[0][:120]}",
              file=sys.stderr)
        return 1

    soll = erneuere(manifest, ZIEL, datetime.date.today().isoformat())
    print(f"Sollstand erneuert: {len(soll['quellen'])} Quellen, "
          f"{soll['eintraege_gesamt']} Eintraege -> {ZIEL.relative_to(ZIEL.parents[1])}")
    print("Die Datei gehoert in den Commit - sonst meldet der naechste `check-pi` "
          "dieselbe Abweichung erneut.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
