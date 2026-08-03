"""Die Bestandsübersicht als Discord-Nachricht (`/bestand`) - reine Textlogik, ohne
discord.py und damit vollständig testbar (wie `antwort.py`).

Gleiche Frage wie die Website-Karte „Was steckt drin?", gleiche Antwort: Gruppierung und
Beschriftung kommen aus `app/bestand.py`, hier steht nur die Darstellung. Wer die Liste
in Discord liest, soll dieselben Bücher in denselben Gruppen sehen wie auf der Seite -
sonst wäre die Übersicht keine Auskunft, sondern eine zweite Meinung.

Warum eine LISTE und keine Tabelle (Rückmeldung der Runde, 03.08.2026): Der erste Wurf
war eine Codeblock-Tabelle wie auf der Website. Discord bricht Codeblöcke auf dem Handy
aber bei rund 40 Zeichen hart um - aus vier Spalten wurde dort Zeilensalat, und gelesen
wird Discord vor allem am Handy. Fließtextzeilen brechen weich um: der Titel bleibt
ungekürzt, und die drei Angaben dahinter tragen ihre Bedeutung im Wort („Regeln 2024")
statt in der Spaltenposition - sie überleben damit jeden Umbruch.
"""
from __future__ import annotations

from app import bestand as _bestand

# Kein Bestand - fast immer ein laufender Import oder ein fehlender Mount. Ehrlich sagen
# statt eine leere Liste zeigen (B1: nichts gefunden heisst "nicht gefunden").
LEER = ("❌ Im Bestand steht gerade kein Buch - vermutlich läuft ein Import oder die "
        "Datenbank ist nicht eingebunden. Bitte David Bescheid geben.")

# Je Gruppe EIN Halbsatz direkt an der Überschrift: warum sie getrennt steht. Mehr Text
# stand hier schon - die Sätze der Website wirkten in Discord aufgesagt (Rückmeldung
# 03.08.2026); die ausführliche Fassung bleibt auf der Seite.
ERKLAERUNG = {
    _bestand.REGELWERKE: "die Grundlage jeder Auskunft",
    _bestand.REVISION: "offizielle Nachträge zum Grundtext",
    _bestand.ABENTEUER: "nur Regelwerte, keine Handlung (Spoiler-Schutz)",
}


def _zahl(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _eintraege(n: int) -> str:
    return f"{_zahl(n)} " + ("Eintrag" if n == 1 else "Einträge")


def zeile(q: dict) -> str:
    """Ein Buch als eine Listenzeile: Titel fett, dahinter Sprache, Regelstand und
    Umfang mit ·-Trennern. Dieselben vier Angaben wie eine Website-Zeile."""
    titel = " ".join(str(q.get("titel") or "?").split()) or "?"
    return (f"• **{titel}** — {_bestand.sprachname(q.get('sprache'))} · "
            f"{_bestand.regelstand(q.get('edition'), q.get('versions_stand'))} · "
            f"{_eintraege(q.get('eintraege') or 0)}")


def text(quellen: list[dict]) -> str:
    """Die ganze Antwort auf `/bestand`. Absatzgetrennt (\\n\\n) je Gruppe, damit
    `antwort.teile` an Gruppengrenzen schneidet, falls der Bestand über eine
    Discord-Nachricht hinauswächst."""
    if not quellen:
        return LEER
    gesamt = sum(q.get("eintraege") or 0 for q in quellen)
    buecher = f"{len(quellen)} " + ("Buch" if len(quellen) == 1 else "Bücher")
    # Dativ ("mit ... Einträgen"), nicht _eintraege(): die Zeilenform ist Nominativ.
    eintraege = f"{_zahl(gesamt)} " + ("Eintrag" if gesamt == 1 else "Einträgen")
    teile = [f"📚 **Was steckt im Bestand?**\n"
             f"**{buecher}** mit zusammen **{eintraege}** — "
             f"direkt aus der Datenbank, immer aktuell."]
    for name, gruppe in _bestand.gruppiere(quellen).items():
        if gruppe:
            zeilen = "\n".join(zeile(q) for q in gruppe)
            teile.append(f"**{name}** — {ERKLAERUNG[name]}\n{zeilen}")
    return "\n\n".join(teile)


def aus_datenbank() -> str:
    """Bestandsliste aus der Bestands-DB. BLOCKIEREND (SQLite) - der Bot ruft sie
    deshalb in einem Thread auf.

    Über `db.connect_readonly` wie jeder andere Lesepfad: mode=ro plus
    `PRAGMA query_only` (CONCEPT.md §13). Fehlt die Datei, ist das kein Fehlerfall,
    sondern derselbe leere Bestand wie eine leere Tabelle."""
    from app import db

    pfad = db.standard_pfad()
    if not pfad.exists():
        return LEER
    con = db.connect_readonly(str(pfad))
    try:
        return text(_bestand.lies_quellen(con))
    finally:
        con.close()
