import pytest

from aseprite._binary import FILE_MAGIC, FRAME_MAGIC, HEADER_SIZE, Reader, Writer
from aseprite._errors import FormatError
from aseprite._limits import bytes_per_tile


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


def test_writer_rejects_out_of_range() -> None:
    w = Writer()
    with pytest.raises(ValueError, match="out of range"):
        w.u16(0x10000)
    with pytest.raises(ValueError, match="out of range"):
        w.i16(40_000)
    with pytest.raises(ValueError, match="out of range"):
        w.u8(256)


def test_reader_skip_and_writer_pad_patch() -> None:
    w = Writer()
    start = w.tell()
    w.u16(0)
    w.pad(2)
    w.patch_u16(start, 7)
    w.patch_u32(start, 0x11223344)
    r = Reader(bytes(w.buf))
    r.skip(2)
    assert r.u16() == 0x1122
    assert w.tell() == 4


def test_writer_string_and_uuid_limits() -> None:
    w = Writer()
    with pytest.raises(ValueError, match="WORD length"):
        w.string("x" * 0x10000)
    with pytest.raises(ValueError, match="16 bytes"):
        w.uuid(b"short")


def test_reader_invalid_utf8() -> None:
    r = Reader((3).to_bytes(2, "little") + b"\xff\xff\xff")
    with pytest.raises(FormatError, match="UTF-8"):
        r.string()


def test_bytes_per_tile() -> None:
    assert bytes_per_tile(32) == 4
    assert bytes_per_tile(16) == 2
    assert bytes_per_tile(8) == 1
