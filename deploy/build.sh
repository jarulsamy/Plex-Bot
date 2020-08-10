#!/usr/bin/env bash

VERSION=$(python PlexBot/__version__.py)

docker build -t "jarulsamy/plex-bot:$VERSION" .

if [ $? -eq 0 ]
then
  echo "Successfully build docker image."
  exit 0
else
  echo "Failed to build docker image." >&2
  exit 1
fi
