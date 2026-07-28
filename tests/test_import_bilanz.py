"""Import beobachtbar machen (Phase 4) - Befunde D1, D2, D3, D6 und C3.

Die Verifikation, die der Plan verlangt: ein absichtlich fehlerhafter Import muss in der
Bilanz auffallen UND am Wachstums-Schutz abbrechen. Genau das war vorher nicht so - ein
Import, der zehnmal so viele Chunks lieferte, lief kommentarlos durch.
"""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from importer import schwellen
from importer.import_glossar import ist_begriff
from importer.import_markdown import _chunks, importiere_markdown, letzte_bilanz

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture()
def con(tmp_path):
    pfad = tmp_path / "bilanz.sqlite"
    c = sqlite3.connect(pfad)
    c.executescript(_SCHEMA.read_text(encoding="utf-8"))
    c.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
              "VALUES ('testbuch','Testbuch','de','2024','pdf',10)")
    c.commit()
    c.close()
    verbindung = adb.connect(str(pfad))
    yield verbindung
    verbindung.close()


# --------------------------------------------------------------------- D3 Schwellen

def test_wachstumsschutz_bricht_bei_zerlegungsfehler_ab():
    """Das fehlende Gegenstueck zum Schrumpf-Schutz: ein falsches Split-Level
    vervielfacht die Chunkzahl - vorher lief das kommentarlos durch."""
    with pytest.raises(ValueError, match="Wachstums-Schutz"):
        schwellen.pruefe_umfang("testbuch", neu=3000, alt=300)


def test_schrumpfschutz_greift_weiter():
    with pytest.raises(ValueError, match="Schrumpf-Schutz"):
        schwellen.pruefe_umfang("testbuch", neu=100, alt=300)


@pytest.mark.parametrize("neu,alt", [(300, 300), (450, 300), (899, 300), (200, 300),
                                     (5000, 0)])
def test_plausible_umfaenge_passieren(neu, alt):
    """Auch der Erstimport (alt=0): ohne Altbestand gibt es keinen Massstab."""
    schwellen.pruefe_umfang("testbuch", neu=neu, alt=alt)


def test_force_setzt_beide_richtungen_ausser_kraft():
    schwellen.pruefe_umfang("testbuch", neu=3000, alt=300, erlaubt=True)
    schwellen.pruefe_umfang("testbuch", neu=1, alt=300, erlaubt=True)


def test_schwellen_haben_genau_eine_quelle():
    """D3: vorher lagen drei Schwellen in drei Modulen. Die alten Namen bleiben als
    Re-Export bestehen, muessen aber denselben Wert liefern."""
    from importer import import_ddb, import_markdown, ocr_vorstufe
    assert import_markdown.SCHRUMPF_SCHWELLE is schwellen.SCHRUMPF_SCHWELLE
    assert import_ddb.MIN_REIMPORT_RATIO is schwellen.DDB_SCHRUMPF_SCHWELLE
    assert ocr_vorstufe.SCAN_SCHWELLE is schwellen.SCAN_SCHWELLE


# ------------------------------------------------------------------------ D1 Bilanz

def test_bilanz_zaehlt_text_vor_dem_ersten_heading(con):
    """Deckblatt/Praeambel wird bewusst verworfen - aber nicht mehr stillschweigend.
    Versagt die Heading-Erkennung einer Quelle, landet hier das halbe Buch."""
    markdown = ("Ein Deckblatt ohne Ueberschrift.\nNoch eine Vorspannzeile.\n\n"
                "# Kapitel\n\n## Regel A\n\nText der Regel A.\n")
    importiere_markdown(con, "testbuch", markdown, edition="2024")
    bilanz = letzte_bilanz()
    assert bilanz.verworfen.get("Zeile vor dem ersten Heading (Deckblatt/Praeambel)") == 2
    assert "2x Zeile vor dem ersten Heading" in bilanz.zeile()


def test_bilanz_meldet_eine_reparatur_ohne_anker(con):
    """Der eigentliche Zweck (D1): ein PDF-Update verschiebt einen Anker, die kuratierte
    Reparatur passiert lautlos NICHT. Vorher gab es dafuer kein Signal."""
    from importer.import_markdown import _BILANZ, _verschiebe

    _BILANZ.wirkungslos.clear()
    unveraendert = _verschiebe("nur etwas Text", r"^GIBTSNICHT$", r"^AUCHNICHT$", r"^EGAL$")
    assert unveraendert == "nur etwas Text"          # defensiv: Text bleibt wie er war
    assert _BILANZ.wirkungslos, "fehlender Anker blieb unbemerkt"
    assert "WIRKUNGSLOS" in _BILANZ.zeile()
    assert _BILANZ.auffaellig is True


def test_bilanz_ist_je_import_frisch(con):
    """Sonst summieren sich die Zahlen ueber Laeufe und die Veraenderung - das eigentlich
    interessante Signal - ist nicht mehr ablesbar."""
    markdown = "Vorspann.\n\n# Kapitel\n\n## Regel A\n\nText.\n"
    importiere_markdown(con, "testbuch", markdown, edition="2024")
    erst = dict(letzte_bilanz().verworfen)
    importiere_markdown(con, "testbuch", markdown, edition="2024")
    assert dict(letzte_bilanz().verworfen) == erst


def test_sauberer_import_schlaegt_keinen_alarm(con):
    """Gegenprobe - die Bilanz darf nicht bei jedem Lauf rot leuchten, sonst liest sie
    niemand mehr (dieselbe Ueberlegung wie beim Glossar-Konflikt-Gate).

    Ein Kapitel-Kopf OHNE eigenen Text ist dabei der strukturelle Normalfall (seine Kinder
    haben den Text) - er wird gezaehlt, weil ein Sprung der Zahl etwas bedeutet, aber er
    macht die Bilanz NICHT auffaellig. Auffaellig ist allein die wirkungslose Reparatur."""
    markdown = "# Kapitel\n\n## Regel A\n\nText A.\n\n## Regel B\n\nText B.\n"
    importiere_markdown(con, "testbuch", markdown, edition="2024")
    bilanz = letzte_bilanz()
    assert bilanz.verworfen == {"Abschnitt ohne Regeltext (leerer Body)": 1}
    assert bilanz.auffaellig is False
    assert "WIRKUNGSLOS" not in bilanz.zeile()


# --------------------------------------------------------------------------- D6 NBSP

def test_geschuetztes_leerzeichen_im_namen_wird_normalisiert():
    """U+00A0 != U+0020 bricht die exakte Namenssuche (28 Faelle in
    ddb-basic-rules-2014-en). Reines Druck-Layout, an der Wurzel normalisiert."""
    chunks = _chunks("# Kapitel\n\n## Classes Summary\n\nText dazu.\n")
    namen = [c["name"] for c in chunks]
    assert "Classes Summary" in namen
    assert not any(" " in n for n in namen)


# ---------------------------------------------------------------------------- C3

@pytest.mark.parametrize("term,erwartet", [
    ("Backpack", True),
    ("Mask of the Wild", True),
    ("Alchemist's Supplies", True),
    # Der reale Fehleintrag: eine Schatzbeschreibung als 'Begriff'.
    ("Ceremonial electrum dagger with a black pearl set in the pommel", False),
    ("", False),
    ("ein satz mit deutlich zu vielen einzelnen woertern darin fuer einen begriff", False),
])
def test_glossar_begriff_ist_ein_name_kein_satz(term, erwartet):
    assert ist_begriff(term) is erwartet
