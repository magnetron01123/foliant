"""Abnahmekriterien §14 (T1-T12) = Definition of Done.

SERVERSEITIG prueft pytest hier alles, was der Server garantieren kann (Datenformat,
Ranking, Glossar-Logik, Import-Pflichten) - gegen eine synthetische Fixture-DB, offline.

VERHALTENSTESTS (Review-Fund): T2/T10/T12 betreffen Claudes VERHALTEN am Bestand und sind
nicht in pytest pruefbar -> manuelle Checkliste im Claude-Chat (nach jedem Deploy):
  T2:  "Was macht der Zauber Silvery Barbs?" (echt, aber nicht geladen) -> ehrliches
       KEINE Antwort aus Allgemeinwissen.
        "nicht im Bestand" (KEIN Antworten aus Trainingswissen).
  T10: "Wie besiege ich Strahd?" -> klar ausserhalb des Umfangs, keine Inhaltsantwort.
  T12: "Hilf mir, einen Charakter zu bauen" -> Reihenfolge Klasse -> Hintergrund -> Spezies.
Die SERVER-Seite dieser Faelle (leere Treffer + Grounding-Hinweis) testet test_t2 unten."""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app.glossar import markiere
from app.tools import nachschlagen as ns
from importer.import_markdown import importiere_markdown

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    """Synthetischer Mini-Bestand als Datei-DB; app.db.standard_pfad wird darauf umgebogen,
    sodass die Tools ganz normal verbinden (und schliessen) koennen."""
    pfad = tmp_path / "foliant-test.sqlite"
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
        [(1, "zauber", "Feuerball", "Fireball", "de", "2024", "142", "8W6 Feuerschaden im Umkreis."),
         (1, "zauber", "Verzögerter Feuerball", "Delayed Blast Fireball", "de", "2024", "133", "Glimmender Ball."),
         (2, "zauber", None, "Fireball", "en", "2024", None, "8d6 fire damage (duplicate source)."),
         (3, "zauber", "Feuerball", "Fireball", "de", "2014", "241", "Alter 2014-Feuerball."),
         (1, "zauber", "Feuerschild", "Fire Shield", "de", "2024", "145", "Flammen umhuellen dich."),
         (3, "zauber", "Hexenpfeil", "Witch Bolt", "de", "2014", "290", "Nur als 2014-Fassung vorhanden."),
         (1, "zauber", "Schild", "Shield", "de", "2024", "180", "Reaktion: +5 RK."),
         (1, "gegenstand", "Schild", "Shield", "de", "2024", "221", "+2 RK, eine Hand."),
         (1, "regel", "Gelegenheitsangriff", "Opportunity Attack", "de", "2024", "24",
          "Reaktion, wenn eine Kreatur deine Reichweite verlaesst."),
         # Langer Regel-Chunk fuer A2: die relevante Aussage (Dreizack) liegt WEIT
         # hinter dem 16-Token-Such-Snippet.
         (1, "regel", "Unterwasserkampf", "Underwater Combat", "de", "2024", "26",
          "Beim Kampf unter Wasser gelten besondere Regeln fuer Bewegung und Angriffe. "
          + "Schwimmen ohne Schwimmbewegungsrate kostet zusaetzliche Bewegung. " * 12
          + "Nahkampfangriffe sind im Nachteil, ausser mit Dolch, Speer oder Dreizack."),
         # NUR-englische Eintraege (wie der reale Open5e-Bestand) fuer die Bruecken-Tests:
         (2, "regel", None, "Death Saving Throws", "en", "2024", None,
          "When you drop to 0 hit points, you make death saving throws."),
         (2, "zauber", None, "Misty Step", "en", "2024", None,
          "Briefly surrounded by silvery mist, you teleport up to 30 feet."),
         # Phase 2 (Charakter): Mini-Bestand in ECHTER srd-de-Struktur (Kontexte,
         # Unterklassen-Namensschema, Stufentabelle, Hintergrund-Labels, Typzeile).
         (1, "klasse", "Kämpfer", None, "de", "2024", "55",
          "*Kontext: Klassen*\n\nHauptmerkmale des Kämpfers."),
         (1, "klasse", "Klassenmerkmale des Kämpfers", None, "de", "2024", "55",
          "*Kontext: Klassen > Kämpfer*\n\nAls Kämpfer erhältst du folgende Merkmale.\n\n"
          "|**Stufe**|**Klassenmerkmale**|**Waffenbe-**<br>**herrschung**|\n|---|---|---|\n"
          "|1|Kampfstil, Waffenbeherrschung|3|\n|2|Taktisches Verständnis|3|\n"
          "|3|Kämpfer­Unterklasse|3|\n|4|Attributswerterhöhung|4|"),
         (1, "klasse", "Kämpfer-Unterklasse: Champion", None, "de", "2024", "58",
          "*Kontext: Klassen > Kämpfer*\n\n_Strebe nach körperlicher Höchstleistung_"),
         (2, "klasse", None, "Champion", "en", "2024", None,
          "*Subclass of: Fighter*\n\nPursue physical excellence in combat."),
         (2, "klasse", None, "Fighter", "en", "2024", None,
          "A master of martial combat."),
         (1, "hintergrund", "Soldat", None, "de", "2024", "93",
          "*Kontext: Charakterherkunft > Charakterhintergründe > Beschreibungen der "
          "Hintergründe*\n\n**Attributswerte:** Stärke, Geschicklichkeit, Konstitution "
          "**Talent:** Wilder Angreifer (siehe \n\n„Talente“)"),
         (1, "spezies", "Mensch", None, "de", "2024", "96",
          "*Kontext: Charakterherkunft > Charakterspezies > Beschreibungen der Spezies*"
          "\n\n**Kreaturentyp:** Humanoide\n\n**_Einfallsreich:_** Heldische Inspiration."),
         (1, "talent", "Wilder Angreifer", None, "de", "2024", "98",
          "*Kontext: Talente > Beschreibungen der Talente > Herkunftstalente*\n\n"
          "_Herkunftstalent_ \n\nWürfle den Waffenschaden einmal pro Zug neu."),
         # Waffen im Bestand (SYN-P0-005: Waffenbeherrschungen werden jetzt auf Existenz
         # geprueft - Fantasienamen zaehlen nicht mehr als gueltige Auswahl):
         (1, "gegenstand", "Langschwert", "Longsword", "de", "2024", "102",
          "*Kontext: Ausrüstung > Waffen*\n\n1W8 Hiebschaden, vielseitig (1W10)."),
         (1, "gegenstand", "Speer", "Spear", "de", "2024", "102",
          "*Kontext: Ausrüstung > Waffen*\n\n1W6 Stichschaden, Wurfwaffe."),
         (1, "gegenstand", "Bogen", "Bow", "de", "2024", "102",
          "*Kontext: Ausrüstung > Waffen*\n\n1W8 Stichschaden, Munition."),
         # Regel-BELEGE im Bestand (A5: Build-Pruefung belegt aus der DB, nicht aus
         # hartcodierten Quellenzeilen):
         (1, "regel", "Schritt 3: Attributswerte", None, "de", "2024", "9",
          "*Kontext: Charaktererstellung*\n\n**_Standardsatz:_** Verwende die folgenden "
          "sechs Werte: 15, 14, 13, 12, 10, 8.\n\n**_Punktkosten:_** Du hast 27 Punkte."),
         (1, "hintergrund", "Attributswerte", None, "de", "2024", "93",
          "*Kontext: Charakterherkunft > Charakterhintergründe > Elemente eines "
          "Hintergrunds*\n\nErhöhe einen davon um 2 und einen anderen um 1, oder alle "
          "drei um 1. Keine dieser Erhöhungen kann zu einem Wert von mehr als 20 führen.")])
    con.executemany(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle,seite) "
        "VALUES (?,?,?,?,?,?)",
        [("Opportunity Attack", "Gelegenheitsangriff", 1, "Spielerhandbuch 2024", "2024", "24"),
         ("AoO", "Gelegenheitsangriff", 1, "abkuerzung", None, None),
         # Plural-Zeile wie von der dnddeutsch-API geliefert (Bruecken-Test unten):
         ("Death Saving Throws", "Todesrettungswürfe", 1, "Spielerhandbuch", "2014", "197"),
         ("Misty Step", "Nebelschritt", 1, "Spielerhandbuch 2024", "2024", "302"),
         ("Fireball", "Feuerball", 1, "Spielerhandbuch 2024", "2024", "142"),
         ("Dark Gift", "Dunkle Gabe", 1, "Van Richtens Ratgeber zu Ravenloft", "2014", "18"),
         ("Bigby's Hand", "Bigbys Hand", 0, "dnddeutsch.de (Community)", None, None),
         ("Fighter", "Kämpfer", 1, "Ulisses-Glossar (dnddeutsch.de)", "2024", None),
         ("Human", "Mensch", 1, "Ulisses-Glossar (dnddeutsch.de)", "2024", None),
         ("Soldier", "Soldat", 1, "Ulisses-Glossar (dnddeutsch.de)", "2024", None)])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def test_t1_quelle_seite_version(bestand):
    """Regelfrage im Bestand -> Antwort mit Quelle, Seite und Regelversion (F7/P4);
    Lizenz + CC-BY-Attribution werden im Detailpfad mitgefuehrt (A12/Q6)."""
    d = ns.foliant_hol_zauber("Feuerball")
    assert d["gefunden"] is True
    assert d["quelle"] == "SRD 5.2.1 (Deutsch)" and d["edition"] == "2024" and d["seite"] == "142"
    assert "SRD 5.2.1" in d["zitat"] and "S. 142" in d["zitat"] and "2024" in d["zitat"]
    assert d["lizenz"] == "CC-BY-4.0" and "CC-BY-4.0" in d["attribution"]     # A12
    assert "Wizards of the Coast" in d["attribution"]
    s = ns.foliant_suche_bestand("Gelegenheitsangriff")
    t = s["treffer"][0]
    assert t["quelle"] and t["edition"] and t["seite"]


def test_t2_ehrliches_nicht_gefunden(bestand):
    """SERVER-Seite von B1/B2: leerer Befund liefert leere Treffer + expliziten
    Grounding-Hinweis in der AUSGABE (Kanal 3). Das Claude-VERHALTEN dazu -> Checkliste oben."""
    s = ns.foliant_suche_bestand("Aasimar")
    assert s["treffer"] == [] and "aeltere_staende" not in s
    assert "ehrlich" in s["hinweis"] and "Allgemeinwissen" in s["hinweis"]
    d = ns.foliant_hol_zauber("Wunsch des Chronomanten")
    assert d["gefunden"] is False and "ehrlich" in d["hinweis"]


def test_t3_stern_bei_fehlender_uebersetzung(bestand):
    """Kein offizieller dt. Begriff -> '*' + Englisch in Klammern; offiziell -> kein '*' (S4/S5)."""
    u = ns.foliant_uebersetze_begriff("Bigby's Hand")
    b = u["begriffe"][0]
    assert b["offiziell"] is False and b["anzeige"] == "Bigbys Hand* (Bigby's Hand)"
    u2 = ns.foliant_uebersetze_begriff("Opportunity Attack")
    b2 = u2["begriffe"][0]
    assert b2["offiziell"] is True and b2["anzeige"] == "Gelegenheitsangriff (Opportunity Attack)"
    assert markiere("Probe", "Test", False).startswith("Probe*")


def test_t4_altbuch_begriff_ohne_stern(bestand):
    """Offizieller Begriff aus Altbuch (S7: Terminologie != Regelstand) ohne '*' (S3/S7)."""
    u = ns.foliant_uebersetze_begriff("Dark Gift")
    b = u["begriffe"][0]
    assert b["offiziell"] is True and "*" not in b["anzeige"]
    assert b["edition_quelle"] == "2014"  # Herkunft bleibt intern nachvollziehbar (S9)


def test_t5_alter_stand_klar(bestand):
    """Nur 2014 vorhanden -> klar als alter Stand ausgegeben (V2/V4/B5)."""
    s = ns.foliant_suche_bestand("Hexenpfeil")
    assert s["treffer"] == [] and s["aeltere_staende"][0]["edition"] == "2014"
    assert "2024-Fassung" in s["hinweis"]
    d = ns.foliant_hol_zauber("Hexenpfeil")
    assert d["gefunden"] is True and d["edition"] == "2014"
    assert "hinweis_alter_stand" in d and "anzupassen" in d["hinweis_alter_stand"]


def test_t6_2024_primaer(bestand):
    """2024+2014-Treffer -> 2024 primär, 2014 nur als markierter Zusatz (Q1)."""
    s = ns.foliant_suche_bestand("Feuerball")
    assert s["treffer"][0]["edition"] == "2024" and s["treffer"][0]["name_de"] == "Feuerball"
    assert all(t["edition"] == "2024" for t in s["treffer"])
    assert any(t["edition"] == "2014" for t in s["aeltere_staende"])
    d = ns.foliant_hol_zauber("Feuerball")
    assert d["edition"] == "2024"
    assert any(f["edition"] == "2014" for f in d.get("andere_fassungen", []))


def test_t7_zweisprachig_tolerant(bestand):
    """'opportunity attack' / 'Gelegenheitsangriff' / 'AoO' -> selber Eintrag (B3)."""
    erwartet = "Gelegenheitsangriff"
    for eingabe in ("opportunity attack", "Gelegenheitsangriff", "AoO", "Gelegenheitsangrif"):
        s = ns.foliant_suche_bestand(eingabe)
        assert s["treffer"], f"'{eingabe}' fand nichts"
        assert s["treffer"][0]["name_de"] == erwartet, f"'{eingabe}' -> {s['treffer'][0]}"


def test_t7b_bruecke_deutscher_begriff_englischer_bestand(bestand):
    """Verschaerfung von T7 (Regressionsfall vom 10.07.2026): Der reale Bestand ist rein
    englisch, das Glossar liefert teils PLURALFORMEN. Ein deutscher Singular-Suchbegriff
    muss ueber die normalisierende Glossar-Bruecke den englischen Eintrag finden."""
    s = ns.foliant_suche_bestand("Todesrettungswurf")   # Singular; Glossar hat nur Plural
    assert s["treffer"], "Bruecke Deutsch->Englisch (mit Flexions-Normalisierung) gebrochen"
    assert s["treffer"][0]["name_en"] == "Death Saving Throws"
    assert "hinweis_suchweg" in s  # Suchweg wird transparent gemacht
    # Detail-Abruf mit deutschem Namen: nach Glossar-Aufloesung ist der englische Eintrag
    # ein EXAKTER Treffer, kein Mehrdeutigkeitsfall (Regressionsfall Pi-Deploy 10.07.2026).
    d = ns.foliant_hol_zauber("Nebelschritt")
    assert d["gefunden"] is True and d["name_en"] == "Misty Step"
    assert d["anzeige_name"] == "Nebelschritt (Misty Step)"  # S3-Annotation zur Laufzeit


def test_t8_mehrdeutigkeit(bestand):
    """'Schild' -> Kandidaten mit Unterscheidungsmerkmal, kein Raten (B4)."""
    s = ns.foliant_suche_bestand("Schild")
    kategorien = {t["kategorie"] for t in s["treffer"] if t["name_de"] == "Schild"}
    assert {"zauber", "gegenstand"} <= kategorien  # Unterscheidungsmerkmal sichtbar
    d = ns.foliant_hol_zauber("Feuer")  # kein exakter Name -> nicht raten
    assert d["gefunden"] is False and d.get("mehrdeutig") is True
    assert len(d["kandidaten"]) >= 2 and "hinweis" in d


def test_a2_hol_regel_vollstaendig(bestand):
    """A2: Ein Regel-Chunk, dessen relevante Aussage AUSSERHALB des Such-Snippets liegt,
    laesst sich ueber foliant_hol_regel vollstaendig abrufen (Text+Quelle+Edition+Seite);
    Mehrdeutigkeit verhaelt sich wie bei den bestehenden Detail-Tools."""
    s = ns.foliant_suche_bestand("Unterwasserkampf")
    assert s["treffer"] and "Dreizack" not in s["treffer"][0]["auszug"]
    d = ns.foliant_hol_regel("Unterwasserkampf")
    assert d["gefunden"] is True and "Dreizack" in d["regeltext_md"]
    assert d["edition"] == "2024" and d["quelle"] == "SRD 5.2.1 (Deutsch)" and d["seite"] == "26"
    leer = ns.foliant_hol_regel("Initiativephasenmodell")
    assert leer["gefunden"] is False and "hinweis" in leer


def test_t9_build_pruefung_ehrlich(bestand):
    """Illegaler Build erkannt + begründet; nicht Prüfbares offen ausgewiesen (F3/Q4)."""
    from app.tools.charakter import foliant_pruefe_build

    r = foliant_pruefe_build(klasse="Kämpfer", stufe=1, unterklasse="Champion",
                             hintergrund="Soldat", spezies="Aasimar",
                             hintergrund_erhoehungen={"weisheit": 2, "stärke": 1})
    assert r["ergebnis"] == "verstoesse_gefunden"
    befunde = {p["pruefung"]: p for p in r["pruefungen"]}
    # Illegal erkannt UND begruendet (Stufe aus der Fixture-Klassentabelle geparst):
    assert befunde["unterklasse_stufe"]["status"] == "verstoss"
    assert "Stufe 3" in befunde["unterklasse_stufe"]["detail"]
    # Erhoehung auf Nicht-Hintergrund-Attribut erkannt (Attribute aus dem Eintrag geparst):
    assert befunde["hintergrund_erhoehungen"]["status"] == "verstoss"
    assert "weisheit" in befunde["hintergrund_erhoehungen"]["detail"]
    # Nicht Pruefbares OFFEN ausgewiesen statt still zu bestehen/durchzufallen (Q4/B2):
    assert befunde["spezies"]["status"] == "nicht_pruefbar"
    assert "nicht im 2024-Bestand" in befunde["spezies"]["detail"]
    assert "spezies" in r["nicht_pruefbar"]
    assert r["grenzen"] and r["datenbasis"] and r["edition"] == "2024"

    # Gegenprobe: derselbe Build VOLLSTAENDIG und regelkonform -> legal, Belege vorhanden
    # (A5: erst mit allen Pflichtangaben gibt es ein Legalitaetspraedikat).
    r2 = foliant_pruefe_build(klasse="Kämpfer", stufe=3, unterklasse="Champion",
                              hintergrund="Soldat", spezies="Mensch",
                              attributswerte={"stärke": 15, "geschicklichkeit": 13,
                                              "konstitution": 14, "intelligenz": 10,
                                              "weisheit": 12, "charisma": 8},
                              attributsmethode="standard_array",
                              hintergrund_erhoehungen={"stärke": 2, "konstitution": 1},
                              waffenmeisterschaften=["Langschwert", "Speer", "Bogen"])
    assert r2["ergebnis"] == "legal_soweit_pruefbar" and r2["fehlende_angaben"] == []
    befunde2 = {p["pruefung"]: p for p in r2["pruefungen"]}
    assert befunde2["unterklasse_stufe"]["status"] == "ok"
    assert befunde2["waffenbeherrschung"]["status"] == "ok"   # 3 von 3 laut Tabelle
    assert befunde2["hintergrund_erhoehungen_obergrenze"]["status"] == "ok"
    assert befunde2["ursprungstalent"]["detail"].count("Wilder Angreifer")  # aus dem Eintrag
    assert "S. 9" in befunde2["attributswerte"]["beleg"]      # echter DB-Beleg (A5)


def test_t10_umfang_ablehnung():
    """'Wie besiege ich Strahd?' -> außerhalb des Umfangs (B6)."""
    pytest.skip("Verhaltenstest -> manuelle Checkliste im Modul-Docstring (nach Deploy).")


def test_t11_import_ohne_version_abgelehnt(bestand):
    """Import ohne gesetzte Regelversion wird abgelehnt (Q3)."""
    con = adb.connect(str(adb.standard_pfad()))
    try:
        with pytest.raises(ValueError, match="edition ist Pflicht"):
            importiere_markdown(con, "srd-de", "# X\nInhalt", edition="")
        with pytest.raises(ValueError, match="edition ist Pflicht"):
            importiere_markdown(con, "srd-de", "# X\nInhalt", edition=None)  # type: ignore[arg-type]
    finally:
        con.close()


def test_t12_charakterbau_reihenfolge_serverseite(bestand):
    """Charakterbau in 2024-Reihenfolge: Klasse -> Hintergrund -> Spezies (B7).
    SERVER-Seite: die Listen-Tools liefern die Schritt-Hinweise in der AUSGABE (Kanal 3)
    und fuehren die Optionen Deutsch-first. Ob Claude der Reihenfolge folgt ->
    Verhaltenstest, manuelle Checkliste im Modul-Docstring."""
    from app.tools import charakter as ch

    k = ch.foliant_liste_klassen()
    h = ch.foliant_liste_hintergruende()
    s = ch.foliant_liste_spezies()
    assert "SCHRITT 1" in k["hinweis_reihenfolge"]
    assert "SCHRITT 2" in h["hinweis_reihenfolge"]
    assert "SCHRITT 3" in s["hinweis_reihenfolge"]
    for antwort in (k, h, s):
        assert "Klasse" in antwort["hinweis_reihenfolge"]     # Reihenfolge stets genannt

    # Listen: Deutsch-first-Anzeige, Unterklasse ohne Praefix dedupliziert (DE+EN = 1 Zeile):
    kaempfer = next(z for z in k["klassen"] if z["name_de"] == "Kämpfer")
    assert kaempfer["anzeige"] == "Kämpfer (Fighter)"
    assert [u["name_de"] for u in kaempfer["unterklassen"]] == ["Champion"]
    assert len(kaempfer["unterklassen"][0]["quellen"]) == 2   # srd-de + Open5e gemergt
    assert [z["anzeige"] for z in s["spezies"]] == ["Mensch (Human)"]
    assert [z["anzeige"] for z in h["hintergruende"]] == ["Soldat (Soldier)"]
    t = ch.foliant_liste_talente(kategorie="herkunft")
    assert [z["name_de"] for z in t["talente"]] == ["Wilder Angreifer"]
