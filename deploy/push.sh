#!/usr/bin/env bash

VERSION=$(python PlexBot/__version__.py)

docker push "jarulsamy/plex-bot:$VERSION"

if [ $? -eq 0 ]
then
  echo "Successfully pushed docker image."
  exit 0
else
  echo "Failed to push docker image." >&2
  exit 1
fi
