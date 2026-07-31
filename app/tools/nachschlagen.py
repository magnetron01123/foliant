"""Nachschlage-Werkzeuge (F1/F2). Namensschema foliant_<verb>_<nomen> (BP #2).
Suche = KNAPPE Trefferliste; Detail = volle Ausgabe (BP #1).

Review-Fund, Kanal 3 (zuverlaessigster Weg zum Modell): Grounding-Hinweise stehen IN den
Tool-AUSGABEN - eine leere Suche sagt explizit "Nichts im Bestand - ehrlich sagen...".
Kanal 2: Kurzfassung der Kernregeln in jeder Tool-Beschreibung (= Docstring)."""
from __future__ import annotations

import re
import sqlite3
import time
from typing import Literal, NamedTuple

from app import db as _db
from app.db import Kategorie
from app import glossar as _glossar
from app import protokoll as _protokoll
from app.tools.ausgabe import (
    HINWEIS_DB_FEHLT,
    HINWEIS_LEER,
    HINWEIS_MEHRDEUTIG,
    _HINWEIS_PARAMETER,
    _HINWEIS_STERN,
    _alias_hinweis,
    _detail,
    _knapp,
    _markiere_inhaltsart,
    _verbinde,
)



def _texte_weichen_ab(a: str, b: str) -> bool:
    """Wesentliche Textabweichung zweier Fassungen (SYN-P1-009). Normalisiert
    (Kontextzeile weg, Kleinschreibung, Whitespace kollabiert), dann rapidfuzz-ratio
    unter der Schwelle. Nur fuer GLEICHSPRACHIGE Fassungen aussagekraeftig - DE/EN-Paare
    weichen naturgemaess ab und laufen stattdessen in 'fremdsprachige_fassungen'.
    Wert und Begruendung in app/glossar.py bei den uebrigen Fuzzy-Schwellen."""
    from rapidfuzz import fuzz

    def norm(t: str) -> str:
        t = _db.KONTEXT_ZEILE.sub("", t or "", count=1)
        return " ".join(t.lower().split())
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    return fuzz.ratio(na, nb) < _glossar.FUZZY_ABWEICHUNG


# Abschnitts-Ueberschriften IN einem Eintrag: Markdown-Header (optional mit srd-de-
# Stufenpraefix 'N. Stufe:') sowie fette Merkmals-/Sub-Feature-Koepfe ('**_Kampfrausch:_**',
# '***Rage.***'). Nur EXAKTE (normalisierte) Gleichheit mit dem gesuchten Begriff zaehlt -
# die breiten Muster sind unkritisch, weil jeder Fund noch den Namensvergleich bestehen muss.
_SUB_UEBERSCHRIFTEN = (
    re.compile(r"^#+\s*\**\s*(?:\d+\.\s*Stufe:\s*)?(.+?)\s*\**\s*$", re.MULTILINE),
    re.compile(r"\*\*_([^_\n]{2,80}?)[.:]?_\*\*"),
    re.compile(r"\*\*\*([^*\n]{2,80}?)[.:]?\*\*\*"),
)


def _unterabschnitts_nachsuche(con: sqlite3.Connection, kategorie: str,
                               varianten: set[str], edition: str) -> list[dict]:
    """Zusatz-Kandidaten fuer den Unterabschnitts-Check: eine gezielte FTS-Suche NUR in
    der Ziel-Edition. Noetig, weil die editionsuebergreifende Top-6-Liste auf dem vollen
    Bestand von woertlichen Alt-Treffern dominiert wird (Pi-Befund 18.07.2026: der
    2014-Eintrag 'Rage' + Rauschen verdraengten 'Klassenmerkmale des Barbaren' - lokal,
    ohne 2014-Quelle, war derselbe Eintrag sichtbar und der Fallback griff)."""
    gesehen: set[int] = set()
    extra: list[dict] = []
    for begriff in sorted(varianten):
        for k in _db.fts_suche(con, begriff, kategorie=kategorie, edition=edition,
                               limit=8)["treffer"]:
            if k["id"] not in gesehen:
                gesehen.add(k["id"])
                extra.append(k)
    return extra


def _unterabschnitts_treffer(con: sqlite3.Connection, kandidaten: list[dict],
                             varianten: set[str], edition: str) -> tuple[dict, str] | None:
    """Findet unter den FTS-Kandidaten der ZIEL-Edition einen Eintrag, der den gesuchten
    Begriff als ABSCHNITTS-UEBERSCHRIFT im Body traegt - z. B. 'Kampfrausch' als
    '1. Stufe: Kampfrausch' in 'Klassenmerkmale des Barbaren' (srd-de chunkt Klassen-/
    Spezies-Merkmale als Sammelseiten, nicht als Einzeleintraege). Ohne diesen Schritt
    fiel der Lookup auf eine AELTERE oder FREMDSPRACHIGE Fassung zurueck, obwohl die
    aktuelle deutsche Antwort im Bestand steht (Befund 17.07.2026: hol_klasse('Rage')
    lieferte die englische 2014-Fassung). Die Kandidatenliste ist prioritaets-/Deutsch-
    first-sortiert - der erste Body-Treffer ist die kanonische Quelle.
    Rueckgabe: (kandidat, gefundene_ueberschrift) oder None."""
    for k in kandidaten:
        if k.get("edition") != edition:
            continue
        voll = _db.hole_eintrag(con, k["id"])
        if not voll:
            continue
        body = voll.get("body_md") or ""
        for muster in _SUB_UEBERSCHRIFTEN:
            for m in muster.finditer(body):
                if _glossar.norm_begriff(m.group(1)) in varianten:
                    return k, m.group(1).strip()
    return None


def _kinder_texte(con: sqlite3.Connection, voll: dict) -> list[str]:
    """Direkte Unterabschnitte eines Options-Eintrags fuer die Detail-ZUSAMMENFUEHRUNG (DDB
    zerlegt eine Option in Intro + '<Name> Traits' + ggf. Abstammungen; die Werte stehen im
    Unterabschnitt). Kind = gleiche Kategorie/Edition/Quelle UND Kontext exakt
    '<Eltern-Kontext> > <Eltern-Name>'. So bleibt es auf DIREKTE Kinder begrenzt (kein
    Einsaugen ganzer Kapitelbaeume) und quellen-/editionsrein. Rueckgabe: formatierte
    Abschnitte (Unterabschnitts-Name als Zwischenueberschrift, Kontextzeile entfernt)."""
    eltern_kontext = _db.kontext_aus_body(voll.get("body_md"))
    namen = {n for n in (voll.get("name_en"), voll.get("name_de")) if n}
    ziele = {f"{eltern_kontext} > {n}" if eltern_kontext else n for n in namen}
    stuecke: list[str] = []
    for r in con.execute(
            "SELECT e.name_de, e.name_en, e.body_md FROM eintraege e "
            "JOIN quellen q ON q.id = e.quelle_id WHERE e.kategorie = ? AND e.edition = ? "
            "AND q.kuerzel = ? AND e.id != ? ORDER BY e.id",
            (voll["kategorie"], voll["edition"], voll["quelle"], voll["id"])):
        if _db.kontext_aus_body(r["body_md"]) in ziele:
            kname = (r["name_de"] or r["name_en"] or "").strip()
            koerper = _db.KONTEXT_ZEILE.sub("", r["body_md"], count=1).strip()
            stuecke.append(f"### {kname}\n\n{koerper}" if kname else koerper)
    return stuecke


def _hole_detail(kategorie: str, name: str | None = None,
                 edition: str = _db.STANDARD_EDITION,
                 aggregiere_kinder: bool = False,
                 eintrag_id: int | None = None) -> dict:
    """Detailabruf OHNE Protokollierung - der gemeinsame Kern des Detailpfads.

    Protokolliert wird auf der WERKZEUG-Ebene (foliant_hol_eintrag), nicht hier. Bis zum
    31.07.2026 sass der Hook an dieser Stelle, und das verzerrte den Suchbericht in beide
    Richtungen: `app/tools/charakter.py` ruft diese Funktion dreimal als INTERNE Sonde
    (Regelbeleg, Klassenmerkmale, Attributsregel), und jede dieser Sonden schrieb eine
    Zeile, als haette ein Nutzer gefragt. Am Live-Protokoll gemessen stand
    'Schritt 3: Attributswerte' mit 186 Treffern als VIERTHAEUFIGSTER Suchbegriff im
    Bericht - hinter 'Feuerball' und 'Kämpfer'. Umgekehrt tauchten die drei
    Charakter-Werkzeuge selbst nie auf. Der Bericht ist die Kurationsliste (O4/M5); was
    darin steht, entscheidet, welche Glossar-Paare jemand von Hand nachzieht."""
    antwort = _hole_detail_impl(kategorie, name, edition, aggregiere_kinder, eintrag_id)
    if not antwort.get("gefunden") and (alias := _alias_hinweis(edition)):
        antwort["hinweis_edition_alias"] = alias
    return antwort


def _mit_kindern(con, voll: dict, aggregiere_kinder: bool) -> tuple[dict, list[str]]:
    """(Eintrag, Kindertexte): direkte Unterabschnitte in den Regeltext zusammenfuehren,
    damit die Detailauskunft VOLLSTAENDIG ist (DDB-Optionen). Ohne Kinder bleibt der
    Eintrag unveraendert - kopiert wird nur, wenn wirklich etwas angehaengt wird."""
    kinder = _kinder_texte(con, voll) if aggregiere_kinder else []
    if kinder:
        voll = dict(voll)
        voll["body_md"] = voll["body_md"].rstrip() + "\n\n" + "\n\n".join(kinder)
    return voll, kinder


def _detail_per_id(con, kategorie: str, eintrag_id: int,
                   aggregiere_kinder: bool) -> dict:
    """SYN-P1-002: Direktabruf per stabiler Referenz aus einem Suchtreffer - KEINE
    Namensaufloesung, keine Editions-/Prioritaetswahl: exakt DIESER Eintrag oder ein
    strukturierter Fehler (nie ein stiller Quellenwechsel)."""
    voll = _db.hole_eintrag(con, int(eintrag_id))
    if voll is None:
        return {"gefunden": False,
                "fehler": f"eintrag_id {eintrag_id} gibt es in diesem Bestand nicht - "
                          f"die Referenz ist veraltet. Mit foliant_suche_bestand neu "
                          f"suchen und die eintrag_id aus dem frischen Treffer nehmen.",
                "hinweis": _HINWEIS_PARAMETER}
    if voll["kategorie"] != kategorie:
        # Selbstkorrigierend formuliert: der Aufruf ist bis auf EIN Feld richtig, also
        # nennt die Meldung den Wert, der dort hingehoert. Der alte Wortlaut ('passendes
        # foliant_hol_* nutzen') stammte aus der Zeit der acht Detail-Werkzeuge und
        # schickte das Modell zu einem Werkzeug, das es nicht mehr gibt.
        return {"gefunden": False,
                "fehler": f"eintrag_id {eintrag_id} ist Kategorie "
                          f"'{voll['kategorie']}', angefragt war '{kategorie}' - "
                          f"denselben Aufruf mit kategorie='{voll['kategorie']}' "
                          f"wiederholen.",
                "hinweis": _HINWEIS_PARAMETER}
    voll, _kinder = _mit_kindern(con, voll, aggregiere_kinder)
    return {"gefunden": True, **_detail(voll, con)}


class _Auswahl(NamedTuple):
    """Ergebnis der Kandidatenwahl - ENTWEDER ein Treffer ODER eine fertige Absage."""
    gewaehlt: dict | None
    unterabschnitt: str | None        # Abschnittsname, falls per Unterabschnitt gefunden
    weitere_abschnitte: list[dict]    # gleichnamige Abschnitte DERSELBEN Quelle
    exakt: list[dict]                 # exakte Namenstreffer (fuer Fassungen/Konflikte)
    absage: dict | None               # fertige Antwort, wenn nichts eindeutig waehlbar ist


def _waehle_kandidat(con, name: str, kategorie: str, edition: str,
                     kandidaten: list[dict]) -> _Auswahl:
    """WELCHEN Eintrag liefern wir? Die Entscheidung, getrennt vom Antwortaufbau.

    Vier Wege, in dieser Reihenfolge: exakter Namenstreffer der Zieledition ->
    Unterabschnitt eines Sammel-Eintrags -> exakter Treffer einer anderen Edition (B5) ->
    Namensrelevanz. Bleibt es mehrdeutig, ist die Absage das Ergebnis."""
    # Exakt zaehlt auch der per Glossar aufgeloeste Begriff ('Feuerball' <-> 'Fireball'):
    # nach Begriffsaufloesung ist das KEIN Raten (B3/B4). NUR exakte Glossarbeziehungen
    # (SYN-P0-001: die Fuzzy-Naehe 'Aktionen'~'Reaktionen' machte einen FREMDEN Eintrag
    # zum Exakt-Treffer). Die prioritaets-sortierte Trefferliste stellt dabei deutsche
    # Quellen nach vorn (S10/Q2).
    varianten = _db.anfrage_varianten(con, name)
    exakt = [k for k in kandidaten if _glossar._eintrag_namen(k) & varianten]
    # S10 EXPLIZIT statt per Annahme: die FTS-Rangfolge stellt einen englischen
    # Volltreffer ('Warrior of the Open Hand', Open5e) vor den deutschen Praefix-Titel
    # ('Moench-Unterklasse: Krieger der Offenen Hand', srd-de) - fuer die Detailwahl
    # zaehlt aber Deutsch-first. Stabile Sortierung: DE-Fassungen nach vorn, sonst
    # FTS-Reihenfolge unveraendert (Befund 17.07.2026).
    exakt.sort(key=lambda k: k.get("sprache") != "de")
    ziel_exakt = [k for k in exakt if k["edition"] == edition]

    if ziel_exakt:
        gewaehlt, weitere = _waehle_aus_gleichnamigen(con, ziel_exakt)
        return _Auswahl(gewaehlt, None, weitere, exakt, None)

    # Der Begriff existiert in der ZIEL-Edition als Abschnitts-Ueberschrift eines
    # Sammel-Eintrags (srd-de-Chunking) - das schlaegt den Rueckfall auf aeltere/
    # fremdsprachige Fassungen: die aktuelle deutsche Antwort ist ja im Bestand.
    sub = (_unterabschnitts_treffer(con, kandidaten, varianten, edition)
           or _unterabschnitts_treffer(
               con, _unterabschnitts_nachsuche(con, kategorie, varianten, edition),
               varianten, edition))
    if sub:
        gewaehlt, unterabschnitt = sub
        return _Auswahl(gewaehlt, unterabschnitt, [], exakt, None)

    if exakt:
        if edition == _db.STANDARD_EDITION:
            return _Auswahl(exakt[0], None, [], exakt, None)   # nur aeltere Fassung (B5)
        fassungen = [_knapp(k, con) for k in exakt[:6]]
        absage = {"gefunden": False, "vorhandene_fassungen": fassungen,
                  "hinweis": (f"Keine Fassung der Regelversion {edition} im Bestand - "
                              f"vorhandene Fassungen siehe 'vorhandene_fassungen'; "
                              f"nicht still ersetzen (V5).")}
        _markiere_inhaltsart(con, absage, fassungen)
        return _Auswahl(None, None, [], exakt, absage)

    # #1: reine Body-Erwaehnungen (deren Name gar nicht zur Anfrage passt, z. B.
    # 'Schild'/'Zauberplaetze' bei der Suche nach 'Magic Missile') aus der Kandidatenliste
    # draengen. Bleibt genau EIN starker Namenstreffer der gewuenschten Edition (auch
    # vertippt: 'Missle'->'Missile'), ihn direkt liefern statt rueckzufragen. Sonst die
    # BEREINIGTE Kandidatenliste zeigen.
    #
    # Befund 30.07.2026: Hier stand davor ein Sonderzweig, der einen EINZELNEN
    # FTS-Kandidaten ungeprueft als Treffer auslieferte - ohne _glossar._NAME_MIN. Der Suchpfad
    # hat fuer genau diese Fehlerform seit A4 die Namensrelevanz; der Detailpfad, der
    # verbindlicher antwortet, hatte sie nicht. Der Zweig ist ersatzlos gestrichen: die
    # Zeilen darunter behandeln den Einzelkandidaten bereits, nur eben mit Relevanzgate.
    # Seine Editionsbedingung war das einzig Tragende daran - sie steht jetzt unten.
    relevante = [k for k in kandidaten if _glossar._name_score(k, varianten) >= _glossar._NAME_MIN]
    rel_std = [k for k in relevante if k["edition"] == edition]
    if len(rel_std) == 1:
        return _Auswahl(rel_std[0], None, [], exakt, None)
    # Nur beim Standard greift der B5-Rueckfall auf eine andere Fassung. Eine
    # AUSDRUECKLICH angefragte Regelversion wird nie still ersetzt (V5) - dieselbe
    # Unterscheidung, die der exakt-Zweig oben schon trifft.
    if len(relevante) == 1 and edition == _db.STANDARD_EDITION:
        return _Auswahl(relevante[0], None, [], exakt, None)
    gezeigt = [_knapp(k, con) for k in (relevante or kandidaten)[:6]]
    absage = {"gefunden": False, "mehrdeutig": True,
              "kandidaten": gezeigt, "hinweis": HINWEIS_MEHRDEUTIG}
    _markiere_inhaltsart(con, absage, gezeigt)
    return _Auswahl(None, None, [], exakt, absage)


def _waehle_aus_gleichnamigen(con, ziel_exakt: list[dict]) -> tuple[dict, list[dict]]:
    """Aus den exakten Treffern der Zieledition den zu liefernden waehlen.

    ziel_exakt ist prioritaets-/Deutsch-first-sortiert (_dedupe_und_sortiere.rang): [0] ist
    der kanonische Treffer der Vorrang-Quelle (deutsche Quelle vor DDB/Open5e, Q2/S10). Die
    SYN-P0-003-Laengenwahl (KERNABSCHNITT vor Statblock-Format-Meta 'Elemente von
    Wertekaesten' bzw. Glossar-Kurzverweis) vergleicht NUR gleichnamige Abschnitte DERSELBEN
    Quelle - verschiedene QUELLEN sind Fassungen und werden von der Quellen-Prioritaet
    entschieden, NIE von der Textlaenge. Sonst schlaegt ein laengerer englischer
    DDB-Abschnitt den exakten deutschen srd-de-Treffer (Deutsch-first-Bug: engl.
    'Reactions' ist laenger als der srd-de-Kernabschnitt 'Reaktionen')."""
    kopf = ziel_exakt[0]
    geschwister = [k for k in ziel_exakt if k["quelle"] == kopf["quelle"]]
    if len(geschwister) <= 1:
        return kopf, []
    # Gleichnamige Abschnitte DERSELBEN Quelle sind verschiedene TEXTSTELLEN (Spielregel-
    # Kapitel vs. Statblock-Format-Meta vs. Glossar-Kurzverweis, codex DND-002): den
    # AUSFUEHRLICHSTEN deterministisch waehlen (Bonusaktionen 837 vs. 200, Temp-TP 1665 vs.
    # 235); die uebrigen als nachladbare `weitere_abschnitte` ausweisen.
    def _regeltext_laenge(v: dict) -> int:
        # Laenge OHNE die Kontext-Breadcrumb-Zeile messen (ein langer Kontext taeuscht
        # sonst Textumfang vor).
        return len(_db.KONTEXT_ZEILE.sub("", v.get("body_md") or "", count=1))

    voll_paare = [(_db.hole_eintrag(con, k["id"]), k) for k in geschwister]
    voll_paare = [(v, k) for v, k in voll_paare if v]
    voll_paare.sort(key=lambda vk: _regeltext_laenge(vk[0]), reverse=True)
    return voll_paare[0][1], [_knapp(k, con) for _v, k in voll_paare[1:]]


def _quellabweichungen(con, voll: dict, gewaehlt: dict, exakt: list[dict],
                       weitere_abschnitte: list[dict]) -> tuple[list[dict], list[dict]]:
    """(konflikte, fremdsprachige) - SYN-P1-009 (codex DND-011, Vampir 'weiss'/'unaware').

    Dubletten GLEICHER Edition aus anderen Quellen textlich vergleichen: weicht der Wortlaut
    wesentlich ab, ist das ein QUELLKONFLIKT und darf nicht still von der Prioritaetsquelle
    entschieden werden. Max. 3 Vergleiche (Kosten)."""
    # Kandidaten fuer den Vergleich: die im Dedupe weggemergten Fassungen des gewaehlten
    # Treffers (gleiche Edition/Kategorie per Gruppenschluessel) plus etwaige weitere exakte
    # Kandidaten anderer Quellen. Die gleichnamigen Same-Source-Abschnitte sind bereits als
    # `weitere_abschnitte` ausgewiesen - sie duerfen den Vergleich (der QUELLuebergreifende
    # Dubletten meint) nicht als Scheinkonflikt fuellen.
    abschnitt_ids = {w["eintrag_id"] for w in weitere_abschnitte}
    vergleiche = list(gewaehlt.get("weitere_fassungen") or [])
    vergleiche += [{"id": k["id"], "quelle_titel": k["quelle_titel"]}
                   for k in exakt
                   if k["edition"] == voll["edition"] and k["id"] != voll["id"]
                   and k["id"] not in abschnitt_ids]
    konflikte, fremdsprachige = [], []
    gesehen_ids = {voll["id"]}
    for wf in vergleiche[:3]:
        if wf["id"] in gesehen_ids:
            continue
        gesehen_ids.add(wf["id"])
        anderer = _db.hole_eintrag(con, wf["id"])
        if not anderer:
            continue
        if anderer["sprache"] != voll["sprache"]:
            # Uebersetzungen koennen inhaltlich abweichen (Vampir-Fall), sind aber nicht
            # automatisch als Konflikt beweisbar -> Referenz zum Nachladen.
            fremdsprachige.append({"eintrag_id": wf["id"], "quelle": wf["quelle_titel"],
                                   "sprache": anderer["sprache"]})
        elif _texte_weichen_ab(voll["body_md"], anderer["body_md"]):
            konflikte.append({"eintrag_id": wf["id"], "quelle": wf["quelle_titel"],
                              "hinweis": "Textfassung weicht inhaltlich ab"})
    return konflikte, fremdsprachige


def _hole_detail_impl(kategorie: str, name: str | None = None,
                      edition: str = _db.STANDARD_EDITION,
                      aggregiere_kinder: bool = False,
                      eintrag_id: int | None = None) -> dict:
    """Detail-Auswahl (A1): edition ist die GEWUENSCHTE Regelversion (Standard 2024).
    Beim Standard bleibt der B5-Fallback (nur aeltere Fassung -> liefern + Warnung);
    eine AUSDRUECKLICH angeforderte andere Edition wird nie still ersetzt - fehlt sie,
    kommt ein ehrliches 'nicht gefunden' mit den vorhandenen Fassungen.
    aggregiere_kinder=True fuehrt direkte Unterabschnitte (z. B. '<Spezies> Traits') in den
    Regeltext zusammen, damit die Detailauskunft VOLLSTAENDIG ist (DDB-Optionen).
    name ist OPTIONAL, sobald eintrag_id gesetzt ist (dann wird er ohnehin ignoriert)."""
    if eintrag_id is None and not (name and name.strip()):
        return {"gefunden": False, "fehler": "kein_kriterium",
                "hinweis": "Bitte 'name' ODER 'eintrag_id' angeben. Das ist ein "
                           "PARAMETER-Fehler, KEIN 'nicht im Bestand' - Aufruf "
                           "ergaenzen, dem Nutzer keine Fehlanzeige melden (B1/B4)."}
    con = _verbinde()
    if con is None:
        return {"gefunden": False, "hinweis": HINWEIS_DB_FEHLT}
    try:
        # Befund 30.07.2026: Die KATEGORIE kam bis zur Zusammenlegung der acht
        # foliant_hol_<typ> nie vom Nutzer - sie war im Werkzeugnamen verdrahtet und konnte
        # gar nicht ungueltig sein. Seit foliant_hol_eintrag ist sie ein Parameter, und ein
        # ungueltiger Wert flog als ungefangene ValueError aus _pruefe_kategorie (ueber
        # fts_suche) heraus, statt als strukturierter 'fehler' zurueckzukommen. Der SUCH-Pfad
        # faengt sie seit SYN-P0-006; der Detailpfad hatte die Stelle nie gebraucht.
        # Die Pruefung steht VOR der eintrag_id-Weiche, damit BEIDE Wege sie nehmen - sonst
        # meldet der ID-Weg bei falscher Kategorie 'Referenz veraltet' statt des echten Grundes.
        try:
            _db._pruefe_kategorie(kategorie)
        except ValueError as fehler:
            return {"gefunden": False, "fehler": str(fehler),
                    "hinweis": _HINWEIS_PARAMETER}
        if eintrag_id is not None:
            return _detail_per_id(con, kategorie, eintrag_id, aggregiere_kinder)
        edition = _db.normalisiere_edition(edition)      # '5.5e' -> '2024' (SYN-P2-001)
        try:
            _db._pruefe_edition(con, edition)
        except ValueError as fehler:
            return {"gefunden": False, "fehler": str(fehler),
                    "hinweis": _HINWEIS_PARAMETER}
        # edition=None: AUSDRUECKLICH editionsuebergreifend suchen - gewaehlt wird unten
        # gezielt; so bleiben andere Fassungen fuer den Zusatz sichtbar (Q1/T6).
        ergebnis = _db.fts_suche(con, name, kategorie=kategorie, edition=None, limit=6)
        kandidaten = ergebnis["treffer"]
        if not kandidaten:
            return {"gefunden": False, "hinweis": HINWEIS_LEER}

        auswahl = _waehle_kandidat(con, name, kategorie, edition, kandidaten)
        if auswahl.absage is not None:
            return auswahl.absage
        gewaehlt, unterabschnitt = auswahl.gewaehlt, auswahl.unterabschnitt
        weitere_abschnitte, exakt = auswahl.weitere_abschnitte, auswahl.exakt

        voll, kinder = _mit_kindern(con, _db.hole_eintrag(con, gewaehlt["id"]),
                                    aggregiere_kinder)
        if gewaehlt.get("weitere_fassungen"):
            # hole_eintrag liefert die blanke Zeile - die vom Dedup weggemergten Fassungen
            # stehen nur am Kandidaten. _facetten_von braucht sie als Rueckfallebene (A5).
            voll = dict(voll)
            voll["weitere_fassungen"] = gewaehlt["weitere_fassungen"]
        antwort = {"gefunden": True, **_detail(voll, con)}
        if unterabschnitt:
            antwort["hinweis_unterabschnitt"] = (
                f"'{name}' steht als Abschnitt '{unterabschnitt}' im gelieferten Eintrag "
                f"'{antwort.get('anzeige_name')}' - den dortigen Abschnitt wiedergeben "
                f"(Quelle/Regelversion wie angegeben).")
        if kinder:
            antwort["hinweis_zusammengefuehrt"] = (
                f"{len(kinder)} Unterabschnitt(e) (z. B. Merkmale/Abstammungen) sind in den "
                f"Regeltext zusammengefuehrt - vollstaendige Optionsbeschreibung.")
        if weitere_abschnitte:
            # SYN-P0-003: der ausfuehrlichste gleichnamige Abschnitt wurde geliefert -
            # die uebrigen (z. B. Statblock-Format-Erklaerung) bleiben transparent und
            # per eintrag_id abrufbar, statt still verschluckt zu werden.
            antwort["weitere_abschnitte"] = weitere_abschnitte
            antwort["hinweis_weitere"] = (
                "Es gibt weitere gleichnamige Abschnitte in dieser Quelle (z. B. die "
                "Erklaerung des Statblock-Feldes). Geliefert wurde der ausfuehrlichste "
                "Regelabschnitt; die uebrigen sind per eintrag_id abrufbar.")
        # Q1/T6: existiert zusaetzlich eine andere Fassung, nur als markierten Zusatz nennen.
        andere = [k for k in exakt if k["edition"] != voll["edition"]]
        if andere:
            antwort["andere_fassungen"] = [_knapp(k, con) for k in andere]
        # #5: Der pauschale hinweis_alter_stand ('keine 2024-Fassung im Bestand') ist FALSCH,
        # wenn eine Standard-Fassung tatsaechlich vorliegt (Nutzer hat ausdruecklich die
        # aeltere Edition angefragt). Dann korrekt formulieren statt in die Irre zu fuehren.
        if (voll["edition"] != _db.STANDARD_EDITION
                and any(k["edition"] == _db.STANDARD_EDITION for k in andere)):
            antwort["hinweis_alter_stand"] = (
                f"⚠️ Dies ist die {voll['edition']}-Fassung. Es gibt AUCH eine "
                f"{_db.STANDARD_EDITION}-Fassung im Bestand (siehe 'andere_fassungen') - "
                f"die aktuelle Version nennen, sofern nicht bewusst die aeltere gewuenscht ist.")
        # F7-Nachzug (Befund 30.07.2026): Fuehrt eine ANDERE Bestandsquelle denselben
        # Eintrag, ist ihre Seite ein echter Beleg - "steht auch im Spielerhandbuch,
        # S. 112". Bis hierher lag sie in der DB und fiel aus der Antwort; die Auskunft
        # konnte nur die Fundstelle der Vorrangquelle nennen.
        #
        # Bewusst KEINE zweite Rangfolge (BACKLOG par. 4 riet ausdruecklich davon ab):
        # das hier ist ein Beleg-Feld, kein Wettbewerb um den kanonischen Text. Und die
        # Seiten sind Bestandswerte - fehlt eine, steht `null`, nie eine Schaetzung.
        fundstellen = [f for f in (gewaehlt.get("weitere_fassungen") or [])
                       if f.get("seite")]
        if fundstellen:
            antwort["weitere_fundstellen"] = gewaehlt["weitere_fassungen"]
            antwort["hinweis_fundstellen"] = (
                "Dieselbe Regel steht auch in den unter 'weitere_fundstellen' genannten "
                "Bestandsquellen. Die Seitenangaben stammen aus dem Bestand - sie duerfen "
                "genannt werden (hilfreich zum Nachschlagen am Tisch), aber NIE geraten "
                "oder auf Quellen uebertragen, die dort nicht stehen (B1/F7).")
        elif gewaehlt.get("weitere_fassungen"):
            antwort["weitere_fundstellen"] = gewaehlt["weitere_fassungen"]
        konflikte, fremdsprachige = _quellabweichungen(
            con, voll, gewaehlt, exakt, weitere_abschnitte)
        if fremdsprachige:
            antwort["fremdsprachige_fassungen"] = fremdsprachige
            antwort["hinweis_fremdfassung"] = (
                "Es existiert eine Fassung in anderer Sprache (per eintrag_id ladbar). "
                "Offizielle Uebersetzungen koennen inhaltlich abweichen - bei "
                "strittigen Detailfragen beide Fassungen pruefen und Abweichungen "
                "offenlegen (⚖️ Errata-/Original-Policy der Runde).")
        if konflikte:
            antwort["konflikt_quellen"] = konflikte
            antwort["hinweis_konflikt"] = (
                "⚖️ Die Fassungen dieser Quellen weichen textlich voneinander ab "
                "(z. B. Uebersetzungs-/Errata-Unterschied). Beide Aussagen nennen und "
                "die Abweichung offenlegen - nicht still die Prioritaetsquelle als "
                "einzige Wahrheit ausgeben; im Zweifel entscheidet die SL/Errata-Policy.")
        # A2-Nachzug (Audit 28.07.2026): Die Nebenlisten des Detail-Pfads trugen die
        # Abenteuer-Kennzeichnung NICHT - nur die Trefferliste der Suche und der
        # gelieferte Eintrag selbst. `weitere_abschnitte`/`andere_fassungen` fuehren aber
        # ebenfalls einen `auszug` aus dem Bestand mit, also denselben Spoiler-Weg.
        _markiere_inhaltsart(con, antwort, antwort.get("weitere_abschnitte") or [],
                            antwort.get("andere_fassungen") or [])
        return antwort
    finally:
        con.close()


# Kategorien, deren Eintraege die Quelle in Intro + Unterabschnitt zerlegt ('<Name>
# Traits' bei DDB) - dort fuehrt der Detailabruf die direkten Kinder zusammen, damit die
# Auskunft VOLLSTAENDIG ist. Die Asymmetrie stand vorher unbegruendet in zwei Wrappern
# verstreut (charakter.py); hier steht sie an EINER sichtbaren Stelle.
_KINDER_AGGREGATION = frozenset({"spezies", "talent"})


def _verwandte_klassenabschnitte(d: dict) -> dict:
    """Bei Klassen die verwandten Abschnitte (Klassenmerkmale, Zauberliste, Unterklassen)
    als NAMEN nachreichen, statt sie in den Regeltext einzusaugen - das haelt die Antwort
    knapp und laesst das Modell gezielt nachladen."""
    if not d.get("gefunden") or not d.get("name_de"):
        return d
    con = _verbinde()
    if con is None:
        return d
    try:
        bedingung, params = _db.kontext_bedingung(con, f"Klassen > {d['name_de']}")
        verwandte = [r[0] for r in con.execute(
            "SELECT name_de FROM eintraege WHERE kategorie='klasse' AND name_de IS NOT NULL "
            f"AND edition = ? AND {bedingung} ORDER BY id",
            [d["edition"], *params])]
        if verwandte:
            d["verwandte_abschnitte"] = verwandte
            d["hinweis_abschnitte"] = (
                "Stufentabelle und Merkmale stehen in den verwandten Abschnitten "
                "(per foliant_hol_eintrag mit kategorie='klasse' abrufbar).")
        return d
    finally:
        con.close()


def foliant_hol_eintrag(kategorie: Kategorie, name: str | None = None,
                        edition: str = "2024", eintrag_id: int | None = None) -> dict:
    """Vollstaendiger Eintrag aus dem Bestand, mit Zitat (Quelle, ggf. Seite,
    Regelversion) - die Suche liefert nur knappe Auszuege, dieses Werkzeug den ganzen Text.

    kategorie ist PFLICHT und sagt, WORUM es geht:
      zauber      Zauber-Steckbrief
      monster     Monster-Statblock
      gegenstand  Gegenstands-Steckbrief
      regel       allgemeiner Regelabschnitt (Zustaende, Bewegung, Rasten, Proben,
                  Regelglossar) - NICHT als Auffangwert benutzen: fuer Zauber, Monster,
                  Gegenstaende, Spezies, Klassen, Hintergruende und Talente gibt es die
                  eigenen Werte, und ein falscher Wert liefert einen fremden Eintrag.
      spezies     Spezies inkl. Merkmalen (Schritt 3 der 2024-Erstellung, B7)
      klasse      Klasse ODER Unterklasse ('Kaempfer', 'Champion'); bei Klassen kommen
                  die verwandten Abschnitte als Namen dazu (Schritt 1, B7)
      hintergrund Hintergrund mit Attributswerten, Ursprungstalent, Ausruestung (Schritt 2)
      talent      Talent (Feat) inkl. Voraussetzungen
    Im Zweifel welche Kategorie: erst foliant_suche_bestand, dessen Treffer nennen sie.

    name deutsch oder englisch - alternativ eintrag_id aus einem Suchtreffer (dann wird
    name ignoriert). edition Standard '2024'; eine andere Regelversion (z. B. '2014')
    laesst sich gezielt anfordern und wird nie still ersetzt. Bei Mehrdeutigkeit kommen
    Kandidaten zurueck - dann rueckfragen statt raten.
    KERNREGELN: nur aus dem Bestand; Quelle + Regelversion nennen;
    Deutsch-first (Original in Klammern)."""
    start = time.monotonic()
    d = _hole_detail(kategorie, name, edition, eintrag_id=eintrag_id,
                     aggregiere_kinder=kategorie in _KINDER_AGGREGATION)
    if eintrag_id is not None:
        suchweg = "direkt_id"        # Nachladen einer Referenz - kein Kurations-Signal
    elif "fehler" in d:
        suchweg = "fehler"
    else:
        suchweg = "name"
    # werkzeug bleibt kategoriebasiert (hol_<kategorie>), damit der Suchbericht ueber die
    # Zusammenlegung der zwoelf hol_*-Werkzeuge hinweg vergleichbar bleibt.
    _protokoll.protokolliere(
        werkzeug=f"hol_{kategorie}", kategorie=kategorie,
        suchbegriff=None if eintrag_id is not None else name, edition=edition,
        anzahl_treffer=(len(d.get("kandidaten", [])) or int(bool(d.get("gefunden")))),
        suchweg=suchweg, mehrdeutig=bool(d.get("mehrdeutig")),
        gefunden=d.get("gefunden"),
        dauer_ms=(time.monotonic() - start) * 1000)
    return _verwandte_klassenabschnitte(d) if kategorie == "klasse" else d


def foliant_uebersetze_begriff(begriff: str,
        richtung: Literal["en_de", "de_en", "auto"] = "auto") -> dict:
    """Glossar-Nachschlag DE<->EN fuer Spielbegriffe (auch Abkuerzungen wie AoO/HP/AC).
    richtung: 'en_de', 'de_en' oder 'auto' (beide probieren) - andere Werte werden mit
    'fehler' abgelehnt. Liefert offizielle deutsche Begriffe (Ulisses/offizielle Buecher)
    samt Herkunft; offiziell=false bedeutet: mit '*' kennzeichnen ('* keine offizielle
    deutsche Uebersetzung', S5). Ohne EXAKTEN Eintrag kommen hoechstens
    'aehnliche_begriffe' (Schreibvarianten) zurueck - die sind KEINE bestaetigte
    Uebersetzung des angefragten Begriffs. KERNREGELN: englisches Original immer in
    Klammern; nichts erfinden - kein Treffer heisst kein offizieller Begriff."""
    start = time.monotonic()
    antwort = _uebersetze_begriff_impl(begriff, richtung)
    if "fehler" in antwort:
        suchweg = "fehler"
    elif antwort.get("gefunden"):
        suchweg = "exakt"
    elif antwort.get("aehnliche_begriffe"):
        suchweg = "fuzzy"
    else:
        suchweg = "-"                # direkte Glossar-Luecke: Kurations-Signal (O4)
    _protokoll.protokolliere(
        werkzeug="uebersetze_begriff", suchbegriff=begriff,
        anzahl_treffer=len(antwort.get("begriffe", [])
                           or antwort.get("aehnliche_begriffe", [])),
        suchweg=suchweg, gefunden=antwort.get("gefunden"),
        dauer_ms=(time.monotonic() - start) * 1000)
    return antwort


def _uebersetze_begriff_impl(begriff: str, richtung: str) -> dict:
    """Kernlogik; Tool-Beschreibung und Protokoll-Hook sitzen im oeffentlichen Wrapper."""
    # Befund 30.07.2026: Ein leerer Begriff lief bis zum Schluss durch und kam als
    # "Kein Glossar-Eintrag im Bestand" zurueck - eine Luecken-Meldung fuer eine Frage,
    # die nie gestellt wurde. Dieselbe Antwortklasse wie SYN-P0-006, und hier besonders
    # irrefuehrend: das Modell haette daraus geschlossen, es gebe keine Uebersetzung.
    if not (begriff and begriff.strip()):
        return {"gefunden": False, "fehler": "kein_kriterium",
                "hinweis": "Bitte einen Begriff angeben. Das ist ein PARAMETER-Fehler, "
                           "KEIN fehlender Glossareintrag - dem Nutzer keine Fehlanzeige "
                           "melden (B1/B4)."}
    if richtung not in ("en_de", "de_en", "auto"):
        return {"gefunden": False,
                "fehler": f"Unbekannte richtung {richtung!r} - gueltig: 'en_de', "
                          f"'de_en', 'auto'.",
                "hinweis": "Parameterfehler - dem Nutzer NICHT 'kein Glossareintrag' "
                           "melden, sondern den Aufruf korrigieren."}
    con = _verbinde()
    if con is None:
        return {"gefunden": False, "hinweis": HINWEIS_DB_FEHLT}
    try:
        richtungen = [richtung] if richtung != "auto" else ["en_de", "de_en"]
        zeilen: list[dict] = []
        for r in richtungen:
            for z in _glossar.lookup(con, begriff, richtung=r):
                if z not in zeilen:
                    zeilen.append(z)

        def _zeile(z: dict) -> dict:
            return {"term_de": z["term_de"], "term_en": z["term_en"],
                    "offiziell": bool(z["offiziell"]),
                    "anzeige": _glossar.markiere(z["term_de"], z["term_en"],
                                                 bool(z["offiziell"])),
                    "begriffsquelle": z.get("quelle"),
                    "edition_quelle": z.get("edition_quelle")}

        # SYN-P0-001: Nur EXAKTE Zeilen sind eine Uebersetzung des angefragten Begriffs.
        # Fuzzy-Zeilen ('Aktionen'~'Reaktionen', aber auch harmlose Flexion) kommen
        # getrennt und ausdruecklich unbestaetigt zurueck.
        exakte = [z for z in zeilen if z["match"] == "exakt"]
        if exakte:
            return {"gefunden": True,
                    "begriffe": [_zeile(z) for z in exakte[:10]],
                    "hinweis_stern": _HINWEIS_STERN}
        aehnliche = [z for z in zeilen if z["match"] == "fuzzy"]
        if aehnliche:
            return {"gefunden": False,
                    "aehnliche_begriffe": [{**_zeile(z), "score": z.get("score")}
                                           for z in aehnliche[:5]],
                    "hinweis": ("Kein EXAKTER Glossar-Eintrag zu diesem Begriff. Die "
                                "aehnlichen Zeilen sind Schreib-/Flexionsvarianten ODER "
                                "fremde Begriffe - NICHT ungeprueft als Uebersetzung des "
                                "angefragten Begriffs ausgeben. Nur bei offensichtlicher "
                                "Flexion (Singular/Plural) verwenden und das kenntlich "
                                "machen; sonst gilt: keine offizielle Uebersetzung im "
                                "Bestand (S3 Stufe 4/S5).")}
        return {"gefunden": False,
                "hinweis": ("Kein Glossar-Eintrag im Bestand. Falls du den Begriff dennoch "
                            "brauchst: konsistente deutsche Wiedergabe mit * verwenden und "
                            "das * einmal erlaeutern (S3 Stufe 4/S5) - NICHT Englisch mitten "
                            "im Satz.")}
    finally:
        con.close()
