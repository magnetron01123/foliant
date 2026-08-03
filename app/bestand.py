"""Bestandsübersicht: welche Bücher stecken drin? — die GEMEINSAME Logik dahinter.

Die Frage stellen zwei Oberflächen: die Website (`app/charakterbogen/web.py`, Karte „Was
steckt drin?") und der Discord-Befehl `/bestand` (`app/discord_bot/bestand.py`). Beide
müssen dieselbe Antwort geben - und zwar nicht nur ungefähr: Ein Buch, das auf der Seite
unter „Regelwerke" steht, darf im Bot nicht unter „Abenteuer & Settings" auftauchen. Die
Gruppierung ist keine Kosmetik, sondern die Ansage, WOZU Foliant aus dieser Quelle
Auskunft gibt (aus Abenteuerbänden nur Regelwerte, nie Handlung - Spoiler-Schutz ist die
oberste Verhaltensregel).

Hier steht deshalb, was BEIDE brauchen: Sprachname, Regelstand-Beschriftung und die
Zuordnung zu den drei Gruppen. Die Darstellung selbst - HTML-Tabelle dort, Textblock hier -
bleibt bei der jeweiligen Oberfläche; sie ist das, was sich unterscheiden DARF.

Bewusst ohne Abhängigkeit auf `app.db`, Starlette oder discord.py: reine Daten- und
Textlogik über einer offenen SQLite-Verbindung. Die Website liest die schmale Web-DB
(nur Metadaten), der Bot den Vollbestand - wer die Verbindung öffnet, entscheidet der
Aufrufer.
"""
from __future__ import annotations

import sqlite3

# Foliant führt heute nur deutsche und englische Quellen. Eine dritte Sprache wäre
# deshalb nicht "unbekannt", sondern schlicht neu - und würde ohne diese Zuordnung als
# "Englisch" ausgewiesen, weil alles Nicht-Deutsche vorher in den Englisch-Zweig fiel.
# Ein falsches Etikett ist schlechter als ein ungewohntes: der Sprachcode ist ehrlich.
SPRACHNAMEN = {"de": "Deutsch", "en": "Englisch"}

# Die drei Gruppen, in der Reihenfolge, in der sie ausgegeben werden.
REGELWERKE = "Regelwerke"
REVISION = "Errata & Regelauslegung"
ABENTEUER = "Abenteuer & Settings"

# Zuordnung als POSITIVLISTE, nicht als Ausschluss: ein `!= 'abenteuer_setting'` liess
# bis zum 31.07.2026 alles Neue unter den Regelwerken landen - die Errata-Quellen
# stuenden dort, als waeren sie Regelbuecher. Eine kuenftige inhaltsart faellt hier
# sichtbar in die Regelwerke und wird dann bewusst eingeordnet.
_ARTEN = {REVISION: ("errata", "regelauslegung"),
          ABENTEUER: ("abenteuer_setting",)}


def sprachname(code: str | None) -> str:
    """'de' -> 'Deutsch'. Unbekannter Code bleibt als Code stehen (s. SPRACHNAMEN)."""
    kurz = (code or "").strip().lower()[:2]
    return SPRACHNAMEN.get(kurz, kurz.upper() or "Sprache offen")


def regelstand(edition: str | None, versions_stand: str | None = None) -> str:
    """Die Regelversion mit ihrem Wort: 'Regeln 2024'. Eine nackte Jahreszahl neben
    einem Buchtitel liest sich wie ein Erscheinungsjahr.

    Ein `versions_stand` gehört an dieselbe Marke - er präzisiert genau diese Angabe
    ('Regeln 2024 · Errata Version 1.0'). An den Titel dürfte er nicht: der trägt nach
    dem Beschriftungs-Standard (importer/quellen.py) nur den Werktitel."""
    edition = str(edition or "").strip()
    stand = str(versions_stand or "").strip()
    marke = f"Regeln {edition}" if edition else "Regelversion offen"
    return f"{marke} · {stand}" if stand else marke


def gruppiere(quellen: list[dict]) -> dict[str, list[dict]]:
    """Die Quellen auf die drei Gruppen verteilen; Reihenfolge innerhalb einer Gruppe
    bleibt die der Eingabe. Immer alle drei Schlüssel - eine leere Gruppe lässt der
    Aufrufer weg, statt hier auf ein fehlendes Feld zu laufen."""
    gruppen: dict[str, list[dict]] = {REGELWERKE: [], REVISION: [], ABENTEUER: []}
    for q in quellen:
        art = (q.get("inhaltsart") or "").strip()
        for name, arten in _ARTEN.items():
            if art in arten:
                gruppen[name].append(q)
                break
        else:
            gruppen[REGELWERKE].append(q)
    return gruppen


def lies_quellen(con: sqlite3.Connection) -> list[dict]:
    """Quellen samt Eintragszahl aus einer BESTANDS-DB (Vollbestand), grösste zuerst.

    Nur Metadaten - kein `body_md`, kein `dateipfad`: dieselbe Grenze, die
    `app/charakterbogen/glossar_export.py` für die Web-DB zieht. Eine Übersicht sagt,
    WAS im Schrank steht, nicht was drinsteht.

    Leere Liste, wenn die Tabelle fehlt (uninitialisierte DB) - dann fällt die Übersicht
    weg, statt den Aufrufer mit einem SQL-Fehler zu beschäftigen."""
    con.row_factory = sqlite3.Row
    try:
        zeilen = con.execute(
            "SELECT q.titel, q.sprache, q.edition, q.inhaltsart, q.versions_stand, "
            "       count(e.id) AS eintraege "
            "FROM quellen q LEFT JOIN eintraege e ON e.quelle_id = q.id "
            "GROUP BY q.id ORDER BY eintraege DESC, q.titel").fetchall()
    except sqlite3.Error:
        return []
    return [dict(r) for r in zeilen]
