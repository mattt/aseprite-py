import pytest

from aseprite import (
    BlendMode,
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
from aseprite._model import TILESET_FLAG_EMBEDDED
from tests.helpers import (
    TILE_BL,
    TILE_BR,
    TILE_PIXELS,
    TILE_TL,
    TILE_TR,
    rgba_sprite,
    tilemap_sprite,
)


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


def test_flatten_rejects_isolated_group_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("aseprite._render.MAX_UNCOMPRESSED_BYTES", 8)
    sprite = Sprite(2, 2, empty=True)
    sprite.group_blend = True
    group = sprite.add_layer("g", kind=LayerType.GROUP)
    sprite.add_layer("c", parent=group)
    sprite.add_frame()
    with pytest.raises(ValueError, match="isolated"):
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


def test_flatten_tilemap() -> None:
    assert tilemap_sprite().flatten(0) == TILE_PIXELS


def test_flatten_tilemap_x_flip() -> None:
    assert (
        tilemap_sprite(x_flip=True).flatten(0) == TILE_TR + TILE_TL + TILE_BR + TILE_BL
    )


def test_flatten_tilemap_y_flip() -> None:
    assert (
        tilemap_sprite(y_flip=True).flatten(0) == TILE_BL + TILE_BR + TILE_TL + TILE_TR
    )


def test_flatten_tilemap_d_flip() -> None:
    assert (
        tilemap_sprite(d_flip=True).flatten(0) == TILE_TL + TILE_BL + TILE_TR + TILE_BR
    )


def test_flatten_tilemap_d_flip_nonsquare() -> None:
    sprite = Sprite(2, 2, ColorMode.RGBA, empty=True)
    sprite.tilesets.append(
        Tileset(
            id=0,
            name="t",
            tile_count=1,
            tile_width=2,
            tile_height=1,
            flags=TILESET_FLAG_EMBEDDED,
            pixels=Pixels(2, 1, TILE_TL + TILE_TR, ColorMode.RGBA),
        )
    )
    layer = sprite.add_layer("map", kind=LayerType.TILEMAP, tileset_index=0)
    sprite.add_frame(100).set_tilemap_cel(
        layer,
        Tilemap(
            width=1,
            height=1,
            bits_per_tile=32,
            tile_id_mask=0x1FFFFFFF,
            x_flip_mask=0x20000000,
            y_flip_mask=0x40000000,
            d_flip_mask=0x80000000,
            tiles=(0x80000000).to_bytes(4, "little"),
        ),
    )
    data = sprite.flatten(0)
    assert data[0:4] == TILE_TL
    assert data[4:8] == b"\x00\x00\x00\x00"
    assert data[8:12] == TILE_TR
    assert data[12:16] == b"\x00\x00\x00\x00"


def test_flatten_tilemap_16bit_and_empty_is_zero() -> None:
    assert tilemap_sprite(bits_per_tile=16).flatten(0) == TILE_PIXELS
    assert tilemap_sprite(empty_is_zero=True).flatten(0) == b"\x00" * 16


def test_flatten_grayscale() -> None:
    sprite = Sprite(1, 1, ColorMode.GRAYSCALE)
    sprite.frames[0].set_cel(
        sprite.layers[0], Pixels(1, 1, b"\x10\xff", ColorMode.GRAYSCALE)
    )
    assert sprite.flatten(0) == b"\x10\x10\x10\xff"


def test_flatten_group_blend_isolates_opacity() -> None:
    sprite = Sprite(1, 1, ColorMode.RGBA, empty=True)
    group = sprite.add_layer("g", kind=LayerType.GROUP, opacity=128)
    child = sprite.add_layer("c", parent=group)
    sprite.add_frame(100).set_cel(
        child, Pixels(1, 1, b"\xff\x00\x00\xff", ColorMode.RGBA)
    )
    sprite.group_blend = False
    assert sprite.flatten(0) == b"\xff\x00\x00\xff"
    sprite.group_blend = True
    isolated = sprite.flatten(0)
    assert isolated[0:3] == b"\xff\x00\x00"
    assert isolated[3] == 128


def _layer_and_group(group_first: bool) -> Sprite:
    sprite = Sprite(1, 1, ColorMode.RGBA, empty=True)
    if group_first:
        group = sprite.add_layer("g", kind=LayerType.GROUP)
        child = sprite.add_layer("c", parent=group)
        plain = sprite.add_layer("plain")
    else:
        plain = sprite.add_layer("plain")
        group = sprite.add_layer("g", kind=LayerType.GROUP)
        child = sprite.add_layer("c", parent=group)
    frame = sprite.add_frame(100)
    frame.set_cel(plain, Pixels(1, 1, b"\xff\x00\x00\xff", ColorMode.RGBA))
    frame.set_cel(child, Pixels(1, 1, b"\x00\xff\x00\xff", ColorMode.RGBA))
    return sprite


@pytest.mark.parametrize("isolate", [False, True])
def test_flatten_group_above_layer_paints_on_top(isolate: bool) -> None:
    sprite = _layer_and_group(group_first=False)
    sprite.group_blend = isolate
    assert sprite.flatten(0) == b"\x00\xff\x00\xff"


@pytest.mark.parametrize("isolate", [False, True])
def test_flatten_group_below_layer_is_covered(isolate: bool) -> None:
    sprite = _layer_and_group(group_first=True)
    sprite.group_blend = isolate
    assert sprite.flatten(0) == b"\xff\x00\x00\xff"


def test_flatten_cel_offset_and_clip() -> None:

    sprite = Sprite(2, 2, ColorMode.RGBA, empty=True)
    layer = sprite.add_layer("L")
    sprite.add_frame(100).set_cel(
        layer, Pixels(1, 1, b"\xff\x00\x00\xff", ColorMode.RGBA), x=1, y=1
    )
    data = sprite.flatten(0)
    assert data[0:12] == b"\x00" * 12
    assert data[12:16] == b"\xff\x00\x00\xff"

    clipped = Sprite(2, 2, ColorMode.RGBA, empty=True)
    clayer = clipped.add_layer("L")
    clipped.add_frame(100).set_cel(
        clayer,
        Pixels(
            2,
            2,
            b"\x01\x00\x00\xff\x02\x00\x00\xff\x03\x00\x00\xff\x04\x00\x00\xff",
            ColorMode.RGBA,
        ),
        x=-1,
        y=-1,
    )
    assert clipped.flatten(0)[0:4] == b"\x04\x00\x00\xff"
    assert clipped.flatten(0)[4:] == b"\x00" * 12


def test_flatten_z_index() -> None:
    sprite = Sprite(1, 1, ColorMode.RGBA, empty=True)
    bottom = sprite.add_layer("bottom")
    top = sprite.add_layer("top")
    frame = sprite.add_frame(100)
    frame.set_cel(bottom, Pixels(1, 1, b"\xff\x00\x00\xff", ColorMode.RGBA), z_index=1)
    frame.set_cel(top, Pixels(1, 1, b"\x00\xff\x00\xff", ColorMode.RGBA), z_index=0)
    assert sprite.flatten(0) == b"\xff\x00\x00\xff"


def test_flatten_linked_chain_and_cycle() -> None:
    sprite = Sprite(1, 1, ColorMode.RGBA, empty=True)
    layer = sprite.add_layer("L")
    sprite.add_frame(100).set_cel(
        layer, Pixels(1, 1, b"\x01\x02\x03\xff", ColorMode.RGBA)
    )
    sprite.add_frame(100).set_linked_cel(layer, 0)
    sprite.add_frame(100).set_linked_cel(layer, 1)
    assert sprite.flatten(2) == b"\x01\x02\x03\xff"

    cycle = Sprite(1, 1, ColorMode.RGBA, empty=True)
    clayer = cycle.add_layer("L")
    cycle.add_frame(100).set_linked_cel(clayer, 1)
    cycle.add_frame(100).set_linked_cel(clayer, 0)
    assert cycle.flatten(0) == b"\x00\x00\x00\x00"


def test_flatten_indexed_background_keeps_transparent_index() -> None:
    sprite = Sprite(1, 1, ColorMode.INDEXED)
    sprite.palette = Palette([Color(255, 0, 0), Color(0, 255, 0)])
    sprite.transparent_index = 0
    sprite.layers[0].background = True
    sprite.frames[0].set_cel(sprite.layers[0], Pixels(1, 1, b"\x00", ColorMode.INDEXED))
    assert sprite.flatten(0) == b"\xff\x00\x00\xff"


def test_flatten_indexed_out_of_range_is_transparent() -> None:
    sprite = Sprite(1, 1, ColorMode.INDEXED)
    sprite.palette = Palette([Color(255, 0, 0)])
    sprite.frames[0].set_cel(sprite.layers[0], Pixels(1, 1, b"\x05", ColorMode.INDEXED))
    assert sprite.flatten(0) == b"\x00\x00\x00\x00"


def test_flatten_non_normal_blend_uses_normal() -> None:
    sprite = Sprite(1, 1, ColorMode.RGBA, empty=True)
    bottom = sprite.add_layer("b")
    top = sprite.add_layer("t", blend_mode=BlendMode.MULTIPLY)
    frame = sprite.add_frame(100)
    frame.set_cel(bottom, Pixels(1, 1, b"\x00\x00\xff\xff", ColorMode.RGBA))
    frame.set_cel(top, Pixels(1, 1, b"\xff\x00\x00\xff", ColorMode.RGBA))
    assert sprite.flatten(0) == b"\xff\x00\x00\xff"
