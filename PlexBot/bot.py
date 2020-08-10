"""All discord bot and Plex api interactions."""
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

root_log = logging.getLogger()
plex_log = logging.getLogger("Plex")
bot_log = logging.getLogger("Bot")


class General(commands.Cog):
    """General commands

    Manage general bot behavior
    """

    def __init__(self, bot):
        """Initialize commands

        Args:
            bot: discord.ext.command.Bot, bind for cogs

        Returns:
            None

        Raises:
            None
        """
        self.bot = bot

    @command()
    async def kill(self, ctx, *args):
        """Kill the bot

        Args:
            ctx: discord.ext.commands.Context message context from command
            *args: optional flags

        Returns:
            None

        Raises:
            None
        """
        if "silent" not in args:
            await ctx.send(f"Stopping upon the request of {ctx.author.mention}")

        await self.bot.close()
        bot_log.info("Stopping upon the request of %s", ctx.author.mention)

    @command()
    async def cleanup(self, ctx, limit=250):
        """Delete old messages from bot

        Args:
            ctx: discord.ext.commands.Context message context from command
            limit: int number of messages to go back by to delete. Default 250

        Raises:
            None

        Returns:
            None
        """
        channel = ctx.message.channel

        try:
            async for i in channel.history(limit=limit):
                # Only delete messages sent by self
                if i.author == self.bot.user:
                    try:
                        await i.delete()
                    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                        pass

        except discord.Forbidden:
            bot_log.info("Unable to delete messages, insufficient permissions.")
            await ctx.send("I don't have the necessary permissions to delete messages.")


class Plex(commands.Cog):
    """Discord commands pertinent to interacting with Plex

        Contains user commands such as play, pause, resume, stop, etc.
        Grabs, and parses all data from plex database.

    """

    # pylint: disable=too-many-instance-attributes
    # All are necessary to detect global interactions
    # within the bot.

    def __init__(
        self, bot, base_url: str, plex_token: str, lib_name: str, bot_prefix: str
    ):
        """Initializes Plex resources

        Connects to Plex library and sets up
        all asyncronous communications.

        Args:
            bot: discord.ext.command.Bot, bind for cogs
            base_url: str url to Plex server
            plex_token: str X-Token of Plex server
            lib_name: str name of Plex library to search through
            bot_prefix: str prefix used to interact with bots

        Raises:
            plexapi.exceptions.Unauthorized: Invalid Plex token

        Returns:
            None
        """

        self.bot = bot
        self.base_url = base_url
        self.plex_token = plex_token
        self.library_name = lib_name
        self.bot_prefix = bot_prefix

        # Log fatal invalid plex token
        try:
            self.pms = PlexServer(self.base_url, self.plex_token)
        except Unauthorized:
            plex_log.fatal("Invalid Plex token, stopping...")
            raise Unauthorized("Invalid Plex token")

        self.music = self.pms.library.section(self.library_name)
        plex_log.debug("Connected to plex library: %s", self.library_name)

        # Initialize necessary vars
        self.voice_channel = None
        self.current_track = None
        self.np_message_id = None
        self.ctx = None

        # Initialize events
        self.play_queue = asyncio.Queue()
        self.play_next_event = asyncio.Event()

        bot_log.info("Started bot successfully")
        self.bot.loop.create_task(self._audio_player_task())

    def _search_tracks(self, title: str):
        """Search the Plex music db

        Uses a fuzzy search algorithm to find the closest matching song
        title in the Plex music database.

        Args:
            title: str title of song to search for

        Returns:
            plexapi.audio.Track pointing to closest matching title
            None if song can't be found.

        Raises:
            None
        """
        tracks = self.music.searchTracks()
        score = [None, -1]
        for i in tracks:
            ratio = fuzz.ratio(title.lower(), i.title.lower())
            if ratio > score[1]:
                score[0] = i
                score[1] = ratio
            elif ratio == score[1]:
                score[0] = i

        return score[0]

    async def _play(self):
        """Heavy lifting of playing songs

        Grabs the appropiate streaming URL, sends the `now playing`
        message, and initiates playback in the vc.

        Args:
            None

        Returns:
            None

        Raises:
            None
        """
        track_url = self.current_track.getStreamURL()
        audio_stream = FFmpegPCMAudio(track_url)

        while self.voice_channel.is_playing():
            asyncio.sleep(2)

        self.voice_channel.play(audio_stream, after=self._toggle_next)

        plex_log.debug("%s - URL: %s", self.current_track, track_url)

        embed, img = self._build_embed(self.current_track)
        self.np_message_id = await self.ctx.send(embed=embed, file=img)

    async def _audio_player_task(self):
        """Coroutine to handle playback and queuing

        Always-running function awaiting new songs to be added.
        Auto disconnects from VC if idle for > 15 seconds.
        Handles auto deletion of now playing song notifications.

        Args:
            None

        Returns:
            None

        Raises:
            None
        """
        while True:
            self.play_next_event.clear()
            if self.voice_channel:
                try:
                    # Disconnect after 15 seconds idle
                    async with timeout(15):
                        self.current_track = await self.play_queue.get()
                except asyncio.TimeoutError:
                    await self.voice_channel.disconnect()
                    self.voice_channel = None

            if not self.current_track:
                self.current_track = await self.play_queue.get()

            await self._play()
            await self.play_next_event.wait()
            await self.np_message_id.delete()

    def _toggle_next(self, error=None):
        """Callback for vc playback

        Clears current track, then activates _audio_player_task
        to play next in queue or disconnect.

        Args:
            error: Optional parameter required for discord.py callback

        Returns:
            None

        Raises:
            None
        """
        self.current_track = None
        self.bot.loop.call_soon_threadsafe(self.play_next_event.set)

    def _build_embed(self, track, type_="play"):
        """Creates a pretty embed card.

        Builds a helpful status embed with the following info:
        Status, song title, album, artistm and album art. All
        pertitent information is grabbed dynamically from the Plex db.

        Args:
            track: plexapi.audio.Track object of song
            type_: Type of card to make (play, queue).

        Returns:
            embed: discord.embed fully constructed img payload.
            thumb_art: io.BytesIO of album thumbnail img.

        Raises:
            ValueError: Unsupported type of embed {type_}
        """
        # Grab the relevant thumbnail
        img_stream = urlopen(track.thumbUrl)
        img = io.BytesIO(img_stream.read())

        # Attach to discord embed
        art_file = discord.File(img, filename="image0.png")
        # Get appropiate status message
        if type_ == "play":
            title = f"Now Playing - {track.title}"
        elif type_ == "queue":
            title = f"Added to queue - {track.title}"
        else:
            raise ValueError(f"Unsupported type of embed {type_}")

        # Include song details
        descrip = f"{track.album().title} - {track.artist().title}"

        # Build the actual embed
        embed = discord.Embed(
            title=title, description=descrip, colour=discord.Color.red()
        )
        embed.set_author(name="Plex")
        # Point to file attached with ctx object.
        embed.set_thumbnail(url="attachment://image0.png")

        bot_log.debug("Built embed for %s", track.title)

        return embed, art_file

    @command()
    async def play(self, ctx, *args):
        """User command to start playback

        Searchs plex db and either, initiates playback, or
        adds to queue. Handles invalid usage from the user.

        Args:
            ctx: discord.ext.commands.Context message context from command
            *args: Title of song to play

        Returns:
            None

        Raises:
            None
        """
        # Save the context to use with async callbacks
        self.ctx = ctx

        if not args:
            await ctx.send(f"Usage: {self.bot_prefix}play TITLE_OF_SONG")
            bot_log.debug("Failed to play, invalid usage")
            return

        title = " ".join(args)
        track = self._search_tracks(title)

        # Fail if song title can't be found
        if not track:
            await ctx.send(f"Can't find song: {title}")
            bot_log.debug("Failed to play, can't find song - %s", title)
            return

        # Fail if user not in vc
        if not ctx.author.voice:
            await ctx.send("Join a voice channel first!")
            bot_log.debug("Failed to play, requester not in voice channel")
            return

        # Connect to voice if not already
        if not self.voice_channel:
            self.voice_channel = await ctx.author.voice.channel.connect()
            bot_log.debug("Connected to vc.")

        # Specific add to queue message
        if self.voice_channel.is_playing():
            bot_log.debug("Added to queue - %s", title)
            embed, img = self._build_embed(track, type_="queue")
            await ctx.send(embed=embed, file=img)

        # Add the song to the async queue
        await self.play_queue.put(track)

    @command()
    async def stop(self, ctx):
        """User command to stop playback

        Stops playback and disconnects from vc.

        Args:
            ctx: discord.ext.commands.Context message context from command

        Returns:
            None

        Raises:
            None
        """
        if self.voice_channel:
            self.voice_channel.stop()
            await self.voice_channel.disconnect()
            self.voice_channel = None
            self.ctx = None
            bot_log.debug("Stopped")
            await ctx.send(":stop_button: Stopped")

    @command()
    async def pause(self, ctx):
        """User command to pause playback

        Pauses playback, but doesn't reset anything
        to allow playback resuming.

        Args:
            ctx: discord.ext.commands.Context message context from command

        Returns:
            None

        Raises:
            None
        """
        if self.voice_channel:
            self.voice_channel.pause()
            bot_log.debug("Paused")
            await ctx.send(":play_pause: Paused")

    @command()
    async def resume(self, ctx):
        """User command to resume playback

        Args:
            ctx: discord.ext.commands.Context message context from command

        Returns:
            None

        Raises:
            None
        """
        if self.voice_channel:
            self.voice_channel.resume()
            bot_log.debug("Resumed")
            await ctx.send(":play_pause: Resumed")

    @command()
    async def skip(self, ctx):
        """User command to skip song in queue

        Skips currently playing song. If no other songs in
        queue, stops playback, otherwise moves to next song.

        Args:
            ctx: discord.ext.commands.Context message context from command

        Returns:
            None

        Raises:
            None
        """
        bot_log.debug("Skip")
        if self.voice_channel:
            self.voice_channel.stop()
            bot_log.debug("Skipped")
            self._toggle_next()

    @command(name="np")
    async def now_playing(self, ctx):
        """User command to get currently playing song.

        Deletes old `now playing` status message,
        Creates a new one with up to date information.

        Args:
            ctx: discord.ext.commands.Context message context from command

        Returns:
            None

        Raises:
            None
        """
        if self.current_track:
            embed, img = self._build_embed(self.current_track)
            bot_log.debug("Now playing")
            if self.np_message_id:
                await self.np_message_id.delete()
                bot_log.debug("Deleted old np status")

            bot_log.debug("Created np status")
            self.np_message_id = await ctx.send(embed=embed, file=img)

    @command()
    async def clear(self, ctx):
        """User command to clear play queue.

        Args:
            ctx: discord.ext.commands.Context message context from command

        Returns:
            None

        Raises:
            None
        """
        self.play_queue = asyncio.Queue()
        bot_log.debug("Cleared queue")
        await ctx.send(":boom: Queue cleared.")
