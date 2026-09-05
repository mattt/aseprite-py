"""Caps that stop untrusted files from allocating unbounded memory."""

from aseprite._errors import FormatError

# 256 MiB of RGBA, or an 8192×8192 canvas.
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_PIXELS = MAX_UNCOMPRESSED_BYTES // 4
MAX_PALETTE_COLORS = 65_535
# Counts entries materialized across all palette snapshots in a document.
# Partial updates otherwise amplify tiny chunks into full lists of Color objects.
MAX_TOTAL_PALETTE_COLORS = 1 << 20
MAX_GROUP_DEPTH = 256
# Aseprite expects one user-data chunk per tile after an embedded tileset.
# Pad up to this many tiles; a larger count only occurs in corrupt files.
MAX_PADDED_TILE_USER_DATA = 1 << 20


class DocumentBudget:
    """Tracks pixel bytes and palette allocations for one document read."""

    def __init__(self, limit: int) -> None:
        self.used = 0
        self.limit = limit
        self.palette_colors = 0

    def allow(self, n: int) -> None:
        if n < 0 or self.used + n > self.limit:
            raise FormatError("decompressed data exceeds the size limit")

    def charge(self, n: int) -> None:
        self.allow(n)
        self.used += n

    def charge_palette(self, n: int) -> None:
        if n < 0 or self.palette_colors + n > MAX_TOTAL_PALETTE_COLORS:
            raise FormatError("document palette allocation exceeds the size limit")
        self.palette_colors += n


def bytes_per_tile(bits_per_tile: int) -> int:
    """Returns the stored size of one tilemap cell."""
    if bits_per_tile == 32:
        return 4
    if bits_per_tile == 16:
        return 2
    return 1
