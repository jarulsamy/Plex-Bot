from discord.ext.commands import Bot

from .bot import General
from .bot import Plex
from PlexBot import load_config
from . import FORMAT

import logging

# Load config from file
config = load_config("config.yaml")

BOT_PREFIX = config["discord"]["prefix"]
TOKEN = config["discord"]["token"]

BASE_URL = config["plex"]["base_url"]
PLEX_TOKEN = config["plex"]["token"]
LIBRARY_NAME = config["plex"]["library_name"]
LOG_LEVEL = config["general"]["log_level"]

# Set appropiate log level
logger = logging.getLogger("PlexBot")
logging.basicConfig(format=FORMAT)
logger.setLevel(LOG_LEVEL)

bot = Bot(command_prefix=BOT_PREFIX)
bot.add_cog(General(bot))
bot.add_cog(Plex(bot, BASE_URL, PLEX_TOKEN, LIBRARY_NAME))
bot.run(TOKEN)
