import pytest

from aseprite._binary import FILE_MAGIC, FRAME_MAGIC, HEADER_SIZE, Reader, Writer
from aseprite._errors import FormatError


def test_roundtrip_primitives() -> None:
    w = Writer()
    w.u8(255)
    w.i8(-8)
    w.u16(0xA5E0)
    w.i16(-300)
    w.u32(0x12345678)
    w.i32(-40000)
    w.u64(2**40)
    w.i64(-(2**40))
    w.f32(1.5)
    w.f64(2.25)
    w.string("hello")
    w.uuid(b"0123456789abcdef")
    r = Reader(bytes(w.buf))
    assert r.u8() == 255
    assert r.i8() == -8
    assert r.u16() == FILE_MAGIC
    assert r.i16() == -300
    assert r.u32() == 0x12345678
    assert r.i32() == -40000
    assert r.u64() == 2**40
    assert r.i64() == -(2**40)
    assert r.f32() == pytest.approx(1.5)
    assert r.f64() == pytest.approx(2.25)
    assert r.string() == "hello"
    assert r.uuid() == b"0123456789abcdef"
    assert r.remaining() == 0


def test_bounded_reader() -> None:
    r = Reader(b"abcdef")
    inner = r.bounded(3)
    assert inner.raw(3) == b"abc"
    assert r.raw(3) == b"def"


def test_short_read_raises() -> None:
    r = Reader(b"\x00")
    with pytest.raises(FormatError):
        r.u16()


def test_header_constants() -> None:
    assert HEADER_SIZE == 128
    assert FRAME_MAGIC == 0xF1FA
