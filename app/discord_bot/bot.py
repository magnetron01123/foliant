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
from app.discord_bot import antwort, rebuild
from app.discord_bot.gespraech import GespraechsSpeicher
from app.discord_bot.schranken import Schranken

_log = logging.getLogger("foliant.discord")

# Wie weit der Bot fuer einen Rebuild zurueckliest. Der GespraechsSpeicher haelt ohnehin
# nur die juengsten 12 Nachrichten - 40 Rohnachrichten decken das mit Reserve ab, weil
# eine Antwort aus mehreren Teilen bestehen kann.
_HISTORIE_LIMIT = 40


class FoliantBot(discord.Client):
    def __init__(self, *, guild_id: int, kanal_ids: frozenset[int],
                 tagesdeckel: int, api_key: str, modell: str, system: str,
                 cooldown_s: float = 10.0):
        intents = discord.Intents.default()
        intents.message_content = True      # Privileged Intent - im Dev-Portal aktivieren
        super().__init__(intents=intents,
                         # Der Zusatz-Prompt verbietet Mentions; hier die technische
                         # Leitplanke dahinter - egal was im Antworttext steht.
                         allowed_mentions=discord.AllowedMentions.none())
        self.baum = app_commands.CommandTree(self)
        self._guild = discord.Object(id=guild_id)
        self.schranken = Schranken(guild_id, kanal_ids, tagesdeckel, cooldown_s)
        self.gespraeche = GespraechsSpeicher()
        self._api_key, self._modell, self._system = api_key, modell, system
        # Semaphore(2): der Pi traegt auch MCP + Website, und die API kostet - mehr
        # als zwei gleichzeitige Schleifen bringt der Runde nichts.
        self._semaphor = asyncio.Semaphore(2)
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
        @app_commands.describe(frage="Deine Regelfrage (deutsch oder englisch)",
                               privat="Antwort nur fuer dich - dann ohne Thread "
                                      "fuer Nachfragen")
        async def regel(interaction: discord.Interaction, frage: str,
                        privat: bool = False) -> None:
            await self._slash_regel(interaction, frage, privat)

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

    async def _slash_regel(self, interaction: discord.Interaction, frage: str,
                           privat: bool = False) -> None:
        kanal = interaction.channel
        kanal_id = getattr(kanal, "parent_id", None) or interaction.channel_id
        if not self.schranken.richtiger_ort(interaction.guild_id, kanal_id):
            return                           # falscher Ort: still (kein Orakel)
        grund = self.schranken.ablehnungsgrund(interaction.user.id)
        if grund:
            await interaction.response.send_message(grund, ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=privat)
        text = await self._beantworte(interaction.user.id, frage, verlauf=[])
        teile = antwort.teile(text)
        if privat:
            # Ephemer: kein Thread, kein Verlauf - die Antwort existiert nur fuer den
            # Fragenden und ist fuer den Bot danach vorbei.
            for teil in teile:
                await interaction.followup.send(teil, ephemeral=True)
            await interaction.followup.send(antwort.HINWEIS_PRIVAT, ephemeral=True)
            return
        nachricht = await interaction.followup.send(teile[0], wait=True)
        thread = None
        if isinstance(kanal, discord.TextChannel):
            thread = await nachricht.create_thread(name=antwort.thread_titel(frage))
            for teil in teile[1:]:
                await thread.send(teil)
        else:                                # im Thread aufgerufen: nicht verschachteln
            for teil in teile[1:]:
                await interaction.followup.send(teil)
        ziel_id = thread.id if thread else kanal_id
        self.gespraeche.ergaenze(ziel_id, frage, text)

    async def on_message(self, nachricht: discord.Message) -> None:
        if nachricht.author.bot or not nachricht.guild:
            return
        kanal = nachricht.channel
        ist_thread = isinstance(kanal, discord.Thread)
        kanal_id = kanal.parent_id if ist_thread else kanal.id
        if not self.schranken.richtiger_ort(nachricht.guild.id, kanal_id):
            return
        erwaehnt = self.user in nachricht.mentions

        if (ist_thread and not self.gespraeche.kennt(kanal.id)
                and kanal.owner_id == (self.user and self.user.id)):
            # Eigener Thread ohne Verlauf (Pi-Neustart): aus der Discord-Historie
            # zurueckholen, statt das Gespraech aufzugeben.
            if not await self._stelle_verlauf_her(kanal):
                return                       # Hinweis ist raus, Frage kommt neu
        if ist_thread and self.gespraeche.kennt(kanal.id):
            await self._thread_folgefrage(nachricht)
        elif erwaehnt:
            await self._mention_frage(nachricht, ist_thread)

    async def _stelle_verlauf_her(self, thread: discord.Thread) -> bool:
        """Verlauf eines eigenen Threads aus der Discord-Historie rekonstruieren.
        True = es gibt wieder Kontext. False = nichts Verwertbares gefunden; dann ist
        der Vergessen-Hinweis raus und die Frage soll im Ganzen neu kommen.

        Der Thread gilt danach in JEDEM Fall als bekannt (auch mit leerem Verlauf) -
        sonst liefe der Hinweis bei jeder weiteren Nachricht erneut."""
        try:
            roh = await self._lies_historie(thread)
        except discord.HTTPException as fehler:
            # Nur die Ursache loggen, nie Inhalte (Datenschutz wie bei on_ready).
            _log.warning("Historie von Thread %s nicht lesbar: %s",
                         thread.id, type(fehler).__name__)
            roh = []
        # Der Titel ist die Ersatzfrage fuer /regel-Threads (dort steht die Frage
        # nirgends im Kanal) - aber nur, wenn der Anfang wirklich mitgelesen wurde.
        vollstaendig = len(roh) < _HISTORIE_LIMIT
        verlauf = rebuild.baue_verlauf(roh, thread.name if vollstaendig else None)
        self.gespraeche.setze(thread.id, verlauf)
        if verlauf:
            _log.info("Verlauf von Thread %s wiederhergestellt (%d Nachrichten)",
                      thread.id, len(verlauf))
            return True
        await thread.send(antwort.HINWEIS_VERGESSEN)
        return False

    async def _lies_historie(self, thread: discord.Thread) -> list[tuple[bool, str]]:
        """Die juengsten Thread-Nachrichten als (ist_bot, inhalt) in chronologischer
        Reihenfolge. Fremde Bots bleiben draussen - sie sind weder Frage noch Antwort."""
        eigene_id = self.user and self.user.id
        nachrichten = [n async for n in thread.history(limit=_HISTORIE_LIMIT)]
        nachrichten.reverse()                # history() liefert neueste zuerst
        roh = [(n.author.id == eigene_id, n.content) for n in nachrichten
               if not n.author.bot or n.author.id == eigene_id]
        starter = await self._starter_nachricht(thread)
        if starter is not None and len(nachrichten) < _HISTORIE_LIMIT:
            # Der Startbeitrag steht im ELTERN-Kanal, nicht in der Thread-Historie:
            # bei @Mention die Frage, bei /regel Teil 1 der Antwort. Nur anhaengen,
            # wenn nicht gekappt wurde - sonst klebte er an einer fremden Antwort.
            roh.insert(0, (starter.author.id == eigene_id, starter.content))
        return roh

    async def _starter_nachricht(self, thread: discord.Thread):
        eltern = thread.parent
        if eltern is None:
            return None
        if thread.starter_message is not None:
            return thread.starter_message
        try:
            return await eltern.fetch_message(thread.id)
        except discord.HTTPException:
            return None                      # geloescht oder nicht lesbar

    def _ohne_mentions(self, text: str) -> str:
        """Die eigene Erwaehnung aus dem Fragetext nehmen - sie ist Adressierung,
        nicht Inhalt, und stuende sonst als '<@123...>' in der Frage an das Modell."""
        eigene_id = self.user and self.user.id
        for mention in (f"<@{eigene_id}>", f"<@!{eigene_id}>"):
            text = text.replace(mention, "")
        return text.strip()

    async def _mention_frage(self, nachricht: discord.Message, ist_thread: bool) -> None:
        frage = self._ohne_mentions(nachricht.content)
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
        frage = self._ohne_mentions(nachricht.content)
        if not frage:
            return
        grund = self.schranken.ablehnungsgrund(nachricht.author.id)
        if grund:
            await nachricht.channel.send(grund)
            return
        verlauf = self.gespraeche.verlauf(nachricht.channel.id)
        async with nachricht.channel.typing():
            text = await self._beantworte(nachricht.author.id, frage, verlauf=verlauf)
        for teil in antwort.teile(text):
            await nachricht.channel.send(teil)
        self.gespraeche.ergaenze(nachricht.channel.id, frage, text)

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
