# /// script
# requires-python = ">=3.12"
# dependencies = ["aseprite"]
#
# [tool.uv.sources]
# aseprite = { path = ".." }
# ///
"""Animate a flame by changing its palette while reusing one cel.

Run with ``uv run examples/indexed_animation.py [output.aseprite]``.
Uses the package in the parent directory; remove the ``[tool.uv.sources]``
table to use a published install.
"""

from __future__ import annotations

import sys
from pathlib import Path

from aseprite import Color, ColorMode, Palette, Sprite


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    output = Path(args[0]) if args else Path("flame.aseprite")

    sprite = Sprite(8, 8, ColorMode.INDEXED)
    layer = sprite.layers[0]
    layer.name = "flame"
    sprite.transparent_index = 0
    transparent = Color(0, 0, 0, 0)
    sprite.palette = Palette(
        [transparent, Color(235, 65, 35), Color(255, 165, 40), Color(255, 240, 130)]
    )

    # Each character is a palette index; 0 leaves the canvas transparent.
    rows = (
        "00010000",
        "00011000",
        "00121000",
        "01122100",
        "01232110",
        "01233210",
        "00122100",
        "00011000",
    )
    pixels = sprite.blank_pixels()
    for y, row in enumerate(rows):
        for x, index in enumerate(row):
            pixels[x, y] = int(index)
    sprite.frames[0].duration_ms = 120
    sprite.frames[0][layer] = pixels

    for colors in (
        [(255, 95, 30), (255, 200, 55), (255, 250, 185)],
        [(200, 40, 40), (245, 125, 30), (255, 215, 90)],
    ):
        frame = sprite.add_frame(duration_ms=120)
        frame.set_linked_cel(layer, source_frame=0)
        # A new palette changes this frame onward without changing frame 0.
        frame.palette = Palette([transparent, *(Color(*rgb) for rgb in colors)])

    sprite.add_tag("flicker", 0, len(sprite.frames) - 1)
    sprite.save(output)
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
