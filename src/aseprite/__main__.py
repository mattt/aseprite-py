"""Inspect and export sprites from the command line.

Use ``python -m aseprite``.
This module does not register a console script named ``aseprite``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aseprite import Sprite
from aseprite._errors import AsepriteError


def main(argv: list[str] | None = None) -> int:
    """Runs the command-line interface.

    Args:
        argv: Argument vector without the program name.
            ``None`` uses ``sys.argv[1:]``.

    Returns:
        A process exit status.
    """
    parser = argparse.ArgumentParser(
        prog="python -m aseprite",
        description="Inspect and export Aseprite documents.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    info = sub.add_parser("info", help="print sprite metadata")
    info.add_argument("path", type=Path)

    export = sub.add_parser("export", help="write a flattened frame as PNG")
    export.add_argument("path", type=Path)
    export.add_argument("output", type=Path)
    export.add_argument("--frame", type=int, default=0)

    args = parser.parse_args(argv)
    try:
        sprite = Sprite.open(args.path)
    except (AsepriteError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.command == "info":
        _print_info(sprite, args.path)
        return 0

    try:
        image = sprite.image(args.frame)
    except (AsepriteError, ImportError, IndexError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    image.save(args.output)
    return 0


def _print_info(sprite: Sprite, path: Path) -> None:
    print(f"{path}")
    print(f"size: {sprite.width}x{sprite.height}")
    print(f"color_mode: {sprite.color_mode.name}")
    print(f"frames: {len(sprite.frames)}")
    print(f"layers: {len(sprite.layers)}")
    for layer in sprite.layers:
        indent = "  " * (layer.child_level + 1)
        print(f"{indent}{layer.name} ({layer.kind.name})")
    print(f"tags: {len(sprite.tags)}")
    for tag in sprite.tags:
        print(f"  {tag.name} {tag.from_frame}-{tag.to_frame}")
    print(f"slices: {len(sprite.slices)}")
    for sl in sprite.slices:
        print(f"  {sl.name}")


if __name__ == "__main__":
    raise SystemExit(main())
