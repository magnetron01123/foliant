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
    # Würfelnotation erscheint DEUTSCH (5d8 -> 5W8, 1d8+4 -> 1W8+4): zentrale Normalisierung
    for erwartet in ("Sorin Vale", "Monk", "5", "17", "5W8", "+3", "18", "+4", "+7",
                     "Unarmed Strike", "1W8+4 Bludgeoning", "Darkness", "80"):
        assert erwartet in txt, erwartet
    assert "5d8" not in txt and "1d8" not in txt


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
    assert doc.page_count > 2                        # Fortsetzungsseite(n) eingefügt
    voll = _text_von(pdf)
    assert "ANHANG" not in voll                      # kein selbstgezeichneter Anhang mehr
    assert marker in voll                            # der Rest ist NICHT verloren
    # Jede Fortsetzungsseite ist eine KOPIE der leeren Vorlagenseite ...
    for i in range(doc.page_count):
        assert "HINTERGRUND-MARKER" in doc[i].get_text(), f"Seite {i} ist keine Vorlagen-Kopie"
    # ... und steht DIREKT hinter ihrer Ursprungsseite: die Original-Seite 2
    # (Zaubertabelle mit 'Darkness') rutscht ans Ende.
    assert "Darkness" in doc[doc.page_count - 1].get_text()


def test_viele_zauber_ueberlauf_in_fortsetzung():
    c = _mini_charakter()
    c.zauberwirken.zauber = [Zauber(grad=1, name=UeText(en=f"Zauber{i}"), zeitaufwand="1A")
                             for i in range(40)]  # mehr als Tabellenzeilen (30)
    pdf = _rendere_synth(c)
    doc = fitz.open(stream=pdf, filetype="pdf")
    assert doc.page_count == 3                       # Kopie von Seite 2 direkt hinter Seite 2
    assert "Zauber5" in doc[1].get_text()            # Tabellenanfang auf der Ursprungsseite
    assert "Zauber39" in doc[2].get_text()           # Rest als echte Tabellenzeilen, nicht verloren
    assert "ANHANG" not in _text_von(pdf)


def test_fortsetzungen_stehen_hinter_ihrer_ursprungsseite():
    """Überlauf auf Seite 1 UND Seite 2: Kopien stehen jeweils DIREKT hinter ihrer
    Ursprungsseite (S1, S1-Kopie(n), S2, S2-Kopie) - nicht gesammelt am Ende."""
    c = _mini_charakter()
    marker = "KLASSENUEBERLAUFMARKER"
    c.merkmale = [Merkmal(name=UeText(en="Riesenmerkmal"), quelle="PHB-2024", seite="1",
                          beschreibung=UeText(en=("Text. " * 2000) + marker), herkunft="klasse")]
    c.zauberwirken.zauber = [Zauber(grad=1, name=UeText(en=f"Zauber{i}"), zeitaufwand="1A")
                             for i in range(40)]
    doc = fitz.open(stream=_rendere_synth(c), filetype="pdf")
    texte = [doc[i].get_text() for i in range(doc.page_count)]
    s_merkmal_rest = next(i for i, t in enumerate(texte) if marker in t)
    s_zauber_start = next(i for i, t in enumerate(texte) if "Zauber0" in t)
    s_zauber_rest = next(i for i, t in enumerate(texte) if "Zauber39" in t)
    assert 1 <= s_merkmal_rest < s_zauber_start < s_zauber_rest


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

    from app.charakterbogen.de_bogen import _ohne_marker
    assert rest, "Der lange Absatz muss ueberlaufen"
    gezeichnet = page.get_text().replace(FORTS_MARKE, "").strip()
    # Der gezeichnete Teil endet auf einem Satzzeichen, der Rest beginnt mit einem neuen Satz:
    assert gezeichnet.rstrip().endswith("."), f"Schnitt mitten im Satz: …{gezeichnet[-45:]!r}"
    assert _ohne_marker(rest)[0].isupper(), f"Rest beginnt mitten im Satz: {rest[:45]!r}"
    assert "18" not in gezeichnet[-6:], "Zahl darf nicht von ihrer Einheit getrennt werden"


def test_fortsetzung_im_anhang_nennt_das_merkmal():
    """Reisst EIN Merkmal mitten durch, muss die Fortsetzung sagen, wozu sie gehoert -
    sonst steht dort ein herrenloser Textblock. Der Kopf ist FETT markiert (\\x01…\\x02)."""
    import fitz
    from app.charakterbogen.de_bogen import FORTS_MARKE, _fortsetzungskopf, _ohne_marker, _para

    kopf = _fortsetzungskopf("Angriffe abwehren* (Deflect Attacks) (PHB-2024 102).")
    assert _ohne_marker(kopf) == "Angriffe abwehren* (Deflect Attacks) (Fortsetzung):"
    assert kopf.startswith("\x01") and kopf.endswith("\x02")   # fett ausgezeichnet
    # kettenfaehig: ein vorhandenes '(Fortsetzung):' wird nicht verdoppelt
    assert _ohne_marker(_fortsetzungskopf(_ohne_marker(kopf) + " Wenn du den Schaden…")) == \
        "Angriffe abwehren* (Deflect Attacks) (Fortsetzung):"

    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    merkmal = ("Angriffe abwehren* (Deflect Attacks) (PHB-2024 102). "
               + "Du kannst eine Reaktion nutzen und den Schaden verringern. " * 8)
    rest = _para(page, [20, 20, 300, 60], merkmal, 8.5, 6, (0, 0, 0), endmarke=FORTS_MARKE)
    assert _ohne_marker(rest).startswith(
        "Angriffe abwehren* (Deflect Attacks) (Fortsetzung):"), rest[:70]


def test_fortsetzungsseite_nennt_merkmal_auch_bei_zeilen_split():
    """Bricht der Fluss an einer ZEILEN-Grenze mitten im Merkmal (mehrzeiliges Merkmal),
    traegt der Rest trotzdem den Merkmalskopf (Befund 16.07.2026: Seite 2 begann verwaist
    mit 'Wenn du den Schaden auf 0 reduzierst …')."""
    import fitz
    from app.charakterbogen.de_bogen import _ohne_marker, _para

    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    kopfzeile = "Angriffe abwehren* (Deflect Attacks) (PHB-2024 102). Erste Zeile."
    zeile2 = "· Zweite Zeile, die noch passt."
    zeile3 = "· Dritte Zeile, die in die Fortsetzung wandert."
    merkmal = "\n".join([kopfzeile, zeile2, zeile3])
    rest = _para(page, [20, 20, 320, 25], merkmal, 8.5, 8.5, (0, 0, 0))
    assert rest, "Es muss ein Rest ueberlaufen"
    assert _ohne_marker(rest).startswith(
        "Angriffe abwehren* (Deflect Attacks) (Fortsetzung): ·"), rest[:90]


# --- Rüstungsvertrautheit / K-R-M / Fußnote / Zauberwirken-Kopf ---------------

def test_ruestungs_schluessel_mapping():
    from app.charakterbogen.de_bogen import _ruestungs_schluessel
    assert _ruestungs_schluessel("Light Armor, Medium Armor, Shields") == \
        {"leicht", "mittelschwer", "schilde"}
    assert _ruestungs_schluessel("All Armor, Shields") == \
        {"leicht", "mittelschwer", "schwer", "schilde"}
    assert _ruestungs_schluessel("Heavy Armor") == {"schwer"}
    assert _ruestungs_schluessel("") == set()
    assert _ruestungs_schluessel("Padded") == set()   # nichts raten


def test_ruestungsmarken_werden_gezeichnet():
    c = _mini_charakter()
    ohne = fitz.open(stream=_rendere_synth(c), filetype="pdf")
    c.uebungen.ruestung.append(UeText(en="Light Armor, Shields", art="liste"))
    mit = fitz.open(stream=_rendere_synth(c), filetype="pdf")
    assert len(mit[0].get_drawings()) > len(ohne[0].get_drawings())


def test_ritual_marke_nur_bei_beleg():
    from app.charakterbogen.de_bogen import _ist_ritual
    assert _ist_ritual(Zauber(name=UeText(en="Detect Magic (Ritual)")))
    assert _ist_ritual(Zauber(name=UeText(en="Detect Magic"), notiz=UeText(en="(R), V/S")))
    assert not _ist_ritual(Zauber(name=UeText(en="Fireball")))
    assert not _ist_ritual(Zauber(name=UeText(en="Spiritual Weapon")))  # 'ritual' nur als Wort


def test_stern_fussnote_nur_wo_stern_vorkommt():
    from app.charakterbogen.de_bogen import _FUSSNOTE
    c = _mini_charakter()
    assert _FUSSNOTE not in _text_von(_rendere_synth(c))   # ohne '*' keine Fußnote
    c.identitaet.klasse = UeText(en="Monk", de="Mönch* (Monk)", art="term")
    doc = fitz.open(stream=_rendere_synth(c), filetype="pdf")
    assert _FUSSNOTE in doc[0].get_text()       # Seite mit '*' trägt die Erklärung
    assert _FUSSNOTE not in doc[1].get_text()   # Seite ohne '*' bleibt frei


def test_zauberwirken_kopf_erscheint():
    c = _mini_charakter()
    c.zauberwirken.attribut = UeText(en="Wisdom", de="Weisheit (Wisdom)", art="term")
    c.zauberwirken.modifikator = "+4"
    c.zauberwirken.rettungs_sg = "15"
    c.zauberwirken.angriffsbonus = "+7"
    txt = _text_von(_rendere_synth(c))
    assert "Weisheit (Wisdom)" in txt and "15" in txt


# --- Review-Runde 2 (16.07.2026): Fett, Größen, Überlauf-Stufen, Notation ------

def test_merkmalskopf_wird_fett_gerendert():
    """Merkmalsköpfe erscheinen in Helvetica-Bold vor der Erklärung (D&D-Beyond-Optik)."""
    pdf = _rendere_synth(_mini_charakter())
    doc = fitz.open(stream=pdf, filetype="pdf")
    spans = [s for b in doc[0].get_text("dict")["blocks"]
             for l in b.get("lines", []) for s in l.get("spans", [])]
    fette = [s["text"] for s in spans if "Bold" in s["font"]]
    assert any("Martial Arts" in t for t in fette), fette


def test_grossbox_spalten_eine_schriftgroesse():
    """2-spaltige Kästen fitten EINE Größe über beide Spalten (kein Schriftgrad-Sprung)."""
    c = _mini_charakter()
    lang = "Merkmalstext hat hier viele Worte und noch mehr. " * 14
    c.merkmale = [Merkmal(name=UeText(en=f"Merkmal{i}"), beschreibung=UeText(en=lang),
                          herkunft="klasse") for i in range(3)]
    pdf = _rendere_synth(c)
    doc = fitz.open(stream=pdf, filetype="pdf")
    import app.charakterbogen.de_bogen as db
    box = db.lade_layout()["grossbox"]["klassenmerkmale"]["rect"]
    groessen = {round(s["size"], 1) for b in doc[0].get_text("dict")["blocks"]
                for l in b.get("lines", []) for s in l.get("spans", [])
                if box[0] - 1 <= l["bbox"][0] and l["bbox"][2] <= box[2] + 2
                and box[1] - 1 <= l["bbox"][1] and l["bbox"][3] <= box[3] + 3
                and "HINTERGRUND-MARKER" not in s["text"]}
    assert len(groessen) == 1, groessen


def test_einzeiler_bleibt_in_der_box():
    """Überlange Einzeiler: §5-Klammer opfern, dann stauchen - nie über die Boxgrenze."""
    c = _mini_charakter()
    c.identitaet.unterklasse = UeText(en="Warrior of Shadow",
                                      de="Krieger des Schattens* (Warrior of Shadow)",
                                      art="term")
    pdf = _rendere_synth(c)
    doc = fitz.open(stream=pdf, filetype="pdf")
    import app.charakterbogen.de_bogen as db
    rect = db.lade_layout()["felder"]["identitaet.unterklasse"]["rect"]
    im_feld = [w for w in doc[0].get_text("words")
               if rect[0] - 1 <= w[0] <= rect[2] and rect[1] - 3 <= w[1] <= rect[3] + 3]
    assert im_feld, "Unterklasse muss gerendert sein"
    assert max(w[2] for w in im_feld) <= rect[2] + 0.6, im_feld
    # Stufe 2 griff: die §5-Klammer '(Warrior of Shadow)' wurde geopfert, der Stern bleibt
    assert any(w[4] == "Schattens*" for w in im_feld)
    assert not any("Warrior" in w[4] for w in im_feld)


def test_zauber_notiz_wird_eingedeutscht():
    from app.charakterbogen.de_bogen import _normalisiere_notiz
    assert _normalisiere_notiz("D: 1 Min, V/S") == "WD: 1 Min, V/G"
    assert _normalisiere_notiz("D: 10 Min, 4,5 m Kugel, S/M") == "WD: 10 Min, 4,5 m Kugel, G/M"
    assert _normalisiere_notiz("D: 1 Min, V/S/M") == "WD: 1 Min, V/G/M"


def test_saeubere_quotes_wuerfel_streupunkt():
    assert _saeubere("„Wille des Schattens“") == '"Wille des Schattens"'
    assert _saeubere("5d8 und 1d10+9, d20") == "5W8 und 1W10+9, W20"
    assert _saeubere("(+2 / +1) ·]") == "(+2 / +1)]"


def test_traglast_erscheint_in_ausruestung():
    c = _mini_charakter()
    c.ausruestung.getragenes_gewicht = "17 lb."
    c.ausruestung.belastet_ab = "120 lb."
    txt = _text_von(_rendere_synth(c))
    assert "Traglast:" in txt and "7,7 kg" in txt and "54,4" in txt   # kg kann umbrechen


def test_sinne_erscheinen_auf_dem_bogen():
    c = _mini_charakter()
    c.kampf.sinne = UeText(en="Darkvision 60 ft.", de="Dunkelsicht 18 m")
    txt = _text_von(_rendere_synth(c))
    assert "Dunkelsicht 18 m" in txt


def test_fortsetzungs_kopie_traegt_charakternamen():
    """Die Vorlagen-Kopie ist einem Charakter zuzuordnen (Name/Klasse/Stufe im Kopf)."""
    c = _mini_charakter()
    c.merkmale = [Merkmal(name=UeText(en="Riesenmerkmal"), quelle="PHB-2024", seite="1",
                          beschreibung=UeText(en="Sehr langer Text. " * 600), herkunft="klasse")]
    doc = fitz.open(stream=_rendere_synth(c), filetype="pdf")
    assert doc.page_count > 2
    assert "Sorin Vale" in doc[1].get_text()   # Kopie direkt hinter Seite 1


# --- Review-Runde 4 (17.07.2026): Kurzfassung (nur Merkmal-Namen) -------------

def _charakter_mit_merkmalen() -> Charakter:
    # Einwort-Marker statt Mehrwort-Phrasen: get_text() bricht Zeilen mit '\n' um, eine
    # Mehrwort-Phrase kann dabei ueber zwei Zeilen zerrissen werden (falsches Testsignal).
    c = _mini_charakter()
    c.merkmale = [
        Merkmal(name=UeText(en="Martial Arts"), quelle="PHB-2024", seite="101",
               beschreibung=UeText(en="Erklaerungstext KLASSENMARKIERUNG."), herkunft="klasse"),
        Merkmal(name=UeText(en="Darkvision"), quelle="PHB-2024", seite="194",
               beschreibung=UeText(en="Erklaerungstext SPEZIESMARKIERUNG."), herkunft="spezies"),
        Merkmal(name=UeText(en="Grappler"), quelle="PHB-2024", seite="204",
               beschreibung=UeText(en="Erklaerungstext TALENTMARKIERUNG."), herkunft="talent"),
    ]
    return c


def test_kurzfassung_listet_nur_namen_ohne_erklaerung():
    c = _charakter_mit_merkmalen()
    voll = _text_von(_rendere_synth(c))
    kurz = _text_von(_rendere_synth(c, kurzfassung=True))
    for name in ("Martial Arts", "Darkvision", "Grappler"):
        assert name in voll and name in kurz
    for marker in ("KLASSENMARKIERUNG", "SPEZIESMARKIERUNG", "TALENTMARKIERUNG"):
        assert marker in voll
        assert marker not in kurz


def test_kurzfassung_namen_nicht_fett():
    """Volle Fassung: Merkmalskopf ist fett. Kurzfassung: reiner Listeneintrag, nicht fett -
    es gibt nichts mehr, wovon sich der Name fett absetzen müsste."""
    c = _charakter_mit_merkmalen()

    def _fette_texte(pdf: bytes) -> list[str]:
        doc = fitz.open(stream=pdf, filetype="pdf")
        spans = [s for i in range(doc.page_count) for b in doc[i].get_text("dict")["blocks"]
                for l in b.get("lines", []) for s in l.get("spans", [])]
        return [s["text"] for s in spans if "Bold" in s["font"]]

    fette_voll = _fette_texte(_rendere_synth(c))
    fette_kurz = _fette_texte(_rendere_synth(c, kurzfassung=True))
    assert any("Martial Arts" in t for t in fette_voll), fette_voll
    assert not any("Martial Arts" in t for t in fette_kurz), fette_kurz


def test_kurzfassung_veraendert_uebrige_boxen_nicht():
    """Nur Klassenmerkmale/Spezies-Merkmale/Talente werden gekürzt - Ausrüstung, Geschichte,
    Sprachen usw. bleiben unveraendert (KONZEPT: die Übersetzung bleibt wie gehabt)."""
    c = _mini_charakter()
    c.ausruestung.gegenstaende.append(Gegenstand(name=UeText(en="Rope"), menge="1", gewicht="5 lb."))
    voll = _text_von(_rendere_synth(c))
    kurz = _text_von(_rendere_synth(c, kurzfassung=True))
    for erwartet in ("Rope", "2,3 kg", "Sorin Vale", "Darkness"):
        assert erwartet in voll and erwartet in kurz
