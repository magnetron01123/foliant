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

import re
import sqlite3

# Rueckfall, wenn ein Aufrufer keine Prioritaet mitbringt. Entspricht dem DEFAULT in
# db/schema.sql - die Zahl steht bewusst am hinteren Ende: eine Quelle ohne bewusst
# gesetzte Wertigkeit soll vorhandene Quellen nicht verdraengen (Q2).
STANDARD_PRIORITAET = 100

# --- Beschriftungs-Standard fuer Quellen ------------------------------------------
# EINE Quelle wird ueberall mit denselben drei Angaben beschrieben, jede an ihrem
# eigenen Platz:
#   1. `titel`   - der WERKTITEL des Buches, so wie es sich selbst nennt. Sonst nichts.
#   2. `sprache` - 'de' | 'en'      -> Anzeige "Deutsch" / "Englisch"
#   3. `edition` - '2024' | '2014'  -> Anzeige "Regeln 2024" / "Regeln 2014"
#
# Der Standard entstand aus einem konkreten Befund: jeder Importweg hing einen ANDEREN
# Klammer-Zusatz an denselben Werktitel ("SRD 5.2.1 (Deutsch)", "Player's Handbook
# (D&D Beyond)", "Basic Rules (2014) (D&D Beyond)", "Spielerhandbuch (Deutsch, 2014er
# Regeln)"). Die Zusaetze wiederholten nur, was `sprache`, `edition` und `herkunft`
# ohnehin als eigene Spalten tragen - und weil jeder Weg es anders tat, waren die
# Quellen nebeneinander nicht mehr vergleichbar.
#
# Die Positivliste ist bewusst eng: Was hier nicht steht, bleibt am Titel. Lieber ein
# ungekuerzter Titel als ein abgeschnittener Werkname - "Monstrous Compendium Vol. 1
# (Spelljammer Creatures)" muss seinen Zusatz behalten.
_TITEL_ZUSATZ = {
    "deutsch", "englisch", "english", "de", "en",
    "d&d beyond", "dnd beyond", "ddb", "open5e", "druck", "pdf", "scan",
    "2014", "2024", "2014er regeln", "2024er regeln",
}
_KLAMMER_AM_ENDE = re.compile(r"\s*\(([^()]*)\)\s*$")


def werktitel(titel: str) -> str:
    """Werktitel nach dem Beschriftungs-Standard: ohne die Zusaetze, die Sprache,
    Regelversion oder Bezugsweg doppeln.

    Entfernt wird nur am ENDE und nur, wenn JEDER kommagetrennte Teil der Klammer in der
    Positivliste steht - "Curse of Strahd: Character Options (D&D Beyond)" verliert die
    Herkunft, "Monstrous Compendium Vol. 1 (Spelljammer Creatures)" behaelt seinen
    Zusatz. Mehrfach angewandt, weil manche Titel zwei Klammern tragen ("(2014) (D&D
    Beyond)"). Der gerade Apostroph wird zum typografischen: derselbe Verlag schreibt
    "Player's" und "Player's", und nebeneinander liest sich das wie ein Fehler.
    """
    rest = " ".join((titel or "").split()).replace("'", "’")
    while True:
        treffer = _KLAMMER_AM_ENDE.search(rest)
        if not treffer:
            return rest
        teile = [t.strip().lower() for t in treffer.group(1).split(",")]
        if not teile or not all(t in _TITEL_ZUSATZ for t in teile):
            return rest
        gekuerzt = rest[:treffer.start()].strip()
        if not gekuerzt:                 # Titel BESTEHT nur aus dem Zusatz -> unangetastet
            return rest
        rest = gekuerzt


def normalisiere_titel(con: sqlite3.Connection) -> int:
    """Bestehende Quellen auf den Standard ziehen; liefert die Zahl der geaenderten Zeilen.

    Noetig, weil `registriere_quelle` nur beim IMPORT laeuft: die Titel im Bestand stammen
    aus der Zeit davor und wuerden erst beim naechsten Re-Import gerade gezogen - fuer ein
    DDB-Buch also womoeglich nie. Idempotent und billig (eine Handvoll Zeilen), committet
    bewusst nicht selbst (der Aufrufer haelt die Transaktion).

    Ohne `titel`-Spalte passiert nichts: der Aufrufer ist die Schema-Nachruestung, und
    eine dort geworfene Ausnahme wuerde deren restliche Schritte mit abbrechen."""
    spalten = {r[1] for r in con.execute("PRAGMA table_info(quellen)")}
    if "titel" not in spalten:
        return 0
    aenderungen = [(neu, kuerzel) for kuerzel, alt in con.execute(
        "SELECT kuerzel, titel FROM quellen").fetchall()
        if (neu := werktitel(alt)) != alt]
    con.executemany("UPDATE quellen SET titel = ? WHERE kuerzel = ?", aenderungen)
    return len(aenderungen)

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
    # Beschriftungs-Standard hier und nicht in der Anzeige: sonst muesste ihn jede
    # Ausgabe (Website, Belegzeile, admin) einzeln nachbauen - und die Fassungen liefen
    # wieder auseinander, genau wie zuvor die drei INSERTs.
    titel = werktitel(titel)
    zuweisungen = ", ".join(f"{s}=excluded.{s}" for s in _AKTUALISIERT)
    con.execute(
        "INSERT INTO quellen (kuerzel, titel, sprache, edition, herkunft, lizenz, "
        "prioritaet, dateipfad, inhaltsart) VALUES (?,?,?,?,?,?,?,?,?) "
        f"ON CONFLICT(kuerzel) DO UPDATE SET {zuweisungen}",
        (kuerzel, titel, sprache, edition, herkunft, lizenz, prioritaet, dateipfad,
         inhaltsart))
    return con.execute("SELECT id FROM quellen WHERE kuerzel = ?", (kuerzel,)).fetchone()[0]
