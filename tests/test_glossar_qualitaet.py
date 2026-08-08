"""Regressionstests A9 (Glossar: korrekte Edition + kanonische Auswahl) - offline,
mit gefakter dnddeutsch-Antwort (kein Netz, kein Cache)."""
import sqlite3
from pathlib import Path

import pytest

import importer.import_glossar as ig
from app import glossar as gl
from tests.hilfen import SCHEMA

_SCHEMA = SCHEMA
@pytest.fixture()
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "glossar.sqlite")
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA.read_text(encoding="utf-8"))
    yield c
    c.close()


def test_a9_ulisses_ist_nicht_automatisch_2024(con, monkeypatch):
    """Ein Ulisses-Begriff mit 2014-Buchbeleg (PHB(de)) wird NICHT als 2024 markiert;
    ohne sicheren Beleg bleibt die Edition unbekannt (NULL) - nichts wird geraten."""
    antworten = {
        "witch bolt": {"result": [{
            "name_en": "Witch Bolt", "name_de": "Hexenpfeil",
            "name_de_ulisses": "Hexenpfeil",
            "src_de": {"book": "PHB(de)", "book_long": "Spielerhandbuch (2014)", "p": "290"}}]},
        "weird begriff": {"result": [{
            "name_en": "Weird Begriff", "name_de": "Seltsamer Begriff",
            "name_de_ulisses": "Seltsamer Begriff", "src_de": {}}]},
        "community only": {"result": [{
            "name_en": "Community Only", "name_de": "Nur Community",
            "name_de_ulisses": "", "src_de": {}}]},
    }
    monkeypatch.setattr(ig, "_hole_api", lambda client, begriff: antworten[begriff])
    monkeypatch.setattr(ig, "_PAUSE_S", 0)

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    import httpx
    monkeypatch.setattr(httpx, "Client", lambda **kw: _FakeClient())
    ig.seed_glossar(con, list(antworten))

    zeilen = {r["term_en"]: r for r in con.execute("SELECT * FROM glossar")}
    assert zeilen["Witch Bolt"]["offiziell"] == 1
    assert zeilen["Witch Bolt"]["edition_quelle"] == "2014"        # nicht 2024!
    assert zeilen["Weird Begriff"]["offiziell"] == 1               # Ulisses = offiziell ...
    assert zeilen["Weird Begriff"]["edition_quelle"] is None       # ... Edition unbekannt
    assert zeilen["Community Only"]["offiziell"] == 0              # '*'-Fall (T3)


def test_a9_kanonische_auswahl_deterministisch(con):
    """Fuer einen englischen Begriff gewinnt: offiziell > neuere belegte Edition >
    unbekannte Edition > Community; Alphabet nur als letzter Determinismus-Anker."""
    con.executemany(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle,seite) "
        "VALUES (?,?,?,?,?,?)",
        [("Sample Term", "Alter Begriff", 1, "Spielerhandbuch (2014)", "2014", "10"),
         ("Sample Term", "Neuer Begriff", 1, "Spielerhandbuch 2024", "2024", "12"),
         ("Sample Term", "Unbekannt-Edition", 1, "Ulisses-Glossar (dnddeutsch.de)", None, None),
         ("Sample Term", "Aaa Community", 0, "dnddeutsch.de (Community)", None, None)])
    con.commit()
    zeilen = gl.nachschlagen(con, "Sample Term", richtung="en_de")
    assert [z["term_de"] for z in zeilen][:3] == \
        ["Neuer Begriff", "Alter Begriff", "Unbekannt-Edition"]
    assert zeilen[-1]["term_de"] == "Aaa Community"        # trotz Alphabet ganz hinten
    de, offiziell = gl.term_de(con, "Sample Term")
    assert (de, offiziell) == ("Neuer Begriff", True)      # S8: neuer offizieller gewinnt


def test_konflikt_klassen_trennen_edition_von_echtem_risiko(con):
    """Das Audit darf editionsgetrennte Mehrfachformen nicht als Risiko zaehlen: bei
    '2014 vs. 2024' entscheidet S8 eindeutig (und term_de liefert genau die 2024-Form).
    ECHT ist nur, was die Auswahlregel offen laesst - Homonyme oder gleiche Edition.
    Befund Pi-Seeding 26.07.2026: die Rohzahl sprang von 41 auf 47, obwohl jeder neue
    Fall korrekt aufgeloest wurde."""
    from app.admin import _teile_konflikte

    con.executemany(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
        "VALUES (?,?,?,?,?)",
        [# editionsgetrennt -> geregelt (der 2024-Begriff des dt. SRD gewinnt)
         ("Pouch", "Tasche", 1, "Spielerhandbuch", "2014"),
         ("Pouch", "Beutel", 1, "SRD 5.2.1 (Strukturabgleich Gegenstaende)", "2024"),
         # gleiche Edition, NICHT als Homonym belegt -> ECHTER Konflikt
         ("Shoggoth", "Schoggothe", 1, "Cthulhu Mythos", "2024"),
         ("Shoggoth", "Shoggothe", 1, "Buch der Bestien", "2024"),
         # gleiche Edition, ABER geprueftes Homonym -> weder echt noch geregelt
         ("Hide", "Fell", 1, "Spielerhandbuch 2024", "2024"),
         ("Hide", "Verstecken", 1, "SRD 5.2.1", "2024"),
         # ohne belegte Edition -> ECHTER Konflikt (nichts entscheidet)
         ("Scout", "Kundschafter", 1, "Community", None),
         ("Scout", "Spaeher", 1, "Community", None),
         # nur eine Form -> gar kein Konflikt
         ("Torch", "Fackel", 1, "SRD 5.2.1", "2024"),
         # Abkuerzungszeilen sind beabsichtigt und bleiben aussen vor
         ("Armor Class", "RK", 1, "abkuerzung", None),
         ("Armor Class", "Ruestungsklasse", 1, "SRD 5.2.1", "2024")])
    con.commit()

    echt, geregelt, homonyme = _teile_konflikte(con)
    assert {e["kandidat"] for e in echt} == {"Shoggoth", "Scout"}
    assert [g["kandidat"] for g in geregelt] == ["Pouch"]
    assert geregelt[0]["gewinner"] == "Beutel" and geregelt[0]["edition"] == "2024"
    assert [h["kandidat"] for h in homonyme] == ["Hide"]
    assert "Fell" in homonyme[0]["grund"]          # Begruendung wird mitgeliefert
    # Und die Anzeige bestaetigt, dass 'geregelt' wirklich geregelt ist (S8):
    assert gl.term_de(con, "Pouch") == ("Beutel", True)


def test_dritte_form_hebt_die_homonym_klaerung_auf(con):
    """Die Homonym-Liste ist ein BELEG, kein Deckel: sie gilt nur fuer exakt die geprueften
    Formen. Taucht eine dritte auf, ist der Fall ungeprueft und muss wieder als echter
    Konflikt erscheinen - sonst versteckt die Liste kuenftige Fehler."""
    from app.admin import _teile_konflikte

    con.executemany(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
        "VALUES (?,?,?,?,?)",
        [("Hide", "Fell", 1, "Spielerhandbuch 2024", "2024"),
         ("Hide", "Verstecken", 1, "SRD 5.2.1", "2024"),
         ("Hide", "Haut", 1, "Irgendein Drittanbieter", "2024")])
    con.commit()

    echt, _geregelt, homonyme = _teile_konflikte(con)
    assert [h["kandidat"] for h in homonyme] == [], "dritte Form darf nicht als geprueft gelten"
    assert {e["kandidat"] for e in echt} == {"Hide"}


def test_geprueftes_homonym_bleibt_von_kanonisierung_unberuehrt(con):
    """Gegenprobe zur Aufloesung: kanonisiere_konflikte darf ein Homonym NICHT demoten -
    beide Formen sind offiziell und muessen es bleiben."""
    con.executemany(
        "INSERT INTO glossar (term_en,term_de,offiziell,quelle,edition_quelle) "
        "VALUES (?,?,?,?,?)",
        [("Hide", "Fell", 1, "Spielerhandbuch 2024", "2024"),
         ("Hide", "Verstecken", 1, "SRD 5.2.1", "2024")])
    con.commit()

    from importer.import_glossar import kanonisiere_konflikte

    kanonisiere_konflikte(con)
    offizielle = {r[0] for r in con.execute(
        "SELECT term_de FROM glossar WHERE lower(term_en)='hide' AND offiziell=1")}
    assert offizielle == {"Fell", "Verstecken"}


def test_waffeneigenschaften_sind_offiziell_gepaart(con):
    """Review-Befund 08.08.2026: Die Langschwert-Auskunft schrieb „Vielseitig*" — der Stern
    behauptet „keine offizielle deutsche Übersetzung", dabei steht jede Waffeneigenschaft
    als eigener srd-de-Eintrag unter „Ausrüstung > Waffen > Eigenschaften". Ein falscher
    Stern ist eine falsche Aussage über den Bestand.

    Die acht Meisterschaftseigenschaften waren längst gepaart — die Waffeneigenschaften
    waren die vergessene Schwesterliste."""
    ig.seed_kern_singulare(con)
    con.commit()
    gl.leere_cache()
    for term_en, term_de in (("Versatile", "Vielseitig"), ("Finesse", "Finesse"),
                             ("Heavy", "Schwer"), ("Loading", "Laden"),
                             ("Ammunition", "Geschosse"), ("Thrown", "Wurfwaffe"),
                             ("Two-Handed", "Zweihändig"), ("Reach", "Weitreichend")):
        assert gl.term_de(con, term_en) == (term_de, True), term_en


def test_light_bleibt_der_zauber(con):
    """'Light' darf NICHT zusätzlich auf 'Leicht' zeigen: Das Glossar führt den Zauber
    Licht, und ein zweites Paar machte das Lemma mehrdeutig — `term_de` nähme die erste
    Zeile. Dieselbe Falle, die aus einem Errata-Verweis 'Fell (Hide)' machte."""
    paare = {(en, de) for en, de, _ed in ig.KERN_SINGULAR_PAARE}
    assert ("Light", "Leicht") not in paare
    assert not [de for en, de in paare if en == "Light"], "Light gehoert dem Zauber"


def test_statblock_lemmata_bleiben_aus_dem_inline_annotator(con):
    """'Reach' steht in JEDEM Statblock für die Reichweite eines Angriffs, nicht für die
    Waffeneigenschaft 'Weitreichend'; 'Heavy' trägt jede schwere Rüstung. Beide sind als
    Paar richtig und im Fließtext gefährlich — deshalb Homonym-Stopp: exakte Suche ja,
    Inline-Annotation nein."""
    ig.seed_kern_singulare(con)
    con.commit()
    gl.leere_cache()
    text = "Melee Attack Roll: +7, Reach 10 ft. The knight wears Heavy armor."
    gefunden = {z["term_en"] for z in gl.begriffe_im_text(con, text)}
    assert "Reach" not in gefunden and "Heavy" not in gefunden, gefunden
    # Die exakte Suche muss sie trotzdem aufloesen - dafuer stehen sie im Glossar:
    assert gl.term_de(con, "Reach") == ("Weitreichend", True)


def test_kurze_meisterschaftsnamen_erreichen_das_modell(con):
    """Review-Befund 08.08.2026: Die Langschwert-Auskunft erfand „Schwächung*" statt des
    amtlichen „Auslaugen" — obwohl das Paar Sap→Auslaugen seit jeher im Glossar steht.

    Ursache: `_MIN_LEMMA = 4` hält kurze englische Lemmata aus dem Inline-Annotator
    heraus (richtig für „Age", „Aid", „Cat", „Net") — und traf damit auch die
    dreibuchstabigen Meisterschaftseigenschaften Sap und Vex. Die Hürde bleibt, die zwei
    kuratierten Fachbegriffe sind die belegte Ausnahme."""
    ig.seed_kern_singulare(con)
    con.commit()
    gl.leere_cache()
    text = ("**Mastery — Sap.** If you hit a creature with this weapon, that creature has "
            "Disadvantage on its next attack roll. The Dagger has the Vex property.")
    gefunden = {z["term_en"]: z["term_de"] for z in gl.begriffe_im_text(con, text)}
    assert gefunden.get("Sap") == "Auslaugen", gefunden
    assert gefunden.get("Vex") == "Plagen", gefunden


def test_die_kurzhuerde_bleibt_fuer_alltagswoerter(con):
    """Die Ausnahme darf nicht zur Regel werden: 'Aid', 'Web' und Co. sind der Grund,
    warum es die Hürde überhaupt gibt."""
    for term_en, term_de in (("Aid", "Beistand"), ("Web", "Spinnennetz"),
                             ("Cat", "Katze")):
        ig._upsert(con, term_en, term_de, 1, "Spielerhandbuch", "2024", None)
    con.commit()
    gl.leere_cache()
    text = "The cat came to his aid, tangled in a web of lies."
    assert gl.begriffe_im_text(con, text) == []
