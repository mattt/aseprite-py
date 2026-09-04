import pytest

from aseprite import FormatError, Sprite
from aseprite._binary import (
    CHUNK_HEADER_SIZE,
    FILE_MAGIC,
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    HEADER_SIZE,
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
    layer = sprite.add_layer("L")
    frame = sprite.add_frame(100)
    from aseprite import ColorMode, Pixels

    frame.set_cel(layer, Pixels(1, 1, b"\x00\x00\x00\x00", ColorMode.RGBA))
    raw = bytearray(sprite.to_bytes())
    # Corrupt the zlib stream near the end of the file.
    raw[-4:] = b"\x00\x00\x00\x00"
    with pytest.raises(FormatError):
        Sprite.from_bytes(bytes(raw))
