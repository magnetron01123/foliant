"""Thread-Eroeffnung: der Weg, an dem `/regel` im Kanal live gescheitert ist.

LIVE-BEFUND 03.08.2026 (Pi-Log, 02.08. 19:05): `/regel` riss mit
`ValueError: This message does not have guild info attached.` ab. Ursache: Die Antwort auf
einen Slash-Befehl kommt aus `interaction.followup.send(wait=True)` und ist damit eine
`WebhookMessage` - die traegt KEINE Guild-Referenz, und `Message.create_thread()` wirft
deshalb ValueError, noch bevor ein HTTP-Aufruf passiert. Das lief am
`except discord.HTTPException` vorbei.

Folge fuer den Spieler: Teil 1 der Antwort stand im Kanal, dann brach der Befehl ab - kein
Thread, keine Folgeteile, kein Gespraechskontext. Bei einem langen Statblock also eine
abgeschnittene Auskunft plus Discord-Fehlermeldung. Der @Mention-Weg war NICHT betroffen
(dort ist die Nachricht eine echte Message) - genau deshalb fiel es nicht sofort auf.

Getestet wird mit Fakes: `bot.py` ist der einzige manuell abgenommene Teil, aber DIESE
Entscheidung (Thread ueber den Kanal, nicht ueber die Nachricht) ist pruefbar - und ohne
Test waere sie beim naechsten Aufraeumen wieder weg.
"""
from __future__ import annotations

import asyncio
import types

import discord
import pytest

from app.discord_bot.bot import FoliantBot


class WebhookNachricht:
    """Was `interaction.followup.send(wait=True)` liefert: eine Nachricht MIT id, aber
    ohne Guild-Bezug. Ihr `create_thread` wirft genau wie das echte discord.py."""

    def __init__(self, mid: int = 4242):
        self.id = mid

    async def create_thread(self, **_):
        raise ValueError("This message does not have guild info attached.")


class FakeKanal:
    """TextChannel-Ersatz. `create_thread(message=...)` braucht nur einen Snowflake -
    das ist der Grund, warum der Weg ueber den Kanal funktioniert."""

    def __init__(self, fehler: Exception | None = None):
        self.fehler = fehler
        self.aufrufe: list[dict] = []

    async def create_thread(self, *, name, message=None, **_):
        self.aufrufe.append({"name": name, "message_id": getattr(message, "id", None)})
        if self.fehler:
            raise self.fehler
        return types.SimpleNamespace(id=777, name=name)


@pytest.fixture
def bot():
    return FoliantBot(guild_id=111, kanal_ids=frozenset(), tagesdeckel=100,
                      api_key="x", modell="x", system="x")


def test_thread_entsteht_auch_fuer_eine_webhook_antwort(bot):
    """DER Regressionstest. Ohne den Fix ruft `_eroeffne_thread` die Nachricht selbst und
    fliegt mit ValueError raus; mit dem Fix geht es ueber den Kanal und der Thread steht."""
    kanal, nachricht = FakeKanal(), WebhookNachricht()

    thread = asyncio.run(
        bot._eroeffne_thread(kanal, nachricht, "Was macht Verwandlung?"))

    assert thread is not None, "kein Thread - die Folgefragen-Funktion waere weg"
    assert kanal.aufrufe == [{"name": kanal.aufrufe[0]["name"], "message_id": 4242}]
    assert kanal.aufrufe[0]["name"], "der Thread braucht einen Titel (die Frage)"


def test_verweigerter_thread_kostet_nur_den_komfort_nicht_die_antwort(bot):
    """Fehlendes Recht oder eine Nachricht, die schon einen Thread traegt: dann None,
    damit der Aufrufer in den Kanal zurueckfaellt. Die Antwort ist bezahlt und darf nicht
    an einer Komfortfunktion sterben."""
    kanal = FakeKanal(fehler=discord.HTTPException(
        types.SimpleNamespace(status=403, reason="Forbidden"), "keine Rechte"))

    assert asyncio.run(
        bot._eroeffne_thread(kanal, WebhookNachricht(), "Frage")) is None


def test_auch_ein_valueerror_wird_gefangen(bot):
    """Guertel und Hosentraeger: Sollte discord.py kuenftig an anderer Stelle einen
    ValueError werfen, kostet das wieder nur den Thread - nicht den Befehl. Genau diese
    Zusage fehlte und wurde am 02.08.2026 in der echten Guild eingeloest."""
    kanal = FakeKanal(fehler=ValueError("irgendwas fehlt"))

    assert asyncio.run(
        bot._eroeffne_thread(kanal, WebhookNachricht(), "Frage")) is None


def test_die_nachricht_wird_nie_selbst_gefragt(bot):
    """Die eigentliche Zusage des Fixes: `Message.create_thread` wird NICHT mehr benutzt.
    Waere es so, schluege dieser Test mit demselben ValueError fehl wie die echte Guild -
    das ist der Unterschied zwischen 'gefangen' und 'behoben'."""
    class LauteNachricht(WebhookNachricht):
        async def create_thread(self, **_):
            raise AssertionError("Message.create_thread darf nicht mehr gerufen werden")

    kanal = FakeKanal()
    assert asyncio.run(
        bot._eroeffne_thread(kanal, LauteNachricht(), "Frage")) is not None
