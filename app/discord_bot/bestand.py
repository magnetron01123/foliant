"""Die Bestandsübersicht als Discord-Nachricht (`/bestand`) - reine Textlogik, ohne
discord.py und damit vollständig testbar (wie `antwort.py`).

Gleiche Frage wie die Website-Karte „Was steckt drin?", gleiche Antwort: Gruppierung und
Beschriftung kommen aus `app/bestand.py`, hier steht nur die Darstellung. Wer die Liste
in Discord liest, soll dieselben Bücher in denselben Gruppen sehen wie auf der Seite -
sonst wäre die Übersicht keine Auskunft, sondern eine zweite Meinung.

Warum eine Tabelle im Codeblock statt einer Aufzählung: Discord rendert Codeblöcke in
Festbreitenschrift, und nur dort stehen Sprache, Regelstand und Zahl untereinander in
einer Spalte. In Fließtext („Spielerhandbuch (Deutsch, Regeln 2024, 1.539 Einträge)")
verschiebt sich jede Angabe mit der Titellänge - genau die Unvergleichbarkeit, gegen die
der Beschriftungs-Standard (`importer/quellen.py`) angetreten ist. Markdown-Tabellen kann
Discord nicht.
"""
from __future__ import annotations

from app import bestand as _bestand

# Lange Titel kürzen: der Codeblock scrollt in Discord waagerecht, und ein einziges
# ausuferndes Buch schöbe die Zahlenspalte aller anderen Zeilen aus dem Bild. 34 Zeichen
# tragen die längsten echten Werktitel ("Forgotten Realms: Heroes of Faerûn").
TITEL_MAX = 34

KOPFZEILE = ("Buch", "Sprache", "Regelstand", "Einträge")

# Kein Bestand - fast immer ein laufender Import oder ein fehlender Mount. Ehrlich sagen
# statt eine leere Tabelle zeigen (B1: nichts gefunden heisst "nicht gefunden").
LEER = ("❌ Im Bestand steht gerade kein Buch - vermutlich läuft ein Import oder die "
        "Datenbank ist nicht eingebunden. Bitte David Bescheid geben.")

# Je Gruppe EIN Satz: warum sie getrennt steht. Das ist genau das, was die Runde über
# eine Auskunft wissen muss - die ausführliche Fassung steht auf der Website.
ERKLAERUNG = {
    _bestand.REGELWERKE:
        "Die Grundlage jeder Auskunft — Foliant antwortet *nur* hieraus.",
    _bestand.REVISION:
        "Kein eigener Regeltext, sondern die offiziellen Nachträge dazu. Foliant nennt "
        "sie immer zusammen mit dem Grundtext.",
    _bestand.ABENTEUER:
        "Daraus nennt Foliant nur *Regelwerte* — Handlung, Orte und Geheimnisse gibt es "
        "nicht, auch nicht auf Nachfrage.",
}


def _zahl(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _kuerze(text: str, grenze: int) -> str:
    sauber = " ".join(str(text or "?").split()) or "?"
    return sauber if len(sauber) <= grenze else sauber[:grenze - 1] + "…"


def _zeile(q: dict) -> tuple[str, str, str, str]:
    return (_kuerze(q.get("titel"), TITEL_MAX),
            _bestand.sprachname(q.get("sprache")),
            _bestand.regelstand(q.get("edition"), q.get("versions_stand")),
            _zahl(q.get("eintraege") or 0))


def tabelle(quellen: list[dict]) -> str:
    """Eine Gruppe als Codeblock-Tabelle. Spaltenbreiten JE Gruppe, nicht global: die
    Errata-Zeilen tragen zusätzlich ihren Errata-Stand, und ihre Breite soll nicht die
    Regelwerk-Tabelle auseinanderziehen, in der die Spalte leer bliebe."""
    zeilen = [KOPFZEILE] + [_zeile(q) for q in quellen]
    breiten = [max(len(z[i]) for z in zeilen) for i in range(len(KOPFZEILE))]
    gebaut = []
    for z in zeilen:
        # Zahlen rechtsbündig - nur so stehen Tausenderstellen untereinander und die
        # Grössenverhältnisse sind auf einen Blick lesbar (der Balken der Website).
        spalten = [t.ljust(b) for t, b in zip(z[:-1], breiten[:-1])]
        spalten.append(z[-1].rjust(breiten[-1]))
        gebaut.append("  ".join(spalten).rstrip())
    return "```\n" + "\n".join(gebaut) + "\n```"


def text(quellen: list[dict]) -> str:
    """Die ganze Antwort auf `/bestand`. Absatzgetrennt (\\n\\n), damit `antwort.teile`
    an sinnvollen Stellen schneidet, falls der Bestand über eine Discord-Nachricht
    hinauswächst - die Zaun-Behandlung dort hält die Codeblöcke dabei geschlossen."""
    if not quellen:
        return LEER
    gesamt = sum(q.get("eintraege") or 0 for q in quellen)
    teile = [f"📚 **Was steckt im Bestand?**\n"
             f"Foliant schlägt in **{len(quellen)} Büchern** mit zusammen "
             f"**{_zahl(gesamt)} Einträgen** nach. Diese Liste kommt direkt aus dem "
             f"Bestand — sie ist immer aktuell."]
    for name, gruppe in _bestand.gruppiere(quellen).items():
        if gruppe:
            teile.append(f"**{name}**\n{ERKLAERUNG[name]}\n{tabelle(gruppe)}")
    teile.append("Was hier fehlt, sagt Foliant ehrlich — es füllt nichts aus "
                 "Allgemeinwissen auf.")
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
