import pytest

from aseprite import (
    Color,
    ColorMode,
    LayerType,
    Palette,
    Pixels,
    Sprite,
    Tilemap,
    Tileset,
)
from aseprite._limits import MAX_GROUP_DEPTH, MAX_PIXELS
from tests.helpers import rgba_sprite


def test_flatten_single_cel() -> None:
    sprite = rgba_sprite(2, 2, color=b"\x10\x20\x30\xff")
    data = sprite.flatten(0)
    assert len(data) == 16
    assert data[0:4] == b"\x10\x20\x30\xff"


def test_flatten_hidden_layer_skipped() -> None:
    sprite = rgba_sprite(1, 1, color=b"\xff\x00\x00\xff")
    sprite.layers[0].visible = False
    data = sprite.flatten(0)
    assert data == b"\x00\x00\x00\x00"


def test_flatten_linked_cel() -> None:
    sprite = Sprite(1, 1, ColorMode.RGBA, empty=True)
    layer = sprite.add_layer("L")
    sprite.add_frame(100).set_cel(
        layer, Pixels(1, 1, b"\x01\x02\x03\xff", ColorMode.RGBA)
    )
    sprite.add_frame(100).set_linked_cel(layer, 0)
    assert sprite.flatten(1) == b"\x01\x02\x03\xff"


def test_flatten_indexed_transparent() -> None:
    sprite = Sprite(2, 1, ColorMode.INDEXED)
    sprite.palette = Palette([Color(255, 0, 0), Color(0, 255, 0)])
    sprite.transparent_index = 0
    sprite.frames[0].set_cel(
        sprite.layers[0], Pixels(2, 1, b"\x00\x01", ColorMode.INDEXED)
    )
    data = sprite.flatten(0)
    assert data[0:4] == b"\x00\x00\x00\x00"
    assert data[4:8] == b"\x00\xff\x00\xff"


def test_flatten_opacity() -> None:
    sprite = Sprite(1, 1, ColorMode.RGBA)
    sprite.layers[0].opacity = 128
    sprite.frames[0].set_cel(
        sprite.layers[0],
        Pixels(1, 1, b"\xff\x00\x00\xff", ColorMode.RGBA),
        opacity=128,
    )
    data = sprite.flatten(0)
    assert data[3] < 255
    assert data[0] > 0


def test_image_extra() -> None:
    sprite = rgba_sprite(1, 1)
    image = sprite.image(0)
    assert image.size == (1, 1)
    assert image.mode == "RGBA"


def test_flatten_rejects_huge_canvas() -> None:
    sprite = Sprite(8193, 8193)
    with pytest.raises(ValueError, match="canvas exceeds"):
        sprite.flatten(0)
    assert 8193 * 8193 > MAX_PIXELS


def test_flatten_rejects_huge_tilemap() -> None:
    sprite = Sprite(8, 8, empty=True)
    sprite.tilesets.append(
        Tileset(id=0, name="t", tile_count=1, tile_width=256, tile_height=256)
    )
    layer = sprite.add_layer("map", kind=LayerType.TILEMAP, tileset_index=0)
    sprite.add_frame(100).set_tilemap_cel(
        layer,
        Tilemap(
            width=256,
            height=256,
            bits_per_tile=32,
            tile_id_mask=0x1FFFFFFF,
            x_flip_mask=0x20000000,
            y_flip_mask=0x40000000,
            d_flip_mask=0x80000000,
            tiles=b"",
        ),
    )
    with pytest.raises(ValueError, match="tilemap exceeds"):
        sprite.flatten(0)


def test_flatten_rejects_deep_groups() -> None:
    sprite = Sprite(1, 1, empty=True)
    parent = None
    for i in range(MAX_GROUP_DEPTH + 2):
        parent = sprite.add_layer(f"g{i}", parent=parent, kind=LayerType.GROUP)
    sprite.add_layer("leaf", parent=parent)
    sprite.add_frame()
    with pytest.raises(ValueError, match="nesting"):
        sprite.flatten(0)
