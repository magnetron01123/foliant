"""Das Register bekannter Fehler IN DEN QUELLEN (config/quellfehler.py).

Ein Register, das behauptet statt zu belegen, ist schlimmer als keines: Es sieht aus wie
eine gepruefte Aussage und ist eine Meinung. Deshalb prueft diese Datei beide Richtungen:

  * Steht der dokumentierte Wortlaut WIRKLICH so im Bestand? (Sonst ist der Eintrag
    veraltet - der Fall gilt dann als ungeprueft, nicht als geheilt.)
  * Geht die Rechnung fuer den als richtig eingetragenen Wert WIRKLICH auf, und fuer den
    gedruckten wirklich nicht? So kann kein Registereintrag mit falschem 'richtig'-Wert
    unbemerkt hereinkommen.

Und die Grundregel selbst: Der ausgelieferte Regeltext bleibt unveraendert. Das Register
stellt die Korrektur DANEBEN, es ersetzt nie - dieselbe Zusage wie bei einem Erratum (V9),
nur ohne amtliches Korrekturdokument.
"""
import re
import sqlite3

import pytest

from app import db as adb
from app import logikpruefung as lp
from app.tools import nachschlagen as ns
from config import quellfehler as qf
from tests.hilfen import SCHEMA


def test_register_ist_widerspruchsfrei():
    """Formale Mindestanforderungen an jeden Eintrag - sie kosten nichts und verhindern
    den halbfertigen Eintrag, der spaeter niemandem mehr erklaerbar ist."""
    schluessel = [(e.quelle, e.name) for e in qf.BEKANNTE_QUELLFEHLER]
    assert len(schluessel) == len(set(schluessel)), "doppelter Registerschluessel"
    for e in qf.BEKANNTE_QUELLFEHLER:
        assert e.wortlaute and all(e.wortlaute), f"{e.name}: kein Wortlaut"
        assert e.richtig and e.richtig not in e.wortlaute, f"{e.name}: 'richtig' = falsch"
        assert len(e.beleg) > 80, f"{e.name}: Beleg zu duenn - er traegt die Aussage"
        assert e.wirkung, f"{e.name}: ohne Wirkung ist unklar, warum es jemanden angeht"


def test_belegte_werte_gehen_rechnerisch_auf():
    """Der wichtigste Test der Datei: Fuer die zwei TP-Faelle muss die Rechnung mit dem
    REGISTRIERTEN Wert aufgehen und mit dem GEDRUCKTEN nicht. Ein Zahlendreher im Register
    faellt damit sofort auf, statt als 'Korrektur' ausgeliefert zu werden."""
    geprueft = 0
    for e in qf.BEKANNTE_QUELLFEHLER:
        for wortlaut in e.wortlaute:
            if not re.search(r"\d+\s*[WwDd]\d+", wortlaut):
                continue
            assert lp.pruefe_tp_formel(wortlaut), f"{e.name}: {wortlaut} ist gar kein Befund"
            label = wortlaut.split("(")[0]
            assert lp.pruefe_tp_formel(f"{label}({e.richtig.split('(')[-1]}") == [], \
                f"{e.name}: der als richtig registrierte Wert geht selbst nicht auf"
            geprueft += 1
    assert geprueft == 2, f"erwartet 2 rechenbare Faelle, geprueft {geprueft}"


def test_zuordnung_ist_exakt_und_nicht_unscharf():
    """Ein falsch zugeordneter Korrekturhinweis ist schlimmer als keiner - er behauptet
    einen Fehler an einem Statblock, der ihn nicht hat."""
    assert qf.quellfehler_zu("srd-de", "Balor", None).name == "Balor"
    assert qf.quellfehler_zu("srd-de", "Balors", None) is None
    assert qf.quellfehler_zu("open5e-srd-2024", "Balor", None) is None   # falsche Quelle
    assert qf.quellfehler_zu(None, "Balor", None) is None


@pytest.mark.parametrize("eintrag", qf.BEKANNTE_QUELLFEHLER, ids=lambda e: e.name)
def test_wortlaut_steht_so_im_echten_bestand(eintrag):
    """Beleg, kein Deckel: Verschwindet der Wortlaut (Re-Import, PDF-Update), ist der Fall
    ungeprueft. Quellen, die diese Datenbank nicht fuehrt, werden uebersprungen - das
    Mac-Subset fuehrt nicht alle (CONCEPT.md, Korpus-Luecke)."""
    pfad = adb.standard_pfad()
    if not pfad.exists():
        pytest.skip("kein echter Bestand")
    con = adb.connect_readonly(str(pfad))
    try:
        if not con.execute("SELECT 1 FROM quellen WHERE kuerzel = ?",
                           (eintrag.quelle,)).fetchone():
            pytest.skip(f"Quelle {eintrag.quelle} in dieser DB nicht importiert")
        zeilen = con.execute(
            "SELECT e.body_md FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
            "WHERE q.kuerzel = ? AND (e.name_de = ? OR e.name_en = ?)",
            (eintrag.quelle, eintrag.name, eintrag.name)).fetchall()
        assert zeilen, f"{eintrag.name}: kein Eintrag mit diesem Namen"
        assert any(eintrag.steht_noch_im_bestand(z[0]) for z in zeilen), (
            f"{eintrag.name}: der dokumentierte Wortlaut {eintrag.wortlaute} steht nicht "
            f"mehr im Bestand - Register nachziehen (config/quellfehler.py)")
    finally:
        con.close()


@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    """Ein Mini-Bestand mit genau dem registrierten Balor-Wortlaut."""
    pfad = tmp_path / "foliant-quellfehler.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet,"
        "inhaltsart) VALUES ('srd-de','SRD 5.2.1','de','2024','pdf','CC-BY-4.0',20,"
        "'regelwerk')")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [(1, "monster", "Balor", None, "de", "2024", "302",
          "_Gigantischer Unhold_\n\n**RK** 19 **TP** 287 (23W12+161)\n\nFeuerpeitsche."),
         (1, "monster", "Bulette", None, "de", "2024", "310",
          "_Grosses Monstrositaet_\n\n**RK** 17 **TP** 94 (9W10+45)\n\nBiss.")])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def test_auskunft_nennt_die_korrektur_und_laesst_den_text_stehen(bestand):
    """Die Kernzusage in einem Test: Der Regeltext geht WOERTLICH raus, die belegte
    Korrektur steht daneben. Waere der Text still ersetzt, stuende die Aenderung in keinem
    Diff und waere beim naechsten Re-Import weg."""
    d = ns.foliant_hol_eintrag("monster", "Balor")
    assert "23W12+161" in d["regeltext_md"], "der Quelltext wurde veraendert"
    hinweis = d.get("hinweis_quellfehler", "")
    assert "23W12+138" in hinweis and "23W12+161" in hinweis
    assert "nicht stillschweigend ersetzen" in hinweis


def test_eintrag_ohne_registereintrag_traegt_keinen_hinweis(bestand):
    """Ein Feld, das ueberall steht, sagt nichts mehr."""
    d = ns.foliant_hol_eintrag("monster", "Bulette")
    assert "hinweis_quellfehler" not in d


def test_hinweis_verschwindet_wenn_die_quelle_repariert_wurde(bestand, monkeypatch):
    """Korrigiert eine spaetere Auflage den Druckfehler, darf der Hinweis nicht weiter
    behaupten, er staende noch da. Der Wortlaut-Abgleich erledigt das von selbst."""
    con = sqlite3.connect(bestand)
    con.execute("UPDATE eintraege SET body_md = replace(body_md,'23W12+161','23W12+138') "
                "WHERE name_de = 'Balor'")
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    d = ns.foliant_hol_eintrag("monster", "Balor")
    assert "hinweis_quellfehler" not in d


def test_register_fuehrt_nur_faelle_die_im_bestand_bleiben_sollen():
    """Abgrenzung zum Import-Gurt (importer/import_open5e.kreatur_unplausibel), die am
    03.08.2026 aus einem realen Fall entstand: Der Open5e-'Octopus' (KON 0, Rettungswurf
    +30) stand erst hier und wird jetzt beim Import verworfen.

    Das Kriterium ist, ob der Eintrag im Bestand STEHEN SOLL. Ein Fehler in einem BUCH
    bleibt drin - der Text ist der Buchtext, die Korrektur steht daneben. Ein kaputter
    DATENSATZ einer API kann ersatzlos entfallen; er kommt von selbst zurueck, sobald die
    Quelle ihn repariert. Ein Register-Eintrag fuer eine API-Quelle waere deshalb ein
    Widerspruch: Er hielte einen Statblock im Bestand, mit dem man wuerfeln kann und der
    grob falsch ist."""
    api_quellen = {"open5e-srd-2024", "open5e-srd-2014"}
    drin = [e.name for e in qf.BEKANNTE_QUELLFEHLER if e.quelle in api_quellen]
    assert not drin, (f"{drin} stehen im Register, obwohl sie aus einer API-Quelle kommen "
                      f"- dort gehoert der Gurt in den Importer, nicht der Beleg hierher")
