"""Ausgabe-Schicht der Werkzeuge: WIE ein Treffer beim Modell ankommt.

Hier liegt alles, was aus einer Datenbankzeile eine Antwort macht - die knappe
Trefferform, die volle Detailform, der Deutsch-first-Anzeigename, das Zitat, die
Facetten-Anreicherung - und die GROUNDING-HINWEISE, die laut SPEC.md par. 7 der
zuverlaessigste der drei Verhaltenskanaele sind, weil sie bei jeder Antwort im Kontext
stehen.

Warum eine eigene Datei (30.07.2026): Diese Schicht lag verstreut in nachschlagen.py,
und app/tools/charakter.py borgte sie sich ueber sieben Zugriffe auf fremde
Modul-Interna (_ns.HINWEIS_LEER, _ns._anzeige_name, _ns._markiere_inhaltsart ...).
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
from config import quellfehler as _quellfehler


# "Eventuell fehlt ein Buch" stand hier bis zum 04.08.2026 als Angebot - und die Runde
# markierte prompt eine Antwort, die genau das tat (B2). Der Bot war dabei REGELKONFORM:
# Kanal 1 und die Prompt-Kanaele gaben die Vermutung woertlich vor. Eine Mutmassung ueber
# den Bestand ist aber ueberfluessig, seit `/bestand` ihn belegt auflistet - und eine
# Vermutung an der Stelle einer moeglichen Abfrage ist genau der Fuellstoff, den B2 meint.
HINWEIS_LEER = ("Nichts im Bestand gefunden. Sag das ehrlich mit ❌ ('Dazu finde ich nichts "
                "im Foliant-Bestand') und antworte NICHT aus Allgemeinwissen, 2014-Regeln oder "
                "Homebrew (B1). Mutmasse NICHT ueber fehlende Buecher - welche im Bestand "
                "stehen, zeigt '/bestand' (Discord) bzw. die Bestandsliste der Website (B2). "
                "Falls danach "
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

# Rueckmeldung der Runde, 04.08.2026: Auf "Kann man 2 Gelegenheitsangriffe machen?" kam ein
# klares "Ja" - belegt mit der Hydra, also einem MONSTER-Merkmal. Fuer Spielercharaktere
# lautet die Antwort "nein", und die eigene Folgeantwort widerrief das zwei Minuten spaeter.
# Der Treffer war geerdet; falsch war, ihn als allgemeine Regel auszugeben (B4).
HINWEIS_MONSTER_MERKMAL = (
    "Dies ist ein MONSTER-Steckbrief. Seine Merkmale gelten fuer diese Kreatur, NICHT "
    "allgemein und NICHT fuer Spielercharaktere. Zielt die Frage auf Spielerfiguren, sag "
    "das ausdruecklich dazu, statt das Merkmal als allgemeine Regel auszugeben - und "
    "beantworte die eigentliche Frage getrennt (B4).")

HINWEIS_DB_FEHLT = ("Der Regelbestand ist noch leer (keine Datenbank/keine Importe). Sag ehrlich, "
                    "dass noch keine Quellen importiert sind - erfinde keine Regeln (B1).")

_HINWEIS_STERN = "* = keine offizielle deutsche Uebersetzung (einmal erlaeutern, S5)"

# S12: aus dem EINEN Register (config/abkuerzungen.py) gebaut, nicht abgeschrieben - sonst
# liefe der Hinweis der Liste davon, sobald eine Abkuerzung dazukommt.
def _baue_abkuerzungs_hinweis() -> str:
    from config import abkuerzungen as _abk

    deutsch = " · ".join(f"{k} ({lang})" for k, lang, _en, _n in _abk.EMPFOHLEN[:6])
    attribute = ", ".join(k for k, _lang, _en in _abk.ATTRIBUTE)
    englisch = ", ".join(en for _k, _lang, en, _n in _abk.EMPFOHLEN[:6] if en)
    return (f"Wenn du abkuerzt, nimm die OFFIZIELLE DEUTSCHE Form: {deutsch}. "
            f"Attribute: {attribute}. Wuerfel deutsch (8W6, W20 - nie 8d6/d20). "
            f"Die englischen Kuerzel ({englisch}, gp) musst du VERSTEHEN, aber nie "
            f"schreiben. Kennst du die deutsche Abkuerzung nicht, schreib den Begriff aus - "
            f"eine erfundene Abkuerzung ist schlimmer als keine (S12).")


HINWEIS_ABKUERZUNGEN = _baue_abkuerzungs_hinweis()

# Das eckige Klammer-Suffix der DDB-Regelglossar-Namen ('Hide \[Action]',
# 'Blinded \[Condition]') - im Markdown escaped, deshalb der optionale Backslash.
_ECKIGES_SUFFIX = __import__("re").compile(r"\\?\[[^\]]{1,24}\\?\]\s*$")

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

# Der Hinweis je Inhaltsart - EINMAL formuliert, in beiden Ausgabewegen (Trefferliste
# ueber _markiere_inhaltsart, Einzelabruf ueber _detail) derselbe Wortlaut.
#
# Dreiteilig (Symbol, WORAUS der Treffer stammt, WAS daraus folgt), damit beide Wege
# denselben Text tragen koennen: die Trefferliste sagt "N Treffer stammen aus <woraus>:
# <folge>", der Einzelabruf "Dieser Eintrag stammt aus <woraus>: <folge>". Vorher stand
# der Abenteuer-Satz zweimal ausgeschrieben da und lief in den Klammerzusaetzen bereits
# auseinander.
#
# Warum drei getrennte Texte und nicht ein "Achtung, Sonderquelle": weil die drei Faelle
# etwas voellig Verschiedenes verlangen. Beim Abenteuerband soll das Modell Inhalte
# VERSCHWEIGEN, bei Errata soll es sie ZUSAETZLICH nennen (und die Korrektur gewinnen
# lassen), bei einer Auslegung soll es sie als Auslegung KENNZEICHNEN statt als Regeltext
# zu zitieren. Ein gemeinsamer Text muesste alles drei zugleich sagen und saegte damit am
# Spoiler-Schutz, der obersten Regel.
#
# 'regelwerk' steht bewusst NICHT drin: der Normalfall traegt keine Kennzeichnung, sonst
# verliert die Kennzeichnung ihre Bedeutung.
INHALTSART_HINWEISE: dict[str, tuple[str, str, str]] = {
    "abenteuer_setting": (
        "🚫", "einem ABENTEUER-/SETTING-Band (nur fuer Terminologie/Werte geladen)",
        "Handlung, Geheimnisse und Ortsdetails NIE wiedergeben (Spoiler-Schutz, oberste "
        "Regel); reine Regel-/Wertangaben sind ok."),
    "errata": (
        "📌", "einer ERRATA-Quelle (offizielle Korrektur zum Grundtext)",
        "KEIN eigenstaendiger Regeltext: Grundtext UND Korrektur zusammen wiedergeben und "
        "sagen, dass die Korrektur gilt. Nie als eigene Regel zitieren - und nie "
        "verschweigen, wenn du den korrigierten Text nennst."),
    "regelauslegung": (
        "⚖️", "einer OFFIZIELLEN REGELAUSLEGUNG (Sage Advice)",
        "KEIN Regeltext: als Auslegung kennzeichnen ('offizielle Auslegung, kein "
        "Regelwortlaut'), nie als Regelzitat ausgeben und nie mit dem Wortlaut des "
        "Regeltexts vermischen."),
}

def _inhaltsart_je_kuerzel(con: sqlite3.Connection) -> dict[str, str]:
    """Kuerzel -> inhaltsart fuer alle Quellen, die KEIN schlichtes Regelwerk sind -
    EIN Query ueber eine ~15-zeilige Tabelle.

    Review 28.07.2026 (Spoiler-Schutz, oberste Regel): `hinweis_inhaltsart` sass nur im
    Detail-Abruf. Die Trefferliste liefert aber bereits Volltext-Auszuege - ein Modell
    konnte also aus einem Abenteuerband zitieren, ohne die Kennzeichnung je gesehen zu
    haben (belegt: Suche 'Beholder' lieferte 'Zombie March' aus Ravenloft, unmarkiert).
    Dasselbe Argument gilt seit v3 fuer Errata und Regelauslegung, nur mit umgekehrtem
    Vorzeichen: dort ist die Gefahr, dass eine Korrektur wie normaler Regeltext zitiert
    wird.

    `!= 'regelwerk'` statt einer Werte-Aufzaehlung: eine kuenftig ergaenzte Inhaltsart
    faellt damit automatisch auf, statt still als Regelwerk durchzugehen. Unbekannte
    Werte bekommen unten keinen Hinweistext, aber das Feld am Treffer - sichtbar statt
    verschluckt. Defensiv gegen Bestands-DBs ohne die Spalte (vor der v2-Migration
    importiert): der SERVING-Pfad migriert nicht."""
    try:
        return {r[0]: r[1] for r in con.execute(
            "SELECT kuerzel, inhaltsart FROM quellen WHERE inhaltsart != 'regelwerk'")}
    except sqlite3.OperationalError:
        return {}

def markiere_unuebersetzte(antwort: dict, *listen: list[dict]) -> None:
    """Sammelhinweis, wenn Treffer OHNE belegten deutschen Namen dabei sind (S3 Stufe 4).

    Rueckmeldung der Runde, 04.08.2026: Eine Uebersichtsantwort gab 'Mist Wanderer*',
    'Spirit Medium*', 'Touch of Death*' aus - englische Namen mit einem Stern dran. Das
    Sternchen heisst aber "keine offizielle Uebersetzung", es ERSETZT die Uebersetzung
    nicht; S3 Stufe 4 verlangt ausdruecklich eine deutsche Wiedergabe und *nicht* Englisch
    mitten im Satz.

    Warum hier und nicht im Prompt: Die Regel STEHT in beiden Prompt-Kanaelen und im
    Detail-Hinweis - nur die TREFFERLISTE trug sie nie, und aus ihr beantwortet das Modell
    genau die Uebersichtsfragen, bei denen viele Namen auf einmal anfallen. `_anzeige_name`
    gibt bei fehlendem Glossar-Treffer korrekt den englischen Namen zurueck (raten waere
    schlimmer) - das Modell braucht nur die Ansage, was es damit tun soll."""
    ohne_deutsch = [k for liste in listen for k in liste
                    if not k.get("name_de")
                    and k.get("anzeige_name", k.get("name_en")) == k.get("name_en")]
    if not ohne_deutsch:
        return
    beispiel = ohne_deutsch[0].get("name_en") or "Mist Walker"
    antwort["hinweis_ohne_deutschen_namen"] = (
        f"{len(ohne_deutsch)} Treffer tragen KEINEN belegten deutschen Namen. Gib sie "
        f"trotzdem nicht englisch aus: konsistente deutsche Wiedergabe MIT '*' und dem "
        f"Original in Klammern - '{beispiel}' wird also zu '<deutsche Fassung>* "
        f"({beispiel})'. Ein '*' allein am englischen Namen erfuellt S3 NICHT: er markiert "
        f"die fehlende offizielle Uebersetzung, er ersetzt sie nicht.")


def _markiere_inhaltsart(con: sqlite3.Connection, antwort: dict, *listen: list[dict]) -> None:
    """Treffer aus Sonderquellen kennzeichnen und je Art einen Sammelhinweis setzen -
    dieselbe Aussage wie im Detail, nur schon in der Trefferliste."""
    je_kuerzel = _inhaltsart_je_kuerzel(con)
    if not je_kuerzel:
        return
    betroffen: dict[str, int] = {}
    for liste in listen:
        for k in liste:
            art = je_kuerzel.get(k.get("quelle_kuerzel"))
            if art:
                k["inhaltsart"] = art
                betroffen[art] = betroffen.get(art, 0) + 1
    if not betroffen:
        return
    # Die Kennzeichnung am EINZELNEN Treffer wird immer gesetzt. Beim Sammelhinweis hat
    # ein bereits vorhandener Vorrang: Im Detail-Pfad hat _detail schon gesagt "DIESER
    # Eintrag stammt aus ..." - die praezisere Aussage, die keine Zaehlung ueberschreiben
    # darf.
    #
    # Er darf sie aber auch nicht VERDRAENGEN. Bis dahin brach die Funktion hier ab, sobald
    # irgendein Hinweis stand - solange nur Abenteuerbaende gekennzeichnet wurden, war das
    # folgenlos (derselbe Text). Mit Errata und Auslegung nicht mehr: liefert der Detail-
    # Pfad ein ERRATUM (📌) und steht in den Nebenlisten ein ABENTEUERBAND, fiel dessen
    # 🚫-Hinweis lautlos weg - der Spoiler-Schutz, also die oberste Regel, verschwand
    # hinter einer Korrektur-Meldung (Review-Befund 31.07.2026, reproduziert).
    # Deshalb: nur die Arten ueberspringen, die der vorhandene Hinweis schon nennt.
    schon = antwort.get("hinweis_inhaltsart")
    if schon:
        betroffen = {art: n for art, n in betroffen.items()
                     if INHALTSART_HINWEISE.get(art, ("",))[0] not in schon}
        if not betroffen:
            return
    teile = [f"{symbol} {betroffen[art]} Treffer "
             f"{'stammt' if betroffen[art] == 1 else 'stammen'} aus {woraus}: {folge}"
             for art, (symbol, woraus, folge) in INHALTSART_HINWEISE.items()
             if art in betroffen]
    if teile:
        antwort["hinweis_inhaltsart"] = " | ".join(([schon] if schon else []) + teile)

def _revisions_eintraege(con: sqlite3.Connection) -> list[dict]:
    """Alle Eintraege aus Revisionsquellen (Errata, offizielle Regelauslegung) - eine
    Abfrage ueber ~46 Zeilen.

    Die Unterabfrage auf `quellen` ist nicht Geschmackssache: `WHERE q.inhaltsart IN (...)`
    im JOIN erzwingt einen Scan ueber alle 12 500 Eintraege (gemessen 4,5 ms), die
    Unterabfrage nutzt idx_eintraege_quelle (0,08 ms). Bei einer Verbindung je Tool-Aufruf
    ist das der Unterschied zwischen unmessbar und spuerbar.

    Ungecacht - dieselbe Begruendung wie bei db._revisions_kuerzel: Der Glossar-Cache faellt
    an der Zeilenzahl des Glossars, und eine neu importierte Errata-Quelle aendert die
    nicht. Ein Cache mit dem falschen Ausloeser waere schlimmer als keiner.

    Defensiv gegen Bestands-DBs ohne `inhaltsart`/`kontext`: der Serving-Pfad migriert nie."""
    try:
        return [dict(r) for r in con.execute("""
            SELECT e.id, e.kategorie, e.name_de, e.name_en, e.sprache, e.edition, e.seite,
                   e.body_md, q.kuerzel AS quelle, q.titel AS quelle_titel, q.inhaltsart
            FROM eintraege e JOIN quellen q ON q.id = e.quelle_id
            WHERE e.quelle_id IN (SELECT id FROM quellen
                                  WHERE inhaltsart IN ('errata','regelauslegung'))
            ORDER BY e.id""")]
    except sqlite3.OperationalError:
        return []


def _revisionen_zu(con: sqlite3.Connection, eintraege: list[dict],
                   ausser_ids: frozenset[int] = frozenset(),
                   max_treffer: int = 3) -> list[dict]:
    """Die offiziellen Nachtraege zu den uebergebenen Eintraegen (B11/V9).

    WARUM ES DIESE FUNKTION GIBT: Der Bestand kannte bisher nur die Gegenrichtung - drei
    Stellen nehmen Revisionsquellen aus etwas HERAUS (db._dedupe_und_sortiere,
    nachschlagen._quellabweichungen, charakter._eintraege). Dass es zu einem Eintrag eine
    Korrektur GIBT, erfuhr man allein dadurch, dass die Volltextsuche sie zufaellig
    danebenspuelte - und das fiel weg, sobald ein Kategorie-Filter griff oder der Eintrag
    direkt per foliant_hol_eintrag geladen wurde (Datenbank-Audit 03.08.2026).

    Der Abgleich laeuft ueber NAMEN, nicht ueber Kategorie:
    - Namensvarianten kommen aus glossar._eintrag_namen, der EINEN Definition (A3) - keine
      zweite Normalisierung; eine eigene Kopie war genau der Fehler, den A3 beseitigt hat.
    - Dazu die Glossar-Bruecke (db._brueckennamen, gecacht): Errata heissen englisch
      ('Polymorph'), der kanonische Grundtext deutsch ('Verwandlung'). Ohne Bruecke faende
      man nur die zufaellig gleichlautenden Faelle.
    - Die EDITION muss uebereinstimmen: ein 2024-Erratum sagt nichts ueber einen
      2014-Eintrag.
    - Die KATEGORIE wird bewusst NICHT verglichen. Alle 43 Errata tragen heute
      kategorie='regel', weil die PDF-Rubriken nicht durchgaengig auf eine Kategorie
      abbildbar sind (BACKLOG §4). Ein Kategorie-Vergleich wuerde deshalb jeden Treffer
      wegwerfen. Faellt diese Entscheidung spaeter anders, entfaellt hier nur dieser Absatz.

    `ausser_ids` laesst Nachtraege weg, die im selben Aufruf schon als eigener Treffer
    stehen - die ungefilterte Suche zeigt das Erratum ohnehin, und ein Eintrag soll nicht
    zweimal in derselben Antwort erscheinen."""
    revisionen = _revisions_eintraege(con)
    if not revisionen:
        return []
    eigene = _db._revisions_kuerzel(con)
    ziele = [e for e in eintraege if e.get("quelle") not in eigene
             and e.get("quelle_kuerzel") not in eigene]
    if not ziele:
        return []                          # ein Erratum verweist nicht auf sich selbst
    bruecke = _db._brueckennamen(con)

    def namen_von(zeile: dict) -> set[str]:
        namen = _glossar._eintrag_namen(zeile)
        # Eckiges Klammer-Suffix zusaetzlich abziehen ('Hide [Action]' -> 'Hide'), damit
        # die Glossar-Bruecke greift: das Erratum heisst so, der deutsche Grundeintrag
        # 'Verstecken (Aktion)'. Bewusst NUR hier und nicht in glossar._eintrag_namen -
        # das ist die gemeinsame Identitaetsregel von Dedupe und Ranking, und 83 Eintraege
        # tragen dieses Suffix. Hier kann es hoechstens einen Nachtrag mehr anhaengen.
        namen |= {_glossar.norm_begriff(_ECKIGES_SUFFIX.sub("", n).strip())
                  for n in namen if _ECKIGES_SUFFIX.search(n)} - {""}
        return namen | {b for n in namen for b in bruecke.get(n, set())}

    ziel_namen = [(e, namen_von(e)) for e in ziele]
    gefunden: dict[int, dict] = {}
    for rev in revisionen:
        if rev["id"] in ausser_ids:
            continue
        rev_namen = namen_von(rev)
        for ziel, namen in ziel_namen:
            if ziel.get("edition") != rev["edition"] or not (namen & rev_namen):
                continue
            eintrag = {
                "eintrag_id": rev["id"],
                "anzeige_name": _anzeige_name(con, rev),
                "inhaltsart": rev["inhaltsart"],
                "kategorie": rev["kategorie"],
                "edition": rev["edition"],
                "quelle": rev["quelle_titel"],
                "quelle_kuerzel": rev["quelle"],
                "zitat": _zitat(rev),
                "text_md": _db.KONTEXT_ZEILE.sub("", rev["body_md"] or "",
                                                 count=1).strip()[:600],
                "betrifft_eintrag_id": ziel.get("id") or ziel.get("eintrag_id"),
            }
            if rev.get("seite"):
                eintrag["seite"] = rev["seite"]
            gefunden.setdefault(rev["id"], eintrag)
            break
    return [gefunden[i] for i in sorted(gefunden)][:max_treffer]


def _hinweis_revision(arten: set[str]) -> str:
    """Der Begleittext zu `revisionen` - gebaut aus INHALTSART_HINWEISE, nicht neu
    formuliert. Dritte Satzform neben 'N Treffer stammen aus ...' (Trefferliste) und
    'Dieser Eintrag stammt aus ...' (Einzelabruf).

    Er geht bewusst NICHT nach `hinweis_inhaltsart`: dort entscheidet _markiere_inhaltsart
    am SYMBOL, welche Art schon genannt ist. Stuende dort ein 📌 aus diesem Nachschlag,
    fiele ein ECHTES Erratum in den Nebenlisten aus dem Sammelhinweis - genau der
    Erosionspfad, den CONCEPT.md §12 beschreibt ('Eine Kennzeichnung, die eine andere
    unterdrueckt, ist kein Schutz')."""
    teile = [f"{symbol} Zu diesem Eintrag gibt es einen Nachtrag aus {woraus}: {folge}"
             for art, (symbol, woraus, folge) in INHALTSART_HINWEISE.items()
             if art in arten]
    return " | ".join(teile) + (
        " Der Nachtrag steht in 'revisionen' (Feld 'text_md'; der volle Eintrag ist per "
        "eintrag_id ladbar). Grundtext UND Nachtrag zusammen wiedergeben - weder "
        "verschweigen noch als eigene Regel zitieren (B11/V9).")


def _haenge_revisionen_an(con: sqlite3.Connection, antwort: dict,
                          *listen: list[dict]) -> None:
    """Die Nachtraege zu den gezeigten Treffern an die SUCHANTWORT haengen.

    Der Anhang ist das Gegenstueck zum harten Kategorie-Filter: `kategorie='zauber'`
    filtert das Erratum zum Zauber heraus (es traegt kategorie='regel'), und ohne diesen
    Anhang saehe niemand mehr, dass es existiert - der Filter machte die Antwort also
    stiller, statt sie zu schaerfen. Den Filter selbst aufzuweichen waere der schlechtere
    Weg: er ist eine Zusage, und eine Monstersuche soll nicht mit Regelglossar-Errata
    volllaufen.

    Bewusst NICHT ueber _markiere_inhaltsart: das schriebe einen 📌-Sammelsatz nach
    `hinweis_inhaltsart` und vermischte 'was der Treffer IST' mit 'was es dazu GIBT'."""
    gezeigt = frozenset(k.get("eintrag_id") for liste in listen for k in liste)
    rev = _revisionen_zu(con, [k for liste in listen for k in liste],
                         ausser_ids=gezeigt, max_treffer=5)
    if rev:
        antwort["revisionen"] = rev
        antwort["hinweis_revision"] = _hinweis_revision({r["inhaltsart"] for r in rev})


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
    # term_de liefert None, wenn es keinen belegten deutschen Begriff gibt (seit
    # 31.07.2026 statt des mehrdeutigen (term_en, False)). Der `de != name_en`-Test
    # bleibt trotzdem stehen - er unterdrueckt die sinnlose Klammer bei gleichlautenden
    # Begriffen ("Aasimar (Aasimar)"), und genau das ist hier die richtige Anzeige.
    treffer = _glossar.term_de(con, name_en)
    if treffer:
        de, offiziell = treffer
        if de != name_en:
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
    # SYN-P0-007: Sonderquellen sind bewusst geladen - Abenteuerbaende wegen der
    # Terminologie, Errata und Auslegungen wegen ihres Inhalts -, aber jede Antwort daraus
    # traegt die Kennzeichnung. Spoiler-Schutz und 'kein Regeltext' duerfen nicht allein am
    # Quellentitel haengen. Defensiv gegen Bestands-DBs ohne die Spalte (vor der Migration
    # importiert).
    try:
        art = con.execute(
            "SELECT q.inhaltsart FROM quellen q JOIN eintraege e2 ON e2.quelle_id = q.id "
            "WHERE e2.id = ?", (e["id"],)).fetchone()
    except sqlite3.OperationalError:
        art = None
    if art and art[0] and art[0] != "regelwerk":
        d["inhaltsart"] = art[0]
        kennzeichen = INHALTSART_HINWEISE.get(art[0])
        if kennzeichen:
            symbol, woraus, folge = kennzeichen
            d["hinweis_inhaltsart"] = f"{symbol} Dieser Eintrag stammt aus {woraus}: {folge}"
    if e["edition"] != _db.STANDARD_EDITION:
        d["hinweis_alter_stand"] = HINWEIS_ALT
    if e.get("kategorie") == "monster":
        d["hinweis_monster_merkmal"] = HINWEIS_MONSTER_MERKMAL
    if e.get("sprache") == "en":
        # S3/S5: dem Modell die AMTLICHEN deutschen Begriffe INLINE mitgeben, statt sie nur
        # anzumahnen - genau die Luecke, an der eine Antwort sonst englisch stehen bleibt
        # (Warlock-Test 13.07.2026: Cloudkill/Bane/Greater Invisibility blieben englisch,
        # obwohl das Glossar Todeswolke/Verderben/Maechtige Unsichtbarkeit kennt).
        # Der NAME steht mit im durchsuchten Text (Rueckmeldung der Runde, 04.08.2026):
        # `begriffe_im_text` las bis dahin nur `body_md`, also alles AUSSER der
        # Ueberschrift der Antwort. Bei "Archfey Patron" war die Folge, dass das Modell 30
        # amtliche Begriffe aus dem Fliesstext mitgeliefert bekam - und ausgerechnet den
        # Namen, den der Spieler zuerst liest, englisch mit '*' ausgab. Genau die
        # Fehlerklasse, die das Feld verhindern soll (S2/S3/S7/S11).
        treffer = _glossar.begriffe_im_text(
            con, f"{e.get('name_en') or ''}\n{e.get('body_md') or ''}")
        # Abkuerzungen getrennt ausweisen: Sie sind etwas anderes als ein Fachbegriff -
        # 'AC' wird nicht "uebersetzt", sondern durch die deutsche Notation ERSETZT, und
        # das Original gehoert dabei NICHT in Klammern dahinter ("RK (AC) 17" waere
        # Unsinn). In einem Topf gaben beide dieselbe Anweisung, obwohl sie
        # Verschiedenes verlangen.
        begriffe = [z for z in treffer if (z["quelle"] or "") != "abkuerzung"]
        kuerzel = [z for z in treffer if (z["quelle"] or "") == "abkuerzung"]
        hinweis = ("Regeltext liegt nur ENGLISCH vor. Antworte dennoch auf Deutsch und "
                   "uebersetze JEDEN englischen Fachbegriff: ")
        if begriffe:
            d["begriffe_deutsch"] = {z["term_en"]: z["term_de"] for z in begriffe}
            hinweis += ("die in 'begriffe_deutsch' aufgefuehrten Begriffe tragen die "
                        "OFFIZIELLE deutsche Form - diese verwenden (Original in Klammern, "
                        "KEIN *). ")
        if kuerzel:
            d["abkuerzungen_deutsch"] = {z["term_en"]: z["term_de"] for z in kuerzel}
            hinweis += ("Die in 'abkuerzungen_deutsch' aufgefuehrten KUERZEL durch ihre "
                        "deutsche Form ersetzen ('AC 17' -> 'RK 17') - hier gehoert das "
                        "englische Kuerzel NICHT in Klammern dahinter. ")
        hinweis += ("Jeden weiteren englischen Fachbegriff (Merkmals-/Zaubernamen), der dort "
                    "nicht steht, konsistent deutsch wiedergeben und mit * markieren "
                    "('* keine offizielle deutsche Uebersetzung', einmal erlaeutern). Das "
                    "*-System NICHT durch Prosa wie 'sinngemaess uebertragen' ersetzen und "
                    "nichts unuebersetzt englisch stehen lassen (S3/S5).")
        d["hinweis_uebersetzung"] = hinweis
    # S12: Abkuerzungen sind die leiseste Stelle, an der eine deutsche Antwort englisch
    # bleibt - "AC 15", "DC 14", "8d6" fallen in einem deutschen Satz nicht auf. Der
    # Hinweis haengt NICHT am englischen Text: auch eine Antwort aus deutscher Quelle
    # kann englisch abkuerzen, wenn das Modell die Kuerzel aus seinem Training nimmt.
    #
    # Bewusst hier und nicht nur in der Instruktion: Von den drei Verhaltenskanaelen ist
    # dieser der einzige, den JEDE Antwort mitfuehrt. Die Projektanweisung muss jede
    # Person selbst in ihr Claude-Projekt kopieren - wer das nicht tut, hatte bis zum
    # 31.07.2026 keine Abkuerzungsregel (SPEC.md §7: die Grounding-Hinweise sind der
    # zuverlaessigste Kanal).
    d["hinweis_abkuerzungen"] = HINWEIS_ABKUERZUNGEN
    fac = _facetten_von(con, e)
    if fac:
        d["facetten"] = fac
    # B11/V9: Gibt es zu diesem Eintrag einen offiziellen Nachtrag, steht er hier daneben.
    # Bewusst in _detail und nicht in einem der Wrapper: BEIDE Detailwege muenden hier -
    # der Namensweg (_hole_detail_impl) und der eintrag_id-Weg (_detail_per_id), der
    # _markiere_inhaltsart gar nicht ruft.
    rev = _revisionen_zu(con, [e])
    if rev:
        for r in rev:
            r.pop("betrifft_eintrag_id", None)   # im Einzelabruf redundant
        d["revisionen"] = rev
        d["hinweis_revision"] = _hinweis_revision({r["inhaltsart"] for r in rev})
    # Bekannter Fehler in der QUELLE selbst (config/quellfehler.py): Der Regeltext oben
    # bleibt unveraendert - hier steht nur daneben, was belegt richtig ist. Dieselbe Zusage
    # wie bei einem Erratum, nur ohne amtliches Korrekturdokument.
    fehler = _quellfehler.quellfehler_zu(e.get("quelle"), e.get("name_de"), e.get("name_en"))
    if fehler and fehler.steht_noch_im_bestand(e.get("body_md")):
        d["hinweis_quellfehler"] = (
            f"⚠️ Bekannter Fehler in dieser Quelle"
            + (f" (S. {fehler.seite})" if fehler.seite else "")
            + f": Dort steht {' bzw. '.join(repr(w) for w in fehler.wortlaute)}. Belegt "
            f"richtig ist '{fehler.richtig}' - {fehler.beleg} Den Quelltext wiedergeben "
            f"WIE ER IST und die Korrektur dazusagen, nicht stillschweigend ersetzen.")
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
