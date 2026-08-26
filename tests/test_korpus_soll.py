"""`admin check` kann die Frage „ist noch alles da?" stellen - vorher konnte er es nicht.

Anlass (Review 14.08.2026, S-01): Der Check verglich die Eintragszahl nur mit der eigenen
FTS-Zeilenzahl. Beide fallen bei einem verlorenen Buch GEMEINSAM, der Vergleich blieb also
gruen; ein Rueckgang galt als „Basiswert nachziehen". Eine fehlende Quelle war damit
unsichtbar.

Die zweite Haelfte des Befunds ist die interessantere: Die Pruefung darf lokal nicht
dauerhaft rot stehen, weil die Dev-DB ein SUBSET ist (7 von 18 Quellen). Eine Kennzahl,
die immer rot ist, hoert man auf zu lesen - deshalb `streng` nur am Vollbestand.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.admin import pruefe_korpus_soll
from tests.hilfen import neue_db

SOLL = {
    "erhoben_an": "2026-08-14",
    "eintraege_gesamt": 30,
    "quellen": [
        {"kuerzel": "srd-de", "edition": "2024", "eintraege": 20},
        {"kuerzel": "efota-en", "edition": "2024", "eintraege": 10},
    ],
}


@pytest.fixture
def baue(tmp_path):
    """Liefert (bestand, soll) -> (Verbindung, Soll-Pfad)."""
    def _baue(bestand: dict[str, int], soll: dict | None = SOLL):
        con = neue_db(tmp_path / "test.sqlite")
        for i, (kuerzel, anzahl) in enumerate(bestand.items(), start=1):
            con.execute("INSERT INTO quellen (id, kuerzel, titel, sprache, edition, "
                        "herkunft, lizenz) VALUES (?,?,?,?,?,?,?)",
                        (i, kuerzel, kuerzel, "de", "2024", "manuell", "privat"))
            for n in range(anzahl):
                con.execute("INSERT INTO eintraege (quelle_id, kategorie, name_de, sprache, "
                            "edition, body_md) VALUES (?,?,?,?,?,?)",
                            (i, "regel", f"{kuerzel}-{n}", "de", "2024", "x" * 40))
        con.commit()
        pfad = tmp_path / "korpus_soll.json"
        if soll is not None:
            pfad.write_text(json.dumps(soll), encoding="utf-8")
        return con, pfad
    return _baue


def test_vollstaendiger_bestand_ist_ok(baue):
    con, pfad = baue({"srd-de": 20, "efota-en": 10})
    fehler, zeilen = pruefe_korpus_soll(con, streng=True, soll_pfad=pfad)
    assert fehler == 0
    assert "OK" in zeilen[0]


def test_fehlende_quelle_ist_am_vollbestand_ein_fehler(baue):
    """Der Fall, den es vorher nicht gab: eine Quelle kommt gar nicht erst mit."""
    con, pfad = baue({"srd-de": 20})
    fehler, zeilen = pruefe_korpus_soll(con, streng=True, soll_pfad=pfad)
    assert fehler == 1
    assert any("FEHLENDE Quellen" in z and "efota-en" in z for z in zeilen)


def test_fehlende_quelle_ist_lokal_kein_fehler(baue):
    """Auf der Dev-Maschine ist genau das der Normalfall - sonst stuende das Gate
    dauerhaft rot und niemand laese es noch."""
    con, pfad = baue({"srd-de": 20})
    fehler, zeilen = pruefe_korpus_soll(con, streng=False, soll_pfad=pfad)
    assert fehler == 0
    assert any("Dev-Subset" in z for z in zeilen)


def test_eingebrochene_quelle_faellt_auf(baue):
    """Die Quelle ist da, aber halb leer - der Fall, den der FTS-Vergleich nie sah,
    weil Eintraege und FTS-Zeilen gemeinsam fallen."""
    con, pfad = baue({"srd-de": 20, "efota-en": 4})
    fehler, zeilen = pruefe_korpus_soll(con, streng=True, soll_pfad=pfad)
    assert fehler == 1
    assert any("'efota-en'" in z and "4 statt 10" in z for z in zeilen)


def test_einbruch_ist_lokal_nur_warnung(baue):
    """Am Subset kann dieselbe Quelle legitim kleiner sein - melden ja, brechen nein."""
    con, pfad = baue({"srd-de": 20, "efota-en": 4})
    fehler, zeilen = pruefe_korpus_soll(con, streng=False, soll_pfad=pfad)
    assert fehler == 0
    assert any("WARNUNG" in z for z in zeilen)


def test_kleine_schwankung_bricht_nicht(baue):
    """Ein Re-Import schwankt um einzelne Chunks; die Toleranz soll den Einbruch finden,
    nicht die Kommastelle. 19 von 20 sind 5 % - gerade noch drin."""
    con, pfad = baue({"srd-de": 19, "efota-en": 10})
    fehler, _ = pruefe_korpus_soll(con, streng=True, soll_pfad=pfad)
    assert fehler == 0


def test_neue_quelle_ist_hinweis_kein_fehler(baue):
    """Ein beabsichtigter Import darf das Gate nicht brechen - er soll nur auffallen."""
    con, pfad = baue({"srd-de": 20, "efota-en": 10, "neu-en": 5})
    fehler, zeilen = pruefe_korpus_soll(con, streng=True, soll_pfad=pfad)
    assert fehler == 0
    assert any("Neue Quellen" in z and "neu-en" in z for z in zeilen)


def test_ohne_soll_datei_wird_uebersprungen(baue):
    """Ein frisches Repo ohne erhobenen Sollstand soll nicht scheitern."""
    con, pfad = baue({"srd-de": 20}, soll=None)
    fehler, zeilen = pruefe_korpus_soll(con, streng=True, soll_pfad=pfad)
    assert fehler == 0 and "fehlt" in zeilen[0]


def test_echte_solldatei_passt_zum_schema():
    """Die eingecheckte Datei muss die Felder tragen, die die Pruefung liest - sonst
    faellt es erst am Pi auf."""
    pfad = pathlib.Path(__file__).resolve().parents[1] / "config" / "korpus_soll.json"
    soll = json.loads(pfad.read_text("utf-8"))
    assert soll["quellen"] and soll["eintraege_gesamt"] > 0
    for q in soll["quellen"]:
        assert q["kuerzel"] and isinstance(q["eintraege"], int)
    # Buchtitel gehoeren bewusst NICHT hinein, solange die Veroeffentlichungsfrage
    # offen ist (BACKLOG M9).
    assert all("titel" not in q for q in soll["quellen"])
