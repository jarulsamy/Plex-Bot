import os
import sys

sys.path.append("PlexBot")

from __version__ import VERSION

sys.exit(os.system(f"docker build -t jarulsamy/plex-bot:{VERSION} ."))
