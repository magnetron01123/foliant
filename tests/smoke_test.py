"""Smoke-Test ueber ALLE Tool-Kategorien mit Beispielausgabe (BP #9). Ergaenzt die formalen
Abnahmetests (§14): feuert jedes foliant_*-Tool gegen die ECHTE Datenbank (data/foliant.sqlite)
und druckt Samples - fuer die Import-Kontrolle (O3) nach jedem echten Import.
Zusaetzlich ein Deutsch-Term-Smoke (Foliants Kern). Aufruf:  python -m tests.smoke_test"""
from __future__ import annotations

import json
import sys

from app import db as adb
from app.tools import charakter as ch
from app.tools import nachschlagen as ns


def _drucke(titel: str, daten: dict, felder: list[str] | None = None) -> None:
    print(f"\n=== {titel} ===")
    if felder:
        daten = {k: v for k, v in daten.items() if k in felder}
    print(json.dumps(daten, ensure_ascii=False, indent=1)[:900])


def smoke_alle_tools() -> int:
    """Ruft jedes foliant_*-Tool einmal auf, druckt Beispielausgabe; inkl. Cross-Edition-
    Hinweis (aeltere_staende), falls beide Fassungen vorhanden. Rueckgabe: Fehlerzahl."""
    fehler = 0

    s = ns.foliant_suche_regeln("fireball")
    _drucke("foliant_suche_regeln('fireball')", s)
    if not s["treffer"]:
        print("!! Suche fand nichts - Bestand importiert?"); fehler += 1

    # Kernfall Deutsch-first (Regressionsfall 10.07.2026): deutscher Suchbegriff muss den
    # englischen Bestand ueber die Glossar-Bruecke treffen.
    for deutsch in ("Feuerball", "Gelegenheitsangriff"):
        sd = ns.foliant_suche_regeln(deutsch)
        kurz = [t["name_en"] or t["name_de"] for t in sd["treffer"][:3]]
        print(f"\n=== foliant_suche_regeln('{deutsch}') ===\n treffer={kurz} "
              f"suchweg={sd.get('hinweis_suchweg', 'direkt')}")
        if not sd["treffer"]:
            print(f"!! Deutscher Begriff '{deutsch}' fand nichts (Glossar geseedet?)"); fehler += 1

    d = ns.foliant_hol_zauber("Fireball")
    _drucke("foliant_hol_zauber('Fireball')", d,
            ["gefunden", "anzeige_name", "zitat", "edition", "hinweis_uebersetzung"])
    fehler += 0 if d.get("gefunden") else 1

    m = ns.foliant_hol_monster("Aboleth")
    _drucke("foliant_hol_monster('Aboleth')", m, ["gefunden", "anzeige_name", "zitat"])
    fehler += 0 if m.get("gefunden") else 1

    g = ns.foliant_hol_gegenstand("Battleaxe")
    _drucke("foliant_hol_gegenstand('Battleaxe')", g,
            ["gefunden", "anzeige_name", "zitat", "regeltext_md"])
    if g.get("gefunden") and "Mastery" not in g.get("regeltext_md", ""):
        print("!! Waffenmeisterschaft fehlt im Gegenstand (weapons-Merge kaputt?)"); fehler += 1
    fehler += 0 if g.get("gefunden") else 1

    u = ns.foliant_uebersetze_begriff("opportunity attack")
    _drucke("foliant_uebersetze_begriff('opportunity attack')", u)
    fehler += 0 if u.get("gefunden") else 1

    leer = ns.foliant_suche_regeln("Zzxqmbl Qwertzuiop Vhnjmklop")  # garantiert nicht im Bestand
    _drucke("Leersuche (Grounding-Hinweis, Kanal 3)", leer)
    if leer.get("treffer") or "hinweis" not in leer:
        print("!! Leersuche ohne Grounding-Hinweis"); fehler += 1
    return fehler


# Generische DDB-Kapitel-Titel, die NIE in einer Options-Liste stehen duerfen (QS 2026-07-11).
_LISTEN_JUNK = {"species", "species descriptions", "backgrounds", "background descriptions",
                "feats", "feat descriptions", "classes", "class descriptions", "spells",
                "spell descriptions", "magic items", "items", "equipment", "monsters",
                "creatures", "character creation", "character origins"}


def _junk_namen(liste: list[dict]) -> list[str]:
    """Kapitel-Header-Titel, die faelschlich als Option in einer Liste auftauchen."""
    treffer = set()
    for z in liste:
        for n in ((z.get("name_de") or "").lower(), (z.get("name_en") or "").lower()):
            if n in _LISTEN_JUNK:
                treffer.add(n)
    return sorted(treffer)


def smoke_charakter() -> int:
    """Phase 2 (F3/B7): Listen enthalten die SRD-Optionen und KEINEN Kapitel-Header-Muell,
    Details deutsch-first, Build-Pruefung erkennt Verstoesse und weist Luecken offen aus
    (T9/Q4). Robust gegen den Mehrquellen-Bestand: Teilmengen-Praesenz statt starrer Zahlen -
    DDB/Open5e duerfen Optionen ERGAENZEN, aber die SRD-Basis muss da und muellfrei sein."""
    fehler = 0

    k = ch.foliant_liste_klassen()
    SRD_KLASSEN = {"barbar", "barde", "druide", "hexenmeister", "kämpfer", "kleriker",
                   "magier", "mönch", "paladin", "schurke", "waldläufer", "zauberer"}
    vorhanden = {(z.get("name_de") or "").lower() for z in k["klassen"]}
    print(f"\n=== foliant_liste_klassen ===\n {len(k['klassen'])} Klassen")
    if SRD_KLASSEN - vorhanden:
        print(f"!! SRD-Klassen fehlen in der Liste: {sorted(SRD_KLASSEN - vorhanden)}"); fehler += 1
    if _junk_namen(k["klassen"]):
        print(f"!! Kapitel-Header als Klasse (Import-Filter kaputt?): {_junk_namen(k['klassen'])}")
        fehler += 1
    ohne_uk = [z["anzeige"] for z in k["klassen"]
               if (z.get("name_de") or "").lower() in SRD_KLASSEN and not z.get("unterklassen")]
    if ohne_uk:
        print(f"!! SRD-Klassen ohne Unterklasse: {ohne_uk}"); fehler += 1

    s = ch.foliant_liste_spezies()
    SRD_SPEZIES = {"elf", "zwerg", "gnom", "goliath", "halbling", "mensch", "ork",
                   "tiefling", "drachenblütiger"}
    sp_de = {(z.get("name_de") or "").lower() for z in s["spezies"]}
    print(f"=== foliant_liste_spezies ===\n {[z['anzeige'] for z in s['spezies']]}")
    if SRD_SPEZIES - sp_de:
        print(f"!! SRD-Spezies fehlen in der Liste: {sorted(SRD_SPEZIES - sp_de)}"); fehler += 1
    if _junk_namen(s["spezies"]):
        print(f"!! Kapitel-Header als Spezies (Import-Filter kaputt?): {_junk_namen(s['spezies'])}")
        fehler += 1

    h = ch.foliant_liste_hintergruende()
    t = ch.foliant_liste_talente()
    kategorien = {z.get("kategorie") for z in t["talente"]}
    print(f"=== hintergruende/talente ===\n {len(h['hintergruende'])} Hintergruende, "
          f"{len(t['talente'])} Talente, Kategorien: {sorted(str(k) for k in kategorien)}")
    h_de = {(z.get("name_de") or "").lower() for z in h["hintergruende"]}
    if {"akolyth", "soldat"} - h_de:                       # zwei sichere SRD-Hintergruende
        print(f"!! SRD-Hintergruende fehlen: {sorted({'akolyth', 'soldat'} - h_de)}"); fehler += 1
    if _junk_namen(h["hintergruende"]) or _junk_namen(t["talente"]):
        print(f"!! Kapitel-Header in Hintergrund/Talent-Liste: "
              f"{_junk_namen(h['hintergruende']) + _junk_namen(t['talente'])}"); fehler += 1
    if None in kategorien:
        print("!! Talente ohne Kategorie (Typzeile nicht geparst / Header-Stub?)"); fehler += 1

    d = ch.foliant_hol_klasse("Kämpfer")
    _drucke("foliant_hol_klasse('Kämpfer')", d,
            ["gefunden", "anzeige_name", "zitat", "verwandte_abschnitte"])
    fehler += 0 if d.get("gefunden") and d.get("verwandte_abschnitte") else 1
    d = ch.foliant_hol_spezies("Elf")
    print(f"\n=== foliant_hol_spezies('Elf') ===\n {d.get('anzeige_name')} | {d.get('zitat')}")
    if not (d.get("gefunden") and "Elfische Abstammungen" in d.get("regeltext_md", "")):
        print("!! Elf unvollstaendig (Abstammungs-Tabelle fehlt - Spezies-Merge kaputt?)")
        fehler += 1

    # Build-Pruefung: illegaler Unterklassen-Zeitpunkt MUSS auffallen; eine garantiert NICHT
    # im Bestand vorhandene Spezies MUSS ehrlich 'nicht_pruefbar' liefern (nicht raten, A5).
    b = ch.foliant_pruefe_build(klasse="Kämpfer", stufe=1, unterklasse="Champion",
                                hintergrund="Soldat", spezies="Nichtspezies-XYZ (Fixture)")
    statusse = {p["pruefung"]: p["status"] for p in b["pruefungen"]}
    print(f"\n=== foliant_pruefe_build (illegal: Unterklasse auf Stufe 1, Fantasiespezies) ===\n"
          f" ergebnis={b['ergebnis']} | unterklasse_stufe={statusse.get('unterklasse_stufe')}"
          f" | spezies={statusse.get('spezies')}")
    if b["ergebnis"] != "verstoesse_gefunden" \
            or statusse.get("unterklasse_stufe") != "verstoss" \
            or statusse.get("spezies") != "nicht_pruefbar":
        print("!! Build-Pruefung erkennt Verstoss/Luecke nicht (T9)"); fehler += 1
    return fehler


def smoke_detail_tools() -> int:
    """Deckt die restlichen Detail-Tools ab (BP #9: JEDES Tool einmal gegen echte Daten):
    hol_hintergrund, hol_talent, hol_regel, hol_attributswerte. Die Namen werden aus dem
    Bestand gezogen (robust gegen Import-Varianten), NICHT hartkodiert - ein Listeneintrag,
    der sich nicht per Detail-Tool abrufen laesst, ist ein echter Bruch (Liste<->Detail)."""
    import sqlite3
    fehler = 0

    h = ch.foliant_liste_hintergruende()
    if h.get("hintergruende"):
        name = h["hintergruende"][0].get("name_de") or h["hintergruende"][0].get("name_en")
        d = ch.foliant_hol_hintergrund(name)
        print(f"\n=== foliant_hol_hintergrund('{name}') ===\n {d.get('anzeige_name')} | {d.get('zitat')}")
        if not d.get("gefunden"):
            print(f"!! Hintergrund '{name}' aus der Liste nicht abrufbar (Liste<->Detail kaputt?)")
            fehler += 1

    t = ch.foliant_liste_talente()
    if t.get("talente"):
        name = t["talente"][0].get("name_de") or t["talente"][0].get("name_en")
        d = ch.foliant_hol_talent(name)
        print(f"=== foliant_hol_talent('{name}') ===\n {d.get('anzeige_name')} | {d.get('zitat')}")
        if not d.get("gefunden"):
            print(f"!! Talent '{name}' aus der Liste nicht abrufbar (Liste<->Detail kaputt?)")
            fehler += 1

    # hol_regel hat kein Listen-Tool -> einen echten 'regel'-Namen aus dem Bestand ziehen.
    con = sqlite3.connect(f"file:{adb.standard_pfad()}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT name_de, name_en FROM eintraege WHERE kategorie='regel' "
            "AND (name_de IS NOT NULL OR name_en IS NOT NULL) ORDER BY id LIMIT 1").fetchone()
    finally:
        con.close()
    if row:
        name = row[0] or row[1]
        d = ns.foliant_hol_regel(name)
        print(f"=== foliant_hol_regel('{name}') ===\n {d.get('anzeige_name')} | {d.get('zitat')}")
        if not d.get("gefunden"):
            print(f"!! Regel '{name}' aus dem Bestand nicht abrufbar (Detailabruf kaputt?)")
            fehler += 1
    else:
        print("=== foliant_hol_regel ===\n   keine 'regel'-Eintraege im Bestand")

    # hol_attributswerte: am Bestand belegt (B1/A5) - fehlt der Beleg, ist 'nicht verfuegbar'
    # ehrlich (kein Fehler), nur ein Hinweis auf eine fehlende importierte Regelquelle.
    for methode in ("standard_array", "point_buy"):
        a = ch.foliant_hol_attributswerte(methode)
        belegt = ("werte" in a) or ("budget" in a)
        print(f"=== foliant_hol_attributswerte('{methode}') ===\n verfuegbar={belegt}")
        if not belegt:
            print("   Hinweis: keine belegte 2024-Attributsregel im Bestand (ehrlich, kein Fehler).")
    return fehler


def smoke_srd_paare() -> int:
    """A9-Kuratierungs-Check: Jedes SRD_2024_BEGRIFFSPAAR, dessen EINE Seite im Bestand
    existiert, muss auch die ANDERE Seite finden (sonst Tippfehler in der Kuratierung).
    Noch nicht geseedete Paare sind KEIN Fehler - nur ein Hinweis mit Anleitung."""
    import sqlite3

    from app.glossar import norm_begriff
    from importer.import_glossar import SRD_2024_BEGRIFFSPAARE
    fehler = 0
    con = sqlite3.connect(f"file:{adb.standard_pfad()}?mode=ro", uri=True)
    try:
        # Kanonisch normalisiert vergleichen (norm_begriff): der Bestand kann NFD-Namen
        # tragen (bekannte_macken); Unterklassen zaehlen auch als Namens-SUFFIX
        # ('Barbaren-Unterklasse: Pfad des Berserkers').
        namen_en = {norm_begriff(r[0]) for r in con.execute(
            "SELECT DISTINCT name_en FROM eintraege WHERE name_en IS NOT NULL")}
        namen_de = set()
        for (n,) in con.execute(
                "SELECT DISTINCT name_de FROM eintraege WHERE name_de IS NOT NULL"):
            norm = norm_begriff(n)
            namen_de.add(norm)
            if "-unterklasse:" in norm:
                namen_de.add(norm.split("-unterklasse:", 1)[1].strip())
        geseedet = {(r[0], r[1]) for r in con.execute("SELECT term_en, term_de FROM glossar")}
        kaputt = [(en, de) for en, de in SRD_2024_BEGRIFFSPAARE
                  if (norm_begriff(en) in namen_en) != (norm_begriff(de) in namen_de)]
        fehlend = [(en, de) for en, de in SRD_2024_BEGRIFFSPAARE
                   if (en, de) not in geseedet]
        print(f"\n=== SRD-Begriffspaare === {len(SRD_2024_BEGRIFFSPAARE)} kuratiert, "
              f"{len(fehlend)} noch nicht geseedet")
        if kaputt:
            print(f"!! Paare mit nur EINER Bestandsseite (Kuratierungsfehler?): {kaputt}")
            fehler += len(kaputt)
        if fehlend:
            print(f"   -> zum Seeden: python -m app.admin import --quelle glossar "
                  f"(offline, Upsert; korrigiert auch A9-Editionen)")
    finally:
        con.close()
    return fehler


def smoke_deutsch_term() -> int:
    """Prueft an Beispielen: offizieller dt. Begriff OHNE '*'; inoffizieller MIT '*';
    Englisch immer in Klammern (S4/S5)."""
    fehler = 0
    for begriff, erwartet_offiziell in [("opportunity attack", True), ("grappled", True)]:
        u = ns.foliant_uebersetze_begriff(begriff)
        if not u.get("gefunden"):
            print(f"!! Glossar kennt '{begriff}' nicht - Glossar geseedet?"); fehler += 1
            continue
        b = u["begriffe"][0]
        klammer_ok = b["anzeige"].endswith(f"({b['term_en']})")
        stern_ok = ("*" not in b["anzeige"]) == b["offiziell"]
        print(f"  {b['anzeige']:<45} offiziell={b['offiziell']} klammer={klammer_ok} stern-logik={stern_ok}")
        fehler += 0 if (klammer_ok and stern_ok) else 1
        if erwartet_offiziell and not b["offiziell"]:
            print(f"  Hinweis: '{begriff}' ist im Bestand (noch) nicht offiziell belegt.")
    return fehler


if __name__ == "__main__":
    if not adb.standard_pfad().exists():
        sys.exit(f"DB fehlt ({adb.standard_pfad()}) - Smoke-Test braucht echte Daten.")
    probleme = (smoke_alle_tools() + smoke_deutsch_term() + smoke_charakter()
                + smoke_detail_tools() + smoke_srd_paare())
    print(f"\nSmoke-Test: {'OK' if probleme == 0 else f'{probleme} Problem(e)'}")
    sys.exit(0 if probleme == 0 else 1)
