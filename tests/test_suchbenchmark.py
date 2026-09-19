"""Der Such-Benchmark selbst (M10/R06).

Er ist ein Messinstrument, und ein Messinstrument, das niemand nachmisst, ist eine
Behauptung. Geprueft wird deshalb die Mechanik - Rangbestimmung, Soll-Nulltreffer,
Ueberspringen fehlender Ziele -, nicht die Guete des Bestands: Die steht als Zahl in
config/qualitaet_basis.json und wird von `admin check --vollbestand` verglichen.
"""
import argparse
import json
import sqlite3

import pytest

from app import admin as adm
from app import db as adb
from tests.hilfen import SCHEMA


@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    pfad = tmp_path / "foliant-benchmark.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,"
                "prioritaet) VALUES ('srd-de','SRD 5.2.1 (Deutsch)','de','2024','pdf',"
                "'CC-BY-4.0',10)")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [(1, "zauber", "Feuerball", "Fireball", "de", "2024", "241",
          "*Kontext: Zauber*\n\n8W6 Feuerschaden."),
         (1, "regel", "Verstecken (Aktion)", None, "de", "2024", "20",
          "*Kontext: Regeln*\n\nDu machst einen Geschicklichkeitswurf."),
         (1, "gegenstand", None, "Longsword", "de", "2024", "90",
          "*Kontext: Ausruestung*\n\nEine vielseitige Klinge.")])
    con.execute("INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
                "VALUES ('Longsword','Langschwert',1,'Spielerhandbuch','2024')")
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def _lauf(tmp_path, monkeypatch, faelle, capsys):
    datei = tmp_path / "benchmark.json"
    datei.write_text(json.dumps({"faelle": faelle}), encoding="utf-8")
    monkeypatch.setattr(adm, "SUCHBENCHMARK", datei)
    adm.cmd_suchbenchmark(argparse.Namespace(json=True))
    return json.loads(capsys.readouterr().out)


def test_treffer_wird_als_rang_gezaehlt(bestand, tmp_path, monkeypatch, capsys):
    e = _lauf(tmp_path, monkeypatch,
              [{"frage": "Feuerball", "ziel": "Feuerball", "kategorie": "zauber"}], capsys)
    assert e["treffer_at_1"] == 1 and e["mrr"] == 1.0 and not e["verfehlt"]


def test_klammerzusatz_zaehlt_als_treffer(bestand, tmp_path, monkeypatch, capsys):
    """Der Bestand fuehrt 'Verstecken (Aktion)', der Nutzer fragt 'Verstecken' - der
    Zusatz ist Qualifikator, nicht Name (dieselbe Regel wie in glossar.KLAMMER_SUFFIX)."""
    e = _lauf(tmp_path, monkeypatch,
              [{"frage": "Verstecken", "ziel": "Verstecken", "kategorie": "regel"}], capsys)
    assert e["treffer_at_1"] == 1, e["verfehlt"]


def test_deutscher_name_aus_dem_glossar_zaehlt(bestand, tmp_path, monkeypatch, capsys):
    """63 % der Eintraege tragen keinen `name_de`; ihr deutscher Name entsteht erst in
    der Ausgabe. Gemessen wird, was ANKOMMT - sonst muesste der Benchmark seine Ziele
    englisch fuehren und haette ausgerechnet Deutsch-first nicht mehr im Blick."""
    e = _lauf(tmp_path, monkeypatch,
              [{"frage": "Langschwert", "ziel": "Langschwert", "kategorie": "gegenstand"}],
              capsys)
    assert e["treffer_at_1"] == 1, e["verfehlt"]


def test_soll_nulltreffer_wird_belohnt_nicht_bestraft(bestand, tmp_path, monkeypatch, capsys):
    """Die wertvollsten Faelle: Ein Benchmark, der nur Treffer belohnt, treibt geradewegs
    in die Halluzination, gegen die Kernregel 1 steht."""
    e = _lauf(tmp_path, monkeypatch,
              [{"frage": "Silvery Barbs", "ziel": None}], capsys)
    assert e["treffer_at_1"] == 1 and not e["verfehlt"]


def test_unerwarteter_treffer_auf_einen_nulltreffer_faellt_auf(bestand, tmp_path,
                                                               monkeypatch, capsys):
    e = _lauf(tmp_path, monkeypatch, [{"frage": "Feuerball", "ziel": None}], capsys)
    assert e["treffer_at_1"] == 0
    assert "sollte LEER sein" in e["verfehlt"][0]


def test_fehlendes_ziel_wird_uebersprungen_nicht_verfehlt(bestand, tmp_path,
                                                          monkeypatch, capsys):
    """Dieselbe Regel, mit der `_vergleiche_je_quelle` fehlende Quellen auslaesst: Ein
    Ziel, das der geprueufte Bestand gar nicht fuehrt, ist kein Ranking-Problem. Ohne
    diese Schranke meldete das Mac-Subset Scheinverfehlungen fuer Buecher, die es nicht
    hat - und der Basiswert waere fuer eine der beiden Umgebungen immer falsch."""
    e = _lauf(tmp_path, monkeypatch,
              [{"frage": "Beholder", "ziel": "Beholder", "kategorie": "monster"}], capsys)
    assert e["uebersprungen"] == 1 and e["faelle"] == 0 and not e["verfehlt"]


def test_falsche_kategorie_zaehlt_nicht_als_treffer(bestand, tmp_path, monkeypatch, capsys):
    """'Feuerball' als monster gefragt darf den Zauber nicht gutschreiben - sonst
    verdeckte der Benchmark genau die Kategorie-Verwechslung aus R02."""
    e = _lauf(tmp_path, monkeypatch,
              [{"frage": "Feuerball", "ziel": "Feuerball", "kategorie": "monster"}], capsys)
    assert e["uebersprungen"] == 1, "Ziel existiert in dieser Kategorie nicht"


def test_benchmark_schreibt_nicht_ins_abfrage_protokoll(bestand, tmp_path, monkeypatch):
    """Eigene Messreihen im Suchbericht sind ein bekannter Gotcha (CONCEPT §12) - der
    Kurations-Durchgang wuerde sonst Testdaten kuratieren."""
    from app import protokoll as _protokoll

    gerufen = []
    monkeypatch.setattr(_protokoll, "protokolliere",
                        lambda *a, **k: gerufen.append(a))
    datei = tmp_path / "b.json"
    datei.write_text(json.dumps({"faelle": [{"frage": "Feuerball", "ziel": "Feuerball",
                                             "kategorie": "zauber"}]}), encoding="utf-8")
    monkeypatch.setattr(adm, "SUCHBENCHMARK", datei)
    adm.cmd_suchbenchmark(argparse.Namespace(json=True))
    assert gerufen == []


def test_echter_datensatz_ist_wohlgeformt():
    """Die ausgelieferte Datei selbst: Jeder Fall braucht eine Frage, und ein Ziel ohne
    Kategorie waere mehrdeutig (dieselbe Frage kann in zwei Kategorien landen)."""
    daten = json.loads(adm.SUCHBENCHMARK.read_text(encoding="utf-8"))
    fragen = [f["frage"] for f in daten["faelle"]]
    assert len(fragen) == len(set(fragen)), "doppelte Frage im Datensatz"
    for fall in daten["faelle"]:
        assert fall.get("frage"), fall
        if fall.get("ziel") is not None:
            assert fall.get("kategorie"), f"Ziel ohne Kategorie: {fall}"
        else:
            assert fall.get("warum"), f"Soll-Nulltreffer ohne Begruendung: {fall}"
