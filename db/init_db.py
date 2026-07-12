#!/usr/bin/env python3
"""Foliant — Datenbank initialisieren (nur Standardbibliothek).
Aufruf:  python db/init_db.py [pfad/zur/foliant.sqlite]
"""
from __future__ import annotations
import sqlite3, sys
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")

def init_db(db_path: str | Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        # DELETE-Journal: MVP hat einen Zugang; kompatibel mit späteren read-only
        # Container-Mounts (Rollen-Trennung). Bei Bedarf auf 'WAL' ändern.
        con.execute("PRAGMA journal_mode=DELETE;")
        con.execute("PRAGMA foreign_keys=ON;")
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
        # Schema-Version (codex TECH-019): Grundlage fuer kuenftige Migrationen. v2 =
        # quellen.inhaltsart + CHECK-Constraints (siehe schema.sql-Kopf).
        con.execute("PRAGMA user_version = 2;")
        con.commit()
    finally:
        con.close()
    print(f"OK: Schema angelegt in {db_path}")

if __name__ == "__main__":
    init_db(sys.argv[1] if len(sys.argv) > 1 else "data/foliant.sqlite")
