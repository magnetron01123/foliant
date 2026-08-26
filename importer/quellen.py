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
#                                                  nachschlagbar; deshalb VOR dem SRD.
#                                                  NUR Kernregelwerke - ein Abenteuerband
#                                                  gehoert hier nicht hin
#   20  deutsches SRD, deutsche Ergaenzungs- und Abenteuerbaende 2024 - offiziell, aber
#                                                  kein Kernregeltext
#   40  englische Kaufbuecher (DDB/PDF)          - vollstaendig, aber nicht deutsch
#   60  englische freie API-/SRD-Quellen         - abgeleitet, ohne Seitenzahlen
#   70  Errata und offizielle Regelauslegung     - ergaenzen den Grundtext, ersetzen ihn
#                                                  nie: sie duerfen ihn auch im Ranking
#                                                  nicht verdraengen
#   80  deutsche Altbuecher 2014 (Scans)         - ganz hinten, s. u.
#  100  unklassifiziert (STANDARD_PRIORITAET)
#
# WARUM DIE DEUTSCHEN ALTBUECHER HINTEN STEHEN und nicht, wie man nach "Deutsch zuerst"
# (S10) vermuten wuerde, gleich hinter dem SRD: Ihr REGELINHALT ist die alte Fassung, und
# die Scans sind OCR-Text mit messbar schlechterer Qualitaet als jedes sauber importierte
# Buch. Ihr eigentlicher Wert liegt in der TERMINOLOGIE - und die laeuft ueber das Glossar
# (S7/V6), nicht ueber `prioritaet`. Der Produktions-Pi setzt sie deshalb seit jeher auf
# 80/85/90 und staffelt sie darin untereinander (PHB vor Xanathar vor Schwertkueste).
#
# Diese Zeilen standen bis zum 31.07.2026 falsch hier (Band 30, also VOR den englischen
# Kaufbuechern). Der Fehler entstand, weil die drei Buecher lokal gar nicht importiert sind
# - die Baender waren an einer Config kalibriert, die sie nicht enthaelt. Aufgefallen ist
# es erst beim Abgleich mit dem echten Pi-Bestand vor dem Deploy: `admin check` haette
# dort drei dauerhafte Warnungen fuer bewusst gesetzte Werte geworfen, und eine Warnung,
# die immer ansteht, liest bald niemand mehr.
#
# Bewusst offen gelassen: dass das gekaufte deutsche Vollbuch VOR dem deutschen SRD steht,
# ist eine Abwaegung, keine Naturkonstante. Dagegen spricht die Texttreue (das PHB kommt
# als OCR-Scan, das SRD als sauberes PDF). Sie ist umkehrbar, ohne dass etwas nachgezogen
# werden muss: eine Zahl in der Config und `admin quellen-auffrischen`.
BAND_DE_KERNREGELWERK = 10
BAND_DE_SRD = 20
BAND_EN_KAUFBUCH = 40
BAND_EN_FREI = 60
BAND_REVISION = 70
BAND_DE_ALTBUCH = 80

# Ein Band reicht bis zum Beginn des naechsten - nicht ueber eine feste Breite. Der
# Unterschied ist praktisch: Die realen Werte sind ueber ihre Klasse gestaffelt (efota/
# frhof auf 45 innerhalb der englischen Kaufbuecher, die drei Altbuecher auf 80/85/90),
# und eine starre Zehnerbreite haette 90 aus seinem eigenen Band fallen lassen.
_BANDGRENZEN = sorted((BAND_DE_KERNREGELWERK, BAND_DE_SRD, BAND_EN_KAUFBUCH,
                       BAND_EN_FREI, BAND_REVISION, BAND_DE_ALTBUCH,
                       STANDARD_PRIORITAET))


def band_fuer(*, sprache: str, edition: str, herkunft: str,
              inhaltsart: str = "regelwerk", lizenz: str | None = None) -> int:
    """Das erwartete Prioritaets-BAND einer Quelle - Grundlage der Warnung in `admin check`.

    Bewusst eine Erwartung und kein Zwang: die Funktion sagt, wo eine Quelle nach ihrer
    Klasse staende. Weicht die Config ab, ist das eine Meldung wert, aber kein Fehler -
    es gibt legitime Feinsortierung innerhalb einer Klasse, und ein hartes Gate wuerde
    genau die Handbreite nehmen, die die Baender offen lassen sollen.

    Bekannte Grenzen der Heuristik (Review 31.07.2026) - sie fuehren zu einer FALSCHEN
    WARNUNG, nie zu einem falschen Import:
      * Der deutsche Zweig unterscheidet Vollbuch und SRD an der Lizenz. Eine deutsche
        2024-Quelle ohne `lizenz` oder mit anders geschriebener Lizenz ('CC BY 4.0' mit
        Leerzeichen) gilt als Kaufbuch und wird bei Band 20 angemahnt.
      * Der englische Zweig erkennt freie Quellen an `herkunft='open5e'`. Eine kuenftige
        freie API mit anderer `herkunft` wuerde bei Band 60 angemahnt - dann gehoert sie
        in die Aufzaehlung unten, nicht die Zahl in der Config verbogen."""
    # Zuerst die Faelle, deren Klasse an DEM haengt, was die Quelle IST - nicht an
    # Sprache oder Bezugsweg. Ein deutsches Errata bliebe eine Korrektur und duerfte den
    # Grundtext trotzdem nicht ueberholen.
    if inhaltsart in ("errata", "regelauslegung"):
        return BAND_REVISION
    if sprache == "de":
        if edition != "2024":
            return BAND_DE_ALTBUCH
        # Band 10 ist AUSDRUECKLICH dem Kernregelwerk vorbehalten. Ein Abenteuer-/
        # Settingband ist keines: er liefert Regelwerte, aber keine Kernregeln, und stuende
        # dort vor dem SRD - bei einer Dublette gaebe also die Abenteuervariante den
        # Ausschlag (Review-Befund 31.07.2026: er bekam vorher Band 10).
        if inhaltsart == "abenteuer_setting":
            return BAND_DE_SRD
        # Das SRD ist eine offizielle TEILMENGE des Kernregelwerks; unterschieden wird
        # an der Lizenz, weil genau sie den Unterschied ausmacht: frei weitergebbar
        # (CC-BY) gegen gekauftes Vollbuch ('privat').
        if (lizenz or "").upper().startswith("CC-BY"):
            return BAND_DE_SRD
        return BAND_DE_KERNREGELWERK
    return BAND_EN_FREI if herkunft in ("open5e",) else BAND_EN_KAUFBUCH


def band_ende(band: int) -> int:
    """Der erste Wert, der NICHT mehr zu diesem Band gehoert (= Start des naechsten)."""
    hoeher = [g for g in _BANDGRENZEN if g > band]
    return hoeher[0] if hoeher else band + 10


def band_passt(prioritaet: int, band: int) -> bool:
    """Liegt die vergebene Prioritaet in ihrem Band? (Start bis vor das naechste Band)"""
    return band <= prioritaet < band_ende(band)

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


# --- Register-Export (Review 14.08.2026, K-01) ---------------------------------------
#
# `config/foliant.toml` ist gitignored, aus dem Deploy-rsync ausgeschlossen und in keinem
# Backup. Pi und Mac trugen deshalb zwei VERSCHIEDENE Register (12 gegen 8 Quellenbloecke,
# sieben Kuerzel disjunkt), und keines beschrieb den Produktionsbestand vollstaendig - die
# sieben DDB-Quellen standen in gar keiner der beiden Dateien.
#
# Die Datenbank weiss es besser: `quellen` fuehrt alle 18 Quellen mit Edition, Lizenz,
# Prioritaet, `inhaltsart` und Herkunft. Genau die Angaben macht Kernregel 2 ("Editionen
# werden NIE geraten") nach einem Kartenausfall unersetzlich - raten ist verboten, also
# muss es aufgeschrieben sein.
#
# Der Export ist ein WIEDERHERSTELLUNGS-Artefakt, kein Laufzeit-Eingang: Er wird gelesen,
# wenn jemand den Bestand neu aufbauen muss, nicht bei jedem Start. Deshalb aendert er
# nichts an `lade_konfig` - eine zweite Konfigurationsquelle waere ein Risiko fuer einen
# Nutzen, den niemand taeglich braucht.

# `titel` steht bewusst NICHT hier (Davids Entscheidung, 14.08.2026): Die Buchtitel der
# Kaufbuecher sollen nicht ins oeffentliche Repo. Die Kuerzel tun es ohnehin schon, und
# die Dateipfade sind durchgehend kuerzel-basiert - geprueft, es leckt keiner.
REGISTER_FELDER = ("kuerzel", "sprache", "edition", "herkunft", "lizenz", "prioritaet",
                   "dateipfad", "inhaltsart", "versions_stand", "quell_url", "quell_hash")


def _toml_wert(wert) -> str:
    if isinstance(wert, bool):
        return "true" if wert else "false"
    if isinstance(wert, int):
        return str(wert)
    return '"' + str(wert).replace("\\", "\\\\").replace('"', '\\"') + '"'


def exportiere_register(con: sqlite3.Connection, stand: str) -> str:
    """Das Quellen-Register als TOML-Text, erzeugt aus der Datenbank.

    Format wie die `[[quelle]]`-Bloecke in `config/foliant.toml`, damit der Text im
    Ernstfall direkt dorthin zurueckwandern kann. Felder ohne Wert bleiben weg statt als
    leerer String dazustehen - ein `lizenz = ""` sieht aus wie eine Angabe und ist keine.
    """
    zeilen = [
        "# Quellen-Register des Produktionsbestands - ERZEUGT, nicht von Hand gepflegt.",
        "#",
        "# Zweck: Wiederherstellung. Faellt die SD-Karte aus, ist dies die einzige Stelle,",
        "# an der Edition, Lizenz, Prioritaet und inhaltsart jeder Quelle noch stehen -",
        "# und geraten werden duerfen sie laut Kernregel 2 nicht.",
        "#",
        "# Erneuern nach einem beabsichtigten Import:  make register-vom-pi",
        "# Buchtitel fehlen bewusst; beim Wiederherstellen von Hand nachtragen.",
        "#",
        f"# Stand: {stand}",
        "",
    ]
    for zeile in con.execute(
            f"SELECT {', '.join(REGISTER_FELDER)} FROM quellen ORDER BY prioritaet, kuerzel"):
        zeilen.append("[[quelle]]")
        for feld, wert in zip(REGISTER_FELDER, zeile):
            if wert is not None and wert != "":
                zeilen.append(f"{feld} = {_toml_wert(wert)}")
        zeilen.append("")
    return "\n".join(zeilen)
