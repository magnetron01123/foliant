"""Nachschlage-Werkzeuge (F1/F2). Namensschema foliant_<verb>_<nomen> (BP #2).
Suche = KNAPPE Trefferliste; Detail = volle Ausgabe (BP #1).

Review-Fund, Kanal 3 (zuverlaessigster Weg zum Modell): Grounding-Hinweise stehen IN den
Tool-AUSGABEN - eine leere Suche sagt explizit "Nichts im Bestand - ehrlich sagen...".
Kanal 2: Kurzfassung der Kernregeln in jeder Tool-Beschreibung (= Docstring)."""
from __future__ import annotations

import re
import sqlite3
from typing import Literal

from app import db as _db
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


def foliant_suche_regeln(suchbegriff: str, kategorie: Kategorie | None = None,
                         edition: str = "2024", quelle: str | None = None) -> dict:
    """Volltextsuche im importierten Regelbestand (Kampf UND ausserhalb): Regeln, Zauber,
    Monster, Gegenstaende, Spezies, Klassen, Hintergruende, Talente. Deutsch UND Englisch
    moeglich, auch Abkuerzungen (AoO) und kleine Tippfehler. Liefert KNAPPE Treffer
    (Name, Auszug, Quelle, ggf. Seite, Regelversion) - Details per foliant_hol_*.
    kategorie optional: regel|zauber|monster|gegenstand|spezies|klasse|hintergrund|talent
    (exakt diese Werte). quelle optional: das QUELLEN-KUERZEL (z. B. 'srd-de'), nicht der
    Titel. edition Standard '2024'; andere Regelversionen (z. B. '2014') explizit angeben.
    Ungueltige Parameterwerte werden mit 'fehler' abgelehnt - das bedeutet NICHT 'nicht
    im Bestand'. Beim 2024-Standard kommen aeltere
    Staende getrennt als 'aeltere_staende'; bei explizit anderer Edition heissen weitere
    Fassungen neutral 'andere_fassungen'. KERNREGELN: Antworte NUR aus dem Bestand
    (nichts erfinden); nenne stets Quelle und Regelversion; Deutsch-first mit englischem
    Original in Klammern."""
    con = _verbinde()
    if con is None:
        return {"treffer": [], "hinweis": HINWEIS_DB_FEHLT}
    try:
        try:
            ergebnis = _db.fts_suche(con, suchbegriff, kategorie=kategorie,
                                     edition=edition, quelle=quelle)
        except ValueError as fehler:
            # SYN-P0-006: Parameterfehler (Edition/Kategorie/Quelle) sind KEIN leerer
            # Befund - vor dem Fix bekam das Modell hier den B1-Leerhinweis und meldete
            # dem Nutzer ein falsches 'nicht im Bestand' fuer vorhandene Inhalte.
            return {"treffer": [], "fehler": str(fehler),
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
        if not antwort["treffer"]:
            if antwort.get("aeltere_staende"):
                antwort["hinweis"] = HINWEIS_ALT
            elif andere:
                antwort["hinweis"] = (f"In Regelversion {edition} nichts im Bestand; "
                                      f"es gibt aber Fassungen anderer Versionen (siehe "
                                      f"'andere_fassungen') - klar unterscheiden (V5).")
            else:
                antwort["hinweis"] = HINWEIS_LEER
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
        d["hinweis_uebersetzung"] = ("Regeltext liegt nur englisch vor. Auf Deutsch antworten, "
                                     "offizielle deutsche Begriffe verwenden (Original in "
                                     "Klammern), fehlende mit * markieren (S3/S5).")
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
            return {"gefunden": False, "mehrdeutig": True,
                    "kandidaten": [_knapp(k) for k in kandidaten[:6]],
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
    KERNREGELN: nur aus dem Bestand antworten; Quelle und Regelversion nennen;
    Deutsch-first, englisches Original in Klammern."""
    return _hole_detail("zauber", name, edition, eintrag_id=eintrag_id)


def foliant_hol_monster(name: str, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Vollstaendiger Monster-Statblock aus dem Bestand, mit Zitat (Quelle, ggf. Seite,
    Regelversion). Name deutsch oder englisch. edition Standard '2024'; eine andere
    Regelversion (z. B. '2014') laesst sich gezielt anfordern und wird nie still ersetzt.
    Bei Mehrdeutigkeit kommen Kandidaten zurueck - dann rueckfragen statt raten.
    KERNREGELN: nur aus dem Bestand antworten; Quelle und Regelversion nennen;
    Deutsch-first, englisches Original in Klammern."""
    return _hole_detail("monster", name, edition, eintrag_id=eintrag_id)


def foliant_hol_gegenstand(name: str, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Gegenstands-Steckbrief aus dem Bestand, mit Zitat (Quelle, ggf. Seite, Regelversion).
    Name deutsch oder englisch. edition Standard '2024'; eine andere Regelversion
    (z. B. '2014') laesst sich gezielt anfordern und wird nie still ersetzt. Bei
    Mehrdeutigkeit kommen Kandidaten zurueck - dann rueckfragen statt raten. KERNREGELN:
    nur aus dem Bestand antworten; Quelle und Regelversion nennen; Deutsch-first,
    englisches Original in Klammern."""
    return _hole_detail("gegenstand", name, edition, eintrag_id=eintrag_id)


def foliant_hol_regel(name: str, edition: str = "2024",
        eintrag_id: int | None = None) -> dict:
    """Vollstaendiger Text eines allgemeinen Regelabschnitts aus dem Bestand (Zustaende,
    Bewegung, Rasten, Proben, Regelglossar-Definitionen ...), mit Zitat (Quelle, ggf.
    Seite, Regelversion) - die Suche liefert nur knappe Auszuege, dieses Tool den ganzen
    Abschnitt (A2). Name deutsch oder englisch. edition Standard '2024'; eine andere
    Regelversion laesst sich gezielt anfordern und wird nie still ersetzt. Bei
    Mehrdeutigkeit kommen Kandidaten zurueck - dann rueckfragen statt raten. KERNREGELN:
    nur aus dem Bestand antworten; Quelle und Regelversion nennen; Deutsch-first,
    englisches Original in Klammern."""
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
