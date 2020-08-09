"""Plex music bot for discord.

    Do not import this module, it is intended to be
    used exclusively within a docker environment.

"""
import logging
import sys
from pathlib import Path
from typing import Dict

import yaml

FORMAT = "%(asctime)s %(levelname)s: [%(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"

logging.basicConfig(format=FORMAT)
root_log = logging.getLogger()
plex_log = logging.getLogger("Plex")
bot_log = logging.getLogger("Bot")


def load_config(filename: str) -> Dict[str, str]:
    """Loads config from yaml file

    Grabs key/value config pairs from a file.

    Args:
        filename: str path to yaml file.

    Returns:
        Dict[str, str] Values from config file.

    Raises:
        FileNotFound Configuration file not found.
    """
    # All config files should be in /config
    # for docker deployment.
    filename = Path("/config", filename)
    try:
        with open(filename, "r") as config_file:
            config = yaml.safe_load(config_file)
    except FileNotFoundError:
        root_log.fatal("Configuration file not found.")
        sys.exit(-1)

    # Convert str level type to logging constant
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    config["root"]["log_level"] = levels[config["root"]["log_level"].upper()]
    config["plex"]["log_level"] = levels[config["plex"]["log_level"].upper()]
    config["discord"]["log_level"] = levels[config["discord"]["log_level"].upper()]

    return config
