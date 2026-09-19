"""Restore-Probe: aus einer Sicherung zurueckspielen und beweisen, dass sie traegt.

WARUM (M9/R13): CONCEPT.md §8 schreibt die Probe seit Monaten vor, und es gibt keinen
Beleg, dass sie je gelaufen ist. Eine Sicherung, aus der noch nie jemand zurueckgespielt
hat, ist eine Vermutung - `integrity_check` sagt nur, dass die Datei nicht zerrissen ist,
nicht dass der Bestand vollstaendig und bedienbar daraus hervorgeht.

Die Probe faehrt deshalb keine Dateipruefung, sondern die ECHTEN Lesewege:
  1. Integritaet und Zeilenzahlen (billig, faengt die groben Faelle)
  2. `admin check` gegen den wiederhergestellten Stand - dieselbe Datenqualitaets-
     Pruefung wie im Deploy, inkl. der Qualitaets-Basiswerte
  3. die Golden-Suite - Regel-Semantik am wiederhergestellten Korpus
  4. den Such-Benchmark - findet der zurueckgespielte Bestand noch, was er soll?

Schritt 3 und 4 sind der eigentliche Punkt: Sie beweisen, dass aus der Sicherung ein
ARBEITSFAEHIGER Bestand wird, nicht nur eine lesbare Datei.

Die Probe fasst NICHTS an: Sie kopiert in ein temporaeres Verzeichnis und biegt
`db.standard_pfad` dorthin um. Die bediente Datenbank und `config/foliant.toml` bleiben
unberuehrt - eine Wiederherstellungs-Uebung, die den Produktionsstand ueberschreiben
koennte, waere selbst das groesste Risiko im Verfahren.

EINE Fehlerklasse ist KEIN Defekt der Sicherung: Ist der CODE neuer als der gesicherte
Stand, koennen Golden-Tests fehlschlagen, die frische Kuration voraussetzen. Beim ersten
Lauf am 19.09.2026 passierte genau das - die Sicherung stammte von VOR dem Glossar-Lauf,
und `test_golden_grapple_liefert_die_regel_nicht_das_talent` fiel durch, weil die
Suchvariante darin noch fehlte. Die Probe gehoert deshalb gegen eine Sicherung gefahren,
die zum Code passt; deploy/sicherung_holen.sh erzeugt sie sich zu Beginn selbst.

Aufruf:  .venv/bin/python deploy/restore_probe.py <sicherung.sqlite>
         make restore-probe DATEI=<pfad>
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))


def _stufe(nummer: int, titel: str) -> None:
    print(f"\n=== {nummer}. {titel}")


def pruefe_datei(pfad: Path) -> bool:
    _stufe(1, "Integritaet und Umfang")
    con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    try:
        integ = con.execute("PRAGMA integrity_check").fetchone()[0]
        eintraege = con.execute("SELECT count(*) FROM eintraege").fetchone()[0]
        fts = con.execute("SELECT count(*) FROM eintraege_fts").fetchone()[0]
        quellen = con.execute("SELECT count(*) FROM quellen").fetchone()[0]
        glossar = con.execute("SELECT count(*) FROM glossar").fetchone()[0]
    finally:
        con.close()
    print(f"    integrity_check : {integ}")
    print(f"    Eintraege       : {eintraege}   (FTS: {fts})")
    print(f"    Quellen         : {quellen}")
    print(f"    Glossarzeilen   : {glossar}")
    ok = integ == "ok" and eintraege > 0 and eintraege == fts and quellen > 0
    # Das Glossar ist kein Nebenwert: Ohne es faellt Deutsch-first aus, und die
    # Suchbruecken auch. Eine Sicherung ohne Glossar ist technisch heil und fachlich
    # unbrauchbar - genau der Unterschied, den eine blosse Dateipruefung nicht sieht.
    if glossar == 0:
        print("    FEHLER: Glossar ist leer - Deutsch-first und die Suchbruecken fehlen.")
        ok = False
    print("    " + ("INTAKT" if ok else "FEHLGESCHLAGEN"))
    return ok


def fahre_pruefungen(db: Path) -> bool:
    """`admin check`, Golden-Suite und Benchmark gegen den wiederhergestellten Stand.

    Ueber eine Kindprozess-Umgebung statt eines Monkeypatch im selben Prozess: pytest
    laedt die Module selbst, und ein hier gesetzter Patch waere dort nicht wirksam.
    `FOLIANT_DB_PROBE` liest `db.standard_pfad` (nur fuer diesen Zweck)."""
    import os

    umgebung = {**os.environ, "FOLIANT_DB_PROBE": str(db), "PYTHONPATH": str(WURZEL)}
    python = WURZEL / ".venv" / "bin" / "python"
    if not python.exists():
        python = Path(sys.executable)

    erfolg = True
    for nummer, titel, befehl in (
            (2, "admin check gegen den wiederhergestellten Stand",
             [str(python), "-m", "app.admin", "check"]),
            (3, "Golden-Suite (Regel-Semantik am wiederhergestellten Korpus)",
             [str(python), "-m", "pytest", "-q", "tests/test_golden_bestand.py"]),
            (4, "Such-Benchmark",
             [str(python), "-m", "app.admin", "suchbenchmark"])):
        _stufe(nummer, titel)
        lauf = subprocess.run(befehl, cwd=WURZEL, env=umgebung,
                              capture_output=True, text=True)
        for zeile in (lauf.stdout or "").splitlines()[-8:]:
            print(f"    {zeile}")
        if lauf.returncode != 0:
            print(f"    FEHLGESCHLAGEN (Exitcode {lauf.returncode})")
            for zeile in (lauf.stderr or "").splitlines()[-5:]:
                print(f"    {zeile}")
            erfolg = False
    return erfolg


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    quelle = Path(sys.argv[1]).expanduser()
    if not quelle.exists():
        print(f"FEHLER: {quelle} gibt es nicht.")
        return 1

    print(f"Restore-Probe aus: {quelle}")
    print(f"Groesse          : {quelle.stat().st_size / 1024 / 1024:.0f} MiB")

    with tempfile.TemporaryDirectory(prefix="foliant-restore-") as tmp:
        ziel = Path(tmp) / "foliant.sqlite"
        print(f"Zurueckgespielt  : {ziel}")
        shutil.copyfile(quelle, ziel)

        if not pruefe_datei(ziel):
            print("\nERGEBNIS: FEHLGESCHLAGEN - die Sicherung traegt nicht.")
            return 1
        if not fahre_pruefungen(ziel):
            print("\nERGEBNIS: FEHLGESCHLAGEN - aus der Sicherung entsteht kein "
                  "arbeitsfaehiger Bestand.")
            return 1

    print("\nERGEBNIS: BESTANDEN - aus dieser Sicherung entsteht ein arbeitsfaehiger "
          "Bestand.")
    print("Datum, Dateiname und dieses Ergebnis gehoeren nach CONCEPT.md §8.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
