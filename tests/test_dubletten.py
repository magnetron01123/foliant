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
from app.tools import suche as su
from tests.hilfen import SCHEMA

_SCHEMA = SCHEMA
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
         ("phb-2014-de", "Spielerhandbuch (2014)", "de", "2014", "pdf", "privat", 40),
         # Ein gedrucktes Buch, das denselben Zauber fuehrt und eine SEITE hat - der Fall,
         # an dem sich zeigt, ob die Fundstelle einer unterlegenen Quelle erhalten bleibt.
         # Apostroph typografisch wie ihn registriere_quelle schreibt (Beschriftungs-
         # Standard) - die Fixture soll den echten Bestand abbilden, nicht danebenliegen.
         ("ddb-phb-2024-en", "Player’s Handbook", "en", "2024", "ddb", "privat", 40)])
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [# Die fachliche Dublette: deutscher Eintrag OHNE name_en (realer PDF-Import)
         # + englischer Open5e-Eintrag; Bruecke NUR ueber die exakte Glossar-Zeile.
         (1, "zauber", "Feuerball", None, "de", "2024", "139", "8W6 Feuerschaden (deutsch)."),
         (2, "zauber", None, "Fireball", "en", "2024", None, "8d6 fire damage (english)."),
         # Dritte Fassung desselben Zaubers, MIT Seite - unterliegt der deutschen Quelle,
         # ihre Fundstelle soll trotzdem in der Antwort stehen.
         (4, "zauber", None, "Fireball", "en", "2024", "241", "8d6 fire damage (print)."),
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
        s = su.foliant_suche_bestand(suchbegriff)
        feuerbaelle = [t for t in _zauber_2024(s)
                       if (t["name_de"] or t["name_en"]) in ("Feuerball", "Fireball")]
        assert len(feuerbaelle) == 1, (suchbegriff, feuerbaelle)
        kanon = feuerbaelle[0]
        assert kanon["name_de"] == "Feuerball"            # kanonischer Text = prio 10
        assert kanon["name_en"] == "Fireball"             # Provenienz beider Namen
        assert kanon["quelle"] == "SRD 5.2.1 (Deutsch)"
        assert any("Open5e" in q for q in kanon.get("weitere_quellen", [])), kanon


def test_weitere_quellen_nennen_die_fundstelle(bestand):
    """Befund 30.07.2026: Die Seite der weggemergten Fassung lag in der DB und fiel aus
    der Antwort - eine Auskunft konnte nicht 'steht auch im Player's Handbook, S. 241'
    sagen, obwohl genau das den Wert eines gedruckten Buches ausmacht.

    Die harte Grenze aus Regel 1 wird mitgeprueft: Open5e fuehrt keine Seiten, also steht
    dort NUR der Titel - keine erfundene Zahl."""
    s = su.foliant_suche_bestand("Feuerball")
    kanon = next(t for t in _zauber_2024(s) if t["name_de"] == "Feuerball")
    weitere = kanon.get("weitere_quellen", [])
    assert "Player’s Handbook, S. 241" in weitere, weitere
    assert "SRD 5.2 (Open5e)" in weitere, weitere        # ohne Seite: nur der Titel
    assert not any("S. None" in q or "S. ," in q for q in weitere), weitere


def test_weitere_fassungen_fuehren_seite_und_kuerzel(bestand):
    """Die nachladbaren Fassungen tragen die Fundstelle als eigene Felder mit (nicht nur
    im Fliesstext): `seite` fuer den Beleg, `quelle` als Kuerzel fuer eine gezielte
    Nachsuche - der Titel allein taugt dafuer nicht, foliant_suche_bestand verlangt das
    Kuerzel.

    Ueber den NAMEN abgerufen, nicht per eintrag_id: die Fundstellen entstehen aus der
    Dublettengruppe, und die kennt nur dieser Weg. Ein Abruf per eintrag_id laedt bewusst
    genau EINE Fassung - dort waere eine Gruppenaussage falsch.

    Das Kuerzel heisst `quelle_kuerzel` wie ueberall in der Ausgabeschicht - nur unter
    diesem Namen findet die Inhaltsart-Kennzeichnung den Eintrag, und eine weggemergte
    Fassung kann aus einem Abenteuerband stammen (Review-Befund 31.07.2026)."""
    d = ns.foliant_hol_eintrag("zauber", "Feuerball")
    fassungen = {f["quelle_kuerzel"]: f for f in d.get("weitere_fundstellen", [])}
    assert fassungen["ddb-phb-2024-en"]["seite"] == "241"
    assert fassungen["open5e-srd-2024"]["seite"] is None   # keine geratene Seite
    assert "S. 241" in d["hinweis_fundstellen"] or "Bestand" in d["hinweis_fundstellen"]


def test_a3_aehnliche_zauber_bleiben_getrennt(bestand):
    """'Verzögerter Feuerball' ist KEINE Dublette von 'Feuerball' (kein Uebermerge)."""
    s = su.foliant_suche_bestand("Feuerball")
    namen = {t["name_de"] or t["name_en"] for t in _zauber_2024(s)}
    assert "Feuerball" in namen and "Verzögerter Feuerball" in namen


def test_a3_kategorien_bleiben_getrennt(bestand):
    """'Schild' als Zauber und als Gegenstand bleiben zwei Treffer (B4/T8)."""
    s = su.foliant_suche_bestand("Schild")
    kategorien = {t["kategorie"] for t in s["treffer"] if t["name_de"] == "Schild"}
    assert kategorien == {"zauber", "gegenstand"}


def test_a3_editionen_bleiben_getrennt(bestand):
    """Der 2014-Feuerball wird nie in den 2024-Treffer gemergt (V5)."""
    s = su.foliant_suche_bestand("Feuerball")
    assert all(t["edition"] == "2024" for t in s["treffer"])
    assert any(t["edition"] == "2014" for t in s.get("aeltere_staende", []))
    d = ns.foliant_hol_eintrag("zauber", "Feuerball", edition="2014")
    assert d["gefunden"] and "Alter 2014" in d["regeltext_md"]


def test_p0_gleichnamige_abschnitte_derselben_quelle_bleiben_getrennt(bestand):
    """SYN-P0-003 (Synthese 2026-07-12, verifiziert an 'Solar'/'Bonusaktionen'): zwei
    gleichnamige srd-de-Abschnitte werden in der Suche nicht verschmolzen; im Detail
    wird der AUSFUEHRLICHSTE Kernabschnitt geliefert (codex-Kriterium 'Kernabschnitt
    priorisieren'), die uebrigen bleiben als nachladbare weitere_abschnitte sichtbar -
    kein stilles Fragment, aber auch keine unnoetige Mehrdeutigkeit."""
    s = su.foliant_suche_bestand("Reaktionen")
    reaktionen = [t for t in s["treffer"] if t["name_de"] == "Reaktionen"]
    assert len(reaktionen) == 2, reaktionen                 # beide Abschnitte sichtbar
    d = ns.foliant_hol_eintrag("regel", "Reaktionen")
    assert d["gefunden"] is True                            # Kernabschnitt geliefert
    assert "eine Reaktion pro Runde" in d["regeltext_md"]   # der laengere Spielregel-Text
    assert "Wertekasten" not in d["regeltext_md"]           # nicht die Meta-Erklaerung
    assert len(d.get("weitere_abschnitte", [])) == 1        # der andere bleibt nachladbar
    assert d["weitere_abschnitte"][0].get("eintrag_id")


def test_a3_fuzzy_brueckt_keine_dublette(bestand):
    """Nur fuzzy-nahe Glossar-Zeilen ('Eisstrahlen'-Plural) verschmelzen 'Eisstrahl' und
    'Ray of Frost' NICHT - beide bleiben eigenstaendige Treffer."""
    s = su.foliant_suche_bestand("Eisstrahl")
    namen = {t["name_de"] or t["name_en"] for t in s["treffer"]}
    assert "Eisstrahl" in namen
    s_en = su.foliant_suche_bestand("Ray of Frost")
    namen_en = {t["name_de"] or t["name_en"] for t in s_en["treffer"]}
    assert "Ray of Frost" in namen_en
    # und der englische Eintrag traegt NICHT ploetzlich den deutschen Namen:
    ray = next(t for t in s_en["treffer"] if (t["name_en"] or "") == "Ray of Frost")
    assert ray["name_de"] is None


def test_identische_fassungen_derselben_quelle_werden_zusammengefasst(tmp_path, monkeypatch):
    """Bestandsprüfung 01.08.2026: Das Buch führt 'Ability Score Improvement' bei jeder
    Klasse einmal auf - zehnmal derselbe Absatz. Die Suche zeigte daraufhin acht
    gleichnamige Treffer mit identischem Auszug; im Bestand waren es 16 solcher Gruppen
    mit 30 überzähligen Einträgen, und sie trafen ausgerechnet die häufig gesuchten
    Klassenmerkmale.

    Das widerspricht SYN-P0-003 nicht, sondern schärft es: Dort ging es um Abschnitte mit
    VERSCHIEDENEM Inhalt, bei denen das Verschmelzen Text verschluckte. Hier ist der Text
    zeichengleich - verlieren kann man nichts. Die abweichenden FUNDSTELLEN bleiben."""
    pfad = tmp_path / "dubletten.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (id,kuerzel,titel,sprache,edition,herkunft,prioritaet)"
                " VALUES (1,'phb-2014-de','Spielerhandbuch','de','2014','pdf',80)")
    text = "*Kontext: Klassen*\n\nBeim Erreichen der 4. Stufe erhoehst du einen Attributswert."
    for seite in ("47", "64", "77", "85"):        # dasselbe Merkmal bei vier Klassen
        con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,"
                    "seite,body_md) VALUES (1,'regel','Attributswerterhoehung','de','2014',?,?)",
                    (seite, text))
    # Ein gleichnamiger Abschnitt mit ANDEREM Text muss eigenständig bleiben (SYN-P0-003)
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,seite,"
                "body_md) VALUES (1,'regel','Attributswerterhoehung','de','2014','300',?)",
                ("*Kontext: Anhang*\n\nKurzverweis im Regelglossar, anderer Wortlaut.",))
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)

    s = su.foliant_suche_bestand("Attributswerterhoehung", edition="2014")
    treffer = [t for t in s["treffer"] if t["name_de"] == "Attributswerterhoehung"]
    assert len(treffer) == 2, [t.get("seite") for t in treffer]   # 4 identische -> 1, plus 1 andere
    zusammengefasst = next(t for t in treffer if t["seite"] == "47")
    weitere = zusammengefasst.get("weitere_quellen") or []
    assert any("S. 64" in w for w in weitere), weitere            # Fundstellen bleiben
    assert any("S. 85" in w for w in weitere), weitere
