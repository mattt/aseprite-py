from tests.helpers import rgba_sprite

from aseprite import Color, ColorMode, Palette, Pixels, Sprite


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
    sprite = Sprite(1, 1, ColorMode.RGBA)
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
    layer = sprite.add_layer("L")
    sprite.add_frame(100).set_cel(layer, Pixels(2, 1, b"\x00\x01", ColorMode.INDEXED))
    data = sprite.flatten(0)
    assert data[0:4] == b"\x00\x00\x00\x00"
    assert data[4:8] == b"\x00\xff\x00\xff"


def test_flatten_opacity() -> None:
    sprite = Sprite(1, 1, ColorMode.RGBA)
    layer = sprite.add_layer("L", opacity=128)
    sprite.add_frame(100).set_cel(
        layer, Pixels(1, 1, b"\xff\x00\x00\xff", ColorMode.RGBA), opacity=128
    )
    data = sprite.flatten(0)
    assert data[3] < 255
    assert data[0] > 0


def test_image_extra() -> None:
    sprite = rgba_sprite(1, 1)
    image = sprite.image(0)
    assert image.size == (1, 1)
    assert image.mode == "RGBA"
