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

### Open and inspect a file

```python
from aseprite import Sprite

sprite = Sprite.open("hero.aseprite")
print(sprite.width, sprite.height, sprite.color_mode)
print(len(sprite.frames), "frames")

idle = sprite.tags["idle"]
print(idle.from_frame, idle.to_frame)

for layer in sprite.layers:
    print(layer.name, layer.type)
```

### Flatten a frame

```python
from aseprite import Sprite

sprite = Sprite.open("hero.aseprite")
rgba = sprite.flatten(frame=0)  # width * height * 4 bytes

# Requires aseprite[image]
image = sprite.image(frame=0)
image.save("hero.png")
```

### Create a sprite

```python
from aseprite import ColorMode, Pixels, Sprite

sprite = Sprite(32, 32, ColorMode.RGBA)
layer = sprite.add_layer("Layer 1")
frame = sprite.add_frame(duration_ms=100)
pixels = Pixels.blank(32, 32, ColorMode.RGBA)
frame.set_cel(layer, pixels, x=0, y=0)
sprite.add_tag("idle", 0, 0)
sprite.save("hero.aseprite")
```

### Command line

There is no `aseprite` console script.
That name belongs to the editor.

```sh
python -m aseprite info hero.aseprite
python -m aseprite export hero.aseprite hero.png --frame 0
```

## Limits

These caps bound memory use when you open or flatten a file.

- A palette may have at most 65,536 colors.
- Cel and tileset zlib data may expand to at most 256 MiB.
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

The default test suite does not need Aseprite installed.
When `ASEPRITE_PATH` is set and mall-game art is present,
pytest also compares `flatten()` to `aseprite -b --save-as`.

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
