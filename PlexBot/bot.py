import asyncio
import io
import logging
from urllib.request import urlopen

import discord
from async_timeout import timeout
from discord import FFmpegPCMAudio
from discord.ext import commands
from discord.ext.commands import command
from fuzzywuzzy import fuzz
from plexapi.exceptions import Unauthorized
from plexapi.server import PlexServer

logger = logging.getLogger("PlexBot")


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @command()
    async def kill(self, ctx):
        await ctx.send(f"Stopping upon the request of {ctx.author.mention}")
        await self.bot.close()
        logger.info(f"Stopping upon the request of {ctx.author.mention}")


class Plex(commands.Cog):
    def __init__(self, bot, base_url, plex_token, lib_name, bot_prefix) -> None:
        self.bot = bot
        self.base_url = base_url
        self.plex_token = plex_token
        self.library_name = lib_name
        self.bot_prefix = bot_prefix

        try:
            self.pms = PlexServer(self.base_url, self.plex_token)
        except Unauthorized:
            logger.fatal("Invalid Plex token, stopping...")
            raise Unauthorized("Invalid Plex token")

        self.music = self.pms.library.section(self.library_name)

        self.vc = None
        self.current_track = None
        self.play_queue = asyncio.Queue()
        self.play_next_event = asyncio.Event()

        self.bot.loop.create_task(self._audio_player_task())

        logger.info("Started bot successfully")

    def _search_tracks(self, title):
        tracks = self.music.searchTracks()
        score = [None, -1]
        for i in tracks:
            s = fuzz.ratio(title.lower(), i.title.lower())
            if s > score[1]:
                score[0] = i
                score[1] = s
            elif s == score[1]:
                score[0] = i

        return score[0]

    @command()
    async def hello(self, ctx, *, member: discord.member = None):
        member = member or ctx.author
        await ctx.send(f"Hello {member}")

    async def _play(self):
        track_url = self.current_track.getStreamURL()
        audio_stream = FFmpegPCMAudio(track_url)

        while self.vc.is_playing():
            asyncio.sleep(2)

        self.vc.play(audio_stream, after=self._toggle_next)

        logger.debug(f"Playing {self.current_track.title}")
        logger.debug(f"URL: {track_url}")

        embed, f = self._build_embed(self.current_track)
        await self.ctx.send(embed=embed, file=f)

    async def _audio_player_task(self):
        while True:
            self.play_next_event.clear()
            if self.vc:
                try:
                    # Disconnect after 15 seconds idle
                    async with timeout(15):
                        self.current_track = await self.play_queue.get()
                except asyncio.TimeoutError:
                    await self.vc.disconnect()
                    self.vc = None

            if not self.current_track:
                self.current_track = await self.play_queue.get()

            await self._play()
            await self.play_next_event.wait()

    def _toggle_next(self, error=None):
        self.current_track = None
        self.bot.loop.call_soon_threadsafe(self.play_next_event.set)

    def _build_embed(self, track, t="play"):
        """Creates a pretty embed card.
        """
        # Grab the relevant thumbnail
        img_stream = urlopen(track.thumbUrl)
        img = io.BytesIO(img_stream.read())

        # Attach to discord embed
        f = discord.File(img, filename="image0.png")
        # Get appropiate status message
        if t == "play":
            title = f"Now Playing - {track.title}"
        elif t == "queue":
            title = f"Added to queue - {track.title}"
        else:
            raise ValueError(f"Unsupported type of embed {t}")

        # Include song details
        descrip = f"{track.album().title} - {track.artist().title}"

        # Build the actual embed
        embed = discord.Embed(
            title=title, description=descrip, colour=discord.Color.red()
        )
        embed.set_author(name="Plex")
        # Point to file attached with ctx object.
        embed.set_thumbnail(url="attachment://image0.png")

        return embed, f

    @command()
    async def play(self, ctx, *args):

        if not len(args):
            await ctx.send(f"Usage: {self.bot_prefix}play TITLE_OF_SONG")
            return

        title = " ".join(args)
        track = self._search_tracks(title)

        # Fail if song title can't be found
        if not track:
            await ctx.send(f"Can't find song: {title}")
            return
        # Fail if user not in vc
        elif not ctx.author.voice:
            await ctx.send("Join a voice channel first!")
            return

        # Connect to voice if not already
        if not self.vc:
            self.vc = await ctx.author.voice.channel.connect()
            logger.debug("Connected to vc.")

        # Specific add to queue message
        if self.vc.is_playing():
            embed, f = self._build_embed(track, t="queue")
            await ctx.send(embed=embed, file=f)

        # Save the context to use with async callbacks
        self.ctx = ctx
        # Add the song to the async queue
        await self.play_queue.put(track)

    @command()
    async def stop(self, ctx):
        if self.vc:
            self.vc.stop()
            await self.vc.disconnect()
            self.vc = None
            self.ctx = None
            await ctx.send(":stop_button: Stopped")

    @command()
    async def pause(self, ctx):
        if self.vc:
            self.vc.pause()
            await ctx.send(":play_pause: Paused")

    @command()
    async def resume(self, ctx):
        if self.vc:
            self.vc.resume()
            await ctx.send(":play_pause: Resumed")

    @command()
    async def skip(self, ctx):
        logger.debug("Skip")
        if self.vc:
            self.vc.stop()
            self._toggle_next()

    @command()
    async def np(self, ctx):
        if self.current_track:
            embed, f = self._build_embed(self.current_track)
            await ctx.send(embed=embed, file=f)

    @command()
    async def clear(self, ctx):
        self.play_queue = asyncio.Queue()
        await ctx.send(":boom: Queue cleared.")
