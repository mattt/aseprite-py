import zlib

import pytest

from aseprite import FormatError, Sprite
from aseprite._binary import (
    CHUNK_HEADER_SIZE,
    FILE_MAGIC,
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    HEADER_SIZE,
    Writer,
)
from aseprite._limits import MAX_PALETTE_COLORS
from aseprite._reader import (
    CHUNK_CEL,
    CHUNK_LAYER,
    CHUNK_PALETTE,
    CHUNK_TILESET,
    CHUNK_USER_DATA,
)


def _header(
    *,
    magic: int = FILE_MAGIC,
    frames: int = 1,
    width: int = 1,
    height: int = 1,
    depth: int = 32,
) -> bytearray:
    data = bytearray(HEADER_SIZE)
    data[0:4] = (HEADER_SIZE + 16).to_bytes(4, "little")
    data[4:6] = magic.to_bytes(2, "little")
    data[6:8] = frames.to_bytes(2, "little")
    data[8:10] = width.to_bytes(2, "little")
    data[10:12] = height.to_bytes(2, "little")
    data[12:14] = depth.to_bytes(2, "little")
    return data


def _frame(chunks: int = 0) -> bytes:
    buf = bytearray(16)
    buf[0:4] = (16).to_bytes(4, "little")
    buf[4:6] = FRAME_MAGIC.to_bytes(2, "little")
    buf[6:8] = chunks.to_bytes(2, "little")
    buf[8:10] = (100).to_bytes(2, "little")
    return bytes(buf)


def test_short_file() -> None:
    with pytest.raises(FormatError):
        Sprite.from_bytes(b"short")


def test_bad_magic() -> None:
    data = _header(magic=0x0000) + _frame()
    with pytest.raises(FormatError, match="magic"):
        Sprite.from_bytes(bytes(data) + _frame())


def test_bad_frame_magic() -> None:
    header = _header()
    frame = bytearray(_frame())
    frame[4:6] = b"\x00\x00"
    with pytest.raises(FormatError, match="frame magic"):
        Sprite.from_bytes(bytes(header) + bytes(frame))


def test_bad_depth() -> None:
    with pytest.raises(FormatError, match="color depth"):
        Sprite.from_bytes(bytes(_header(depth=24)) + _frame())


def test_truncated_frame() -> None:
    with pytest.raises(FormatError):
        Sprite.from_bytes(bytes(_header()))


def test_chunk_exceeds_frame() -> None:
    header = _header(frames=2)
    frame0 = bytearray(FRAME_HEADER_SIZE + CHUNK_HEADER_SIZE)
    frame0[0:4] = (FRAME_HEADER_SIZE + CHUNK_HEADER_SIZE).to_bytes(4, "little")
    frame0[4:6] = FRAME_MAGIC.to_bytes(2, "little")
    frame0[6:8] = (1).to_bytes(2, "little")
    frame0[8:10] = (100).to_bytes(2, "little")
    frame0[16:20] = (FRAME_HEADER_SIZE + CHUNK_HEADER_SIZE + 8).to_bytes(4, "little")
    frame0[20:22] = (0x0000).to_bytes(2, "little")
    with pytest.raises(FormatError, match="chunk exceeds frame"):
        Sprite.from_bytes(bytes(header) + bytes(frame0) + _frame())


def test_invalid_zlib() -> None:
    sprite = Sprite(1, 1)
    from aseprite import ColorMode, Pixels

    sprite.frames[0].set_cel(
        sprite.layers[0], Pixels(1, 1, b"\x00\x00\x00\x00", ColorMode.RGBA)
    )
    raw = bytearray(sprite.to_bytes())
    # Corrupt the zlib stream near the end of the file.
    raw[-4:] = b"\x00\x00\x00\x00"
    with pytest.raises(FormatError):
        Sprite.from_bytes(bytes(raw))


def _chunk(chunk_type: int, payload: bytes) -> bytes:
    size = 6 + len(payload)
    return size.to_bytes(4, "little") + chunk_type.to_bytes(2, "little") + payload


def _document(*chunks: bytes, width: int = 1, height: int = 1) -> bytes:
    body = b"".join(chunks)
    frame = bytearray(16 + len(body))
    frame[0:4] = (16 + len(body)).to_bytes(4, "little")
    frame[4:6] = FRAME_MAGIC.to_bytes(2, "little")
    frame[6:8] = len(chunks).to_bytes(2, "little")
    frame[8:10] = (100).to_bytes(2, "little")
    frame[12:16] = len(chunks).to_bytes(4, "little")
    frame[16:] = body
    header = _header(width=width, height=height)
    header[0:4] = (HEADER_SIZE + len(frame)).to_bytes(4, "little")
    return bytes(header) + bytes(frame)


def test_palette_size_limit() -> None:
    payload = bytearray()
    payload += (MAX_PALETTE_COLORS + 1).to_bytes(4, "little")
    payload += (0).to_bytes(4, "little")
    payload += (0).to_bytes(4, "little")
    payload += bytes(8)
    payload += (0).to_bytes(2, "little")
    payload += b"\x00\x00\x00\xff"
    with pytest.raises(FormatError, match="palette size"):
        Sprite.from_bytes(_document(_chunk(CHUNK_PALETTE, bytes(payload))))


def test_decompress_rejects_huge_expected_size() -> None:
    payload = bytearray()
    payload += (0).to_bytes(2, "little")
    payload += (0).to_bytes(2, "little")
    payload += (0).to_bytes(2, "little")
    payload += b"\xff"
    payload += (2).to_bytes(2, "little")
    payload += (0).to_bytes(2, "little")
    payload += bytes(5)
    payload += (65535).to_bytes(2, "little")
    payload += (65535).to_bytes(2, "little")
    payload += zlib.compress(b"\x00\x00\x00\xff")
    with pytest.raises(FormatError, match="size limit"):
        Sprite.from_bytes(_document(_chunk(CHUNK_CEL, bytes(payload))))


def test_decompress_rejects_extra_output() -> None:
    payload = bytearray()
    payload += (0).to_bytes(2, "little")
    payload += (0).to_bytes(2, "little")
    payload += (0).to_bytes(2, "little")
    payload += b"\xff"
    payload += (2).to_bytes(2, "little")
    payload += (0).to_bytes(2, "little")
    payload += bytes(5)
    payload += (1).to_bytes(2, "little")
    payload += (1).to_bytes(2, "little")
    payload += zlib.compress(b"\x00" * 1024)
    with pytest.raises(FormatError, match="size limit"):
        Sprite.from_bytes(_document(_chunk(CHUNK_CEL, bytes(payload))))


def test_zero_canvas_is_format_error() -> None:
    with pytest.raises(FormatError, match="positive"):
        Sprite.from_bytes(bytes(_header(width=0, height=1)) + _frame())


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


def test_short_cel_pixels_is_format_error() -> None:
    with pytest.raises(FormatError, match="pixel data length"):
        Sprite.from_bytes(
            _document(
                _chunk(CHUNK_CEL, _raw_cel_payload(width=2, height=2, pixels=b"\x00"))
            )
        )


def test_unknown_cel_type_is_format_error() -> None:
    w = Writer()
    w.u16(0)
    w.i16(0)
    w.i16(0)
    w.u8(255)
    w.u16(99)
    w.i16(0)
    w.pad(5)
    with pytest.raises(FormatError, match="unsupported cel type"):
        Sprite.from_bytes(_document(_chunk(CHUNK_CEL, bytes(w.buf))))


def test_unknown_property_type_is_format_error() -> None:
    layer = Writer()
    layer.u16(3)
    layer.u16(0)
    layer.u16(0)
    layer.u16(0)
    layer.u16(0)
    layer.u16(0)
    layer.u8(255)
    layer.pad(3)
    layer.string("L")
    user = Writer()
    user.u32(4)
    size_at = user.tell()
    user.u32(0)
    user.u32(1)
    user.u32(0)
    user.u32(1)
    user.string("x")
    user.u16(0xFFFF)
    user.patch_u32(size_at, user.tell() - size_at)
    with pytest.raises(FormatError, match="unsupported property type"):
        Sprite.from_bytes(
            _document(
                _chunk(CHUNK_LAYER, bytes(layer.buf)),
                _chunk(CHUNK_USER_DATA, bytes(user.buf)),
            )
        )


def test_document_byte_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aseprite._reader.MAX_UNCOMPRESSED_BYTES", 6)
    cel = _chunk(CHUNK_CEL, _raw_cel_payload(pixels=b"\x00\x00\x00\xff"))

    def frame_with(*chunks: bytes) -> bytes:
        body = b"".join(chunks)
        frame = bytearray(16 + len(body))
        frame[0:4] = (16 + len(body)).to_bytes(4, "little")
        frame[4:6] = FRAME_MAGIC.to_bytes(2, "little")
        frame[6:8] = len(chunks).to_bytes(2, "little")
        frame[8:10] = (100).to_bytes(2, "little")
        frame[12:16] = len(chunks).to_bytes(4, "little")
        frame[16:] = body
        return bytes(frame)

    header = _header(frames=2)
    payload = frame_with(cel) + frame_with(cel)
    header[0:4] = (HEADER_SIZE + len(payload)).to_bytes(4, "little")
    with pytest.raises(FormatError, match="size limit"):
        Sprite.from_bytes(bytes(header) + payload)


def test_tileset_user_data_write_does_not_pad() -> None:
    tileset = Writer()
    tileset.u32(0)
    tileset.u32(0)
    tileset.u32(10_000_000)
    tileset.u16(16)
    tileset.u16(16)
    tileset.i16(1)
    tileset.pad(14)
    tileset.string("t")
    user = Writer()
    user.u32(1)
    user.string("note")
    sprite = Sprite.from_bytes(
        _document(
            _chunk(CHUNK_TILESET, bytes(tileset.buf)),
            _chunk(CHUNK_USER_DATA, bytes(user.buf)),
        )
    )
    data = sprite.to_bytes()
    assert len(data) < 100_000


def test_tileset_user_data_does_not_preallocate() -> None:
    tileset = Writer()
    tileset.u32(0)
    tileset.u32(0)
    tileset.u32(10_000_000)
    tileset.u16(16)
    tileset.u16(16)
    tileset.i16(1)
    tileset.pad(14)
    tileset.string("t")
    user = Writer()
    user.u32(0)
    sprite = Sprite.from_bytes(
        _document(
            _chunk(CHUNK_TILESET, bytes(tileset.buf)),
            _chunk(CHUNK_USER_DATA, bytes(user.buf)),
        )
    )
    assert sprite.tilesets[0].tile_count == 10_000_000
    assert sprite.tilesets[0].tile_user_data == []
