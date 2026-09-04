from io import BytesIO
from typing import Any
from uuid import UUID

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
    Tileset,
    UserData,
    __version__,
)
from aseprite._model import TILESET_FLAG_EMBEDDED


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
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.tilesets["tiles"].tile_width == 2
    assert loaded.tilesets["tiles"].pixels is None
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


def test_grayscale_pixel_access() -> None:
    pixels = Pixels.blank(1, 1, ColorMode.GRAYSCALE)
    pixels[0, 0] = (16, 255)
    assert pixels[0, 0] == Color(16, 16, 16, 255)
    pixels[0, 0] = Color(8, 0, 0, 128)
    assert pixels[0, 0] == Color(8, 8, 8, 128)


def test_pixels_type_errors() -> None:
    pixels = Pixels.blank(1, 1, ColorMode.RGBA)
    bad_key: Any = 0
    with pytest.raises(TypeError, match="pixel index"):
        pixels[bad_key]
    with pytest.raises(TypeError, match="RGBA pixel"):
        pixels[0, 0] = 3
    gray = Pixels.blank(1, 1, ColorMode.GRAYSCALE)
    with pytest.raises(TypeError, match="grayscale"):
        gray[0, 0] = 3
    indexed = Pixels.blank(1, 1, ColorMode.INDEXED)
    bad_value: Any = None
    with pytest.raises(TypeError, match="indexed"):
        indexed[0, 0] = bad_value


def test_pixels_buffer() -> None:
    pixels = Pixels.blank(1, 1, ColorMode.RGBA)
    view = memoryview(pixels)
    assert bytes(view) == bytes(pixels.data)


def test_pixels_setitem_mutates_in_place() -> None:
    pixels = Pixels.blank(2, 1, ColorMode.RGBA)
    pixels[0, 0] = (1, 2, 3, 4)
    buf = pixels.data
    assert isinstance(buf, bytearray)
    pixels[1, 0] = (5, 6, 7, 8)
    assert pixels.data is buf


def test_pixels_validation() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        Pixels(-1, 1, b"", ColorMode.RGBA)
    with pytest.raises(ValueError, match="does not match"):
        Pixels(1, 1, b"\x00", ColorMode.RGBA)


def test_blank_pixels_custom_size() -> None:
    sprite = Sprite(4, 4)
    pixels = sprite.blank_pixels(3, 2)
    assert pixels.width == 3
    assert pixels.height == 2
    assert pixels.color_mode is ColorMode.RGBA


def test_replace_layer_drops_cel() -> None:
    sprite = Sprite(1, 1)
    sprite.frames[0][sprite.layers[0]] = Pixels(
        1, 1, b"\xff\x00\x00\xff", ColorMode.RGBA
    )
    sprite.layers[0] = Layer("new")
    assert sprite.frames[0].cel(0) is None


def test_color_mode_bytes_per_pixel() -> None:
    assert ColorMode.RGBA.bytes_per_pixel == 4
    assert ColorMode.GRAYSCALE.bytes_per_pixel == 2
    assert ColorMode.INDEXED.bytes_per_pixel == 1


def test_user_data_bool() -> None:
    assert not UserData()
    assert UserData(text="")
    assert UserData(color=Color(0, 0, 0))


def test_named_list_missing_name() -> None:
    sprite = Sprite(1, 1)
    with pytest.raises(KeyError, match="missing"):
        sprite.layers["missing"]


def test_frame_missing_cel() -> None:
    sprite = Sprite(1, 1)
    with pytest.raises(KeyError):
        sprite.frames[0][99]


def test_add_tileset_without_pixels_roundtrips() -> None:
    sprite = Sprite(8, 8)
    sprite.add_tileset("tiles", 8, 8, 1)
    loaded = Sprite.from_bytes(sprite.to_bytes())
    tileset = loaded.tilesets[0]
    assert tileset.name == "tiles"
    assert tileset.pixels is None
    assert not (tileset.flags & TILESET_FLAG_EMBEDDED)


def test_add_tileset_with_pixels_roundtrips() -> None:
    sprite = Sprite(8, 8)
    pixels = sprite.blank_pixels(8, 8)
    sprite.add_tileset("tiles", 8, 8, 1, pixels=pixels)
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.tilesets[0].pixels is not None
    assert loaded.tilesets[0].pixels.width == 8
    assert loaded.tilesets[0].pixels.height == 8


def test_add_tileset_rejects_mismatched_pixels() -> None:
    sprite = Sprite(8, 8)
    with pytest.raises(ValueError, match="tile dimensions"):
        sprite.add_tileset("tiles", 8, 8, 2, pixels=sprite.blank_pixels(8, 8))


def test_embedded_tileset_without_pixels_cannot_write() -> None:
    sprite = Sprite(1, 1)
    sprite.tilesets.append(
        Tileset(
            id=0,
            name="t",
            tile_count=1,
            tile_width=8,
            tile_height=8,
            flags=TILESET_FLAG_EMBEDDED,
        )
    )
    with pytest.raises(ValueError, match="tile dimensions"):
        sprite.to_bytes()


def test_nil_uuid_stays_none_when_sibling_has_uuid() -> None:
    sprite = Sprite(1, 1)
    sprite.add_layer("B")
    sprite.layers[0].uuid = UUID(int=42)
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.layers[0].uuid == UUID(int=42)
    assert loaded.layers[1].uuid is None


def test_new_sprite_num_colors() -> None:
    sprite = Sprite(1, 1)
    assert sprite.num_colors == 256
    assert Sprite.from_bytes(sprite.to_bytes()).num_colors == 256


def test_write_rejects_oversized_palette() -> None:
    from aseprite._limits import MAX_PALETTE_COLORS

    sprite = Sprite(1, 1)
    sprite.palette.extend([Color(0, 0, 0)] * (MAX_PALETTE_COLORS + 1))
    with pytest.raises(ValueError, match="palette size"):
        sprite.to_bytes()
