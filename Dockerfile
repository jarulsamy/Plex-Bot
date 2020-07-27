# Python 3.7
FROM python:3.7

# All source code
WORKDIR /src

# Copy of dependency manifest
COPY requirements.txt .

# Install all dependencies.
RUN pip install -r requirements.txt

# Copy PlexBot over to src.
COPY PlexBot/ PlexBot

# Run the bot
CMD ["python", "-OO", "-m", "PlexBot"]
