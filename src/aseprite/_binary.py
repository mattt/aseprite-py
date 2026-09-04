"""Little-endian binary primitives from the Aseprite file spec."""

from __future__ import annotations

import struct
from typing import Self

from aseprite._errors import FormatError

FILE_MAGIC = 0xA5E0
FRAME_MAGIC = 0xF1FA

HEADER_SIZE = 128
FRAME_HEADER_SIZE = 16
CHUNK_HEADER_SIZE = 6


class Reader:
    """Reads little-endian values from a bounded byte buffer."""

    def __init__(self, data: bytes, pos: int = 0, end: int | None = None) -> None:
        self.data = data
        self.pos = pos
        self.end = len(data) if end is None else end

    def remaining(self) -> int:
        return self.end - self.pos

    def _need(self, n: int) -> None:
        if n < 0 or self.pos + n > self.end:
            raise FormatError("unexpected end of Aseprite data")

    def raw(self, n: int) -> bytes:
        self._need(n)
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def skip(self, n: int) -> None:
        self._need(n)
        self.pos += n

    def u8(self) -> int:
        return self.raw(1)[0]

    def i8(self) -> int:
        return struct.unpack_from("<b", self.raw(1))[0]

    def u16(self) -> int:
        return struct.unpack_from("<H", self.raw(2))[0]

    def i16(self) -> int:
        return struct.unpack_from("<h", self.raw(2))[0]

    def u32(self) -> int:
        return struct.unpack_from("<I", self.raw(4))[0]

    def i32(self) -> int:
        return struct.unpack_from("<i", self.raw(4))[0]

    def u64(self) -> int:
        return struct.unpack_from("<Q", self.raw(8))[0]

    def i64(self) -> int:
        return struct.unpack_from("<q", self.raw(8))[0]

    def f32(self) -> float:
        return struct.unpack_from("<f", self.raw(4))[0]

    def f64(self) -> float:
        return struct.unpack_from("<d", self.raw(8))[0]

    def string(self) -> str:
        length = self.u16()
        raw = self.raw(length)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FormatError("string is not valid UTF-8") from exc

    def uuid(self) -> bytes:
        return self.raw(16)

    def bounded(self, size: int) -> Self:
        self._need(size)
        start = self.pos
        self.pos += size
        return type(self)(self.data, start, start + size)


class Writer:
    """Writes little-endian values into a growable buffer."""

    def __init__(self) -> None:
        self.buf = bytearray()

    def tell(self) -> int:
        return len(self.buf)

    def raw(self, data: bytes | bytearray) -> None:
        self.buf.extend(data)

    def pad(self, n: int) -> None:
        self.buf.extend(b"\x00" * n)

    def _pack(self, fmt: str, value: int) -> bytes:
        try:
            return struct.pack(fmt, value)
        except struct.error as exc:
            raise ValueError(f"integer {value} is out of range") from exc

    def u8(self, value: int) -> None:
        self.buf.extend(self._pack("<B", value))

    def i8(self, value: int) -> None:
        self.buf.extend(self._pack("<b", value))

    def u16(self, value: int) -> None:
        self.buf.extend(self._pack("<H", value))

    def i16(self, value: int) -> None:
        self.buf.extend(self._pack("<h", value))

    def u32(self, value: int) -> None:
        self.buf.extend(self._pack("<I", value))

    def i32(self, value: int) -> None:
        self.buf.extend(self._pack("<i", value))

    def u64(self, value: int) -> None:
        self.buf.extend(self._pack("<Q", value))

    def i64(self, value: int) -> None:
        self.buf.extend(self._pack("<q", value))

    def f32(self, value: float) -> None:
        self.buf.extend(struct.pack("<f", value))

    def f64(self, value: float) -> None:
        self.buf.extend(struct.pack("<d", value))

    def string(self, value: str) -> None:
        encoded = value.encode("utf-8")
        if len(encoded) > 0xFFFF:
            raise ValueError("string exceeds WORD length")
        self.u16(len(encoded))
        self.raw(encoded)

    def uuid(self, value: bytes) -> None:
        if len(value) != 16:
            raise ValueError("UUID must be 16 bytes")
        self.raw(value)

    def patch_u32(self, offset: int, value: int) -> None:
        self.buf[offset : offset + 4] = self._pack("<I", value)

    def patch_u16(self, offset: int, value: int) -> None:
        self.buf[offset : offset + 2] = self._pack("<H", value)
