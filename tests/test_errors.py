import zlib
from pathlib import Path

import pytest

from aseprite import (
    AsepriteError,
    BlendMode,
    Cel,
    ColorMode,
    ExternalFileType,
    FormatError,
    Pixels,
    Sprite,
    UserData,
)
from aseprite._binary import (
    CHUNK_HEADER_SIZE,
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    HEADER_SIZE,
    Writer,
)
from aseprite._limits import MAX_PALETTE_COLORS
from aseprite._reader import (
    CHUNK_CEL,
    CHUNK_COLOR_PROFILE,
    CHUNK_LAYER,
    CHUNK_PALETTE,
    CHUNK_TAGS,
    CHUNK_TILESET,
    CHUNK_USER_DATA,
)
from aseprite._userdata import write_user_data
from tests.helpers import (
    _chunk,
    _document,
    _frame,
    _header,
    _raw_cel_payload,
)


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


def test_every_truncation_is_format_error() -> None:
    data = (Path(__file__).parent / "fixtures" / "editor.aseprite").read_bytes()
    for length in range(len(data)):
        with pytest.raises(FormatError):
            Sprite.from_bytes(data[:length])


def test_chunk_past_end_of_data_is_format_error() -> None:
    header = _header()
    frame = bytearray(FRAME_HEADER_SIZE + CHUNK_HEADER_SIZE + 2)
    frame[0:4] = (FRAME_HEADER_SIZE + 64).to_bytes(4, "little")
    frame[4:6] = FRAME_MAGIC.to_bytes(2, "little")
    frame[6:8] = (1).to_bytes(2, "little")
    frame[8:10] = (100).to_bytes(2, "little")
    frame[16:20] = (CHUNK_HEADER_SIZE + 16).to_bytes(4, "little")
    frame[20:22] = CHUNK_COLOR_PROFILE.to_bytes(2, "little")
    header[0:4] = (HEADER_SIZE + len(frame)).to_bytes(4, "little")
    with pytest.raises(FormatError, match="unexpected end"):
        Sprite.from_bytes(bytes(header) + bytes(frame))


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
    sprite.frames[0].set_cel(
        sprite.layers[0], Pixels(1, 1, b"\x00\x00\x00\x00", ColorMode.RGBA)
    )
    raw = bytearray(sprite.to_bytes())
    raw[-4:] = b"\x00\x00\x00\x00"
    with pytest.raises(FormatError):
        Sprite.from_bytes(bytes(raw))


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


def test_short_cel_pixels_is_format_error() -> None:
    with pytest.raises(FormatError, match="pixel data length"):
        Sprite.from_bytes(
            _document(
                _chunk(CHUNK_CEL, _raw_cel_payload(width=2, height=2, pixels=b"\x00"))
            )
        )


def test_unknown_blend_mode_is_preserved() -> None:
    layer = Writer()
    layer.u16(3)
    layer.u16(0)
    layer.u16(0)
    layer.u16(0)
    layer.u16(0)
    layer.u16(99)
    layer.u8(255)
    layer.pad(3)
    layer.string("L")
    cel = _raw_cel_payload(pixels=b"\xff\x00\x00\xff")
    sprite = Sprite.from_bytes(
        _document(_chunk(CHUNK_LAYER, bytes(layer.buf)), _chunk(CHUNK_CEL, cel))
    )
    mode = sprite.layers[0].blend_mode
    assert mode == 99
    assert isinstance(mode, BlendMode)
    assert mode.name == "UNKNOWN_99"
    assert mode is not BlendMode.NORMAL
    assert sprite.flatten(0) == b"\xff\x00\x00\xff"
    again = Sprite.from_bytes(sprite.to_bytes())
    assert again.layers[0].blend_mode == 99


def test_unknown_layer_type_is_format_error() -> None:
    layer = Writer()
    layer.u16(3)
    layer.u16(99)
    layer.u16(0)
    layer.u16(0)
    layer.u16(0)
    layer.u16(0)
    layer.u8(255)
    layer.pad(3)
    layer.string("L")
    with pytest.raises(FormatError, match="unsupported layer type"):
        Sprite.from_bytes(_document(_chunk(CHUNK_LAYER, bytes(layer.buf))))


def test_unknown_loop_direction_is_preserved() -> None:
    tags = Writer()
    tags.u16(1)
    tags.pad(8)
    tags.u16(0)
    tags.u16(0)
    tags.u8(99)
    tags.u16(0)
    tags.pad(6)
    tags.u8(0)
    tags.u8(0)
    tags.u8(0)
    tags.u8(0)
    tags.string("t")
    sprite = Sprite.from_bytes(_document(_chunk(CHUNK_TAGS, bytes(tags.buf))))
    assert sprite.tags[0].direction == 99
    assert sprite.tags[0].direction.name == "UNKNOWN_99"
    again = Sprite.from_bytes(sprite.to_bytes())
    assert again.tags[0].direction == 99


def test_unknown_color_profile_type_is_preserved() -> None:
    profile = Writer()
    profile.u16(99)
    profile.u16(0)
    profile.u32(0)
    profile.pad(8)
    sprite = Sprite.from_bytes(
        _document(_chunk(CHUNK_COLOR_PROFILE, bytes(profile.buf)))
    )
    assert sprite.color_profile is not None
    assert sprite.color_profile.kind == 99
    again = Sprite.from_bytes(sprite.to_bytes())
    assert again.color_profile is not None
    assert again.color_profile.kind == 99


def test_open_enum_rejects_non_integers() -> None:
    assert ExternalFileType(99).name == "UNKNOWN_99"
    assert ExternalFileType(1) is ExternalFileType.TILESET
    with pytest.raises(ValueError):
        ExternalFileType(-1)
    with pytest.raises(ValueError):
        ExternalFileType("palette")  # type: ignore[arg-type]


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


def test_huge_embedded_tileset_is_not_padded_with_user_data() -> None:
    from aseprite._limits import MAX_PADDED_TILE_USER_DATA

    tileset = Writer()
    tileset.u32(0)
    tileset.u32(2)
    tileset.u32(MAX_PADDED_TILE_USER_DATA + 1)
    tileset.u16(1)
    tileset.u16(0)
    tileset.i16(1)
    tileset.pad(14)
    tileset.string("t")
    compressed = zlib.compress(b"")
    tileset.u32(len(compressed))
    tileset.raw(compressed)
    sprite = Sprite.from_bytes(_document(_chunk(CHUNK_TILESET, bytes(tileset.buf))))
    assert len(sprite.to_bytes()) < 10_000


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


def test_trailing_empty_tile_user_data_is_dropped() -> None:
    tileset = Writer()
    tileset.u32(0)
    tileset.u32(0)
    tileset.u32(3)
    tileset.u16(1)
    tileset.u16(1)
    tileset.i16(1)
    tileset.pad(14)
    tileset.string("t")
    empty = Writer()
    empty.u32(0)
    note = Writer()
    note.u32(1)
    note.string("tile 1")
    sprite = Sprite.from_bytes(
        _document(
            _chunk(CHUNK_TILESET, bytes(tileset.buf)),
            _chunk(CHUNK_USER_DATA, bytes(empty.buf)),
            _chunk(CHUNK_USER_DATA, bytes(empty.buf)),
            _chunk(CHUNK_USER_DATA, bytes(note.buf)),
            _chunk(CHUNK_USER_DATA, bytes(empty.buf)),
        )
    )
    loaded = sprite.tilesets[0]
    assert loaded.user_data is None
    assert loaded.tile_user_data == [None, UserData(text="tile 1")]
    again = Sprite.from_bytes(sprite.to_bytes())
    assert again == sprite


def test_truncated_chunk_header() -> None:
    header = _header()
    frame = bytearray(FRAME_HEADER_SIZE + 3)
    frame[0:4] = (FRAME_HEADER_SIZE + 3).to_bytes(4, "little")
    frame[4:6] = FRAME_MAGIC.to_bytes(2, "little")
    frame[6:8] = (1).to_bytes(2, "little")
    frame[8:10] = (100).to_bytes(2, "little")
    frame[12:16] = (1).to_bytes(4, "little")
    header[0:4] = (HEADER_SIZE + len(frame)).to_bytes(4, "little")
    with pytest.raises(FormatError, match="truncated chunk header"):
        Sprite.from_bytes(bytes(header) + bytes(frame))


def test_chunk_size_too_small() -> None:
    with pytest.raises(FormatError, match="smaller than 6"):
        Sprite.from_bytes(
            _document((5).to_bytes(4, "little") + (0).to_bytes(2, "little"))
        )


def test_palette_index_range_invalid() -> None:
    payload = bytearray()
    payload += (2).to_bytes(4, "little")
    payload += (1).to_bytes(4, "little")
    payload += (0).to_bytes(4, "little")
    payload += bytes(8)
    with pytest.raises(FormatError, match="palette index range"):
        Sprite.from_bytes(_document(_chunk(CHUNK_PALETTE, bytes(payload))))


def test_short_tileset_image_is_zero_padded() -> None:
    tileset = Writer()
    tileset.u32(0)
    tileset.u32(2)
    tileset.u32(2)
    tileset.u16(2)
    tileset.u16(1)
    tileset.i16(1)
    tileset.pad(14)
    tileset.string("t")
    compressed = zlib.compress(b"\x00\x00\x00\xff")
    tileset.u32(len(compressed))
    tileset.raw(compressed)
    sprite = Sprite.from_bytes(_document(_chunk(CHUNK_TILESET, bytes(tileset.buf))))
    pixels = sprite.tilesets[0].pixels
    assert pixels is not None
    assert (pixels.width, pixels.height) == (2, 2)
    assert bytes(pixels.data) == b"\x00\x00\x00\xff" + bytes(12)


def test_short_tileset_image_counts_against_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("aseprite._reader.MAX_UNCOMPRESSED_BYTES", 8)
    tileset = Writer()
    tileset.u32(0)
    tileset.u32(2)
    tileset.u32(2)
    tileset.u16(2)
    tileset.u16(1)
    tileset.i16(1)
    tileset.pad(14)
    tileset.string("t")
    compressed = zlib.compress(b"\x00\x00\x00\xff")
    tileset.u32(len(compressed))
    tileset.raw(compressed)
    with pytest.raises(FormatError, match="size limit"):
        Sprite.from_bytes(_document(_chunk(CHUNK_TILESET, bytes(tileset.buf))))


def test_user_data_properties_exceed_size() -> None:
    user = Writer()
    user.u32(4)
    user.u32(8)
    user.u32(1)
    user.u32(0)
    user.u32(1)
    user.string("x")
    user.u16(6)
    user.i32(1)
    with pytest.raises(FormatError, match="exceed declared size"):
        Sprite.from_bytes(_document(_chunk(CHUNK_USER_DATA, bytes(user.buf))))


def test_user_data_nesting_exceeds_limit() -> None:
    from aseprite import PropertiesMap, PropertyType, UserData, UserProperty

    prop: UserProperty = UserProperty("n", PropertyType.INT32, 1)
    for _ in range(129):
        prop = UserProperty("p", PropertyType.PROPERTIES, [prop])
    with pytest.raises(ValueError, match="nesting"):
        write_user_data(Writer(), UserData(properties=[PropertiesMap(0, [prop])]))


def test_user_data_read_nesting_exceeds_limit() -> None:
    from aseprite import PropertyType

    inner = Writer()

    def nest(depth: int) -> None:
        inner.string("n")
        inner.u16(int(PropertyType.PROPERTIES))
        if depth == 0:
            inner.u32(0)
            return
        inner.u32(1)
        nest(depth - 1)

    nest(129)
    user = Writer()
    user.u32(4)
    size_at = user.tell()
    user.u32(0)
    user.u32(1)
    user.u32(0)
    user.u32(1)
    user.raw(bytes(inner.buf))
    user.patch_u32(size_at, user.tell() - size_at)
    with pytest.raises(FormatError, match="nesting"):
        Sprite.from_bytes(_document(_chunk(CHUNK_USER_DATA, bytes(user.buf))))


def test_user_data_write_rejects_bad_values() -> None:
    from aseprite import PropertiesMap, PropertyType, UserData, UserProperty

    w = Writer()
    with pytest.raises(ValueError, match="integer"):
        write_user_data(
            w,
            UserData(
                properties=[
                    PropertiesMap(0, [UserProperty("x", PropertyType.INT32, "bad")])
                ]
            ),
        )
    with pytest.raises(ValueError, match="pair"):
        write_user_data(
            w,
            UserData(
                properties=[
                    PropertiesMap(0, [UserProperty("p", PropertyType.POINT, (1,))])
                ]
            ),
        )
    with pytest.raises(ValueError, match="UUID"):
        write_user_data(
            w,
            UserData(
                properties=[
                    PropertiesMap(0, [UserProperty("u", PropertyType.UUID, "nope")])
                ]
            ),
        )


def test_cel_without_pixels_cannot_write() -> None:
    sprite = Sprite(1, 1)
    sprite.frames[0]._cels[0] = Cel(layer_index=0)
    with pytest.raises(ValueError, match="no pixel data"):
        sprite.to_bytes()


def test_open_rejects_text_file() -> None:
    from io import StringIO
    from typing import Any

    source: Any = StringIO("not binary")
    with pytest.raises(TypeError, match="binary"):
        Sprite.open(source)


def test_format_error_is_aseprite_error() -> None:
    assert issubclass(FormatError, AsepriteError)
    with pytest.raises(AsepriteError):
        Sprite.from_bytes(b"short")
