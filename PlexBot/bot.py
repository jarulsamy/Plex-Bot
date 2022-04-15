"""All discord bot and Plex api interactions."""
import asyncio
import io
import logging
from urllib.request import urlopen
import requests

import discord
from async_timeout import timeout
from discord import FFmpegPCMAudio
from discord.ext import commands
from discord.ext.commands import command
from plexapi.exceptions import Unauthorized
from plexapi.exceptions import NotFound
from plexapi.server import PlexServer

from .exceptions import MediaNotFoundError
from .exceptions import VoiceChannelError

root_log = logging.getLogger()
plex_log = logging.getLogger("Plex")
bot_log = logging.getLogger("Bot")

help_text = """
General:
    kill [silent] - Halt the bot [silently].
    help - Print this help message.
    cleanup - Delete old messages from the bot.

Plex:
    play <SONG_NAME> - Play a song from the plex server.
    album <ALBUM_NAME> - Queue an entire album to play.
    playlist <PLAYLIST_NAME> - Queue an entire playlist to play.
    show_playlists <ARG> <ARG> - Query for playlists with a name matching any of the arguments.
    lyrics - Print the lyrics of the song (Requires Genius API)
    np - Print the current playing song.
    q - Print the current queue (This can take very long!)
    stop - Halt playback and leave vc.
    loop - Loop the current song.
    unloop - Disable looping.
    pause - Pause playback.
    resume - Resume playback.
    skip - Skip the current song. Give a number as argument to skip more than 1.
    clear - Clear play queue.

[] - Optional args.
"""


class General(commands.Cog):
    """
    General commands

    Manage general bot behavior
    """

    def __init__(self, bot):
        """
        Initialize commands

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
        """
        Kill the bot

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

    @command(name="help")
    async def help(self, ctx):
        """
        Prints command help

        Args:
            ctx: discord.ext.commands.Context message context from command

        Returns:
            None

        Raise:
            None
        """

        await ctx.send(f"```{help_text}```")

    @command()
    async def cleanup(self, ctx, limit=250):
        """
        Delete old messages from bot

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

            async for i in channel.history(limit=limit):
                if i.author == ctx.message.author and i.content.startswith(
                    self.bot.command_prefix
                ):
                    try:
                        await i.delete()
                    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                        pass

        except discord.Forbidden:
            bot_log.info("Unable to delete messages, insufficient permissions.")
            await ctx.send("I don't have the necessary permissions to delete messages.")


class Plex(commands.Cog):
    """
    Discord commands pertinent to interacting with Plex

    Contains user commands such as play, pause, resume, stop, etc.
    Grabs, and parses all data from plex database.
    """

    # pylint: disable=too-many-instance-attributes
    # All are necessary to detect global interactions
    # within the bot.

    def __init__(self, bot, **kwargs):
        """
        Initializes Plex resources

        Connects to Plex library and sets up
        all asyncronous communications.

        Args:
            bot: discord.ext.command.Bot, bind for cogs
            base_url: str url to Plex server
            plex_token: str X-Token of Plex server
            lib_name: str name of Plex library to search through

        Raises:
            plexapi.exceptions.Unauthorized: Invalid Plex token

        Returns:
            None
        """

        self.bot = bot
        self.base_url = kwargs["base_url"]
        self.plex_token = kwargs["plex_token"]
        self.library_name = kwargs["lib_name"]
        self.bot_prefix = bot.command_prefix

        if kwargs["lyrics_token"]:
            import lyricsgenius
            self.genius = lyricsgenius.Genius(kwargs["lyrics_token"])
        else:
            plex_log.warning("No lyrics token specified, lyrics disabled")
            self.genius = None

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
        self.is_looping = False
        self.np_message_id = None
        self.show_queue_message_ids = []        
        self.ctx = None

        # Initialize events
        self.play_queue = asyncio.Queue()
        self.play_next_event = asyncio.Event()

        bot_log.info("Started bot successfully")
        self.bot.loop.create_task(self._audio_player_task())

    def _search_tracks(self, title: str):
        """
        Search the Plex music db for track

        Args:
            title: str title of song to search for

        Returns:
            plexapi.audio.Track pointing to best matching title

        Raises:
            MediaNotFoundError: Title of track can't be found in plex db
        """
        results = self.music.searchTracks(title=title, maxresults=1)
        try:
            return results[0]
        except IndexError:
            raise MediaNotFoundError("Track cannot be found")

    def _search_albums(self, title: str):
        """
        Search the Plex music db for album

        Args:
            title: str title of album to search for

        Returns:
            plexapi.audio.Album pointing to best matching title

        Raises:
            MediaNotFoundError: Title of album can't be found in plex db
        """
        results = self.music.searchAlbums(title=title, maxresults=1)
        try:
            return results[0]
        except IndexError:
            raise MediaNotFoundError("Album cannot be found")

    def _search_playlists(self, title: str):
        """
        Search the Plex music db for playlist

        Args:
            title: str title of playlist to search for

        Returns:
            plexapi.playlist pointing to best matching title

        Raises:
            MediaNotFoundError: Title of playlist can't be found in plex db
        """
        try:
            return self.pms.playlist(title)
        except NotFound:
            raise MediaNotFoundError("Playlist cannot be found")

    def _get_playlists(self):
        """
        Search the Plex music db for playlist

        Returns:
            List of plexapi.playlist
        """
        return self.pms.playlists()

    async def _play(self):
        """
        Heavy lifting of playing songs

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

        while self.voice_channel and self.voice_channel.is_playing():
            bot_log.debug("waiting for track to finish")
            await asyncio.sleep(2)
        bot_log.debug("track finished")            

        if self.voice_channel:
            self.voice_channel.play(audio_stream, after=self._toggle_next)
    
            plex_log.debug("%s - URL: %s", self.current_track, track_url)
    
            embed, img = self._build_embed_track(self.current_track)
            self.np_message_id = await self.ctx.send(embed=embed, file=img)

    async def _play_next(self):
        if self.is_looping:
            self.current_track = self.is_looping
        else:
            try:
                self.current_track = await self.play_queue.get()
            except asyncio.exceptions.CancelledError:
                bot_log.debug("failed to pop queue")

            
    async def _audio_player_task(self):
        """
        Coroutine to handle playback and queuing

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
                        await self._play_next()
                except asyncio.TimeoutError:
                    bot_log("timeout - disconnecting")
                    await self.voice_channel.disconnect()
                    self.voice_channel = None

            if not self.current_track:
                await self._play_next()

            await self._play()
            await self.play_next_event.wait()
            if self.np_message_id:
                await self.np_message_id.delete()

    def _toggle_next(self, error=None):
        """
        Callback for vc playback

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

    @staticmethod
    def _build_embed_track(track, type_="play"):
        """
        Creates a pretty embed card for tracks

        Builds a helpful status embed with the following info:
        Status, song title, album, artist and album art. All
        pertitent information is grabbed dynamically from the Plex db.

        Args:
            track: plexapi.audio.Track object of song
            type_: Type of card to make (play, queue).

        Returns:
            embed: discord.embed fully constructed payload.
            thumb_art: io.BytesIO of album thumbnail img.

        Raises:
            ValueError: Unsupported type of embed {type_}
        """
        # Grab the relevant thumbnail
        img_stream = requests.get(track.thumbUrl, stream=True).raw
        img = io.BytesIO(img_stream.read())

        # Attach to discord embed
        art_file = discord.File(img, filename="image0.png")
        # Get appropiate status message
        if type_ == "play":
            title = f"Now Playing - {track.title}"
        elif type_ == "queue":
            title = f"Added to queue - {track.title}"
        elif type_ == "queued":
            title = f"Next in line - {track.title}"
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

        bot_log.debug("Built embed for track - %s", track.title)

        return embed, art_file

    @staticmethod
    def _build_embed_album(album):
        """
        Creates a pretty embed card for albums

        Builds a helpful status embed with the following info:
        album, artist, and album art. All pertitent information
        is grabbed dynamically from the Plex db.

        Args:
            album: plexapi.audio.Album object of album

        Returns:
            embed: discord.embed fully constructed payload.
            thumb_art: io.BytesIO of album thumbnail img.

        Raises:
            None
        """
        # Grab the relevant thumbnail
        img_stream = requests.get(album.thumbUrl, stream=True).raw
        img = io.BytesIO(img_stream.read())

        # Attach to discord embed
        art_file = discord.File(img, filename="image0.png")
        title = "Added album to queue"
        descrip = f"{album.title} - {album.artist().title}"

        embed = discord.Embed(
            title=title, description=descrip, colour=discord.Color.red()
        )
        embed.set_author(name="Plex")
        embed.set_thumbnail(url="attachment://image0.png")
        bot_log.debug("Built embed for album - %s", album.title)

        return embed, art_file

    @staticmethod
    def _build_embed_playlist(self, playlist, title, descrip):
        """
        Creates a pretty embed card for playlists

        Builds a helpful status embed with the following info:
        playlist art. All pertitent information
        is grabbed dynamically from the Plex db.

        Args:
            playlist: plexapi.playlist object of playlist

        Returns:
            embed: discord.embed fully constructed payload.
            thumb_art: io.BytesIO of playlist thumbnail img.

        Raises:
            None
        """
        # Grab the relevant thumbnail
        try:
            img_stream = requests.get(self.pms.url(playlist.composite, True), stream=True).raw
            img = io.BytesIO(img_stream.read())
        except:
            raise MediaNotFoundError("no image available")

        # Attach to discord embed
        art_file = discord.File(img, filename="image0.png")

        embed = discord.Embed(
            title=title, description=descrip, colour=discord.Color.red()
        )
        embed.set_author(name="Plex")
        embed.set_thumbnail(url="attachment://image0.png")
        bot_log.debug("Built embed for playlist - %s", playlist.title)

        return embed, art_file

    async def _validate(self, ctx):
        """
        Ensures user is in a vc

        Args:
            ctx: discord.ext.commands.Context message context from command

        Returns:
            None

        Raises:
            VoiceChannelError: Author not in voice channel
        """
        # Fail if user not in vc
        if not ctx.author.voice:
            await ctx.send("Join a voice channel first!")
            bot_log.debug("Failed to play, requester not in voice channel")
            raise VoiceChannelError

        # Connect to voice if not already
        if not self.voice_channel:
            try:
                self.voice_channel = await ctx.author.voice.channel.connect()
                bot_log.debug("Connected to vc.")
            except asyncio.exceptions.TimeoutError:
                bot_log.debug("Cannot connect to vc - timeout")                

    @command()
    async def play(self, ctx, *args):
        """
        User command to play song

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
        title = " ".join(args)

        try:
            track = self._search_tracks(title)
        except MediaNotFoundError:
            await ctx.send(f"Can't find song: {title}")
            bot_log.debug("Failed to play, can't find song - %s", title)
            return

        try:
            await self._validate(ctx)
        except VoiceChannelError:
            pass

        # Specific add to queue message
        if self.voice_channel and self.voice_channel.is_playing():
            bot_log.debug("Added to queue - %s", title)
            embed, img = self._build_embed_track(track, type_="queue")
            await ctx.send(embed=embed, file=img)

        # Add the song to the async queue
        await self.play_queue.put(track)

    @command()
    async def album(self, ctx, *args):
        """
        User command to play song

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
        title = " ".join(args)

        try:
            album = self._search_albums(title)
        except MediaNotFoundError:
            await ctx.send(f"Can't find album: {title}")
            bot_log.debug("Failed to queue album, can't find - %s", title)
            return

        try:
            await self._validate(ctx)
        except VoiceChannelError:
            pass

        bot_log.debug("Added to queue - %s", title)
        embed, img = self._build_embed_album(album)
        await ctx.send(embed=embed, file=img)

        for track in album.tracks():
            await self.play_queue.put(track)

    @command()
    async def playlist(self, ctx, *args):
        """
        User command to play playlist

        Searchs plex db and either, initiates playback, or
        adds to queue. Handles invalid usage from the user.

        Args:
            ctx: discord.ext.commands.Context message context from command
            *args: Title of playlist to play

        Returns:
            None

        Raises:
            None
        """
        # Save the context to use with async callbacks
        self.ctx = ctx
        title = " ".join(args)

        try:
            playlist = self._search_playlists(title)
        except MediaNotFoundError:
            await ctx.send(f"Can't find playlist: {title}")
            bot_log.debug("Failed to queue playlist, can't find - %s", title)
            return

        try:
            await self._validate(ctx)
        except VoiceChannelError:
            pass

        try:
            embed, img = self._build_embed_playlist(self, playlist, "Added playlist to queue", playlist.title)
            await ctx.send(embed=embed, file=img)

            for item in playlist.items():
                if (item.TYPE == "track"):
                    await self.play_queue.put(item)
            bot_log.debug("Added to queue - %s", title)
        except MediaNotFoundError:
            await ctx.send(message="Playlist "+title+" seems to be empty!")
            bot_log.debug("Playlist empty - %s", title)
    @command()
    async def show_playlists(self, ctx, *args):
        """
        User command to show playlists

        Searchs plex db and shows playlists matching.

        Args:
            ctx: discord.ext.commands.Context message context from command
            *args: String filter for playlist names

        Returns:
            None

        Raises:
            None
        """
        # Save the context to use with async callbacks
        self.ctx = ctx

        playlists = self._get_playlists()

        try:
            await self._validate(ctx)
        except VoiceChannelError:
            pass

        for playlist in playlists:
            if args and not any(arg in playlist.title for arg in args):
                continue
            from datetime import timedelta
            if playlist.duration:
                seconds = playlist.duration / 1000
                embed, img = self._build_embed_playlist(self, playlist, playlist.title, "{:0>8}".format(str(timedelta(seconds=seconds))))
                await ctx.send(embed=embed, file=img)

    @command()
    async def stop(self, ctx):
        """
        User command to stop playback

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
    async def loop(self, ctx):
        """
        User command to activate looping the current track

        Args:
            ctx: discord.ext.commands.Context message context from command

        Returns:
            None

        Raises:
            None
        """
        bot_log.debug("Looping "+str(self.current_track))        
        self.is_looping = self.current_track

    @command()
    async def unloop(self, ctx):
        """
        User command to deactivate looping the current track

        Args:
            ctx: discord.ext.commands.Context message context from command

        Returns:
            None

        Raises:
            None
        """
        bot_log.debug("Unlooping")                
        self.is_looping = False        
            

    @command()
    async def pause(self, ctx):
        """
        User command to pause playback

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
        """
        User command to resume playback

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
    async def skip(self, ctx, *args):
        """
        User command to skip song in queue

        Skips currently playing song. If no other songs in
        queue, stops playback, otherwise moves to next song.

        Args:
            ctx: discord.ext.commands.Context message context from command

        Returns:
            None

        Raises:
            None
        """
        n = 1
        if args:
            n = int(args[0])
        bot_log.debug("Skipping "+str(n))
        if self.voice_channel:
            self.voice_channel.stop()
            bot_log.debug("Skipped")
            if n>1:
                for i in range(n-1):
                    await self.play_queue.get()
            self._toggle_next()

    @command(name="np")
    async def now_playing(self, ctx):
        """
        User command to get currently playing song.

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
            embed, img = self._build_embed_track(self.current_track,type_="play")
            bot_log.debug("Now playing")
            if self.np_message_id:
                try:
                    await self.np_message_id.delete()
                    bot_log.debug("Deleted old np status")
                except discord.errors.NotFound:
                    pass

            bot_log.debug("Created np status")
            self.np_message_id = await ctx.send(embed=embed, file=img)

    @command(name="q")
    async def show_queue(self, ctx):
        """
        User command to print the current queue

        Deletes old `now playing` status message,
        Creates a new one with up to date information.

        Args:
            ctx: discord.ext.commands.Context message context from command

        Returns:
            None

        Raises:
            None
        """
        bot_log.debug("Deleted old queue messages")
        for msg in self.show_queue_message_ids:
            await msg.delete()

        # need to do this in order to avoid errors when queue is modified during inspection
        elems = []
        for track in self.play_queue._queue:
            elems.append(track)

        for track in elems:
            embed, img = self._build_embed_track(track,type_="queued")
            bot_log.debug("Show queue")

            bot_log.debug("Created queue message")
            self.show_queue_message_ids.append(await ctx.send(embed=embed, file=img))

    @command()
    async def clear(self, ctx):
        """
        User command to clear play queue.

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

    @command()
    async def lyrics(self, ctx):
        """
        User command to get lyrics of a song.

        Args:
            ctx: discord.ext.commands.Context message context from command

            Returns:
                None

            Raises:
                None
        """
        if not self.current_track:
            plex_log.info("No song currently playing")
            return

        if self.genius:
            plex_log.info(
                "Searching for %s, %s",
                self.current_track.title,
                self.current_track.artist().title,
            )
            try:
                song = self.genius.search_song(
                    self.current_track.title, self.current_track.artist().title
                )
            except TypeError:
                self.genius = None
                plex_log.error("Invalid genius token, disabling lyrics")
                return

            try:
                lyrics = song.lyrics
                # Split into 1950 char chunks
                # Discord max message length is 2000
                lines = [(lyrics[i : i + 1950]) for i in range(0, len(lyrics), 1950)]

                for i in lines:
                    if i == "":
                        continue
                    # Apply code block format
                    i = f"```{i}```"
                    await ctx.send(i)

            except (IndexError, TypeError):
                plex_log.info("Could not find lyrics")
                await ctx.send("Can't find lyrics for this song.")
        else:
            plex_log.warning("Attempted lyrics without valid token")
