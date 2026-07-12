"""DB-Zugriff: Verbindung + FTS-Suche (bm25 + Exact-Name-Boost, BP #3). F1/Q1.

Suchstrategie (B3, drei Stufen):
  1. FTS5 direkt (name_de UND name_en sind indexiert -> zweisprachig ohne Zusatzlogik).
  2. Glossar-Bruecke: Suchbegriff im Glossar aufloesen (auch Abkuerzungen wie 'AoO'),
     mit den Entsprechungen erneut suchen.
  3. Fuzzy-Fallback (rapidfuzz) ueber die Eintragsnamen fuer kleine Tippfehler.
Ranking: Exact-Name-Treffer VOR Namens-Prefix VOR Lauf-Ordinal (A6: bm25-Scores aus
verschiedenen MATCH-/Fuzzy-Laeufen sind NICHT vergleichbar -> jeder Treffer traegt seinen
Rang im eigenen Lauf; Namens-Tiebreak macht die Ordnung deterministisch).
Edition (A1): Der Editionsfilter wirkt IM SQL vor dem Roh-Limit - viele Treffer einer
anderen Edition koennen die angeforderte nie verdraengen. Default 2024 (V2/Q1); andere
Editionen kommen getrennt als `andere_editionen` zurueck, nie vermischt (V5). Ungueltige/
leere Editionen -> ValueError (keine stille editionsuebergreifende Suche); edition=None
bleibt der EXPLIZITE editionsuebergreifende Modus fuer interne Aufrufer (Detail-Auswahl).
Dubletten gleicher Version/Kategorie loest quellen.prioritaet auf (Q2, kleiner = Vorrang).
"""
from __future__ import annotations

import re
import sqlite3
import tomllib
from pathlib import Path

from rapidfuzz import fuzz, process

from app.glossar import KLAMMER_SUFFIX as _KLAMMER_SUFFIX
from app.glossar import norm_begriff as _gl_norm

STANDARD_EDITION = "2024"
# SYN-P2-001 (codex TECH-011/DND-017): 'unterstuetzt' und 'im Bestand vorhanden' sind
# verschiedene Dinge - ein reiner 2014-Bestand lehnte den 2024-Default als 'unbekannt'
# ab, ein LEERER Bestand akzeptierte jeden String. Unterstuetzt ist konfiguriert;
# Verfuegbarkeit regelt die Suche (leere Treffer + andere_fassungen). Das projektintern
# genutzte '5.5e' ist ein Alias, kein Fehler.
UNTERSTUETZTE_EDITIONEN = ("2024", "2014")
EDITION_ALIASSE = {"5.5e": "2024", "5e": "2014"}


def normalisiere_edition(edition: str | None) -> str | None:
    """Nutzer-Aliasse ('5.5e', '5e') auf kanonische Editionen abbilden; None bleibt der
    explizite editionsuebergreifende Modus."""
    if edition is None:
        return None
    e = str(edition).strip()
    return EDITION_ALIASSE.get(e.lower(), e)

# Die EINE Kategorien-Whitelist (Schema-Kommentar, admin check und Tool-Validierung
# nutzten bisher je eigene Kopien). SYN-P0-006: ein unbekannter kategorie-Wert lief als
# stiller SQL-Filter durch und erzeugte ein falsches 'Nichts im Bestand' samt
# B1-Ehrlichkeitshinweis - die schaedlichste Antwortklasse nach der Halluzination.
KATEGORIEN = ("regel", "zauber", "monster", "gegenstand", "spezies", "klasse",
              "hintergrund", "talent")

_PROJEKT = Path(__file__).resolve().parent.parent
_KONFIG = _PROJEKT / "config" / "foliant.toml"


def projekt_pfad(pfad: str | Path) -> Path:
    """Relative Pfade IMMER ab Projektroot aufloesen (A8) - nie abhaengig vom aktuellen
    Arbeitsverzeichnis. EIN Ort fuer Tools, Admin-CLI und Importer."""
    p = Path(pfad)
    return p if p.is_absolute() else _PROJEKT / p


def standard_pfad() -> Path:
    """DB-Pfad aus config/foliant.toml ([db].pfad), sonst data/foliant.sqlite."""
    pfad = "data/foliant.sqlite"
    if _KONFIG.exists():
        pfad = tomllib.loads(_KONFIG.read_text(encoding="utf-8")).get("db", {}).get("pfad", pfad)
    return projekt_pfad(pfad)


def lade_konfig() -> dict:
    """config/foliant.toml als dict; {} wenn (noch) keine angelegt ist."""
    if _KONFIG.exists():
        return tomllib.loads(_KONFIG.read_text(encoding="utf-8"))
    return {}

# Kappt die Roh-Treffermenge vor der Python-Nachverarbeitung (Dedupe/Boost).
_ROH_FAKTOR = 5
# SYN-P2-004 (codex TECH-013): Eingabe-/Ausgabegrenzen gegen versehentliche oder
# boeswillige Ueberlast. MAX_QUERY kappt ueberlange Suchbegriffe (der FTS-Tokenizer und
# rapidfuzz skalieren mit der Laenge); MAX_LIMIT deckelt die angeforderte Treffermenge.
MAX_QUERY_ZEICHEN = 200
MAX_LIMIT = 50


def connect(pfad: str) -> sqlite3.Connection:
    """Review-Fund: FastMCP fuehrt sync-Tools im Threadpool aus -> KEINE geteilte globale
    Connection. Pro Tool-Aufruf eine Verbindung oeffnen/schliessen (SQLite-Open ist billig,
    Workload read-only); alternativ check_same_thread=False + eigene Serialisierung."""
    con = sqlite3.connect(pfad)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def connect_readonly(pfad: str) -> sqlite3.Connection:
    """Read-only-Verbindung fuer den SERVING-Pfad (SYN-P1-005 + codex TECH-020): die
    Tools lesen ausschliesslich - mode=ro + query_only machen eine Schreibtransaktion
    schon auf App-Ebene unmoeglich (zweite Leitplanke neben dem read-only Volume-Mount).
    Fuer Import/Admin bleibt connect() (read-write)."""
    con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON;")
    return con


def _norm(text: str | None) -> str:
    return (text or "").strip().lower()


def _fts_match(suchbegriff: str) -> str:
    """Roh-Eingabe in sichere FTS5-Query verwandeln: Tokens quoten + Prefix-Stern.
    Quoting neutralisiert FTS5-Operatoren (AND/OR/NEAR, Klammern, '-')."""
    tokens = re.findall(r"[^\W_]+", suchbegriff, re.UNICODE)
    return " ".join(f'"{t}"*' for t in tokens)


_SQL_FTS = """
SELECT e.id, e.kategorie, e.name_de, e.name_en, e.sprache, e.edition, e.seite,
       q.kuerzel AS quelle, q.titel AS quelle_titel, q.prioritaet,
       bm25(eintraege_fts, 10.0, 10.0, 1.0) AS score,
       snippet(eintraege_fts, 2, '»', '«', ' … ', 16) AS auszug
FROM eintraege_fts
JOIN eintraege e ON e.id = eintraege_fts.rowid
JOIN quellen q  ON q.id = e.quelle_id
WHERE eintraege_fts MATCH :match
"""


def _editionen(con: sqlite3.Connection) -> set[str]:
    """Im Bestand vorhandene Regelversionen - die 'klar definierte Menge' fuer die
    Editions-Validierung (A1); waechst mit neuen Quellen ohne Migration (V7)."""
    return {r[0] for r in con.execute("SELECT DISTINCT edition FROM eintraege")}


def _pruefe_edition(con: sqlite3.Connection, edition: str | None) -> None:
    """A1/SYN-P2-001: leere/NICHT UNTERSTUETZTE Editionen strukturiert ablehnen statt
    still editionsuebergreifend zu suchen. Eine unterstuetzte, aber (noch) nicht
    importierte Edition ist KEIN Fehler - die Suche liefert dann ehrlich leere Treffer
    plus die vorhandenen Fassungen. None = expliziter editionsuebergreifender Modus."""
    if edition is None:
        return
    if not isinstance(edition, str) or not edition.strip() or \
            edition not in UNTERSTUETZTE_EDITIONEN:
        verfuegbar = sorted(_editionen(con))
        raise ValueError(
            f"Nicht unterstuetzte Regelversion {edition!r} - unterstuetzt: "
            f"{', '.join(UNTERSTUETZTE_EDITIONEN)} (Aliasse: "
            f"{', '.join(EDITION_ALIASSE)}); im Bestand: "
            f"{', '.join(verfuegbar) or '(leer)'}. Standard ist '{STANDARD_EDITION}'.")


def _pruefe_kategorie(kategorie: str | None) -> None:
    """SYN-P0-006: unbekannte Kategorie strukturiert ablehnen statt still leer zu filtern
    (analog _pruefe_edition). None = kein Filter."""
    if kategorie is None:
        return
    if kategorie not in KATEGORIEN:
        raise ValueError(f"Unbekannte Kategorie {kategorie!r} - gueltig: "
                         f"{', '.join(KATEGORIEN)}.")


def _pruefe_quelle(con: sqlite3.Connection, quelle: str | None) -> None:
    """SYN-P0-006: unbekanntes Quellen-Kuerzel strukturiert ablehnen. Haeufigster
    Fehlaufruf: der TITEL aus einem Suchtreffer statt des Kuerzels."""
    if quelle is None:
        return
    kuerzel = [r[0] for r in con.execute(
        "SELECT kuerzel FROM quellen ORDER BY prioritaet")]
    if quelle not in kuerzel:
        raise ValueError(
            f"Unbekannte Quelle {quelle!r} - gueltig sind die KUERZEL "
            f"{', '.join(kuerzel) or '(keine Quellen im Bestand)'} (nicht der Titel).")


def _roh_suche(con: sqlite3.Connection, match: str, kategorie: str | None,
               quelle: str | None, roh_limit: int, edition: str | None = None,
               edition_ausser: str | None = None) -> list[dict]:
    """Ein FTS-Lauf. Der Editionsfilter steht IM SQL, damit er VOR dem LIMIT wirkt (A1) -
    sonst verdraengen viele Treffer einer anderen Edition die angeforderte. ORDER BY hat
    einen expliziten id-Sekundaerschluessel: bm25-Gleichstaende bleiben deterministisch (A6)."""
    if not match:
        return []
    sql, params = _SQL_FTS, {"match": match, "limit": roh_limit}
    if kategorie:
        sql += " AND e.kategorie = :kategorie"
        params["kategorie"] = kategorie
    if quelle:
        sql += " AND q.kuerzel = :quelle"
        params["quelle"] = quelle
    if edition:
        sql += " AND e.edition = :edition"
        params["edition"] = edition
    if edition_ausser:
        sql += " AND e.edition != :edition_ausser"
        params["edition_ausser"] = edition_ausser
    sql += " ORDER BY score ASC, e.id LIMIT :limit"
    return [dict(r) for r in con.execute(sql, params)]


def _glossar_alternativen(con: sqlite3.Connection, begriff: str,
                          nur_exakt: bool = False) -> list[str]:
    """B3-Bruecke: liefert deutsche UND englische Entsprechungen aus dem Glossar
    (inkl. Abkuerzungen wie 'AoO'), mit denen erneut gesucht werden kann.
    Nutzt glossar.lookup und damit die S11-Normalisierung - noetig, weil die
    dnddeutsch-API teils Pluralformen liefert ('Gelegenheitsangriffe') und der Bestand
    englische Eintraege hat: 'Gelegenheitsangriff' -> Glossar -> 'Opportunity Attacks'.

    nur_exakt=True liefert ausschliesslich EXAKTE Glossarbeziehungen - die einzige
    zulaessige Basis fuer Identitaet, Exakt-Boost und Detail-Auswahl (SYN-P0-001:
    Fuzzy-Naehe wie 'Aktionen'~'Reaktionen' ist ein Suchvorschlag, keine Entsprechung).
    Der Standardmodus (fuzzy inklusive) bleibt der RECALL-Pfad der Suche (S11-Flexion:
    'Todesrettungswurf' muss die Plural-Glossarzeile treffen)."""
    from app import glossar as _gl

    n = _norm(begriff)
    if not n:
        return []

    def sammle(suchwort: str, gesehen: set[str]) -> list[str]:
        gefunden: list[str] = []
        for richtung in ("de_en", "en_de"):
            for z in _gl.lookup(con, suchwort, richtung=richtung):
                if nur_exakt and z["match"] != "exakt":
                    continue
                for kandidat in (z["term_en"], z["term_de"]):
                    if kandidat and _norm(kandidat) not in gesehen:
                        gesehen.add(_norm(kandidat))
                        gefunden.append(kandidat)
        return gefunden

    # Zwei Hops: 'AoO' -> 'Gelegenheitsangriff' (Abkuerzungszeile) -> 'Opportunity Attacks'
    # (Plural-Zeile). Noetig, weil Abkuerzungen auf den deutschen Begriff zeigen, der Bestand
    # aber englisch sein kann.
    gesehen = {n}
    erste = sammle(begriff, gesehen)
    zweite: list[str] = []
    for zwischenbegriff in erste:
        zweite += sammle(zwischenbegriff, gesehen)
    return (erste + zweite)[:8]


def _fuzzy_treffer(con: sqlite3.Connection, begriff: str, kategorie: str | None,
                   quelle: str | None, roh_limit: int, edition: str | None = None,
                   edition_ausser: str | None = None) -> list[dict]:
    """Stufe 3 (B3): kleine Tippfehler ueber rapidfuzz auf den Eintragsnamen abfangen.
    A6: der echte Fuzzy-Score bleibt am Treffer (Sortiergrundlage), die Reihenfolge folgt
    dem Score (bester zuerst; Namens-Tiebreak fuer Determinismus)."""
    sql = ("SELECT e.id, e.edition, coalesce(e.name_de,'') AS nd, coalesce(e.name_en,'') AS ne "
           "FROM eintraege e JOIN quellen q ON q.id = e.quelle_id WHERE 1=1")
    params: list = []
    if kategorie:
        sql += " AND e.kategorie = ?"
        params.append(kategorie)
    if quelle:
        sql += " AND q.kuerzel = ?"
        params.append(quelle)
    if edition:
        sql += " AND e.edition = ?"
        params.append(edition)
    if edition_ausser:
        sql += " AND e.edition != ?"
        params.append(edition_ausser)
    namen: dict[str, set[int]] = {}
    for r in con.execute(sql, params):
        for name in (r["nd"], r["ne"]):
            if name:
                namen.setdefault(name, set()).add(r["id"])
    if not namen:
        return []
    passend = process.extract(begriff, sorted(namen.keys()),
                              scorer=fuzz.WRatio, score_cutoff=86, limit=roh_limit)
    passend.sort(key=lambda t: (-t[1], t[0]))          # Score DESC, Name als Tiebreak
    score_je_id: dict[int, float] = {}
    ids: list[int] = []
    for name, score, _idx in passend:
        for eid in sorted(namen[name]):
            if eid not in score_je_id:
                score_je_id[eid] = score
                ids.append(eid)
    if not ids:
        return []
    marker = ",".join("?" * len(ids))
    rows = con.execute(
        f"""SELECT e.id, e.kategorie, e.name_de, e.name_en, e.sprache, e.edition, e.seite,
                   q.kuerzel AS quelle, q.titel AS quelle_titel, q.prioritaet,
                   substr(e.body_md, 1, 160) AS auszug
            FROM eintraege e JOIN quellen q ON q.id = e.quelle_id
            WHERE e.id IN ({marker})""",
        ids,
    ).fetchall()
    nach_id = {r["id"]: dict(r) for r in rows}
    treffer = [nach_id[i] for i in ids if i in nach_id]
    for t in treffer:
        t["score"] = score_je_id[t["id"]]              # echter rapidfuzz-Score (A6)
    return treffer


def _brueckennamen(con: sqlite3.Connection) -> dict[str, set[str]]:
    """EXAKTE Glossar-Paare als Namensbruecke der Dubletten-Erkennung (A3):
    norm(begriff) -> {norm(gegenstueck), ...}. Bewusst OHNE Fuzzy: Aehnlichkeit allein
    begruendet keine fachliche Dublette (nur belastbare, exakte Entsprechungen).
    SYN-P2-004: liest die gecachten Glossarzeilen statt eines eigenen Voll-Scans."""
    from app import glossar as _gl
    bruecke: dict[str, set[str]] = {}
    for z in _gl._alle_zeilen(con):
        nde, nen = _gl_norm(z["term_de"]), _gl_norm(z["term_en"])
        if nde and nen and nde != nen:
            bruecke.setdefault(nde, set()).add(nen)
            bruecke.setdefault(nen, set()).add(nde)
    return bruecke


def _dedupe_und_sortiere(con: sqlite3.Connection, treffer: list[dict],
                         suchbegriffe: set[str], original: str | None = None) -> list[dict]:
    """Q2/A3: DE- und EN-Eintraege desselben Inhalts in derselben Edition+Kategorie sind
    EINE fachliche Dublette - Identitaetsschluessel aus normalisierten Namen plus exakten
    Glossarentsprechungen. Die Quelle mit der kleinsten prioritaet liefert den kanonischen
    Treffer; die uebrigen bleiben als `weitere_quellen` (Provenienz) erhalten. Editionen
    und Kategorien mischen nie. Danach Exact-Name-Boost VOR Prefix VOR Lauf-Ordinal
    (BP #3/A6). suchbegriffe enthaelt Original UND Glossar-Aufloesungen - so gewinnt bei
    'Fireball' der deutsche 'Feuerball'-Eintrag (S10: deutscher Regeltext primaer)."""
    begriffe = {_norm(s) for s in suchbegriffe if s}
    bruecke = _brueckennamen(con) if treffer else {}

    gruppen: list[dict] = []                 # {"schluessel": set, "mitglieder": [t, ...]}
    index: dict[tuple, dict] = {}            # (namensvariante, edition, kategorie) -> Gruppe
    for t in treffer:
        namen = {_gl_norm(t["name_de"]), _gl_norm(t["name_en"])} - {""}
        erweitert = set(namen)
        for n in namen:
            erweitert |= bruecke.get(n, set())
        schluessel = {(n, t["edition"], t["kategorie"]) for n in erweitert}
        betroffen = {id(index[s]): index[s] for s in schluessel if s in index}
        if betroffen:
            gruppe, *rest = betroffen.values()
            for r in rest:                   # Treffer verbindet mehrere Gruppen -> Union
                gruppe["mitglieder"] += r["mitglieder"]
                gruppe["schluessel"] |= r["schluessel"]
                gruppen.remove(r)
        else:
            gruppe = {"schluessel": set(), "mitglieder": []}
            gruppen.append(gruppe)
        gruppe["mitglieder"].append(t)
        gruppe["schluessel"] |= schluessel
        for s in gruppe["schluessel"]:
            index[s] = gruppe

    kanonisch: list[dict] = []
    for g in gruppen:
        je_quelle: dict[str, int] = {}
        for m in g["mitglieder"]:
            je_quelle[m["quelle"]] = je_quelle.get(m["quelle"], 0) + 1
        if any(n > 1 for n in je_quelle.values()):
            # Gleichnamige Eintraege DERSELBEN Quelle sind keine Dublette, sondern
            # verschiedene Abschnitte (Regelglossar-Kurzverweis vs. Kernkapitel) -
            # das Verschmelzen liess 'vollstaendige' Steckbriefe zu Fragmenten werden
            # (SYN-P0-003, 'Solar'). Alle Mitglieder bleiben eigene Treffer; die
            # Detail-Schicht loest Mehrdeutigkeit per Kandidaten auf (B4).
            kanonisch.extend(dict(m) for m in g["mitglieder"])
            continue
        mitglieder = sorted(g["mitglieder"],
                            key=lambda m: (m["prioritaet"], m.get("lauf_rang", 0),
                                           _norm(m["name_de"]) or _norm(m["name_en"])))
        t = dict(mitglieder[0])              # kanonischer Text = kleinste prioritaet (A3)
        t["name_de"] = next((m["name_de"] for m in mitglieder if m["name_de"]), None)
        t["name_en"] = next((m["name_en"] for m in mitglieder if m["name_en"]), None)
        weitere = sorted({m["quelle_titel"] for m in mitglieder[1:]}
                         - {mitglieder[0]["quelle_titel"]})
        if weitere:
            t["weitere_quellen"] = weitere
        if len(mitglieder) > 1:
            # SYN-P1-009: die IDs der weggemergten Fassungen mitfuehren - nur so kann
            # die Detail-Schicht Textabweichungen erkennen (Konflikt-/Fremdfassungs-
            # Ausweis) und das Modell eine bestimmte Fassung per eintrag_id nachladen.
            t["weitere_fassungen"] = [
                {"id": m["id"], "quelle_titel": m["quelle_titel"],
                 "sprache": m["sprache"]} for m in mitglieder[1:]]
        kanonisch.append(t)

    def rang(t: dict) -> tuple:
        nd, ne = _norm(t["name_de"]), _norm(t["name_en"])
        namen = {nd, ne}
        # srd-de-Unterklassenschema: 'Kämpfer-Unterklasse: Champion' zaehlt auch als
        # exakter 'Champion'-Treffer - sonst verliert der deutsche Eintrag gegen Open5e.
        m = re.match(r".+-unterklasse:\s*(.+)$", nd)
        if m:
            namen.add(m.group(1).strip())
        # Klammer-Suffix ('Erschöpfung (Zustand)') zaehlt auch ohne Zusatz als exakt
        # (SYN-P0-002; kanonische Definition in glossar.KLAMMER_SUFFIX).
        for n in list(namen):
            ohne = _KLAMMER_SUFFIX.sub("", n).strip()
            if ohne:
                namen.add(ohne)
        exakt = 0 if begriffe & namen else 1
        prefix = 0 if any(b and n.startswith(b) for n in namen for b in begriffe) else 1
        # SYN-P1-006 (claude DND-011): Praefix auf den ORIGINAL-Suchbegriff rankt vor
        # Praefix auf eine Glossar-Alternative ('Verstecken' -> erst die Aktion, nicht
        # 'Hide Armor' ueber die 'Hide'-Alternative).
        o = _norm(original) if original else ""
        prefix_orig = 0 if o and any(n.startswith(o) for n in namen) else 1
        # A6: bm25-/Fuzzy-Scores verschiedener Laeufe sind unvergleichbar -> das Ordinal
        # im eigenen Lauf (lauf_rang) vergleicht fair; der Name macht Gleichstaende
        # deterministisch. Bei exakten Treffern entscheidet die Quellen-Praezedenz
        # zuerst (Q2/S10 - deutsche Quelle vor Open5e).
        if exakt == 0:
            return (0, prefix_orig, prefix, t["prioritaet"], t.get("lauf_rang", 0), nd or ne)
        return (1, prefix_orig, prefix, t.get("lauf_rang", 0), t["prioritaet"], nd or ne)

    return sorted(kanonisch, key=rang)


def _sammle_roh(con: sqlite3.Connection, query: str, alternativen: list[str],
                kategorie: str | None, quelle: str | None, roh_limit: int,
                edition: str | None = None, edition_ausser: str | None = None,
                ) -> tuple[list[dict], str]:
    """Alle Suchlaeufe fuer EINEN Editionsfilter: FTS mit Original + Glossar-Alternativen
    (immer, S10), Fuzzy nur als Fallback. Jeder Treffer bekommt sein Lauf-Ordinal
    `lauf_rang` (A6). Liefert (treffer, suchweg)."""
    suchweg = "direkt"
    roh: list[dict] = []
    ids: set[int] = set()
    for i, begriff in enumerate([query, *alternativen]):
        zusatz = [t for t in _roh_suche(con, _fts_match(begriff), kategorie, quelle,
                                        roh_limit, edition, edition_ausser)
                  if t["id"] not in ids]
        for rang, t in enumerate(zusatz):
            t["lauf_rang"] = rang
        if zusatz and not roh and i > 0:
            suchweg = f"glossar:{begriff}"
        roh += zusatz
        ids |= {t["id"] for t in zusatz}
    if not roh:
        roh = _fuzzy_treffer(con, query, kategorie, quelle, roh_limit,
                             edition, edition_ausser)
        for rang, t in enumerate(roh):
            t["lauf_rang"] = rang
        suchweg = "fuzzy" if roh else "-"
    return roh, suchweg


def fts_suche(con: sqlite3.Connection, query: str, kategorie: str | None = None,
              edition: str | None = STANDARD_EDITION, quelle: str | None = None,
              limit: int = 8) -> dict:
    """Volltextsuche. Default edition=2024 (V2/Q1); edition=None sucht AUSDRUECKLICH
    editionsuebergreifend (interner Modus, z. B. Detail-Auswahl); leere/unbekannte
    Editionen -> ValueError (A1). Liefert KNAPPE Treffer (Name, Auszug, Quelle, ggf.
    Seite, Version) - nicht die vollen Bodies (BP #1). Rueckgabe:
      {"treffer": [...], "andere_editionen": [...], "suchweg": "direkt|glossar|fuzzy|-"}
    treffer: nur die angeforderte Edition, editions-gefiltert VOR dem Roh-Limit (A1).
    andere_editionen: Treffer aller uebrigen Editionen, IMMER getrennt (Q1/V5) - die
    Tool-Schicht benennt sie kontextgerecht (bei 2024-Standard: 'aeltere_staende'/B5)."""
    edition = normalisiere_edition(edition)
    _pruefe_edition(con, edition)
    _pruefe_kategorie(kategorie)
    _pruefe_quelle(con, quelle)
    # SYN-P2-004: harte Grenzen. Ueberlange Query kappen (statt abzulehnen - der Nutzer
    # soll ein Ergebnis bekommen), limit deckeln.
    query = (query or "")[:MAX_QUERY_ZEICHEN]
    limit = min(max(int(limit), 1), MAX_LIMIT)
    roh_limit = limit * _ROH_FAKTOR
    # Glossar-Aufloesungen IMMER mitsuchen (nicht nur bei Null Treffern): 'Fireball' soll
    # auch den deutschen 'Feuerball'-Eintrag liefern - deutscher Regeltext primaer (S10).
    alternativen = _glossar_alternativen(con, query)
    # Exakt-Boost NUR aus exakten Beziehungen: eine Fuzzy-Alternative darf einen fremden
    # Begriff nie als exakten Treffer nach vorn heben (SYN-P0-001, 'Aktionen'~'Reaktionen').
    begriffe = {query, *_glossar_alternativen(con, query, nur_exakt=True)}

    roh, suchweg = _sammle_roh(con, query, alternativen, kategorie, quelle,
                               roh_limit, edition=edition)
    sortiert = _dedupe_und_sortiere(con, roh, begriffe, original=query)

    andere: list[dict] = []
    if edition is not None and _editionen(con) - {edition}:
        # Eigener, editions-getrennter Lauf statt Nachfilterung: so verdraengen sich die
        # Editionen nie gegenseitig (A1) und der Zusatz bleibt klein (V5/Q1).
        roh_andere, _ = _sammle_roh(con, query, alternativen, kategorie, quelle,
                                    max(3, limit // 2) * _ROH_FAKTOR,
                                    edition_ausser=edition)
        andere = _dedupe_und_sortiere(con, roh_andere, begriffe, original=query)

    for t in (*sortiert, *andere):
        t.pop("prioritaet", None)
        t.pop("score", None)
        t.pop("lauf_rang", None)
    return {
        "treffer": sortiert[:limit],
        "andere_editionen": andere[: max(3, limit // 2)],
        "suchweg": suchweg,
    }


def fts_rebuild(con: sqlite3.Connection) -> None:
    """FTS extern neu aufbauen - nach jedem (Bulk-)Import Pflicht (Leitplanke): robuster als
    inkrementelle Trigger-Synchronitaet bei grossen Importen."""
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()


def hole_eintrag(con: sqlite3.Connection, eintrag_id: int) -> dict | None:
    """Voller Eintrag (fuer Detail-Tools/BP #1) inkl. Quelle/Edition/Seite."""
    r = con.execute(
        """SELECT e.id, e.kategorie, e.name_de, e.name_en, e.sprache, e.edition,
                  e.seite, e.body_md, q.kuerzel AS quelle, q.titel AS quelle_titel,
                  q.lizenz, q.edition AS quelle_edition
           FROM eintraege e JOIN quellen q ON q.id = e.quelle_id WHERE e.id = ?""",
        (eintrag_id,),
    ).fetchone()
    return dict(r) if r else None
