import os
from pathlib import Path

from aseprite import ColorMode, LayerType, Pixels, Sprite, Tilemap, Tileset
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
