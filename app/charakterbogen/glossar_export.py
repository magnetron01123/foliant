"""Exportiert NUR die Glossar-Tabelle in eine eigene SQLite-DB für den Web-Container.

Sicherheit (AUFTRAG §10): der Web-Container darf die volle Foliant-DB (mit privaten
Buchinhalten) NICHT sehen. Er braucht aber die Begriffs-Terminologie. Diese kleine DB
enthält ausschließlich die `glossar`-Tabelle (öffentliche Begriffspaare) — read-only ins
Web gemountet.

Aufruf (auf dem Pi, im foliant-Container mit Zugriff auf data/):
    docker compose exec foliant python -m app.charakterbogen.glossar_export \\
        /app/data/foliant.sqlite /app/data/glossar_web.sqlite
"""
from __future__ import annotations

import sqlite3
import sys


def exportiere(quelle: str, ziel: str) -> int:
    src = sqlite3.connect(quelle)
    try:
        spalten = [r[1] for r in src.execute("PRAGMA table_info(glossar)")]
        if not spalten:
            raise SystemExit(f"FEHLER: keine 'glossar'-Tabelle in {quelle}")
        zeilen = src.execute("SELECT * FROM glossar").fetchall()
    finally:
        src.close()

    dst = sqlite3.connect(ziel)
    try:
        dst.execute("DROP TABLE IF EXISTS glossar")
        dst.execute(f"CREATE TABLE glossar ({', '.join(spalten)})")
        platz = ", ".join("?" for _ in spalten)
        dst.executemany(f"INSERT INTO glossar VALUES ({platz})", zeilen)
        dst.commit()
    finally:
        dst.close()
    return len(zeilen)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Aufruf: python -m app.charakterbogen.glossar_export <foliant.sqlite> <glossar_web.sqlite>")
    n = exportiere(sys.argv[1], sys.argv[2])
    print(f"Glossar exportiert: {n} Zeilen -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
