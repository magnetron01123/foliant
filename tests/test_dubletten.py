"""Regressionstests A3 (fachliche DE/EN-Dubletten) aus dem Korrekturauftrag.

Kern: 'Feuerball' (srd-de, ohne name_en - wie der reale PDF-Import) und 'Fireball'
(Open5e) sind derselbe Inhalt in derselben Edition/Kategorie -> EIN kanonischer Treffer
(kleinste prioritaet liefert den Text, weitere Quellen als Provenienz). Nur EXAKTE
Glossarentsprechungen bruecken; Fuzzy-Naehe begruendet keine Dublette."""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app.tools import nachschlagen as ns

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    pfad = tmp_path / "foliant-dubletten.sqlite"
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
        [# Die fachliche Dublette: deutscher Eintrag OHNE name_en (realer PDF-Import)
         # + englischer Open5e-Eintrag; Bruecke NUR ueber die exakte Glossar-Zeile.
         (1, "zauber", "Feuerball", None, "de", "2024", "139", "8W6 Feuerschaden (deutsch)."),
         (2, "zauber", None, "Fireball", "en", "2024", None, "8d6 fire damage (english)."),
         # Aehnlich, aber ANDERER Inhalt - darf nie mitgemergt werden:
         (1, "zauber", "Verzögerter Feuerball", None, "de", "2024", "133", "Glimmender Ball."),
         (2, "zauber", None, "Delayed Blast Fireball", "en", "2024", None, "Glowing bead."),
         # Gleicher Name, andere KATEGORIE - bleibt getrennt:
         (1, "zauber", "Schild", "Shield", "de", "2024", "180", "Reaktion: +5 RK."),
         (1, "gegenstand", "Schild", "Shield", "de", "2024", "221", "+2 RK, eine Hand."),
         # Gleicher Inhalt, andere EDITION - bleibt getrennt (V5):
         (3, "zauber", "Feuerball", "Fireball", "de", "2014", "241", "Alter 2014-Feuerball."),
         # Fuzzy-nahe Glossar-Zeile darf NICHT bruecken (A3): 'Eisstrahl' vs 'Eisstrahlen'
         # sind im Glossar nur als PLURAL-Zeile verbunden -> keine exakte Entsprechung.
         (1, "zauber", "Eisstrahl", None, "de", "2024", "150", "Kaeltestrahl (deutsch)."),
         (2, "zauber", None, "Ray of Frost", "en", "2024", None, "A frigid beam (english)."),
         # SYN-P0-003: GLEICHNAMIGE Abschnitte DERSELBEN Quelle (Spielregeln-Kapitel vs.
         # Monster-Wertekasten-Erklaerung) sind KEINE Dublette - Verschmelzen machte
         # den 'vollstaendigen Text' zum Fragment.
         (1, "regel", "Reaktionen", None, "de", "2024", "11",
          "*Kontext: Die Spielregeln > Kampf*\n\nSpielerregel: eine Reaktion pro Runde."),
         (1, "regel", "Reaktionen", None, "de", "2024", "299",
          "*Kontext: Monster > Elemente von Wertekästen*\n\nKurzerklaerung im Wertekasten.")])
    con.executemany(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle,seite) "
        "VALUES (?,?,?,?,?,?)",
        [("Fireball", "Feuerball", 1, "Spielerhandbuch 2024", "2024", "139"),
         ("Delayed Blast Fireball", "Verzögerter Feuerball", 1, "Spielerhandbuch 2024",
          "2024", "133"),
         ("Shield", "Schild", 1, "Spielerhandbuch 2024", "2024", "180"),
         # NUR eine fuzzy-nahe Zeile (Pluralform) - exakt matcht sie 'Eisstrahl' nicht:
         ("Rays of Frost", "Eisstrahlen", 1, "dnddeutsch.de", None, None)])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def _zauber_2024(s):
    return [t for t in s["treffer"] if t["kategorie"] == "zauber" and t["edition"] == "2024"]


def test_a3_genau_ein_kanonischer_feuerball(bestand):
    """'Fireball' UND 'Feuerball' liefern je genau EINEN kanonischen Feuerball-Treffer
    (2024): deutscher Text (kleinste prioritaet), Open5e als weitere Quelle."""
    for suchbegriff in ("Fireball", "Feuerball"):
        s = ns.foliant_suche_bestand(suchbegriff)
        feuerbaelle = [t for t in _zauber_2024(s)
                       if (t["name_de"] or t["name_en"]) in ("Feuerball", "Fireball")]
        assert len(feuerbaelle) == 1, (suchbegriff, feuerbaelle)
        kanon = feuerbaelle[0]
        assert kanon["name_de"] == "Feuerball"            # kanonischer Text = prio 10
        assert kanon["name_en"] == "Fireball"             # Provenienz beider Namen
        assert kanon["quelle"] == "SRD 5.2.1 (Deutsch)"
        assert any("Open5e" in q for q in kanon.get("weitere_quellen", [])), kanon


def test_a3_aehnliche_zauber_bleiben_getrennt(bestand):
    """'Verzögerter Feuerball' ist KEINE Dublette von 'Feuerball' (kein Uebermerge)."""
    s = ns.foliant_suche_bestand("Feuerball")
    namen = {t["name_de"] or t["name_en"] for t in _zauber_2024(s)}
    assert "Feuerball" in namen and "Verzögerter Feuerball" in namen


def test_a3_kategorien_bleiben_getrennt(bestand):
    """'Schild' als Zauber und als Gegenstand bleiben zwei Treffer (B4/T8)."""
    s = ns.foliant_suche_bestand("Schild")
    kategorien = {t["kategorie"] for t in s["treffer"] if t["name_de"] == "Schild"}
    assert kategorien == {"zauber", "gegenstand"}


def test_a3_editionen_bleiben_getrennt(bestand):
    """Der 2014-Feuerball wird nie in den 2024-Treffer gemergt (V5)."""
    s = ns.foliant_suche_bestand("Feuerball")
    assert all(t["edition"] == "2024" for t in s["treffer"])
    assert any(t["edition"] == "2014" for t in s.get("aeltere_staende", []))
    d = ns.foliant_hol_zauber("Feuerball", edition="2014")
    assert d["gefunden"] and "Alter 2014" in d["regeltext_md"]


def test_p0_gleichnamige_abschnitte_derselben_quelle_bleiben_getrennt(bestand):
    """SYN-P0-003 (Synthese 2026-07-12, verifiziert an 'Solar'/'Bonusaktionen'): zwei
    gleichnamige srd-de-Abschnitte werden in der Suche nicht verschmolzen; im Detail
    wird der AUSFUEHRLICHSTE Kernabschnitt geliefert (codex-Kriterium 'Kernabschnitt
    priorisieren'), die uebrigen bleiben als nachladbare weitere_abschnitte sichtbar -
    kein stilles Fragment, aber auch keine unnoetige Mehrdeutigkeit."""
    s = ns.foliant_suche_bestand("Reaktionen")
    reaktionen = [t for t in s["treffer"] if t["name_de"] == "Reaktionen"]
    assert len(reaktionen) == 2, reaktionen                 # beide Abschnitte sichtbar
    d = ns.foliant_hol_regel("Reaktionen")
    assert d["gefunden"] is True                            # Kernabschnitt geliefert
    assert "eine Reaktion pro Runde" in d["regeltext_md"]   # der laengere Spielregel-Text
    assert "Wertekasten" not in d["regeltext_md"]           # nicht die Meta-Erklaerung
    assert len(d.get("weitere_abschnitte", [])) == 1        # der andere bleibt nachladbar
    assert d["weitere_abschnitte"][0].get("eintrag_id")


def test_a3_fuzzy_brueckt_keine_dublette(bestand):
    """Nur fuzzy-nahe Glossar-Zeilen ('Eisstrahlen'-Plural) verschmelzen 'Eisstrahl' und
    'Ray of Frost' NICHT - beide bleiben eigenstaendige Treffer."""
    s = ns.foliant_suche_bestand("Eisstrahl")
    namen = {t["name_de"] or t["name_en"] for t in s["treffer"]}
    assert "Eisstrahl" in namen
    s_en = ns.foliant_suche_bestand("Ray of Frost")
    namen_en = {t["name_de"] or t["name_en"] for t in s_en["treffer"]}
    assert "Ray of Frost" in namen_en
    # und der englische Eintrag traegt NICHT ploetzlich den deutschen Namen:
    ray = next(t for t in s_en["treffer"] if (t["name_en"] or "") == "Ray of Frost")
    assert ray["name_de"] is None
