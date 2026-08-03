"""Rueckmeldungen der Runde: 👎 auf eine Bot-Antwort -> Kurations-Kandidat (O4/M5).

Zwei Ebenen, beide ohne Discord und ohne Netz:
- die discord-freie Entscheidungslogik (app/discord_bot/rueckmeldung.py)
- der Schreibweg im Abfrage-Protokoll (app/protokoll.py)

Der Kleber in bot.py bleibt wie der Rest dieser Datei manuell abgenommen (Modul-Docstring
dort) - was hier stattdessen abgesichert ist, sind die Zusagen, an denen er haengt.
"""
from __future__ import annotations

import sqlite3

import pytest

from app import protokoll
from app.discord_bot import rueckmeldung as rm


# --- welche Reaktion zaehlt ------------------------------------------------------------

def test_nur_der_daumen_zaehlt():
    assert rm.ist_markierung("\N{THUMBS DOWN SIGN}")
    for andere in ("\N{THUMBS UP SIGN}", "\N{FIRE}", "\N{MEMO}", "x", ""):
        assert not rm.ist_markierung(andere), andere


def test_variantenselektor_wird_toleriert():
    """Discord liefert dasselbe Emoji je Client mit oder ohne U+FE0F. Ein direkter
    Stringvergleich haette den Daumen von manchen Geraeten stillschweigend nicht
    erkannt - und stille Nichterkennung ist bei einem Meldeweg schlimmer als ein
    Fehlalarm: niemand merkt, dass die Meldung nicht ankam."""
    assert rm.ist_markierung("\N{THUMBS DOWN SIGN}\N{VARIATION SELECTOR-16}")


# --- welche Frage die markierte Antwort beantwortet hat --------------------------------

def test_letzte_menschliche_frage_gewinnt():
    """Bei einer Folgefrage im Thread ist die GESTELLTE Frage gemeint, nicht die
    urspruengliche - sonst kuratiert man am falschen Begriff."""
    vorlauf = [(False, "Was macht Feuerball?"), (True, "📖 …"),
               (False, "Und bei Deckung?"), (True, "📖 …")]
    assert rm.frage_aus_umgebung(vorlauf, "Was macht Feuerball") == "Und bei Deckung?"


def test_thread_titel_faengt_den_slash_fall():
    """Bei /regel steht die Frage nirgends im Kanal (Slash-Parameter) - der Thread-Titel
    ist die einzige Spur. Derselbe Grund wie fuer rebuild.baue_verlauf(ersatzfrage=...)."""
    assert rm.frage_aus_umgebung([(True, "📖 Antwortteil")],
                                 "Wie funktioniert Umklammern") \
        == "Wie funktioniert Umklammern"


def test_ohne_jede_spur_bleibt_die_markierung_gueltig():
    """None ist ein zulaessiges Ergebnis: Der Link im Protokoll fuehrt trotzdem zur
    Antwort. Die Markierung zu verwerfen, weil ein Komfortfeld leer bleibt, hiesse ein
    Signal wegzuwerfen - und Signale sind hier das knappe Gut."""
    assert rm.frage_aus_umgebung([], None) is None
    assert rm.frage_aus_umgebung([(True, "nur Bot")], "   ") is None


def test_leere_nachrichten_werden_uebersprungen():
    """Bild- und Anhangs-Nachrichten haben keinen Text - sie sind keine Frage."""
    vorlauf = [(False, "Echte Frage?"), (False, "   "), (False, "")]
    assert rm.frage_aus_umgebung(vorlauf) == "Echte Frage?"


def test_verweis_ist_ein_anklickbarer_discord_link():
    assert rm.verweis(1, 2, 3) == "https://discord.com/channels/1/2/3"


# --- der Schreibweg -------------------------------------------------------------------

@pytest.fixture
def protokoll_db(tmp_path, monkeypatch):
    pfad = tmp_path / "protokoll.sqlite"
    monkeypatch.setattr(protokoll, "protokoll_pfad", lambda: pfad)
    monkeypatch.setattr(protokoll, "protokoll_aktiv", lambda: True)
    return pfad


def _zeilen(pfad):
    con = sqlite3.connect(pfad)
    try:
        return [tuple(r) for r in con.execute(
            "SELECT art, frage, verweis FROM rueckmeldungen")]
    finally:
        con.close()


def test_markierung_wird_abgelegt(protokoll_db):
    protokoll.merke_rueckmeldung(rm.ART, "https://d/1/2/3", frage="Was macht Feuerball?")
    assert _zeilen(protokoll_db) == [(rm.ART, "Was macht Feuerball?", "https://d/1/2/3")]


def test_zweite_markierung_derselben_antwort_erzeugt_keine_zweite_zeile(protokoll_db):
    """UNIQUE(art, verweis) ist die PII-freie Entdopplung: Markiert ein zweiter Spieler
    dieselbe Antwort, ist das derselbe Befund. Die Alternative waere, Nutzer
    auseinanderzuhalten - genau das soll das Protokoll nicht (CONCEPT.md §13)."""
    protokoll.merke_rueckmeldung(rm.ART, "https://d/1/2/3", frage="Erste")
    protokoll.merke_rueckmeldung(rm.ART, "https://d/1/2/3", frage="Zweite")
    assert len(_zeilen(protokoll_db)) == 1


def test_zurueckgenommene_markierung_verschwindet(protokoll_db):
    """Ein Fehlgriff soll die Kurationsliste nicht dauerhaft belasten, und die Liste soll
    dem entsprechen, was in Discord steht."""
    protokoll.merke_rueckmeldung(rm.ART, "https://d/1/2/3", frage="Frage")
    protokoll.loesche_rueckmeldung(rm.ART, "https://d/1/2/3")
    assert _zeilen(protokoll_db) == []


def test_markierung_ohne_frage_ist_erlaubt(protokoll_db):
    protokoll.merke_rueckmeldung(rm.ART, "https://d/1/2/3", frage=None)
    assert _zeilen(protokoll_db) == [(rm.ART, None, "https://d/1/2/3")]


def test_kaputter_pfad_kostet_die_markierung_nie_den_bot(tmp_path, monkeypatch):
    """Dieselbe Leitplanke wie protokolliere(): Das Log ist Beiwerk, der laufende Bot
    nicht. Ein Schreibfehler darf nie in ein Discord-Ereignis durchschlagen."""
    monkeypatch.setattr(protokoll, "protokoll_pfad",
                        lambda: tmp_path / "gibt-es-nicht" / "p.sqlite")
    monkeypatch.setattr(protokoll, "protokoll_aktiv", lambda: True)
    protokoll.merke_rueckmeldung(rm.ART, "https://d/1/2/3", frage="X")   # darf nicht werfen
    protokoll.loesche_rueckmeldung(rm.ART, "https://d/1/2/3")


def test_die_abfragen_tabelle_bleibt_unberuehrt(protokoll_db):
    """Eigene Tabelle statt einer Spalte an `abfragen`: Die Markierung gilt einer ANTWORT
    (aus mehreren Tool-Aufrufen), nicht einer Abfrage - und `abfragen` rotiert bei 50 000
    Zeilen, waehrend eine Markierung zu selten und zu wertvoll ist, um mit dem
    Maschinenverkehr wegzulaufen."""
    protokoll.merke_rueckmeldung(rm.ART, "https://d/1/2/3", frage="X")
    con = sqlite3.connect(protokoll_db)
    try:
        assert con.execute("SELECT count(*) FROM abfragen").fetchone()[0] == 0
    finally:
        con.close()


# --- der Bericht ----------------------------------------------------------------------

def test_hilfe_erklaert_den_meldeweg():
    """Ein Meldeweg, den `/hilfe` nicht nennt, existiert fuer die Runde nicht."""
    from app.discord_bot import antwort
    assert "👎" in antwort.HILFE and "📝" in antwort.HILFE


def test_suchbericht_ueberlebt_ein_protokoll_ohne_die_tabelle(protokoll_db, capsys):
    """Bestands-Protokolle kennen `rueckmeldungen` nicht - sie entsteht mit der ersten
    Markierung. Ein fehlender Table darf den Bericht nicht kosten, dessen uebrige
    Abschnitte in Ordnung sind."""
    import argparse

    from app import admin
    protokoll.protokolliere("suche_bestand", suchbegriff="feuerball", anzahl_treffer=1)
    admin.cmd_suchbericht(argparse.Namespace(tage=30, limit=10, json=False))
    ausgabe = capsys.readouterr().out
    assert "Von der Runde markiert" in ausgabe
    assert "keine ✓" in ausgabe
