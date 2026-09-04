# aseprite

[![CI][ci badge]][ci]
[![License][license badge]][license]

A Python library for reading and writing
[Aseprite][aseprite] `.ase` / `.aseprite` files.
It implements the
[Aseprite file format specification][spec].

> [!IMPORTANT]
> This project is unofficial and is not affiliated with Igara Studio.
> It does not include, download, or require the Aseprite application.

## Features

- [x] Read and write `.ase` / `.aseprite` documents
- [x] RGBA, grayscale, and indexed color modes
- [x] Layers, groups, and tilemaps
- [x] Animation tags, slices (nine-patch and pivot), and palettes
- [x] User data with typed properties
- [x] Tilesets, linked cels, color profiles, and external file references
- [x] Flatten a frame to RGBA8
  (visibility, opacity, groups, z-index, linked cels, Normal blend)
- [x] Optional Pillow extra for PNG export

This library specifically **does not**:

- Run the Aseprite application
- Execute Lua scripts
- Wrap the Aseprite CLI

Those belong to Aseprite itself and to
[aseprite-mcp][aseprite-mcp].

## Requirements

- Python 3.12 or later

## Installation

```sh
uv add aseprite
```

Or with pip:

```sh
pip install aseprite
```

For Pillow image export:

```sh
uv add "aseprite[image]"
```

## Usage

`Sprite.open` reads a `.ase` or `.aseprite` file.
`Sprite.from_bytes` reads the same data from memory.
Both raise `FormatError` if the bytes are not a valid document.

```python
from pathlib import Path

from aseprite import Sprite

sprite = Sprite.open("hero.aseprite")
print(sprite.size, sprite.color_mode)
print(len(sprite.frames), "frames")
print(len(sprite.layers), "layers")

data = Path("hero.aseprite").read_bytes()
same = Sprite.from_bytes(data)
```

`open` and `save` also accept a binary file object.

```python
from io import BytesIO

buf = BytesIO()
sprite.save(buf)
buf.seek(0)
copy = Sprite.open(buf)
```

### Layers, tags, and slices

Layers, tags, slices, and tilesets support lookup by index or name.
`"idle" in sprite.tags` is true when a tag with that name exists.
`get` returns `None` when the name is missing.

```python
idle = sprite.tags["idle"]
print(idle.from_frame, idle.to_frame, idle.direction)

if "outline" in sprite.layers:
    outline = sprite.layers["outline"]
    print(outline.name, outline.kind, outline.visible)

box = sprite.slices.get("box")
if box is not None:
    key = box.keys[0]
    print(key.x, key.y, key.width, key.height)
```

Group layers stay in file order.
`layers.children(group)` returns the direct children.

```python
from aseprite import LayerType

for layer in sprite.layers:
    indent = "  " * layer.child_level
    print(f"{indent}{layer.name} ({layer.kind.name})")

body = sprite.layers.get("body")
if body is not None and body.kind is LayerType.GROUP:
    for child in sprite.layers.children(body):
        print(child.name)
```

### Cels and pixels

`frame[layer]` returns the cel on that layer, or raises `KeyError`.
`frame.cel(layer)` returns `None` when the cel is missing.
RGBA and grayscale pixels are `Color` values.
Indexed pixels are palette indices.

```python
layer = sprite.layers[0]
cel = sprite.frames[0].cel(layer)
if cel is not None and cel.pixels is not None:
    print(cel.x, cel.y, cel.pixels[0, 0])
```

`flatten` composites one frame to `width * height * 4` bytes of RGBA.
Hidden layers are skipped.
Linked cels are resolved.
Only the Normal blend mode is applied.
A frame index outside the document raises `IndexError`.

`image` returns a Pillow `Image` in RGBA mode.
It requires the `aseprite[image]` extra.

```python
rgba = sprite.flatten(frame=0)
image = sprite.image(frame=0)
image.save("hero.png")
```

[examples/export_png.py](examples/export_png.py) is a
[PEP 723](https://peps.python.org/pep-0723/) script.
`uv run` installs `aseprite[image]` for that process and writes a PNG.

```sh
uv run examples/export_png.py
uv run examples/export_png.py out.png
```

### Create a sprite

`Sprite(width, height)` uses RGBA and adds one layer named `Layer 1`
and one frame of 100 ms.
Pass `empty=True` if you do not want those defaults.
`to_bytes` and `save` raise `ValueError` when there are no frames.

```python
from aseprite import ColorMode, Sprite

sprite = Sprite(32, 32, ColorMode.RGBA)
layer = sprite.layers[0]
pixels = sprite.blank_pixels()
pixels[0, 0] = (255, 0, 0, 255)
pixels[1, 0] = (0, 255, 0)
sprite.frames[0][layer] = pixels
sprite.add_tag("idle", 0, 0)
sprite.save("hero.aseprite")
```

`add_frame` appends a frame.
`set_linked_cel` points a later frame at an earlier one on the same layer.

```python
from aseprite import LoopDirection

walk = sprite.add_frame(duration_ms=80)
walk.set_linked_cel(layer, 0)
sprite.add_tag("walk", 0, 1, direction=LoopDirection.FORWARD, repeat=0)
```

`add_layer` can nest a layer under a group.

```python
from aseprite import LayerType

group = sprite.add_layer("body", kind=LayerType.GROUP)
sprite.add_layer("outline", parent=group)
```

### Indexed color

An indexed sprite stores a palette.
`transparent_index` selects the index that `flatten` treats as transparent
on non-background layers.

```python
from aseprite import Color, ColorMode, Sprite

sprite = Sprite(16, 16, ColorMode.INDEXED)
sprite.palette.append(Color(0, 0, 0, 0))
sprite.palette.append(Color(255, 80, 40))
sprite.transparent_index = 0

pixels = sprite.blank_pixels()
pixels[2, 3] = 1
sprite.frames[0][sprite.layers[0]] = pixels
```

### Slices and user data

A slice is a named rectangle.
Keys may include a nine-patch center and a pivot.

```python
from aseprite import NinePatch, SliceKey

sprite.add_slice(
    "box",
    [
        SliceKey(
            frame=0,
            x=2,
            y=2,
            width=12,
            height=12,
            nine_patch=NinePatch(1, 1, 10, 10),
            pivot=(6, 6),
        )
    ],
)
```

User data can hold text, a color, and typed properties.

```python
from aseprite import Color, PropertiesMap, PropertyType, UserData, UserProperty

sprite.layers[0].user_data = UserData(
    text="npc",
    color=Color(255, 0, 0),
    properties=[
        PropertiesMap(0, [UserProperty("hp", PropertyType.INT32, 10)]),
    ],
)
```

### Command line

There is no `aseprite` console script.
That name belongs to the editor.

```sh
python -m aseprite info hero.aseprite
python -m aseprite export hero.aseprite hero.png --frame 0
```

`export` needs the `aseprite[image]` extra.

## Limits

These caps bound memory use when you open or flatten a file.

- A palette may have at most 65,535 colors.
- Uncompressed cel and tileset pixels in one document may total at most 256 MiB.
- `flatten()`, `image()`, and `python -m aseprite export` accept at most 67,108,864 pixels (8192×8192).

`python -m aseprite info` still prints metadata when the canvas is larger than that pixel cap.

## Development

```sh
uv sync --all-extras --dev
uv run ruff format
uv run ruff check
uv run ty check
uv run pytest
```

The default test suite does not need the Aseprite application.

## License

aseprite is available under the Apache 2.0 license.
See the [LICENSE](LICENSE) file for more info.
Aseprite is separate software under its own license.

## Contact

Mattt ([@mattt](https://twitter.com/mattt))

[ci]: https://github.com/mattt/aseprite-py/actions
[ci badge]: https://github.com/mattt/aseprite-py/workflows/CI/badge.svg
[license]: https://www.apache.org/licenses/LICENSE-2.0
[license badge]: https://img.shields.io/badge/license-Apache%202.0-blue.svg?style=flat
[aseprite]: https://www.aseprite.org
[spec]: https://github.com/aseprite/aseprite/blob/main/docs/ase-file-specs.md
[aseprite-mcp]: https://github.com/mattt/aseprite-mcp
