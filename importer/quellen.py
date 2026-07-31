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
QUELLEN-WERTIGKEIT (BACKLOG.md par. 4) ist seit dem 31.07.2026 hier beantwortet: die
PRIORITAETSBAENDER unten sagen, welche Quellenklasse in welchem Zehnerbereich steht, die
Importe beziehen ihre Zahlen daraus, und `admin check` meldet Ausreisser.

Was hier NICHT passiert: Eintraege schreiben, loeschen, committen. Die Funktion ist ein
Baustein INNERHALB der Import-Transaktion des Aufrufers (A7) - sie committet bewusst nicht
selbst, sonst zerrisse sie genau die Atomaritaet, die jeder Importweg zusagt.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

# Rueckfall, wenn ein Aufrufer keine Prioritaet mitbringt. Entspricht dem DEFAULT in
# db/schema.sql - die Zahl steht bewusst am hinteren Ende: eine Quelle ohne bewusst
# gesetzte Wertigkeit soll vorhandene Quellen nicht verdraengen (Q2).
STANDARD_PRIORITAET = 100

# Die einzigen erlaubten Inhaltsklassen (db/schema.sql). Sie entscheiden ueber die
# Kennzeichnung bis in die Tool-Ausgaben (SYN-P0-007): Spoiler-Schutz beim Abenteuerband,
# Korrektur-Hinweis bei Errata, Auslegungs-Hinweis bei Sage Advice.
INHALTSARTEN = frozenset({"regelwerk", "abenteuer_setting", "errata", "regelauslegung"})

# --- Prioritaetsbaender -----------------------------------------------------------
# Die Antwort auf die oben aufgeworfene Frage nach der QUELLEN-WERTIGKEIT (Entscheidung
# 31.07.2026). Statt vier Stellen, die unabhaengig Zahlen vergaben, gibt es BAENDER: eine
# Quellenklasse belegt einen Zehnerbereich, innerhalb dessen ein Import fein sortieren
# darf (Open5e legt seinen Laufindex drauf, mehrere Kaufbuecher stehen nebeneinander).
#
# Die Reihenfolge folgt der Frage "welcher Text soll bei einer fachlichen Dublette den
# Ausschlag geben?" - also Q2/S10, Deutsch vor Englisch, offiziell vor abgeleitet:
#
#   10  deutsches Kernregelwerk 2024 (Kaufbuch)  - Obermenge des SRD UND am Tisch
#                                                  nachschlagbar; deshalb VOR dem SRD
#   20  deutsches SRD / freie deutsche Quellen   - offiziell, aber Teilmenge
#   30  deutsche Altbuecher 2014 (Scans)         - offiziell, aber aeltere Regelversion;
#                                                  Terminologie bleibt gueltig (V6/S7)
#   40  englische Kaufbuecher (DDB/PDF)          - vollstaendig, aber nicht deutsch
#   60  englische freie API-/SRD-Quellen         - abgeleitet, ohne Seitenzahlen
#   70  Errata und offizielle Regelauslegung     - ergaenzen den Grundtext, ersetzen ihn
#                                                  nie: sie duerfen ihn auch im Ranking
#                                                  nicht verdraengen
#  100  unklassifiziert (STANDARD_PRIORITAET)
#
# Bewusst offen gelassen: dass das gekaufte deutsche Vollbuch VOR dem deutschen SRD steht,
# ist eine Abwaegung, keine Naturkonstante. Dagegen spricht die Texttreue (das PHB kommt
# als OCR-Scan, das SRD als sauberes PDF). Sie ist umkehrbar, ohne dass etwas nachgezogen
# werden muss: eine Zahl in der Config und `admin quellen-auffrischen`.
BAND_DE_KERNREGELWERK = 10
BAND_DE_SRD = 20
BAND_DE_ALTBUCH = 30
BAND_EN_KAUFBUCH = 40
BAND_EN_FREI = 60
BAND_REVISION = 70
BAND_BREITE = 10          # ein Band reicht von seinem Startwert bis Start + BREITE - 1


def band_fuer(*, sprache: str, edition: str, herkunft: str,
              inhaltsart: str = "regelwerk", lizenz: str | None = None) -> int:
    """Das erwartete Prioritaets-BAND einer Quelle - Grundlage der Warnung in `admin check`.

    Bewusst eine Erwartung und kein Zwang: die Funktion sagt, wo eine Quelle nach ihrer
    Klasse staende. Weicht die Config ab, ist das eine Meldung wert, aber kein Fehler -
    es gibt legitime Feinsortierung innerhalb einer Klasse, und ein hartes Gate wuerde
    genau die Handbreite nehmen, die die Baender offen lassen sollen.

    Errata und Regelauslegung zuerst: ihre Klasse haengt an DEM, was sie sind, nicht an
    Sprache oder Bezugsweg - ein deutsches Errata bliebe eine Korrektur und duerfte den
    Grundtext trotzdem nicht ueberholen."""
    if inhaltsart in ("errata", "regelauslegung"):
        return BAND_REVISION
    if sprache == "de":
        if edition != "2024":
            return BAND_DE_ALTBUCH
        # Das SRD ist eine offizielle TEILMENGE des Kernregelwerks; unterschieden wird
        # an der Lizenz, weil genau sie den Unterschied ausmacht: frei weitergebbar
        # (CC-BY) gegen gekauftes Vollbuch ('privat').
        if (lizenz or "").upper().startswith("CC-BY"):
            return BAND_DE_SRD
        return BAND_DE_KERNREGELWERK
    return BAND_EN_FREI if herkunft in ("open5e",) else BAND_EN_KAUFBUCH


def band_passt(prioritaet: int, band: int) -> bool:
    """Liegt die vergebene Prioritaet in ihrem Band? (Start bis Start + BREITE - 1)"""
    return band <= prioritaet < band + BAND_BREITE

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
                 "dateipfad", "inhaltsart", "versions_stand", "quell_url", "quell_hash")
# `importiert_am` steht bewusst NICHT in _AKTUALISIERT, sondern haengt am Schalter
# `setze_importzeit` unten: sonst spraenge der Zeitstempel auch bei einer reinen
# Metadaten-Pflege (`admin quellen-auffrischen`, das keine einzige Datei liest) auf
# "jetzt" - und das Feld behauptete einen Import, den es nicht gab.


def registriere_quelle(con: sqlite3.Connection, *, kuerzel: str, titel: str, sprache: str,
                       edition: str, herkunft: str, lizenz: str | None = None,
                       prioritaet: int = STANDARD_PRIORITAET,
                       dateipfad: str | None = None,
                       inhaltsart: str = "regelwerk",
                       versions_stand: str | None = None,
                       quell_url: str | None = None,
                       quell_hash: str | None = None,
                       setze_importzeit: bool = True) -> int:
    """Quelle anlegen oder auffrischen; liefert die `quellen.id`.

    `edition` ist Pflicht und wird NICHT geraten (V1/Q3) - wer keine hat, importiert nicht.
    `inhaltsart` traegt die Kennzeichnung bis in die Tool-Ausgaben (SYN-P0-007);
    der Default 'regelwerk' gilt nur, wo der Aufrufer nachweislich ein Regelwerk hat.

    `versions_stand`, `quell_url` und `quell_hash` sind die Provenienz aus Schema v3 und
    optional - eine Quelle ohne sie bleibt gueltig, sie kann nur weniger ueber sich sagen.
    Sie stehen in `_AKTUALISIERT`, folgen also der A8-Regel: WAS DER AUFRUFER NICHT NENNT,
    WIRD GELEERT. Das ist bei einem Re-Import richtig (er baut die Quelle neu auf, ein
    stehengebliebener Errata-Stand waere eine Falschaussage), aber es heisst auch: wer nur
    einen Titel korrigieren will, nimmt `admin quellen-auffrischen` - das faellt bewusst
    auf den Bestandswert zurueck statt auf einen Standard.

    `importiert_am` ist bewusst KEIN durchgereichter Wert: es ist der Zeitpunkt DIESES
    Laufs, und ein Parameter waere nur eine Gelegenheit, ihn falsch zu setzen. Wer keine
    Quelldaten gelesen hat, setzt stattdessen `setze_importzeit=False` - dann bleibt der
    Zeitstempel des letzten echten Imports stehen, statt eine Datei-Lesung zu behaupten,
    die nicht stattgefunden hat (`admin quellen-auffrischen`).

    Nur Schluesselwort-Argumente: Bei zwoelf gleichartigen Feldern ist eine vertauschte
    Reihenfolge (sprache/edition, titel/kuerzel) ein Fehler, den kein Test zuverlaessig
    faengt - der Import laeuft durch und schreibt Unsinn in die Provenienz."""
    if not (edition or "").strip():
        raise ValueError(f"Quelle {kuerzel!r} ohne Regelversion - Import abgelehnt (Q3/T11).")
    # `db/schema.sql` traegt dafuer eine CHECK-Klausel - aber nur in FRISCH angelegten
    # Datenbanken. Wo die Spalte per ALTER TABLE nachkam (`db.stelle_schema_sicher`),
    # gibt es sie nicht; auf dem Pi am 31.07.2026 nachgesehen: keine CHECK-Klausel.
    # Genau dort waere ein Tippfehler am teuersten - alles ausser 'abenteuer_setting'
    # gilt als Regelwerk, ein verschriebenes 'abenteur_setting' naehme einem Band also
    # still den Spoiler-Schutz (SPEC.md par. 7). Dasselbe gilt seit v3 fuer 'errata' und
    # 'regelauslegung': ein Tippfehler machte eine Korrektur wieder zum Regeltext.
    if inhaltsart not in INHALTSARTEN:
        raise ValueError(
            f"Quelle {kuerzel!r} mit unbekannter inhaltsart {inhaltsart!r} - erlaubt ist "
            f"{' oder '.join(sorted(INHALTSARTEN))}. Import abgelehnt (SYN-P0-007).")
    # Beschriftungs-Standard hier und nicht in der Anzeige: sonst muesste ihn jede
    # Ausgabe (Website, Belegzeile, admin) einzeln nachbauen - und die Fassungen liefen
    # wieder auseinander, genau wie zuvor die drei INSERTs.
    titel = werktitel(titel)
    importiert_am = datetime.now(timezone.utc).isoformat(timespec="seconds")
    felder = _AKTUALISIERT + ("importiert_am",) if setze_importzeit else _AKTUALISIERT
    zuweisungen = ", ".join(f"{s}=excluded.{s}" for s in felder)
    con.execute(
        "INSERT INTO quellen (kuerzel, titel, sprache, edition, herkunft, lizenz, "
        "prioritaet, dateipfad, inhaltsart, importiert_am, versions_stand, quell_url, "
        "quell_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
        f"ON CONFLICT(kuerzel) DO UPDATE SET {zuweisungen}",
        (kuerzel, titel, sprache, edition, herkunft, lizenz, prioritaet, dateipfad,
         inhaltsart, importiert_am, versions_stand, quell_url, quell_hash))
    return con.execute("SELECT id FROM quellen WHERE kuerzel = ?", (kuerzel,)).fetchone()[0]
