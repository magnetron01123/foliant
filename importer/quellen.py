"""Das Quellen-Register: der EINE Weg, eine Quelle anzulegen oder aufzufrischen.

Bis zum 31.07.2026 stand derselbe `INSERT INTO quellen ... ON CONFLICT` dreimal im Repo -
in `app/admin.py` (PDF-/Markdown-Weg), `importer/import_ddb.py` und
`importer/import_open5e.py`. Die drei Fassungen waren bereits AUSEINANDERGELAUFEN: Open5e
schrieb nur sieben Spalten und liess `dateipfad` und `inhaltsart` aus, die anderen beiden
neun. Eine neue Spalte in `quellen` haette an drei Stellen nachgezogen werden muessen, und
nichts haette gemeldet, wenn eine vergessen worden waere.

Praktische Folge derselben Streuung: `prioritaet` wurde an vier Stellen unabhaengig
vergeben (Config-Vorlage 10/20/60, DDB fest 40, Open5e 60+Laufindex, Admin-Rueckfall 100),
ohne dass irgendwo stuende, warum eine Zahl so ausfaellt. Die Frage nach der
QUELLEN-WERTIGKEIT (BACKLOG.md par. 4) ist damit nicht beantwortet - aber sie ist jetzt an
EINER Stelle beantwortbar: hier.

Was hier NICHT passiert: Eintraege schreiben, loeschen, committen. Die Funktion ist ein
Baustein INNERHALB der Import-Transaktion des Aufrufers (A7) - sie committet bewusst nicht
selbst, sonst zerrisse sie genau die Atomaritaet, die jeder Importweg zusagt.
"""
from __future__ import annotations

import sqlite3

# Rueckfall, wenn ein Aufrufer keine Prioritaet mitbringt. Entspricht dem DEFAULT in
# db/schema.sql - die Zahl steht bewusst am hinteren Ende: eine Quelle ohne bewusst
# gesetzte Wertigkeit soll vorhandene Quellen nicht verdraengen (Q2).
STANDARD_PRIORITAET = 100

# Alle veraenderbaren Spalten werden beim Upsert aufgefrischt (A8). Sonst behaelt eine
# bestehende Quelle stillschweigend alte Lizenz, Prioritaet oder Herkunft - und bei
# `inhaltsart` waere das ein stehengebliebener Spoiler-Status.
_AKTUALISIERT = ("titel", "sprache", "edition", "herkunft", "lizenz", "prioritaet",
                 "dateipfad", "inhaltsart")


def registriere_quelle(con: sqlite3.Connection, *, kuerzel: str, titel: str, sprache: str,
                       edition: str, herkunft: str, lizenz: str | None = None,
                       prioritaet: int = STANDARD_PRIORITAET,
                       dateipfad: str | None = None,
                       inhaltsart: str = "regelwerk") -> int:
    """Quelle anlegen oder auffrischen; liefert die `quellen.id`.

    `edition` ist Pflicht und wird NICHT geraten (V1/Q3) - wer keine hat, importiert nicht.
    `inhaltsart` traegt die Spoiler-Kennzeichnung bis in die Tool-Ausgaben (SYN-P0-007);
    der Default 'regelwerk' gilt nur, wo der Aufrufer nachweislich ein Regelwerk hat.

    Nur Schluesselwort-Argumente: Bei neun gleichartigen Feldern ist eine vertauschte
    Reihenfolge (sprache/edition, titel/kuerzel) ein Fehler, den kein Test zuverlaessig
    faengt - der Import laeuft durch und schreibt Unsinn in die Provenienz."""
    if not (edition or "").strip():
        raise ValueError(f"Quelle {kuerzel!r} ohne Regelversion - Import abgelehnt (Q3/T11).")
    zuweisungen = ", ".join(f"{s}=excluded.{s}" for s in _AKTUALISIERT)
    con.execute(
        "INSERT INTO quellen (kuerzel, titel, sprache, edition, herkunft, lizenz, "
        "prioritaet, dateipfad, inhaltsart) VALUES (?,?,?,?,?,?,?,?,?) "
        f"ON CONFLICT(kuerzel) DO UPDATE SET {zuweisungen}",
        (kuerzel, titel, sprache, edition, herkunft, lizenz, prioritaet, dateipfad,
         inhaltsart))
    return con.execute("SELECT id FROM quellen WHERE kuerzel = ?", (kuerzel,)).fetchone()[0]
