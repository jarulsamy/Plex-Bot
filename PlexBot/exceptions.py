class MediaNotFoundError(Exception):
    """Raised when a PlexAPI media resource cannot be found."""

    pass


class VoiceChannelError(Exception):
    """Raised when user is not connected to a voice channel."""

    pass
