import struct

import pytest

from aseprite import Color, ColorMode, Palette, Pixels, Sprite
from tests.helpers import _chunk, _document, tilemap_sprite


def test_reverse_preserves_cels_across_frames() -> None:
    sprite = Sprite(1, 1)
    first = sprite.layers[0]
    second = sprite.add_layer("second")
    red = Pixels(1, 1, b"\xff\x00\x00\xff", ColorMode.RGBA)
    green = Pixels(1, 1, b"\x00\xff\x00\xff", ColorMode.RGBA)
    sprite.frames[0][first] = red
    sprite.frames[0][second] = green
    sprite.add_frame().set_linked_cel(first, 0)
    sprite.frames[1].set_linked_cel(second, 0)
    sprite.layers.reverse()
    assert sprite.frames[0][first].pixels is red
    assert sprite.frames[0][second].pixels is green
    for frame in (0, 1):
        assert sprite.flatten(frame) == red.data
        assert Sprite.from_bytes(sprite.to_bytes()).flatten(frame) == red.data
    sprite.layers.reverse()
    assert sprite.flatten(1) == green.data


@pytest.mark.parametrize(
    "mode", [ColorMode.RGBA, ColorMode.GRAYSCALE, ColorMode.INDEXED]
)
def test_linked_chain_keeps_current_placement_and_opacity(mode: ColorMode) -> None:
    sprite = Sprite(3, 2, mode)
    sprite.palette = Palette([Color(0, 0, 0, 0), Color(255, 255, 255)])
    pixels = sprite.blank_pixels(1, 1)
    pixels[0, 0] = 1 if mode is ColorMode.INDEXED else Color(255, 255, 255)
    layer = sprite.layers[0]
    sprite.frames[0].set_cel(layer, pixels, opacity=60)
    sprite.add_frame().set_linked_cel(layer, 0, x=1, opacity=80)
    link = sprite.add_frame().set_linked_cel(layer, 1, x=2, y=1, opacity=128)
    expected = bytes(20) + bytes(
        (255, 255, 255, 255 if mode is ColorMode.INDEXED else 128)
    )
    assert sprite.flatten(2) == expected
    assert Sprite.from_bytes(sprite.to_bytes()).flatten(2) == expected
    assert link.link == 1 and link.pixels is None


def test_linked_cel_keeps_current_z_index() -> None:
    sprite = Sprite(1, 1)
    lower = sprite.layers[0]
    upper = sprite.add_layer("upper")
    red = Pixels(1, 1, b"\xff\x00\x00\xff", ColorMode.RGBA)
    green = Pixels(1, 1, b"\x00\xff\x00\xff", ColorMode.RGBA)
    sprite.frames[0][lower] = red
    frame = sprite.add_frame()
    frame.set_linked_cel(lower, 0, z_index=2)
    frame[upper] = green
    assert sprite.flatten(1) == red.data


def test_linked_tilemap_keeps_current_placement() -> None:
    sprite = tilemap_sprite()
    sprite.width = 4
    original = sprite.flatten(0)
    sprite.add_frame().set_linked_cel(sprite.layers[0], 0, x=2)
    expected = bytes(8) + original[:8] + bytes(8) + original[16:24]
    assert sprite.flatten(1) == expected


def _palette_chunk(
    first: int, colors: list[tuple[int, int, int, int]], *, old: bool
) -> bytes:
    if old:
        payload = struct.pack("<HBB", 1, first, len(colors))
        payload += b"".join(bytes(color[:3]) for color in colors)
        return _chunk(0x0004, payload)
    payload = struct.pack("<III8x", 3, first, first + len(colors) - 1)
    payload += b"".join(struct.pack("<H4B", 0, *color) for color in colors)
    return _chunk(0x2019, payload)


@pytest.mark.parametrize("old", [False, True])
def test_palette_animation_partial_updates_and_roundtrip(old: bool) -> None:
    sprite = Sprite(2, 1, ColorMode.INDEXED)
    sprite.palette = Palette([Color(0, 0, 0), Color(255, 0, 0), Color(0, 255, 0)])
    pixels = Pixels(2, 1, b"\x01\x02", ColorMode.INDEXED)
    sprite.frames[0][sprite.layers[0]] = pixels
    data = bytearray(sprite.to_bytes())
    # Each subsequent frame links the original image, but changes its palette.
    link = _chunk(0x2005, struct.pack("<HhhBHh5xH", 0, 0, 0, 255, 1, 0, 0))
    for chunks in (
        [_palette_chunk(2, [(0, 0, 255, 255)], old=old), link],
        [link],
        [
            _palette_chunk(
                0, [(0, 0, 0, 255), (255, 255, 0, 255), (255, 0, 255, 255)], old=old
            ),
            link,
        ],
    ):
        data.extend(_document(*chunks, width=2, depth=8)[128:])
    struct.pack_into("<I", data, 0, len(data))
    struct.pack_into("<H", data, 6, 4)
    loaded = Sprite.from_bytes(bytes(data))
    expected = [
        bytes.fromhex("ff0000ff00ff00ff"),
        bytes.fromhex("ff0000ff0000ffff"),
        bytes.fromhex("ff0000ff0000ffff"),
        bytes.fromhex("ffff00ffff00ffff"),
    ]
    for document in (loaded, Sprite.from_bytes(loaded.to_bytes())):
        assert [document.flatten(i) for i in range(4)] == expected
    assert loaded.frames[2].palette is None
    loaded.palette_at(1)[1].r = 10
    assert loaded.palette[1].r == 255


def test_create_palette_animation() -> None:
    sprite = Sprite(1, 1, ColorMode.INDEXED)
    sprite.palette = Palette([Color(0, 0, 0, 0), Color(255, 0, 0)])
    sprite.frames[0][0] = Pixels(1, 1, b"\x01", ColorMode.INDEXED)
    sprite.add_frame().set_linked_cel(0, 0)
    sprite.frames[1].palette = Palette([Color(0, 0, 0, 0), Color(0, 0, 255)])
    sprite.add_frame().set_linked_cel(0, 0)
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert [loaded.flatten(i) for i in range(3)] == [
        bytes.fromhex(v) for v in ("ff0000ff", "0000ffff", "0000ffff")
    ]
    with pytest.raises(IndexError):
        sprite.palette_at(-1)
