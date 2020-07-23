import discord
from discord.ext import commands
from discord.ext.commands import command
from fuzzywuzzy import fuzz
from plexapi.server import PlexServer


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @command()
    async def stop(self, ctx):
        await ctx.send(f"Stopping upon the request of {ctx.author.mention}")
        await self.bot.close()


class Plex(commands.Cog):
    def __init__(self, bot, base_url, plex_token, lib_name) -> None:
        self.bot = bot
        self.base_url = base_url
        self.plex_token = plex_token
        self.library_name = lib_name

        self.pms = PlexServer(self.base_url, self.plex_token)
        self.music = self.pms.library.section(self.library_name)

    def _search_tracks(self, title):
        tracks = self.music.searchTracks()
        score = [[None], -1]
        for i in tracks:
            # scores[i].append(fuzz.ratio(title.lower(), i.lower))
            s = fuzz.ratio(title.lower(), i.title.lower())
            if s > score[1]:
                score[0] = [i]
                score[1] = s
            elif s == score[1]:
                score[0].append(i)

        return score

    @command()
    async def hello(self, ctx, *, member: discord.member = None):
        member = member or ctx.author
        await ctx.send(f"Hello {member}")

    @command()
    async def play(self, ctx, *args):
        title = " ".join(args)
        track = self._search_tracks(title)
        if track[0][0]:
            await ctx.send(track[0][0].title)
        else:
            await ctx.send("Song not found!")
