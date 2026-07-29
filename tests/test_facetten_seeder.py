"""Facetten persistieren (Phase 3, 28.07.2026) - Befund C1.

Die Meta-Tabellen waren auf dem Pi leer, weil nur der Open5e-Import sie schrieb. Geprueft
wird deshalb genau das, was damals gefehlt hat: dass ALLE Quellen bedient werden, dass der
Wertraum EINER ist, dass nichts geraten wird, dass Alt-DBs die neuen Spalten bekommen -
und dass die Beweisgrundlage der Glossar-Zauberbruecken (fingerabdruck) sich NICHT bewegt.
"""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app import facetten as F
from app.tools import nachschlagen as ns
from importer import facetten_seeder as seeder
from importer import srd_zauberbruecken as Z

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

# Echte Kopfformen aus dem Bestand (gekuerzt) - kein erfundenes Wunschformat.
_FEUERBALL_DE = ("*Kontext: Zauber > Beschreibungen der Zauber* "
                 "_Hervorrufungszauber 3. Grades (Magier, Zauberer)_ "
                 "**Zeitaufwand:** Aktion **Reichweite:** 45 Meter "
                 "**Komponenten:** V, G, M (eine Kugel aus Guano) "
                 "**Wirkungsdauer:** Unmittelbar Du verschiesst einen Lichtstrahl.")
_ALARM_EN = ("**Level:** 1 · **School:** Abjuration · **Classes:** Ranger, Wizard "
             "**Casting Time:** 1minute · **Range:** 30 feet · "
             "**Components:** V, S, M (a bell and silver wire) "
             "**Duration:** 8 hours · **Ritual:** yes You set an alarm.")
_GOBLIN_DE = ("_Kleiner Humanoider, Chaotisch Boese_ **RK** 15 **TP** 7 "
              "**HG** 1/4 **Stä** 8 **Ges** 15 **Kon** 10 **Int** 10 **Wei** 8 **Cha** 8")


def _db_mit(tmp_path, eintraege, *, name="f.sqlite"):
    """Schema + zwei Quellen (srd-de vorrangig, Open5e nachrangig) + die Eintraege."""
    pfad = tmp_path / name
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
                "VALUES ('srd-de','SRD de','de','2024','pdf',10)")
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
                "VALUES ('open5e-srd-2024','SRD en','en','2024','open5e',60)")
    ids = {r[0]: r[1] for r in con.execute("SELECT kuerzel, id FROM quellen")}
    for quelle, kategorie, name_de, name_en, sprache, body in eintraege:
        con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,"
                    "edition,seite,body_md) VALUES (?,?,?,?,?, '2024',NULL,?)",
                    (ids[quelle], kategorie, name_de, name_en, sprache, body))
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    return pfad


# --------------------------------------------------------------- Senke fuer ALLE Quellen

def test_seeder_bedient_alle_quellen_nicht_nur_open5e(tmp_path):
    """Kern von C1: die deutsche Quelle bekam frueher NIE eine Meta-Zeile."""
    pfad = _db_mit(tmp_path, [
        ("srd-de", "zauber", "Feuerball", None, "de", _FEUERBALL_DE),
        ("open5e-srd-2024", "zauber", None, "Alarm", "en", _ALARM_EN),
        ("srd-de", "monster", "Goblin", None, "de", _GOBLIN_DE),
    ])
    con = adb.connect(str(pfad))
    try:
        with con:
            bilanz = seeder.seed_facetten(con)
        assert bilanz == {"zauber": 2, "monster": 1, "gegenstand": 0}
        quellen = {r[0] for r in con.execute(
            "SELECT q.kuerzel FROM zauber_meta m JOIN eintraege e ON e.id=m.eintrag_id "
            "JOIN quellen q ON q.id=e.quelle_id")}
        assert quellen == {"srd-de", "open5e-srd-2024"}
    finally:
        con.close()


def test_wertraum_ist_kanonisch_und_sprachunabhaengig(tmp_path):
    """Deutsche und englische Fassung desselben Zaubers ergeben DIESELBEN Strukturwerte -
    genau das leistete der alte Open5e-Pfad nicht ('Evocation' vs. 'hervorrufung')."""
    alarm_de = ("_Bannzauber 1. Grades (Magier, Waldläufer)_ **Zeitaufwand:** 1 Minute oder "
                "Ritual **Reichweite:** 9 Meter **Komponenten:** V, G, M (eine Glocke) "
                "**Wirkungsdauer:** 8 Stunden")
    pfad = _db_mit(tmp_path, [
        ("srd-de", "zauber", "Alarm", None, "de", alarm_de),
        ("open5e-srd-2024", "zauber", None, "Alarm", "en", _ALARM_EN),
    ])
    con = adb.connect(str(pfad))
    try:
        with con:
            seeder.seed_facetten(con)
        zeilen = [dict(r) for r in con.execute(
            "SELECT q.kuerzel, m.grad, m.schule, m.reichweite_m, m.komponenten, "
            "m.dauer_min, m.konzentration, m.ritual FROM zauber_meta m "
            "JOIN eintraege e ON e.id=m.eintrag_id JOIN quellen q ON q.id=e.quelle_id "
            "ORDER BY q.kuerzel")]
        de = next(z for z in zeilen if z["kuerzel"] == "srd-de")
        en = next(z for z in zeilen if z["kuerzel"] == "open5e-srd-2024")
        for feld in ("grad", "schule", "reichweite_m", "komponenten", "dauer_min",
                     "konzentration", "ritual"):
            assert de[feld] == en[feld], f"{feld}: {de[feld]!r} != {en[feld]!r}"
        assert de["schule"] == "bannzauber"          # kanonischer Schluessel, nicht 'Abjuration'
        assert de["reichweite_m"] == "9"             # 30 feet == 9 Meter
        assert de["komponenten"] == "VSM"            # Konvention, nicht alphabetisch
        assert de["dauer_min"] == 480                # 8 Stunden
        assert de["ritual"] == 1
    finally:
        con.close()


def test_hg_wird_kanonisch_gespeichert(tmp_path):
    """Open5e fuehrt CR dezimal ('0.25'/'10.0'). facetten.monster_hg normalisiert das; die
    Meta-Tabelle tat es frueher NICHT und widersprach damit dem Filter (hg_passt)."""
    pfad = _db_mit(tmp_path, [
        ("open5e-srd-2024", "monster", None, "Aboleth", "en",
         "_Large aberration_ **CR** 10.0 **AC** 17 **HP** 135"),
        ("open5e-srd-2024", "monster", None, "Rat", "en",
         "_Tiny beast_ **CR** 0.125 **AC** 10 **HP** 1"),
    ])
    con = adb.connect(str(pfad))
    try:
        with con:
            seeder.seed_facetten(con)
        hg = {r[0]: r[1] for r in con.execute(
            "SELECT e.name_en, m.hg FROM monster_meta m JOIN eintraege e ON e.id=m.eintrag_id")}
        assert hg == {"Aboleth": "10", "Rat": "1/8"}
        rk = con.execute("SELECT rk, tp FROM monster_meta m JOIN eintraege e "
                         "ON e.id=m.eintrag_id WHERE e.name_en='Aboleth'").fetchone()
        assert tuple(rk) == (17, 135)
    finally:
        con.close()


def test_kein_raten_ohne_ableitbaren_text(tmp_path):
    """Regel 1: aus einem Eintrag ohne Struktur im Text entsteht KEINE Zeile - kein
    Platzhalter, kein Default."""
    pfad = _db_mit(tmp_path, [
        ("srd-de", "zauber", "Verbalkomponente (V)", None, "de",
         "*Kontext: Zauber > Zauber wirken* Ein Zauber mit Verbalkomponente verlangt Sprache."),
    ])
    con = adb.connect(str(pfad))
    try:
        with con:
            assert seeder.seed_facetten(con)["zauber"] == 0
        assert con.execute("SELECT count(*) FROM zauber_meta").fetchone()[0] == 0
    finally:
        con.close()


def test_ritual_bleibt_unbekannt_ohne_erkannten_zauberkopf(tmp_path):
    """'kein Ritual-Marker' darf nur bei erkanntem Zauberkopf 'kein Ritual' heissen -
    sonst ist es unbekannt (NULL). Ein stilles 0 waere eine Falschaussage (A1-Klasse)."""
    pfad = _db_mit(tmp_path, [
        # Kopf ohne Grad, aber mit Reichweite -> Zeile entsteht, ritual bleibt NULL.
        ("srd-de", "zauber", "Bruchstueck", None, "de", "**Reichweite:** 9 Meter"),
        ("srd-de", "zauber", "Feuerball", None, "de", _FEUERBALL_DE),
    ])
    con = adb.connect(str(pfad))
    try:
        with con:
            seeder.seed_facetten(con)
        werte = {r[0]: r[1] for r in con.execute(
            "SELECT e.name_de, m.ritual FROM zauber_meta m JOIN eintraege e ON e.id=m.eintrag_id")}
        assert werte["Bruchstueck"] is None
        assert werte["Feuerball"] == 0               # Kopf erkannt, kein Marker -> belegt 0
    finally:
        con.close()


def test_seeder_ist_idempotent(tmp_path):
    """Zweiter Lauf = gleiches Ergebnis (INSERT OR REPLACE, kein UNIQUE-Fehler)."""
    pfad = _db_mit(tmp_path, [("srd-de", "zauber", "Feuerball", None, "de", _FEUERBALL_DE)])
    con = adb.connect(str(pfad))
    try:
        with con:
            erst = seeder.seed_facetten(con)
        with con:
            zweit = seeder.seed_facetten(con)
        assert erst == zweit
        assert con.execute("SELECT count(*) FROM zauber_meta").fetchone()[0] == 1
    finally:
        con.close()


def test_seeder_nur_eine_quelle(tmp_path):
    pfad = _db_mit(tmp_path, [
        ("srd-de", "zauber", "Feuerball", None, "de", _FEUERBALL_DE),
        ("open5e-srd-2024", "zauber", None, "Alarm", "en", _ALARM_EN),
    ])
    con = adb.connect(str(pfad))
    try:
        qid = con.execute("SELECT id FROM quellen WHERE kuerzel='srd-de'").fetchone()[0]
        with con:
            assert seeder.seed_facetten(con, qid)["zauber"] == 1
        namen = {r[0] for r in con.execute(
            "SELECT e.name_de FROM zauber_meta m JOIN eintraege e ON e.id=m.eintrag_id")}
        assert namen == {"Feuerball"}
    finally:
        con.close()


# ------------------------------------------------------------------------ Migration

def test_alt_db_bekommt_die_neuen_spalten(tmp_path):
    """Bestands-DB im Ur-Zuschnitt -> connect() ruestet additiv nach (NF7), vorhandene
    Daten bleiben. Dasselbe Muster wie bei quellen.inhaltsart.

    Geprueft wird gegen META_TABELLEN, nicht gegen eine abgeschriebene Spaltenliste: die
    Nachruestung (db.FACETTEN_SPALTEN) ist die dritte Stelle, an der Facetten-Spalten
    stehen, und die einzige, die man beim Ergaenzen einer Facette vergessen KANN, ohne
    dass am Mac etwas auffaellt - eine frische DB bekommt die Spalte ja aus schema.sql.
    Erst auf dem Pi liefe dann das INSERT des Seeders auf."""
    pfad = tmp_path / "alt.sqlite"
    con = sqlite3.connect(pfad)
    con.execute("CREATE TABLE quellen (id INTEGER PRIMARY KEY, kuerzel TEXT UNIQUE NOT NULL)")
    con.execute("CREATE TABLE eintraege (id INTEGER PRIMARY KEY)")
    con.execute("CREATE TABLE zauber_meta (eintrag_id INTEGER PRIMARY KEY, grad INTEGER, "
                "schule TEXT, klassen TEXT)")
    con.execute("CREATE TABLE monster_meta (eintrag_id INTEGER PRIMARY KEY, hg TEXT, typ TEXT)")
    con.execute("CREATE TABLE gegenstand_meta (eintrag_id INTEGER PRIMARY KEY, seltenheit TEXT)")
    con.execute("INSERT INTO zauber_meta VALUES (7, 3, 'hervorrufung', 'Magier')")
    con.commit()
    con.close()

    c = adb.connect(str(pfad))
    try:
        for _kategorie, (tabelle, felder) in F.META_TABELLEN.items():
            spalten = {r[1] for r in c.execute(f"PRAGMA table_info({tabelle})")}
            fehlend = set(felder) - spalten
            assert not fehlend, (f"{tabelle}: {sorted(fehlend)} nach der Migration nicht da "
                                 f"- fehlt der Eintrag in db.FACETTEN_SPALTEN?")
        assert tuple(c.execute("SELECT grad, schule, klassen FROM zauber_meta").fetchone()) \
            == (3, "hervorrufung", "Magier")          # Altdaten unangetastet
    finally:
        c.close()
    adb.connect(str(pfad)).close()                    # idempotent: zweiter Lauf kein Fehler


def test_migration_ueberspringt_fehlende_tabelle(tmp_path):
    """gegenstand_meta fehlt ganz -> kein Crash (die Tabelle legt das Schema an)."""
    pfad = tmp_path / "ohne.sqlite"
    con = sqlite3.connect(pfad)
    con.execute("CREATE TABLE quellen (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    adb.connect(str(pfad)).close()


# --------------------------------------------------- Bruecken duerfen sich NICHT bewegen

@pytest.mark.parametrize("body,deutsch", [
    (_FEUERBALL_DE, True), (_ALARM_EN, False), (_GOBLIN_DE, True), ("", True), (None, False),
    ("_Nekromantie des 3. Grades (Ritual)_ Zeitaufwand: 1 Aktion Reichweite: Berührung "
     "Komponenten: V, G, M Wirkungsdauer: 1 Stunde", True),
])
def test_kopf_felder_laesst_fingerabdruck_unberuehrt(body, deutsch):
    """kopf_felder() liest denselben Kopf tolerant (ohne Markdown, mit Wortgrenzen) -
    fingerabdruck() bleibt bewusst roh, weil er die Beweisgrundlage der geseedeten
    Zauber-Bruecken ist. Der Test haelt die Trennung fest: kopf_felder darf sich
    weiterentwickeln, ohne dass Glossar-Paare wandern."""
    vorher = Z.fingerabdruck(body, deutsch)
    Z.kopf_felder(body, deutsch)
    assert Z.fingerabdruck(body, deutsch) == vorher


def test_kopf_felder_liest_was_fingerabdruck_entgeht():
    """Der Grund fuer den toleranten Kopf: '**Komponenten:** V, G, M' laeuft im rohen
    Kopf ins Leere (die zwei Sterne stehen zwischen Label und Wert), und 'Range' traf
    ohne Wortgrenze das 'Range' in 'Ranger'."""
    felder = Z.kopf_felder(_FEUERBALL_DE, deutsch=True)
    assert felder["komponenten"] == "VSM"
    assert Z.fingerabdruck(_FEUERBALL_DE, deutsch=True)[3] is None    # roh: nicht erkannt

    en = Z.kopf_felder(_ALARM_EN, deutsch=False)
    assert en["reichweite_m"] == "9"                  # trotz '**Classes:** Ranger, ...'
    assert en["ritual"] == 1                          # '**Ritual:** yes'


# ------------------------------------------------------------------ Klassen-Ableitung

@pytest.mark.parametrize("body,erwartet", [
    ("_Hervorrufungszauber 3. Grades (Magier, Zauberer)_", ["Magier", "Zauberer"]),
    ("**Level:** 1 · **Classes:** Ranger, Wizard **Components:** V, S, M (a bell)",
     ["Ranger", "Wizard"]),
    # Die Klammer ist nur eine Positions-Vermutung: '(Ritual)' und Materialkomponenten
    # sind keine Klassenliste (dt. 2014-Koepfe, Befund 28.07.2026).
    ("_Nekromantie des 3. Grades (Ritual)_", []),
    ("_Bannzauber 1. Grades_ **Komponenten:** V, G, M (ein Stück Fell)", []),
])
def test_zauber_klassen_nur_belegte_klassenlisten(body, erwartet):
    assert F.zauber_klassen(body) == erwartet


# ------------------------------------------------------------------------- Ausgabe

def test_facetten_faellt_auf_weggemergte_fassung_zurueck(tmp_path, monkeypatch):
    """Der Dedup laesst die deutsche Quelle gewinnen. Traegt gerade DIE keine Facette,
    darf die Auskunft nicht leer bleiben, solange die englische Schwesterfassung eine hat
    (A5) - sonst sind persistierte Facetten im Regelfall unsichtbar."""
    pfad = _db_mit(tmp_path, [
        # Deutscher Gewinner OHNE ableitbare Struktur, englische Fassung MIT.
        ("srd-de", "zauber", "Alarm", None, "de", "*Kontext: Zauber* Alarm schlaegt an."),
        ("open5e-srd-2024", "zauber", None, "Alarm", "en", _ALARM_EN),
    ])
    con = adb.connect(str(pfad))
    try:
        with con:
            seeder.seed_facetten(con)
        # Vorbedingung: nur die englische Fassung hat eine Zeile.
        assert {r[0] for r in con.execute(
            "SELECT q.kuerzel FROM zauber_meta m JOIN eintraege e ON e.id=m.eintrag_id "
            "JOIN quellen q ON q.id=e.quelle_id")} == {"open5e-srd-2024"}
    finally:
        con.close()
    con2 = sqlite3.connect(pfad)
    con2.row_factory = sqlite3.Row
    try:
        de_id = con2.execute("SELECT id FROM eintraege WHERE sprache='de'").fetchone()["id"]
        en_id = con2.execute("SELECT id FROM eintraege WHERE sprache='en'").fetchone()["id"]
        gewinner = dict(con2.execute("SELECT * FROM eintraege WHERE id=?", (de_id,)).fetchone())
        assert ns._facetten_von(con2, gewinner) is None          # ohne Rueckfallebene
        gewinner["weitere_fassungen"] = [{"id": en_id, "quelle_titel": "SRD en",
                                          "sprache": "en"}]
        fac = ns._facetten_von(con2, gewinner)
        assert fac and fac["grad"] == 1 and fac["schule"] == "Bannzauber"
    finally:
        con2.close()


def test_facetten_ueberleben_eine_unmigrierte_alt_db(tmp_path):
    """Der Serving-Pfad ist read-only und migriert NICHT. Auf einer Bestands-DB, die die
    neuen Spalten noch nicht hat (deployed, aber noch kein Import gelaufen), muessen die
    ALTEN Facetten weiter erscheinen - statt dass eine zu breite Spaltenliste alles
    verschluckt."""
    pfad = tmp_path / "alt.sqlite"
    con = sqlite3.connect(pfad)
    con.execute("CREATE TABLE zauber_meta (eintrag_id INTEGER PRIMARY KEY, grad INTEGER, "
                "schule TEXT, klassen TEXT)")
    con.execute("INSERT INTO zauber_meta VALUES (7, 3, 'hervorrufung', 'Magier')")
    con.commit()
    con.close()
    lese = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    lese.row_factory = sqlite3.Row
    try:
        fac = ns._facetten_von(lese, {"id": 7, "kategorie": "zauber"})
        assert fac == {"grad": 3, "schule": "Hervorrufung", "klassen": "Magier"}
        # Fehlt die Tabelle ganz, bleibt es beim ehrlichen 'kein Feld'.
        assert ns._facetten_von(lese, {"id": 7, "kategorie": "monster"}) is None
    finally:
        lese.close()


def test_facetten_geben_null_werte_und_wahrheitswerte_ehrlich_aus(tmp_path, monkeypatch):
    """0 ist ein WERT (Zaubertrick, 'unmittelbar', 'kein Ritual') und darf nicht wie ein
    fehlendes Feld verschwinden; konzentration/ritual kommen als true/false."""
    zaubertrick = ("_Hervorrufungs-Zaubertrick_ **Zeitaufwand:** Aktion "
                   "**Reichweite:** 36 Meter **Komponenten:** V, G "
                   "**Wirkungsdauer:** Unmittelbar")
    pfad = _db_mit(tmp_path, [("srd-de", "zauber", "Flammenhand", None, "de", zaubertrick)])
    con = adb.connect(str(pfad))
    try:
        with con:
            seeder.seed_facetten(con)
    finally:
        con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    d = ns.foliant_hol_zauber("Flammenhand")
    assert d["gefunden"] is True
    fac = d["facetten"]
    assert fac["grad"] == 0                       # Zaubertrick - NICHT weggefiltert
    assert fac["dauer_min"] == 0                  # unmittelbar
    assert fac["konzentration"] is False and fac["ritual"] is False
    assert fac["schule"] == "Hervorrufung"        # deutsche Anzeigeform


def test_check_meldet_facetten_deckung(tmp_path, monkeypatch, capsys):
    """Ohne diese Zeile blieb der Dev/Prod-Drift aus C1 unbemerkt."""
    pfad = _db_mit(tmp_path, [("srd-de", "zauber", "Feuerball", None, "de", _FEUERBALL_DE)])
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    con = adb.connect(str(pfad))
    try:
        with con:
            seeder.seed_facetten(con)
    finally:
        con.close()
    admin_modul = __import__("app.admin", fromlist=["cmd_check"])
    admin_modul.cmd_check(None)
    ausgabe = capsys.readouterr().out
    assert "Facetten-Deckung" in ausgabe
    assert "zauber 1/1" in ausgabe


def test_meta_definition_deckt_sich_mit_dem_schema():
    """Die EINE Definition (app.facetten.META_TABELLEN) und die Tabellen in db/schema.sql
    muessen dieselben Spalten kennen.

    Schreiber (facetten_seeder) und Leser (nachschlagen) teilen sich die Definition seit
    dem 29.07.2026 - vorher fuehrte jede Seite eine eigene, byte-identische Kopie, und eine
    neue Facette erschien nie in der Tool-Ausgabe, bis jemand die zweite Liste fand. Die
    dritte Stelle bleibt aber das Schema: eine Spalte, die nur in der Definition steht,
    laesst das INSERT des Seeders auflaufen; eine, die nur im Schema steht, bleibt
    dauerhaft NULL, ohne dass es auffaellt."""
    import re

    sql = _SCHEMA.read_text(encoding="utf-8")
    for kategorie, (tabelle, felder) in F.META_TABELLEN.items():
        block = sql.split(f"CREATE TABLE IF NOT EXISTS {tabelle} (", 1)[1].split(");", 1)[0]
        ohne_kommentar = "\n".join(z.split("--")[0] for z in block.splitlines())
        # Spaltendeklaration = Name + Typ, egal ob eine je Zeile oder mehrere hintereinander.
        spalten = {m.group(1) for m in re.finditer(
            r"(?:^|,)\s*(\w+)\s+(?:INTEGER|TEXT|REAL|BLOB)", ohne_kommentar)}
        fehlend = set(felder) - spalten
        assert not fehlend, (f"{kategorie}: {sorted(fehlend)} steht in META_TABELLEN, "
                             f"aber nicht in db/schema.sql -> der Seeder laeuft auf")
        # seltenheit ist bewusst nicht in META_TABELLEN (keine belastbare Ableitung,
        # BACKLOG par. 3) - alles andere waere eine unbemerkt tote Spalte.
        ungenutzt = spalten - set(felder) - {"eintrag_id", "seltenheit"}
        assert not ungenutzt, (f"{tabelle}: {sorted(ungenutzt)} steht im Schema, wird aber "
                               f"von niemandem geschrieben - Spalte oder Eintrag in "
                               f"META_TABELLEN fehlt")
