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

from rapidfuzz import fuzz

from app import db as _db
from app import facetten as _facetten
from app import glossar as _glossar
from app import protokoll as _protokoll

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


def _knapp(t: dict, con: sqlite3.Connection | None = None) -> dict:
    """Knapper Suchtreffer (BP #1): Name, Auszug, Quelle, ggf. Seite, Version.
    eintrag_id/quelle_kuerzel (SYN-P1-002): stabile Referenz - ein ausgewaehlter
    Treffer laesst sich per foliant_hol_*(eintrag_id=...) EXAKT nachladen, statt ueber
    den Namen erneut zu raten (der Rundlauf wechselte sonst still die Quelle).

    Review 28.07.2026 - der Suchtreffer trug drei Dinge nicht, die die Verhaltensregeln
    voraussetzen:
    - `zitat`: stil.py verlangt, es WOERTLICH auszugeben. Es gab das Feld aber nur im
      Detail; wer aus einem Auszug antwortete, musste die Belegzeile selbst bauen -
      genau das, was der Prompt verbietet.
    - `anzeige_name`: Deutsch-first lief nur im Detail. 63 % der Eintraege tragen nur
      einen englischen Namen -> die Trefferliste war fuer den Grossteil des Bestands
      englisch, obwohl Deutsch-first Kernregel ist. Braucht `con` fuer das Glossar.
    """
    k = {"eintrag_id": t["id"], "name_de": t["name_de"], "name_en": t["name_en"],
         "kategorie": t["kategorie"], "edition": t["edition"],
         "quelle": t["quelle_titel"], "quelle_kuerzel": t["quelle"],
         "zitat": _zitat(t), "auszug": t["auszug"]}
    if con is not None:
        k["anzeige_name"] = _anzeige_name(con, t)
    if t.get("seite"):
        k["seite"] = t["seite"]
    if t.get("weitere_quellen"):
        # A3: fachliche Dublette kanonisch dedupliziert - Provenienz bleibt sichtbar.
        k["weitere_quellen"] = t["weitere_quellen"]
    return k


def _abenteuer_kuerzel(con: sqlite3.Connection) -> set[str]:
    """Kuerzel aller Abenteuer-/Setting-Quellen - EIN Query ueber eine ~15-zeilige Tabelle.

    Review 28.07.2026 (Spoiler-Schutz, oberste Regel): `hinweis_inhaltsart` sass nur im
    Detail-Abruf. Die Trefferliste liefert aber bereits Volltext-Auszuege - ein Modell
    konnte also aus einem Abenteuerband zitieren, ohne die Kennzeichnung je gesehen zu
    haben (belegt: Suche 'Beholder' lieferte 'Zombie March' aus Ravenloft, unmarkiert).
    Defensiv gegen Bestands-DBs ohne die Spalte (vor der v2-Migration importiert)."""
    try:
        return {r[0] for r in con.execute(
            "SELECT kuerzel FROM quellen WHERE inhaltsart = 'abenteuer_setting'")}
    except sqlite3.OperationalError:
        return set()


def _markiere_abenteuer(con: sqlite3.Connection, antwort: dict, *listen: list[dict]) -> None:
    """Treffer aus Abenteuer-/Setting-Baenden kennzeichnen und einen Sammelhinweis setzen -
    dieselbe Aussage wie HINWEIS_INHALTSART im Detail, nur schon in der Trefferliste."""
    kuerzel = _abenteuer_kuerzel(con)
    if not kuerzel:
        return
    betroffen = 0
    for liste in listen:
        for k in liste:
            if k.get("quelle_kuerzel") in kuerzel:
                k["inhaltsart"] = "abenteuer_setting"
                betroffen += 1
    # Die Kennzeichnung am EINZELNEN Treffer wird immer gesetzt; der Sammelhinweis nur,
    # wenn nicht schon ein spezifischerer dasteht. Im Detail-Pfad hat _detail bereits
    # gesagt "DIESER Eintrag stammt aus einem Abenteuerband" - das ist die praezisere
    # Aussage und darf nicht von der Zaehlung ueberschrieben werden.
    if betroffen and "hinweis_inhaltsart" not in antwort:
        antwort["hinweis_inhaltsart"] = (
            f"🚫 {betroffen} Treffer stammen aus einem ABENTEUER-/SETTING-Band (Feld "
            f"inhaltsart): Handlung, Geheimnisse und Ortsdetails NIE wiedergeben "
            f"(Spoiler-Schutz, oberste Regel); reine Regel-/Wertangaben sind ok.")


def _reichere_facetten_an(con: sqlite3.Connection, *treffer_listen: list[dict]) -> None:
    """#2: knappe Zauber-/Monster-Treffer um eine kompakte Facette ('Grad 3' bzw. 'HG 1')
    anreichern - genau das Feld, nach dem ein Spieler triagiert. EINE Batch-Abfrage der
    Textkoepfe fuer alle gezeigten Treffer (BP #1: kein Body im Output).

    Bewusst aus dem Body geparst und NICHT aus zauber_meta/monster_meta: der Text ist die
    Autoritaet, die Meta-Tabelle ist daraus abgeleitet (app/facetten.py). Ein Umweg ueber
    die Tabelle brauchte hier zusaetzlich einen Rueckfall fuer Eintraege ohne Meta-Zeile -
    mehr Code fuer denselben Wert. Bei hoechstens ~20 gezeigten Treffern und einem
    900-Zeichen-Kopf je Treffer ist die Ersparnis ohnehin nicht messbar; der Vorfilter, wo
    es wirklich zaehlte (1627 Aufrufe je Filteranfrage), sitzt in _vorfilter_sql."""
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


# Namensrelevanz eines Kandidaten (#1). Wert und Begruendung in app/glossar.py, wo alle
# vier Fuzzy-Schwellen des Projekts zusammen stehen (Befund E5).
_NAME_MIN = _glossar.FUZZY_NAME


def _name_score(k: dict, ziele: set[str]) -> float:
    """Relevanz des Kandidatennamens zur Anfrage (0-100): exakt = 100, sonst der beste
    rapidfuzz.ratio gegen die (normalisierten) Anfrage-Varianten `ziele`. Trennt echte
    Namenstreffer von blossen Body-Erwaehnungen (deren Name gar nicht passt).

    KEIN Praefix-Kurzschluss (Befund 30.07.2026): 'n.startswith(z) or z.startswith(n)'
    gab JEDEM Praefix 100.0, ohne Mindestlaenge - 'Elf' war damit ein voller Namenstreffer
    auf 'Elfenruestung', und der Detailpfad lieferte den Fremdeintrag als belegte Antwort
    aus (Verstoss gegen B1, die Anti-Halluzinations-Regel). Die abgedeckten ECHTEN Faelle
    - Wortrisse und OCR-Verstuemmelungen um ein bis zwei Zeichen - traegt fuzz.ratio
    ohnehin: ein echter Praefix erreicht 2*len(kurz)/(len(kurz)+len(lang))*100, liegt also
    ab rund 82 % Namensdeckung ueber der Schwelle von 90. Genau die kurzen, unspezifischen
    Praefixe fallen heraus, und nur die."""
    namen = _eintrag_namen(k)
    if namen & ziele:
        return 100.0
    best = 0.0
    for n in namen:
        for z in ziele:
            if not n or not z:
                continue
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
    tabelle = {"zauber": "zauber_meta", "monster": "monster_meta"}.get(kategorie)
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
                "hinweis": "Ungueltiger PARAMETER - KEIN 'nicht im Bestand' (B1/B4)."}
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
    _markiere_abenteuer(con, antwort, treffer)
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
                    "hinweis": "Ungueltiger PARAMETER - das ist KEIN 'nicht im Bestand'. "
                               "Aufruf mit einem gueltigen Wert (siehe fehler) "
                               "wiederholen; dem Nutzer keine Fehlanzeige melden (B1/B4)."}
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
        varianten = {_glossar.norm_begriff(suchbegriff)}
        varianten |= {_glossar.norm_begriff(a)
                      for a in _db._glossar_alternativen(con, suchbegriff, nur_exakt=True)}
        namenstreffer = 0
        for liste in listen:
            for k in liste:
                treffer_am_namen = _name_score(k, varianten) >= _NAME_MIN
                k["relevanz"] = "name" if treffer_am_namen else "nur_im_text"
                namenstreffer += int(treffer_am_namen)
        if antwort["treffer"] and not namenstreffer:
            antwort["hinweis_geringe_relevanz"] = (
                "Kein Treffer passt dem NAMEN nach zur Anfrage - alle erwaehnen den Begriff "
                "nur im Fliesstext. Das ist oft das Zeichen, dass der gesuchte Eintrag NICHT "
                "im Bestand ist (z. B. nicht SRD-lizenziert). Treffer kritisch pruefen und "
                "im Zweifel ehrlich 'nicht gefunden' sagen, statt Unpassendes auszugeben (B1).")
        _markiere_abenteuer(con, antwort, *listen)
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
            zeilen = _glossar.lookup_exakt(con, e["name_de"], richtung="de_en")
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
    """Strukturierte Facetten aus dem Meta-Seitenwagen: ADDITIV zum verbatim body_md,
    ersetzen den Regeltext nie. None, wenn keine Zeile/Tabelle vorhanden ist (dann fehlt
    das Feld schlicht - kein Raten). `0` ist ein WERT, kein Fehlen: 'Grad 0' (Zaubertrick),
    'dauer_min 0' (unmittelbar) und 'ritual 0' bleiben erhalten.

    Faellt zum Dedup-Gewinner nichts, werden die weggemergten Fassungen befragt (A5,
    Review 28.07.2026): Der Dedup laesst die deutsche Quelle gewinnen, und die gelieferte
    ID ist damit fast immer eine srd-de-ID. Kann der Seeder aus DEREN Text nichts ableiten
    (OCR-Riss, Kurzabschnitt), aus der englischen Schwesterfassung aber schon, waeren die
    Facetten sonst unsichtbar - obwohl sie im Bestand stehen. Die Facetten sind
    sprachunabhaengige Strukturwerte (Grad, HG, RK/TP), deshalb ist das dieselbe Aussage
    und keine Vermischung von Regeltexten."""
    spez = _facetten.META_TABELLEN.get(e["kategorie"])
    if not spez:
        return None
    tabelle, felder = spez
    ids = [e["id"]] + [f["id"] for f in (e.get("weitere_fassungen") or []) if f.get("id")]
    for eid in ids:
        try:
            # Bewusst SELECT *: der SERVING-Pfad ist read-only und migriert NICHT (das tut
            # stelle_schema_sicher nur auf dem Schreibpfad). Eine Bestands-DB, auf der noch
            # kein Import lief, kennt die neuen Spalten nicht - eine feste Spaltenliste
            # wuerde dort die Abfrage sprengen und ALLE Facetten verschlucken, auch die
            # laengst vorhandenen. So fehlen bloss die neuen Felder.
            row = con.execute(f"SELECT * FROM {tabelle} WHERE eintrag_id = ?",
                              (eid,)).fetchone()
        except sqlite3.OperationalError:
            return None                               # Alt-DB ohne die Facetten-Tabelle
        if not row:
            continue
        vorhanden = set(row.keys())
        werte = {f: (bool(row[f]) if f in _facetten.META_BOOL else row[f])
                 for f in felder if f in vorhanden and row[f] is not None}
        # Kanonische Schluessel sind DB-intern; nach aussen geht die deutsche Anzeigeform
        # (Deutsch-first, S3) - 'hervorrufung' liest sich sonst wie ein Tippfehler.
        for feld, anzeige in (("schule", _facetten.schule_anzeige),
                              ("typ", _facetten.typ_anzeige)):
            if werte.get(feld):
                werte[feld] = anzeige(werte[feld]) or werte[feld]
        if werte:
            return werte
    return None


def _detail(e: dict, con: sqlite3.Connection) -> dict:
    # eintrag_id/quelle_kuerzel (A7, Review 28.07.2026): Der Rundlauf war einseitig -
    # Suche->Detail ging, Detail->weiter nicht. Ohne eintrag_id konnte das Modell den
    # gerade gelieferten Eintrag nicht erneut referenzieren (etwa gegen die IDs in
    # konflikt_quellen), ohne quelle_kuerzel nicht 'in dieser Quelle weitersuchen' -
    # foliant_suche_bestand verlangt dort das KUERZEL, nicht den Titel.
    d = {"eintrag_id": e["id"], "anzeige_name": _anzeige_name(con, e),
         "name_de": e["name_de"], "name_en": e["name_en"], "kategorie": e["kategorie"],
         "edition": e["edition"], "sprache": e["sprache"], "quelle": e["quelle_titel"],
         "quelle_kuerzel": e.get("quelle"),
         "seite": e.get("seite"), "zitat": _zitat(e), "regeltext_md": e["body_md"],
         "hinweis_sprache_begriffe": _HINWEIS_STERN}
    if e.get("lizenz"):
        # A12/Q6: die Quellenlizenz wird im Detailpfad nicht verworfen; CC-BY verlangt
        # die mitgefuehrte Attribution (Wortlaut konsistent mit README.md, Lizenz & Recht).
        d["lizenz"] = e["lizenz"]
        if str(e["lizenz"]).upper().startswith("CC-BY"):
            d["attribution"] = ("Enthaelt Material aus dem System Reference Document "
                                "5.2.1 von Wizards of the Coast LLC, lizenziert unter "
                                "CC-BY-4.0.")
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
    """Protokollierender Mantel um _hole_detail_impl - EIN Hook deckt alle acht
    foliant_hol_*-Tools (nachschlagen.py UND charakter.py delegieren hierher)."""
    start = time.monotonic()
    antwort = _hole_detail_impl(kategorie, name, edition, aggregiere_kinder, eintrag_id)
    if eintrag_id is not None:
        suchweg = "direkt_id"        # Nachladen einer Referenz - kein Kurations-Signal
    elif "fehler" in antwort:
        suchweg = "fehler"
    else:
        suchweg = "name"
    _protokoll.protokolliere(
        werkzeug=f"hol_{kategorie}", kategorie=kategorie,
        suchbegriff=None if eintrag_id is not None else name, edition=edition,
        anzahl_treffer=(len(antwort.get("kandidaten", []))
                        or int(bool(antwort.get("gefunden")))),
        suchweg=suchweg, mehrdeutig=bool(antwort.get("mehrdeutig")),
        gefunden=antwort.get("gefunden"),
        dauer_ms=(time.monotonic() - start) * 1000)
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
                "fehler": f"eintrag_id {eintrag_id} existiert nicht (Referenz "
                          f"veraltet? Neu suchen)."}
    if voll["kategorie"] != kategorie:
        return {"gefunden": False,
                "fehler": f"eintrag_id {eintrag_id} ist Kategorie "
                          f"'{voll['kategorie']}' - dieses Werkzeug liefert "
                          f"'{kategorie}' (passendes foliant_hol_* nutzen)."}
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
    varianten = {_glossar.norm_begriff(name)}
    varianten |= {_glossar.norm_begriff(a)
                  for a in _db._glossar_alternativen(con, name, nur_exakt=True)}
    exakt = [k for k in kandidaten if _eintrag_namen(k) & varianten]
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
        _markiere_abenteuer(con, absage, fassungen)
        return _Auswahl(None, None, [], exakt, absage)

    # #1: reine Body-Erwaehnungen (deren Name gar nicht zur Anfrage passt, z. B.
    # 'Schild'/'Zauberplaetze' bei der Suche nach 'Magic Missile') aus der Kandidatenliste
    # draengen. Bleibt genau EIN starker Namenstreffer der gewuenschten Edition (auch
    # vertippt: 'Missle'->'Missile'), ihn direkt liefern statt rueckzufragen. Sonst die
    # BEREINIGTE Kandidatenliste zeigen.
    #
    # Befund 30.07.2026: Hier stand davor ein Sonderzweig, der einen EINZELNEN
    # FTS-Kandidaten ungeprueft als Treffer auslieferte - ohne _NAME_MIN. Der Suchpfad
    # hat fuer genau diese Fehlerform seit A4 die Namensrelevanz; der Detailpfad, der
    # verbindlicher antwortet, hatte sie nicht. Der Zweig ist ersatzlos gestrichen: die
    # Zeilen darunter behandeln den Einzelkandidaten bereits, nur eben mit Relevanzgate.
    # Seine Editionsbedingung war das einzig Tragende daran - sie steht jetzt unten.
    relevante = [k for k in kandidaten if _name_score(k, varianten) >= _NAME_MIN]
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
    _markiere_abenteuer(con, absage, gezeigt)
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
        if eintrag_id is not None:
            return _detail_per_id(con, kategorie, eintrag_id, aggregiere_kinder)
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
        _markiere_abenteuer(con, antwort, antwort.get("weitere_abschnitte") or [],
                            antwort.get("andere_fassungen") or [])
        return antwort
    finally:
        con.close()


def foliant_hol_zauber(name: str | None = None, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Vollstaendiger Zauber-Steckbrief aus dem Bestand, mit Zitat (Quelle, ggf. Seite,
    Regelversion). Name deutsch oder englisch - alternativ eintrag_id aus einem
    Suchtreffer. edition Standard '2024'; eine andere
    Regelversion (z. B. '2014') laesst sich gezielt anfordern und wird nie still ersetzt.
    Bei Mehrdeutigkeit kommen Kandidaten zurueck - dann rueckfragen statt raten.
    KERNREGELN: nur aus dem Bestand; Quelle + Regelversion nennen;
    Deutsch-first (Original in Klammern)."""
    return _hole_detail("zauber", name, edition, eintrag_id=eintrag_id)


def foliant_hol_monster(name: str | None = None, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Vollstaendiger Monster-Statblock aus dem Bestand, mit Zitat (Quelle, ggf. Seite,
    Regelversion). Name deutsch oder englisch - alternativ eintrag_id aus einem
    Suchtreffer. edition Standard '2024'; eine andere
    Regelversion (z. B. '2014') laesst sich gezielt anfordern und wird nie still ersetzt.
    Bei Mehrdeutigkeit kommen Kandidaten zurueck - dann rueckfragen statt raten.
    KERNREGELN: nur aus dem Bestand; Quelle + Regelversion nennen;
    Deutsch-first (Original in Klammern)."""
    return _hole_detail("monster", name, edition, eintrag_id=eintrag_id)


def foliant_hol_gegenstand(name: str | None = None, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Gegenstands-Steckbrief aus dem Bestand, mit Zitat (Quelle, ggf. Seite, Regelversion).
    Name deutsch oder englisch - alternativ eintrag_id aus einem Suchtreffer.
    edition Standard '2024'; eine andere Regelversion
    (z. B. '2014') laesst sich gezielt anfordern und wird nie still ersetzt. Bei
    Mehrdeutigkeit kommen Kandidaten zurueck - dann rueckfragen statt raten.
    KERNREGELN: nur aus dem Bestand; Quelle + Regelversion nennen;
    Deutsch-first (Original in Klammern)."""
    return _hole_detail("gegenstand", name, edition, eintrag_id=eintrag_id)


def foliant_hol_regel(name: str | None = None, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Vollstaendiger Text eines allgemeinen Regelabschnitts aus dem Bestand (Zustaende,
    Bewegung, Rasten, Proben, Regelglossar-Definitionen ...), mit Zitat (Quelle, ggf.
    Seite, Regelversion) - die Suche liefert nur knappe Auszuege, dieses Tool den ganzen
    Abschnitt (A2). Name deutsch oder englisch - alternativ eintrag_id aus einem
    Suchtreffer. edition Standard '2024'; eine andere
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
