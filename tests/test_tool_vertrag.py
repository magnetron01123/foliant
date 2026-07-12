"""Tool-Vertrag (SYN-P1-002/003/009, Synthese 2026-07-12): stabile Referenzen,
geschlossene Schemas, Konfliktausweis.

Drei Vertragsversprechen, deren Fehlen die Reviews nachwiesen: (1) ein Suchtreffer war
nicht exakt nachladbar (Detail wechselte still zur Prioritaetsquelle), (2) Wertemengen-
Parameter waren freie Strings ohne enum (Client konnte Fehlaufrufe nicht abfangen),
(3) inhaltlich abweichende Dubletten verschwanden hinter der Quellenprioritaet."""
import asyncio
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app.tools import nachschlagen as ns

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    pfad = tmp_path / "foliant-vertrag.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
        "VALUES (?,?,?,?,?,?,?)",
        [("srd-de", "SRD 5.2.1 (Deutsch)", "de", "2024", "pdf", "CC-BY-4.0", 10),
         ("open5e-srd-2024", "SRD 5.2 (Open5e)", "en", "2024", "open5e", "CC-BY-4.0", 60)])
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [# DE/EN-Dublette mit INHALTLICH ABWEICHENDER Aussage (Vampir-Muster: 'weiss'
         # vs. 'unaware') - gleiche Edition, exakte Glossar-Bruecke:
         (1, "monster", "Nachtmahr", None, "de", "2024", "350",
          "*Kontext: Monster von A–Z*\n\nDas Ziel weiß danach, dass es bezaubert wurde."),
         (2, "monster", None, "Nightmare", "en", "2024", None,
          "When the spell ends, the target is unaware it was charmed."),
         # Zwei gleichsprachige srd-de-Fassungen desselben Namens/derselben Edition mit
         # klar abweichendem Text (Errata-Muster) - fuer den harten Konfliktausweis:
         (1, "zauber", "Konfliktzauber", None, "de", "2024", "10",
          "*Kontext: Zauber*\n\nDer Schaden betraegt 8W6 und der Radius sechs Meter."),
         (1, "zauber", "Konfliktzauber", None, "de", "2024", "11",
          "*Kontext: Zauber (Errata)*\n\nDer Schaden betraegt 10W6 und der Radius "
          "neun Meter, ausserdem wirkt der Zauber eine Runde laenger nach.")])
    con.execute(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
        "VALUES ('Nightmare','Nachtmahr',1,'Spielerhandbuch 2024','2024')")
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def test_p1_rundlauf_per_eintrag_id(bestand):
    """SYN-P1-002: Treffer tragen eintrag_id/quelle_kuerzel; der Detailabruf per
    Referenz liefert EXAKT diesen Eintrag - auch wenn die Namensaufloesung eine andere
    (Prioritaets-)Quelle waehlen wuerde."""
    s = ns.foliant_suche_bestand("Nightmare")
    t = s["treffer"][0]
    assert t["eintrag_id"] and t["quelle_kuerzel"] == "srd-de"   # kanonisch: Prio 10
    # Open5e-Fassung gezielt: ueber fremdsprachige_fassungen/Konflikt-Referenz laden.
    d_kanon = ns.foliant_hol_monster("Nightmare")
    fremde = d_kanon.get("fremdsprachige_fassungen") or []
    assert fremde, d_kanon
    d_en = ns.foliant_hol_monster("egal", eintrag_id=fremde[0]["eintrag_id"])
    assert d_en["gefunden"] and d_en["quelle"] == "SRD 5.2 (Open5e)"
    assert "unaware" in d_en["regeltext_md"]
    # Falsche Kategorie zur Referenz -> strukturierter Fehler, kein stilles Umbiegen:
    falsch = ns.foliant_hol_zauber("egal", eintrag_id=fremde[0]["eintrag_id"])
    assert falsch["gefunden"] is False and "fehler" in falsch
    # Veraltete Referenz -> ehrlicher Fehler:
    weg = ns.foliant_hol_monster("egal", eintrag_id=999999)
    assert weg["gefunden"] is False and "existiert nicht" in weg["fehler"]


def test_p1_fremdfassung_wird_ausgewiesen(bestand):
    """SYN-P1-009 (Vampir-Muster): die anderssprachige Fassung gleicher Edition wird als
    nachladbare Referenz ausgewiesen statt still von der Prioritaet verdeckt."""
    d = ns.foliant_hol_monster("Nachtmahr")
    assert d["gefunden"] and d["quelle"] == "SRD 5.2.1 (Deutsch)"
    fremde = d.get("fremdsprachige_fassungen")
    assert fremde and fremde[0]["sprache"] == "en"
    assert "hinweis_fremdfassung" in d and "abweichen" in d["hinweis_fremdfassung"]


def test_p1_gleichsprachiger_konflikt_wird_markiert(bestand):
    """SYN-P1-009 + SYN-P0-003: zwei deutsche Fassungen desselben Eintrags mit
    wesentlich abweichendem Text. Der Detailabruf liefert den ausfuehrlichsten
    (Errata-)Abschnitt UND weist die abweichende Zweitfassung transparent aus -
    entweder als weitere_abschnitte oder als konflikt_quellen (nie still verdeckt)."""
    d = ns.foliant_hol_zauber("Konfliktzauber")
    assert d["gefunden"] is True
    assert "10W6" in d["regeltext_md"]                      # die laengere Errata-Fassung
    ausgewiesen = d.get("weitere_abschnitte") or d.get("konflikt_quellen")
    assert ausgewiesen, d                                   # Zweitfassung nicht verdeckt
    assert ausgewiesen[0].get("eintrag_id")


def test_p1_schemas_tragen_enums_und_annotations(bestand):
    """SYN-P1-003: kategorie/richtung/methoden sind enums im JSON-Schema; alle 16 Tools
    tragen readOnlyHint/idempotentHint."""
    from app.server import mcp

    async def hole():
        return await mcp.get_tools()

    tools = asyncio.run(hole())
    assert len(tools) == 16
    def enum_von(tool, feld):
        prop = tools[tool].parameters["properties"][feld]
        for variante in [prop, *prop.get("anyOf", [])]:
            if "enum" in variante:
                return set(variante["enum"])
        return set()
    assert "zauber" in enum_von("foliant_suche_bestand", "kategorie")
    assert enum_von("foliant_uebersetze_begriff", "richtung") == {"en_de", "de_en", "auto"}
    assert enum_von("foliant_hol_attributswerte", "attributsmethode") == {"standard_array", "point_buy"}
    assert "herkunft" in enum_von("foliant_liste_talente", "kategorie")
    for name, t in tools.items():
        ann = t.annotations
        assert ann is not None and ann.readOnlyHint is True, name
        assert ann.idempotentHint is True, name
