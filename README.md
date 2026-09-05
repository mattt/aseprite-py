# aseprite

[![CI][ci badge]][ci]
[![License][license badge]][license]

A Python library for reading and writing [Aseprite][aseprite]
`.ase` / `.aseprite` files, based on the [file format specification][spec].

This project is unofficial and is not affiliated with Igara Studio.
It works directly with files and does not require the Aseprite application.

- RGBA, grayscale, and indexed color
- Layers, groups, tilemaps, tilesets, and linked cels
- Animation tags, palettes, and slices with nine-patch centers and pivots
- Color profiles, external file references, and typed user data
- Frame rendering with Normal blending and optional PNG export

## Installation

Requires Python 3.12 or later.

```sh
uv add aseprite
```

Or with pip:

```sh
pip install aseprite
```

Include the Pillow extra for image export:

```sh
uv add "aseprite[image]"
```

## Open and export a sprite

```python
from aseprite import Sprite

sprite = Sprite.open("hero.aseprite")
print(sprite.size, sprite.color_mode)
print(len(sprite.frames), "frames")
print([layer.name for layer in sprite.layers])

sprite.image(frame=0).save("hero.png")
```

`image()` returns a Pillow image. Use `flatten()` for raw RGBA bytes.
Rendering supports Normal blending; use Aseprite to export other blend modes.

`Sprite.from_bytes(data)` reads from memory. `open()` and `save()` also accept
binary file objects:

```python
from io import BytesIO

buf = BytesIO()
sprite.save(buf)
buf.seek(0)
copy = Sprite.open(buf)
```

## Create and animate

A new sprite starts with one layer and one frame.

```python
from aseprite import Sprite

sprite = Sprite(32, 32)
layer = sprite.layers[0]
pixels = sprite.blank_pixels()
pixels[0, 0] = (255, 0, 0, 255)
pixels[1, 0] = (0, 255, 0)
sprite.frames[0][layer] = pixels

walk = sprite.add_frame(duration_ms=80)
walk.set_linked_cel(layer, source_frame=0)
sprite.add_tag("walk", 0, 1)
sprite.save("hero.aseprite")
```

Nest layers by passing a group as the parent:

```python
from aseprite import LayerType

group = sprite.add_layer("body", kind=LayerType.GROUP)
sprite.add_layer("outline", parent=group)

for child in sprite.layers.children(group):
    print(child.name)
```

## Inspect layers and metadata

Layers, tags, slices, and tilesets support lookup by index or name.
Use `get()` for an optional lookup.

```python
idle = sprite.tags.get("idle")
if idle is not None:
    print(idle.from_frame, idle.to_frame, idle.direction)

if "outline" in sprite.layers:
    outline = sprite.layers["outline"]
    print(outline.visible, outline.opacity)

box = sprite.slices.get("box")
if box is not None:
    print(box.keys[0])
```

`frame.cel(layer)` returns the cel, or `None` if that layer has no cel.
RGBA and grayscale pixels are `Color` values; indexed pixels are integers.

```python
cel = sprite.frames[0].cel(sprite.layers[0])
if cel is not None and cel.pixels is not None:
    print(cel.x, cel.y, cel.pixels[0, 0])
```

## Indexed color

Populate the palette, then draw with palette indices:

```python
from aseprite import Color, ColorMode, Palette, Sprite

sprite = Sprite(16, 16, ColorMode.INDEXED)
sprite.palette = Palette([Color(0, 0, 0, 0), Color(255, 80, 40)])
sprite.transparent_index = 0

pixels = sprite.blank_pixels()
pixels[2, 3] = 1
sprite.frames[0][sprite.layers[0]] = pixels
```

To animate colors, assign a new `Palette` to `frame.palette`.
Use `sprite.palette_at(frame)` to get the palette effective at a frame.

## Slices and user data

Add named bounds for hitboxes, layout, or export regions:

```python
from aseprite import SliceKey

sprite.add_slice("hitbox", [SliceKey(frame=0, x=2, y=2, width=12, height=12)])
```

Attach text, colors, and typed properties to document objects:

```python
from aseprite import PropertiesMap, PropertyType, UserData, UserProperty

sprite.layers[0].user_data = UserData(
    text="npc",
    properties=[PropertiesMap(0, [UserProperty("hp", PropertyType.INT32, 10)])],
)
```

Detailed behavior, mutation rules, and allocation limits are documented on
the corresponding APIs. For example, use `help(Sprite.flatten)`,
`help(Sprite.from_bytes)`, or `help(type(sprite.layers))`.

## Examples

These scripts generate their own artwork and use the local package:

- [Export PNG](examples/export_png.py): draw pixels and export a frame.
- [Indexed animation](examples/indexed_animation.py): animate a palette with linked cels.
- [Tilemap](examples/tilemap.py): build an embedded tileset and place flipped tiles.

Run an example with `uv run`, optionally passing an output path:

```sh
uv run examples/indexed_animation.py flame.aseprite
```

## Command line

```sh
python -m aseprite info hero.aseprite
python -m aseprite export hero.aseprite hero.png --frame 0
```

`export` requires the `aseprite[image]` extra.

## Development

```sh
uv sync --all-extras --dev
uv run ruff format
uv run ruff check
uv run ty check
uv run pytest
```

The tests use [Hypothesis][hypothesis] for generated documents and include
regression cases for reading, writing, rendering, and editing.
Set `HYPOTHESIS_PROFILE=long` for an extended search.

Editor comparisons run when Aseprite is available. On macOS the suite looks
in `/Applications/Aseprite.app`; set `ASEPRITE_PATH` to use another binary.
The rest of the suite runs without the editor.


## License

aseprite is available under the [Apache 2.0 license](LICENSE).
Aseprite is separate software under its own license.

## Contact

Mattt ([@mattt](https://twitter.com/mattt))

[ci]: https://github.com/mattt/aseprite-py/actions/workflows/ci.yml
[ci badge]: https://github.com/mattt/aseprite-py/actions/workflows/ci.yml/badge.svg
[license badge]: https://img.shields.io/badge/license-Apache%202.0-blue.svg?style=flat
[license]: https://www.apache.org/licenses/LICENSE-2.0
[aseprite]: https://www.aseprite.org
[spec]: https://github.com/aseprite/aseprite/blob/main/docs/ase-file-specs.md
[hypothesis]: https://hypothesis.readthedocs.io
