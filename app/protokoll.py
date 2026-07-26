"""Abfrage-Protokoll (O4/M5, Feedback & Iteration): protokolliert Nachschlage-Anfragen
serverseitig, damit `admin suchbericht` Glossar-/Synonym-Luecken datengetrieben sichtbar
macht (Nulltreffer, Fuzzy-Landungen, Mehrdeutigkeiten) statt auf Zufallsfunde zu warten.

Bewusst eine SEPARATE SQLite-Datei (Default data/foliant-protokoll.sqlite):
- Die Korpus-DB bleibt auf dem Serving-Pfad read-only (SYN-P1-005); ausserdem wuerden
  Writes dort den mtime-basierten Glossar-Cache und den inhalts_hash stoeren.
- data/ ist im Container read-write gemountet -> das Log ueberlebt Image-Rebuilds.
- Der Dateiname passt bewusst NICHT auf das Backup-Glob '<korpus-stem>-*.sqlite'.

Leitplanke: protokolliere() darf NIE eine Ausnahme in den Tool-Aufruf tragen - ein
fehlgeschlagener Log-Write verwirft den Eintrag, nie die fertige Antwort. Nach
_MAX_FEHLER Fehlschlaegen in Folge deaktiviert sich das Logging bis zum Neustart,
damit ein kaputter Pfad keine Dauerkosten pro Anfrage erzeugt."""
from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime, timezone

from app import db as _db

_SCHEMA = """
CREATE TABLE IF NOT EXISTS abfragen (
    id INTEGER PRIMARY KEY,
    zeitpunkt TEXT NOT NULL,
    werkzeug TEXT NOT NULL,
    suchbegriff TEXT,
    kategorie TEXT,
    edition TEXT,
    quelle_kuerzel TEXT,
    filter_json TEXT,
    anzahl_treffer INTEGER NOT NULL DEFAULT 0,
    suchweg TEXT NOT NULL DEFAULT '-',
    mehrdeutig INTEGER NOT NULL DEFAULT 0,
    gefunden INTEGER,
    dauer_ms INTEGER
);
"""

# Nach so vielen Fehlschlaegen IN FOLGE schaltet sich das Logging bis zum Neustart ab.
_MAX_FEHLER = 20
_fehler_in_folge = 0

# Rotation amortisiert statt pro Write: im Mittel prueft nur jeder 200. Write den Deckel.
_ROTATIONS_QUOTE = 200


def _konfig() -> dict:
    return _db.lade_konfig().get("protokoll", {})


def protokoll_aktiv() -> bool:
    return bool(_konfig().get("aktiv", True)) and _fehler_in_folge < _MAX_FEHLER


def protokoll_pfad():
    return _db.projekt_pfad(_konfig().get("pfad", "data/foliant-protokoll.sqlite"))


def max_zeilen() -> int:
    return int(_konfig().get("max_zeilen", 50_000))


def verbinde_lesend(pfad=None) -> sqlite3.Connection | None:
    """Read-only-Zugriff fuer den Bericht; None wenn (noch) kein Protokoll existiert."""
    pfad = pfad or protokoll_pfad()
    if not pfad.exists():
        return None
    con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _rotiere(con: sqlite3.Connection) -> None:
    """Groessen-Deckel: aelteste Zeilen ueber max_zeilen loeschen (id ist monoton)."""
    con.execute(
        "DELETE FROM abfragen WHERE id <= ("
        "  SELECT id FROM abfragen ORDER BY id DESC LIMIT 1 OFFSET ?)",
        (max_zeilen(),))


def protokolliere(werkzeug: str, suchbegriff: str | None = None,
                  kategorie: str | None = None, edition: str | None = None,
                  quelle_kuerzel: str | None = None, filter: dict | None = None,
                  anzahl_treffer: int = 0, suchweg: str = "-",
                  mehrdeutig: bool = False, gefunden: bool | None = None,
                  dauer_ms: float | None = None) -> None:
    """Fire-and-forget am ENDE des Tool-Bodies (nach dem Antwortbau) - darf nie werfen."""
    global _fehler_in_folge
    try:
        if not protokoll_aktiv():
            return
        filter_kompakt = {k: v for k, v in (filter or {}).items() if v is not None}
        con = sqlite3.connect(protokoll_pfad(), timeout=0.25)
        try:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA busy_timeout=250;")
            con.execute(_SCHEMA)
            con.execute(
                "INSERT INTO abfragen (zeitpunkt, werkzeug, suchbegriff, kategorie,"
                " edition, quelle_kuerzel, filter_json, anzahl_treffer, suchweg,"
                " mehrdeutig, gefunden, dauer_ms)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 werkzeug, suchbegriff, kategorie, edition, quelle_kuerzel,
                 json.dumps(filter_kompakt, ensure_ascii=False) if filter_kompakt else None,
                 int(anzahl_treffer), suchweg, int(bool(mehrdeutig)),
                 None if gefunden is None else int(bool(gefunden)),
                 None if dauer_ms is None else int(dauer_ms)))
            if random.randrange(_ROTATIONS_QUOTE) == 0:
                _rotiere(con)
            con.commit()
        finally:
            con.close()
        _fehler_in_folge = 0
    except Exception:
        # Bewusst schlucken: die Antwort ist laengst berechnet, das Log ist Beiwerk.
        _fehler_in_folge += 1
