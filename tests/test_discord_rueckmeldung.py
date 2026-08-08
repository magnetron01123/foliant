"""Rueckmeldungen der Runde: 👎/👍 auf eine Bot-Antwort -> Kandidat fuer Kuration bzw.
Regressionsschutz (O4/M5).

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

def test_beide_daumen_zaehlen_getrennt():
    """Bis 04.08.2026 pruefte dieser Test das Gegenteil - dass 👍 NICHT zaehlt. Der
    Meinungswechsel ist begruendet (rueckmeldung.ARTEN): Der urspruengliche Einwand galt
    NUANCE-Emoji, die man erklaeren muss; 👍/👎 ist Polaritaet und braucht keine
    Erklaerung. Was von diesem Test bleibt und wichtiger ist als die Erweiterung: fremde
    Reaktionen duerfen NICHT zaehlen - der Kanal ist voller Geplauder."""
    assert rm.art_der_markierung("\N{THUMBS DOWN SIGN}") == rm.ART_RUNTER
    assert rm.art_der_markierung("\N{THUMBS UP SIGN}") == rm.ART_HOCH
    for andere in ("\N{FIRE}", "\N{MEMO}", "\N{PARTY POPPER}", "x", ""):
        assert rm.art_der_markierung(andere) is None, andere


@pytest.mark.parametrize("emoji, art", [("\N{THUMBS DOWN SIGN}", rm.ART_RUNTER),
                                        ("\N{THUMBS UP SIGN}", rm.ART_HOCH)])
def test_variantenselektor_wird_toleriert(emoji, art):
    """Discord liefert dasselbe Emoji je Client mit oder ohne U+FE0F. Ein direkter
    Stringvergleich haette den Daumen von manchen Geraeten stillschweigend nicht
    erkannt - und stille Nichterkennung ist bei einem Meldeweg schlimmer als ein
    Fehlalarm: niemand merkt, dass die Meldung nicht ankam. Bei 👍 wiegt das schwerer:
    iOS schickt ihn praktisch immer mit Variantenselektor."""
    assert rm.art_der_markierung(emoji + "\N{VARIATION SELECTOR-16}") == art


# --- welche Frage die markierte Antwort beantwortet hat --------------------------------

def test_letzte_menschliche_frage_gewinnt():
    """Bei einer Folgefrage im Thread ist die GESTELLTE Frage gemeint, nicht die
    urspruengliche - sonst kuratiert man am falschen Begriff."""
    vorlauf = [(False, "Was macht Feuerball?"), (True, "📖 …"),
               (False, "Und bei Deckung?"), (True, "📖 …")]
    assert rm.frage_aus_umgebung(vorlauf, "Was macht Feuerball") == "Und bei Deckung?"


def test_thread_titel_faengt_den_slash_fall():
    """Bei /regel steht die Frage nirgends im Kanal (Slash-Parameter) - der Thread-Titel
    ist die einzige Spur. Derselbe Grund wie fuer wiederaufbau.baue_verlauf(ersatzfrage=...)."""
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
    protokoll.merke_rueckmeldung(rm.ART_RUNTER, "https://d/1/2/3",
                                 frage="Was macht Feuerball?")
    assert _zeilen(protokoll_db) == [
        (rm.ART_RUNTER, "Was macht Feuerball?", "https://d/1/2/3")]


def test_zweite_markierung_derselben_antwort_erzeugt_keine_zweite_zeile(protokoll_db):
    """UNIQUE(art, verweis) ist die PII-freie Entdopplung: Markiert ein zweiter Spieler
    dieselbe Antwort, ist das derselbe Befund. Die Alternative waere, Nutzer
    auseinanderzuhalten - genau das soll das Protokoll nicht (CONCEPT.md §13)."""
    protokoll.merke_rueckmeldung(rm.ART_RUNTER, "https://d/1/2/3", frage="Erste")
    protokoll.merke_rueckmeldung(rm.ART_RUNTER, "https://d/1/2/3", frage="Zweite")
    assert len(_zeilen(protokoll_db)) == 1


def test_zurueckgenommene_markierung_verschwindet(protokoll_db):
    """Ein Fehlgriff soll die Kurationsliste nicht dauerhaft belasten, und die Liste soll
    dem entsprechen, was in Discord steht."""
    protokoll.merke_rueckmeldung(rm.ART_RUNTER, "https://d/1/2/3", frage="Frage")
    protokoll.loesche_rueckmeldung(rm.ART_RUNTER, "https://d/1/2/3")
    assert _zeilen(protokoll_db) == []


def test_beide_arten_stehen_nebeneinander(protokoll_db):
    """UNIQUE(art, verweis) entdoppelt JE ART. Sind sich zwei Spieler uneins, ist das
    kein Konflikt, den der Code aufloesen darf, sondern zwei Befunde - und eine
    zurueckgenommene Reaktion loescht nur die eigene Zeile. Das ist die Zusage, fuer die
    `art` als FELD gebaut wurde (statt einer Tabelle je Art)."""
    protokoll.merke_rueckmeldung(rm.ART_RUNTER, "https://d/1/2/3", frage="Strittig?")
    protokoll.merke_rueckmeldung(rm.ART_HOCH, "https://d/1/2/3", frage="Strittig?")
    assert len(_zeilen(protokoll_db)) == 2

    protokoll.loesche_rueckmeldung(rm.ART_HOCH, "https://d/1/2/3")
    assert _zeilen(protokoll_db) == [
        (rm.ART_RUNTER, "Strittig?", "https://d/1/2/3")]


def test_markierung_ohne_frage_ist_erlaubt(protokoll_db):
    protokoll.merke_rueckmeldung(rm.ART_RUNTER, "https://d/1/2/3", frage=None)
    assert _zeilen(protokoll_db) == [(rm.ART_RUNTER, None, "https://d/1/2/3")]


def test_kaputter_pfad_kostet_die_markierung_nie_den_bot(tmp_path, monkeypatch):
    """Dieselbe Leitplanke wie protokolliere(): Das Log ist Beiwerk, der laufende Bot
    nicht. Ein Schreibfehler darf nie in ein Discord-Ereignis durchschlagen."""
    monkeypatch.setattr(protokoll, "protokoll_pfad",
                        lambda: tmp_path / "gibt-es-nicht" / "p.sqlite")
    monkeypatch.setattr(protokoll, "protokoll_aktiv", lambda: True)
    protokoll.merke_rueckmeldung(rm.ART_RUNTER, "https://d/1/2/3", frage="X")  # wirft nie
    protokoll.loesche_rueckmeldung(rm.ART_RUNTER, "https://d/1/2/3")


def test_die_abfragen_tabelle_bleibt_unberuehrt(protokoll_db):
    """Eigene Tabelle statt einer Spalte an `abfragen`: Die Markierung gilt einer ANTWORT
    (aus mehreren Tool-Aufrufen), nicht einer Abfrage - und `abfragen` rotiert bei 50 000
    Zeilen, waehrend eine Markierung zu selten und zu wertvoll ist, um mit dem
    Maschinenverkehr wegzulaufen."""
    protokoll.merke_rueckmeldung(rm.ART_RUNTER, "https://d/1/2/3", frage="X")
    con = sqlite3.connect(protokoll_db)
    try:
        assert con.execute("SELECT count(*) FROM abfragen").fetchone()[0] == 0
    finally:
        con.close()


# --- der Bericht ----------------------------------------------------------------------

def test_hilfe_erklaert_beide_meldewege():
    """Ein Meldeweg, den `/hilfe` nicht nennt, existiert fuer die Runde nicht."""
    from app.discord_bot import antwort
    assert "👎" in antwort.HILFE and "👍" in antwort.HILFE and "📝" in antwort.HILFE


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
    assert "Von der Runde gelobt" in ausgabe
    assert "keine ✓" in ausgabe


def test_lob_steht_nicht_unter_der_fehler_ueberschrift(protokoll_db, capsys):
    """Die ART traegt die Ueberschrift, nicht die Zeile. Ginge der Bot vor dieser
    Aenderung live, stuende Lob unter 'markiert' - und der naechste Durchgang kuratierte
    eine gelungene Antwort als Fehler."""
    import argparse

    from app import admin
    protokoll.merke_rueckmeldung(rm.ART_HOCH, "https://d/1/2/3", frage="Gelungene Frage")
    admin.cmd_suchbericht(argparse.Namespace(tage=30, limit=10, json=False))
    ausgabe = capsys.readouterr().out
    fehler, lob = ausgabe.split("Von der Runde gelobt", 1)
    assert "Gelungene Frage" in lob and "Gelungene Frage" not in fehler


def test_json_trennt_die_beiden_arten(protokoll_db, capsys):
    """Der Auswertungs-Durchgang liest JSON. `markiert` behaelt seine Bedeutung
    (nur 👎) - sonst zaehlte ein spaeterer Leser Lob als Fehlerbefund mit."""
    import argparse
    import json

    from app import admin
    protokoll.merke_rueckmeldung(rm.ART_RUNTER, "https://d/1/2/3", frage="Falsch")
    protokoll.merke_rueckmeldung(rm.ART_HOCH, "https://d/1/2/4", frage="Gut")
    admin.cmd_suchbericht(argparse.Namespace(tage=30, limit=10, json=True))
    bericht = json.loads(capsys.readouterr().out)
    assert [z["frage"] for z in bericht["markiert"]] == ["Falsch"]
    assert [z["frage"] for z in bericht["gelobt"]] == ["Gut"]


# --- Selbstanzeige: Ablehnung ohne Werkzeugaufruf (Befund 08.08.2026) -----------------

def test_ablehnung_ohne_werkzeug_wird_erkannt():
    """Auf das nackte Wort 'verstecken' kam eine 🚫-Spoiler-Ablehnung OHNE einen einzigen
    Werkzeugaufruf - regelwidrig (nie 🚫/❌ ohne Nachschlag) und die einzige
    Fehlerklasse, die das Abfrage-Protokoll strukturell nicht sieht: protokolliere()
    haengt an den Werkzeugen, und genau die liefen nie."""
    assert rm.ablehnung_ohne_werkzeug("🚫 **Spoiler-Ablehnung** …", [])
    assert rm.ablehnung_ohne_werkzeug("❌ Dazu finde ich nichts …", [])
    # Mit Werkzeugaufruf ist eine Ablehnung legitim (echter Leerbefund/Spoiler):
    assert not rm.ablehnung_ohne_werkzeug("🚫 …", ["foliant_suche_bestand"])
    assert not rm.ablehnung_ohne_werkzeug("❌ …", ["foliant_suche_bestand"])
    # Und eine normale Antwort ohne Werkzeuge (Rueckfrage ❓) ist kein Befund:
    assert not rm.ablehnung_ohne_werkzeug("❓ Welchen meinst du?", [])


def test_auto_verweis_ist_idempotent_je_frage():
    """Derselbe Fehlalarm auf dieselbe Frage ist DERSELBE Befund - wie bei den Daumen.
    Whitespace/Case duerfen keine Duplikate erzeugen."""
    assert rm.auto_verweis("  Verstecken \n bitte ") == rm.auto_verweis("verstecken bitte")
    assert rm.auto_verweis("x" * 500) == rm.auto_verweis("x" * 500)
    assert len(rm.auto_verweis("x" * 500)) <= 130


def test_selbstanzeige_erscheint_im_suchbericht(protokoll_db, capsys):
    """Der Bericht ist der Ort, an dem der Befund jemanden erreicht - eine Selbstanzeige,
    die nur in der Tabelle liegt, waere genauso unsichtbar wie vorher."""
    import argparse
    import json as _json

    from app import admin
    protokoll.merke_rueckmeldung(rm.ART_AUTO_ABLEHNUNG,
                                 rm.auto_verweis("verstecken"), frage="verstecken")
    admin.cmd_suchbericht(argparse.Namespace(tage=30, limit=10, json=False))
    ausgabe = capsys.readouterr().out
    assert "Selbstanzeige des Bots" in ausgabe
    assert "verstecken" in ausgabe
    # Und maschinenlesbar fuer den zeitgesteuerten Durchgang:
    admin.cmd_suchbericht(argparse.Namespace(tage=30, limit=10, json=True))
    daten = _json.loads(capsys.readouterr().out)
    assert daten["auto_ablehnungen"][0]["frage"] == "verstecken"


def test_der_bot_meldet_die_ablehnung_selbst(protokoll_db, monkeypatch):
    """Der Kleber in bot.py: Nach der Schleife wird die Selbstanzeige geschrieben - ohne
    dass die Antwort sich aendert. Vorher waere genau dieser Fall (🚫 ohne Werkzeuge)
    spurlos geblieben; gefunden hat ihn nur die Meldung eines Spielers."""
    import asyncio
    import types

    from app import llm
    from app.discord_bot.bot import FoliantBot

    bot = FoliantBot(guild_id=1, kanal_ids=frozenset(), tagesdeckel=100,
                     api_key="x", modell="x", system="x")

    async def fake_schleife(*_a, **_k):
        return llm.SchleifenErgebnis("🚫 **Spoiler-Ablehnung** …", [], [], "end_turn")

    gemeldet: list[tuple] = []
    monkeypatch.setattr(llm, "fahre_schleife", fake_schleife)
    monkeypatch.setattr(protokoll, "merke_rueckmeldung",
                        lambda art, verweis, frage=None, kanal="discord":
                        gemeldet.append((art, verweis, frage)))

    text = asyncio.run(bot._beantworte(42, "verstecken", []))

    assert text.startswith("🚫")                        # die Antwort selbst bleibt
    assert gemeldet == [(rm.ART_AUTO_ABLEHNUNG, rm.auto_verweis("verstecken"),
                         "verstecken")]
