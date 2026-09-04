"""Errors raised by this package."""


class AsepriteError(Exception):
    """Base error for reading, writing, or inspecting a sprite."""


class FormatError(AsepriteError):
    """The bytes are not a valid Aseprite document."""
