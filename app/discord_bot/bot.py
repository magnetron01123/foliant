"""FoliantBot - der duenne Discord-Kleber. Alles Fachliche (Splitting, Verlauf,
Schranken, LLM-Schleife) lebt in den discord-freien Nachbarmodulen bzw. app/llm.py;
diese Datei uebersetzt nur zwischen Discord-Ereignissen und diesen Bausteinen und
bleibt damit der einzige manuell abgenommene Teil.

Zugriffsmodell (SPEC §12): Die Tools laufen in-process (fastmcp.Client an
app.server.mcp, wie der Eval-Harness) - bewusst am ZugriffsFilter vorbei, der nur den
HTTP-Weg schuetzt. Der Bot hat KEINE eingehende HTTP-Flaeche; Zugangskontrolle ist die
Guild-Sperre plus die Schranken."""
from __future__ import annotations

import asyncio
import logging

import discord
import httpx
from discord import app_commands

from app import llm
from app.discord_bot import antwort
from app.discord_bot.gespraech import GespraechsSpeicher, verlaufsschluessel
from app.discord_bot.schranken import Schranken

_log = logging.getLogger("foliant.discord")


class FoliantBot(discord.Client):
    def __init__(self, *, guild_id: int, kanal_ids: frozenset[int],
                 tagesdeckel: int, api_key: str, modell: str, system: str):
        intents = discord.Intents.default()
        intents.message_content = True      # Privileged Intent - im Dev-Portal aktivieren
        super().__init__(intents=intents,
                         # Der Zusatz-Prompt verbietet Mentions; hier die technische
                         # Leitplanke dahinter - egal was im Antworttext steht.
                         allowed_mentions=discord.AllowedMentions.none())
        self.baum = app_commands.CommandTree(self)
        self._guild = discord.Object(id=guild_id)
        self.schranken = Schranken(guild_id, kanal_ids, tagesdeckel)
        self.gespraeche = GespraechsSpeicher()
        self._api_key, self._modell, self._system = api_key, modell, system
        # Semaphore(2): der Pi traegt auch MCP + Website, und die API kostet - mehr
        # als zwei gleichzeitige Schleifen bringt der Runde nichts.
        self._semaphor = asyncio.Semaphore(2)
        self._vergessen_gemeldet: set[int] = set()
        self._mcp = None
        self._http: httpx.AsyncClient | None = None
        self._werkzeuge: list[dict] = []

    # --- Aufbau -------------------------------------------------------------------

    async def setup_hook(self) -> None:
        from fastmcp import Client
        from app.server import mcp as foliant_mcp

        self._mcp = Client(foliant_mcp)
        await self._mcp.__aenter__()        # lebt so lange wie der Bot-Prozess
        self._werkzeuge = await llm.lade_werkzeuge(self._mcp)
        self._http = httpx.AsyncClient(timeout=180.0)

        @self.baum.command(name="regel", guild=self._guild,
                           description="Regelfrage an Foliant - die Antwort "
                                       "oeffnet einen Thread fuer Nachfragen")
        @app_commands.describe(frage="Deine Regelfrage (deutsch oder englisch)")
        async def regel(interaction: discord.Interaction, frage: str) -> None:
            await self._slash_regel(interaction, frage)

        # Guild-scoped Sync: sofort verfuegbar (globaler Sync braucht bis zu 1 h).
        await self.baum.sync(guild=self._guild)

    async def on_ready(self) -> None:
        _log.info("angemeldet als %s (Guilds: %d)", self.user, len(self.guilds))
        for guild in self.guilds:
            if guild.id != self._guild.id:
                # Server-Sperre (SPEC §12): der Bestand ist privat fuer die Runde -
                # fremde Guilds werden verlassen, nur die ID geloggt, nie Inhalte.
                _log.warning("verlasse fremde Guild %s", guild.id)
                await guild.leave()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        if guild.id != self._guild.id:
            _log.warning("verlasse fremde Guild %s (join)", guild.id)
            await guild.leave()

    # --- Ereignisse ---------------------------------------------------------------

    async def _slash_regel(self, interaction: discord.Interaction, frage: str) -> None:
        kanal = interaction.channel
        # ZWEI verschiedene IDs, die nicht verwechselt werden duerfen (Befund 31.07.2026):
        #   ort_id     - fuer die Kanal-Allowlist. In einem Thread ist das der ELTERN-Kanal,
        #                denn allowlistet ist der Kanal, nicht jeder Thread darin.
        #   verlauf_id - fuer den Gespraechsspeicher. Das ist der Ort, an dem die Antwort
        #                landet, also im Thread der THREAD.
        # Vorher trug eine einzige `kanal_id` beide Bedeutungen. Ein `/regel` IM Thread
        # legte den Verlauf deshalb unter der Eltern-ID ab, waehrend `on_message` die
        # Folgefrage unter `kanal.id` (der Thread-ID) suchte - und ihn nie fand. Der
        # Nutzer bekam stattdessen HINWEIS_VERGESSEN ("nach einem Neustart vergessen"),
        # also eine falsche Begruendung fuer ein Verhalten, das kein Neustart verursacht hat.
        ort_id = getattr(kanal, "parent_id", None) or interaction.channel_id
        if not self.schranken.richtiger_ort(interaction.guild_id, ort_id):
            return                           # falscher Ort: still (kein Orakel)
        grund = self.schranken.ablehnungsgrund(interaction.user.id)
        if grund:
            await interaction.response.send_message(grund, ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        text = await self._beantworte(interaction.user.id, frage, verlauf=[])
        teile = antwort.teile(text)
        nachricht = await interaction.followup.send(teile[0], wait=True)
        thread = None
        if isinstance(kanal, discord.TextChannel):
            thread = await nachricht.create_thread(name=antwort.thread_titel(frage))
            for teil in teile[1:]:
                await thread.send(teil)
        else:                                # im Thread aufgerufen: nicht verschachteln
            for teil in teile[1:]:
                await interaction.followup.send(teil)
        self.gespraeche.ergaenze(verlaufsschluessel(kanal, thread) or ort_id, frage, text)

    async def on_message(self, nachricht: discord.Message) -> None:
        if nachricht.author.bot or not nachricht.guild:
            return
        kanal = nachricht.channel
        ist_thread = isinstance(kanal, discord.Thread)
        ort_id = kanal.parent_id if ist_thread else kanal.id   # Allowlist: der KANAL
        if not self.schranken.richtiger_ort(nachricht.guild.id, ort_id):
            return
        erwaehnt = self.user in nachricht.mentions

        if ist_thread and self.gespraeche.kennt(kanal.id):
            await self._thread_folgefrage(nachricht)
        elif ist_thread and not erwaehnt and kanal.owner_id == (self.user and self.user.id):
            # Eigener Thread, aber kein Verlauf mehr (Pi-Neustart): einmal ehrlich sagen.
            if kanal.id not in self._vergessen_gemeldet:
                self._vergessen_gemeldet.add(kanal.id)
                await kanal.send(antwort.HINWEIS_VERGESSEN)
        elif erwaehnt:
            await self._mention_frage(nachricht, ist_thread)

    async def _mention_frage(self, nachricht: discord.Message, ist_thread: bool) -> None:
        frage = nachricht.content
        for mention in (f"<@{self.user.id}>", f"<@!{self.user.id}>"):
            frage = frage.replace(mention, "")
        frage = frage.strip()
        if not frage:
            return
        grund = self.schranken.ablehnungsgrund(nachricht.author.id)
        if grund:
            await nachricht.channel.send(grund)
            return
        async with nachricht.channel.typing():
            text = await self._beantworte(nachricht.author.id, frage, verlauf=[])
        teile = antwort.teile(text)
        if ist_thread:
            ziel = nachricht.channel
        else:
            # Thread auf der NUTZER-Nachricht: die Frage steht sichtbar ueber dem
            # Gespraech, der Kanal bleibt aufgeraeumt.
            ziel = await nachricht.create_thread(
                name=antwort.thread_titel(frage))
        for teil in teile:
            await ziel.send(teil)
        self.gespraeche.ergaenze(ziel.id, frage, text)

    async def _thread_folgefrage(self, nachricht: discord.Message) -> None:
        grund = self.schranken.ablehnungsgrund(nachricht.author.id)
        if grund:
            await nachricht.channel.send(grund)
            return
        verlauf = self.gespraeche.verlauf(nachricht.channel.id)
        async with nachricht.channel.typing():
            text = await self._beantworte(nachricht.author.id, nachricht.content,
                                          verlauf=verlauf)
        for teil in antwort.teile(text):
            await nachricht.channel.send(teil)
        self.gespraeche.ergaenze(nachricht.channel.id, nachricht.content, text)

    # --- Kern ---------------------------------------------------------------------

    async def _beantworte(self, nutzer_id: int, frage: str,
                          verlauf: list[dict]) -> str:
        """Eine Frage durch die geteilte Schleife fahren; liefert IMMER einen
        sendbaren deutschen Text (Fehler werden zu ehrlichen Meldungen, nie zu
        Stacktraces im Kanal)."""
        self.schranken.beginne(nutzer_id)
        try:
            async with self._semaphor:
                erg = await llm.fahre_schleife(
                    self._mcp, self._http, self._api_key, self._modell, self._system,
                    self._werkzeuge,
                    verlauf + [{"role": "user", "content": frage}],
                    system_cachen=True)
            fehler = antwort.fehlertext(erg.stop_grund)
            if fehler and erg.stop_grund != "max_tokens":
                return fehler
            if fehler:                       # max_tokens: Teiltext + Hinweis
                return f"{erg.text}\n\n{fehler}" if erg.text else fehler
            return erg.text or antwort.FEHLER_API
        except Exception:
            _log.exception("Schleife fehlgeschlagen (Nutzer %s)", nutzer_id)
            return antwort.FEHLER_API
        finally:
            self.schranken.beende(nutzer_id)
