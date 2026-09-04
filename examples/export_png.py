# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "aseprite[image]",
# ]
#
# [tool.uv.sources]
# aseprite = { path = ".." }
# ///
"""Create a sprite and write frame 0 as a PNG.

Uses the package in the parent directory.
To run against a published install, remove the ``[tool.uv.sources]`` table.
"""

from __future__ import annotations

import sys
from pathlib import Path

from aseprite import Sprite


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    output = Path(args[0]) if args else Path("hero.png")

    sprite = Sprite(16, 16)
    pixels = sprite.blank_pixels()
    for x in range(16):
        pixels[x, x] = (255, 80, 40)
        pixels[15 - x, x] = (40, 120, 255)
    sprite.frames[0][sprite.layers[0]] = pixels

    sprite.image(0).save(output)
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
