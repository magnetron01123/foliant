"""Regressionstests A1 (Editionslogik) + A6 (Fuzzy/Ranking) aus dem Korrekturauftrag.

Synthetische Fixture-DB (offline, temporaer): ein 2024-Bestand, ein 2014-Bestand und
eine 2014-'Flut', die im alten Code das editionsuebergreifende Roh-Limit ausschoepfte
und vorhandene 2024-Treffer verdraengte."""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app.tools import nachschlagen as ns

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    pfad = tmp_path / "foliant-editionen.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
        "VALUES (?,?,?,?,?,?,?)",
        [("srd-de", "SRD 5.2.1 (Deutsch)", "de", "2024", "pdf", "CC-BY-4.0", 10),
         ("phb-2014-de", "Spielerhandbuch (2014)", "de", "2014", "pdf", "privat", 40)])
    eintraege = [
        # Gleichnamige Fassungen beider Editionen (gezielter Abruf, A1.3):
        (1, "zauber", "Feuerball", "Fireball", "de", "2024", "139", "2024er Feuerball: 8W6."),
        (2, "zauber", "Feuerball", "Fireball", "de", "2014", "241", "2014er Feuerball: 8W6, alte Fassung."),
        # Schwacher 2024-Treffer: 'Blitz' NUR im Body (A1.1):
        (1, "zauber", "Donnerkeil", "Thunderbolt", "de", "2024", "150",
         "Ein greller Blitz faehrt vom Himmel."),
        # Fuzzy-Ziele (A6): Dreher ohne gemeinsamen Prefix-Token.
        (1, "zauber", "Nebelschritt", "Misty Step", "de", "2024", "160", "Teleport 9 Meter."),
        (1, "zauber", "Nebelschrei", None, "de", "2024", "161", "Ein Schrei aus Nebel."),
        # SYN-P0-002 (Synthese 2026-07-12, verifiziert): Die Pi-Konstellation - der
        # 2024-Zustand traegt den Klammer-Zusatz, der englische 2014-Eintrag den blanken
        # Namen (Glossar-Bruecke). Vor dem Fix waehlte der klammerlose Nutzerbegriff den
        # 2014-Eintrag und behauptete 'keine 2024-Fassung'.
        (1, "regel", "Erschöpfung (Zustand)", None, "de", "2024", "206",
         "*Kontext: Regelglossar*\n\n2024: kumulativ, je Stufe -2 auf W20-Prüfungen."),
        (2, "regel", None, "Exhaustion", "en", "2014", "291",
         "2014: six levels with different effects per level."),
    ]
    # 2014-Flut: 45 Eintraege, die auf 'Blitz' stark ranken (Name + Body) - mehr als das
    # Roh-Limit der Suche (limit 8 * Faktor 5 = 40).
    for i in range(45):
        eintraege.append((2, "zauber", f"Blitz {i:02d}", None, "de", "2014", str(200 + i),
                          "Blitz Blitz Blitz - alter Blitzzauber."))
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)", eintraege)
    con.execute(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
        "VALUES ('Exhaustion','Erschöpfung',1,'Spielerhandbuch (2014)','2014')")
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def test_a1_flut_verdraengt_2024_nicht(bestand):
    """>40 gut rankende 2014-Treffer + 1 schwacher 2024-Treffer: Die 2024-Suche muss den
    2024-Treffer finden (Editionsfilter VOR dem Roh-Limit)."""
    s = ns.foliant_suche_bestand("Blitz")
    namen = [t["name_de"] for t in s["treffer"]]
    assert "Donnerkeil" in namen, f"2024-Treffer von 2014-Flut verdraengt: {namen}"
    assert all(t["edition"] == "2024" for t in s["treffer"])


def test_a1_explizite_2014_suche_ohne_falschen_altstand(bestand):
    """Explizite 2014-Suche: angeforderte Edition unter 'treffer'; 2024er neutral als
    'andere_fassungen', NICHT als 'aeltere_staende' mit 'Keine 2024-Fassung'-Text."""
    s = ns.foliant_suche_bestand("Feuerball", edition="2014")
    assert s["treffer"] and s["treffer"][0]["edition"] == "2014"
    assert "aeltere_staende" not in s
    assert all("2024-Fassung" not in str(v) for v in s.values() if isinstance(v, str))
    if "andere_fassungen" in s:
        assert all(t["edition"] != "2014" for t in s["andere_fassungen"])

    # Explizite 2014-Suche nach einem NUR-2024-Inhalt: ehrlich leer, kein Altstand-Text.
    s2 = ns.foliant_suche_bestand("Nebelschritt", edition="2014")
    assert s2["treffer"] == []
    assert "Keine 2024-Fassung" not in s2.get("hinweis", "")


def test_a1_gezielter_editions_abruf(bestand):
    """Gleichnamiger 2014-/2024-Eintrag: beide Fassungen gezielt und vollstaendig abrufbar."""
    d24 = ns.foliant_hol_zauber("Feuerball")                     # Default = 2024
    assert d24["gefunden"] and d24["edition"] == "2024" and "2024er" in d24["regeltext_md"]
    d14 = ns.foliant_hol_zauber("Feuerball", edition="2014")     # ausdruecklich 2014
    assert d14["gefunden"] and d14["edition"] == "2014" and "alte Fassung" in d14["regeltext_md"]
    # Ausdruecklich angeforderte, nicht vorhandene Edition: ehrlich nicht gefunden,
    # mit Verweis auf die vorhandene Fassung - nicht still die andere liefern.
    d = ns.foliant_hol_zauber("Nebelschritt", edition="2014")
    assert d["gefunden"] is False
    assert d.get("vorhandene_fassungen") or "2024" in d.get("hinweis", "")


def test_a1_ungueltige_edition_strukturiert(bestand):
    """Leere und unbekannte Editionsangaben: klarer Validierungsfehler, keine stille
    editionsuebergreifende Suche, keine Exception nach aussen."""
    for kaputt in ("", "  ", "2034", "3e"):
        s = ns.foliant_suche_bestand("Feuerball", edition=kaputt)
        assert s["treffer"] == [] and "fehler" in s, f"edition={kaputt!r} nicht abgelehnt"
    # SYN-P2-001: '5.5e'/'5e' sind AKZEPTIERTE Aliasse (das Projekt nennt 2024 selbst
    # so), keine Fehler - sie normalisieren auf die kanonische Edition.
    s55 = ns.foliant_suche_bestand("Feuerball", edition="5.5e")
    assert s55["treffer"] and s55["treffer"][0]["edition"] == "2024"
    s5 = ns.foliant_suche_bestand("Feuerball", edition="5e")
    assert s5["treffer"] and s5["treffer"][0]["edition"] == "2014"
    d = ns.foliant_hol_zauber("Feuerball", edition="quatsch")
    assert d["gefunden"] is False and "fehler" in d
    with pytest.raises(ValueError):
        con = adb.connect(str(adb.standard_pfad()))
        try:
            adb.fts_suche(con, "Feuerball", edition="")
        finally:
            con.close()


def test_p0_klammerloser_zustand_faellt_nie_auf_2014(bestand):
    """SYN-P0-002: 'Erschöpfung' (klammerlos) liefert bei Standard-Edition den
    2024-Eintrag 'Erschöpfung (Zustand)' - NIE den englischen 2014-'Exhaustion' mit
    falscher 'keine 2024-Fassung'-Behauptung. Explizit 2014 bleibt gezielt abrufbar."""
    d = ns.foliant_hol_regel("Erschöpfung")
    assert d["gefunden"] is True and d["edition"] == "2024", d
    assert d["name_de"] == "Erschöpfung (Zustand)"
    assert "hinweis_alter_stand" not in d
    assert "W20" in d["regeltext_md"]                     # wirklich der 2024-Text
    # die 2014-Fassung bleibt als markierter Zusatz sichtbar (Q1/T6):
    assert any(f["edition"] == "2014" for f in d.get("andere_fassungen", []))

    d14 = ns.foliant_hol_regel("Erschöpfung", edition="2014")
    assert d14["gefunden"] is True and d14["edition"] == "2014"
    assert d14["name_en"] == "Exhaustion"

    s = ns.foliant_suche_bestand("Erschöpfung")
    assert s["treffer"] and s["treffer"][0]["edition"] == "2024"
    assert s["treffer"][0]["name_de"] == "Erschöpfung (Zustand)"


def test_a6_fuzzy_ohne_prefix_und_score_ordnung(bestand):
    """Buchstabendreher OHNE Prefix-Match ('Nebelschirtt') laeuft ueber den Fuzzy-Fallback;
    der bessere Fuzzy-Score gewinnt (Nebelschritt vor Nebelschrei)."""
    s = ns.foliant_suche_bestand("Nebelschirtt")
    namen = [t["name_de"] for t in s["treffer"]]
    assert namen and namen[0] == "Nebelschritt", namen
    assert s.get("hinweis_suchweg", "").startswith("Aehnliche Schreibweise")


def test_a6_deterministische_sortierung(bestand):
    """Gleiche Eingabe -> exakt gleiche Reihenfolge, auch ueber Glossar-/FTS-Laeufe
    hinweg (kein Vergleich unvergleichbarer bm25-Scores)."""
    laeufe = [tuple((t["name_de"], t["edition"]) for t in
                    ns.foliant_suche_bestand("Blitz")["treffer"]) for _ in range(3)]
    assert laeufe[0] == laeufe[1] == laeufe[2]
    # Flut-Namen untereinander deterministisch (Namens-Tiebreak):
    s14 = ns.foliant_suche_bestand("Blitz", edition="2014")
    namen = [t["name_de"] for t in s14["treffer"]]
    assert namen == sorted(namen), "2014-Flut nicht deterministisch sortiert"


def test_c1_editionszustaende_leer_und_2014only(tmp_path, monkeypatch):
    """SYN-P2-001 C1-Abnahme: leerer Bestand lehnt jede unerlaubte Edition ab (kein
    stiller Durchlass); reiner 2014-Bestand liefert bei 2024-Standardsuche ehrlich leer
    + den 2014-Altstand (statt den Default 2024 als 'ungültig' abzuweisen)."""
    import sqlite3
    schema = _SCHEMA.read_text(encoding="utf-8")
    # leerer Bestand
    leer = tmp_path / "leer.sqlite"
    c = sqlite3.connect(leer); c.executescript(schema); c.commit()
    c.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')"); c.commit(); c.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: leer)
    s = ns.foliant_suche_bestand("Feuerball")                 # 2024-Default auf leerer DB
    assert s["treffer"] == [] and "hinweis" in s             # ehrlich leer, kein Crash
    assert "fehler" not in s                                 # 2024 ist unterstützt, nicht ungültig
    r = ns.foliant_suche_bestand("Feuerball", edition="2027")  # nicht unterstützt
    assert "fehler" in r

    # reiner 2014-Bestand
    nur14 = tmp_path / "nur14.sqlite"
    c = sqlite3.connect(nur14); c.executescript(schema)
    c.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet) "
              "VALUES ('phb14','PHB 2014','de','2014','pdf',40)")
    c.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,seite,body_md) "
              "VALUES (1,'zauber','Hexenpfeil','de','2014','290','Alter 2014-Zauber.')")
    c.commit(); c.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    c.commit(); c.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: nur14)
    s2 = ns.foliant_suche_bestand("Hexenpfeil")               # 2024-Default, nur 2014 da
    assert s2["treffer"] == []                               # kein 2024-Treffer
    assert s2.get("aeltere_staende"), s2                     # aber 2014 als Altstand sichtbar
    assert "2024-Fassung" in s2["hinweis"]
