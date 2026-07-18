"""Übersetzer-Tests: Terminologie (bestehende Glossar-Logik) + LLM-Pfad mit FAKE-Provider.

Keine echten API-Aufrufe (AUFTRAG §8.4: automatisierte Tests nur mit Fake). Glossar als
In-Memory-Fixture. Prüft §5-Regel, Terminologie-Determinismus, Übersetzungsgedächtnis,
gebündelten Aufruf, JSON-Vertrag und dass Zahlen nie durch das Modell laufen.
"""
from __future__ import annotations

import sqlite3

import pytest

from app import glossar
from app.charakterbogen import terminologie, uebersetzer
from app.charakterbogen.modelle import Attribut, Charakter, Merkmal, UeText
from app.charakterbogen.uebersetzer import (
    AnthropicProvider, FakeProvider, ProviderNichtKonfiguriert, UebersetzungsFehler,
    _json_aus_text, uebersetze,
)


@pytest.fixture()
def con():
    glossar._GLOSSAR_CACHE.clear()  # Test-Isolation (Cache ist signatur-basiert)
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE glossar (term_de TEXT, term_en TEXT, offiziell INT, "
              "quelle TEXT, edition_quelle TEXT, seite TEXT, "
              "UNIQUE(term_en, term_de))")   # wie das echte Schema (Upsert-Ziel)
    c.executemany("INSERT INTO glossar VALUES (?,?,?,?,?,?)", [
        ("Mönch", "Monk", 1, "Ulisses", "2024", ""),
        ("Schlaghagel", "Flurry of Blows", 1, "Ulisses", "2024", ""),
        ("Fokuspunkt", "Focus Point", 0, "Community", "", ""),   # inoffiziell -> '*'
    ])
    c.commit()
    yield c
    glossar._GLOSSAR_CACHE.clear()
    c.close()


# --- Terminologie (§5) -------------------------------------------------------

def test_terminologie_offiziell(con):
    assert terminologie.aufloesen(con, "Monk") == "Mönch (Monk)"
    assert terminologie.aufloesen(con, "Flurry of Blows") == "Schlaghagel (Flurry of Blows)"


def test_terminologie_inoffiziell_mit_stern(con):
    assert terminologie.aufloesen(con, "Focus Point") == "Fokuspunkt* (Focus Point)"


def test_terminologie_kein_treffer_ist_none(con):
    assert terminologie.aufloesen(con, "Mist Wanderer") is None


def test_terminologie_fallback_markiert(con):
    assert terminologie.markiere_fallback("Mist Wanderer", "Nebelwanderer") == "Nebelwanderer* (Mist Wanderer)"


# --- Übersetzung des Modells -------------------------------------------------

def _charakter() -> Charakter:
    c = Charakter()
    c.identitaet.name = "Sorin Vale"  # str -> nie übersetzt
    c.identitaet.klasse = UeText(en="Monk", art="term")
    c.identitaet.hintergrund = UeText(en="Mist Wanderer", art="term")  # nicht im Glossar
    c.attribute["dex"] = Attribut(wert=18, mod="+4", rettungswurf="+7", rettung_geuebt=True)
    c.merkmale.append(Merkmal(name=UeText(en="Flurry of Blows", art="term"),
                              beschreibung=UeText(en="You make two Unarmed Strikes.", art="text"),
                              herkunft="klasse"))
    c.merkmale.append(Merkmal(name=UeText(en="Patient Defense", art="term"),
                              beschreibung=UeText(en="You make two Unarmed Strikes.", art="text"),
                              herkunft="klasse"))  # gleiche Beschreibung -> Gedächtnis
    return c


def test_feste_begriffe_ueber_glossar_ohne_llm(con):
    c = _charakter()
    fake = FakeProvider()
    uebersetze(c, con, fake)
    assert c.identitaet.klasse.de == "Mönch (Monk)"
    assert c.merkmale[0].name.de == "Schlaghagel (Flurry of Blows)"
    # Glossar-Begriffe dürfen NICHT an den LLM gehen:
    gesendet = {t for anruf in fake.gesehene_ids for t in anruf.values()}
    assert "Monk" not in gesendet and "Flurry of Blows" not in gesendet


def test_unbelegter_begriff_ueber_llm_mit_stern(con):
    c = _charakter()
    fake = FakeProvider(mapping={"Mist Wanderer": "Nebelwanderer"})
    uebersetze(c, con, fake)
    assert c.identitaet.hintergrund.de == "Nebelwanderer* (Mist Wanderer)"


def test_freier_text_ueber_llm(con):
    c = _charakter()
    fake = FakeProvider(mapping={"You make two Unarmed Strikes.": "Du machst zwei waffenlose Schläge."})
    uebersetze(c, con, fake)
    assert c.merkmale[0].beschreibung.de == "Du machst zwei waffenlose Schläge."


def test_name_wird_nicht_uebersetzt(con):
    c = Charakter()
    c.persoenlichkeit.notizen = UeText(en="Sorin Vale", art="name")
    uebersetze(c, con, FakeProvider())
    assert c.persoenlichkeit.notizen.de == "Sorin Vale"


def test_zahlen_bleiben_unberuehrt(con):
    c = _charakter()
    uebersetze(c, con, FakeProvider())
    assert c.attribute["dex"].wert == 18 and c.attribute["dex"].mod == "+4"


def test_gebuendelte_aufrufe_und_gedaechtnis(con):
    """Zwei gebündelte Aufrufe (Stufe 1 Begriffe, Stufe 2 Fließtexte) - nicht mehr pro Feld.
    Das Übersetzungsgedächtnis bleibt: gleicher englischer Text -> genau EIN Eintrag."""
    c = _charakter()
    fake = FakeProvider()
    uebersetze(c, con, fake)
    assert fake.aufrufe == 2
    # die identische Beschreibung erscheint nur EINMAL in der Anfrage (Gedächtnis)
    werte = [w for anfrage in fake.gesehene_ids for w in anfrage.values()]
    assert werte.count("You make two Unarmed Strikes.") == 1
    # ...aber BEIDE Merkmale bekommen die Übersetzung
    assert c.merkmale[0].beschreibung.de == c.merkmale[1].beschreibung.de


def test_ein_aufruf_wenn_nur_begriffe_offen(con):
    """Ohne Fließtexte entfällt Stufe 2 (kein Leer-Aufruf)."""
    c = Charakter()
    c.identitaet.spezies = UeText(en="Mist Wanderer", art="term")
    fake = FakeProvider()
    uebersetze(c, con, fake)
    assert fake.aufrufe == 1


def test_leerer_text_bleibt_leer(con):
    c = Charakter()
    c.identitaet.klasse = UeText(en="", art="term")
    uebersetze(c, con, FakeProvider())
    assert c.identitaet.klasse.de == ""


def test_liste_bekommt_klammer_ohne_stern(con):
    """art='liste' -> item-weise DETERMINISTISCH aus dem Glossar (nie LLM), '(English)'
    auf Listenebene, KEIN irreführender einzelner Stern."""
    con.execute("INSERT INTO glossar VALUES ('Gemeinsprache','Common',1,'U','2024',''),"
                "('Elfisch','Elvish',1,'U','2024','')")
    con.commit()
    from app import glossar as g
    g._GLOSSAR_CACHE.clear()
    c = Charakter()
    c.uebungen.sprachen.append(UeText(en="Common, Elvish", art="liste"))
    try:
        fake = FakeProvider()
        uebersetze(c, con, fake)
    finally:
        g._GLOSSAR_CACHE.clear()
    assert c.uebungen.sprachen[0].de == "Gemeinsprache, Elfisch (Common, Elvish)"
    assert "*" not in c.uebungen.sprachen[0].de
    assert fake.aufrufe == 0                     # Listen erreichen das Modell nie


def test_vorgaben_enthalten_aufgeloeste_begriffe(con):
    """Aufgelöste Glossar-Namen gehen als Vorgabe an den Provider (Konsistenz Tabelle<->Fließtext)."""
    c = _charakter()
    fake = FakeProvider()
    uebersetze(c, con, fake)
    assert fake.letzte_vorgaben.get("Monk") == "Mönch"
    assert fake.letzte_vorgaben.get("Flurry of Blows") == "Schlaghagel"


def test_unbelegte_begriffe_werden_zur_vorgabe_fuer_den_fliesstext(con):
    """Der Kern der Zweistufigkeit (Befund 16.07.2026): Ein unbelegter Begriff wird ZUERST
    übersetzt und geht dann als Vorgabe in den Fließtext-Aufruf - sonst hieß derselbe Name
    im Feld 'Krieger des Schattens' und im Fließtext 'Kämpfer des Schattens'."""
    c = Charakter()
    c.identitaet.unterklasse = UeText(en="Warrior of Shadow", art="term")
    c.merkmale.append(Merkmal(name=UeText(en="Monk", art="term"),
                              beschreibung=UeText(en="You are a Warrior of Shadow."),
                              herkunft="klasse"))
    fake = FakeProvider(mapping={"Warrior of Shadow": "Krieger des Schattens"})
    uebersetze(c, con, fake)

    assert fake.aufrufe == 2
    # Stufe 1 übersetzte NUR den Begriff ...
    assert list(fake.gesehene_ids[0].values()) == ["Warrior of Shadow"]
    # ... das Feld trägt die §5-Form mit Stern ...
    assert c.identitaet.unterklasse.de == "Krieger des Schattens* (Warrior of Shadow)"
    # ... und Stufe 2 bekam den Namen OHNE Stern/Klammer als bindende Vorgabe.
    assert fake.letzte_vorgaben.get("Warrior of Shadow") == "Krieger des Schattens"
    assert "You are a Warrior of Shadow." in fake.gesehene_ids[1].values()


def test_deterministisch(con):
    fake = FakeProvider(mapping={"Mist Wanderer": "Nebelwanderer"})
    a = uebersetze(_charakter(), con, fake).identitaet.hintergrund.de
    b = uebersetze(_charakter(), con, fake).identitaet.hintergrund.de
    assert a == b == "Nebelwanderer* (Mist Wanderer)"


# --- JSON-Vertrag / Fehlerpfade ---------------------------------------------

class _KaputterProvider:
    def uebersetze(self, felder, vorgaben=None):
        return {k: "x" for k in list(felder)[:-1]}  # ein Schlüssel fehlt


def test_unvollstaendige_antwort_schlaegt_fehl(con):
    c = _charakter()
    with pytest.raises(UebersetzungsFehler):
        uebersetze(c, con, _KaputterProvider())


def test_anthropic_ohne_key_nicht_konfiguriert():
    with pytest.raises(ProviderNichtKonfiguriert):
        AnthropicProvider(api_key="", modell="")


def test_json_aus_text_toleriert_codefence():
    assert _json_aus_text('```json\n{"0": "hallo"}\n```') == {"0": "hallo"}
    assert _json_aus_text('Hier: {"1": "welt"} fertig') == {"1": "welt"}


# --- Review-Runde 2 (16.07.2026): Listen-Guard + Fließtext-Vorgaben ------------

def test_liste_unbelegt_bleibt_ehrlich_englisch(con):
    """KEIN Item belegt -> Liste bleibt unveraendert englisch (keine redundante Klammer,
    kein LLM-Aufruf). Der fruehere Item-Anzahl-Guard ist damit obsolet: das Modell kann
    keine Eintraege mehr erfinden, weil es Listen gar nicht mehr sieht."""
    c = Charakter()
    c.uebungen.waffen.append(UeText(en="Wargong, Mystery Blade", art="liste"))
    fake = FakeProvider(mapping={"Wargong, Mystery Blade": "Kriegsgong, Raetselklinge"})
    uebersetze(c, con, fake)
    assert c.uebungen.waffen[0].de == "Wargong, Mystery Blade"
    assert fake.aufrufe == 0


def test_liste_teilbelegt_mischt_deterministisch(con):
    """Belegte Items amtlich, unbelegte unveraendert - laufuebergreifend stabil
    (Befund 17.07.2026: 'Wargong' hiess je Lauf 'Kriegsgong'/'Trommel'/englisch)."""
    con.execute("INSERT INTO glossar VALUES "
                "('Handarmbrust','Hand Crossbow',1,'U','2024',''),"
                "('Krummsäbel','Scimitar',1,'U','2024','')")
    con.commit()
    from app import glossar as g
    g._GLOSSAR_CACHE.clear()
    c = Charakter()
    c.uebungen.waffen.append(UeText(en="Hand Crossbow, Wargong, Scimitar", art="liste"))
    try:
        uebersetze(c, con, FakeProvider())
    finally:
        g._GLOSSAR_CACHE.clear()
    assert c.uebungen.waffen[0].de == \
        "Handarmbrust, Wargong, Krummsäbel (Hand Crossbow, Wargong, Scimitar)"


def test_fliesstext_begriffe_werden_als_vorgaben_erzwungen(con):
    """Glossar-Begriffe, die nur im FREITEXT vorkommen, gehen als Vorgaben an den Provider
    (Befund: 'Grappled' wurde frei als 'ergriffen' übersetzt statt amtlich 'Gepackt')."""
    c = Charakter()
    c.merkmale.append(Merkmal(name=UeText(en="Mist Wanderer Feature"),
                              beschreibung=UeText(en="You can use Flurry of Blows twice."),
                              herkunft="klasse"))
    provider = FakeProvider()
    uebersetze(c, con, provider)
    assert provider.letzte_vorgaben.get("Flurry of Blows") == "Schlaghagel"


# --- Nachfragegetriebenes Nachschlagen (16.07.2026) ----------------------------

def test_nachschlager_treffer_gilt_als_belegt_ohne_llm(con):
    """Findet der Nachschlager einen Begriff, bekommt er KEINEN Stern und geht NICHT
    ans Sprachmodell; der Name wird Vorgabe für den Fließtext."""
    c = Charakter()
    c.identitaet.klasse = UeText(en="Martial Arts", art="term")
    c.merkmale.append(Merkmal(name=UeText(en="Monk", art="term"),
                              beschreibung=UeText(en="Use Martial Arts."), herkunft="klasse"))
    fake = FakeProvider()

    def nachschlager(con_, begriff):
        return "Kampfkünste (Martial Arts)" if begriff == "Martial Arts" else None

    uebersetze(c, con, fake, nachschlager=nachschlager)
    assert c.identitaet.klasse.de == "Kampfkünste (Martial Arts)"   # belegt, OHNE Stern
    assert fake.letzte_vorgaben.get("Martial Arts") == "Kampfkünste"
    # Der Begriff lief NICHT durchs Sprachmodell (nur der Fließtext, Stufe 2):
    alle_angefragt = [w for a in fake.gesehene_ids for w in a.values()]
    assert "Martial Arts" not in alle_angefragt


def test_nachschlager_none_faellt_auf_llm_stufe_zurueck(con):
    c = Charakter()
    c.identitaet.klasse = UeText(en="Mist Wanderer", art="term")
    fake = FakeProvider(mapping={"Mist Wanderer": "Nebelwanderer"})
    uebersetze(c, con, fake, nachschlager=lambda con_, b: None)
    assert c.identitaet.klasse.de == "Nebelwanderer* (Mist Wanderer)"   # wie ohne Nachschlager


def test_dnddeutsch_nachschlager_wertet_antwort_aus(con, monkeypatch):
    """Der echte Nachschlager: exakter Treffer -> §5-Form; Best-Effort-Upsert ins Glossar."""
    from app.charakterbogen.uebersetzer import DnddeutschNachschlager

    n = DnddeutschNachschlager(zeitbudget_s=60)
    monkeypatch.setattr(n, "_hole", lambda begriff: {"result": [
        {"name_en": "Martial Arts", "name_de": "Kampfkünste",
         "name_de_ulisses": "", "src_de": {"book": "PHB(de)", "book_long": "PHB", "p": "78"}},
        {"name_en": "Martial Arts Adept", "name_de": "Kampfkunst-Adept",
         "name_de_ulisses": "", "src_de": {}}]})
    assert n(con, "Martial Arts") == "Kampfkünste (Martial Arts)"
    # Best-Effort-Upsert hat das (schreibbare) Test-Glossar dauerhaft verbessert:
    zeile = con.execute("SELECT term_de, offiziell FROM glossar "
                        "WHERE term_en='Martial Arts'").fetchone()
    assert tuple(zeile) == ("Kampfkünste", 1)


def test_dnddeutsch_nachschlager_degradiert_bei_fehlern(con, monkeypatch):
    from app.charakterbogen.uebersetzer import DnddeutschNachschlager

    kaputt = DnddeutschNachschlager(zeitbudget_s=60)
    monkeypatch.setattr(kaputt, "_hole", lambda b: (_ for _ in ()).throw(OSError("offline")))
    assert kaputt(con, "Martial Arts") is None      # offline -> None, kein Crash

    leer = DnddeutschNachschlager(zeitbudget_s=60)
    monkeypatch.setattr(leer, "_hole", lambda b: {"result": []})
    assert leer(con, "Mist Wanderer") is None       # kein Treffer -> ehrlicher Stern

    muede = DnddeutschNachschlager(zeitbudget_s=-1)  # Budget sofort erschöpft
    assert muede(con, "Martial Arts") is None


# --- Mehrklassen-Anzeige (17.07.2026) ----------------------------------------
# Der Extractor laesst klasse/stufe bei 'Fighter 3 / Wizard 2' bewusst leer (§7.4) -
# auf dem Bogen standen dadurch STUMM leere Felder. Der Uebersetzer baut jetzt eine
# deterministische Anzeige (nur exakte Glossar-Treffer, sonst englisch) und setzt die
# Charakterstufe als regeldefinierte SUMME (srd-de 'Klassenkombinationen', S. 28).

def _mehrklassen_charakter():
    from app.charakterbogen.modelle import Charakter
    c = Charakter()
    c.identitaet.name = "Rowan"
    c.identitaet.klasse_stufe_roh = "Monk 3 / Rogue 2"
    return c


def test_mehrklassen_anzeige_und_stufensumme(con):
    con.execute("INSERT INTO glossar VALUES ('Schurke','Rogue',1,'Ulisses','2024','')")
    con.commit()
    from app import glossar as g
    g._GLOSSAR_CACHE.clear()
    try:
        c = uebersetze(_mehrklassen_charakter(), con, FakeProvider())
    finally:
        g._GLOSSAR_CACHE.clear()
    assert c.identitaet.mehrklassen_anzeige == "Mönch 3 / Schurke 2 (Monk 3 / Rogue 2)"
    assert c.identitaet.stufe == 5                       # Summe, regeldefiniert
    assert c.identitaet.klasse is None                   # Beleg-Semantik unveraendert


def test_mehrklassen_unbelegte_klasse_bleibt_englisch(con):
    # 'Rogue' ist hier NICHT belegt -> Teil bleibt englisch, kein Raten
    from app import glossar as g
    g._GLOSSAR_CACHE.clear()
    try:
        c = uebersetze(_mehrklassen_charakter(), con, FakeProvider())
    finally:
        g._GLOSSAR_CACHE.clear()
    assert c.identitaet.mehrklassen_anzeige == "Mönch 3 / Rogue 2 (Monk 3 / Rogue 2)"
    assert c.identitaet.stufe == 5


def test_einklassig_bleibt_unberuehrt(con):
    from app.charakterbogen.modelle import Charakter, UeText
    c = Charakter()
    c.identitaet.klasse = UeText(en="Monk", art="term")
    c.identitaet.stufe = 5
    c.identitaet.klasse_stufe_roh = "Monk 5"
    c = uebersetze(c, con, FakeProvider())
    assert c.identitaet.mehrklassen_anzeige is None
    assert c.identitaet.stufe == 5
