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
        t = _text(ns.foliant_hol_gegenstand(name))
        assert klausel in t, (name, t[:200])
    z = _text(ns.foliant_hol_gegenstand("Zweihändig"))
    assert "zwei Händen" in z and "Rettungswurf" not in z


def test_golden_zauber_steckbriefe_repariert():
    """Eissturm/Göttliche Gunst/Symbol/Windwall waren Fragmente bzw. kreuzkontaminiert
    (codex DND-003)."""
    e = _text(ns.foliant_hol_zauber("Eissturm"))
    assert "Hagel" in e and "2W10" in e and "Fausthandschuh" in e
    g = _text(ns.foliant_hol_zauber("Göttliche Gunst"))
    assert "1W4" in g and "gleißenden Schaden" in g
    assert "Wunsch" not in g and "Konzentration" not in g      # 2024: KEINE Konzentration
    sy = _text(ns.foliant_hol_zauber("Symbol"))
    assert "Diamantpulver" in sy and "Glyphe" in sy
    ww = _text(ns.foliant_hol_zauber("Windwall"))
    assert "36 Meter" in ww and "Belagerungsmaschinen" in ww


def test_golden_monster_statbloecke_vollstaendig():
    """Solar/Vampirbrut lieferten Fragmente bzw. fremde Aktionen (codex TECH-002/DND-003);
    Aboleth-Kopf hatte Zellrisse (claude DND-004)."""
    s = _text(ns.foliant_hol_monster("Solar"))
    assert "297" in s and "RK" in s and "Bogen des Tötens" in s
    vb = _text(ns.foliant_hol_monster("Vampirbrut"))
    assert "90 (12W8+36)" in vb and "Spinnenklettern" in vb
    assert "Windstreich" not in vb                             # Pirscher-Aktionen raus
    pi = _text(ns.foliant_hol_monster("Unsichtbarer Pirscher"))
    assert "Windstreich" in pi and "Wirbel" in pi
    ab = _text(ns.foliant_hol_monster("Aboleth"))
    assert "20W10+40" in ab


def test_golden_zustaende_und_aktionen_direkt():
    """Klammerlose Kernbegriffe treffen den 2024-Eintrag direkt (SYN-P0-002) statt in
    Mehrdeutigkeit oder (bei gemischtem Bestand) auf 2014 zu laufen."""
    for begriff, klausel in (("Erschöpfung", "W20-Prüfungen"),
                             ("Verstecken", "SG-15"),
                             ("Gepackt", "Bewegungsrate beträgt 0")):
        d = ns.foliant_hol_regel(begriff)
        t = _text(d)
        assert klausel.replace("SG-15", "SG") in t, (begriff, t[:150])
        assert d["edition"] == "2024"


def test_golden_aktionen_ist_nie_reaktionen():
    """SYN-P0-001: 'Aktionen' darf weder als Uebersetzung noch im Detail bei
    'Reaktionen' landen."""
    u = ns.foliant_uebersetze_begriff("Aktionen")
    assert not any(b.get("term_de") == "Reaktionen" for b in u.get("begriffe", []))
    d = ns.foliant_hol_regel("Aktionen")
    if d.get("gefunden"):
        assert "Reaktion" not in (d.get("name_de") or "")
    else:                                                       # ehrliche Kandidaten ok
        namen = [k.get("name_de") for k in d.get("kandidaten", [])]
        assert d.get("mehrdeutig") and any("Aktion" in (n or "") for n in namen)


def test_golden_beeinflussen_und_attributswurf_getrennt():
    """codex DND-004: der Beeinflussen-SG (15/Intelligenzwert) darf nicht im
    allgemeinen Attributswurf-Glossareintrag stehen."""
    aw = _text(ns.foliant_hol_regel("Attributswurf"))
    assert "bereitwillig" not in aw
    be = _text(ns.foliant_hol_regel("Beeinflussen (Aktion)"))
    assert "Nicht bereitwillig" in be and "Zögerlich" in be


def test_golden_parameterfehler_ist_kein_leerbefund():
    """SYN-P0-006 am echten Bestand: vorhandener Inhalt + falscher Kategoriewert."""
    s = ns.foliant_suche_bestand("Feuerball", kategorie="spell")
    assert "fehler" in s and "Nichts im Bestand" not in s.get("hinweis", "")


def test_golden_open5e_trigger_und_referenzlauf():
    """SYN-P1-008 + SYN-P1-002 kombiniert: die Open5e-Fassung eines Reaktionszaubers
    traegt nach dem Formatter-Fix ihren Trigger UND ist vom kanonischen deutschen
    Treffer aus per eintrag_id gezielt nachladbar."""
    d = ns.foliant_hol_zauber("Counterspell")
    assert d["gefunden"] and d["quelle"] == "SRD 5.2.1 (Deutsch)"   # kanonisch: Deutsch
    fremde = d.get("fremdsprachige_fassungen") or []
    assert fremde, "Open5e-Fassung nicht als Referenz ausgewiesen"
    en = ns.foliant_hol_zauber("egal", eintrag_id=fremde[0]["eintrag_id"])
    assert en["gefunden"] and "Open5e" in en["quelle"]
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
        d = ns.foliant_hol_regel(name)
        assert d.get("gefunden"), (name, d.get("kandidaten"))
        assert klausel in d["regeltext_md"]
        # der Spielregel-Kernabschnitt, nicht die kurze Wertekasten-Meta-Erklaerung:
        assert "Elemente von Wertekästen" not in d["regeltext_md"]
        if d.get("weitere_abschnitte"):
            assert all("eintrag_id" in w for w in d["weitere_abschnitte"])
    # Todesrettungswurf: das Regelglossar fuehrt nur einen Verweis-Stub; der VOLLE
    # Abschnitt heisst 'Auf 0 Trefferpunkte sinken' und muss ueber die Suche sichtbar
    # sein (RAW-treu: das Glossar verweist mit 'Siehe auch').
    treffer = {t["name_de"] for t in ns.foliant_suche_bestand("Todesrettungswurf")["treffer"]}
    assert "Auf 0 Trefferpunkte sinken" in treffer
    voll = ns.foliant_hol_regel("Auf 0 Trefferpunkte sinken")
    assert "10" in voll["regeltext_md"] and "drei" in voll["regeltext_md"]


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
        s = ns.foliant_suche_bestand(begriff)
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
        d = ns.foliant_hol_regel(z)
        assert d.get("gefunden") and d["edition"] == "2024", (z, d.get("kandidaten"))
        assert "hinweis_alter_stand" not in d, z


def test_golden_struktur_filter_in_suche():
    """#3 (Finetuning 13.07.2026): der Struktur-Filter ist in foliant_suche_bestand gefaltet
    (kein eigenes Tool). Zauber (grad/schule/klasse/schadensart) UND Monster (hg/typ);
    Fehlwerte sind KEIN Leerbefund."""
    # Zauber: Grad-1-Feuerzauber des Hexenmeisters = Höllischer Tadel (Hellish Rebuke).
    r = ns.foliant_suche_bestand(grad=1, klasse="Hexenmeister", schadensart="feuer")
    assert r["treffer"] and all(t.get("kurzinfo") == "Grad 1" for t in r["treffer"]), r
    assert any("Tadel" in (t.get("name_de") or t.get("name_en") or "") for t in r["treffer"])
    # Monster: Feenwesen mit HG 1/4 -> u. a. der Goblinkrieger.
    m = ns.foliant_suche_bestand(hg="1/4", typ="Feenwesen")
    assert m["treffer"] and all(t.get("kurzinfo") == "HG 1/4" for t in m["treffer"]), m
    # Kombi Suchbegriff + Facette (UND): 'Feuerball' + grad=3 bleibt, grad=1 fällt raus.
    assert ns.foliant_suche_bestand("Feuerball", kategorie="zauber", grad=3)["treffer"]
    assert not ns.foliant_suche_bestand("Feuerball", kategorie="zauber", grad=1)["treffer"]
    # Guards -> strukturierter 'fehler', nie 'nicht im Bestand'.
    assert ns.foliant_suche_bestand().get("fehler") == "kein_kriterium"
    assert ns.foliant_suche_bestand(grad=1, typ="Untoter").get("fehler") \
        == "zauber_und_monster_filter_gemischt"
    ungueltig = ns.foliant_suche_bestand(schule="Zauberei")
    assert "fehler" in ungueltig and ungueltig.get("gueltige_schulen")


def test_golden_tippfehler_direkttreffer_statt_rauschen():
    """#1 (Finetuning 13.07.2026): ein eindeutiger (auch vertippter) Namenstreffer wird
    direkt geliefert - nicht als Mehrdeutigkeit mit blossen Body-Erwaehnungen (Schild,
    Zauberplaetze) verrauscht. Deutsch-first bleibt gewahrt."""
    d = ns.foliant_hol_zauber("Magic Missle")                  # Tippfehler: Missle
    assert d.get("gefunden") and not d.get("mehrdeutig"), d.get("kandidaten")
    assert d["quelle"] == "SRD 5.2.1 (Deutsch)"
    assert "Magic Missile" in d["anzeige_name"] and "Magisches Geschoss" in d["anzeige_name"]


def test_golden_suchtreffer_tragen_grad_und_hg():
    """#2 (Finetuning 13.07.2026): knappe Zauber-/Monster-Treffer tragen die
    Triage-Facette (Grad bzw. HG) aus dem Body."""
    s = ns.foliant_suche_bestand("Feuerball", kategorie="zauber")
    assert s["treffer"] and s["treffer"][0].get("kurzinfo", "").startswith("Grad"), s["treffer"][:1]
    m = ns.foliant_suche_bestand("Goblin", kategorie="monster")
    assert any((t.get("kurzinfo") or "").startswith("HG") for t in m["treffer"]), m["treffer"]
