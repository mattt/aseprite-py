from io import BytesIO

import pytest

from aseprite import (
    Color,
    ColorMode,
    HeaderFlags,
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
