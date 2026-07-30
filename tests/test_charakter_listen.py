"""Was die OPTIONSLISTEN dem Modell zeigen (Review 30.07.2026).

Die Nachschlage-Werkzeuge hatten fuer diese Fehlerformen laengst Leitplanken; die
Charakter-Werkzeuge daneben nicht - jede Leitplanke sass genau an dem Pfad, an dem der
Fehler damals auffiel:

  L1  `_markiere_abenteuer` lief in nachschlagen.py an JEDER Ausgabeliste, in charakter.py
      an keiner einzigen. Die Optionslisten mischten Regelwerk und Abenteuer-/Setting-Band
      ununterscheidbar - gemessen am echten Bestand stammten 75 von 92 Talenten aus einem
      Abenteuerband, keines davon markiert. Spoiler-Schutz ist die OBERSTE Regel (B6).
  L2  Die Listenzeilen trugen keine `eintrag_id`. SYN-P1-002 sichert den Rundlauf
      Liste -> Detail ausdruecklich zu; `_knapp` setzt das Feld seit jeher, `_zeile` nicht.
  L3  Die Klassen-Weiche kannte nur `kontext == 'Klassen'` und das deutsche Namensschema
      '<Klasse>-Unterklasse: <Name>'. Unterklassen aus englischen Druckquellen ('SUBCLASSES',
      'ARTIFICER SUBCLASSES') fielen aus BEIDEN Listen - lautlos, obwohl foliant_hol_eintrag
      sie liefert. Am echten Bestand waren das 13 Stueck.
  L4  Traegt eine Waisen-Zeile (Unterklasse ohne Klasse im Bestand) spaeter selbst eine
      Unterklasse, griff der Code auf ein nie gesetztes Feld zu -> KeyError, das ganze
      Werkzeug fiel aus.
"""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app.tools import charakter as ch
from app.tools import nachschlagen as ns

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    """Zwei Quellen: ein Regelwerk und ein Abenteuer-/Setting-Band. Die Klassen decken die
    DREI Schreibweisen ab, in denen Quellen eine Unterklasse ihrer Klasse zuordnen:
    deutscher Namenspraefix, '*Subclass of:*' im Body, Klammer-Suffix am Namen."""
    pfad = tmp_path / "foliant-charakterlisten.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet,"
        "inhaltsart) VALUES (?,?,?,?,?,?,?,?)",
        [("srd-de", "SRD 5.2.1 (Deutsch)", "de", "2024", "pdf", "CC-BY-4.0", 10,
          "regelwerk"),
         ("efota-en", "Eberron: Forge of the Artificer (Druck)", "en", "2024", "pdf",
          "privat", 40, "abenteuer_setting")])
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [# --- Regelwerk: Klasse + Unterklasse im deutschen Namensschema
         (1, "klasse", "Magier", "Wizard", "de", "2024", "88",
          "*Kontext: Klassen*\n\nHauptmerkmale des Magiers."),
         (1, "klasse", "Magier-Unterklasse: Hervorrufer", None, "de", "2024", "92",
          "*Kontext: Klassen > Magier*\n\n_Meister der Energie_"),
         # Unterabschnitte: duerfen in KEINER Liste auftauchen (weder Klasse noch Unterklasse)
         (1, "klasse", "Klassenmerkmale des Magiers", None, "de", "2024", "89",
          "*Kontext: Klassen > Magier*\n\nAls Magier erhaeltst du folgende Merkmale."),
         (1, "klasse", "Zauberliste des Magiers", None, "de", "2024", "90",
          "*Kontext: Klassen > Magier*\n\nDie Zauber des Magiers."),
         # --- Abenteuerband: Unterklasse mit Klammer-Suffix unter 'SUBCLASSES'
         (2, "klasse", None, "BLADESINGER (WIZARD)", "en", "2024", "31",
          "*Kontext: SUBCLASSES*\n\nA wizard who fights with blade and spell."),
         # --- Abenteuerband: Talent, das es NUR dort gibt
         (2, "talent", None, "ABERRANT DRAGONMARK", "en", "2024", "47",
          "*Kontext: General Feats*\n\nYou have manifested an aberrant dragonmark."),
         (1, "talent", "Wachsam", "Alert", "de", "2024", "200",
          "*Kontext: Allgemeine Talente*\n\n_Allgemeines Talent_\n\nDu bist wachsam."),
         # --- ZWEI Unterklassen einer Klasse, die es im Bestand NICHT gibt (der
         # Artificer-Fall: seine Merkmale sind importiert, eine Klassen-Zeile nicht).
         # Die erste wird zur Waisen-Zeile, die zweite findet sie als Ziel wieder.
         (2, "klasse", None, "ALCHEMIST (ARTIFICER)", "en", "2024", "18",
          "*Kontext: ARTIFICER SUBCLASSES*\n\nAn artificer of potions."),
         (2, "klasse", None, "ARMORER (ARTIFICER)", "en", "2024", "19",
          "*Kontext: ARTIFICER SUBCLASSES*\n\nAn artificer of armor."),
         # --- Spezies fuer den Rundlauf-Test
         (1, "spezies", "Zwerg", "Dwarf", "de", "2024", "94",
          "*Kontext: Beschreibungen der Spezies*\n\nZwerge sind zaeh."),
         ])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def test_optionsliste_kennzeichnet_abenteuerherkunft(bestand):
    """L1 - der schwerste der vier. Ein Talent, das es nur im Abenteuerband gibt, stand
    ununterscheidbar zwischen den Regelwerks-Talenten; das Modell konnte daraus zitieren,
    ohne die Kennzeichnung je gesehen zu haben."""
    r = ch.foliant_liste_optionen("talent")
    nach_namen = {t["name_de"] or t["name_en"]: t for t in r["talente"]}
    assert nach_namen["ABERRANT DRAGONMARK"].get("inhaltsart") == "abenteuer_setting"
    assert nach_namen["Wachsam"].get("inhaltsart") is None, "Regelwerk faelschlich markiert"
    assert "Spoiler" in (r.get("hinweis_inhaltsart") or "")


def test_geschachtelte_unterklassen_sind_ebenfalls_gekennzeichnet(bestand):
    """L1, zweite Tuer: Unterklassen liegen verschachtelt unter ihrer Klasse. Eine
    Kennzeichnung, die nur die oberste Ebene erreicht, laesst genau die Zeilen
    unmarkiert, die aus dem Abenteuerband stammen."""
    magier = next(k for k in ch.foliant_liste_optionen("klasse")["klassen"]
                  if k["name_de"] == "Magier")
    nach_namen = {u["name_de"] or u["name_en"]: u for u in magier["unterklassen"]}
    assert nach_namen["BLADESINGER"].get("inhaltsart") == "abenteuer_setting"
    assert nach_namen["Hervorrufer"].get("inhaltsart") is None


def test_listenzeile_traegt_eintrag_id_und_loest_wieder_auf(bestand):
    """L2 - SYN-P1-002 sichert den Rundlauf zu. Ohne eintrag_id musste das Modell den
    gerade gezeigten Eintrag ueber seinen NAMEN erneut suchen und lief damit in dieselbe
    Mehrdeutigkeit, die die Liste gerade aufgeloest hatte."""
    zeile = ch.foliant_liste_optionen("spezies")["spezies"][0]
    assert isinstance(zeile["eintrag_id"], int)
    assert ns.foliant_hol_eintrag("spezies", eintrag_id=zeile["eintrag_id"])["name_de"] == "Zwerg"


def test_unterklasse_aus_druckquelle_geht_nicht_verloren(bestand):
    """L3 - 'BLADESINGER (WIZARD)' steht unter dem Kapitel 'SUBCLASSES' und traegt seine
    Klasse als Klammer-Suffix: weder 'Klassen > X' noch das deutsche Namensschema. Vorher
    fiel der Eintrag aus BEIDEN Listen, obwohl foliant_hol_eintrag ihn liefert."""
    magier = next(k for k in ch.foliant_liste_optionen("klasse")["klassen"]
                  if k["name_de"] == "Magier")
    namen = {u["name_de"] or u["name_en"] for u in magier["unterklassen"]}
    assert "BLADESINGER" in namen, f"Unterklasse verschluckt: {namen}"


def test_klammer_suffix_wird_nicht_als_deutsch_first_missverstanden(bestand):
    """Der Anzeigename darf nicht 'BLADESINGER (WIZARD)' lauten: dieses Format bedeutet in
    jeder anderen Ausgabe 'Deutsch (English)' - der Klassenname saehe aus wie die englische
    Entsprechung der Unterklasse (S3/S4)."""
    magier = next(k for k in ch.foliant_liste_optionen("klasse")["klassen"]
                  if k["name_de"] == "Magier")
    bs = next(u for u in magier["unterklassen"] if (u["name_en"] or "") == "BLADESINGER")
    assert bs["anzeige"] == "BLADESINGER"


def test_zwei_waisen_derselben_fehlenden_klasse_stuerzen_nicht_ab(bestand):
    """L4 - 'ALCHEMIST (ARTIFICER)' wird zur Waisen-Zeile, weil der Artificer keine
    Klassen-Zeile im Bestand hat. Die zweite Artificer-Unterklasse findet diese Zeile
    dann als Ziel wieder - und griff auf ein Feld zu, das nur echte Klassen-Zeilen
    tragen. Ergebnis war ein KeyError: das ganze Werkzeug fiel aus, statt eine
    unvollstaendige Liste zu liefern.

    Der Absturz war schon vor L3 erreichbar - ueber zwei Open5e-Unterklassen mit
    '*Subclass of: X*' zu einem nicht importierten X. Ueber die Druckquellen wurde er
    erst durch L3 erreichbar, weil deren Unterklassen vorher gar nicht erst in der
    Zuordnungsschleife ankamen. Verifiziert am 30.07.2026: mit L3 und ohne setdefault
    wirft dieser Fall KeyError: 'unterklassen'."""
    r = ch.foliant_liste_optionen("klasse")                      # darf schlicht nicht werfen
    waisen = [k for k in r["klassen"] if k.get("hinweis")]
    assert waisen, "Waisen-Fall nicht erzeugt - Fixture pruefen"
    assert all("nicht im Bestand" in w["hinweis"] for w in waisen), \
        "Waise ohne ehrlichen Hinweis - sie saehe wie eine waehlbare Klasse aus (B2)"


def test_unterabschnitte_bleiben_aus_beiden_listen_draussen(bestand):
    """Gegenprobe zu L3: die Weiche darf nicht in die andere Richtung kippen.
    'Klassenmerkmale des Magiers' und 'Zauberliste des Magiers' sind Unterabschnitte -
    foliant_hol_eintrag weist sie als 'verwandte_abschnitte' aus, die LISTE nicht."""
    klassen = ch.foliant_liste_optionen("klasse")["klassen"]
    alle = {k["name_de"] or k["name_en"] for k in klassen}
    alle |= {u["name_de"] or u["name_en"]
             for k in klassen for u in k.get("unterklassen", [])}
    assert "Klassenmerkmale des Magiers" not in alle
    assert "Zauberliste des Magiers" not in alle
