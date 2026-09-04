"""Caps that stop untrusted files from allocating unbounded memory."""

from aseprite._errors import FormatError

# 256 MiB of RGBA, or an 8192×8192 canvas.
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_PIXELS = MAX_UNCOMPRESSED_BYTES // 4
MAX_PALETTE_COLORS = 65_535
MAX_GROUP_DEPTH = 256


class DocumentBudget:
    """Tracks uncompressed pixel bytes for one ``open()`` / ``from_bytes()`` call."""

    def __init__(self, limit: int) -> None:
        self.used = 0
        self.limit = limit

    def allow(self, n: int) -> None:
        if n < 0 or self.used + n > self.limit:
            raise FormatError("decompressed data exceeds the size limit")

    def charge(self, n: int) -> None:
        self.allow(n)
        self.used += n


def bytes_per_tile(bits_per_tile: int) -> int:
    """Returns the stored size of one tilemap cell."""
    if bits_per_tile == 32:
        return 4
    if bits_per_tile == 16:
        return 2
    return 1
