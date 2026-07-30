"""Ausgabe-Schicht der Werkzeuge: WIE ein Treffer beim Modell ankommt.

Hier liegt alles, was aus einer Datenbankzeile eine Antwort macht - die knappe
Trefferform, die volle Detailform, der Deutsch-first-Anzeigename, das Zitat, die
Facetten-Anreicherung - und die GROUNDING-HINWEISE, die laut SPEC.md par. 7 der
zuverlaessigste der drei Verhaltenskanaele sind, weil sie bei jeder Antwort im Kontext
stehen.

Warum eine eigene Datei (30.07.2026): Diese Schicht lag verstreut in nachschlagen.py,
und app/tools/charakter.py borgte sie sich ueber sieben Zugriffe auf fremde
Modul-Interna (_ns.HINWEIS_LEER, _ns._anzeige_name, _ns._markiere_abenteuer ...).
Beide Werkzeug-Module brauchen dieselbe Ausgabe - jetzt importieren sie sie, statt dass
eines ins andere hineingreift. Der Zuschnitt ist am Code geprueft: keine Funktion hier
ruft etwas aus dem Such- oder Detailpfad, die Schicht ist geschlossen.

Sie kennt db, glossar und facetten - aber NICHT die Werkzeuge. Diese Richtung ist die
Regel: Ausgabe weiss nichts davon, wer sie benutzt.
"""
from __future__ import annotations

import sqlite3

from app import db as _db
from app import facetten as _facetten
from app import glossar as _glossar


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
    Treffer laesst sich per foliant_hol_eintrag(kategorie, eintrag_id=...) EXAKT
    nachladen, statt ueber den Namen erneut zu raten (der Rundlauf wechselte sonst still
    die Quelle).

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

# Derselbe Satz an jeder Stelle, die einen PARAMETER-Fehler meldet (SYN-P0-006): das
# Modell muss ihn von einem echten Leerbefund unterscheiden koennen, sonst meldet es dem
# Nutzer eine Fehlanzeige fuer Inhalte, die es gibt.
def _alias_hinweis(roh: str | None) -> str | None:
    """Sagt es, wenn ein Editions-ALIAS die Anfrage umgeschrieben hat.

    Befund 30.07.2026: '5e' bildet still auf 2014 ab, '5.5e' auf 2024 (db.EDITION_ALIASSE).
    Umgangssprachlich meint '5e' aber die ganze 5. Edition INKLUSIVE 2024 - fragte ein
    Modell danach, bekam es "Keine Fassung der Regelversion 2014 im Bestand" fuer einen
    Eintrag, den der Bestand in 2024 fuehrt, und meldete dem Nutzer eine Fehlanzeige.
    Der eigene Wert tauchte in der Antwort nirgends mehr auf, also gab es auch keinen
    Anhaltspunkt. Genau die Fehlerklasse aus B1, nur ueber einen Parameter erzeugt."""
    if roh is None:
        return None
    ziel = _db.normalisiere_edition(roh)
    if ziel is None or str(roh).strip() == ziel:
        return None
    return (f"ACHTUNG: '{roh}' wurde als Regelversion {ziel} gelesen (Alias). Ist die "
            f"aktuelle Fassung gemeint, den Aufruf ohne 'edition' oder mit "
            f"edition='{_db.STANDARD_EDITION}' wiederholen, BEVOR du eine Fehlanzeige "
            f"meldest.")

_HINWEIS_PARAMETER = ("Ungueltiger PARAMETER - das ist KEIN 'nicht im Bestand'. Aufruf mit "
                      "einem gueltigen Wert (siehe fehler) wiederholen; dem Nutzer keine "
                      "Fehlanzeige melden (B1/B4).")
