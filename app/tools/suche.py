"""Die Bestandssuche: foliant_suche_bestand und alles, was NUR sie braucht.

Freitext ODER Struktur-Filter ODER beides. Der Struktur-Pfad (kein Suchbegriff, nur
Facetten) ist der Grund fuer den halben Umfang dieser Datei: Grad, Schule, Klasse,
Schadensart, Herausforderungsgrad und Typ muessen validiert, kanonisiert, in einen
SQL-Vorfilter uebersetzt und danach am Text nachgefiltert werden.

Warum eine eigene Datei (30.07.2026): nachschlagen.py trug Suche UND Detailabruf in
1429 Zeilen. Beide Pfade beruehren einander an genau EINER Stelle - der Namensrelevanz -,
und die liegt seit demselben Tag in app/glossar.py, wo auch ihre Schwelle (FUZZY_NAME)
und die Normalisierung wohnen. Danach war der Schnitt sauber.

Die Ausgabeform kommt aus app/tools/ausgabe.py, die Namensrelevanz aus app/glossar.py -
diese Datei entscheidet nur, WAS gefunden wird, nicht wie es aussieht.
"""
from __future__ import annotations

import re
import sqlite3
import time

from app import db as _db
from app.db import Kategorie
from app import facetten as _facetten
from app import glossar as _glossar
from app import protokoll as _protokoll
from app.tools.ausgabe import (
    _HINWEIS_PARAMETER, HINWEIS_ABKUERZUNGEN, HINWEIS_ALT, HINWEIS_KOPFZEILE, HINWEIS_DB_FEHLT, markiere_mehrdeutige_treffer, HINWEIS_LEER, _haenge_revisionen_an, _knapp, _markiere_inhaltsart, _reichere_facetten_an,
    _verbinde, markiere_unuebersetzte,
)


# Herausforderungsgrad, wie die Statbloecke ihn fuehren: ganze Zahl oder Bruch.
_HG_FORMAT = re.compile(r"\d+(?:/\d+)?")

def _facetten_vorbereiten(kategorie, grad, schule, klasse, schadensart, hg, typ):
    """Validiert die STRUKTUR-Filter und baut ein Praedikat body->bool (fuer #3, in die
    Suche gefaltet). Liefert (praedikat|None, kategorie|None, echo, fehler_antwort|None).
    Zauber-Facetten (grad/schule/klasse/schadensart) und Monster-Facetten (hg/typ) sind
    kategoriegebunden und nicht mischbar. Ungueltige Werte -> strukturierter 'fehler'."""
    z_aktiv = grad is not None or bool(schule) or bool(klasse) or bool(schadensart)
    m_aktiv = bool(hg) or bool(typ)
    if not z_aktiv and not m_aktiv:
        return None, None, {}, None
    if z_aktiv and m_aktiv:
        return None, None, {}, {"treffer": [], "fehler": "zauber_und_monster_filter_gemischt",
                "hinweis": "Zauber-Facetten (grad/schule/klasse/schadensart) und Monster-"
                           "Facetten (hg/typ) getrennt anfragen - eine Kategorie pro Suche."}
    implizit = "zauber" if z_aktiv else "monster"
    if kategorie and kategorie != implizit:
        return None, None, {}, {"treffer": [], "fehler": "kategorie_passt_nicht_zu_filter",
                "hinweis": f"Die gesetzten Filter gehoeren zu kategorie='{implizit}', nicht "
                           f"'{kategorie}'. KEIN 'nicht im Bestand' (B1/B4)."}
    echo: dict = {}
    schule_key = schaden_key = typ_key = None
    if grad is not None:
        if not (0 <= int(grad) <= 9):
            return None, None, {}, {"treffer": [], "fehler": "grad_ausserhalb_0_9",
                    "hinweis": "grad ist 0 (Zaubertrick) bis 9. KEIN 'nicht im Bestand'."}
        echo["grad"] = int(grad)
    if schule:
        schule_key = _facetten.schule_schluessel(schule)
        if not schule_key:
            return None, None, {}, {"treffer": [], "fehler": f"unbekannte Schule {schule!r}",
                    "gueltige_schulen": _facetten.schulen_anzeige(),
                    "hinweis": "Gueltige Schule aus 'gueltige_schulen' nutzen (B1/B4)."}
        echo["schule"] = _facetten.schule_anzeige(schule_key)
    if klasse:
        # Befund 30.07.2026: klasse war nach hg der LETZTE ungepruefte Facetten-Parameter.
        # 'Quatschklasse' erzeugte keinen Parameterfehler, sondern einen ehrlich
        # klingenden Nulltreffer - dieselbe Antwortklasse, gegen die SYN-P0-006 antrat.
        # Der Wert wird kanonisiert (DE/EN), aber im echo bleibt die Nutzereingabe stehen,
        # damit die Filterzeile zeigt, wonach der Nutzer gefragt hat.
        if _facetten._klasse_kanon(klasse) not in _facetten._KANON_KLASSEN:
            return None, None, {}, {
                "treffer": [], "fehler": f"unbekannte Klasse {klasse!r}",
                "gueltige_klassen": _facetten.klassen_anzeige(),
                "hinweis": "Gueltige Klasse aus 'gueltige_klassen' nutzen (deutsch oder "
                           "englisch). Ungueltiger PARAMETER - das ist KEIN 'nicht im "
                           "Bestand' (B1/B4)."}
        echo["klasse"] = klasse
    if schadensart:
        schaden_key = _facetten.schadensart_schluessel(schadensart)
        if not schaden_key:
            return None, None, {}, {"treffer": [], "fehler": f"unbekannte Schadensart {schadensart!r}",
                    "gueltige_schadensarten": _facetten.schadensarten_anzeige(),
                    "hinweis": "Gueltige Schadensart aus 'gueltige_schadensarten' nutzen."}
        echo["schadensart"] = schaden_key
    if hg:
        # Befund 30.07.2026: hg ging als EINZIGER Facetten-Parameter ungeprueft durch,
        # waehrend schule, schadensart und typ einen strukturierten Fehler liefern.
        # 'abc' erzeugte deshalb keinen Parameterfehler, sondern einen ehrlich klingenden
        # Nulltreffer ("Kein Eintrag passt auf ALLE Filter") - genau die Antwortklasse,
        # gegen die SYN-P0-006 angetreten ist. Erlaubt ist der Herausforderungsgrad als
        # ganze Zahl oder Bruch, wie ihn die Statbloecke fuehren ('1', '1/4', '0').
        hg_text = str(hg).strip()
        if not _HG_FORMAT.fullmatch(hg_text):
            return None, None, {}, {
                "treffer": [], "fehler": f"unbekannter Herausforderungsgrad {hg!r}",
                "hinweis": "hg ist der Herausforderungsgrad als ganze Zahl oder Bruch, "
                           "z. B. '0', '1', '1/4', '1/2'. Ungueltiger PARAMETER - das ist "
                           "KEIN 'nicht im Bestand' (B1/B4)."}
        echo["hg"] = hg_text
    if typ:
        typ_key = _facetten.typ_schluessel(typ)
        if not typ_key:
            return None, None, {}, {"treffer": [], "fehler": f"unbekannter Typ {typ!r}",
                    "gueltige_typen": _facetten.typen_anzeige(),
                    "hinweis": "Gueltigen Kreaturentyp aus 'gueltige_typen' nutzen (B1/B4)."}
        echo["typ"] = _facetten.typ_anzeige(typ_key)

    def praedikat(body: str) -> bool:
        if grad is not None and _facetten.zauber_grad(body) != int(grad):
            return False
        if schule_key and _facetten.zauber_schule(body) != schule_key:
            return False
        if klasse and not _facetten.klasse_passt(_facetten.zauber_klassen(body), klasse):
            return False
        if schaden_key and not _facetten.hat_schadensart(body, schaden_key):
            return False
        if hg and not _facetten.hg_passt(body, str(hg)):
            return False
        if typ_key and _facetten.monster_typ(body) != typ_key:
            return False
        return True

    return praedikat, implizit, echo, None

# Welche Meta-Spalte zu welchem Filter gehoert. `klasse` fehlt bewusst: die Spalte haelt
# die ROHE Liste ("Magier, Zauberer"), das Praedikat kanonisiert dagegen - ein
# Gleichheitsvergleich waere falsch. `schadensart` hat gar keine Spalte.
_META_SPALTE = {"zauber": {"grad": "grad", "schule": "schule"},
                "monster": {"hg": "hg", "typ": "typ"}}

# Spalten, die AUSSCHLIESSLICH facetten_seeder schreibt. Der bis Phase 3 zustaendige
# Open5e-Sonderweg kannte sie nicht - ist eine davon irgendwo gefuellt, stammt die Tabelle
# nachweislich vom heutigen Seeder und traegt damit den kanonischen Wertraum.
_META_NEUZEIT = {"zauber_meta": "ritual", "monster_meta": "rk"}

def _meta_ist_kanonisch(con, tabelle: str, spalten: set[str]) -> bool:
    """Traegt die Meta-Tabelle den KANONISCHEN Wertraum aus app/facetten.py?

    Der Vorfilter darf nur greifen, wenn er das bejahen kann. Eine Datenbank, deren
    Meta-Zeilen noch vom alten Open5e-Sonderweg stammen, fuehrt dort `schule='Evocation'`
    statt `'hervorrufung'` und `hg='0.25'` statt `'1/4'` - ein Vorfilter darauf wuerde
    passende Eintraege still WEGWERFEN. Genau die Fehlerform, gegen die dieser Filter
    abgesichert sein muss: lieber langsam richtig als schnell falsch.

    Der Nachweis kommt aus den Daten selbst, ohne neuen Zustand: eine Spalte, die es zur
    Zeit des alten Schreibers gar nicht gab. Ist sie irgendwo gefuellt, hat der heutige
    Seeder die Tabelle geschrieben."""
    zeuge = _META_NEUZEIT.get(tabelle)
    if not zeuge or zeuge not in spalten:
        return False
    return con.execute(f"SELECT 1 FROM {tabelle} WHERE {zeuge} IS NOT NULL "
                       f"LIMIT 1").fetchone() is not None

def _meta_vorfilter(kategorie, grad, schule, hg, typ) -> dict[str, object]:
    """Die Filterwerte in der Form, in der `facetten_seeder` sie in die Meta-Tabelle
    geschrieben hat - Grundlage des Vorfilters in `_struktur_filter`.

    Wird erst gerufen, wenn `_facetten_vorbereiten` die Eingaben schon als gueltig
    abgenommen hat; die Schluessel lassen sich daher gefahrlos erneut ableiten."""
    werte: dict[str, object] = {}
    if kategorie == "zauber":
        if grad is not None:
            werte["grad"] = int(grad)
        if schule:
            werte["schule"] = _facetten.schule_schluessel(schule)
    elif kategorie == "monster":
        if hg:
            werte["hg"] = str(hg).strip()
        if typ:
            werte["typ"] = _facetten.typ_schluessel(typ)
    return {k: v for k, v in werte.items() if v is not None}

def _vorfilter_sql(con, kategorie: str, werte: dict) -> tuple[str, str, list]:
    """(JOIN, WHERE-Zusatz, Parameter) fuer den Meta-Vorfilter - oder dreimal leer.

    Der Vorfilter ENTSCHEIDET NICHTS. Er schliesst nur Zeilen aus, deren gespeicherter
    Wert nachweislich ein anderer ist; ueber alle uebrigen urteilt weiterhin das
    Textpraedikat. Das ist aequivalent, weil `facetten_seeder` die Spalten mit DENSELBEN
    Parsern fuellt, die das Praedikat benutzt - eine Zeile mit `grad = 4` kann unmoeglich
    `zauber_grad(body) == 3` erfuellen.

    `IS NULL` faengt beide Faelle ab, in denen nichts belegt ist: keine Meta-Zeile (der
    LEFT JOIN liefert NULL) und eine Zeile, aus deren Text sich der Wert nicht ableiten
    liess. Genau deshalb bleibt der Filter auf einer ungeseedeten Datenbank
    selbsttragend - er faellt dann auf das Textpraedikat zurueck, statt still nichts zu
    liefern (das war die C1-Fehlerform, die in Phase 3 gegen einen reinen SQL-Filter
    sprach).

    Fehlt die Tabelle ganz (Alt-DB), wird gar nicht vorgefiltert."""
    # Kategorie -> Meta-Tabelle aus der EINEN Definition (app.facetten.META_TABELLEN),
    # deren Docstring genau das zusagt: "EINE Definition fuer Schreiber und Leser".
    # Hier stand bis zum 31.07.2026 ein eigenes Dict - eine dritte Kopie neben
    # Seeder und Ausgabe, und die einzige, die `gegenstand` gar nicht kannte.
    spez = _facetten.META_TABELLEN.get(kategorie)
    tabelle = spez[0] if spez else None
    if not tabelle or not werte:
        return "", "", []
    try:
        vorhanden = {r[1] for r in con.execute(f"PRAGMA table_info({tabelle})")}
        if not _meta_ist_kanonisch(con, tabelle, vorhanden):
            return "", "", []
    except sqlite3.Error:
        return "", "", []
    nutzbar = {k: v for k, v in werte.items()
               if _META_SPALTE.get(kategorie, {}).get(k) in vorhanden}
    if not nutzbar:
        return "", "", []
    bedingungen, params = [], []
    for schluessel, wert in nutzbar.items():
        spalte = _META_SPALTE[kategorie][schluessel]
        bedingungen.append(f"(m.{spalte} IS NULL OR m.{spalte} = ?)")
        params.append(wert)
    return (f" LEFT JOIN {tabelle} m ON m.eintrag_id = e.id",
            " AND " + " AND ".join(bedingungen), params)

def _struktur_filter(con, kategorie, edition, praedikat, echo, limit=25,
                     vorfilter=None, quelle_kuerzel=None) -> dict:
    """Reiner Struktur-Filter (kein Suchbegriff): scannt eine Kategorie und filtert per
    Praedikat aus dem Body. Deutsch-first-Dedup, knappe Treffer mit 'kurzinfo'.

    quelle_kuerzel (Befund 30.07.2026): Der Parameter wurde hier gar nicht erst
    entgegengenommen - foliant_suche_bestand reichte ihn nur in den VOLLTEXT-Pfad weiter.
    Eine Struktur-Anfrage mit Quellen-Einschraenkung lieferte deshalb still den GESAMTEN
    Bestand, und ein Tippfehler im Kuerzel blieb ebenso still: gemessen ergab
    quelle_kuerzel='GIBTESNICHT' 25 Treffer statt eines Fehlers. Beides ist gefaehrlich,
    weil die Antwort plausibel aussieht - die Filterzeile 'gefiltert_nach' behauptete
    sogar, die Quelle sei beruecksichtigt."""
    try:
        edition = _db.normalisiere_edition(edition)
        _db._pruefe_edition(con, edition)
        _db._pruefe_quelle(con, quelle_kuerzel)
    except ValueError as fehler:
        return {"treffer": [], "fehler": str(fehler),
                "hinweis": _HINWEIS_PARAMETER}
    join, zusatz, vor_params = _vorfilter_sql(con, kategorie, vorfilter or {})
    if quelle_kuerzel:
        zusatz += " AND q.kuerzel = ?"
        vor_params = (*vor_params, quelle_kuerzel)
    roh: list[dict] = []
    for r in con.execute(
            f"""SELECT e.id, e.kategorie, e.name_de, e.name_en, e.sprache, e.edition,
                       e.seite, e.body_md, q.kuerzel AS quelle, q.titel AS quelle_titel,
                       q.prioritaet
                FROM eintraege e JOIN quellen q ON q.id = e.quelle_id{join}
                WHERE e.kategorie = ? AND e.edition = ?{zusatz}""",
            (kategorie, edition, *vor_params)):
        e = dict(r)
        if not praedikat(e["body_md"] or ""):
            continue
        e["auszug"] = (e["body_md"] or "")[:160]
        e["lauf_rang"] = 0
        roh.append(e)
    deduped = _db._dedupe_und_sortiere(con, roh, set())
    if kategorie == "zauber":
        deduped.sort(key=lambda t: (_facetten.zauber_grad(t.get("body_md") or "") or 0,
                                    (t.get("name_de") or t.get("name_en") or "").lower()))
    else:
        deduped.sort(key=lambda t: (t.get("name_de") or t.get("name_en") or "").lower())
    treffer = []
    for t in deduped[: min(max(int(limit), 1), 50)]:
        k = _knapp(t, con)
        info = (_facetten.zauber_kurz(t.get("body_md") or "") if kategorie == "zauber"
                else _facetten.hg_kurz(t.get("body_md") or ""))
        if info:
            k["kurzinfo"] = info
        treffer.append(k)
    antwort = {"treffer": treffer, "anzahl_gesamt": len(deduped),
               "gefiltert_nach": {**echo, "kategorie": kategorie, "edition": edition}}
    # Spoiler-Kennzeichnung auch im reinen Struktur-Pfad (A2) - hier gibt es keinen
    # Suchbegriff, also auch keine Namensrelevanz zu bewerten.
    _markiere_inhaltsart(con, antwort, treffer)
    markiere_unuebersetzte(antwort, treffer)
    _haenge_revisionen_an(con, antwort, treffer)
    if treffer:
        antwort["hinweis_abkuerzungen"] = HINWEIS_ABKUERZUNGEN
        antwort["hinweis_darstellung"] = HINWEIS_KOPFZEILE
        markiere_mehrdeutige_treffer(antwort, treffer)
    if not treffer:
        antwort["hinweis"] = ("Kein Eintrag im Bestand passt auf ALLE Filter - ehrlicher "
                              "Nulltreffer (nicht raten, nichts aus Allgemeinwissen ergaenzen); "
                              "evtl. Filter lockern oder ein Buch fehlt (B1/B2).")
    elif len(deduped) > len(treffer):
        antwort["hinweis_gekuerzt"] = (f"{len(deduped)} Treffer, {len(treffer)} gezeigt "
                                       f"(limit={limit}).")
    return antwort

def _nachfiltern_facetten(con, antwort, praedikat) -> None:
    """Volltext-Treffer zusaetzlich strukturell filtern (Suchbegriff UND Facetten):
    Eintraege, deren Body das Praedikat nicht erfuellt, aus allen Trefferlisten werfen."""
    listen = [antwort.get("treffer", []), antwort.get("aeltere_staende", []),
              antwort.get("andere_fassungen", [])]
    ids = {k["eintrag_id"] for liste in listen for k in liste}
    if not ids:
        return
    marker = ",".join("?" * len(ids))
    body = {r[0]: r[1] for r in con.execute(
        f"SELECT id, body_md FROM eintraege WHERE id IN ({marker})", tuple(ids))}
    for liste in listen:
        liste[:] = [k for k in liste if praedikat(body.get(k["eintrag_id"]) or "")]

def _suche_bestand_impl(suchbegriff: str | None = None, kategorie: Kategorie | None = None,
                        edition: str = "2024", quelle_kuerzel: str | None = None,
                        grad: int | None = None, schule: str | None = None,
                        klasse: str | None = None, schadensart: str | None = None,
                        hg: str | None = None, typ: str | None = None) -> dict:
    """Kernlogik der Bestandssuche; Tool-Beschreibung und Protokoll-Hook sitzen im
    oeffentlichen Wrapper foliant_suche_bestand."""
    con = _verbinde()
    if con is None:
        return {"treffer": [], "hinweis": HINWEIS_DB_FEHLT}
    try:
        praedikat, kat_filter, echo, fehler = _facetten_vorbereiten(
            kategorie, grad, schule, klasse, schadensart, hg, typ)
        if fehler is not None:
            return fehler
        hat_suchbegriff = bool(suchbegriff and suchbegriff.strip())
        if not hat_suchbegriff and praedikat is None:
            return {"treffer": [], "fehler": "kein_kriterium",
                    "hinweis": "Bitte einen Suchbegriff ODER einen Filter (grad/schule/klasse/"
                               "schadensart/hg/typ) angeben - sonst ist es weder Text- noch "
                               "Struktursuche. KEIN 'nicht im Bestand'."}
        if not hat_suchbegriff:
            return _struktur_filter(
                con, kat_filter, edition, praedikat, echo,
                vorfilter=_meta_vorfilter(kat_filter, grad, schule, hg, typ),
                quelle_kuerzel=quelle_kuerzel)
        try:
            # A1-Fix (Review 28.07.2026): Mit aktivem Struktur-Filter MEHR Kandidaten holen.
            # Vorher lief die Nachfilterung auf den bereits auf 8 gekappten Treffern - fielen
            # dabei alle weg, meldete der Code HINWEIS_LEER ('Nichts im Bestand gefunden'),
            # obwohl nur der Top-8-Ausschnitt geprueft war. Das System behauptete dem Modell
            # damit ausgerechnet bei der Anti-Halluzinations-Regel etwas Falsches.
            such_limit = _db.MAX_LIMIT if praedikat is not None else 8
            ergebnis = _db.fts_suche(con, suchbegriff, kategorie=(kat_filter or kategorie),
                                     edition=edition, quelle=quelle_kuerzel,
                                     limit=such_limit)
        except ValueError as fehler_v:
            # SYN-P0-006: Parameterfehler (Edition/Kategorie/Quelle) sind KEIN leerer
            # Befund - vor dem Fix bekam das Modell hier den B1-Leerhinweis und meldete
            # dem Nutzer ein falsches 'nicht im Bestand' fuer vorhandene Inhalte.
            return {"treffer": [], "fehler": str(fehler_v),
                    "hinweis": _HINWEIS_PARAMETER}
        antwort: dict = {"treffer": [_knapp(t, con) for t in ergebnis["treffer"]],
                         # Privat fuer den Protokoll-Hook (Wrapper poppt den Schluessel):
                         # der rohe Suchweg 'direkt|glossar:<begriff>|fuzzy|-'.
                         "_suchweg": ergebnis["suchweg"]}
        andere = ergebnis["andere_editionen"]
        edition = _db.normalisiere_edition(edition)
        if andere and edition == _db.STANDARD_EDITION:
            # Standardmodus: nur numerisch AELTERE Fassungen sind 'aeltere_staende'
            # (SYN-P2-001: eine kuenftige NEUERE Edition darf nicht 'aelter' heissen).
            aeltere = [t for t in andere
                       if t["edition"].isdigit() and edition.isdigit()
                       and int(t["edition"]) < int(edition)]
            neuere = [t for t in andere if t not in aeltere]
            if aeltere:
                antwort["aeltere_staende"] = [_knapp(t, con) for t in aeltere]
            if neuere:
                antwort["andere_fassungen"] = [_knapp(t, con) for t in neuere]
        elif andere:
            # Explizit andere Edition angefragt: neutral benennen - die uebrigen
            # Fassungen (z. B. 2024) sind nicht 'aelter' (A1).
            antwort["andere_fassungen"] = [_knapp(t, con) for t in andere]
        if ergebnis["suchweg"].startswith("glossar:"):
            antwort["hinweis_suchweg"] = (f"Treffer ueber das Glossar gefunden "
                                          f"({suchbegriff} -> {ergebnis['suchweg'][8:]}).")
        elif ergebnis["suchweg"] == "fuzzy":
            antwort["hinweis_suchweg"] = "Aehnliche Schreibweise angenommen (Tippfehler-Toleranz)."
        geprueft = ergebnis["anzahl_gesamt"]
        if praedikat is not None:
            # Suchbegriff UND Struktur-Filter: die Volltext-Treffer zusaetzlich strukturell
            # einschraenken (UND-Semantik), bevor der Leer-Hinweis entscheidet.
            _nachfiltern_facetten(con, antwort, praedikat)
            antwort["gefiltert_nach"] = echo
            # anzahl_gesamt meint ab hier: passende Treffer im geprueften Bereich, nicht
            # Volltext-Treffer vor dem Filter. VOR dem Kappen zaehlen - bis zum Audit
            # 28.07.2026 stand die Zaehlung dahinter, war damit per Konstruktion gleich
            # der Anzeigemenge und der hinweis_gekuerzt unten konnte nie feuern: 25
            # passende Zauber, 8 gezeigt, kein Signal (A5, dieselbe Ehrlichkeitsklasse
            # wie A1 - nur in der Richtung 'zu wenig gezeigt').
            passend = len(antwort["treffer"])
            # Erst JETZT auf die Anzeigemenge kappen - vorher lief die Filterung auf einer
            # schon gekappten Liste (A1).
            for schluessel in ("treffer", "aeltere_staende", "andere_fassungen"):
                if antwort.get(schluessel):
                    antwort[schluessel] = antwort[schluessel][:8]
            ergebnis = {**ergebnis, "anzahl_gesamt": passend}
        if antwort["treffer"] and ergebnis["anzahl_gesamt"] > len(antwort["treffer"]):
            # Ohne dieses Signal kappt der Volltext-Pfad still - stil.py/SPEC par. 8
            # versprechen dem Modell aber 'hinweis_gekuerzt' generell (bisher setzte es
            # nur der Struktur-Filter-Pfad). 'mindestens': die Zahl ist eine Untergrenze,
            # weil fts_suche schon vor dem Zaehlen auf das Roh-Limit kappt (A5).
            antwort["anzahl_gesamt"] = ergebnis["anzahl_gesamt"]
            antwort["hinweis_gekuerzt"] = (
                f"mindestens {ergebnis['anzahl_gesamt']} Treffer, "
                f"{len(antwort['treffer'])} gezeigt - Suche ggf. mit kategorie oder "
                f"Struktur-Filtern praezisieren.")
        if not antwort["treffer"]:
            if antwort.get("aeltere_staende"):
                antwort["hinweis"] = HINWEIS_ALT
            elif andere:
                antwort["hinweis"] = (f"In Regelversion {edition} nichts im Bestand; "
                                      f"es gibt aber Fassungen anderer Versionen (siehe "
                                      f"'andere_fassungen') - klar unterscheiden (V5).")
            elif praedikat is not None and geprueft:
                # KEIN HINWEIS_LEER: der Suchbegriff HAT getroffen, nur der Struktur-Filter
                # passte auf keinen davon. 'Nichts im Bestand' waere hier schlicht falsch.
                antwort["hinweis"] = (
                    f"Der Suchbegriff traf {geprueft} Eintraege, aber keiner davon erfuellt "
                    f"die gesetzten Filter ({', '.join(f'{k}={v}' for k, v in echo.items())}). "
                    f"Das ist KEIN 'nicht im Bestand' - Filter lockern oder ohne Filter "
                    f"suchen, bevor du dem Nutzer eine Fehlanzeige meldest (B1/B4).")
            else:
                antwort["hinweis"] = HINWEIS_LEER
        listen = [antwort["treffer"], antwort.get("aeltere_staende", []),
                  antwort.get("andere_fassungen", [])]
        # A4 (Review 28.07.2026): Relevanz sichtbar machen. db.py loescht den bm25-Score vor
        # der Rueckgabe - das Modell bekam eine blosse Reihenfolge ohne Qualitaetsmass und
        # konnte einen zufaelligen Body-Treffer nicht von einem Namenstreffer unterscheiden.
        # Belegt: 'Beholder' lieferte 8 Treffer, obwohl der Bestand keinen Beholder enthaelt
        # (nicht SRD-lizenziert). Statt bm25 zu interpretieren (im Fuzzy-Pfad steht dort ein
        # ganz anderer Wert) nutzen wir die vorhandene NAMENS-Relevanz - sie trennt genau
        # diese beiden Faelle und ist dieselbe Schwelle wie bei der Detail-Auswahl.
        varianten = _db.anfrage_varianten(con, suchbegriff)
        namenstreffer = 0
        for liste in listen:
            for k in liste:
                treffer_am_namen = _glossar._name_score(k, varianten) >= _glossar._NAME_MIN
                k["relevanz"] = "name" if treffer_am_namen else "nur_im_text"
                namenstreffer += int(treffer_am_namen)
        if antwort["treffer"] and not namenstreffer:
            antwort["hinweis_geringe_relevanz"] = (
                "Kein Treffer passt dem NAMEN nach zur Anfrage - alle erwaehnen den Begriff "
                "nur im Fliesstext. Das ist oft das Zeichen, dass der gesuchte Eintrag NICHT "
                "im Bestand ist (z. B. nicht SRD-lizenziert). Treffer kritisch pruefen und "
                "im Zweifel ehrlich 'nicht gefunden' sagen, statt Unpassendes auszugeben (B1).")
        _markiere_inhaltsart(con, antwort, *listen)
        markiere_unuebersetzte(antwort, *listen)
        _haenge_revisionen_an(con, antwort, *listen)
        # S12: Die Auszuege tragen englische Kuerzel ('AC 17', '8d6') in die Antwort -
        # wer aus ihnen formuliert, braucht die Regel hier, nicht nur im Detailabruf.
        if antwort.get("treffer"):
            antwort["hinweis_abkuerzungen"] = HINWEIS_ABKUERZUNGEN
            antwort["hinweis_darstellung"] = HINWEIS_KOPFZEILE
            markiere_mehrdeutige_treffer(antwort, antwort["treffer"])
        _reichere_facetten_an(con, *listen)
        return antwort
    finally:
        con.close()

def foliant_suche_bestand(suchbegriff: str | None = None, kategorie: Kategorie | None = None,
                          edition: str = "2024", quelle_kuerzel: str | None = None,
                          grad: int | None = None, schule: str | None = None,
                          klasse: str | None = None, schadensart: str | None = None,
                          hg: str | None = None, typ: str | None = None) -> dict:
    """Findet Eintraege im GESAMTEN Bestand - per Freitext ODER per STRUKTUR-Filter (oder
    beides kombiniert). Liefert KNAPPE Treffer (Name, Auszug, Quelle, ggf. Seite,
    Regelversion; Zauber/Monster zusaetzlich 'kurzinfo' mit Grad bzw. HG) - den vollen
    Text eines Treffers holt foliant_hol_eintrag (dessen `kategorie` und `eintrag_id`
    stehen an jedem Treffer).
    - Freitext: `suchbegriff` deutsch ODER englisch, auch Abkuerzungen (AoO) und Tippfehler.
    - Struktur-Filter (fuer 'welche Grad-1-Feuerzauber kann ein Hexenmeister lernen?', die
      der Freitext nur zufaellig trifft): Zauber ueber grad (0-9, 0=Zaubertrick), schule,
      klasse, schadensart; Monster ueber hg ('1', '1/4') und typ. Werte deutsch ODER
      englisch. Mehrere Filter werden UND-verknuepft; Zauber- und Monster-Facetten nicht
      mischen. Ohne Suchbegriff genuegt EIN Filter.
    kategorie optional: regel|zauber|monster|gegenstand|spezies|klasse|hintergrund|talent.
    quelle_kuerzel optional: das QUELLEN-KUERZEL (z. B. 'srd-de'), NICHT der Titel. edition
    Standard '2024'; andere Regelversionen (z. B. '2014') explizit angeben. Ungueltige
    Parameterwerte werden mit 'fehler' abgelehnt - das bedeutet NICHT 'nicht im Bestand'.
    Beim 2024-Standard kommen aeltere Staende getrennt als 'aeltere_staende'; bei explizit
    anderer Edition heissen weitere Fassungen neutral 'andere_fassungen'. KERNREGELN: nur
    aus dem Bestand; Quelle + Regelversion nennen; Deutsch-first (Original in Klammern);
    Abkuerzungen DEUTSCH (RK/TP/SG/HG, W20 - nie AC/HP/DC/d20)."""
    start = time.monotonic()
    antwort = _suche_bestand_impl(suchbegriff, kategorie, edition, quelle_kuerzel,
                                  grad, schule, klasse, schadensart, hg, typ)
    suchweg = antwort.pop("_suchweg", None)
    if suchweg is None:
        # Pfade ohne FTS-Lauf: Parameterfehler, reiner Struktur-Filter-Scan, fehlende DB.
        if "fehler" in antwort:
            suchweg = "fehler"
        elif not (suchbegriff and suchbegriff.strip()):
            suchweg = "struktur"
        else:
            suchweg = "-"
    _protokoll.protokolliere(
        werkzeug="suche_bestand", suchbegriff=suchbegriff, kategorie=kategorie,
        edition=edition, quelle_kuerzel=quelle_kuerzel,
        filter={"grad": grad, "schule": schule, "klasse": klasse,
                "schadensart": schadensart, "hg": hg, "typ": typ},
        anzahl_treffer=len(antwort.get("treffer", [])), suchweg=suchweg,
        dauer_ms=(time.monotonic() - start) * 1000)
    return antwort
