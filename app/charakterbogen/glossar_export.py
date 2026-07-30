"""Exportiert Glossar UND Quellen-Metadaten in eine eigene SQLite-DB für den Web-Container.

Sicherheit (SPEC.md §14): der Web-Container darf die volle Foliant-DB (mit privaten
Buchinhalten) NICHT sehen. Er braucht aber die Begriffs-Terminologie — und seit dem
30.07.2026 auch die Liste der geladenen Bücher, damit die Runde nachschauen kann, was
im Bestand steht, statt zu raten.

Was hier NICHT hineinkommt, ist die eigentliche Grenze:
- kein `eintraege`-Inhalt (das ist der private Buchtext),
- kein `dateipfad` (Pfade auf dem Wirt gehören nicht ins Web),
- keine internen Felder (`id`, `prioritaet`) — sie sagen der Runde nichts und wären
  nur eine weitere Stelle, die driften kann.
Es bleiben Titel, Sprache, Regelversion, Herkunft, Lizenz, Inhaltsart und die ZAHL der
Einträge. Alles davon steht ohnehin in jeder Auskunft, die der Server gibt.

Bewusst OHNE Abhängigkeit auf app.db (Betriebszusage, CONCEPT.md §12): diese Datei muss
mit dem System-Python des Wirts laufen, BEVOR der web-Container startet — sonst legt
Docker ein Verzeichnis statt der Datei an. `app.admin` zöge über app.db u. a. tomllib
und rapidfuzz nach und liefe dort nicht. Deshalb nur sqlite3 und sys.

Aufruf (auf dem Pi, im foliant-Container mit Zugriff auf data/):
    docker compose exec foliant python -m app.charakterbogen.glossar_export \\
        /app/data/foliant.sqlite /app/data/glossar_web.sqlite
Nach jedem `admin import` passiert das automatisch (app/admin.py).
"""
from __future__ import annotations

import sqlite3
import sys

# Die Quellen-Spalten, die ins Web dürfen - als Positivliste, nicht als Ausschluss:
# eine neue interne Spalte in `quellen` landet damit NICHT versehentlich im Web.
QUELLEN_SPALTEN = ("kuerzel", "titel", "sprache", "edition", "herkunft", "lizenz",
                   "inhaltsart")


def _kopiere_glossar(src: sqlite3.Connection, dst: sqlite3.Connection) -> int:
    spalten = [r[1] for r in src.execute("PRAGMA table_info(glossar)")]
    if not spalten:
        raise SystemExit("FEHLER: keine 'glossar'-Tabelle in der Quelle")
    zeilen = src.execute("SELECT * FROM glossar").fetchall()
    dst.execute("DROP TABLE IF EXISTS glossar")
    dst.execute(f"CREATE TABLE glossar ({', '.join(spalten)})")
    platz = ", ".join("?" for _ in spalten)
    dst.executemany(f"INSERT INTO glossar VALUES ({platz})", zeilen)
    return len(zeilen)


def _kopiere_quellen(src: sqlite3.Connection, dst: sqlite3.Connection) -> int:
    """Quellen-Metadaten plus Eintragszahl. Fehlt die Spalte `inhaltsart` (Bestands-DB
    vor der v2-Migration), wird sie als NULL gefuehrt statt den Export zu sprengen."""
    vorhanden = {r[1] for r in src.execute("PRAGMA table_info(quellen)")}
    if not vorhanden:
        raise SystemExit("FEHLER: keine 'quellen'-Tabelle in der Quelle")
    felder = [s if s in vorhanden else f"NULL AS {s}" for s in QUELLEN_SPALTEN]
    zeilen = src.execute(
        f"SELECT {', '.join('q.' + f if ' AS ' not in f else f for f in felder)}, "
        f"       count(e.id) AS eintraege "
        f"FROM quellen q LEFT JOIN eintraege e ON e.quelle_id = q.id "
        f"GROUP BY q.id ORDER BY q.prioritaet, q.titel").fetchall()
    dst.execute("DROP TABLE IF EXISTS quellen")
    dst.execute(f"CREATE TABLE quellen ({', '.join(QUELLEN_SPALTEN)}, eintraege INTEGER)")
    platz = ", ".join("?" for _ in range(len(QUELLEN_SPALTEN) + 1))
    dst.executemany(f"INSERT INTO quellen VALUES ({platz})", zeilen)
    return len(zeilen)


def exportiere(quelle: str, ziel: str) -> tuple[int, int]:
    """(Glossarzeilen, Quellen). Beides in EINER Transaktion - eine halb geschriebene
    Web-DB waere schlimmer als eine veraltete."""
    src = sqlite3.connect(f"file:{quelle}?mode=ro", uri=True)
    dst = sqlite3.connect(ziel)
    try:
        with dst:
            n_glossar = _kopiere_glossar(src, dst)
            n_quellen = _kopiere_quellen(src, dst)
    finally:
        src.close()
        dst.close()
    return n_glossar, n_quellen


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Aufruf: python -m app.charakterbogen.glossar_export "
                         "<foliant.sqlite> <glossar_web.sqlite>")
    n_glossar, n_quellen = exportiere(sys.argv[1], sys.argv[2])
    print(f"Web-DB geschrieben: {n_glossar} Glossarzeilen, {n_quellen} Quellen "
          f"-> {sys.argv[2]}")


if __name__ == "__main__":
    main()
