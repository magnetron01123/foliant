"""Gemeinsame Bausteine der Testsuite.

Bis zum 31.07.2026 leiteten 27 Testdateien den Pfad zu `db/schema.sql` jede fuer sich ab
(`Path(__file__).resolve().parent.parent / "db" / "schema.sql"`), und 28 riefen
`executescript` mit eigenem Rumpf. `tests/conftest.py` trug dabei genau eine Fixture. Die
Datenaufbauten der einzelnen Tests sind zu Recht verschieden - jeder braucht anderen
Bestand -, aber der Weg zum Schema ist es nicht.

Hier steht deshalb nur das wirklich Gemeinsame: wo das Schema liegt und wie man eine leere
Datenbank daraus baut. Alles Weitere bleibt beim jeweiligen Test.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
SCHEMA = WURZEL / "db" / "schema.sql"


def neue_db(pfad: str | Path) -> sqlite3.Connection:
    """Leere Datenbank mit dem echten Schema; offene Verbindung, NICHT committet.

    Bewusst ueber `sqlite3.connect` statt `app.db.connect`: Manche Tests pruefen genau,
    was `stelle_schema_sicher` auf einer rohen DB tut (tests/test_kontext_spalte.py) -
    liefe die Migration hier schon mit, waere der Test tautologisch."""
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    return con
