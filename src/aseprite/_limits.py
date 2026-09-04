"""Caps that stop untrusted files from allocating unbounded memory."""

# 256 MiB of RGBA, or an 8192×8192 canvas.
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_PIXELS = MAX_UNCOMPRESSED_BYTES // 4
MAX_PALETTE_COLORS = 65_536


def bytes_per_tile(bits_per_tile: int) -> int:
    """Returns the stored size of one tilemap cell."""
    if bits_per_tile == 32:
        return 4
    if bits_per_tile == 16:
        return 2
    return 1
