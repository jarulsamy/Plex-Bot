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

# Set appropiate log level
root_log = logging.getLogger()
plex_log = logging.getLogger("Plex")
bot_log = logging.getLogger("Bot")

plex_log.setLevel(config["plex"]["log_level"])
bot_log.setLevel(config["discord"]["log_level"])

bot = Bot(command_prefix=BOT_PREFIX)
# Remove help command, we have our own custom one.
bot.remove_command("help")
bot.add_cog(General(bot))
bot.add_cog(Plex(bot, BASE_URL, PLEX_TOKEN, LIBRARY_NAME, BOT_PREFIX))
bot.run(TOKEN)
