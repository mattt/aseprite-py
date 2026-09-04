from io import BytesIO

import pytest

from aseprite import (
    Color,
    ColorMode,
    HeaderFlags,
    Layer,
    LayerType,
    NinePatch,
    Palette,
    Pixels,
    SliceKey,
    Sprite,
    __version__,
)


def test_constructor_is_saveable() -> None:
    sprite = Sprite(4, 4)
    assert sprite.size == (4, 4)
    assert len(sprite.layers) == 1
    assert sprite.layers[0].name == "Layer 1"
    assert len(sprite.frames) == 1
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.size == (4, 4)
    assert loaded.layers[0].name == "Layer 1"


def test_empty_sprite_cannot_save() -> None:
    sprite = Sprite(4, 4, empty=True)
    with pytest.raises(ValueError, match="at least one frame"):
        sprite.to_bytes()


def test_repr_and_version() -> None:
    sprite = Sprite(2, 3)
    assert repr(sprite) == (
        "Sprite(width=2, height=3, color_mode=RGBA, frames=1, layers=1)"
    )
    assert isinstance(__version__, str)
    assert __version__


def test_named_collections() -> None:
    sprite = Sprite(2, 2)
    sprite.add_tag("idle", 0, 0)
    sprite.add_slice("box", [SliceKey(0, 0, 0, 2, 2)])
    sprite.add_tileset("tiles", 2, 2, 1)
    assert "idle" in sprite.tags
    assert sprite.tags.get("missing") is None
    assert sprite.tags.get("idle") is sprite.tags[0]
    assert sprite.layers[0:1][0].name == "Layer 1"
    assert "box" in sprite.slices
    assert sprite.slices["box"].keys[0].width == 2
    assert "tiles" in sprite.tilesets
    assert sprite.tilesets["tiles"].tile_width == 2


def test_layer_tree_and_reindex() -> None:
    sprite = Sprite(1, 1, empty=True)
    group = sprite.add_layer("group", kind=LayerType.GROUP)
    child = sprite.add_layer("child", parent=group)
    other = sprite.add_layer("other")
    assert sprite.layers.children(group) == [child]
    assert sprite.layers.descendants(group) == [child]
    assert other.index == 2
    del sprite.layers[1]
    assert other.index == 1
    assert "child" not in sprite.layers


def test_palette_mutation() -> None:
    palette = Palette()
    palette.append(Color(1, 2, 3))
    palette.extend([Color(4, 5, 6)])
    palette[0] = Color(9, 8, 7)
    assert list(palette) == [Color(9, 8, 7), Color(4, 5, 6)]


def test_frame_getitem_and_pixels() -> None:
    sprite = Sprite(2, 1)
    pixels = sprite.blank_pixels()
    pixels[0, 0] = (10, 20, 30, 255)
    pixels[1, 0] = Color(1, 2, 3, 4)
    layer = sprite.layers[0]
    sprite.frames[0][layer] = pixels
    stored = sprite.frames[0][layer].pixels
    assert stored is not None
    assert stored[0, 0] == Color(10, 20, 30, 255)
    pixel = stored[1, 0]
    assert isinstance(pixel, Color)
    assert tuple(pixel) == (1, 2, 3, 4)
    with pytest.raises(IndexError):
        pixels[9, 0]


def test_indexed_pixel_access() -> None:
    pixels = Pixels.blank(1, 1, ColorMode.INDEXED)
    pixels[0, 0] = 3
    assert pixels[0, 0] == 3


def test_file_like_io() -> None:
    sprite = Sprite(1, 1)
    sprite.frames[0][sprite.layers[0]] = sprite.blank_pixels()
    buf = BytesIO()
    sprite.save(buf)
    buf.seek(0)
    loaded = Sprite.open(buf)
    assert loaded.size == (1, 1)
    assert loaded.color_mode is ColorMode.RGBA


def test_flatten_out_of_range() -> None:
    sprite = Sprite(1, 1)
    with pytest.raises(IndexError, match="out of range"):
        sprite.flatten(3)


def test_bad_dimensions() -> None:
    with pytest.raises(ValueError, match="positive"):
        Sprite(0, 1)
    with pytest.raises(ValueError, match="65535"):
        Sprite(65_536, 1)


def test_write_rejects_out_of_range_fields() -> None:
    sprite = Sprite(1, 1)
    sprite.frames[0].duration_ms = 100_000
    with pytest.raises(ValueError, match="out of range"):
        sprite.to_bytes()
    sprite.frames[0].duration_ms = 100
    sprite.frames[0].set_cel(sprite.layers[0], sprite.blank_pixels(1, 1), x=40_000)
    with pytest.raises(ValueError, match="out of range"):
        sprite.to_bytes()


def test_delete_layer_drops_its_cel() -> None:
    sprite = Sprite(1, 1)
    first = sprite.layers[0]
    second = sprite.add_layer("B")
    sprite.frames[0][first] = Pixels(1, 1, b"\xff\x00\x00\xff", ColorMode.RGBA)
    sprite.frames[0][second] = Pixels(1, 1, b"\x00\xff\x00\xff", ColorMode.RGBA)
    del sprite.layers[0]
    assert sprite.layers[0] is second
    cel = sprite.frames[0].cel(second)
    assert cel is not None and cel.pixels is not None
    assert cel.pixels.data == b"\x00\xff\x00\xff"
    assert sprite.flatten(0) == b"\x00\xff\x00\xff"


def test_insert_layer_shifts_cels() -> None:
    sprite = Sprite(1, 1)
    layer = sprite.layers[0]
    sprite.frames[0][layer] = Pixels(1, 1, b"\xff\x00\x00\xff", ColorMode.RGBA)
    sprite.layers.insert(0, Layer("front"))
    assert layer.index == 1
    cel = sprite.frames[0].cel(layer)
    assert cel is not None and cel.pixels is not None
    assert bytes(cel.pixels.data) == b"\xff\x00\x00\xff"


def test_layer_opacity_flag_roundtrip() -> None:
    sprite = Sprite(1, 1)
    sprite.valid_layer_opacity = False
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.valid_layer_opacity is False


def test_new_indexed_sprite_omits_old_palette() -> None:
    sprite = Sprite(1, 1, ColorMode.INDEXED)
    sprite.palette.append(Color(1, 2, 3))
    from aseprite._binary import FRAME_HEADER_SIZE, HEADER_SIZE, Reader

    data = sprite.to_bytes()
    r = Reader(data, HEADER_SIZE)
    r.skip(FRAME_HEADER_SIZE - 4)
    nchunks = r.u32()
    types = []
    for _ in range(nchunks):
        size = r.u32()
        types.append(r.u16())
        r.skip(size - 6)
    assert 0x0004 not in types


def test_header_flags() -> None:
    sprite = Sprite(1, 1)
    assert sprite.valid_layer_opacity is True
    assert sprite.group_blend is False
    sprite.group_blend = True
    assert sprite.flags & HeaderFlags.GROUP_BLEND
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.group_blend is True


def test_add_slice_nine_patch() -> None:
    sprite = Sprite(4, 4)
    sprite.add_slice(
        "box",
        [SliceKey(0, 0, 0, 4, 4, nine_patch=NinePatch(1, 1, 2, 2))],
    )
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.slices["box"].keys[0].nine_patch == NinePatch(1, 1, 2, 2)
