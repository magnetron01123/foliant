"""Das Abkuerzungs-Register (config/abkuerzungen.py) und seine zwei Zusagen.

Abkuerzungen sind der Ort, an dem eine deutsche Auskunft am leisesten ins Englische
kippt: "AC 15", "8d6", "DC 14" liest sich in einem deutschen Satz unauffaellig und ist
trotzdem falsch, weil am Tisch ein Buch liegt, in dem RK, 8W6 und SG steht.

Zwei Richtungen, zwei verschiedene Zusagen:
  * AUSGABE  - eine Antwort kuerzt DEUTSCH ab. Nur belegte Formen (s. u.).
  * EINGABE  - eine Anfrage darf englisch abkuerzen ('Was ist die AC?') und muss trotzdem
               den deutschen Eintrag finden. Verstehen ja, schreiben nein.
"""
import re
import sqlite3

import pytest

from config import abkuerzungen as abk

_DB = "data/foliant.sqlite"


def test_jede_deutsche_abkuerzung_ist_eindeutig():
    """Zwei Begriffe unter derselben Abkuerzung waeren keine Abkuerzung mehr, sondern eine
    Mehrdeutigkeit - und die Ausgabe muesste raten, welche gemeint ist."""
    kuerzel = [k for k, _lang in abk.empfohlene_paare()]
    doppelt = {k for k in kuerzel if kuerzel.count(k) > 1}
    assert not doppelt, f"mehrfach vergeben: {doppelt}"


def test_englische_kuerzel_kollidieren_nicht_mit_deutschen():
    """Der reale Fall ist 'EP': deutsch Erfahrungspunkte, englisch Electrum Pieces. Die
    englische Lesart bleibt draussen - sonst uebersetzte 'EP' je nach Zeilenreihenfolge
    mal so, mal so. Wer eine weitere Kollision einbaut, soll hier stolpern."""
    deutsch = {k for k, _lang in abk.empfohlene_paare()}
    for engl, ziel in abk.englische_kuerzel():
        if engl in deutsch:
            eigenes = dict(abk.empfohlene_paare())[engl]
            assert eigenes == ziel, (
                f"'{engl}' bedeutet deutsch '{eigenes}', englisch aber '{ziel}' - "
                f"eine solche Kollision muss aufgeloest werden, nicht geseedet")


def test_wuerfel_sind_deutsch_notiert():
    """Die sichtbarste Stelle ueberhaupt: In jeder Schadenszeile steht ein Wuerfel. '8d6
    Feuerschaden' verraet eine englische Vorlage sofort."""
    for deutsch, englisch, _n in abk.WUERFEL:
        assert deutsch.startswith("W") and englisch.startswith("d")
        assert deutsch[1:] == englisch[1:], (deutsch, englisch)


def test_register_speist_das_glossar_in_beide_richtungen():
    """Das Register ist nur so viel wert, wie davon im Glossar landet - dort schlaegt der
    Server nach. Geprueft wird der Seeder, nicht die Datenbank: so gilt der Test auch
    ohne importierten Bestand."""
    from importer.import_glossar import ZUSATZ_ALIASSE, seed_abkuerzungen

    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE glossar (id INTEGER PRIMARY KEY, term_en TEXT NOT NULL, "
                "term_de TEXT NOT NULL, offiziell INTEGER NOT NULL, quelle TEXT, "
                "edition_quelle TEXT, seite TEXT)")
    con.execute("CREATE UNIQUE INDEX idx ON glossar(term_en, term_de)")
    seed_abkuerzungen(con)
    zeilen = {(r[0], r[1]) for r in con.execute("SELECT term_en, term_de FROM glossar")}
    con.close()

    for engl, ziel in abk.englische_kuerzel():          # Eingabe-Richtung
        assert (engl, ziel) in zeilen, f"englisches Kuerzel fehlt: {engl} -> {ziel}"
    for kurz, lang in abk.empfohlene_paare():           # Ausgabe-Richtung
        assert (kurz, lang) in zeilen, f"deutsches Kuerzel fehlt: {kurz} -> {lang}"
    for deutsch, englisch, _n in abk.WUERFEL:
        assert (englisch, deutsch) in zeilen, f"Wuerfel fehlt: {englisch} -> {deutsch}"
    for paar in ZUSATZ_ALIASSE:
        assert paar in zeilen, f"Zusatz-Alias fehlt: {paar}"


def test_verhaltensregel_nennt_die_deutschen_kuerzel():
    """Das Register allein aendert nichts an der ANTWORT - es macht die Kuerzel nur
    auffindbar. Dass eine Auskunft sie auch verwendet, steht in den Verhaltenskanaelen;
    faellt die Regel dort weg, kuerzt das Modell wieder englisch ab."""
    from config import stil

    for kanal, text in (("stil.py", stil.INSTRUCTIONS),
                        ("projektanweisung.md", stil.projektanweisung() or "")):
        for kurz in ("RK", "TP", "SG", "HG", "EP", "ÜB"):
            assert kurz in text, f"{kurz} fehlt in {kanal}"
        assert "STÄ" in text and "GES" in text, f"Attributs-Kuerzel fehlen in {kanal}"


# --------------------------------------------------------------------------- Beleg
# Ab hier gegen den ECHTEN Bestand: Ein Register, das Abkuerzungen behauptet, die das
# offizielle deutsche Buch nicht kennt, waere geraten (Regel 1). Ohne importierte
# Datenbank uebersprungen - wie tests/test_golden_bestand.py.

def _srd_de_text() -> str | None:
    try:
        con = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        zeilen = con.execute(
            "SELECT e.body_md FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
            "WHERE e.sprache = 'de' AND q.kuerzel = 'srd-de'").fetchall()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return "\n".join(r[0] for r in zeilen) or None


@pytest.mark.parametrize("kurz,lang,_en,erwartet",
                         abk.EMPFOHLEN, ids=[e[0] for e in abk.EMPFOHLEN])
def test_abkuerzung_ist_im_deutschen_srd_belegt(kurz, lang, _en, erwartet):
    """Jede empfohlene Abkuerzung muss im deutschen SRD 5.2.1 wirklich vorkommen - und
    zwar ungefaehr so oft, wie das Register behauptet.

    Die Zahl ist kein Selbstzweck: Sie ist der Beleg, dass die Abkuerzung dort GEBRAUCHT
    wird und nicht nur einmal in einer Fussnote steht. Faellt sie deutlich, hat sich der
    Bestand geaendert - dann gehoert das Register nachgezogen, nicht die Zahl."""
    text = _srd_de_text()
    if text is None:
        pytest.skip("kein importierter Bestand (data/foliant.sqlite)")
    n = len(re.findall(rf"\b{re.escape(kurz)}\b", text))
    assert n >= max(1, erwartet // 2), (
        f"'{kurz}' ({lang}) steht nur {n}x im deutschen SRD, erwartet ~{erwartet}")


def test_kein_englisches_kuerzel_schleicht_sich_als_deutsches_ein():
    """Gegenprobe zur Beleg-Pflicht: 'XP', 'CR' und 'PB' sind im deutschen SRD NICHT die
    gebraeuchliche Form - dort stehen EP, HG und ÜB. Genau diese drei standen bis zum
    31.07.2026 als einzige im Register, die deutschen fehlten."""
    text = _srd_de_text()
    if text is None:
        pytest.skip("kein importierter Bestand (data/foliant.sqlite)")
    deutsch = {k for k, _lang in abk.empfohlene_paare()}
    for englisch, deutsches_gegenstueck in (("XP", "EP"), ("CR", "HG"), ("PB", "ÜB")):
        assert englisch not in deutsch, f"'{englisch}' ist keine deutsche Abkuerzung"
        assert deutsches_gegenstueck in deutsch
        n_en = len(re.findall(rf"\b{englisch}\b", text))
        n_de = len(re.findall(rf"\b{deutsches_gegenstueck}\b", text))
        assert n_de > n_en, (
            f"'{englisch}' steht {n_en}x, '{deutsches_gegenstueck}' {n_de}x im dt. SRD")


# --------------------------------------------------------------- Alle drei Kanäle
# Davids Einwand (31.07.2026): "Ich gehe davon aus, dass leider nicht alle die
# Projektanweisung nutzen." Genau richtig - Kanal 2 muss jede Person selbst in ihr
# Claude-Projekt kopieren. Deshalb traegt die Regel auf allen drei Wegen, und der
# WICHTIGSTE davon ist der, den niemand einrichten muss: die Tool-Ausgabe.

def test_hinweis_kommt_bei_jeder_regelauskunft_mit():
    """Kanal 3, der einzige, den JEDE Antwort mitfuehrt (SPEC.md §7). Faellt er weg, haengt
    die Abkuerzungsregel daran, dass jemand die Projektanweisung eingerichtet hat."""
    from app.tools import ausgabe as aus

    hinweis = aus.HINWEIS_ABKUERZUNGEN
    for kurz in ("RK", "TP", "SG", "HG", "EP", "ÜB", "STÄ", "W20"):
        assert kurz in hinweis, f"{kurz} fehlt im Ausgabe-Hinweis"
    for englisch in ("AC", "HP", "DC", "d20"):
        assert englisch in hinweis, f"{englisch} fehlt (muss als 'nicht schreiben' dastehen)"
    assert "S12" in hinweis


def test_hinweis_wird_aus_dem_register_gebaut():
    """Nicht abgeschrieben: kommt eine Abkuerzung ins Register, steht sie auch im Hinweis.
    Eine Kopie liefe der Liste beim ersten Zuwachs davon."""
    from app.tools import ausgabe as aus

    quelltext = (aus._baue_abkuerzungs_hinweis.__code__.co_consts,)
    gebaut = aus._baue_abkuerzungs_hinweis()
    assert gebaut == aus.HINWEIS_ABKUERZUNGEN
    assert abk.EMPFOHLEN[0][0] in gebaut and abk.ATTRIBUTE[0][0] in gebaut


def test_tool_beschreibungen_nennen_die_regel():
    """Kanal 2 im MCP-Sinn: Die Tool-Beschreibungen liefert der Server mit dem Schema aus -
    jeder Client bekommt sie, ohne dass jemand etwas einrichtet."""
    from tests.test_verhaltensregeln import _tool_beschreibungen

    beschreibungen = _tool_beschreibungen()
    for werkzeug in ("foliant_suche_bestand", "foliant_hol_eintrag"):
        text = beschreibungen[werkzeug]
        assert "DEUTSCH" in text and "RK" in text, f"{werkzeug} nennt die Regel nicht"
    assert "Abkuerzungen" in beschreibungen["foliant_uebersetze_begriff"]


def test_englische_abkuerzung_im_regeltext_wird_aufgeloest():
    """Der praktische Fall: ein englischer Statblock ('AC 17', 'CR 10', '150 HP'). Ohne
    Aufloesung uebernimmt eine Antwort die englischen Kuerzel woertlich - sie fallen in
    einem deutschen Satz nicht auf.

    Die Erkennung ist schreibungsGENAU, und das ist die Sicherung: 'pp.' in einem
    Errata-Kopf darf nicht zur Platinmuenze werden."""
    from app import glossar as g
    from importer.import_glossar import seed_abkuerzungen

    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row          # wie die echten Verbindungen (app/db.connect)
    con.execute("CREATE TABLE glossar (id INTEGER PRIMARY KEY, term_en TEXT NOT NULL, "
                "term_de TEXT NOT NULL, offiziell INTEGER NOT NULL, quelle TEXT, "
                "edition_quelle TEXT, seite TEXT)")
    con.execute("CREATE UNIQUE INDEX idx ON glossar(term_en, term_de)")
    seed_abkuerzungen(con)
    con.commit()
    g.leere_cache()                        # sonst liest der Test einen fremden Bestand

    text = "Aboleth: AC 17, HP 150, CR 10 (5900 XP). Make a DC 14 STR save."
    treffer = {z["term_en"]: z["term_de"] for z in g.begriffe_im_text(con, text)}
    for kurz, erwartet in (("AC", "Rüstungsklasse"), ("HP", "Trefferpunkte"),
                           ("CR", "Herausforderungsgrad"), ("DC", "Schwierigkeitsgrad"),
                           ("XP", "Erfahrungspunkte"), ("STR", "Stärke")):
        assert treffer.get(kurz) == erwartet, (kurz, treffer.get(kurz))

    # Gegenprobe: kleingeschrieben darf NICHT anschlagen (ausser 'gp', s. ZUSATZ_ALIASSE)
    falle = "The backpack (pp. 27-28) has a clasp; accepting cp is fine."
    tr = {z["term_en"] for z in g.begriffe_im_text(con, falle)}
    assert "PP" not in tr and "CP" not in tr, tr
    con.close()
