"""
Main entrypoint script.
Sets up loggers and initiates bot.
"""
import logging

from discord.ext.commands import Bot

from . import load_config
from .bot import General
from .bot import Plex

# Load config from file
config = load_config("config.yaml")

BOT_PREFIX = config["discord"]["prefix"]
TOKEN = config["discord"]["token"]

BASE_URL = config["plex"]["base_url"]
PLEX_TOKEN = config["plex"]["token"]
LIBRARY_NAME = config["plex"]["library_name"]

if config["lyrics"]:
    LYRICS_TOKEN = config["lyrics"]["token"]
else:
    LYRICS_TOKEN = None
    
# Set appropiate log level
root_log = logging.getLogger()
plex_log = logging.getLogger("Plex")
bot_log = logging.getLogger("Bot")

plex_log.setLevel(config["plex"]["log_level"])
bot_log.setLevel(config["discord"]["log_level"])

plex_args = {
    "base_url": BASE_URL,
    "plex_token": PLEX_TOKEN,
    "lib_name": LIBRARY_NAME,
    "lyrics_token": LYRICS_TOKEN,
}

bot = Bot(command_prefix=BOT_PREFIX)
# Remove help command, we have our own custom one.
bot.remove_command("help")
bot.add_cog(General(bot))
bot.add_cog(Plex(bot, **plex_args))
bot.run(TOKEN)
