"""Errata und offizielle Regelauslegung: Quellen, die den Grundtext ERGAENZEN.

Beide sind kein Regeltext, sondern Nachtraege dazu - und genau daran haengt ihr ganzes
Verhalten im Bestand:

  * Sie duerfen den Grundtext NICHT ueberschreiben. Ein Erratum wird nie in `body_md`
    eingerechnet; es steht als eigene Quelle daneben. Sonst waere der Bestandstext nicht
    mehr der Buchtext, die Provenienz waere weg - und der korpusweite `inhalts_hash`
    (admin manifest) verschoebe sich bei jedem Errata-Update.
  * Sie duerfen den Grundtext NICHT verdraengen. Ein Erratum zu 'Fireball' heisst
    'Fireball' und traegt dieselbe Edition und Kategorie - es liefe damit unweigerlich in
    die Dublettengruppe des Grundtexts und verschwaende dort in `weitere_fassungen`, also
    aus der Trefferliste. Ein Modell saehe die Korrektur nie.
  * Sie duerfen aber auch nicht UNSICHTBAR sein: wer den korrigierten Text zitiert, muss
    die Korrektur mitbekommen. Deshalb stehen sie als eigene Treffer daneben, hinter dem
    Grundtext (Prioritaetsband 70) und mit eigener Kennzeichnung (📌 bzw. ⚖️).
"""
import sqlite3

import pytest

from app import db as adb
from app.tools import nachschlagen as ns
from app.tools import suche as su
from tests.hilfen import SCHEMA


@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    pfad = tmp_path / "foliant-revision.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet,"
        "inhaltsart) VALUES (?,?,?,?,?,?,?,?)",
        [("srd-de", "SRD 5.2.1", "de", "2024", "pdf", "CC-BY-4.0", 20, "regelwerk"),
         ("errata-phb-2024-en", "Player’s Handbook — Errata", "en", "2024", "pdf",
          "WotC (frei verteilt, keine offene Lizenz)", 70, "errata"),
         ("ddb-sac-en", "Sage Advice Compendium", "en", "2014", "ddb", "privat", 70,
          "regelauslegung")])
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [(1, "zauber", "Feuerball", None, "de", "2024", "139", "8W6 Feuerschaden."),
         # Das Erratum traegt den Namen der betroffenen Regel - nur so findet es, wer nach
         # der Regel sucht. Genau deshalb kollidiert es mit dem Grundtext.
         (2, "zauber", None, "Fireball", "en", "2024", "2",
          "Fireball (p. 275). The spell's damage is 8d6, not 6d6."),
         (3, "regel", None, "Fireball", "en", "2014", "12",
          "Q: Does Fireball ignite worn items? A: Only unattended objects.")])
    con.executemany(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle,seite) "
        "VALUES (?,?,?,?,?,?)",
        [("Fireball", "Feuerball", 1, "SRD 5.2.1", "2024", "139")])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def _treffer_2024(s):
    return [t for t in s["treffer"] if t["edition"] == "2024"]


def test_errata_verdraengt_den_grundtext_nicht(bestand):
    """Der Kernfall: Grundtext UND Erratum stehen nebeneinander in der Trefferliste -
    der Grundtext zuerst, das Erratum nie als kanonischer Sieger."""
    s = su.foliant_suche_bestand("Feuerball")
    kuerzel = [t["quelle_kuerzel"] for t in _treffer_2024(s)]
    assert "srd-de" in kuerzel, kuerzel
    assert "errata-phb-2024-en" in kuerzel, kuerzel
    assert kuerzel.index("srd-de") < kuerzel.index("errata-phb-2024-en"), kuerzel


def test_errata_verschwindet_nicht_in_weitere_fassungen(bestand):
    """Der eigentliche Fallstrick: als Gruppenmitglied waere das Erratum aus der
    Trefferliste verschwunden - sichtbar nur noch als Referenz am Grundtext. Die
    Glossar-Bruecke Feuerball<->Fireball haette es zuverlaessig dorthin gezogen."""
    s = su.foliant_suche_bestand("Feuerball")
    grundtext = next(t for t in _treffer_2024(s) if t["quelle_kuerzel"] == "srd-de")
    weitere = " ".join(grundtext.get("weitere_quellen") or [])
    assert "Errata" not in weitere, grundtext.get("weitere_quellen")
    d = ns.foliant_hol_eintrag("zauber", "Feuerball")
    fundstellen = [f["quelle"] for f in d.get("weitere_fundstellen", [])]
    assert "errata-phb-2024-en" not in fundstellen, fundstellen


def test_errata_traegt_seine_kennzeichnung(bestand):
    """Ohne Kennzeichnung waere ein Errata-Auszug fuer das Modell normaler Regeltext -
    dieselbe Luecke, die 2026 beim Abenteuerband auffiel (Zombie March, unmarkiert)."""
    s = su.foliant_suche_bestand("Feuerball")
    erratum = next(t for t in _treffer_2024(s)
                   if t["quelle_kuerzel"] == "errata-phb-2024-en")
    assert erratum["inhaltsart"] == "errata"
    hinweis = s.get("hinweis_inhaltsart") or ""
    assert "📌" in hinweis and "Korrektur" in hinweis, hinweis
    assert "🚫" not in hinweis, "Errata duerfen NICHT den Spoiler-Hinweis ausloesen"


def test_regelauslegung_traegt_ihre_kennzeichnung(bestand):
    """Sage Advice ist offiziell, aber kein Regelwortlaut - die Ausgabe muss das sagen,
    sonst wird eine Auslegung als Regelzitat weitergereicht."""
    d = ns.foliant_hol_eintrag("regel", "Fireball", edition="2014")
    assert d["gefunden"] is True
    assert d["inhaltsart"] == "regelauslegung"
    assert "⚖️" in d["hinweis_inhaltsart"]
    assert "KEIN Regeltext" in d["hinweis_inhaltsart"]


def test_detail_des_errata_sagt_was_es_ist(bestand):
    """Auch der Einzelabruf traegt die Kennzeichnung - nicht nur die Trefferliste."""
    s = su.foliant_suche_bestand("Feuerball")
    erratum = next(t for t in _treffer_2024(s)
                   if t["quelle_kuerzel"] == "errata-phb-2024-en")
    d = ns.foliant_hol_eintrag("zauber", eintrag_id=erratum["eintrag_id"])
    assert d["inhaltsart"] == "errata"
    assert d["hinweis_inhaltsart"].startswith("📌 Dieser Eintrag stammt aus")
    assert "Korrektur" in d["hinweis_inhaltsart"]


def test_grundtext_bleibt_unveraendert(bestand):
    """Kein stilles Einrechnen: der Bestandstext des Zaubers ist der BUCHTEXT, nicht der
    korrigierte. Die Korrektur steht daneben, nicht darin - sonst waere `body_md` nicht
    mehr das, was im Buch steht, und der korpusweite inhalts_hash verschoebe sich mit
    jedem Errata-Update."""
    d = ns.foliant_hol_eintrag("zauber", "Feuerball")
    assert d["regeltext_md"] == "8W6 Feuerschaden."
    assert "8d6" not in d["regeltext_md"]


def test_optionslisten_fuehren_keine_errata(bestand, monkeypatch):
    """Eine Optionsliste beantwortet "was kann ich WAEHLEN" - ein Erratum ist keine
    waehlbare Option, sondern eine Aussage ueber eine.

    Der Fall ist nicht theoretisch: Die Optionslisten haben eine EIGENE
    Zusammenfuehrung (charakter._varianten), nicht die Dubletten-Logik aus app/db.py.
    Ein Erratum zu 'Alert' heisst 'Alert' und verschmilzt dort als Namensvariante mit
    dem echten Talent - unsichtbar, solange sein Prioritaetsband hinter jedem Regelwerk
    liegt, und ein Korrektur-Fragment als Option, sobald das einmal nicht gilt."""
    import sqlite3 as _sq
    from app.tools import charakter as ch

    con = _sq.connect(bestand)
    qid = con.execute("SELECT id FROM quellen WHERE kuerzel='errata-phb-2024-en'").fetchone()[0]
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,"
                "edition,seite,body_md) VALUES (?,?,?,?,?,?,?,?)",
                (qid, "talent", None, "Alert", "en", "2024", "3",
                 "**Offizielle Korrektur zu S. 200 im Grundbuch.** Alert grants ..."))
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()

    r = ch.foliant_liste_optionen("talent")
    kuerzel = {t.get("quelle_kuerzel") for t in r.get("talente", [])}
    assert "errata-phb-2024-en" not in kuerzel, r.get("talente")


def test_optionslisten_laufen_auch_ohne_die_inhaltsart_spalte(tmp_path):
    """Der Serving-Pfad migriert nicht: eine Bestands-DB von vor der Migration kennt die
    Spalte nicht, auf die der neue Filter zugreift. Dann darf die Abfrage NICHT einfach
    scheitern - sonst waeren die Charakterbau-Listen dort schlagartig leer.

    Geprueft wird `_eintraege` direkt, nicht die fertige Liste: Das ist die Stelle, die
    den Filter traegt. Ob ein einzelner Eintrag danach als waehlbare OPTION gilt, haengt
    an seinem Breadcrumb (`_ist_option`) und ist eine andere Frage."""
    import sqlite3 as _sq
    from app import db as _adb
    from app.tools import charakter as ch

    pfad = tmp_path / "ohne-inhaltsart.sqlite"
    con = _sq.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    # Eine quellen-Tabelle ohne `inhaltsart` - genau so sah der Bestand vor der
    # v2-Migration aus (eine Spalte entfernen kann SQLite nur ueber einen Neuaufbau).
    con.executescript(
        "DROP TABLE quellen;"
        "CREATE TABLE quellen (id INTEGER PRIMARY KEY, kuerzel TEXT UNIQUE, titel TEXT,"
        " sprache TEXT, edition TEXT, herkunft TEXT, lizenz TEXT, prioritaet INTEGER,"
        " dateipfad TEXT);"
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,prioritaet)"
        " VALUES ('srd-de','SRD 5.2.1','de','2024','pdf',20);")
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,"
                "edition,seite,body_md) VALUES (1,'talent','Wachsam','Alert','de','2024',"
                "'200','Du bist wachsam.')")
    con.commit()
    con.close()

    c = _adb.connect_readonly(str(pfad))
    try:
        assert ch._eintraege(c, "talent"), (
            "Alt-DB ohne inhaltsart-Spalte liefert keine Eintraege mehr - der Rueckfall "
            "auf die ungefilterte Abfrage greift nicht")
    finally:
        c.close()


def test_errata_hinweis_verdraengt_den_spoilerschutz_nicht(tmp_path, monkeypatch):
    """Review-Befund 31.07.2026: Der Sammelhinweis fuer die NEBENLISTEN entfiel, sobald
    der Detail-Pfad schon einen Hinweis gesetzt hatte.

    Solange nur Abenteuerbaende gekennzeichnet wurden, war das folgenlos - es war
    derselbe Text. Mit Errata nicht mehr: Liefert der Detailabruf ein ERRATUM (📌) und
    steht in 'andere_fassungen' ein ABENTEUERBAND, fiel dessen 🚫 lautlos weg. Damit
    verschwand der Spoiler-Schutz - die OBERSTE Verhaltensregel - hinter einer
    Korrektur-Meldung."""
    con = sqlite3.connect(tmp_path / "t.sqlite")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet,"
        "inhaltsart) VALUES (?,?,?,?,?,?,?,?)",
        [("errata-phb", "PHB Errata", "en", "2024", "pdf", "WotC", 70, "errata"),
         ("cos-de", "Fluch des Strahd", "de", "2014", "pdf", "privat", 35,
          "abenteuer_setting")])
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,"
        "seite,body_md) VALUES (?,?,?,?,?,?,?,?)",
        [(1, "regel", None, "Vampire", "en", "2024", "2", "Korrektur zu Vampiren."),
         # Andere Edition -> landet als 'andere_fassungen' in der Nebenliste.
         (2, "regel", None, "Vampire", "de", "2014", "88", "Strahds Schloss: Gang ...")])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: tmp_path / "t.sqlite")

    d = ns.foliant_hol_eintrag("regel", "Vampire")
    assert d["quelle_kuerzel"] == "errata-phb"          # Vorbedingung: Erratum geliefert
    neben = d.get("andere_fassungen") or []
    assert any(n.get("inhaltsart") == "abenteuer_setting" for n in neben), neben
    hinweis = d.get("hinweis_inhaltsart") or ""
    assert "📌" in hinweis, "der praezisere Einzelhinweis muss stehen bleiben"
    assert "🚫" in hinweis, "der Spoiler-Hinweis der Nebenliste darf NICHT wegfallen"
