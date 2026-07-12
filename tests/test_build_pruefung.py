"""Regressionstests A4 (Charakterlisten/Build strikt 2024) + A5 (Eingaben, Vollstaendigkeit,
ehrliche Ergebnisse) aus dem Korrekturauftrag. Synthetische Fixture, offline.

Wichtige Konstellationen:
- 'Hexer' existiert NUR als 2014-Klasse -> nie in 2024-Listen, nie 'ok' im Build.
- 'Kämpfer' existiert 2024 (de) UND 2014 (de) -> Listen-Quellen bleiben editionsrein.
- Unterklasse 'Champion' existiert NUR englisch (Open5e, 'Subclass of: Fighter') ->
  Zuordnung zur deutsch gewaehlten Klasse laeuft ueber die exakte Glossar-Bruecke.
- Die Attributs- und Hintergrund-Regelbelege liegen ALS BESTANDSEINTRAEGE vor (A5:
  Belege kommen aus der DB, nicht aus hartcodierten Quellenzeilen)."""
import sqlite3
from pathlib import Path

import pytest

from app.tools import charakter as ch

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

_ATTRIBUTSREGEL = ("*Kontext: Charaktererstellung > Deinen Charakter erstellen*\n\n"
                   "**_Standardsatz:_** Verwende die folgenden sechs Werte für deine "
                   "Attribute: 15, 14, 13, 12, 10, 8.\n\n**_Punktkosten:_** Du hast 27 "
                   "Punkte. Beispiel: Ein Wert von 14 kostet 7 deiner 27 Punkte.")
_HG_REGEL = ("*Kontext: Charakterherkunft > Charakterhintergründe > Elemente eines "
             "Hintergrunds*\n\nIn einem Hintergrund sind drei der Attributswerte deines "
             "Charakters aufgeführt. Erhöhe einen davon um 2 und einen anderen um 1, oder "
             "alle drei um 1. Keine dieser Erhöhungen kann zu einem Wert von mehr als 20 "
             "führen.")
_MERKMALE = ("*Kontext: Klassen > Kämpfer*\n\nAls Kämpfer erhältst du folgende Merkmale.\n\n"
             "|**Stufe**|**Klassenmerkmale**|**Waffenbe-**<br>**herrschung**|\n|---|---|---|\n"
             "|1|Kampfstil, Waffenbeherrschung|3|\n|2|Taktisches Verständnis|3|\n"
             "|3|Kämpfer­Unterklasse|3|\n|4|Attributswerterhöhung|4|")


@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    pfad = tmp_path / "foliant-build.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
        "VALUES (?,?,?,?,?,?,?)",
        [("srd-de", "SRD 5.2.1 (Deutsch)", "de", "2024", "pdf", "CC-BY-4.0", 10),
         ("open5e-srd-2024", "SRD 5.2 (Open5e)", "en", "2024", "open5e", "CC-BY-4.0", 60),
         ("phb-2014-de", "Spielerhandbuch (2014)", "de", "2014", "pdf", "privat", 40)])
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [(1, "klasse", "Kämpfer", None, "de", "2024", "55",
          "*Kontext: Klassen*\n\nHauptmerkmale des Kämpfers."),
         (1, "klasse", "Klassenmerkmale des Kämpfers", None, "de", "2024", "55", _MERKMALE),
         # Unterklasse NUR englisch (A4: Glossar-Bruecke Fighter<->Kämpfer noetig):
         (2, "klasse", None, "Champion", "en", "2024", None,
          "*Subclass of: Fighter*\n\nPursue physical excellence."),
         # Klasse NUR 2014 (darf nirgends als 2024 auftauchen):
         (3, "klasse", "Hexer", "Hexblade", "de", "2014", "70",
          "*Kontext: Klassen*\n\nAlte 2014-Klasse."),
         # Kämpfer AUCH als 2014-Fassung (Editions-Reinheit der Listen-Quellen):
         (3, "klasse", "Kämpfer", "Fighter", "de", "2014", "72",
          "*Kontext: Klassen*\n\nAlter 2014-Kämpfer."),
         (1, "hintergrund", "Soldat", None, "de", "2024", "93",
          "*Kontext: Charakterherkunft > Charakterhintergründe > Beschreibungen der "
          "Hintergründe*\n\n**Attributswerte:** Stärke, Geschicklichkeit, Konstitution "
          "**Talent:** Wilder Angreifer (siehe \n\n„Talente“)"),
         (1, "spezies", "Mensch", None, "de", "2024", "96",
          "*Kontext: Charakterherkunft > Charakterspezies > Beschreibungen der Spezies*"
          "\n\n**Kreaturentyp:** Humanoide\n\nEinfallsreich."),
         (1, "talent", "Wilder Angreifer", None, "de", "2024", "98",
          "*Kontext: Talente > Beschreibungen der Talente > Herkunftstalente*\n\n"
          "_Herkunftstalent_ \n\nWürfle den Waffenschaden neu."),
         # Epische Gabe mit Stufen-Voraussetzung in der Typzeile (SYN-P0-005):
         (1, "talent", "Gabe des Schicksals", None, "de", "2024", "99",
          "*Kontext: Talente > Beschreibungen der Talente > Epische-Gabe-Talente*\n\n"
          "_Epische-Gabe-Talent (Voraussetzung: min. 19. Stufe)_ \n\n"
          "Du kannst das Schicksal beeinflussen."),
         # Regel-Belege im Bestand (A5: Datenbankbeleg statt hartcodierter Zeile):
         (1, "regel", "Schritt 3: Attributswerte", None, "de", "2024", "9", _ATTRIBUTSREGEL),
         (1, "hintergrund", "Attributswerte", None, "de", "2024", "93", _HG_REGEL)])
    con.executemany(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle,seite) "
        "VALUES (?,?,?,?,?,?)",
        [("Fighter", "Kämpfer", 1, "Ulisses-Glossar (dnddeutsch.de)", "2024", None)])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    from app import db as adb
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


_WERTE = {"stärke": 15, "geschicklichkeit": 13, "konstitution": 14,
          "intelligenz": 10, "weisheit": 12, "charisma": 8}


def _befunde(r):
    return {p["pruefung"]: p for p in r["pruefungen"]}


def test_a4_2014_klasse_nicht_in_listen_und_nicht_ok(bestand):
    """Nur-2014-Klasse erscheint nicht in 2024-Listen und wird im Build nie 'ok'."""
    k = ch.foliant_liste_klassen()
    namen = {z["name_de"] or z["name_en"] for z in k["klassen"]}
    assert "Hexer" not in namen and "Kämpfer" in namen
    r = ch.foliant_pruefe_build(klasse="Hexer", stufe=3)
    b = _befunde(r)
    assert b["klasse"]["status"] == "nicht_pruefbar"
    assert "2014" in b["klasse"]["detail"]           # ehrlich: nur als Altstand vorhanden
    assert r["ergebnis"] != "legal_soweit_pruefbar"


def test_a4_listen_quellen_editionsrein(bestand):
    """2014- und 2024-Kämpfer werden nicht editionsuebergreifend gruppiert."""
    k = ch.foliant_liste_klassen()
    kaempfer = next(z for z in k["klassen"] if z["name_de"] == "Kämpfer")
    assert all("2014" not in q for q in kaempfer["quellen"]), kaempfer["quellen"]
    assert kaempfer["edition"] == "2024"


def test_a4_englische_unterklasse_zu_deutscher_klasse(bestand):
    """EN-Unterklasse ('Subclass of: Fighter') passt zur deutsch gewaehlten Klasse
    'Kämpfer' ueber die exakte Glossarentsprechung."""
    r = ch.foliant_pruefe_build(klasse="Kämpfer", stufe=3, unterklasse="Champion",
                                hintergrund="Soldat", spezies="Mensch",
                                attributswerte=dict(_WERTE),
                                attributsmethode="standard_array",
                                hintergrund_erhoehungen={"stärke": 2, "konstitution": 1})
    b = _befunde(r)
    assert b["unterklasse"]["status"] == "ok", b["unterklasse"]
    assert b["unterklasse_stufe"]["status"] == "ok"
    assert r["ergebnis"] == "legal_soweit_pruefbar"
    # Die Klassen-Liste haengt die EN-Unterklasse ebenfalls an die deutsche Klasse:
    k = ch.foliant_liste_klassen()
    kaempfer = next(z for z in k["klassen"] if z["name_de"] == "Kämpfer")
    assert [u["name_en"] for u in kaempfer["unterklassen"]] == ["Champion"]


def test_a5_ungueltige_attributswerte_strukturiert(bestand):
    """'hoch', 15.9, True und Alias-Konflikte: strukturierte Befunde, keine Exception,
    keine stille Konvertierung."""
    for kaputt in ({"stärke": "hoch"}, {"stärke": 15.9}, {"stärke": True},
                   {"str": 15, "stärke": 14}):
        r = ch.foliant_pruefe_build(klasse="Kämpfer", stufe=1,
                                    attributswerte=kaputt,
                                    attributsmethode="standard_array")
        b = _befunde(r)
        assert b["attributswerte"]["status"] == "nicht_pruefbar", (kaputt, b["attributswerte"])
        assert r["ergebnis"] != "legal_soweit_pruefbar"


def test_a5_obergrenze_nur_mit_basiswerten(bestand):
    """Hintergrundserhoehung ohne Basiswerte bestaetigt die Obergrenze 20 NICHT."""
    r = ch.foliant_pruefe_build(klasse="Kämpfer", stufe=1, hintergrund="Soldat",
                                hintergrund_erhoehungen={"stärke": 2, "konstitution": 1})
    b = _befunde(r)
    assert b["hintergrund_erhoehungen"]["status"] == "ok"          # Verteilung pruefbar
    assert b["hintergrund_erhoehungen_obergrenze"]["status"] == "nicht_pruefbar"
    assert "Basiswert" in b["hintergrund_erhoehungen_obergrenze"]["detail"]


def test_a5_leere_oder_unbekannte_klasse_kein_legal(bestand):
    """Leerer/unbekannter Klassenname ergibt kein Legalitaetspraedikat."""
    for klasse in ("", "   ", "Chronomant"):
        r = ch.foliant_pruefe_build(klasse=klasse, stufe=1)
        assert r["ergebnis"] != "legal_soweit_pruefbar", klasse
        assert "klasse" in [f.split(" ")[0] for f in r["fehlende_angaben"]] \
            or any("klasse" in f for f in r["fehlende_angaben"])


def test_a5_unvollstaendiger_build_kein_legalitaetsnachweis(bestand):
    """Fehlende Pflichtangaben (Hintergrund/Spezies/Attribute) -> 'unvollstaendig'
    plus ausdrueckliche fehlende_angaben-Liste."""
    r = ch.foliant_pruefe_build(klasse="Kämpfer", stufe=3)
    assert r["ergebnis"] == "unvollstaendig"
    fehlt = " ".join(r["fehlende_angaben"])
    for angabe in ("hintergrund", "spezies", "attributswerte"):
        assert angabe in fehlt, (angabe, fehlt)


def test_a5_doppelte_waffenmeisterschaften(bestand):
    """Doppelte Waffenmeisterschaften zaehlen nicht als mehrere gueltige Auswahlen."""
    r = ch.foliant_pruefe_build(klasse="Kämpfer", stufe=1,
                                waffenmeisterschaften=["Speer", "Speer", "Langschwert"])
    b = _befunde(r)
    assert b["waffenbeherrschung"]["status"] == "verstoss"
    assert "doppelt" in b["waffenbeherrschung"]["detail"].lower()


def test_a5_bestandsbeleg_statt_hartcodierter_quelle(bestand, tmp_path, monkeypatch):
    """foliant_hol_attributswerte belegt aus der DB; ohne importierte Attributsregel
    gibt es KEINEN erfundenen Bestandsbeleg (B1)."""
    a = ch.foliant_hol_attributswerte("standard_array")
    assert a["werte"] == [15, 14, 13, 12, 10, 8]
    assert "S. 9" in a["beleg"] and "SRD 5.2.1" in a["beleg"]      # echter DB-Beleg

    # Leere DB (nur Schema): keine Regelquelle -> kein Beleg, keine Werte aus
    # Allgemeinwissen; ehrliches nicht_pruefbar.
    leer = tmp_path / "leer.sqlite"
    con = sqlite3.connect(leer)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.commit(); con.close()
    from app import db as adb
    monkeypatch.setattr(adb, "standard_pfad", lambda: leer)
    a2 = ch.foliant_hol_attributswerte("standard_array")
    assert "werte" not in a2 and a2.get("verfuegbar") is False
    assert "beleg" not in a2
    r = ch.foliant_pruefe_build(klasse="Kämpfer", stufe=1,
                                attributswerte=dict(_WERTE),
                                attributsmethode="standard_array")
    assert _befunde(r)["attributswerte"]["status"] == "nicht_pruefbar"


_VOLL = dict(klasse="Kämpfer", hintergrund="Soldat", spezies="Mensch",
             attributswerte=dict(_WERTE), attributsmethode="standard_array")


def test_p0_fehlende_pflichtwahlen_kein_positivurteil(bestand):
    """SYN-P0-005 (Synthese 2026-07-12, Faelle 1+2 verifiziert): fehlende
    Hintergrund-Erhoehungen und fehlende Unterklasse ab der Tabellen-Stufe sind
    PFLICHTWAHLEN - vorher galten beide Builds als 'legal_soweit_pruefbar'."""
    r1 = ch.foliant_pruefe_build(stufe=1, **_VOLL)               # ohne Erhoehungen
    assert r1["ergebnis"] == "unvollstaendig"
    assert any("hintergrund_erhoehungen" in f for f in r1["fehlende_angaben"])

    r2 = ch.foliant_pruefe_build(stufe=3, **_VOLL,               # Stufe 3 ohne Unterklasse
                                 hintergrund_erhoehungen={"stärke": 2, "konstitution": 1})
    assert r2["ergebnis"] == "unvollstaendig"
    assert any("unterklasse" in f for f in r2["fehlende_angaben"])
    assert _befunde(r2)["unterklasse"]["status"] == "nicht_pruefbar"


def test_p0_talent_stufenvoraussetzung_wird_geprueft(bestand):
    """SYN-P0-005 Fall 3: epische Gabe auf Stufe 1 ist ein VERSTOSS (Typzeile
    'min. 19. Stufe'), kein 'ok wegen Existenz'."""
    r = ch.foliant_pruefe_build(stufe=1, **_VOLL,
                                hintergrund_erhoehungen={"stärke": 2, "konstitution": 1},
                                talente=["Gabe des Schicksals"])
    b = _befunde(r)
    assert b["talent:Gabe des Schicksals"]["status"] == "verstoss"
    assert "19" in b["talent:Gabe des Schicksals"]["detail"]
    assert r["ergebnis"] == "verstoesse_gefunden"
    # Talent OHNE Voraussetzung bleibt 'ok' (Erwerbsquelle offen deklariert):
    r_ok = ch.foliant_pruefe_build(stufe=1, **_VOLL,
                                   hintergrund_erhoehungen={"stärke": 2, "konstitution": 1},
                                   talente=["Wilder Angreifer"])
    assert _befunde(r_ok)["talent:Wilder Angreifer"]["status"] == "ok"


def test_p0_fantasiewaffen_kein_positivurteil(bestand):
    """SYN-P0-005 Fall 4: erfundene Waffennamen ('Kartoffel') zaehlen nicht als gueltige
    Waffenbeherrschung - Ergebnis hoechstens 'keine_verstoesse_gefunden', nie das
    positive Label."""
    r = ch.foliant_pruefe_build(stufe=1, **_VOLL,
                                hintergrund_erhoehungen={"stärke": 2, "konstitution": 1},
                                waffenmeisterschaften=["Kartoffel", "Teekanne", "Mondstrahl"])
    b = _befunde(r)
    assert b["waffenbeherrschung"]["status"] == "nicht_pruefbar"
    assert "Kartoffel" in b["waffenbeherrschung"]["detail"]
    assert r["ergebnis"] == "keine_verstoesse_gefunden"
    assert "waffenbeherrschung" in r["nicht_pruefbar"]


def test_ist_option_letztes_kontext_segment():
    """QS-Folgeaufgabe 11.07.2026 (Aasimar-Luecke): eine Option steht DIREKT unter einem
    Kapitel-/Gruppen-Header; nistet ein Eintrag unter einem konkreten Optionsnamen, ist er
    ein Unterabschnitt. So erscheinen DDB-Optionen (Aasimar/Alert/Haunted One) konsistent
    zur Build-Pruefung in den Listen, ohne Merkmals-/Abstammungs-Fragmente - und srd-de/
    Open5e bleiben unveraendert."""
    def e(kontext):
        return {"body_md": (f"*Kontext: {kontext}*\n\nText." if kontext else "Text.")}
    # Spezies: DDB-Option vs. Unterabschnitt (Traits/Abstammung)
    assert ch._ist_option(e("Species Descriptions"), "spezies")               # Aasimar
    assert not ch._ist_option(e("Species Descriptions > Aasimar"), "spezies")  # Aasimar Traits
    assert not ch._ist_option(e("Species Descriptions > Elf"), "spezies")      # Drow/High Elves
    assert ch._ist_option(e("Species"), "spezies")                             # Ravenloft: Dhampir
    # srd-de weiterhin korrekt; Struktur-Abschnitt bleibt draussen
    assert ch._ist_option(
        e("Charakterherkunft > Charakterspezies > Beschreibungen der Spezies"), "spezies")
    assert not ch._ist_option(
        e("Charakterherkunft > Charakterspezies > Elemente einer Spezies"), "spezies")
    assert ch._ist_option(e(""), "spezies")                                    # Open5e: kein Kontext
    # Hintergrund
    assert ch._ist_option(e("Backgrounds"), "hintergrund")                     # Ravenloft
    assert ch._ist_option(e("Beschreibungen der Hintergründe"), "hintergrund")  # srd-de
    assert not ch._ist_option(e("Charakterhintergründe > Elemente eines Hintergrunds"),
                              "hintergrund")
    # Talent: DDB-Feat unter Gruppen-Header = Option; Meta/Unter-Feature nicht
    assert ch._ist_option(e("Feats > Origin Feats"), "talent")                 # Alert
    assert ch._ist_option(e("Beschreibungen der Talente > Herkunftstalente"), "talent")  # srd-de
    assert not ch._ist_option(e("Feat Descriptions"), "talent")                # 'Parts of a Feat'
    assert not ch._ist_option(e("Origin Feats > Crafter"), "talent")           # 'Fast Crafting'


def test_hol_spezies_fuehrt_ddb_unterabschnitte_zusammen(tmp_path, monkeypatch):
    """Fachliche Vollständigkeit: DDB zerlegt eine Spezies in Intro + '<Name> Traits' (die
    eigentlichen Werte). foliant_hol_spezies führt DIREKTE Unterabschnitte in den Regeltext
    zusammen - quellen-/editionsrein und NUR direkte Kinder (kein Einsaugen fremder Abschnitte)."""
    pfad = tmp_path / "foliant-agg.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet)"
                " VALUES ('ddb-phb-2024-en','Player’s Handbook (D&D Beyond)','en','2024',"
                "'ddb','privat',40)")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (1,'spezies',NULL,?,'en','2024',NULL,?)",
        [("Aasimar", "*Kontext: Species Descriptions*\n\nAasimar carry a celestial spark."),
         ("Aasimar Traits", "*Kontext: Species Descriptions > Aasimar*\n\n**Creature Type:** "
          "Humanoid\n\n**Celestial Resistance.** You have Resistance to Necrotic damage."),
         # fremder Unterabschnitt einer ANDEREN Spezies darf NICHT einfliessen:
         ("Dwarf Traits", "*Kontext: Species Descriptions > Dwarf*\n\n**Darkvision.** 120 feet.")])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit(); con.close()
    from app import db as adb
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    d = ch.foliant_hol_spezies("Aasimar")
    assert d["gefunden"]
    assert "Aasimar carry" in d["regeltext_md"]              # Intro
    assert "Celestial Resistance" in d["regeltext_md"]       # Werte aus 'Aasimar Traits'
    assert "Darkvision" not in d["regeltext_md"]             # fremdes Kind NICHT eingesogen
    assert d.get("hinweis_zusammengefuehrt")


def test_c2_pointbuy_beleg_umfang_und_widerspruch(bestand, tmp_path, monkeypatch):
    """SYN-P2-003 C2-Abnahme: der Point-Buy-Beleg unterscheidet 'Tabelle verifiziert' von
    'nur Budget belegt'; eine Quelle, deren Kostentabelle den Konstanten WIDERSPRICHT,
    gibt keine Werte mit Vollbeleg aus (der Bestand ist die einzige Wahrheit, B1/A5)."""
    # Fixture-Beleg trägt '27 Punkte', aber KEINE parsebare Kostentabelle -> beleg_umfang
    # deklariert offen, dass die Tabelle aus der Konstante stammt.
    a = ch.foliant_hol_attributswerte("point_buy")
    assert a["budget"] == 27 and "Kostentabelle nicht maschinell lesbar" in a["beleg_umfang"]

    # Quelle mit WIDERSPRÜCHLICHER Kostentabelle -> keine Werte, ehrlicher Hinweis.
    import sqlite3
    widerspruch = tmp_path / "wid.sqlite"
    c = sqlite3.connect(widerspruch); c.executescript(_SCHEMA.read_text(encoding="utf-8"))
    c.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
              "VALUES ('srd-de','SRD','de','2024','pdf',10)")
    c.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,seite,body_md) "
              "VALUES (1,'regel','Schritt 3: Attributswerte','de','2024','9',?)",
              ("*Kontext: X*\n\n**_Punktkosten:_** Du hast 27 Punkte.\n\n"
               "|**Wert**|**Kosten**|\n|---|---|\n|8|5|\n|9|6|\n|10|7|\n|11|8|"
               "\n|12|9|\n|13|10|\n|14|12|\n|15|14|",))   # falsche Kosten!
    c.commit(); c.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    c.commit(); c.close()
    from app import db as adb
    monkeypatch.setattr(adb, "standard_pfad", lambda: widerspruch)
    a2 = ch.foliant_hol_attributswerte("point_buy")
    assert a2.get("verfuegbar") is False and "weicht" in a2["hinweis"]


def test_c4_fuehrungstext_nennt_pflichtwahlen(bestand):
    """SYN-P2-005 C4-Abnahme: die Charakterbau-Führung nennt die 2024-Pflichtwahlen
    Sprachen und Spezies-Optionen (nicht nur Klasse→Hintergrund→Spezies)."""
    for antwort in (ch.foliant_liste_klassen(), ch.foliant_liste_spezies(),
                    ch.foliant_liste_hintergruende()):
        hinweis = antwort.get("hinweis_reihenfolge", "")
        assert "SPRACHEN" in hinweis.upper() or "Sprachen" in hinweis
