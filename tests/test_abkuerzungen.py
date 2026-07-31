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
