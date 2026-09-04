from aseprite import ColorMode, Pixels, Sprite


def rgba_sprite(
    width: int = 2,
    height: int = 2,
    *,
    color: bytes = b"\xff\x00\x00\xff",
) -> Sprite:
    sprite = Sprite(width, height, ColorMode.RGBA)
    layer = sprite.add_layer("Layer 1")
    frame = sprite.add_frame(100)
    data = color * (width * height)
    frame.set_cel(layer, Pixels(width, height, data, ColorMode.RGBA))
    return sprite
