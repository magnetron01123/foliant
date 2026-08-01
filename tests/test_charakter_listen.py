"""Was die OPTIONSLISTEN dem Modell zeigen (Review 30.07.2026).

Die Nachschlage-Werkzeuge hatten fuer diese Fehlerformen laengst Leitplanken; die
Charakter-Werkzeuge daneben nicht - jede Leitplanke sass genau an dem Pfad, an dem der
Fehler damals auffiel:

  L1  Die Inhaltsart-Kennzeichnung (damals `_markiere_abenteuer`, seit dem 31.07.2026
      `_markiere_inhaltsart`) lief in nachschlagen.py an JEDER Ausgabeliste, in charakter.py
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
from app import glossar
from app.tools import charakter as ch
from app.tools import nachschlagen as ns
from tests.hilfen import SCHEMA

_SCHEMA = SCHEMA
@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    """Drei Quellen: Regelwerk, Abenteuer-/Setting-Band und ein englisches Druck-PHB.
    Die Klassen decken die VIER Schreibweisen ab, in denen Quellen eine Unterklasse
    ihrer Klasse zuordnen: deutscher Namenspraefix, '*Subclass of:*' im Body,
    Klammer-Suffix am Namen, Klasse im Kontext-Pfad ('Warlock > Warlock Subclasses')."""
    pfad = tmp_path / "foliant-charakterlisten.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet,"
        "inhaltsart) VALUES (?,?,?,?,?,?,?,?)",
        [("srd-de", "SRD 5.2.1 (Deutsch)", "de", "2024", "pdf", "CC-BY-4.0", 10,
          "regelwerk"),
         ("efota-en", "Eberron: Forge of the Artificer (Druck)", "en", "2024", "pdf",
          "privat", 40, "abenteuer_setting"),
         ("ddb-phb-2024-en", "Player's Handbook", "en", "2024", "ddb", "privat", 30,
          "regelwerk")])
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [# Umlaut-Sortierung (DIN 5007-1: ae = a): 'Kaempfer' gehoert VOR 'Kleriker'.
         # Bewusst in dieser Reihenfolge eingefuegt, damit nur die Sortierung sie dreht.
         (1, "klasse", "Kleriker", "Cleric", "de", "2024", "60",
          "*Kontext: Klassen*\n\nGoettliche Magie."),
         (1, "klasse", "Kämpfer", "Fighter", "de", "2024", "55",
          "*Kontext: Klassen*\n\nWaffenmeister."),
         # --- Regelwerk: Klasse + Unterklasse im deutschen Namensschema
         # Wie im echten Bestand: der Klassen-Steckbrief beginnt mit der
         # Merkmalstabelle (keine Schlagzeile), die Unterklasse mit ihrer Schlagzeile.
         (1, "klasse", "Magier", "Wizard", "de", "2024", "88",
          "*Kontext: Klassen*\n\n###### **Hauptmerkmale des Magiers** \n\n"
          "|**Hauptattribut**|Intelligenz|\n|---|---|\n"
          "|**Trefferpunktewürfel**|1W6 pro Magierstufe|"),
         (1, "klasse", "Magier-Unterklasse: Hervorrufer", None, "de", "2024", "92",
          "*Kontext: Klassen > Magier*\n\n_Meister der rohen Energie_ \n\nDu formst "
          "rohe Energie zu maechtigen Zaubern."),
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
          "*Kontext: Beschreibungen der Spezies*\n\nZwerge sind ein zaehes Volk "
          "aus den Bergen."),
         # --- DDB-PHB-2024: die Klasse steht NUR im Kontext-Pfad (vierte Schreibweise).
         # 'Wizard' hat im Bestand eine deutsche Klassen-Zeile (Magier) - die Zuordnung
         # muss ueber die Namensvarianten der Gruppe laufen, nicht ueber die Quelle.
         (3, "klasse", None, "Illusionist", "en", "2024", None,
          "*Kontext: Wizard > Wizard Subclasses*\n\nYou master illusions."),
         # Unterabschnitt im SELBEN Kontext wie eine echte Unterklasse (flaches
         # Chunking): fuehrt deren Namen fort und darf NICHT als Unterklasse erscheinen.
         (3, "klasse", None, "Illusionist Spells", "en", "2024", None,
          "*Kontext: Wizard > Wizard Subclasses*\n\nAlways prepared: minor illusion."),
         # Klasse mit Artikel im Kontext-Pfad ('THE ARTIFICER') und ohne Grundeintrag
         # im Bestand: bleibt eine ehrliche Waise.
         (3, "klasse", None, "Cartographer", "en", "2024", None,
          "*Kontext: The Artificer > Artificer Subclasses*\n\nYou map the unknown."),
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


def test_jede_option_traegt_belegzeile_und_kurzcharakteristik(bestand):
    """Simulationslauf 01.08.2026: Das Modell charakterisierte Klassen aus dem
    Gedaechtnis ("kaempft mit Ki-Energie") und baute die Belegzeile selbst zusammen -
    beides, weil die Liste weder 'kurz' noch 'zitat' trug. Die Liste liefert es jetzt,
    damit Raten gar nicht erst noetig ist (B1)."""
    magier = next(k for k in ch.foliant_liste_optionen("klasse")["klassen"]
                  if k["name_de"] == "Magier")
    assert magier["zitat"] == "Quelle: SRD 5.2.1 (Deutsch) · S. 88 · Regelversion: 2024"
    # Klassen-Steckbriefe fuehren keine Schlagzeile, aber die Merkmalstabelle - und das
    # Hauptattribut ist fuer die Klassenwahl ohnehin die nuetzlichere Angabe.
    assert magier["kurz"] == "Hauptattribut: Intelligenz"
    hervorrufer = next(u for u in magier["unterklassen"] if u["name_de"] == "Hervorrufer")
    assert hervorrufer["kurz"] == "Meister der rohen Energie"   # Schlagzeile der Quelle
    zwerg = ch.foliant_liste_optionen("spezies")["spezies"][0]
    assert zwerg["kurz"] == "Zwerge sind ein zaehes Volk aus den Bergen."


def test_kurzzeile_nimmt_keinen_kuenstlernamen(bestand):
    """Die Druckquellen streuen Kuenstlernamen als eigene Zeile in den Text ('ERION
    MAKUO'). Zweiwortzeilen scheiden deshalb aus - sonst stuende so ein Name als
    Charakteristik der Unterklasse in der Liste."""
    # Drei Woerter reichen fuer einen Namen mit Initial ("Helge C. Balzer") - deshalb
    # vier; und der Rueckfall nimmt nur ganze Saetze, keine Datenzeilen.
    assert ch._kurzzeile("*Kontext: SUBCLASSES*\n\nHelge C. Balzer\n\nGroesse: "
                         "Mittelgross\n\nEin ganzer Satz ueber diese Unterklasse.") \
        == "Ein ganzer Satz ueber diese Unterklasse."
    assert ch._kurzzeile("*Kontext: X*\n\nARTIST: KEVIN GNUTZMANS Ability Scores: "
                         "Strength") is None


def test_kurzzeile_doppelt_die_talent_typzeile_nicht(bestand):
    """Die Typzeile ('General Feat (Prerequisite: ...)') steht bereits als eigene Felder
    in der Zeile. Als Kurzcharakteristik verdraengte sie den Satz, der wirklich sagt,
    was das Talent tut - und schleppte dabei die Markdown-Escapes der Druckquelle mit
    ('Level 4\\+')."""
    assert ch._kurzzeile("*Kontext: General Feats*\n\nGeneral Feat (Prerequisite: "
                         "Level 4\\+)\n\nDu bemerkst Gefahren fruehzeitig und handelst "
                         "zuerst.") == "Du bemerkst Gefahren fruehzeitig und handelst zuerst."
    # Escapes werden auch dort entfernt, wo die Zeile selbst durchkommt.
    assert "\\" not in (ch._kurzzeile("*Kontext: X*\n\nAasimar \\(AH\\-sih\\-mar\\) sind "
                                      "Sterbliche mit einem Funken der Oberen Ebenen.") or "")
    assert ch._kurzzeile("*Kontext: X*") is None               # nichts da -> kein Feld


def test_unterklasse_aus_kontextpfad_haengt_an_ihrer_klasse(bestand):
    """Vierte Schreibweise (Befund 01.08.2026): Im DDB-PHB-2024 steht die Klasse NUR im
    Kontext-Pfad ('Wizard > Wizard Subclasses') - kein Namenspraefix, kein Body-Marker,
    kein Klammer-Suffix. Vorher waren damit alle 48 PHB-Unterklassen Waisen mit dem
    falschen Hinweis 'Klasse nicht im Bestand', und der Discord-Bot hat der Runde genau
    das erzaehlt - obwohl der Magier direkt daneben in der Liste stand."""
    klassen = ch.foliant_liste_optionen("klasse")["klassen"]
    magier = next(k for k in klassen if k["name_de"] == "Magier")
    namen = {u["name_de"] or u["name_en"] for u in magier["unterklassen"]}
    assert "Illusionist" in namen, f"PHB-Unterklasse nicht zugeordnet: {namen}"
    oben = {k["name_de"] or k["name_en"] for k in klassen}
    assert "Illusionist" not in oben, "haengt zugeordnet UND als Waise in der Liste"


def test_zauberlisten_abschnitt_ist_keine_unterklasse(bestand):
    """'Illusionist Spells' liegt durch das flache Chunking im SELBEN Kontext wie die
    Unterklasse selbst und ist von ihr nur am Namen zu unterscheiden: er fuehrt den
    Namen der Geschwister-Unterklasse fort. In der Liste stand die Zauberliste sonst
    als eigene Unterklasse neben ihrem Original ('Oath of the Ancients Spells')."""
    klassen = ch.foliant_liste_optionen("klasse")["klassen"]
    alle = {k["name_de"] or k["name_en"] for k in klassen} | {
        u["name_de"] or u["name_en"]
        for k in klassen for u in k.get("unterklassen") or []}
    assert "Illusionist Spells" not in alle


def test_waisen_hinweis_ist_handlungsanweisung(bestand):
    """Der Hinweis einer echten Waise muss dem Modell sagen, was es TUN soll (Option
    anbieten), nicht wie die Datenlage aussieht. Aus 'Zugehoerige Klasse nicht im
    Bestand.' hat der Bot 'kann keinen Steckbrief liefern' gemacht - dabei ist die
    Unterklasse selbst vollstaendig abrufbar."""
    r = ch.foliant_liste_optionen("klasse")
    waisen = [k for k in r["klassen"] if k.get("hinweis")]
    assert waisen, "Waisen-Fall nicht erzeugt - Fixture pruefen"
    for w in waisen:
        assert "Waehlbare Unterklasse" in w["hinweis"]
        assert "Option anbieten" in w["hinweis"]


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


def test_optionslisten_sind_deutsch_alphabetisch_sortiert(bestand):
    """DIN 5007-1: 'ä' zaehlt beim Sortieren als 'a'.

    Bis zum 31.07.2026 sortierten die Optionslisten mit einem reinen `.lower()`. In der
    Codepoint-Ordnung steht 'ä' (U+00E4) hinter 'z', also stand "Kämpfer" in der
    Klassenliste HINTER "Kleriker" - fuer eine Liste, die ein Spieler liest, schlicht
    falsch. Gemessen wurde vorher, dass die Faltung genau diese eine Ausgabe aendert;
    an den Attributsnamen darf sie NICHT angewandt werden (s. charakter._norm)."""
    namen = [z["name_de"] or z["name_en"]
             for z in ch.foliant_liste_optionen("klasse")["klassen"]]
    gefaltet = [glossar.norm_begriff(n) for n in namen]
    assert gefaltet == sorted(gefaltet), (
        f"Klassenliste nicht deutsch-alphabetisch: {namen}")
    if "Kämpfer" in namen and "Kleriker" in namen:
        assert namen.index("Kämpfer") < namen.index("Kleriker"), \
            "'Kämpfer' muss vor 'Kleriker' stehen (ä = a)"
