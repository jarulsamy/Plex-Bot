import logging
import sys
from pathlib import Path
from typing import Dict

import yaml

FORMAT = "%(asctime)s %(levelname)s: [%(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"

logging.basicConfig(format=FORMAT)
logger = logging.getLogger("PlexBot")


def load_config(filename: str) -> Dict[str, str]:

    # All config files should be in /config
    # for docker deployment.
    filename = Path("/config", filename)
    try:
        with open(filename, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logging.fatal("Configuration file not found.")
        sys.exit(-1)

    # Convert str level type to logging constant
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    level = config["general"]["log_level"]
    config["general"]["log_level"] = levels[level.upper()]

    return config
