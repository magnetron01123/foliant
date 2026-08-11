"""Der Qualitäts-Basiswert: aus einer Kennzahl wird ein Gate.

Bis zum 01.08.2026 gab `admin check` nur Zahlen aus. Niemand verglich sie mit dem letzten
Stand — und genau deshalb fiel zweierlei nicht auf:

  * Die gemeldete Zahl war von 51 (so stand es im BACKLOG) auf 91 gewachsen.
  * 42 der 91 waren gar keine OCR-Risse, sondern alphabetische Registerköpfe aus
    DDB-Büchern ('B | Monsters', 'Spells J') — Rauschen, das die 49 echten Risse überdeckte.

Eine Kennzahl, die niemand nachrechnet, ist keine Warnung mehr, sondern Hintergrundrauschen.
Der Basiswert macht daraus drei klare Fälle: STEIGT (Fehler), SINKT (nachziehen), GLEICH
(still).
"""
import json
import sqlite3

import pytest

from app import admin
from tests.hilfen import SCHEMA


def _db_mit(namen: list[tuple[str, str]], tmp_path):
    """DB mit einer Quelle je Kürzel und den gegebenen (name, kuerzel)-Paaren."""
    pfad = tmp_path / "t.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    for i, kuerzel in enumerate(sorted({q for _n, q in namen}), start=1):
        con.execute("INSERT INTO quellen (id,kuerzel,titel,sprache,edition,herkunft,"
                    "prioritaet) VALUES (?,?,?,'de','2024','pdf',20)",
                    (i, kuerzel, kuerzel))
    ids = {r[1]: r[0] for r in con.execute("SELECT id, kuerzel FROM quellen")}
    for name, kuerzel in namen:
        con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,"
                    "body_md) VALUES (?,'regel',?,'de','2024','Text.')",
                    (ids[kuerzel], name))
    con.commit()
    return con


def _basis(tmp_path, inhalt: dict, monkeypatch):
    datei = tmp_path / "basis.json"
    datei.write_text(json.dumps(inhalt), encoding="utf-8")
    monkeypatch.setattr(admin, "QUALITAET_BASIS", datei)


def test_neuer_mangel_bricht_den_check(tmp_path, monkeypatch, capsys):
    """Der eine Fall, der jemanden erreichen muss: Ein Import hat einen NEUEN zerrissenen
    Namen eingeschleppt. Alles andere darf still bleiben, das hier nicht."""
    _basis(tmp_path, {"ocr_risse_je_quelle": {"srd-de": 0}}, monkeypatch)
    con = _db_mit([("D ORNENWAND", "srd-de")], tmp_path)
    risse = [("D ORNENWAND", "srd-de")]

    fehler = admin._pruefe_gegen_basiswerte(con, [], risse)
    con.close()

    assert fehler == 1, "ein neuer Mangel muss den Check brechen"
    ausgabe = capsys.readouterr().out
    assert "NEUE Namensmaengel" in ausgabe and "srd-de" in ausgabe


def test_unveraenderter_stand_bleibt_still(tmp_path, monkeypatch, capsys):
    """Der Normalfall. Eine Warnung, die bei jedem Lauf ansteht, liest bald niemand mehr -
    deshalb meldet der Vergleich hier nur, dass er stattgefunden hat."""
    _basis(tmp_path, {"ocr_risse_je_quelle": {"srd-de": 1}, "erhoben_am": "2026-08-01"},
           monkeypatch)
    con = _db_mit([("D ORNENWAND", "srd-de")], tmp_path)

    fehler = admin._pruefe_gegen_basiswerte(con, [], [("D ORNENWAND", "srd-de")])
    con.close()

    assert fehler == 0
    ausgabe = capsys.readouterr().out
    assert "unveraendert" in ausgabe
    assert "NEUE" not in ausgabe


def test_reparatur_wird_zum_nachziehen_gemeldet(tmp_path, monkeypatch, capsys):
    """Eine Verbesserung darf nicht stillschweigend im Basiswert versickern: Wird sie nicht
    nachgezogen, kann derselbe Mangel später unbemerkt zurückkehren."""
    _basis(tmp_path, {"ocr_risse_je_quelle": {"srd-de": 5}}, monkeypatch)
    con = _db_mit([("D ORNENWAND", "srd-de")], tmp_path)

    fehler = admin._pruefe_gegen_basiswerte(con, [], [("D ORNENWAND", "srd-de")])
    con.close()

    assert fehler == 0, "eine Verbesserung ist kein Fehler"
    ausgabe = capsys.readouterr().out
    assert "gesunken" in ausgabe and "5->1" in ausgabe
    assert "qualitaet-basis" in ausgabe, "der Weg zum Nachziehen muss dastehen"


def test_fehlende_quelle_meldet_keine_scheinverbesserung(tmp_path, monkeypatch, capsys):
    """Das Mac-Subset führt vier von fünfzehn Quellen. Ohne diese Ausnahme meldete der
    Vergleich dort elf Verbesserungen, die nur fehlende Bücher sind (Korpus-Lücke,
    CONCEPT.md §11) - und die Meldung wäre unbrauchbar."""
    _basis(tmp_path, {"ocr_risse_je_quelle": {"srd-de": 1, "xgte-2014-de": 29}}, monkeypatch)
    con = _db_mit([("D ORNENWAND", "srd-de")], tmp_path)   # xgte fehlt in dieser DB

    fehler = admin._pruefe_gegen_basiswerte(con, [], [("D ORNENWAND", "srd-de")])
    con.close()

    assert fehler == 0
    assert "xgte" not in capsys.readouterr().out


def test_metadaten_namen_duerfen_nie_wieder_steigen(tmp_path, monkeypatch, capsys):
    """46 Einträge namens 'Zeitaufwand: 1 Aktion' standen bis zum 27.07.2026 unbemerkt im
    Bestand. Seit dem KOPF_HEADING-Fix sind es null - und das soll so bleiben."""
    _basis(tmp_path, {"metadaten_namen_gesamt": 0}, monkeypatch)
    con = _db_mit([("Zeitaufwand: 1 Aktion", "srd-de")], tmp_path)

    fehler = admin._pruefe_gegen_basiswerte(con, [("Zeitaufwand: 1 Aktion", "srd-de")], [])
    con.close()

    assert fehler == 1
    assert "NEUE Metadaten-Namen" in capsys.readouterr().out


@pytest.mark.parametrize("name,ist_rauschen", [
    ("B | Monsters", True),      # DDB-Register mit geschütztem Leerzeichen
    ("J Spells", True),
    ("Spells J", True),
    ("Magic Items U", True),
    ("Monsters X", True),
    ("D ORNENWAND", False),                # echter OCR-Riss
    ("ABERGLAUB E", False),
    ("’ UPPER TAVICK S LANDING", False),   # Druck-PDF-Riss in efota-en
])
def test_registerkoepfe_gelten_nicht_als_riss(name, ist_rauschen):
    """42 der 91 gemeldeten Treffer waren Registerköpfe - fast die Hälfte der Warnung war
    Rauschen aus Büchern, die gar keine Scans sind. Es überdeckte die echten Risse und
    machte die Zahl unbrauchbar."""
    assert bool(admin._REGISTER_KOPF.match(name)) is ist_rauschen, name


def test_basisdatei_ist_lesbar_und_vollstaendig():
    """Die echte Datei im Repo - sie ist der dokumentierte Stand, gegen den jeder Lauf
    misst. Fehlt sie oder ist sie kaputt, entfällt der Vergleich lautlos."""
    basis = admin._lade_basiswerte()
    assert basis, "config/qualitaet_basis.json fehlt oder ist kein gültiges JSON"
    assert "ocr_risse_je_quelle" in basis
    assert isinstance(basis.get("metadaten_namen_gesamt"), int)
    assert basis.get("erhoben_am"), "ohne Datum ist der Stand nicht einzuordnen"
    # Jeder Zahlenblock trägt seine Erläuterung - sonst weiß niemand, was er akzeptiert.
    assert basis.get("_zweck") and basis.get("_ocr_erlaeuterung")


def test_leere_statblock_sektionen_werden_gezaehlt(tmp_path):
    """Befund 06.08.2026 (Eval-Fall B3): Der Richter warf der ANTWORT vor, beim Solar
    fehle der Block 'Bonusaktionen'. Er fehlt aber im BESTAND — die Überschrift ist dort
    die letzte Zeile des Eintrags, der Inhalt ist beim Import in den Nachbarblock
    gerutscht. Ohne diesen Zähler bleibt so ein Verlust unsichtbar und sieht in jeder
    Auskunft wie ein Modellfehler aus."""
    pfad = tmp_path / "sektionen.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (id,kuerzel,titel,sprache,edition,herkunft,"
                "prioritaet) VALUES (1,'srd-de','SRD','de','2024','pdf',10)")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,body_md) "
        "VALUES (1,?,?,'de','2024',?)",
        [# leer: Ueberschrift als letzte Zeile (der echte Solar-Fall)
         ("monster", "Solar", "###### Aktionen\n\nBogen.\n\n###### Bonusaktionen"),
         # leer: Ueberschrift direkt vor der naechsten Ueberschrift
         ("monster", "Lemure", "###### Merkmale\n\n###### Aktionen\n\nFaust."),
         # vollstaendig: zaehlt NICHT
         ("monster", "Vampirbrut", "###### Merkmale\n\nSpinnenklettern.\n\n"
                                   "###### Aktionen\n\nBiss."),
         # kein Monster: bleibt aussen vor
         ("zauber", "Feuerball", "###### Aktionen"),
         # fehlgeparste Statzeile, die eine generische Header-Suche mitzaehlen wuerde
         ("monster", "Aboleth", "###### **Resistenzen** Kälte\n\n###### Aktionen\n\nHieb.")])
    con.commit()
    con.close()

    verbindung = sqlite3.connect(pfad)
    try:
        je_quelle, beispiele = admin.messe_leere_sektionen(verbindung)
    finally:
        verbindung.close()

    assert je_quelle == {"srd-de": 2}, je_quelle
    assert any("Solar (Bonusaktionen)" == b for b in beispiele), beispiele
    assert any("Lemure (Merkmale)" == b for b in beispiele), beispiele
