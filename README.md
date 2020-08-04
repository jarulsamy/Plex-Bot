# Plex-Bot

A Python-based Plex music bot for discord.

## Setup

Plex-Bot runs entirely in a Docker container. Ensure you have Docker and docker-compose installed according to the official Docker [documentation](https://docs.docker.com/get-docker/).

1.  Clone the repository and `cd` into it:

```
$ git clone https://github.com/jarulsamy/Plex-Bot
$ cd Plex-Bot
```

2. Create a configuration folder:

Create a new `config` folder and copy the sample config file into it:

```
$ mkdir config
$ cp sample-config.yaml config/config.yaml
```

3.  Create a Discord bot application:

    1. Go to the Discord developer portal, [here](https://discord.com/developers/applications).

    2. Log in or create an account

    3. Click New App

    4. Fill in App Name and anything else you'd like to include

    5. Click Create App
        This will provide you with your Client ID and Client Secret

    6. Click Create Bot User
        This will provide you with your bot Username and Token

    7. Fill in all the necessary numbers in `config/config.yaml`

4. Get your plex token:

   Refer to the official [plex documentation](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).

   Add it to `config/config.yaml` in the appropiate spot.

5. Start the service:

```
$ docker-compose up --build
```

## Usage

```
General:
  kill - Stop the bot.
Plex:
  np - View currently playing song.
  pause - Pause currently playing song.
  play - Play a song from the Plex library.
  resume - Resume a paused song.
  skip - Skip a song.
  stop - Stop playing.
​No Category:
  help   Shows this message

Type ?help command for more info on a command.
You can also type ?help category for more info on a category.
```

## Support

Reach out to me at one of the following places!

-   Email (Best) at joshua.gf.arul@gmail.com
-   Twitter at <a href="http://twitter.com/jarulsamy_" target="_blank">`@jarulsamy_`</a>

* * *
