from aseprite import ColorMode, Pixels, Sprite


def rgba_sprite(
    width: int = 2,
    height: int = 2,
    *,
    color: bytes = b"\xff\x00\x00\xff",
) -> Sprite:
    sprite = Sprite(width, height, ColorMode.RGBA)
    data = color * (width * height)
    sprite.frames[0].set_cel(
        sprite.layers[0], Pixels(width, height, data, ColorMode.RGBA)
    )
    return sprite
