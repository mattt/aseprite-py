import os
from pathlib import Path

from aseprite import Color, ColorMode, LayerType, Pixels, Sprite, Tilemap, Tileset
from aseprite._binary import FILE_MAGIC, FRAME_MAGIC, HEADER_SIZE, Reader, Writer
from aseprite._model import TILESET_FLAG_EMBEDDED, TILESET_FLAG_EMPTY_IS_ZERO

TILE_TL = b"\xff\x00\x00\xff"
TILE_TR = b"\x00\xff\x00\xff"
TILE_BL = b"\x00\x00\xff\xff"
TILE_BR = b"\xff\xff\xff\xff"
TILE_PIXELS = TILE_TL + TILE_TR + TILE_BL + TILE_BR


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


def blend_sprite() -> Sprite:
    """Returns two RGBA layers with partial alpha and opacity on every pixel.

    The expected flattened bytes were captured from Aseprite's own export
    of this sprite, so this covers the blend arithmetic on opaque,
    semi-transparent, and fully transparent backdrops.
    """
    sprite = Sprite(4, 2, ColorMode.RGBA)
    base = sprite.blank_pixels()
    base[0, 0] = (200, 40, 40, 255)
    base[1, 0] = (200, 40, 40, 255)
    base[2, 0] = (30, 60, 90, 120)
    base[3, 0] = (30, 60, 90, 120)
    base[0, 1] = (252, 63, 50, 6)
    base[1, 1] = (10, 10, 10, 3)
    base[2, 1] = (0, 0, 0, 0)
    base[3, 1] = (255, 255, 255, 255)
    sprite.frames[0][sprite.layers[0]] = base
    top = sprite.add_layer("top", opacity=200)
    over = sprite.blank_pixels()
    over[0, 0] = (10, 220, 30, 160)
    over[1, 0] = (0, 0, 255, 90)
    over[2, 0] = (255, 255, 255, 40)
    over[3, 0] = (7, 7, 7, 255)
    over[0, 1] = (254, 4, 62, 77)
    over[1, 1] = (100, 200, 50, 2)
    over[2, 1] = (20, 20, 20, 20)
    over[3, 1] = (9, 9, 9, 1)
    sprite.frames[0].set_cel(top, over, opacity=180)
    return sprite


BLEND_SPRITE_EXPECTED = bytes.fromhex(
    "876625ffa12152ff435c75840e161ec3fd0b3c30203914041414140bffffffff"
)


def indexed_overlap_sprite() -> Sprite:
    """Returns two indexed layers whose pixels overlap.

    Aseprite composites indexed sprites by replacing indices, so the
    half-transparent blue on top wins over the red below it and the
    transparent index lets the green show through.
    """
    sprite = Sprite(2, 1, ColorMode.INDEXED)
    sprite.palette.extend(
        [Color(0, 0, 0, 0), Color(255, 0, 0), Color(0, 0, 255, 128), Color(0, 255, 0)]
    )
    sprite.transparent_index = 0
    sprite.layers[0].opacity = 128
    bottom = sprite.blank_pixels()
    bottom[0, 0] = 1
    bottom[1, 0] = 3
    sprite.frames[0][sprite.layers[0]] = bottom
    top = sprite.add_layer("top")
    over = sprite.blank_pixels()
    over[0, 0] = 2
    over[1, 0] = 0
    sprite.frames[0].set_cel(top, over, opacity=128)
    return sprite


INDEXED_OVERLAP_EXPECTED = b"\x00\x00\xff\x80\x00\xff\x00\xff"


def tilemap_sprite(
    *,
    tile_id: int = 0,
    x_flip: bool = False,
    y_flip: bool = False,
    d_flip: bool = False,
    bits_per_tile: int = 32,
    empty_is_zero: bool = False,
) -> Sprite:
    flags = TILESET_FLAG_EMBEDDED
    if empty_is_zero:
        flags |= TILESET_FLAG_EMPTY_IS_ZERO
    if bits_per_tile == 32:
        tile_id_mask = 0x1FFFFFFF
        x_flip_mask = 0x20000000
        y_flip_mask = 0x40000000
        d_flip_mask = 0x80000000
        stride = 4
    elif bits_per_tile == 16:
        tile_id_mask = 0x1FFF
        x_flip_mask = 0x2000
        y_flip_mask = 0x4000
        d_flip_mask = 0x8000
        stride = 2
    else:
        tile_id_mask = 0x1F
        x_flip_mask = 0x20
        y_flip_mask = 0x40
        d_flip_mask = 0x80
        stride = 1
    value = tile_id & tile_id_mask
    if x_flip:
        value |= x_flip_mask
    if y_flip:
        value |= y_flip_mask
    if d_flip:
        value |= d_flip_mask
    sprite = Sprite(2, 2, ColorMode.RGBA, empty=True)
    sprite.tilesets.append(
        Tileset(
            id=0,
            name="tiles",
            tile_count=1,
            tile_width=2,
            tile_height=2,
            flags=flags,
            pixels=Pixels(2, 2, TILE_PIXELS, ColorMode.RGBA),
        )
    )
    layer = sprite.add_layer("map", kind=LayerType.TILEMAP, tileset_index=0)
    sprite.add_frame(100).set_tilemap_cel(
        layer,
        Tilemap(
            width=1,
            height=1,
            bits_per_tile=bits_per_tile,
            tile_id_mask=tile_id_mask,
            x_flip_mask=x_flip_mask,
            y_flip_mask=y_flip_mask,
            d_flip_mask=d_flip_mask,
            tiles=value.to_bytes(stride, "little"),
        ),
    )
    return sprite


def single_tile_sprite(
    *, tileset_id: int = 0, bits_per_tile: int = 32, shifted_mask: bool = False
) -> Sprite:
    """A blank tile followed by a tile with four distinct colors."""
    sprite = Sprite(2, 2, empty=True)
    sprite.add_tileset(
        "tiles",
        2,
        2,
        2,
        tileset_id=tileset_id,
        pixels=Pixels(2, 4, bytes(16) + TILE_PIXELS, ColorMode.RGBA),
    )
    layer = sprite.add_layer("map", kind=LayerType.TILEMAP, tileset_index=tileset_id)
    shift = 3 if shifted_mask else 0
    id_mask = ((1 << (bits_per_tile - 3)) - 1) << shift
    flip_shift = 0 if shifted_mask else bits_per_tile - 3
    sprite.add_frame().set_tilemap_cel(
        layer,
        Tilemap(
            1,
            1,
            bits_per_tile,
            id_mask,
            1 << flip_shift,
            2 << flip_shift,
            4 << flip_shift,
            (1 << shift).to_bytes(bits_per_tile // 8, "little"),
        ),
    )
    return sprite


def reference_layer_sprite(mode: ColorMode = ColorMode.RGBA) -> Sprite:
    sprite = Sprite(1, 1, mode)
    sprite.palette.extend([Color(0, 0, 0, 0), Color(0, 0, 255), Color(255, 0, 0)])
    base = sprite.blank_pixels()
    base[0, 0] = 1 if mode is ColorMode.INDEXED else Color(0, 0, 255)
    sprite.frames[0][0] = base
    reference = sprite.add_layer("reference")
    reference.reference = True
    top = sprite.blank_pixels()
    top[0, 0] = 2 if mode is ColorMode.INDEXED else Color(255, 0, 0)
    sprite.frames[0][reference] = top
    sprite.add_frame().set_linked_cel(0, 0)
    sprite.frames[1].set_linked_cel(reference, 0)
    return sprite


def legacy_palette_document(chunk_type: int = 0x000B) -> bytes:
    sprite = Sprite(1, 1, ColorMode.INDEXED)
    sprite.frames[0][0] = Pixels(1, 1, b"\x01", ColorMode.INDEXED)
    data = sprite.to_bytes()
    chunks = []
    r = Reader(data, HEADER_SIZE + 16)
    while r.remaining():
        size = r.u32()
        kind = r.u16()
        payload = r.raw(size - 6)
        if kind == 0x2019:
            # Two six-bit entries: transparent black, then orange.
            kind = chunk_type
            payload = b"\x01\x00\x00\x02\x00\x00\x00\x3f\x20\x10"
        chunks.append(_chunk(kind, payload))
    return _document(*chunks, depth=8)


def rectangular_tile_sprite(
    width: int, height: int, flips: int, mode: ColorMode = ColorMode.RGBA
) -> Sprite:
    sprite = Sprite(3, 3, mode, empty=True)
    sprite.transparent_index = 2 if mode is ColorMode.INDEXED else 0
    sprite.palette.extend([Color(255, 0, 0), Color(0, 255, 0), Color(0, 0, 0, 0)])
    pixels = sprite.blank_pixels(width, height * 2)
    pixels[0, height] = 0 if mode is ColorMode.INDEXED else Color(255, 0, 0)
    x, y = (1, height) if width == 2 else (0, height + 1)
    pixels[x, y] = 1 if mode is ColorMode.INDEXED else Color(0, 255, 0)
    sprite.add_tileset("tiles", width, height, 2, pixels=pixels)
    layer = sprite.add_layer("map", kind=LayerType.TILEMAP, tileset_index=0)
    sprite.add_frame().set_tilemap_cel(
        layer,
        Tilemap(
            1,
            1,
            32,
            0x1FFFFFFF,
            0x20000000,
            0x40000000,
            0x80000000,
            (1 | (flips << 29)).to_bytes(4, "little"),
        ),
    )
    return sprite


def _header(
    *,
    magic: int = FILE_MAGIC,
    frames: int = 1,
    width: int = 1,
    height: int = 1,
    depth: int = 32,
    speed: int = 0,
) -> bytearray:
    data = bytearray(HEADER_SIZE)
    data[0:4] = (HEADER_SIZE + 16).to_bytes(4, "little")
    data[4:6] = magic.to_bytes(2, "little")
    data[6:8] = frames.to_bytes(2, "little")
    data[8:10] = width.to_bytes(2, "little")
    data[10:12] = height.to_bytes(2, "little")
    data[12:14] = depth.to_bytes(2, "little")
    data[18:20] = speed.to_bytes(2, "little")
    return data


def _frame(chunks: int = 0, *, duration: int = 100) -> bytes:
    buf = bytearray(16)
    buf[0:4] = (16).to_bytes(4, "little")
    buf[4:6] = FRAME_MAGIC.to_bytes(2, "little")
    buf[6:8] = chunks.to_bytes(2, "little")
    buf[8:10] = duration.to_bytes(2, "little")
    return bytes(buf)


def _chunk(chunk_type: int, payload: bytes) -> bytes:
    size = 6 + len(payload)
    return size.to_bytes(4, "little") + chunk_type.to_bytes(2, "little") + payload


def _document(
    *chunks: bytes,
    width: int = 1,
    height: int = 1,
    duration: int = 100,
    speed: int = 0,
    depth: int = 32,
) -> bytes:
    body = b"".join(chunks)
    frame = bytearray(16 + len(body))
    frame[0:4] = (16 + len(body)).to_bytes(4, "little")
    frame[4:6] = FRAME_MAGIC.to_bytes(2, "little")
    frame[6:8] = len(chunks).to_bytes(2, "little")
    frame[8:10] = duration.to_bytes(2, "little")
    frame[12:16] = len(chunks).to_bytes(4, "little")
    frame[16:] = body
    header = _header(width=width, height=height, speed=speed, depth=depth)
    header[0:4] = (HEADER_SIZE + len(frame)).to_bytes(4, "little")
    return bytes(header) + bytes(frame)


def _raw_cel_payload(*, width: int = 1, height: int = 1, pixels: bytes) -> bytes:
    w = Writer()
    w.u16(0)
    w.i16(0)
    w.i16(0)
    w.u8(255)
    w.u16(0)
    w.i16(0)
    w.pad(5)
    w.u16(width)
    w.u16(height)
    w.raw(pixels)
    return bytes(w.buf)


def chunk_types(data: bytes) -> list[int]:
    from aseprite._binary import FRAME_HEADER_SIZE

    r = Reader(data, HEADER_SIZE)
    r.skip(FRAME_HEADER_SIZE - 4)
    nchunks = r.u32()
    types = []
    for _ in range(nchunks):
        size = r.u32()
        types.append(r.u16())
        r.skip(size - 6)
    return types


def aseprite_cli() -> Path | None:
    """Returns the Aseprite executable, if one is available.

    Uses ``ASEPRITE_PATH`` when that file exists.
    Otherwise looks in ``/Applications/Aseprite.app``.
    """
    env = os.environ.get("ASEPRITE_PATH")
    if env:
        path = Path(env)
        return path if path.is_file() else None
    mac = Path("/Applications/Aseprite.app/Contents/MacOS/aseprite")
    return mac if mac.is_file() else None
