"""Golden-Suite (SYN-P1-001): fachliche Realbestands-Regression gegen data/foliant.sqlite.

Anders als die Fixture-Tests prueft diese Suite den ECHTEN importierten Bestand - genau
die Ebene, auf der alle P0-Befunde der Reviews (2026-07-12) trotz gruener Struktur-Tests
unsichtbar blieben. Jeder Fall nennt erwartete Kernklauseln UND verbotene Fremdklauseln.
Laeuft nur, wenn die lokale Dev-DB existiert (wie tests/smoke_test.py); nach jedem
srd-de-Re-Import Pflicht (make test)."""
from pathlib import Path

import pytest

from app import db as adb

if not (Path(__file__).resolve().parent.parent / "data" / "foliant.sqlite").exists():
    pytest.skip("Golden-Suite braucht die echte Dev-DB (data/foliant.sqlite).",
                allow_module_level=True)

from app.tools import nachschlagen as ns  # noqa: E402  (nach dem Modul-Skip)
from app.tools import suche as su
from importer import namensreparatur as nr


def _text(d: dict) -> str:
    assert d.get("gefunden") is True, d.get("kandidaten") or d.get("hinweis")
    return d["regeltext_md"]


def test_golden_meisterschaften_vollstaendig():
    """Alle 8 Meisterschaftseigenschaften einzeln abrufbar; Umstoßen traegt den
    KON-Rettungswurf, Zweihändig NICHT (claude DND-001 / codex DND-004)."""
    erwartet = {"Auslaugen": "Nachteil", "Einkerben": "zusätzlichen Angriff",
                "Plagen": "im Vorteil", "Spalten": "zweite Kreatur",
                "Stoßen": "wegstoßen", "Streifen": "Attributsmodifikator",
                "Umstoßen": "Konstitutionsrettungswurf", "Verlangsamen": "Bewegungsrate"}
    for name, klausel in erwartet.items():
        t = _text(ns.foliant_hol_eintrag("gegenstand", name))
        assert klausel in t, (name, t[:200])
    z = _text(ns.foliant_hol_eintrag("gegenstand", "Zweihändig"))
    assert "zwei Händen" in z and "Rettungswurf" not in z


def test_golden_zauber_steckbriefe_repariert():
    """Eissturm/Göttliche Gunst/Symbol/Windwall waren Fragmente bzw. kreuzkontaminiert
    (codex DND-003)."""
    e = _text(ns.foliant_hol_eintrag("zauber", "Eissturm"))
    assert "Hagel" in e and "2W10" in e and "Fausthandschuh" in e
    g = _text(ns.foliant_hol_eintrag("zauber", "Göttliche Gunst"))
    assert "1W4" in g and "gleißenden Schaden" in g
    assert "Wunsch" not in g and "Konzentration" not in g      # 2024: KEINE Konzentration
    sy = _text(ns.foliant_hol_eintrag("zauber", "Symbol"))
    assert "Diamantpulver" in sy and "Glyphe" in sy
    ww = _text(ns.foliant_hol_eintrag("zauber", "Windwall"))
    assert "36 Meter" in ww and "Belagerungsmaschinen" in ww


def test_golden_monster_statbloecke_vollstaendig():
    """Solar/Vampirbrut lieferten Fragmente bzw. fremde Aktionen (codex TECH-002/DND-003);
    Aboleth-Kopf hatte Zellrisse (claude DND-004)."""
    s = _text(ns.foliant_hol_eintrag("monster", "Solar"))
    assert "297" in s and "RK" in s and "Bogen des Tötens" in s
    vb = _text(ns.foliant_hol_eintrag("monster", "Vampirbrut"))
    assert "90 (12W8+36)" in vb and "Spinnenklettern" in vb
    assert "Windstreich" not in vb                             # Pirscher-Aktionen raus
    pi = _text(ns.foliant_hol_eintrag("monster", "Unsichtbarer Pirscher"))
    assert "Windstreich" in pi and "Wirbel" in pi
    ab = _text(ns.foliant_hol_eintrag("monster", "Aboleth"))
    assert "20W10+40" in ab


def test_golden_zustaende_und_aktionen_direkt():
    """Klammerlose Kernbegriffe treffen den 2024-Eintrag direkt (SYN-P0-002) statt in
    Mehrdeutigkeit oder (bei gemischtem Bestand) auf 2014 zu laufen."""
    for begriff, klausel in (("Erschöpfung", "W20-Prüfungen"),
                             ("Verstecken", "SG-15"),
                             ("Gepackt", "Bewegungsrate beträgt 0")):
        d = ns.foliant_hol_eintrag("regel", begriff)
        t = _text(d)
        assert klausel.replace("SG-15", "SG") in t, (begriff, t[:150])
        assert d["edition"] == "2024"


def test_golden_aktionen_ist_nie_reaktionen():
    """SYN-P0-001: 'Aktionen' darf weder als Uebersetzung noch im Detail bei
    'Reaktionen' landen."""
    u = ns.foliant_uebersetze_begriff("Aktionen")
    assert not any(b.get("term_de") == "Reaktionen" for b in u.get("begriffe", []))
    d = ns.foliant_hol_eintrag("regel", "Aktionen")
    if d.get("gefunden"):
        assert "Reaktion" not in (d.get("name_de") or "")
    else:                                                       # ehrliche Kandidaten ok
        namen = [k.get("name_de") for k in d.get("kandidaten", [])]
        assert d.get("mehrdeutig") and any("Aktion" in (n or "") for n in namen)


def test_golden_beeinflussen_und_attributswurf_getrennt():
    """codex DND-004: der Beeinflussen-SG (15/Intelligenzwert) darf nicht im
    allgemeinen Attributswurf-Glossareintrag stehen."""
    aw = _text(ns.foliant_hol_eintrag("regel", "Attributswurf"))
    assert "bereitwillig" not in aw
    be = _text(ns.foliant_hol_eintrag("regel", "Beeinflussen (Aktion)"))
    assert "Nicht bereitwillig" in be and "Zögerlich" in be


def test_golden_parameterfehler_ist_kein_leerbefund():
    """SYN-P0-006 am echten Bestand: vorhandener Inhalt + falscher Kategoriewert."""
    s = su.foliant_suche_bestand("Feuerball", kategorie="spell")
    assert "fehler" in s and "Nichts im Bestand" not in s.get("hinweis", "")


def test_golden_open5e_trigger_und_referenzlauf():
    """SYN-P1-008 + SYN-P1-002 kombiniert: die Open5e-Fassung eines Reaktionszaubers
    traegt nach dem Formatter-Fix ihren Trigger UND ist vom kanonischen deutschen
    Treffer aus per eintrag_id gezielt nachladbar."""
    d = ns.foliant_hol_eintrag("zauber", "Counterspell")
    # Quellentitel = nur der Werktitel (Beschriftungs-Standard,
    # importer/quellen.py); Sprache und Regelversion stehen daneben.
    assert d["gefunden"] and d["quelle"] == "System Reference Document 5.2.1"   # kanonisch: Deutsch
    fremde = d.get("fremdsprachige_fassungen") or []
    assert fremde, "Open5e-Fassung nicht als Referenz ausgewiesen"
    # Am VOLLEN Korpus stehen neben Open5e auch DDB-Fremdfassungen in der Liste (nach
    # Quellen-Prioritaet, DDB vor Open5e) - die Open5e-Fassung gezielt heraussuchen statt
    # fremde[0] anzunehmen (das galt nur am Mac-Subset ohne DDB, korpusabhaengig).
    # Erkannt am WERKTITEL, nicht mehr am Bezugsweg: der stand frueher als "(Open5e)" im
    # Titel und steht seit dem Beschriftungs-Standard allein in `quellen.herkunft`.
    _OPEN5E_WERK = "System Reference Document 5.2"      # 5.2.1 ist die dt. Fassung
    open5e = next((f for f in fremde if (f.get("quelle") or "") == _OPEN5E_WERK), None)
    assert open5e, ("Open5e-Fassung nicht unter den Fremdfassungen", fremde)
    en = ns.foliant_hol_eintrag("zauber", "egal", eintrag_id=open5e["eintrag_id"])
    assert en["gefunden"] and en["quelle"] == _OPEN5E_WERK
    assert "reaction" in en["regeltext_md"].lower()
    assert "you see" in en["regeltext_md"] or "which you take" in en["regeltext_md"], \
        en["regeltext_md"][:200]                       # Trigger erhalten (B8)


def test_golden_gleichnamige_regelabschnitte_liefern_kernabschnitt():
    """SYN-P0-003 A7-Abnahme (codex DND-002): gleichnamige Same-Source-Abschnitte
    (Spielregel vs. Statblock-Meta vs. Glossar-Verweis) liefern den AUSFUEHRLICHSTEN
    Kernabschnitt - nicht ein Fragment und nicht bloss Mehrdeutigkeit; die uebrigen
    bleiben als weitere_abschnitte nachladbar."""
    for name, klausel in (("Bonusaktionen", "Bonusaktion"),
                          ("Reaktionen", "Reaktion"),
                          ("Temporäre Trefferpunkte", "Trefferpunkte")):
        d = ns.foliant_hol_eintrag("regel", name)
        assert d.get("gefunden"), (name, d.get("kandidaten"))
        assert klausel in d["regeltext_md"]
        # der Spielregel-Kernabschnitt, nicht die kurze Wertekasten-Meta-Erklaerung:
        assert "Elemente von Wertekästen" not in d["regeltext_md"]
        if d.get("weitere_abschnitte"):
            assert all("eintrag_id" in w for w in d["weitere_abschnitte"])
    # Todesrettungswurf: das Regelglossar fuehrt nur einen Verweis-Stub; der VOLLE
    # Abschnitt heisst 'Auf 0 Trefferpunkte sinken' und muss ueber die Suche sichtbar
    # sein (RAW-treu: das Glossar verweist mit 'Siehe auch').
    treffer = {t["name_de"] for t in su.foliant_suche_bestand("Todesrettungswurf")["treffer"]}
    assert "Auf 0 Trefferpunkte sinken" in treffer
    voll = ns.foliant_hol_eintrag("regel", "Auf 0 Trefferpunkte sinken")
    assert "10" in voll["regeltext_md"] and "drei" in voll["regeltext_md"]


def test_golden_deutsch_first_schlaegt_laengeren_fremdeintrag():
    """Regression Deutsch-first-Ranking (14.07.2026): ein exakter deutscher Namenstreffer
    aus deutscher Quelle schlaegt einen fremdsprachigen Treffer - AUCH wenn der englische
    Text laenger ist. Am vollen Korpus zog die EXAKTE Glossar-Bruecke 'Reactions'<->
    'Reaktionen' den laengeren englischen DDB-'Reactions'-Abschnitt in die same-source-
    Laengenwahl (SYN-P0-003) und verdraengte den srd-de-Kernabschnitt. Fix: die Laengenwahl
    vergleicht nur gleichnamige Abschnitte DERSELBEN Quelle; verschiedene QUELLEN entscheidet
    die Quellen-Prioritaet (Q2/S10). Am Mac-Subset (ohne DDB) haelt der Fall trivial - er
    beisst erst am vollen Korpus (Pi-Container-Golden-Lauf, s. CONCEPT.md §11)."""
    faelle = (("regel", "Reaktionen", "Reaktionen"),
              ("regel", "Bonusaktionen", "Bonusaktionen"),
              ("zauber", "Counterspell", "Gegenzauber"))
    for kategorie, begriff, name_de in faelle:
        d = ns.foliant_hol_eintrag(kategorie, begriff)
        assert d.get("gefunden"), (begriff, d.get("kandidaten"))
        # Der gewaehlte Haupttreffer ist die deutsche Quelle - nie der laengere Fremdeintrag.
        assert d["sprache"] == "de", (begriff, d["quelle"], d.get("name_en"))
        assert d["quelle"] == "System Reference Document 5.2.1", (begriff, d["quelle"])
        assert d["name_de"] == name_de, (begriff, d["name_de"])
        # Fremdsprachige Fassungen bleiben ausgewiesen (per eintrag_id ladbar), aber NIE
        # als Haupttreffer - und tauchen nie als Scheinkonflikt auf (Same-Source-Abschnitte
        # sind gesondert 'weitere_abschnitte').
        for f in d.get("fremdsprachige_fassungen") or []:
            assert f.get("sprache") != "de", (begriff, f)
    # Konkret 'Reaktionen': der srd-de-Spielregel-Kernabschnitt, nicht der engl. DDB-Text.
    r = ns.foliant_hol_eintrag("regel", "Reaktionen")
    assert "Certain special abilities" not in r["regeltext_md"], r["regeltext_md"][:120]
    assert "Bestimmte Spezialfähigkeiten" in r["regeltext_md"]


def test_golden_b6_findability_top3():
    """SYN-P1-006 B6-Abnahme: definierte Begriffsliste findet ihren Zieleintrag in den
    Top 3 - inkl. der Terminologie-Divergenz Waffenmeisterschaft/Waffenbeherrschung
    (claude DND-006) und der 2024-Neubegriffe."""
    faelle = {
        "Waffenmeisterschaft": "Meisterschaftseigenschaft",   # PHB-Begriff -> srd-de-Inhalt
        "weapon mastery": "Meisterschaftseigenschaft",
        "Ausströmung": "Ausströmung (Wirkungsbereich)",
        "emanation": "Ausströmung (Wirkungsbereich)",
        "Verstecken": "Verstecken (Aktion)",                  # die Aktion, nicht 'Hide Armor'
    }
    for begriff, ziel in faelle.items():
        s = su.foliant_suche_bestand(begriff)
        top3 = [t["name_de"] or t["name_en"] for t in s["treffer"][:3]]
        assert ziel in top3, (begriff, top3)
    # Die 8 Meisterschaftseigenschaften sind zweisprachig aufloesbar:
    for en, de in (("Cleave", "Spalten"), ("Vex", "Plagen"), ("Topple", "Umstoßen"),
                   ("Push", "Stoßen"), ("Sap", "Auslaugen")):
        u = ns.foliant_uebersetze_begriff(en)
        assert u.get("gefunden") and u["begriffe"][0]["term_de"] == de, (en, u)


def test_golden_alle_15_zustaende_klammerlos_2024():
    """SYN-P0-002 A3-Abnahme: alle 15 SRD-2024-Zustände lösen KLAMMERLOS auf den
    2024-Zustandseintrag auf (nicht auf eine 2014-Fassung, nicht in Mehrdeutigkeit)."""
    zustaende = ["Bewusstlos", "Betäubt", "Erschöpfung", "Gepackt", "Gelähmt",
                 "Verängstigt", "Bezaubert", "Unsichtbar", "Vergiftet", "Versteinert",
                 "Festgesetzt", "Blind", "Taub", "Liegend", "Kampfunfähig"]
    for z in zustaende:
        d = ns.foliant_hol_eintrag("regel", z)
        assert d.get("gefunden") and d["edition"] == "2024", (z, d.get("kandidaten"))
        assert "hinweis_alter_stand" not in d, z


def test_golden_struktur_filter_in_suche():
    """#3 (Finetuning 13.07.2026): der Struktur-Filter ist in foliant_suche_bestand gefaltet
    (kein eigenes Tool). Zauber (grad/schule/klasse/schadensart) UND Monster (hg/typ);
    Fehlwerte sind KEIN Leerbefund."""
    # Zauber: Grad-1-Feuerzauber des Hexenmeisters = Höllischer Tadel (Hellish Rebuke).
    r = su.foliant_suche_bestand(grad=1, klasse="Hexenmeister", schadensart="feuer")
    assert r["treffer"] and all(t.get("kurzinfo") == "Grad 1" for t in r["treffer"]), r
    assert any("Tadel" in (t.get("name_de") or t.get("name_en") or "") for t in r["treffer"])
    # Monster: Feenwesen mit HG 1/4 -> u. a. der Goblinkrieger.
    m = su.foliant_suche_bestand(hg="1/4", typ="Feenwesen")
    assert m["treffer"] and all(t.get("kurzinfo") == "HG 1/4" for t in m["treffer"]), m
    # Kombi Suchbegriff + Facette (UND): 'Feuerball' + grad=3 bleibt, grad=1 fällt raus.
    assert su.foliant_suche_bestand("Feuerball", kategorie="zauber", grad=3)["treffer"]
    assert not su.foliant_suche_bestand("Feuerball", kategorie="zauber", grad=1)["treffer"]
    # Guards -> strukturierter 'fehler', nie 'nicht im Bestand'.
    assert su.foliant_suche_bestand().get("fehler") == "kein_kriterium"
    assert su.foliant_suche_bestand(grad=1, typ="Untoter").get("fehler") \
        == "zauber_und_monster_filter_gemischt"
    ungueltig = su.foliant_suche_bestand(schule="Zauberei")
    assert "fehler" in ungueltig and ungueltig.get("gueltige_schulen")


def test_golden_tippfehler_direkttreffer_statt_rauschen():
    """#1 (Finetuning 13.07.2026): ein eindeutiger (auch vertippter) Namenstreffer wird
    direkt geliefert - nicht als Mehrdeutigkeit mit blossen Body-Erwaehnungen (Schild,
    Zauberplaetze) verrauscht. Deutsch-first bleibt gewahrt."""
    d = ns.foliant_hol_eintrag("zauber", "Magic Missle")                  # Tippfehler: Missle
    assert d.get("gefunden") and not d.get("mehrdeutig"), d.get("kandidaten")
    assert d["quelle"] == "System Reference Document 5.2.1"
    assert "Magic Missile" in d["anzeige_name"] and "Magisches Geschoss" in d["anzeige_name"]


def test_golden_monster_bruecke_strukturabgleich():
    """Monster-Dedup (13.07.2026): der Struktur-Abgleich (Typ+HG+RK+TP) paart dieselbe
    Kreatur ueber die deutsche und englische SRD-Fassung - authentisch, nicht geraten.
    Korrupte srd-de-Namen (PDF-Garble) werden NICHT als offizielle Bruecke geseedet."""
    from importer import import_glossar as ig
    con = adb.connect_readonly(str(adb.standard_pfad()))
    try:
        paare = {en: de for en, de, _k in ig._finde_monster_paare(con)}
    finally:
        con.close()
    # Struktur-identische Kreaturen werden korrekt gepaart:
    assert paare.get("Skeleton") == "Skelett"
    assert paare.get("Ape") == "Menschenaffe"
    assert paare.get("Blink Dog") == "Flimmerhund"
    # Kein korrupter deutscher Name in den Bruecken:
    assert all(nr.name_sauber(de) for de in paare.values()), \
        [de for de in paare.values() if not nr.name_sauber(de)]


def test_golden_suchtreffer_tragen_grad_und_hg():
    """#2 (Finetuning 13.07.2026): knappe Zauber-/Monster-Treffer tragen die
    Triage-Facette (Grad bzw. HG) aus dem Body."""
    s = su.foliant_suche_bestand("Feuerball", kategorie="zauber")
    assert s["treffer"] and s["treffer"][0].get("kurzinfo", "").startswith("Grad"), s["treffer"][:1]
    m = su.foliant_suche_bestand("Goblin", kategorie="monster")
    assert any((t.get("kurzinfo") or "").startswith("HG") for t in m["treffer"]), m["treffer"]


# ---------------------------------------------------------------------------------------
# ERRATA am echten Bestand (Datenbank-Audit 03.08.2026)
#
# Die Suite hatte bis dahin NULL Errata-Faelle: Der ganze Revisions-Layer war nur gegen
# Fixtures geprueft. Am Vollbestand haengt aber das, was Fixtures nicht nachstellen - die
# Glossar-Bruecke (alle 46 Errata-Zeilen tragen name_de = NULL, der deutsche Grundtext
# traegt name_en = NULL) und die Praezedenz gegen 17 andere Quellen.
# ---------------------------------------------------------------------------------------

def _errata_da() -> bool:
    con = adb.connect_readonly(str(adb.standard_pfad()))
    try:
        return bool(con.execute("SELECT 1 FROM quellen WHERE inhaltsart = 'errata'"
                                ).fetchone())
    finally:
        con.close()


golden_errata = pytest.mark.skipif(not _errata_da(),
                                   reason="keine Errata-Quelle in dieser Datenbank")


@golden_errata
def test_golden_errata_haengt_am_deutschen_grundtext():
    """Der Kernfall des Audits: Wer den deutschen Zauber laedt, erfaehrt von der
    englischen Korrektur. Ueber die Glossar-Bruecke Verwandlung<->Polymorph - ohne sie
    faende der Abgleich nur die zufaellig gleichlautenden Namen (Balor, Kraken)."""
    d = ns.foliant_hol_eintrag("zauber", "Verwandlung")
    revisionen = d.get("revisionen") or []
    assert [r["quelle_kuerzel"] for r in revisionen] == ["errata-phb-2024-en"], d.keys()
    assert "S. 306 im Grundbuch" in revisionen[0]["text_md"]
    assert "📌" in d["hinweis_revision"]
    # Der Grundtext bleibt der Grundtext - das Erratum ersetzt ihn nie.
    assert "Verwandlungszauber" in d["regeltext_md"]


@golden_errata
def test_golden_errata_ueberlebt_den_kategorie_filter():
    """Alle 43 Korrekturen tragen kategorie='regel'. Eine Suche mit kategorie='zauber'
    filterte sie deshalb heraus - samt 📌-Hinweis. Sie haengen jetzt als 'revisionen' an."""
    s = su.foliant_suche_bestand("Verwandlung", kategorie="zauber")
    assert "errata-phb-2024-en" not in [t["quelle_kuerzel"] for t in s["treffer"]]
    assert any(r["quelle_kuerzel"] == "errata-phb-2024-en"
               for r in s.get("revisionen", [])), s.get("revisionen")


@golden_errata
def test_golden_errata_steht_in_der_ungefilterten_suche_hinter_dem_grundtext():
    """Band 70: Die Korrektur steht NEBEN dem Grundtext, nie vor ihm - und verschwindet
    nicht in 'weitere_fassungen'."""
    s = su.foliant_suche_bestand("Polymorph")
    kuerzel = [t["quelle_kuerzel"] for t in s["treffer"]]
    assert "errata-phb-2024-en" in kuerzel, kuerzel
    assert kuerzel.index("srd-de") < kuerzel.index("errata-phb-2024-en"), kuerzel
    assert "📌" in s.get("hinweis_inhaltsart", "")


@golden_errata
def test_golden_errata_talent_und_monster():
    """Zwei weitere Kategorien, die je einen eigenen Bruecken-Weg nehmen: das Talent ueber
    das Glossar (Ringer<->Grappler), das Monster ueber den gleichlautenden Namen."""
    t = ns.foliant_hol_eintrag("talent", "Ringer")
    assert "Fast Wrestler" in (t.get("revisionen") or [{}])[0].get("text_md", ""), t.keys()
    m = ns.foliant_hol_eintrag("monster", "Balor")
    assert any("23d12" in r["text_md"] for r in m.get("revisionen", [])), m.keys()


@golden_errata
def test_golden_errata_liste_bleibt_frei_von_nachtraegen():
    """foliant_liste_optionen zeigt WAEHLBARE Optionen - ein Erratum ist keine."""
    from app.tools import charakter as ch
    optionen = ch.foliant_liste_optionen("talent")
    kuerzel = {o["quelle_kuerzel"] for o in optionen.get("talente", [])}
    assert not any(k.startswith("errata-") for k in kuerzel), kuerzel


def test_golden_bekannte_quellfehler_stehen_neben_dem_text():
    """Die zwei Druckfehler des deutschen SRD (config/quellfehler.py): Der Regeltext geht
    WOERTLICH raus, die belegte Korrektur steht daneben. Wer den Text still korrigierte,
    haette den Bestand vom Buch abgekoppelt."""
    d = ns.foliant_hol_eintrag("monster", "Balor")
    assert "23W12+161" in d["regeltext_md"], "der Quelltext wurde veraendert"
    assert "23W12+138" in d.get("hinweis_quellfehler", ""), d.keys()


def test_golden_zerrissene_statblock_werte_repariert():
    """Der Zellriss '**RK**1|3' liess vier Tiere mit einer unmoeglichen Ruestungsklasse 1
    im Bestand stehen, der Huegelriese mit einer TP-Formel, die 0,5 statt 105 ergab
    (Audit 03.08.2026, Sollwerte aus der englischen Fassung im Bestand belegt)."""
    for name, rk in (("Falke", 13), ("Pavian", 12), ("Skorpion", 11),
                     ("Wiesel", 13), ("Hügelriese", 13)):
        d = ns.foliant_hol_eintrag("monster", name)
        assert (d.get("facetten") or {}).get("rk") == rk, (name, d.get("facetten"))
    con = adb.connect_readonly(str(adb.standard_pfad()))
    try:
        zu_klein = con.execute("SELECT count(*) FROM monster_meta WHERE rk < 5").fetchone()[0]
    finally:
        con.close()
    assert zu_klein == 0, f"{zu_klein} Monster mit unmoeglicher Ruestungsklasse"


def test_golden_verschraenkte_statbloecke_entwirrt():
    """Zehn Monsterpaare des zweispaltigen srd-de-Drucks trugen den Statblock des jeweils
    anderen (Datenbank-Audit 03.08.2026). Der teuerste Fall: Wer 'Oktopus' nachschlug,
    bekam den Text des MAULTIERS, weil die Ueberschrift vor dem Rest des Vorgaengers
    stand und der Oktopus-Statblock hinten am 'Nashorn' hing.

    Die Sollwerte stammen NICHT aus dem Gedaechtnis, sondern aus der englischen Fassung
    im Bestand (open5e-srd-2024) - dieselbe Kreatur, dieselben Strukturwerte."""
    paare = {"Oktopus": "Octopus", "Nashorn": "Rhinoceros", "Dogge": "Mastiff",
             "Dachs": "Badger", "Elefant": "Elephant", "Elch": "Elk",
             "Rabenschwarm": "Swarm of Ravens", "Rabe": "Raven",
             "Riesenhyäne": "Giant Hyena", "Riesenhai": "Giant Shark",
             "Allosaurus": "Allosaurus", "Vampirbrut": "Vampire Spawn",
             "Vampir-Vertrauter": "Vampire Familiar", "Dschinni": "Djinni",
             "Hobgoblin-Hauptmann": "Hobgoblin Captain",
             # Der Sonderfall mit dem Dreier-Verschnitt: Gruftschrecken (Wight) und Grul
             # (Ghast) teilten sich zwei Eintraege, einer davon ganz ohne Werte.
             "Gruftschrecken": "Wight", "Grul": "Ghast"}
    con = adb.connect_readonly(str(adb.standard_pfad()))
    try:
        for deutsch, englisch in paare.items():
            soll = con.execute(
                "SELECT m.rk, m.tp FROM eintraege e JOIN monster_meta m ON m.eintrag_id = e.id "
                "JOIN quellen q ON q.id = e.quelle_id "
                "WHERE q.kuerzel = 'open5e-srd-2024' AND e.name_en = ?", (englisch,)).fetchone()
            if not soll:
                continue                       # nicht in jeder Datenbank vorhanden
            ist = con.execute(
                "SELECT m.rk, m.tp FROM eintraege e JOIN monster_meta m ON m.eintrag_id = e.id "
                "JOIN quellen q ON q.id = e.quelle_id "
                "WHERE q.kuerzel = 'srd-de' AND e.name_de = ?", (deutsch,)).fetchall()
            assert len(ist) == 1, f"{deutsch}: {len(ist)} Eintraege mit Statblock statt einem"
            assert tuple(ist[0]) == tuple(soll), (deutsch, englisch, tuple(ist[0]), tuple(soll))
        # Der Fremdtext ist weg: Im Oktopus darf kein Maultier mehr stehen.
        body, = con.execute(
            "SELECT e.body_md FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
            "WHERE q.kuerzel = 'srd-de' AND e.name_de = 'Oktopus'").fetchone()
        assert "Maultier" not in body and "Tentakel" in body, body[:200]
        # Und kein srd-de-Monster steht mehr ohne eigenen Statblock da.
        ohne = con.execute(
            "SELECT count(*) FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
            "LEFT JOIN monster_meta m ON m.eintrag_id = e.id "
            "WHERE q.kuerzel = 'srd-de' AND e.kategorie = 'monster' AND m.rk IS NULL"
        ).fetchone()[0]
        assert ohne == 0, f"{ohne} srd-de-Monster ohne Ruestungsklasse"
    finally:
        con.close()


# --- aus 👍-Rueckmeldungen der Runde (O4/M5) --------------------------------------------
# Was die Runde ausdruecklich gelobt hat, darf nicht unbemerkt kaputtgehen. Diese Faelle
# stammen NICHT aus einem Review, sondern aus dem Durchgang vom 11.08.2026 - Lob ist die
# einzige Quelle fuer die Frage, was schon stimmt (SPEC O4).

def test_golden_dunkelheit_traegt_alle_gelobten_werte():
    """👍 vom 10.08.2026 auf den Zauber Dunkelheit. Gelobt wurde, was aus dem Bestand kam:
    ein vollstaendiger Steckbrief. Genau daran haengen die Werte, die am Tisch zaehlen -
    Radius und Reichweite entscheiden, wer drinsteht, die Materialkomponente, ob man ihn
    ueberhaupt wirken kann."""
    t = _text(ns.foliant_hol_eintrag("zauber", "Dunkelheit"))
    for klausel in ("Hervorrufung", "2. Grade", "18 Meter", "4,5",
                    "Fledermausfell", "Konzentration", "Dunkelsicht"):
        assert klausel in t, (klausel, t[:300])


def test_golden_magieschmied_einstimmung_vier_und_sechs():
    """👍 vom 10.08.2026 auf die Einstimmungs-Grenzen des Magieschmieds. Die Antwort setzte
    ZWEI Merkmale zusammen (Stufe 10 und Stufe 18) - beide Zahlen muessen im Bestand
    stehen bleiben, sonst nennt die naechste Antwort nur die halbe Regel.

    Die Namen stehen in Versalien und ohne `name_de`, weil sie aus einem englischen
    Kampagnen-Band stammen; das ist der Normalfall fuer diese Quelle und kein Defekt."""
    vier = _text(ns.foliant_hol_eintrag("klasse", "LEVEL 10: MAGIC ITEM ADEPT"))
    sechs = _text(ns.foliant_hol_eintrag("klasse", "LEVEL 18: MAGIC ITEM MASTER"))
    assert "four magic items" in vier, vier[:200]
    assert "six magic items" in sechs, sechs[:200]
