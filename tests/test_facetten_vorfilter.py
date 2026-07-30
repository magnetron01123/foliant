"""Meta-Vorfilter im Struktur-Pfad (Lastmessung 28.07.2026, B9-Hebel).

`_struktur_filter` zog fuer JEDEN Eintrag der Kategorie den vollen Body und parste ihn -
1627 `zauber_grad`-Aufrufe je Filteranfrage, 41 % der Profilzeit -, obwohl die Werte seit
Phase 3 in `zauber_meta`/`monster_meta` stehen.

Der Vorfilter ENTSCHEIDET NICHTS. Er schliesst nur Zeilen aus, deren gespeicherter Wert
nachweislich ein anderer ist; ueber alle uebrigen urteilt weiter das Textpraedikat. Drei
Zusicherungen tragen das, und jede hat hier ihren Test:

  1. AEQUIVALENZ - mit Vorfilter kommen dieselben Treffer heraus wie ohne.
  2. SELBSTTRAGEND - Zeilen ohne Meta-Wert werden NIE verworfen, sondern gepruefft.
     (Sonst lieferte eine ungeseedete Datenbank still nichts - die C1-Fehlerform.)
  3. WERTRAUM-WAECHTER - traegt die Tabelle noch den alten Open5e-Wertraum
     ('Evocation' statt 'hervorrufung'), wird GAR NICHT vorgefiltert. Lieber langsam
     richtig als schnell falsch.
"""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app.tools import nachschlagen as ns
from app.tools import suche as su
from importer.facetten_seeder import seed_facetten

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

_ZAUBER = [
    ("Feuerball", "_Hervorrufungszauber 3. Grades (Magier)_ **Reichweite:** 45 Meter "
                  "**Komponenten:** V, G, M **Wirkungsdauer:** Unmittelbar"),
    ("Blitz", "_Hervorrufungszauber 3. Grades (Magier)_ **Reichweite:** 30 Meter "
              "**Komponenten:** V, G, M **Wirkungsdauer:** Unmittelbar"),
    ("Alarm", "_Bannzauber 1. Grades (Magier)_ **Reichweite:** 9 Meter "
              "**Komponenten:** V, G, M **Wirkungsdauer:** 8 Stunden"),
    ("Schild", "_Bannzauber 1. Grades (Magier)_ **Reichweite:** Selbst "
               "**Komponenten:** V, G **Wirkungsdauer:** 1 Runde"),
    # Kein ableitbarer Kopf -> bekommt KEINE Meta-Zeile und muss trotzdem geprueft werden.
    ("Bruchstueck", "*Kontext: Zauber* Ein Abschnitt ohne erkennbaren Zauberkopf."),
]


def _db(tmp_path, seeden=True):
    pfad = tmp_path / "vorfilter.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
                "VALUES ('srd-de','SRD','de','2024','pdf',10)")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (1,'zauber',?,NULL,'de','2024',NULL,?)", _ZAUBER)
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    if seeden:
        c = adb.connect(str(pfad))
        try:
            with c:
                seed_facetten(c)
        finally:
            c.close()
    return pfad


def _vergleiche(con, **kw):
    """(ohne Vorfilter, mit Vorfilter) - dieselbe Anfrage auf beiden Wegen."""
    prae, kat, echo, fehler = su._facetten_vorbereiten(
        "zauber", kw.get("grad"), kw.get("schule"), kw.get("klasse"), None, None, None)
    assert fehler is None, fehler
    vf = su._meta_vorfilter(kat, kw.get("grad"), kw.get("schule"), None, None)
    ohne = su._struktur_filter(con, kat, "2024", prae, echo, 50)
    mit = su._struktur_filter(con, kat, "2024", prae, echo, 50, vorfilter=vf)
    return ohne, mit


@pytest.mark.parametrize("kw", [
    dict(grad=3), dict(grad=1), dict(grad=9),
    dict(schule="Hervorrufung"), dict(schule="Bannzauber"),
    dict(grad=1, schule="Bannzauber"),
    dict(klasse="Magier"),                       # kein Vorfilter moeglich -> Textweg
])
def test_vorfilter_liefert_dieselben_treffer(tmp_path, kw):
    con = adb.connect_readonly(str(_db(tmp_path)))
    try:
        ohne, mit = _vergleiche(con, **kw)
        assert [t["eintrag_id"] for t in ohne["treffer"]] == \
               [t["eintrag_id"] for t in mit["treffer"]], kw
        assert ohne["anzahl_gesamt"] == mit["anzahl_gesamt"]
    finally:
        con.close()


def test_eintrag_ohne_metazeile_wird_geprueft_statt_verworfen(tmp_path):
    """Zusicherung 2: 'Bruchstueck' hat keinen ableitbaren Kopf und damit keine Meta-Zeile.
    Ein Vorfilter, der solche Zeilen wegwirft, lieferte auf einer ungeseedeten Datenbank
    still nichts."""
    pfad = _db(tmp_path)
    con = adb.connect_readonly(str(pfad))
    try:
        # Vorbedingung: der Eintrag hat wirklich keine Meta-Zeile.
        pruef = sqlite3.connect(pfad)
        eid = pruef.execute("SELECT id FROM eintraege WHERE name_de='Bruchstueck'").fetchone()[0]
        assert pruef.execute("SELECT count(*) FROM zauber_meta WHERE eintrag_id=?",
                             (eid,)).fetchone()[0] == 0
        pruef.close()
        # Die SQL-Bedingung darf ihn nicht ausschliessen (der LEFT JOIN liefert NULL).
        join, zusatz, params = su._vorfilter_sql(con, "zauber", {"grad": 3})
        assert "IS NULL" in zusatz
        ids = {r[0] for r in con.execute(
            f"SELECT e.id FROM eintraege e JOIN quellen q ON q.id=e.quelle_id{join} "
            f"WHERE e.kategorie='zauber' AND e.edition=?{zusatz}", ("2024", *params))}
        assert eid in ids, "Eintrag ohne Meta-Zeile wurde vorgefiltert weggeworfen"
    finally:
        con.close()


def test_ungeseedete_db_filtert_nicht_vor_und_findet_trotzdem(tmp_path):
    """Selbsttragend: ohne jede Meta-Zeile faellt der Filter auf den Textweg zurueck."""
    con = adb.connect_readonly(str(_db(tmp_path, seeden=False)))
    try:
        assert su._vorfilter_sql(con, "zauber", {"grad": 3})[0] == ""
        ohne, mit = _vergleiche(con, grad=3)
        assert [t["name_de"] for t in mit["treffer"]] == ["Blitz", "Feuerball"]
        assert ohne["anzahl_gesamt"] == mit["anzahl_gesamt"] == 2
    finally:
        con.close()


def test_alter_wertraum_schaltet_den_vorfilter_ab(tmp_path):
    """Zusicherung 3 - der teuerste Fall. Bis Phase 3 schrieb der Open5e-Import
    'Evocation'/'0.25' statt 'hervorrufung'/'1/4'. Ein Vorfilter darauf wuerde passende
    Eintraege still WEGWERFEN. Der Waechter erkennt den Altbestand daran, dass die
    Spalten des heutigen Seeders (ritual/rk) durchgehend leer sind."""
    pfad = _db(tmp_path)
    con = sqlite3.connect(pfad)
    con.execute("UPDATE zauber_meta SET schule='Evocation', ritual=NULL, "
                "reichweite_m=NULL, komponenten=NULL, dauer_min=NULL, konzentration=NULL")
    con.commit()
    con.close()

    lese = adb.connect_readonly(str(pfad))
    try:
        assert su._vorfilter_sql(lese, "zauber", {"schule": "hervorrufung"})[0] == "", \
            "Vorfilter greift auf einem fremden Wertraum"
        ohne, mit = _vergleiche(lese, schule="Hervorrufung")
        assert [t["name_de"] for t in mit["treffer"]] == ["Blitz", "Feuerball"]
        assert ohne["anzahl_gesamt"] == mit["anzahl_gesamt"] == 2
    finally:
        lese.close()


def test_seeder_raeumt_fremde_altzeilen_weg(tmp_path):
    """Damit der Waechter nicht dauerhaft bremsen muss: ein Seeder-Lauf stellt den
    kanonischen Wertraum her, auch fuer Eintraege, aus denen sich nichts ableiten laesst
    (INSERT OR REPLACE allein wuerde deren Alt-Zeile stehen lassen)."""
    pfad = _db(tmp_path)
    con = adb.connect(str(pfad))
    try:
        eid = con.execute("SELECT id FROM eintraege WHERE name_de='Bruchstueck'").fetchone()[0]
        con.execute("INSERT OR REPLACE INTO zauber_meta (eintrag_id, schule) "
                    "VALUES (?, 'Evocation')", (eid,))
        con.commit()
        assert con.execute("SELECT count(*) FROM zauber_meta WHERE schule='Evocation'"
                           ).fetchone()[0] == 1     # Vorbedingung: Fremdzeile ist drin
        with con:
            seed_facetten(con)
        assert con.execute("SELECT count(*) FROM zauber_meta WHERE eintrag_id=?",
                           (eid,)).fetchone()[0] == 0, "Fremde Alt-Zeile ueberlebt"
        assert con.execute("SELECT count(*) FROM zauber_meta WHERE schule='Evocation'"
                           ).fetchone()[0] == 0
    finally:
        con.close()
