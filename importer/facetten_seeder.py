"""Facetten persistieren - die EINE Senke fuer strukturierte Werte (Phase 3, 28.07.2026).

Befund C1 des Import-/Datenbank-Reviews: `zauber_meta`/`monster_meta`/`gegenstand_meta`
waren auf dem produktiven Pi-Bestand LEER (0 Zeilen bei 4481 passenden Eintraegen), lokal
dagegen teilweise gefuellt - ein unbemerkter Dev/Prod-Drift. Ursache: nur der Open5e-Import
schrieb ueberhaupt Facetten, und der deutsch-gewinnende Dedup lieferte anschliessend fast
immer eine srd-de-ID, die keine Meta-Zeile hatte. Die Werte wurden also berechnet und
weggeworfen; die Suche parste sie stattdessen bei JEDER Anfrage neu aus dem body_md.

Dieses Modul ist kein neuer Parser, sondern eine Senke: es ruft die vorhandenen Parser und
schreibt deren Ergebnis fuer ALLE Quellen weg.

    app/facetten.py                grad, schule, klassen | hg, typ, rk, tp
    srd_zauberbruecken.kopf_felder reichweite, komponenten, dauer, konzentration, ritual
    srd_begriffsbruecken           preis_cent

WELCHE Spalten wohin gehoeren, steht in `app.facetten.META_TABELLEN` - dieselbe Definition,
aus der der LESER (app/tools/nachschlagen.py) die Facetten holt. Bis zum 29.07.2026 fuehrte
jede Seite ihre eigene, byte-identische Kopie; eine neue Facette erschien deshalb nie in der
Tool-Ausgabe, bis jemand die zweite Liste fand.

Zwei Entscheidungen, beide gemessen (28.07.2026 am Mac-Subset, 3084 Eintraege):

1. EIN Wertraum. Der alte Open5e-Pfad schrieb aus den nativen API-Feldern und damit in einen
   ZWEITEN Wertraum: `hg='10.0'` statt kanonisch `'10'`, `schule='Evocation'` statt
   `'hervorrufung'`. facetten.monster_hg normalisiert Dezimal-HG ausdruecklich, weil
   hg_passt('4') die Open5e-Fassung sonst verfehlt - die Meta-Tabelle widersprach also der
   Filterlogik. Hier gilt durchgaengig der kanonische Schluessel aus app/facetten.py, damit
   Filter (Suche) und Anzeige (Detail) nie auseinanderlaufen koennen.

2. Ableitung aus dem body_md, nicht aus Quellformaten. Genau die Funktionen, die der
   Serving-Pfad heute zur Laufzeit ruft - dadurch ist der persistierte Wert per Konstruktion
   derselbe wie der bisher berechnete. Erreicht am Subset 100 % (Open5e) bzw. 93 % (srd-de)
   bei grad/schule/klassen; die Luecke sind die bekannten Nicht-Zauber in der Kategorie
   `zauber` (BACKLOG §3: `Dauer`, `Effekte`, `Verbalkomponente (V)`).

Regel 1 gilt unveraendert: was der Text nicht hergibt, bleibt NULL. Eine fehlende Facette
ist ein fehlendes Feld, nie ein geratener Wert.
"""
from __future__ import annotations

import sqlite3

from app import facetten as _f
from importer import srd_begriffsbruecken as _gb
from importer import srd_zauberbruecken as _zb


def _zauber_werte(body: str | None, name: str | None, deutsch: bool) -> dict:
    grad = _f.zauber_grad(body)
    klassen = _f.zauber_klassen(body)
    kopf = _zb.kopf_felder(body, deutsch)
    return {
        "grad": grad,
        "schule": _f.zauber_schule(body),
        "klassen": ", ".join(klassen) or None,
        "reichweite_m": kopf["reichweite_m"],
        "komponenten": kopf["komponenten"],
        "dauer_min": kopf["dauer_min"],
        "konzentration": kopf["konzentration"],
        # Ohne erkannten Grad ist der Kopf nicht als Zauberkopf belegt - dann heisst ein
        # fehlender Ritual-Marker 'unbekannt', nicht 'kein Ritual' (Regel 1). Sonst waere
        # jeder unerkannte Eintrag stillschweigend als Nicht-Ritual behauptet.
        "ritual": kopf["ritual"] if grad is not None else None,
    }


def _monster_werte(body: str | None, name: str | None, deutsch: bool) -> dict:
    rk, tp = _f.monster_rk(body), _f.monster_tp(body)
    return {"hg": _f.monster_hg(body), "typ": _f.monster_typ(body),
            "rk": int(rk) if rk else None, "tp": int(tp) if tp else None}


def _gegenstand_werte(body: str | None, name: str | None, deutsch: bool) -> dict:
    return {"preis_cent": _gb.preis_cent_von(name, body, deutsch)}


_PARSER = {"zauber": _zauber_werte, "monster": _monster_werte,
           "gegenstand": _gegenstand_werte}


def seed_facetten(con: sqlite3.Connection, quelle_id: int | None = None) -> dict[str, int]:
    """Facetten fuer eine Quelle (quelle_id) oder den GESAMTEN Bestand (None) schreiben.

    Idempotent per INSERT OR REPLACE: ein zweiter Lauf liefert dasselbe Ergebnis, und ein
    Re-Import braucht keine Sonderbehandlung (die alten Zeilen sind ohnehin schon per
    FK ON DELETE CASCADE mit den Eintraegen verschwunden).

    Der Voll-Lauf ist der Nachruest-Weg fuer Bestands-DBs: die Facetten lassen sich damit
    OHNE Re-Import nachziehen. Das ist wichtig, weil ein Re-Import die Namensreparatur der
    2014-Scans zunichte machen wuerde (BACKLOG §1/M1).

    Rueckgabe: {'zauber': n, 'monster': n, 'gegenstand': n} - geschriebene Zeilen je
    Kategorie (nur Zeilen mit MINDESTENS einem erkannten Wert; ein Eintrag, aus dem sich
    nichts ableiten laesst, bekommt bewusst gar keine Zeile statt einer leeren)."""
    bedingung = "WHERE e.kategorie = ?" + ("" if quelle_id is None else " AND e.quelle_id = ?")
    bilanz: dict[str, int] = {}
    for kategorie, (tabelle, felder) in _f.META_TABELLEN.items():
        # Erst raeumen, dann schreiben: INSERT OR REPLACE ersetzt nur Zeilen, die dieser
        # Lauf auch anfasst. Eine Alt-Zeile zu einem Eintrag, aus dem sich heute nichts
        # mehr ableiten laesst, ueberlebte sonst - und mit ihr ein FREMDER Wertraum (der
        # Open5e-Sonderweg schrieb 'Evocation' statt 'hervorrufung'). Der Suchpfad filtert
        # aber gegen die Meta-Werte vor; ein Mischbestand liesse ihn still zu wenig
        # liefern. Nach diesem Lauf gilt: was in der Tabelle steht, stammt von hier.
        if quelle_id is None:
            con.execute(f"DELETE FROM {tabelle}")
        else:
            con.execute(f"DELETE FROM {tabelle} WHERE eintrag_id IN "
                        f"(SELECT id FROM eintraege WHERE quelle_id = ?)", (quelle_id,))
        parse = _PARSER[kategorie]
        zeilen: list[tuple] = []
        parameter = (kategorie,) if quelle_id is None else (kategorie, quelle_id)
        for eid, name_de, name_en, sprache, body in con.execute(
                f"SELECT e.id, e.name_de, e.name_en, e.sprache, e.body_md "
                f"FROM eintraege e {bedingung}", parameter):
            werte = parse(body, name_de or name_en, sprache == "de")
            if all(werte[f] is None for f in felder):
                continue
            zeilen.append((eid, *(werte[f] for f in felder)))
        if zeilen:
            con.executemany(
                f"INSERT OR REPLACE INTO {tabelle} (eintrag_id, {', '.join(felder)}) "
                f"VALUES ({', '.join('?' * (len(felder) + 1))})", zeilen)
        bilanz[kategorie] = len(zeilen)
    return bilanz


def deckung(con: sqlite3.Connection) -> list[tuple[str, int, int]]:
    """[(kategorie, mit_facette, gesamt), ...] - Grundlage der Deckungs-Zeile in
    `admin check`. Ohne sie bliebe ein Dev/Prod-Drift wie C1 wieder unbemerkt."""
    ergebnis = []
    for kategorie, (tabelle, _felder) in _f.META_TABELLEN.items():
        gesamt = con.execute("SELECT count(*) FROM eintraege WHERE kategorie = ?",
                             (kategorie,)).fetchone()[0]
        try:
            mit = con.execute(
                f"SELECT count(*) FROM {tabelle} m JOIN eintraege e ON e.id = m.eintrag_id "
                f"WHERE e.kategorie = ?", (kategorie,)).fetchone()[0]
        except sqlite3.OperationalError:
            mit = 0                                  # Alt-DB ohne die Tabelle
        ergebnis.append((kategorie, mit, gesamt))
    return ergebnis
