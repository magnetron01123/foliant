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
              "quelle TEXT, edition_quelle TEXT, seite TEXT)")
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


def test_ein_gebuendelter_aufruf_und_gedaechtnis(con):
    c = _charakter()
    fake = FakeProvider()
    uebersetze(c, con, fake)
    assert fake.aufrufe == 1  # genau EIN gebündelter Aufruf
    # die identische Beschreibung erscheint nur EINMAL in der Anfrage (Gedächtnis)
    werte = list(fake.gesehene_ids[0].values())
    assert werte.count("You make two Unarmed Strikes.") == 1
    # ...aber BEIDE Merkmale bekommen die Übersetzung
    assert c.merkmale[0].beschreibung.de == c.merkmale[1].beschreibung.de


def test_leerer_text_bleibt_leer(con):
    c = Charakter()
    c.identitaet.klasse = UeText(en="", art="term")
    uebersetze(c, con, FakeProvider())
    assert c.identitaet.klasse.de == ""


def test_liste_bekommt_klammer_ohne_stern(con):
    """art='liste' -> '(English)' auf Listenebene, aber KEIN irreführender einzelner Stern."""
    c = Charakter()
    c.uebungen.sprachen.append(UeText(en="Common, Elvish", art="liste"))
    uebersetze(c, con, FakeProvider(mapping={"Common, Elvish": "Gemeinsprache, Elfisch"}))
    assert c.uebungen.sprachen[0].de == "Gemeinsprache, Elfisch (Common, Elvish)"
    assert "*" not in c.uebungen.sprachen[0].de


def test_vorgaben_enthalten_aufgeloeste_begriffe(con):
    """Aufgelöste Glossar-Namen gehen als Vorgabe an den Provider (Konsistenz Tabelle<->Fließtext)."""
    c = _charakter()
    fake = FakeProvider()
    uebersetze(c, con, fake)
    assert fake.letzte_vorgaben.get("Monk") == "Mönch"
    assert fake.letzte_vorgaben.get("Flurry of Blows") == "Schlaghagel"
    # unbelegte Begriffe (Mist Wanderer) stehen NICHT als amtliche Vorgabe drin
    assert "Mist Wanderer" not in fake.letzte_vorgaben


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

def test_listen_guard_laesst_liste_englisch_bei_falscher_item_anzahl(con):
    """Erfindet der Provider Listeneinträge (Befund: 'Crossbow, Hand' -> zwei Waffen),
    bleibt die Liste nach dem Retry ehrlich englisch statt verfälscht deutsch."""
    c = Charakter()
    c.uebungen.waffen.append(UeText(en="Hand Crossbow, Scimitar", art="liste"))
    provider = FakeProvider(mapping={"Hand Crossbow, Scimitar": "Armbrust, Handarmbrust, Krummsäbel"})
    uebersetze(c, sqlite3.connect(":memory:"), provider) if False else None
    # In-Memory-Glossar der Fixture nutzen (hat die quelle-Spalte)
    uebersetze(c, con, provider)
    assert provider.aufrufe == 2                       # Guard erzwang den Retry
    assert c.uebungen.waffen[0].de == "Hand Crossbow, Scimitar"   # ehrlich englisch


def test_listen_mit_korrekter_anzahl_werden_uebernommen(con):
    c = Charakter()
    c.uebungen.waffen.append(UeText(en="Hand Crossbow, Scimitar", art="liste"))
    provider = FakeProvider(mapping={"Hand Crossbow, Scimitar": "Handarmbrust, Krummsäbel"})
    uebersetze(c, con, provider)
    assert provider.aufrufe == 1
    assert c.uebungen.waffen[0].de == "Handarmbrust, Krummsäbel (Hand Crossbow, Scimitar)"


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
