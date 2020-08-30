FROM python:3.7-slim

LABEL maintainer="Joshua Arulsamy <joshua.gf.arul@gmail.com>"

# Install ffmpeg
RUN apt-get -y update && \
    apt-get install -y --no-install-recommends ffmpeg=7:4.1.6-1~deb10u1 && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# All source code
WORKDIR /src

# Copy of dependency manifest
COPY requirements.txt .

# Install all dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Copy PlexBot over to src.
COPY PlexBot/ PlexBot

# Run the bot
CMD ["python", "-OO", "-m", "PlexBot"]
