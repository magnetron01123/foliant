"""Der Reaktions-Kleber in bot.py: welche Reaktion zur Protokollzeile wird - und welche nicht.

`app/discord_bot/rueckmeldung.py` ist discord-frei und laengst getestet; `bot.py` ist der
Kleber und galt als "nur manuell abnehmbar". Fuer die PRUEFKETTE stimmt das nicht: Sie
besteht aus fuenf Entscheidungen, die alle mit Fakes pruefbar sind - und jede einzelne
kann eine Markierung verschlucken oder eine fremde Nachricht faelschlich aufnehmen.

Warum das zaehlt: Ein Meldeweg, der still nichts tut, ist schlimmer als einer, der fehlt.
Niemand merkt, dass die Meldung nicht ankam - der Spieler denkt, er habe gemeldet, und der
Suchbericht bleibt leer. Bis 04.08.2026 haette nur ein Griff in die echte Guild das gezeigt.

Was hier NICHT geprueft wird und Handarbeit bleibt: dass Discord die Ereignisse ueberhaupt
liefert (Intents, Gateway) und dass das Recht *Add Reactions* fuer die 📝-Bestaetigung
gesetzt ist. Das steht als Posten in BACKLOG M7.
"""
from __future__ import annotations

import asyncio
import types

import discord
import pytest

from app import protokoll
from app.discord_bot import rueckmeldung as rm
from app.discord_bot.bot import FoliantBot

BOT_ID = 999
GUILD = 111
KANAL = 222
NACHRICHT = 333


class FakeNachricht:
    def __init__(self, autor_id: int = BOT_ID, inhalt: str = "📖 Antwort"):
        self.id = NACHRICHT
        self.author = types.SimpleNamespace(id=autor_id, bot=autor_id == BOT_ID)
        self.content = inhalt
        self.thread = None
        self.reaktionen: list[str] = []

    async def add_reaction(self, emoji):
        self.reaktionen.append(emoji)


class FakeKanal:
    """Ein Kanal, der eine Nachricht und einen Vorlauf liefert. `parent_id=None` heisst:
    kein Thread - dann gilt die eigene ID fuer die Kanal-Allowlist."""

    def __init__(self, nachricht: FakeNachricht, vorlauf=(), parent_id=None):
        self.id = KANAL
        self.nachricht = nachricht
        self._vorlauf = list(vorlauf)
        if parent_id is not None:
            self.parent_id = parent_id

    async def fetch_message(self, mid):
        if mid != self.nachricht.id:
            raise discord.NotFound(types.SimpleNamespace(status=404, reason="NF"), "weg")
        return self.nachricht

    def history(self, *, limit, before):
        async def gen():
            for eintrag in reversed(self._vorlauf):     # history: neueste zuerst
                yield eintrag
        return gen()


def _payload(emoji: str, *, user_id: int = 42, guild_id: int = GUILD):
    return types.SimpleNamespace(emoji=emoji, user_id=user_id, guild_id=guild_id,
                                 channel_id=KANAL, message_id=NACHRICHT)


@pytest.fixture
def bot(monkeypatch, tmp_path):
    b = FoliantBot(guild_id=GUILD, kanal_ids=frozenset(), tagesdeckel=100,
                   api_key="x", modell="x", system="x")
    monkeypatch.setattr(type(b), "user",
                        property(lambda self: types.SimpleNamespace(id=BOT_ID)))
    monkeypatch.setattr(protokoll, "protokoll_pfad", lambda: tmp_path / "p.sqlite")
    monkeypatch.setattr(protokoll, "protokoll_aktiv", lambda: True)
    return b


def _haeng_kanal_ein(bot, monkeypatch, kanal):
    monkeypatch.setattr(type(bot), "get_channel", lambda self, kid: kanal, raising=False)


def _zeilen(tmp_path):
    import sqlite3
    con = sqlite3.connect(tmp_path / "p.sqlite")
    try:
        return [tuple(r) for r in con.execute("SELECT art, frage FROM rueckmeldungen")]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


# --- was aufgenommen wird -------------------------------------------------------------

@pytest.mark.parametrize("emoji, art", [
    ("\N{THUMBS DOWN SIGN}", rm.ART_RUNTER),
    ("\N{THUMBS UP SIGN}", rm.ART_HOCH),
    ("\N{THUMBS UP SIGN}\N{VARIATION SELECTOR-16}", rm.ART_HOCH),   # iOS
])
def test_beide_daumen_landen_unter_ihrer_art(bot, monkeypatch, tmp_path, emoji, art):
    """Die Art muss durch die ganze Kette bis in die Protokollzeile durchgereicht werden -
    vorher stand dort eine Konstante, und ein 👍 waere als Fehler kuriert worden."""
    nachricht = FakeNachricht()
    kanal = FakeKanal(nachricht, vorlauf=[types.SimpleNamespace(
        author=types.SimpleNamespace(bot=False), content="Wieviele Reaktionen hat man?")])
    _haeng_kanal_ein(bot, monkeypatch, kanal)

    asyncio.run(bot.on_raw_reaction_add(_payload(emoji)))

    assert _zeilen(tmp_path) == [(art, "Wieviele Reaktionen hat man?")]
    assert nachricht.reaktionen == [rm.BESTAETIGUNG], "ohne 📝 gilt der Knopf als kaputt"


def test_zuruecknehmen_trifft_nur_die_eigene_art(bot, monkeypatch, tmp_path):
    """Sind sich zwei Spieler uneins, stehen zwei Zeilen da. Nimmt einer zurueck, darf die
    andere Meinung nicht mit verschwinden."""
    nachricht = FakeNachricht()
    _haeng_kanal_ein(bot, monkeypatch, FakeKanal(nachricht))

    asyncio.run(bot.on_raw_reaction_add(_payload("\N{THUMBS DOWN SIGN}")))
    asyncio.run(bot.on_raw_reaction_add(_payload("\N{THUMBS UP SIGN}")))
    assert len(_zeilen(tmp_path)) == 2

    asyncio.run(bot.on_raw_reaction_remove(_payload("\N{THUMBS UP SIGN}")))
    assert [art for art, _frage in _zeilen(tmp_path)] == [rm.ART_RUNTER]


# --- was NICHT aufgenommen wird -------------------------------------------------------

@pytest.mark.parametrize("emoji", ["\N{FIRE}", "\N{MEMO}", "\N{PARTY POPPER}"])
def test_geplauder_wird_ignoriert(bot, monkeypatch, tmp_path, emoji):
    """Der Kanal ist voller Reaktionen. Zaehlte jede, waere die Kurationsliste Rauschen -
    und 📝 wuerde sich selbst protokollieren."""
    _haeng_kanal_ein(bot, monkeypatch, FakeKanal(FakeNachricht()))
    asyncio.run(bot.on_raw_reaction_add(_payload(emoji)))
    assert _zeilen(tmp_path) == []


def test_eigene_reaktion_des_bots_zaehlt_nie(bot, monkeypatch, tmp_path):
    """Heute setzt der Bot nur 📝, das ohnehin keine Markierung ist - die Harmlosigkeit
    haengt also an einer Zusage, die kein Test hielt und die der naechste Einzeiler
    kassiert. Seit 04.08.2026 haelt sie dieser Test."""
    _haeng_kanal_ein(bot, monkeypatch, FakeKanal(FakeNachricht()))
    asyncio.run(bot.on_raw_reaction_add(
        _payload("\N{THUMBS DOWN SIGN}", user_id=BOT_ID)))
    assert _zeilen(tmp_path) == []


def test_fremde_guild_wird_ignoriert(bot, monkeypatch, tmp_path):
    """Die Guild-Sperre ist die Zugangskontrolle des Bots (SPEC §12 Nr. 6) - sie gilt auch
    fuer den Meldeweg, sonst schreibt eine fremde Runde in unsere Kurationsliste."""
    _haeng_kanal_ein(bot, monkeypatch, FakeKanal(FakeNachricht()))
    asyncio.run(bot.on_raw_reaction_add(
        _payload("\N{THUMBS DOWN SIGN}", guild_id=GUILD + 1)))
    assert _zeilen(tmp_path) == []


def test_fremde_nachricht_ist_nicht_unsere_auskunft(bot, monkeypatch, tmp_path):
    """Ein 👎 auf den Beitrag eines Mitspielers ist Geplauder, keine Fehlermeldung ueber
    Foliant."""
    _haeng_kanal_ein(bot, monkeypatch, FakeKanal(FakeNachricht(autor_id=BOT_ID + 1)))
    asyncio.run(bot.on_raw_reaction_add(_payload("\N{THUMBS DOWN SIGN}")))
    assert _zeilen(tmp_path) == []


def test_gesperrter_kanal_wird_ignoriert(monkeypatch, tmp_path):
    """Kanal-Allowlist: Markierungen zaehlen nur dort, wo der Bot auch antworten darf."""
    b = FoliantBot(guild_id=GUILD, kanal_ids=frozenset({KANAL + 1}), tagesdeckel=100,
                   api_key="x", modell="x", system="x")
    monkeypatch.setattr(type(b), "user",
                        property(lambda self: types.SimpleNamespace(id=BOT_ID)))
    monkeypatch.setattr(protokoll, "protokoll_pfad", lambda: tmp_path / "p.sqlite")
    monkeypatch.setattr(protokoll, "protokoll_aktiv", lambda: True)
    _haeng_kanal_ein(b, monkeypatch, FakeKanal(FakeNachricht()))

    asyncio.run(b.on_raw_reaction_add(_payload("\N{THUMBS DOWN SIGN}")))
    assert _zeilen(tmp_path) == []


def test_im_thread_entscheidet_der_eltern_kanal(monkeypatch, tmp_path):
    """Threads reicht der Bot als Eltern-Kanal in die Allowlist - sonst waere jede
    Markierung im Thread verworfen, und genau dort laeuft das Gespraech."""
    b = FoliantBot(guild_id=GUILD, kanal_ids=frozenset({KANAL + 1}), tagesdeckel=100,
                   api_key="x", modell="x", system="x")
    monkeypatch.setattr(type(b), "user",
                        property(lambda self: types.SimpleNamespace(id=BOT_ID)))
    monkeypatch.setattr(protokoll, "protokoll_pfad", lambda: tmp_path / "p.sqlite")
    monkeypatch.setattr(protokoll, "protokoll_aktiv", lambda: True)
    _haeng_kanal_ein(b, monkeypatch,
                     FakeKanal(FakeNachricht(), parent_id=KANAL + 1))   # erlaubter Eltern

    asyncio.run(b.on_raw_reaction_add(_payload("\N{THUMBS DOWN SIGN}")))
    assert [art for art, _f in _zeilen(tmp_path)] == [rm.ART_RUNTER]


# --- Leitplanken ----------------------------------------------------------------------

def test_fehlende_bestaetigung_kostet_die_markierung_nicht(bot, monkeypatch, tmp_path):
    """Fehlt das Recht *Add Reactions*, wird die Markierung TROTZDEM notiert - deshalb
    steht der Schreibweg vor dem `add_reaction`. Sonst verloere man mit der Bestaetigung
    auch das Signal."""
    class StummeNachricht(FakeNachricht):
        async def add_reaction(self, emoji):
            raise discord.HTTPException(
                types.SimpleNamespace(status=403, reason="Forbidden"), "kein Recht")

    _haeng_kanal_ein(bot, monkeypatch, FakeKanal(StummeNachricht()))
    asyncio.run(bot.on_raw_reaction_add(_payload("\N{THUMBS DOWN SIGN}")))
    assert [art for art, _f in _zeilen(tmp_path)] == [rm.ART_RUNTER]


def test_geloeschte_nachricht_wirft_nicht(bot, monkeypatch, tmp_path):
    """Zwischen Reaktion und Nachladen kann die Nachricht weg sein. Ein Discord-Ereignis
    darf daran nie sterben - der Bot laeuft weiter, die Markierung entfaellt."""
    class LeererKanal(FakeKanal):
        async def fetch_message(self, mid):
            raise discord.NotFound(types.SimpleNamespace(status=404, reason="NF"), "weg")

    _haeng_kanal_ein(bot, monkeypatch, LeererKanal(FakeNachricht()))
    asyncio.run(bot.on_raw_reaction_add(_payload("\N{THUMBS DOWN SIGN}")))
    assert _zeilen(tmp_path) == []


def test_ohne_vorlauf_bleibt_die_markierung_gueltig(bot, monkeypatch, tmp_path):
    """Die Frage ist ein Komfortfeld - der Link im Protokoll fuehrt ohnehin zur Antwort.
    Eine Markierung zu verwerfen, weil das Feld leer bleibt, hiesse ein Signal wegzuwerfen."""
    _haeng_kanal_ein(bot, monkeypatch, FakeKanal(FakeNachricht(), vorlauf=[]))
    asyncio.run(bot.on_raw_reaction_add(_payload("\N{THUMBS DOWN SIGN}")))
    assert _zeilen(tmp_path) == [(rm.ART_RUNTER, None)]
