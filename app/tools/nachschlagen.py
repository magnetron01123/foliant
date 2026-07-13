"""Nachschlage-Werkzeuge (F1/F2). Namensschema foliant_<verb>_<nomen> (BP #2).
Suche = KNAPPE Trefferliste; Detail = volle Ausgabe (BP #1).

Review-Fund, Kanal 3 (zuverlaessigster Weg zum Modell): Grounding-Hinweise stehen IN den
Tool-AUSGABEN - eine leere Suche sagt explizit "Nichts im Bestand - ehrlich sagen...".
Kanal 2: Kurzfassung der Kernregeln in jeder Tool-Beschreibung (= Docstring)."""
from __future__ import annotations

import re
import sqlite3
from typing import Literal

from rapidfuzz import fuzz

from app import db as _db
from app import facetten as _facetten
from app import glossar as _glossar

# SYN-P1-003: geschlossene Wertemengen als Literal -> FastMCP generiert daraus
# enum-Schemas, der Client faengt Fehlaufrufe VOR dem Server ab. Die
# Laufzeitvalidierung (SYN-P0-006) bleibt als zweite Leitplanke bestehen.
Kategorie = Literal["regel", "zauber", "monster", "gegenstand", "spezies", "klasse",
                    "hintergrund", "talent"]

HINWEIS_LEER = ("Nichts im Bestand gefunden. Sag das ehrlich mit ❌ ('Dazu finde ich nichts "
                "im Foliant-Bestand') und antworte NICHT aus Allgemeinwissen, 2014-Regeln oder "
                "Homebrew (B1). Eventuell fehlt schlicht ein Buch im Bestand (B2). Falls danach "
                "eine Websuche gewuenscht ist: Ergebnisse strikt getrennt und gekennzeichnet "
                "ausgeben ('🌐 Aus dem Web, NICHT aus dem Foliant-Bestand, ungeprueft') - nie "
                "mit Bestandsinhalten vermischen; Abenteuer-/Kampagnen-Spoiler bleiben auch "
                "dort tabu (🚫).")
HINWEIS_ALT = ("Keine 2024-Fassung im Bestand, nur ein aelterer Regelstand. Klar kennzeichnen "
               "mit ⚠️: 'Keine 2024-Fassung im Bestand; hier der aeltere Stand - ggf. an die "
               "aktuellen Regeln anzupassen.' (V4/B5)")
HINWEIS_MEHRDEUTIG = ("Mehrere Eintraege passen. NICHT raten (B4): nenne die Kandidaten mit "
                      "Unterscheidungsmerkmal (Kategorie/Quelle/Version) und frag zurueck - "
                      "oder lade den richtigen direkt per eintrag_id nach (SYN-P1-002).")
HINWEIS_DB_FEHLT = ("Der Regelbestand ist noch leer (keine Datenbank/keine Importe). Sag ehrlich, "
                    "dass noch keine Quellen importiert sind - erfinde keine Regeln (B1).")
_HINWEIS_STERN = "* = keine offizielle deutsche Uebersetzung (einmal erlaeutern, S5)"


def _verbinde() -> sqlite3.Connection | None:
    # SYN-P1-005/TECH-020: Serving-Verbindungen sind READ-ONLY - die Tools schreiben nie,
    # und so kann auch eine kompromittierte Laufzeit den Bestand nicht veraendern.
    pfad = _db.standard_pfad()
    if not pfad.exists():
        return None
    return _db.connect_readonly(str(pfad))


def _zitat(e: dict) -> str:
    """F7/P4: Quelle immer, Seite nur wenn die Quelle eine hat, Version immer."""
    teile = [f"Quelle: {e['quelle_titel']}"]
    if e.get("seite"):
        teile.append(f"S. {e['seite']}")
    teile.append(f"Regelversion: {e['edition']}")
    return " · ".join(teile)


def _knapp(t: dict) -> dict:
    """Knapper Suchtreffer (BP #1): Name, Auszug, Quelle, ggf. Seite, Version.
    eintrag_id/quelle_kuerzel (SYN-P1-002): stabile Referenz - ein ausgewaehlter
    Treffer laesst sich per foliant_hol_*(eintrag_id=...) EXAKT nachladen, statt ueber
    den Namen erneut zu raten (der Rundlauf wechselte sonst still die Quelle)."""
    k = {"eintrag_id": t["id"], "name_de": t["name_de"], "name_en": t["name_en"],
         "kategorie": t["kategorie"], "edition": t["edition"],
         "quelle": t["quelle_titel"], "quelle_kuerzel": t["quelle"],
         "auszug": t["auszug"]}
    if t.get("seite"):
        k["seite"] = t["seite"]
    if t.get("weitere_quellen"):
        # A3: fachliche Dublette kanonisch dedupliziert - Provenienz bleibt sichtbar.
        k["weitere_quellen"] = t["weitere_quellen"]
    return k


def _reichere_facetten_an(con: sqlite3.Connection, *treffer_listen: list[dict]) -> None:
    """#2: knappe Zauber-/Monster-Treffer um eine kompakte Facette ('Grad 3' bzw. 'HG 1')
    anreichern - genau das Feld, nach dem ein Spieler triagiert. Aus dem Body geparst
    (zauber_meta/monster_meta sind auf dem Bestand leer, s. app/facetten.py). EINE
    Batch-Abfrage der Textkoepfe fuer alle gezeigten Treffer (BP #1: kein Body im Output)."""
    ids = {k["eintrag_id"] for liste in treffer_listen for k in liste
           if k.get("kategorie") in ("zauber", "monster")}
    if not ids:
        return
    marker = ",".join("?" * len(ids))
    koepfe = {r[0]: r[1] for r in con.execute(
        f"SELECT id, substr(body_md, 1, 900) FROM eintraege WHERE id IN ({marker})",
        tuple(ids))}
    for liste in treffer_listen:
        for k in liste:
            body = koepfe.get(k["eintrag_id"])
            if not body:
                continue
            if k["kategorie"] == "zauber":
                info = _facetten.zauber_kurz(body)
            elif k["kategorie"] == "monster":
                info = _facetten.hg_kurz(body)
            else:
                info = None
            if info:
                k["kurzinfo"] = info


# Fuzzy-Schwelle fuer die Namensrelevanz eines Kandidaten (#1). BEWUSST >= 90: die
# Fuzzy-Naehe 'Aktionen'~'Reaktionen' (88.9, SYN-P0-001) darf NIE als Namenstreffer
# zaehlen; kleine Tippfehler ('Missle'~'Missile' ~96) liegen klar darueber.
_NAME_MIN = 90.0


def _name_score(k: dict, ziele: set[str]) -> float:
    """Relevanz des Kandidatennamens zur Anfrage (0-100): exakt/Praefix = 100, sonst der
    beste rapidfuzz.ratio gegen die (normalisierten) Anfrage-Varianten `ziele`. Trennt
    echte Namenstreffer von blossen Body-Erwaehnungen (deren Name gar nicht passt)."""
    namen = _eintrag_namen(k)
    if namen & ziele:
        return 100.0
    best = 0.0
    for n in namen:
        for z in ziele:
            if not n or not z:
                continue
            if n.startswith(z) or z.startswith(n):
                return 100.0
            best = max(best, fuzz.ratio(n, z))
    return best


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
        echo["klasse"] = klasse
    if schadensart:
        schaden_key = _facetten.schadensart_schluessel(schadensart)
        if not schaden_key:
            return None, None, {}, {"treffer": [], "fehler": f"unbekannte Schadensart {schadensart!r}",
                    "gueltige_schadensarten": _facetten.schadensarten_anzeige(),
                    "hinweis": "Gueltige Schadensart aus 'gueltige_schadensarten' nutzen."}
        echo["schadensart"] = schaden_key
    if hg:
        echo["hg"] = str(hg).strip()
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


def _struktur_filter(con, kategorie, edition, praedikat, echo, limit=25) -> dict:
    """Reiner Struktur-Filter (kein Suchbegriff): scannt eine Kategorie und filtert per
    Praedikat aus dem Body. Deutsch-first-Dedup, knappe Treffer mit 'kurzinfo'."""
    try:
        edition = _db.normalisiere_edition(edition)
        _db._pruefe_edition(con, edition)
    except ValueError as fehler:
        return {"treffer": [], "fehler": str(fehler),
                "hinweis": "Ungueltiger PARAMETER - KEIN 'nicht im Bestand' (B1/B4)."}
    roh: list[dict] = []
    for r in con.execute(
            """SELECT e.id, e.kategorie, e.name_de, e.name_en, e.sprache, e.edition,
                      e.seite, e.body_md, q.kuerzel AS quelle, q.titel AS quelle_titel,
                      q.prioritaet
               FROM eintraege e JOIN quellen q ON q.id = e.quelle_id
               WHERE e.kategorie = ? AND e.edition = ?""", (kategorie, edition)):
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
        k = _knapp(t)
        info = (_facetten.zauber_kurz(t.get("body_md") or "") if kategorie == "zauber"
                else _facetten.hg_kurz(t.get("body_md") or ""))
        if info:
            k["kurzinfo"] = info
        treffer.append(k)
    antwort = {"treffer": treffer, "anzahl_gesamt": len(deduped),
               "gefiltert_nach": {**echo, "kategorie": kategorie, "edition": edition}}
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


def foliant_suche_bestand(suchbegriff: str | None = None, kategorie: Kategorie | None = None,
                          edition: str = "2024", quelle_kuerzel: str | None = None,
                          grad: int | None = None, schule: str | None = None,
                          klasse: str | None = None, schadensart: str | None = None,
                          hg: str | None = None, typ: str | None = None) -> dict:
    """Findet Eintraege im GESAMTEN Bestand - per Freitext ODER per STRUKTUR-Filter (oder
    beides kombiniert). Liefert KNAPPE Treffer (Name, Auszug, Quelle, ggf. Seite,
    Regelversion; Zauber/Monster zusaetzlich 'kurzinfo' mit Grad bzw. HG) - Details per
    foliant_hol_*.
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
    aus dem Bestand; Quelle + Regelversion nennen; Deutsch-first (Original in Klammern)."""
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
            return _struktur_filter(con, kat_filter, edition, praedikat, echo)
        try:
            ergebnis = _db.fts_suche(con, suchbegriff, kategorie=(kat_filter or kategorie),
                                     edition=edition, quelle=quelle_kuerzel)
        except ValueError as fehler_v:
            # SYN-P0-006: Parameterfehler (Edition/Kategorie/Quelle) sind KEIN leerer
            # Befund - vor dem Fix bekam das Modell hier den B1-Leerhinweis und meldete
            # dem Nutzer ein falsches 'nicht im Bestand' fuer vorhandene Inhalte.
            return {"treffer": [], "fehler": str(fehler_v),
                    "hinweis": "Ungueltiger PARAMETER - das ist KEIN 'nicht im Bestand'. "
                               "Aufruf mit einem gueltigen Wert (siehe fehler) "
                               "wiederholen; dem Nutzer keine Fehlanzeige melden (B1/B4)."}
        antwort: dict = {"treffer": [_knapp(t) for t in ergebnis["treffer"]]}
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
                antwort["aeltere_staende"] = [_knapp(t) for t in aeltere]
            if neuere:
                antwort["andere_fassungen"] = [_knapp(t) for t in neuere]
        elif andere:
            # Explizit andere Edition angefragt: neutral benennen - die uebrigen
            # Fassungen (z. B. 2024) sind nicht 'aelter' (A1).
            antwort["andere_fassungen"] = [_knapp(t) for t in andere]
        if ergebnis["suchweg"].startswith("glossar:"):
            antwort["hinweis_suchweg"] = (f"Treffer ueber das Glossar gefunden "
                                          f"({suchbegriff} -> {ergebnis['suchweg'][8:]}).")
        elif ergebnis["suchweg"] == "fuzzy":
            antwort["hinweis_suchweg"] = "Aehnliche Schreibweise angenommen (Tippfehler-Toleranz)."
        if praedikat is not None:
            # Suchbegriff UND Struktur-Filter: die Volltext-Treffer zusaetzlich strukturell
            # einschraenken (UND-Semantik), bevor der Leer-Hinweis entscheidet.
            _nachfiltern_facetten(con, antwort, praedikat)
            antwort["gefiltert_nach"] = echo
        if not antwort["treffer"]:
            if antwort.get("aeltere_staende"):
                antwort["hinweis"] = HINWEIS_ALT
            elif andere:
                antwort["hinweis"] = (f"In Regelversion {edition} nichts im Bestand; "
                                      f"es gibt aber Fassungen anderer Versionen (siehe "
                                      f"'andere_fassungen') - klar unterscheiden (V5).")
            else:
                antwort["hinweis"] = HINWEIS_LEER
        _reichere_facetten_an(con, antwort["treffer"],
                              antwort.get("aeltere_staende", []),
                              antwort.get("andere_fassungen", []))
        return antwort
    finally:
        con.close()


def _anzeige_name(con: sqlite3.Connection, e: dict) -> str:
    """Deutsch-first-Anzeige (S3/S4): deutscher Begriff mit Englisch in Klammern; kommt der
    Eintrag aus einer deutschen Quelle, ist der Begriff offiziell (kein '*'). Englische
    Eintraege werden ueber das Glossar annotiert; ohne offiziellen Treffer -> '*' (S5)."""
    if e.get("name_de") and e.get("sprache") == "de":
        name_en = e.get("name_en")
        if not name_en:
            # dt. Quellen tragen kein Englisch am Eintrag -> Original via Glossar (S4);
            # NUR exakte Zeilen (SYN-P0-001: eine Fuzzy-Zeile haengte sonst ein FREMDES
            # Original an, 'Aktionen (Reactions)'); ohne exakten Treffer lieber ohne
            # Klammer als 'Feuerball (Feuerball)'.
            zeilen = [z for z in _glossar.lookup(con, e["name_de"], richtung="de_en")
                      if z["match"] == "exakt"]
            name_en = zeilen[0]["term_en"] if zeilen else None
        if name_en and name_en.strip().lower() != e["name_de"].strip().lower():
            return _glossar.markiere(e["name_de"], name_en, offiziell=True)
        return e["name_de"]
    name_en = e.get("name_en") or e.get("name_de") or "?"
    de, offiziell = _glossar.term_de(con, name_en)
    if de and de != name_en:
        return _glossar.markiere(de, name_en, offiziell)
    return name_en


def _facetten_von(con: sqlite3.Connection, e: dict) -> dict | None:
    """Strukturierte Filter-Facetten aus dem zauber_meta/monster_meta-Seitenwagen (heute nur
    aus Open5e befuellt): ADDITIV zum verbatim body_md, ersetzen den Regeltext nie. Zauber ->
    grad/schule/klassen, Monster -> hg/typ. None, wenn keine Zeile/Tabelle vorhanden ist
    (dann fehlt das Feld schlicht - kein Raten)."""
    spez = {"zauber": ("zauber_meta", ("grad", "schule", "klassen")),
            "monster": ("monster_meta", ("hg", "typ"))}.get(e["kategorie"])
    if not spez:
        return None
    tabelle, felder = spez
    try:
        row = con.execute(f"SELECT {', '.join(felder)} FROM {tabelle} WHERE eintrag_id = ?",
                          (e["id"],)).fetchone()
    except sqlite3.OperationalError:
        return None                                   # Alt-DB ohne Facetten-Tabelle
    if not row:
        return None
    return {f: row[f] for f in felder if row[f] is not None} or None


def _detail(e: dict, con: sqlite3.Connection) -> dict:
    d = {"anzeige_name": _anzeige_name(con, e),
         "name_de": e["name_de"], "name_en": e["name_en"], "kategorie": e["kategorie"],
         "edition": e["edition"], "sprache": e["sprache"], "quelle": e["quelle_titel"],
         "seite": e.get("seite"), "zitat": _zitat(e), "regeltext_md": e["body_md"],
         "hinweis_sprache_begriffe": _HINWEIS_STERN}
    if e.get("lizenz"):
        # A12/Q6: die Quellenlizenz wird im Detailpfad nicht verworfen; CC-BY verlangt
        # die mitgefuehrte Attribution (Wortlaut konsistent mit docs/ATTRIBUTION.md).
        d["lizenz"] = e["lizenz"]
        if str(e["lizenz"]).upper().startswith("CC-BY"):
            d["attribution"] = ("Enthaelt Material aus dem System Reference Document "
                                "5.2.1 von Wizards of the Coast LLC, lizenziert unter "
                                "CC-BY-4.0 (Details: docs/ATTRIBUTION.md).")
    # SYN-P0-007: Abenteuer-/Setting-Quellen sind bewusst geladen (Terminologie), aber
    # jede Antwort daraus traegt die Kennzeichnung - Spoiler-Schutz und 'kein finales
    # Spieler-Regelwerk' duerfen nicht allein am Quellentitel haengen. Defensiv gegen
    # Bestands-DBs ohne die Spalte (vor der Migration importiert).
    try:
        art = con.execute(
            "SELECT q.inhaltsart FROM quellen q JOIN eintraege e2 ON e2.quelle_id = q.id "
            "WHERE e2.id = ?", (e["id"],)).fetchone()
    except sqlite3.OperationalError:
        art = None
    if art and art[0] == "abenteuer_setting":
        d["inhaltsart"] = art[0]
        d["hinweis_inhaltsart"] = (
            "🚫 Dieser Eintrag stammt aus einem ABENTEUER-/SETTING-Band (nur fuer "
            "Terminologie/Werte geladen): Handlung, Geheimnisse und Ortsdetails NIE "
            "wiedergeben (Spoiler-Schutz, oberste Regel); reine Regel-/Wertangaben "
            "sind ok.")
    if e["edition"] != _db.STANDARD_EDITION:
        d["hinweis_alter_stand"] = HINWEIS_ALT
    if e.get("sprache") == "en":
        # S3/S5: dem Modell die AMTLICHEN deutschen Begriffe INLINE mitgeben, statt sie nur
        # anzumahnen - genau die Luecke, an der eine Antwort sonst englisch stehen bleibt
        # (Warlock-Test 13.07.2026: Cloudkill/Bane/Greater Invisibility blieben englisch,
        # obwohl das Glossar Todeswolke/Verderben/Maechtige Unsichtbarkeit kennt).
        treffer = _glossar.begriffe_im_text(con, e.get("body_md") or "")
        hinweis = ("Regeltext liegt nur ENGLISCH vor. Antworte dennoch auf Deutsch und "
                   "uebersetze JEDEN englischen Fachbegriff: ")
        if treffer:
            d["begriffe_deutsch"] = {z["term_en"]: z["term_de"] for z in treffer}
            hinweis += ("die in 'begriffe_deutsch' aufgefuehrten Begriffe tragen die "
                        "OFFIZIELLE deutsche Form - diese verwenden (Original in Klammern, "
                        "KEIN *). ")
        hinweis += ("Jeden weiteren englischen Fachbegriff (Merkmals-/Zaubernamen), der dort "
                    "nicht steht, konsistent deutsch wiedergeben und mit * markieren "
                    "('* keine offizielle deutsche Uebersetzung', einmal erlaeutern). Das "
                    "*-System NICHT durch Prosa wie 'sinngemaess uebertragen' ersetzen und "
                    "nichts unuebersetzt englisch stehen lassen (S3/S5).")
        d["hinweis_uebersetzung"] = hinweis
    fac = _facetten_von(con, e)
    if fac:
        d["facetten"] = fac
    return d


# Kanonische Definition in app/glossar.py (gemeinsam mit dem Such-Ranking, SYN-P0-002).
_KLAMMER_SUFFIX = _glossar.KLAMMER_SUFFIX


def _eintrag_namen(k: dict) -> set[str]:
    """Namensvarianten eines Eintrags fuer den Exakt-Vergleich, kanonisch normalisiert
    (glossar.norm_begriff: case-/diakritika-/NFD-fest - PDF-Namen kommen teils
    NFD-dekomponiert an, S11/A3). Das srd-de-Namensschema '<Klasse>-Unterklasse: <Name>'
    zaehlt auch mit dem blanken Unterklassen-Namen als exakt - sonst gewinnt bei
    foliant_hol_klasse('Champion') der englische Open5e-Eintrag (S10). Klammer-Suffixe
    zaehlen zusaetzlich OHNE Zusatz (SYN-P0-002)."""
    namen = {_glossar.norm_begriff(k["name_de"]), _glossar.norm_begriff(k["name_en"])}
    m = re.match(r".+-unterklasse:\s*(.+)$", _glossar.norm_begriff(k["name_de"]))
    if m:
        namen.add(m.group(1).strip())
    for n in list(namen):
        ohne_zusatz = _KLAMMER_SUFFIX.sub("", n).strip()
        if ohne_zusatz:
            namen.add(ohne_zusatz)
    return namen - {""}


def _texte_weichen_ab(a: str, b: str) -> bool:
    """Wesentliche Textabweichung zweier Fassungen (SYN-P1-009). Normalisiert
    (Kontextzeile weg, Kleinschreibung, Whitespace kollabiert), dann rapidfuzz-ratio
    < 90. Nur fuer GLEICHSPRACHIGE Fassungen aussagekraeftig - DE/EN-Paare weichen
    naturgemaess ab und laufen stattdessen in 'fremdsprachige_fassungen'."""
    from rapidfuzz import fuzz

    def norm(t: str) -> str:
        t = _KONTEXT_RE.sub("", t or "", count=1)
        return " ".join(t.lower().split())
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    return fuzz.ratio(na, nb) < 90


_KONTEXT_RE = re.compile(r"^\*Kontext: (.+?)\*")


def _kontext_von(body: str | None) -> str:
    m = _KONTEXT_RE.match(body or "")
    return m.group(1) if m else ""


def _kinder_texte(con: sqlite3.Connection, voll: dict) -> list[str]:
    """Direkte Unterabschnitte eines Options-Eintrags fuer die Detail-ZUSAMMENFUEHRUNG (DDB
    zerlegt eine Option in Intro + '<Name> Traits' + ggf. Abstammungen; die Werte stehen im
    Unterabschnitt). Kind = gleiche Kategorie/Edition/Quelle UND Kontext exakt
    '<Eltern-Kontext> > <Eltern-Name>'. So bleibt es auf DIREKTE Kinder begrenzt (kein
    Einsaugen ganzer Kapitelbaeume) und quellen-/editionsrein. Rueckgabe: formatierte
    Abschnitte (Unterabschnitts-Name als Zwischenueberschrift, Kontextzeile entfernt)."""
    eltern_kontext = _kontext_von(voll.get("body_md"))
    namen = {n for n in (voll.get("name_en"), voll.get("name_de")) if n}
    ziele = {f"{eltern_kontext} > {n}" if eltern_kontext else n for n in namen}
    stuecke: list[str] = []
    for r in con.execute(
            "SELECT e.name_de, e.name_en, e.body_md FROM eintraege e "
            "JOIN quellen q ON q.id = e.quelle_id WHERE e.kategorie = ? AND e.edition = ? "
            "AND q.kuerzel = ? AND e.id != ? ORDER BY e.id",
            (voll["kategorie"], voll["edition"], voll["quelle"], voll["id"])):
        if _kontext_von(r["body_md"]) in ziele:
            kname = (r["name_de"] or r["name_en"] or "").strip()
            koerper = _KONTEXT_RE.sub("", r["body_md"], count=1).strip()
            stuecke.append(f"### {kname}\n\n{koerper}" if kname else koerper)
    return stuecke


def _hole_detail(kategorie: str, name: str, edition: str = _db.STANDARD_EDITION,
                 aggregiere_kinder: bool = False,
                 eintrag_id: int | None = None) -> dict:
    """Detail-Auswahl (A1): edition ist die GEWUENSCHTE Regelversion (Standard 2024).
    Beim Standard bleibt der B5-Fallback (nur aeltere Fassung -> liefern + Warnung);
    eine AUSDRUECKLICH angeforderte andere Edition wird nie still ersetzt - fehlt sie,
    kommt ein ehrliches 'nicht gefunden' mit den vorhandenen Fassungen.
    aggregiere_kinder=True fuehrt direkte Unterabschnitte (z. B. '<Spezies> Traits') in den
    Regeltext zusammen, damit die Detailauskunft VOLLSTAENDIG ist (DDB-Optionen)."""
    con = _verbinde()
    if con is None:
        return {"gefunden": False, "hinweis": HINWEIS_DB_FEHLT}
    try:
        if eintrag_id is not None:
            # SYN-P1-002: Direktabruf per stabiler Referenz aus einem Suchtreffer -
            # KEINE Namensaufloesung, keine Editions-/Prioritaetswahl: exakt DIESER
            # Eintrag oder ein strukturierter Fehler (nie ein stiller Quellenwechsel).
            voll = _db.hole_eintrag(con, int(eintrag_id))
            if voll is None:
                return {"gefunden": False,
                        "fehler": f"eintrag_id {eintrag_id} existiert nicht (Referenz "
                                  f"veraltet? Neu suchen)."}
            if voll["kategorie"] != kategorie:
                return {"gefunden": False,
                        "fehler": f"eintrag_id {eintrag_id} ist Kategorie "
                                  f"'{voll['kategorie']}' - dieses Werkzeug liefert "
                                  f"'{kategorie}' (passendes foliant_hol_* nutzen)."}
            kinder = _kinder_texte(con, voll) if aggregiere_kinder else []
            if kinder:
                voll = dict(voll)
                voll["body_md"] = voll["body_md"].rstrip() + "\n\n" + "\n\n".join(kinder)
            return {"gefunden": True, **_detail(voll, con)}
        edition = _db.normalisiere_edition(edition)      # '5.5e' -> '2024' (SYN-P2-001)
        try:
            _db._pruefe_edition(con, edition)
        except ValueError as fehler:
            return {"gefunden": False, "fehler": str(fehler)}
        # edition=None: AUSDRUECKLICH editionsuebergreifend suchen - gewaehlt wird unten
        # gezielt; so bleiben andere Fassungen fuer den Zusatz sichtbar (Q1/T6).
        ergebnis = _db.fts_suche(con, name, kategorie=kategorie, edition=None, limit=6)
        kandidaten = ergebnis["treffer"]
        if not kandidaten:
            return {"gefunden": False, "hinweis": HINWEIS_LEER}

        # Exakt zaehlt auch der per Glossar aufgeloeste Begriff ('Feuerball' <-> 'Fireball'):
        # nach Begriffsaufloesung ist das KEIN Raten (B3/B4). NUR exakte Glossarbeziehungen
        # (SYN-P0-001: die Fuzzy-Naehe 'Aktionen'~'Reaktionen' machte einen FREMDEN Eintrag
        # zum Exakt-Treffer). Die prioritaets-sortierte Trefferliste stellt dabei deutsche
        # Quellen nach vorn (S10/Q2).
        varianten = {_glossar.norm_begriff(name)}
        varianten |= {_glossar.norm_begriff(a)
                      for a in _db._glossar_alternativen(con, name, nur_exakt=True)}
        exakt = [k for k in kandidaten if _eintrag_namen(k) & varianten]
        ziel_exakt = [k for k in exakt if k["edition"] == edition]

        gewaehlt = None
        weitere_abschnitte: list[dict] = []
        if len(ziel_exakt) > 1 and \
                len({k["quelle"] for k in ziel_exakt}) < len(ziel_exakt):
            # Mehrere exakte Treffer aus DERSELBEN Quelle sind verschiedene TEXTSTELLEN
            # desselben Begriffs (Spielregel-Kapitel vs. Statblock-Format-Meta 'Elemente
            # von Wertekästen' vs. Glossar-Kurzverweis) - SYN-P0-003/codex DND-002.
            # Codex-Kriterium: KERNABSCHNITT priorisieren, nicht bloss raten. Der
            # AUSFUEHRLICHSTE Abschnitt ist praktisch immer der gesuchte (Bonusaktionen
            # 837 vs. 200, Temp-TP 1665 vs. 235) -> ihn deterministisch waehlen; die
            # uebrigen als nachladbare `weitere_abschnitte` ausweisen (nichts verstecken,
            # per eintrag_id abrufbar). Verschiedene QUELLEN sind dagegen Fassungen
            # derselben Sache -> Prioritaet entscheidet (S10/Q2, z. B. Champion).
            def _regeltext_laenge(v: dict) -> int:
                # Laenge OHNE die Kontext-Breadcrumb-Zeile messen (die verfaelscht sonst
                # den Vergleich - ein langer Kontext taeuscht Textumfang vor).
                return len(_KONTEXT_RE.sub("", v.get("body_md") or "", count=1))
            voll_paare = [(_db.hole_eintrag(con, k["id"]), k) for k in ziel_exakt]
            voll_paare = [(v, k) for v, k in voll_paare if v]
            voll_paare.sort(key=lambda vk: _regeltext_laenge(vk[0]), reverse=True)
            gewaehlt = voll_paare[0][1]
            weitere_abschnitte = [_knapp(k) for _v, k in voll_paare[1:]]
        elif ziel_exakt:
            gewaehlt = ziel_exakt[0]
        elif exakt:
            if edition == _db.STANDARD_EDITION:
                gewaehlt = exakt[0]      # nur aeltere Fassung vorhanden (B5)
            else:
                return {"gefunden": False,
                        "vorhandene_fassungen": [_knapp(k) for k in exakt[:6]],
                        "hinweis": (f"Keine Fassung der Regelversion {edition} im "
                                    f"Bestand - vorhandene Fassungen siehe "
                                    f"'vorhandene_fassungen'; nicht still ersetzen (V5).")}
        elif len(kandidaten) == 1 and (edition == _db.STANDARD_EDITION
                                       or kandidaten[0]["edition"] == edition):
            gewaehlt = kandidaten[0]
        if gewaehlt is None:
            # #1: reine Body-Erwaehnungen (deren Name gar nicht zur Anfrage passt, z. B.
            # 'Schild'/'Zauberplaetze' bei der Suche nach 'Magic Missile') aus der
            # Kandidatenliste draengen. Bleibt genau EIN starker Namenstreffer der
            # gewuenschten Edition (auch vertippt: 'Missle'->'Missile'), ihn direkt liefern
            # statt rueckzufragen. Sonst die BEREINIGTE Kandidatenliste zeigen.
            relevante = [k for k in kandidaten if _name_score(k, varianten) >= _NAME_MIN]
            rel_std = [k for k in relevante if k["edition"] == edition]
            if len(rel_std) == 1:
                gewaehlt = rel_std[0]
            elif len(relevante) == 1:
                gewaehlt = relevante[0]
            else:
                anzeige = relevante or kandidaten
                return {"gefunden": False, "mehrdeutig": True,
                        "kandidaten": [_knapp(k) for k in anzeige[:6]],
                        "hinweis": HINWEIS_MEHRDEUTIG}

        voll = _db.hole_eintrag(con, gewaehlt["id"])
        kinder = _kinder_texte(con, voll) if aggregiere_kinder else []
        if kinder:
            voll = dict(voll)
            voll["body_md"] = voll["body_md"].rstrip() + "\n\n" + "\n\n".join(kinder)
        antwort = {"gefunden": True, **_detail(voll, con)}
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
            antwort["andere_fassungen"] = [_knapp(k) for k in andere]
        # #5: Der pauschale hinweis_alter_stand ('keine 2024-Fassung im Bestand') ist FALSCH,
        # wenn eine Standard-Fassung tatsaechlich vorliegt (Nutzer hat ausdruecklich die
        # aeltere Edition angefragt). Dann korrekt formulieren statt in die Irre zu fuehren.
        if (voll["edition"] != _db.STANDARD_EDITION
                and any(k["edition"] == _db.STANDARD_EDITION for k in andere)):
            antwort["hinweis_alter_stand"] = (
                f"⚠️ Dies ist die {voll['edition']}-Fassung. Es gibt AUCH eine "
                f"{_db.STANDARD_EDITION}-Fassung im Bestand (siehe 'andere_fassungen') - "
                f"die aktuelle Version nennen, sofern nicht bewusst die aeltere gewuenscht ist.")
        # SYN-P1-009 (codex DND-011, Vampir 'weiss'/'unaware'): Dubletten GLEICHER
        # Edition aus anderen Quellen textlich vergleichen - weicht der Wortlaut
        # wesentlich ab, ist das ein QUELLKONFLIKT und darf nicht still von der
        # Prioritaetsquelle entschieden werden. Max. 3 Vergleiche (Kosten).
        konflikte, fremdsprachige = [], []
        # Kandidaten fuer den Vergleich: die im Dedupe weggemergten Fassungen des
        # gewaehlten Treffers (gleiche Edition/Kategorie per Gruppenschluessel) plus
        # etwaige weitere exakte Kandidaten anderer Quellen.
        vergleiche = list(gewaehlt.get("weitere_fassungen") or [])
        vergleiche += [{"id": k["id"], "quelle_titel": k["quelle_titel"]}
                       for k in exakt
                       if k["edition"] == voll["edition"] and k["id"] != voll["id"]]
        gesehen_ids = {voll["id"]}
        for wf in vergleiche[:3]:
            if wf["id"] in gesehen_ids:
                continue
            gesehen_ids.add(wf["id"])
            anderer = _db.hole_eintrag(con, wf["id"])
            if not anderer:
                continue
            if anderer["sprache"] != voll["sprache"]:
                # Uebersetzungen koennen inhaltlich abweichen (Vampir-Fall), sind aber
                # nicht automatisch als Konflikt beweisbar -> Referenz zum Nachladen.
                fremdsprachige.append({"eintrag_id": wf["id"],
                                       "quelle": wf["quelle_titel"],
                                       "sprache": anderer["sprache"]})
            elif _texte_weichen_ab(voll["body_md"], anderer["body_md"]):
                konflikte.append({"eintrag_id": wf["id"], "quelle": wf["quelle_titel"],
                                  "hinweis": "Textfassung weicht inhaltlich ab"})
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
        return antwort
    finally:
        con.close()


def foliant_hol_zauber(name: str, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Vollstaendiger Zauber-Steckbrief aus dem Bestand, mit Zitat (Quelle, ggf. Seite,
    Regelversion). Name deutsch oder englisch. edition Standard '2024'; eine andere
    Regelversion (z. B. '2014') laesst sich gezielt anfordern und wird nie still ersetzt.
    Bei Mehrdeutigkeit kommen Kandidaten zurueck - dann rueckfragen statt raten.
    KERNREGELN: nur aus dem Bestand; Quelle + Regelversion nennen;
    Deutsch-first (Original in Klammern)."""
    return _hole_detail("zauber", name, edition, eintrag_id=eintrag_id)


def foliant_hol_monster(name: str, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Vollstaendiger Monster-Statblock aus dem Bestand, mit Zitat (Quelle, ggf. Seite,
    Regelversion). Name deutsch oder englisch. edition Standard '2024'; eine andere
    Regelversion (z. B. '2014') laesst sich gezielt anfordern und wird nie still ersetzt.
    Bei Mehrdeutigkeit kommen Kandidaten zurueck - dann rueckfragen statt raten.
    KERNREGELN: nur aus dem Bestand; Quelle + Regelversion nennen;
    Deutsch-first (Original in Klammern)."""
    return _hole_detail("monster", name, edition, eintrag_id=eintrag_id)


def foliant_hol_gegenstand(name: str, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Gegenstands-Steckbrief aus dem Bestand, mit Zitat (Quelle, ggf. Seite, Regelversion).
    Name deutsch oder englisch. edition Standard '2024'; eine andere Regelversion
    (z. B. '2014') laesst sich gezielt anfordern und wird nie still ersetzt. Bei
    Mehrdeutigkeit kommen Kandidaten zurueck - dann rueckfragen statt raten.
    KERNREGELN: nur aus dem Bestand; Quelle + Regelversion nennen;
    Deutsch-first (Original in Klammern)."""
    return _hole_detail("gegenstand", name, edition, eintrag_id=eintrag_id)


def foliant_hol_regel(name: str, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Vollstaendiger Text eines allgemeinen Regelabschnitts aus dem Bestand (Zustaende,
    Bewegung, Rasten, Proben, Regelglossar-Definitionen ...), mit Zitat (Quelle, ggf.
    Seite, Regelversion) - die Suche liefert nur knappe Auszuege, dieses Tool den ganzen
    Abschnitt (A2). Name deutsch oder englisch. edition Standard '2024'; eine andere
    Regelversion laesst sich gezielt anfordern und wird nie still ersetzt. Bei
    Mehrdeutigkeit kommen Kandidaten zurueck - dann rueckfragen statt raten.
    KERNREGELN: nur aus dem Bestand; Quelle + Regelversion nennen;
    Deutsch-first (Original in Klammern)."""
    return _hole_detail("regel", name, edition, eintrag_id=eintrag_id)


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
