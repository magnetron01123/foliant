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

from app import llm, protokoll
from app.discord_bot import antwort, rebuild, rueckmeldung
from app.discord_bot.gespraech import GespraechsSpeicher, verlaufsschluessel
from app.discord_bot.schranken import Schranken

_log = logging.getLogger("foliant.discord")

# Wie weit der Bot fuer einen Rebuild zurueckliest. Der GespraechsSpeicher haelt ohnehin
# nur die juengsten 12 Nachrichten - 40 Rohnachrichten decken das mit Reserve ab, weil
# eine Antwort aus mehreren Teilen bestehen kann.
_HISTORIE_LIMIT = 40


def _mit_fassung(frage: str, fassung: app_commands.Choice[str] | None) -> str:
    """Die gewaehlte Regelfassung als Klartext-Zusatz an der Frage. Auch die explizite
    Wahl von 2024 wird angehaengt: sie ist eine Aussage des Fragenden und soll gewinnen,
    falls die Frage selbst nach altem Material klingt."""
    if fassung is None:
        return frage
    return f"{frage} (Regelfassung {fassung.value})"


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

        # Die fassung-Wahl ist bewusst nur ein Textzusatz an der Frage (_mit_fassung):
        # die Regelversion steuert das Modell ueber die edition-Filter der Tools, einen
        # eigenen API-Kanal dafuer gibt es nicht - und Standard bleibt 2024 (SPEC §7).
        fassungen = [app_commands.Choice(name="2024 (Standard)", value="2024"),
                     app_commands.Choice(name="2014", value="2014")]

        @self.baum.command(name="regel", guild=self._guild,
                           description="Regelfrage an Foliant - die Antwort "
                                       "oeffnet einen Thread fuer Nachfragen")
        @app_commands.describe(frage="Deine Regelfrage (deutsch oder englisch)",
                               fassung="Regelfassung, falls nicht 2024 gemeint ist")
        @app_commands.choices(fassung=fassungen)
        async def regel(interaction: discord.Interaction, frage: str,
                        fassung: app_commands.Choice[str] | None = None) -> None:
            await self._slash_regel(interaction, _mit_fassung(frage, fassung),
                                    privat=False)

        # Eigener Befehl statt eines Schalters an /regel: den Schalter gab es, aber man
        # musste ihn KENNEN - er stand erst nach dem Aufklappen der Optionen da, und wer
        # ihn nicht kannte, fragte im Zweifel im Kanal. Der gemeinsame Wortstamm ist der
        # Grund fuer genau diesen Namen: Discord zeigt bei der Eingabe von "/regel" beide
        # Befehle untereinander, samt Beschreibung - die Wahl steht damit VOR dem Tippen
        # der Frage, nicht in einem Untermenue dahinter.
        @self.baum.command(name="regel-privat", guild=self._guild,
                           description="Regelfrage, deren Antwort nur du siehst - "
                                       "dafuer ohne Thread fuer Nachfragen")
        @app_commands.describe(frage="Deine Regelfrage (deutsch oder englisch)",
                               fassung="Regelfassung, falls nicht 2024 gemeint ist")
        @app_commands.choices(fassung=fassungen)
        async def regel_privat(interaction: discord.Interaction, frage: str,
                               fassung: app_commands.Choice[str] | None = None) -> None:
            await self._slash_regel(interaction, _mit_fassung(frage, fassung),
                                    privat=True)

        @self.baum.command(name="hilfe", guild=self._guild,
                           description="Kurzanleitung: alle Wege, Foliant zu fragen")
        async def hilfe(interaction: discord.Interaction) -> None:
            ort_id = (getattr(interaction.channel, "parent_id", None)
                      or interaction.channel_id)
            if not self.schranken.richtiger_ort(interaction.guild_id, ort_id):
                return                       # falscher Ort: still (kein Orakel)
            await interaction.response.send_message(antwort.HILFE, ephemeral=True)

        # Kontextmenue (Rechtsklick auf eine Nachricht -> Apps): prueft eine fremde
        # Aussage als Regelfrage, ohne sie abzutippen - der Spieltisch-Fall "stimmt
        # das ueberhaupt?". Laeuft denselben Weg wie /regel; der Thread-Titel traegt
        # die geprueften Worte.
        async def kontext_frage(interaction: discord.Interaction,
                                ziel: discord.Message) -> None:
            ort_id = (getattr(interaction.channel, "parent_id", None)
                      or interaction.channel_id)
            if not self.schranken.richtiger_ort(interaction.guild_id, ort_id):
                return
            if ziel.author.bot:
                await interaction.response.send_message(antwort.HINWEIS_BOT_NACHRICHT,
                                                        ephemeral=True)
                return
            frage = self._ohne_mentions(ziel.content)
            if not frage:                    # nur Bild/Anhang/Embed
                await interaction.response.send_message(antwort.HINWEIS_KEIN_TEXT,
                                                        ephemeral=True)
                return
            await self._slash_regel(interaction, frage, privat=False)

        self.baum.add_command(app_commands.ContextMenu(name="Foliant fragen",
                                                       callback=kontext_frage),
                              guild=self._guild)

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
        # ZWEI verschiedene IDs, die nicht verwechselt werden duerfen (Befund 31.07.2026):
        #   ort_id     - fuer die Kanal-Allowlist. In einem Thread ist das der ELTERN-Kanal,
        #                denn allowlistet ist der Kanal, nicht jeder Thread darin.
        #   verlauf_id - fuer den Gespraechsspeicher. Das ist der Ort, an dem die Antwort
        #                landet, also im Thread der THREAD.
        # Vorher trug eine einzige `kanal_id` beide Bedeutungen. Ein `/regel` IM Thread
        # legte den Verlauf deshalb unter der Eltern-ID ab, waehrend `on_message` die
        # Folgefrage unter `kanal.id` (der Thread-ID) suchte - und ihn nie fand. Seit der
        # Verlaufs-Rekonstruktion (PR #77) faellt das nicht mehr als Vergessen-Hinweis auf:
        # der Bot liest den Thread stattdessen JEDES MAL aus der Discord-Historie zurueck,
        # obwohl der Verlauf im Speicher steht. Der falsche Schluessel bleibt derselbe.
        ort_id = getattr(kanal, "parent_id", None) or interaction.channel_id
        if not self.schranken.richtiger_ort(interaction.guild_id, ort_id):
            return                           # falscher Ort: still (kein Orakel)
        grund = self.schranken.beginne(interaction.user.id)
        if grund:
            await interaction.response.send_message(grund, ephemeral=True)
            return
        try:
            await interaction.response.defer(thinking=True, ephemeral=privat)
            text = await self._beantworte(interaction.user.id, frage, verlauf=[])
            teile = antwort.teile(text)
            if privat:
                # Ephemer: kein Thread, kein Verlauf - die Antwort existiert nur fuer
                # den Fragenden und ist fuer den Bot danach vorbei.
                for teil in teile:
                    await interaction.followup.send(teil, ephemeral=True)
                await interaction.followup.send(antwort.HINWEIS_PRIVAT, ephemeral=True)
                return
            nachricht = await interaction.followup.send(teile[0], wait=True)
            thread = None
            if isinstance(kanal, discord.TextChannel):
                thread = await self._eroeffne_thread(kanal, nachricht, frage)
            if thread is not None:
                for teil in teile[1:]:
                    await thread.send(teil)
            else:                            # im Thread aufgerufen (nicht verschachteln)
                for teil in teile[1:]:       # oder Thread verweigert (Fallback: Kanal)
                    await interaction.followup.send(teil)
            if thread is not None or not isinstance(kanal, discord.TextChannel):
                # Ohne Thread gibt es keinen Ort fuer Folgefragen - ein Verlauf unter
                # der Kanal-ID wuerde nie gelesen und nur 24 h Speicher belegen.
                self.gespraeche.ergaenze(
                    verlaufsschluessel(kanal, thread) or ort_id, frage, text)
        finally:
            self.schranken.beende(interaction.user.id)

    async def _eroeffne_thread(self, kanal, nachricht,
                               frage: str) -> discord.Thread | None:
        """Thread zur Nachricht; None statt Ausnahme, wenn Discord ihn verweigert
        (fehlendes Thread-Recht, Nachricht traegt schon einen). Die bezahlte Antwort
        steht dann bereits im Kanal und darf nicht an der Komfortfunktion scheitern.

        Ueber den KANAL, nicht ueber die Nachricht (Live-Befund 03.08.2026): Die Antwort auf
        einen Slash-Befehl kommt aus `interaction.followup.send(wait=True)` und ist damit
        eine `WebhookMessage` - die traegt KEINE Guild-Referenz, und
        `Message.create_thread()` wirft deshalb `ValueError`, noch bevor ein HTTP-Aufruf
        passiert. Das lief am `except discord.HTTPException` vorbei und riss `/regel` im
        Kanal mit: Teil 1 der Antwort stand da, dann brach der Befehl ab - kein Thread,
        keine Folgeteile, kein Gespraechskontext. `TextChannel.create_thread(message=...)`
        nimmt jeden Snowflake, also genuegt die ID; damit ist der Weg fuer Slash-Antwort und
        @Mention derselbe. `ValueError` wird zusaetzlich gefangen, damit ein kuenftiger Fall
        dieser Art wieder nur die Komfortfunktion kostet, nie die Antwort."""
        try:
            return await kanal.create_thread(name=antwort.thread_titel(frage),
                                             message=nachricht)
        except (discord.HTTPException, ValueError) as fehler:
            _log.warning("Thread zu Nachricht %s nicht erstellbar: %s",
                         getattr(nachricht, "id", "?"), type(fehler).__name__)
            return None

    async def on_message(self, nachricht: discord.Message) -> None:
        if nachricht.author.bot or not nachricht.guild:
            return
        kanal = nachricht.channel
        ist_thread = isinstance(kanal, discord.Thread)
        ort_id = kanal.parent_id if ist_thread else kanal.id   # Allowlist: der KANAL
        if not self.schranken.richtiger_ort(nachricht.guild.id, ort_id):
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

    # --- Rueckmeldungen der Runde (O4/M5) -----------------------------------------

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """👎 auf eine eigene Antwort -> Kurations-Kandidat im Abfrage-Protokoll.

        RAW statt `on_reaction_add`: Das gecachte Ereignis feuert nur fuer Nachrichten, die
        der Bot noch im Speicher hat. Nach einem Neustart - und genau dann liegen die
        interessanten Antworten schon im Kanal - blieben Markierungen sonst stumm."""
        markierung = await self._markierte_antwort(payload)
        if markierung is None:
            return
        nachricht, kanal = markierung
        frage = await self._frage_zur_antwort(nachricht, kanal)
        protokoll.merke_rueckmeldung(
            art=rueckmeldung.ART, frage=frage,
            verweis=rueckmeldung.verweis(payload.guild_id, payload.channel_id,
                                         payload.message_id))
        try:
            await nachricht.add_reaction(rueckmeldung.BESTAETIGUNG)
        except discord.HTTPException as fehler:
            # Fehlt das Reaktions-Recht, ist die Markierung TROTZDEM notiert - nur die
            # Bestaetigung bleibt aus. Deshalb erst schreiben, dann bestaetigen.
            _log.warning("Bestaetigung nicht setzbar: %s", type(fehler).__name__)

    async def on_raw_reaction_remove(self,
                                     payload: discord.RawReactionActionEvent) -> None:
        """Markierung zurueckgenommen -> Zeile weg. Ein Fehlgriff soll die Kurationsliste
        nicht dauerhaft belasten. Die Bestaetigung des Bots bleibt bewusst stehen: sie
        wieder wegzunehmen hiesse zu wissen, ob NIEMAND mehr markiert hat - und dafuer
        muesste der Bot Nutzer auseinanderhalten."""
        if not rueckmeldung.ist_markierung(str(payload.emoji)):
            return
        if payload.guild_id != self._guild.id:
            return
        protokoll.loesche_rueckmeldung(
            art=rueckmeldung.ART,
            verweis=rueckmeldung.verweis(payload.guild_id, payload.channel_id,
                                         payload.message_id))

    async def _markierte_antwort(self, payload: discord.RawReactionActionEvent):
        """(Nachricht, Kanal), wenn das Ereignis eine Markierung an einer EIGENEN Antwort
        im richtigen Ort ist - sonst None. Die Reihenfolge der Pruefungen ist
        Sparsamkeit: Emoji und Guild kosten nichts, das Nachladen der Nachricht einen
        API-Aufruf."""
        if not rueckmeldung.ist_markierung(str(payload.emoji)):
            return None
        if payload.guild_id != self._guild.id:
            return None
        try:
            kanal = (self.get_channel(payload.channel_id)
                     or await self.fetch_channel(payload.channel_id))
            ort_id = getattr(kanal, "parent_id", None) or payload.channel_id
            if not self.schranken.richtiger_ort(payload.guild_id, ort_id):
                return None
            nachricht = await kanal.fetch_message(payload.message_id)
        except discord.HTTPException as fehler:
            _log.warning("Reaktion nicht aufloesbar: %s", type(fehler).__name__)
            return None
        if nachricht.author.id != (self.user and self.user.id):
            return None                      # fremde Nachricht: nicht unsere Auskunft
        return nachricht, kanal

    async def _frage_zur_antwort(self, nachricht: discord.Message, kanal) -> str | None:
        """Die Frage, auf die die markierte Antwort geantwortet hat. Best effort - ein
        leeres Ergebnis verwirft die Markierung NICHT (rueckmeldung.frage_aus_umgebung)."""
        try:
            vorlauf = [(n.author.bot, n.content)
                       async for n in kanal.history(limit=6, before=nachricht)]
            vorlauf.reverse()                # history() liefert neueste zuerst
        except discord.HTTPException:
            vorlauf = []
        if isinstance(kanal, discord.Thread):
            titel = kanal.name
        else:
            # /regel antwortet IM KANAL und haengt den Thread an diese Nachricht - der
            # Titel traegt dort die Frage, die als Slash-Parameter nirgends steht.
            titel = getattr(nachricht.thread, "name", None)
        return rueckmeldung.frage_aus_umgebung(vorlauf, titel)

    async def _stelle_verlauf_her(self, thread: discord.Thread) -> bool:
        """Verlauf eines eigenen Threads aus der Discord-Historie rekonstruieren.
        True = es gibt wieder Kontext. False = nichts Verwertbares gefunden; dann ist
        der Vergessen-Hinweis raus und die Frage soll im Ganzen neu kommen.

        Der Thread gilt danach in JEDEM Fall als bekannt (auch mit leerem Verlauf) -
        sonst liefe der Hinweis bei jeder weiteren Nachricht erneut."""
        try:
            roh, vollstaendig = await self._lies_historie(thread)
        except discord.HTTPException as fehler:
            # Nur die Ursache loggen, nie Inhalte (Datenschutz wie bei on_ready).
            _log.warning("Historie von Thread %s nicht lesbar: %s",
                         thread.id, type(fehler).__name__)
            roh, vollstaendig = [], False
        # Der Titel ist die Ersatzfrage fuer /regel-Threads (dort steht die Frage
        # nirgends im Kanal) - aber nur, wenn der Anfang wirklich mitgelesen wurde.
        verlauf = rebuild.baue_verlauf(roh, thread.name if vollstaendig else None)
        self.gespraeche.setze(thread.id, verlauf)
        if verlauf:
            _log.info("Verlauf von Thread %s wiederhergestellt (%d Nachrichten)",
                      thread.id, len(verlauf))
            return True
        await thread.send(antwort.HINWEIS_VERGESSEN)
        return False

    async def _lies_historie(
            self, thread: discord.Thread) -> tuple[list[tuple[bool, str]], bool]:
        """Die juengsten Thread-Nachrichten als (ist_bot, inhalt) in chronologischer
        Reihenfolge, plus ob der Thread-Anfang mitgelesen wurde. Fremde Bots bleiben
        draussen - sie sind weder Frage noch Antwort. `vollstaendig` zaehlt deshalb
        VOR dem Filtern: eine gekappte Historie, aus der Bots herausfielen, saehe
        sonst faelschlich vollstaendig aus."""
        eigene_id = self.user and self.user.id
        nachrichten = [n async for n in thread.history(limit=_HISTORIE_LIMIT)]
        nachrichten.reverse()                # history() liefert neueste zuerst
        vollstaendig = len(nachrichten) < _HISTORIE_LIMIT
        roh = [(n.author.id == eigene_id, n.content) for n in nachrichten
               if not n.author.bot or n.author.id == eigene_id]
        starter = await self._starter_nachricht(thread)
        if starter is not None and vollstaendig:
            # Der Startbeitrag steht im ELTERN-Kanal, nicht in der Thread-Historie:
            # bei @Mention die Frage, bei /regel Teil 1 der Antwort. Nur anhaengen,
            # wenn nicht gekappt wurde - sonst klebte er an einer fremden Antwort.
            roh.insert(0, (starter.author.id == eigene_id, starter.content))
        return roh, vollstaendig

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
        grund = self.schranken.beginne(nachricht.author.id)
        if grund:
            await nachricht.channel.send(grund)
            return
        try:
            async with nachricht.channel.typing():
                text = await self._beantworte(nachricht.author.id, frage, verlauf=[])
            teile = antwort.teile(text)
            if ist_thread:
                ziel = nachricht.channel
            else:
                # Thread auf der NUTZER-Nachricht: die Frage steht sichtbar ueber dem
                # Gespraech, der Kanal bleibt aufgeraeumt. Verweigert Discord den
                # Thread, geht die Antwort in den Kanal statt verloren.
                ziel = (await self._eroeffne_thread(nachricht.channel, nachricht,
                                                    frage)
                        or nachricht.channel)
            for teil in teile:
                await ziel.send(teil)
            if isinstance(ziel, discord.Thread):
                # Nur Threads tragen Folgefragen - im Kanal-Fallback gibt es keinen
                # Ort, an dem on_message den Verlauf wiederfaende.
                self.gespraeche.ergaenze(ziel.id, frage, text)
        finally:
            self.schranken.beende(nachricht.author.id)

    async def _thread_folgefrage(self, nachricht: discord.Message) -> None:
        frage = self._ohne_mentions(nachricht.content)
        if not frage:
            return
        grund = self.schranken.beginne(nachricht.author.id)
        if grund:
            await nachricht.channel.send(grund)
            return
        try:
            verlauf = self.gespraeche.verlauf(nachricht.channel.id)
            async with nachricht.channel.typing():
                text = await self._beantworte(nachricht.author.id, frage,
                                              verlauf=verlauf)
            for teil in antwort.teile(text):
                await nachricht.channel.send(teil)
            self.gespraeche.ergaenze(nachricht.channel.id, frage, text)
        finally:
            self.schranken.beende(nachricht.author.id)

    # --- Kern ---------------------------------------------------------------------

    async def _beantworte(self, nutzer_id: int, frage: str,
                          verlauf: list[dict]) -> str:
        """Eine Frage durch die geteilte Schleife fahren; liefert IMMER einen
        sendbaren deutschen Text (Fehler werden zu ehrlichen Meldungen, nie zu
        Stacktraces im Kanal). Die Schranken verwaltet der AUFRUFER: beginne()
        muss VOR dem ersten await fallen, sonst ist die Ein-Anfrage-Regel loechrig."""
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
