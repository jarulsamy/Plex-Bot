FROM python:3.7-slim

# Install ffmpeg
RUN apt-get -y update && \
    apt-get install -y --no-install-recommends ffmpeg && \
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
