"""Committbare Renderer-Tests mit SYNTHETISCHER Vorlage (die echte DE-WotC-PDF ist
urheberrechtlich/gitignored). Getestet wird die deterministische Render-ENGINE:
Platzierung, Auto-Fit, code_map, Münz-/Tabellen-/Fortsetzungslogik, MediaBox, Seitenzahl,
Hintergrund-Erhalt. Die visuelle Abnahme auf der echten Vorlage ist ein privater Schritt.
"""
from __future__ import annotations

import fitz
import pytest

from app.charakterbogen import de_bogen
from app.charakterbogen.de_bogen import _fit_size, _gewicht_kg, _para, _saeubere, _umbrich, rendere
from app.charakterbogen.modelle import (
    Attribut, Ausruestung, Charakter, Fertigkeit, Gegenstand, Merkmal, UeText, Waffe, Zauber,
)

MEDIA = (603, 774)


def _synth_vorlage(marker: str = "HINTERGRUND-MARKER") -> bytes:
    """Leere 2-Seiten-Vorlage 603x774 mit einem Marker-Text (fuer Hintergrund-Erhalt)."""
    doc = fitz.open()
    for _ in range(2):
        p = doc.new_page(width=MEDIA[0], height=MEDIA[1])
        p.insert_text((300, 400), marker, fontname="helv", fontsize=8)
    return doc.tobytes()


def _mini_charakter() -> Charakter:
    c = Charakter()
    c.identitaet.name = "Sorin Vale"
    c.identitaet.klasse = UeText(en="Monk", art="term")
    c.identitaet.stufe = 5
    c.kampf.rk = 17
    c.kampf.trefferwuerfel = "5d8"
    c.kampf.uebungsbonus = "+3"
    c.attribute["dex"] = Attribut(wert=18, mod="+4", rettungswurf="+7", rettung_geuebt=True)
    c.fertigkeiten.append(Fertigkeit(schluessel="acrobatics", name=UeText(en="Acrobatics"),
                                     mod="+7", attribut="DEX", geuebt=True))
    c.angriffe.append(Waffe(name=UeText(en="Unarmed Strike"), angriffsbonus="+7",
                            schaden=UeText(en="1d8+4 Bludgeoning")))
    c.merkmale.append(Merkmal(name=UeText(en="Martial Arts"), quelle="PHB-2024", seite="101",
                              beschreibung=UeText(en="You gain benefits."), herkunft="klasse"))
    c.zauberwirken.zauber.append(Zauber(grad=2, name=UeText(en="Darkness"), zeitaufwand="1A",
                                        komponenten="V,M", wirkungsdauer=UeText(en="Concentration, up to 10 minutes")))
    c.ausruestung.muenzen = {"cp": 0, "sp": 0, "ep": 0, "gp": 80, "pp": 0}
    return c


def _text_von(pdf: bytes) -> str:
    doc = fitz.open(stream=pdf, filetype="pdf")
    return "\n".join(doc[i].get_text() for i in range(doc.page_count))


def _rendere_synth(c: Charakter, **kw) -> bytes:
    import os
    import tempfile
    # rendere erwartet einen Pfad; synthetische Vorlage in eine Temp-Datei legen
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(_synth_vorlage())
        pfad = f.name
    try:
        return rendere(c, template_pfad=pfad, **kw)
    finally:
        os.unlink(pfad)


# --- Struktur ----------------------------------------------------------------

def test_ausgabe_mediabox_und_seiten():
    pdf = _rendere_synth(_mini_charakter())
    doc = fitz.open(stream=pdf, filetype="pdf")
    assert doc.page_count == 2  # kleiner Charakter -> kein Überlauf, exakt 2 Seiten
    for i in range(doc.page_count):
        assert round(doc[i].rect.width) == MEDIA[0] and round(doc[i].rect.height) == MEDIA[1]


def test_hintergrund_bleibt_erhalten():
    pdf = _rendere_synth(_mini_charakter())
    assert "HINTERGRUND-MARKER" in _text_von(pdf)  # Vorlageninhalt nicht überschrieben


def test_werte_erscheinen():
    txt = _text_von(_rendere_synth(_mini_charakter()))
    for erwartet in ("Sorin Vale", "Monk", "5", "17", "5d8", "+3", "18", "+4", "+7",
                     "Unarmed Strike", "1d8+4 Bludgeoning", "Darkness", "80"):
        assert erwartet in txt, erwartet


def test_codemap_zeitaufwand():
    """'1A' muss als '1 Aktion' erscheinen, nicht roh (code_map, §7.3)."""
    txt = _text_von(_rendere_synth(_mini_charakter()))
    assert "1 Aktion" in txt


def test_zahlen_bleiben_zahlen():
    """RK/Stufe unverändert als Zahl gerendert (keine Übersetzung von Zahlen)."""
    txt = _text_von(_rendere_synth(_mini_charakter()))
    assert "17" in txt and "80" in txt


def test_uebersetzt_bevorzugt_de_vor_en():
    c = _mini_charakter()
    c.identitaet.klasse = UeText(en="Monk", de="Mönch (Monk)", art="term")
    txt = _text_von(_rendere_synth(c))
    assert "Mönch (Monk)" in txt


# --- Überlauf / Fortsetzungsseiten (KONZEPT §9) ------------------------------

def test_ueberlauf_erzeugt_fortsetzungsseite_ohne_verlust():
    c = _mini_charakter()
    marker = "EINZIGARTIGERUEBERLAUFMARKER"
    lang = ("Sehr langer Merkmalstext. " * 400) + marker  # sprengt die Klassenmerkmale-Box
    c.merkmale = [Merkmal(name=UeText(en="Riesenmerkmal"), quelle="PHB-2024", seite="1",
                          beschreibung=UeText(en=lang), herkunft="klasse")]
    pdf = _rendere_synth(c)
    doc = fitz.open(stream=pdf, filetype="pdf")
    assert doc.page_count > 2  # Anhangseite(n) angehängt
    voll = _text_von(pdf)
    assert "ANHANG" in voll                          # gemeinsame Anhang-Überschrift
    assert "Klassenmerkmale" in voll                 # Abschnitts-Zwischenüberschrift
    assert marker in voll                            # der Rest ist NICHT verloren


def test_viele_zauber_ueberlauf_in_fortsetzung():
    c = _mini_charakter()
    c.zauberwirken.zauber = [Zauber(grad=1, name=UeText(en=f"Zauber{i}"), zeitaufwand="1A")
                             for i in range(40)]  # mehr als Tabellenzeilen
    voll = _text_von(_rendere_synth(c))
    assert "Weitere Zauber" in voll
    assert "Zauber39" in voll  # letzter Zauber landet im Anhang, nicht verloren


# --- Kalibrierung ------------------------------------------------------------

def test_kalibrierung_zwei_seiten_mit_schluesseln():
    pdf = _rendere_synth(_mini_charakter(), kalibrierung=True)
    doc = fitz.open(stream=pdf, filetype="pdf")
    assert doc.page_count == 2  # Kalibrierung: keine Fortsetzung
    txt = _text_von(pdf)
    assert "klassenmerkmale" in txt and "name" in txt  # Feldschlüssel als Umriss-Label


# --- Determinismus -----------------------------------------------------------

def test_deterministischer_textinhalt():
    c = _mini_charakter()
    assert _text_von(_rendere_synth(c)) == _text_von(_rendere_synth(c))


# --- Text-Primitive (Units) --------------------------------------------------

def test_fit_size_verkleinert_bis_es_passt():
    # sehr breiter Text in schmale Box -> Größe sinkt
    assert _fit_size("Ein ziemlich langer Text", 30, 12, 6) < 12
    # kurzer Text -> Größe bleibt
    assert _fit_size("kurz", 200, 12, 6) == 12


def test_para_gibt_rest_bei_ueberlauf():
    doc = fitz.open()
    p = doc.new_page(width=MEDIA[0], height=MEDIA[1])
    kurz = _para(p, [50, 50, 200, 80], "Ein kurzer Satz.", 8, 6, (0, 0, 0))
    assert kurz == ""  # passt vollständig
    lang = _para(p, [50, 50, 120, 70], "Wort " * 200, 8, 6, (0, 0, 0))
    assert lang != ""  # Rest bleibt übrig (verlustfrei -> Fortsetzung)


def test_umbrich_bricht_an_wortgrenzen():
    zeilen = _umbrich("alpha beta gamma delta", 40, 8)
    assert len(zeilen) >= 2
    assert all("alphabeta" not in z for z in zeilen)  # keine verklebten Wörter


# --- Feinschliff-Fixes -------------------------------------------------------

def test_gewicht_lb_zu_kg():
    assert _gewicht_kg("5 lb.") == "2,3 kg"
    assert _gewicht_kg("1 lb.") == "0,5 kg"
    assert _gewicht_kg("ohne Einheit") == "ohne Einheit"
    assert _gewicht_kg(None) is None


def test_saeubere_typografische_zeichen():
    assert _saeubere("Monk’s Focus") == "Monk's Focus"   # U+2019 -> ' (rendert sonst als ·)
    assert _saeubere("a – b …") == "a - b ..."


def test_gewicht_metrisch_im_render():
    c = _mini_charakter()
    c.ausruestung.gegenstaende.append(Gegenstand(name=UeText(en="Rope", de="Seil"), menge="1", gewicht="5 lb."))
    txt = _text_von(_rendere_synth(c))
    assert "2,3 kg" in txt and "lb." not in txt


def test_aktionsoekonomie_wird_uebersetzt_gerendert():
    c = _mini_charakter()
    c.merkmale = [Merkmal(name=UeText(en="X", de="X"), beschreibung=UeText(en="b", de="b"),
                          herkunft="klasse",
                          aktionsoekonomie=[UeText(en="1 Reaction", de="1 Reaktion")])]
    txt = _text_von(_rendere_synth(c))
    assert "1 Reaktion" in txt and "1 Reaction" not in txt


def test_ueberlauf_reisst_nicht_mitten_im_absatz():
    """Regression: der Bogen endete real mit '...innerhalb von 18' und der Anhang begann mit
    'm sehen kannst' - der zeilenweise Schnitt trennte Zahl von Einheit. Der Ueberlauf muss
    ABSATZTREU sein (ganze Merkmale wandern) und einen Hinweis fuer den Leser hinterlassen."""
    import fitz
    from app.charakterbogen.de_bogen import FORTS_MARKE, _para

    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    a = "Erster Absatz. " * 12
    b = "Zweiter Absatz, der komplett wandern muss, weil er nicht mehr passt. " * 6
    rest = _para(page, [20, 20, 300, 60], f"{a}\n\n{b}", 8.5, 6, (0, 0, 0), endmarke=FORTS_MARKE)

    gezeichnet = page.get_text()
    assert rest, "Es muss ein Rest ueberlaufen"
    assert FORTS_MARKE in gezeichnet, "Der Leser braucht den Fortsetzungs-Hinweis"
    # Der Rest beginnt am ABSATZANFANG, nicht mitten im Satz:
    assert rest.startswith("Zweiter Absatz"), f"Rest reisst mitten im Absatz: {rest[:40]!r}"
    # und der zweite Absatz steht NICHT halb auf der Seite:
    assert "Zweiter Absatz" not in gezeichnet


def test_ueberlauf_eines_langen_merkmals_trennt_satztreu():
    """Ein EINZELNES Merkmal, das allein den Kasten sprengt, darf nicht mitten im Satz reissen
    (real: '...innerhalb von 18' | 'm sehen kannst'). Der Schnitt muss auf einem Satzende liegen."""
    import fitz
    from app.charakterbogen.de_bogen import FORTS_MARKE, _para

    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    lang = ("Du waehlst eine Kreatur, die du innerhalb von 18 Metern sehen kannst. "
            "Sie muss einen Rettungswurf bestehen. " * 8).strip()
    rest = _para(page, [20, 20, 300, 60], lang, 8.5, 6, (0, 0, 0), endmarke=FORTS_MARKE)

    assert rest, "Der lange Absatz muss ueberlaufen"
    gezeichnet = page.get_text().replace(FORTS_MARKE, "").strip()
    # Der gezeichnete Teil endet auf einem Satzzeichen, der Rest beginnt mit einem neuen Satz:
    assert gezeichnet.rstrip().endswith("."), f"Schnitt mitten im Satz: …{gezeichnet[-45:]!r}"
    assert rest[0].isupper(), f"Rest beginnt mitten im Satz: {rest[:45]!r}"
    assert "18" not in gezeichnet[-6:], "Zahl darf nicht von ihrer Einheit getrennt werden"
