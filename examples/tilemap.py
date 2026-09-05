# /// script
# requires-python = ">=3.12"
# dependencies = ["aseprite"]
#
# [tool.uv.sources]
# aseprite = { path = ".." }
# ///
"""Build a tilemap from an embedded tileset, including flipped tiles.

Run with ``uv run examples/tilemap.py [output.aseprite]``.
Uses the package in the parent directory; remove the ``[tool.uv.sources]``
table to use a published install.
"""

from __future__ import annotations

import sys
from pathlib import Path

from aseprite import LayerType, Sprite, Tilemap


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    output = Path(args[0]) if args else Path("tilemap.aseprite")

    tile_size = 8
    columns, rows = 4, 3
    sprite = Sprite(columns * tile_size, rows * tile_size, empty=True)

    # Tiles are stacked vertically. Tile 0 stays transparent for Aseprite.
    pixels = sprite.blank_pixels(tile_size, tile_size * 3)
    for y in range(tile_size):
        for x in range(tile_size):
            pixels[x, tile_size + y] = (55, 135, 80) if y < 2 else (100, 65, 45)
            if x <= y:
                pixels[x, 2 * tile_size + y] = (245, 175, 65)
    tileset = sprite.add_tileset("terrain", tile_size, tile_size, 3, pixels=pixels)
    layer = sprite.add_layer("map", kind=LayerType.TILEMAP, tileset_index=tileset.id)

    # Each cell is a little-endian 32-bit tile ID plus optional flip flags.
    x_flip, y_flip, d_flip = 0x20000000, 0x40000000, 0x80000000
    cells = (
        2,
        2 | x_flip,
        2 | y_flip,
        2 | d_flip,
        0,
        2,
        2 | x_flip,
        0,
        1,
        1,
        1,
        1,
    )
    tilemap = Tilemap(
        width=columns,
        height=rows,
        bits_per_tile=32,
        tile_id_mask=0x1FFFFFFF,
        x_flip_mask=x_flip,
        y_flip_mask=y_flip,
        d_flip_mask=d_flip,
        tiles=b"".join(cell.to_bytes(4, "little") for cell in cells),
    )
    sprite.add_frame().set_tilemap_cel(layer, tilemap)
    sprite.save(output)
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
