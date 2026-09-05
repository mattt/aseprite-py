import struct
import zlib

import pytest

from aseprite import FormatError, Sprite
from aseprite._reader import CHUNK_CEL, CHUNK_TILESET
from aseprite._writer import _compress
from tests.helpers import _chunk, _document


def _compressed_document(kind: str, compressed: bytes) -> bytes:
    """Builds a chunk declaring four uncompressed bytes."""
    if kind == "tileset":
        header = struct.pack("<IIIHHh14xH", 0, 2, 1, 1, 1, 1, 0)
        payload = header + struct.pack("<I", len(compressed)) + compressed
        return _document(_chunk(CHUNK_TILESET, payload))
    cel_type = 3 if kind == "tilemap" else 2
    header = struct.pack("<HhhBHh5xHH", 0, 0, 0, 255, cel_type, 0, 1, 1)
    if kind == "tilemap":
        header += struct.pack(
            "<H4I10x", 32, 0x1FFFFFFF, 0x20000000, 0x40000000, 0x80000000
        )
    return _document(_chunk(CHUNK_CEL, header + compressed))


@pytest.mark.parametrize("kind", ["image", "tilemap", "tileset"])
def test_compressed_chunk_rejects_unconsumed_output(kind: str) -> None:
    # A stored DEFLATE block leaves unconsumed input when the output cap
    # is reached; decompress(b"", 1) does not inspect that input.
    compressed = zlib.compress(b"x" * 4096, level=0)
    with pytest.raises(FormatError, match="size limit"):
        Sprite.from_bytes(_compressed_document(kind, compressed))


@pytest.mark.parametrize("kind", ["image", "tilemap", "tileset"])
@pytest.mark.parametrize("missing", [1, 4, 6])
def test_compressed_chunk_rejects_incomplete_stream(kind: str, missing: int) -> None:
    compressed = zlib.compress(b"abcd")[:-missing]
    with pytest.raises(FormatError):
        Sprite.from_bytes(_compressed_document(kind, compressed))


@pytest.mark.parametrize("kind", ["image", "tilemap", "tileset"])
def test_compressed_chunk_accepts_complete_stream(kind: str) -> None:
    sprite = Sprite.from_bytes(_compressed_document(kind, zlib.compress(b"abcd")))
    if kind == "tileset":
        pixels = sprite.tilesets[0].pixels
        assert pixels is not None and pixels.data == b"abcd"
    else:
        cel = sprite.frames[0][0]
        if kind == "tilemap":
            assert cel.tilemap is not None and cel.tilemap.tiles == b"abcd"
        else:
            assert cel.pixels is not None and cel.pixels.data == b"abcd"


def test_write_bounds_cached_compressed_data(monkeypatch: pytest.MonkeyPatch) -> None:
    sprite = Sprite(1, 1)
    pixels = sprite.blank_pixels()
    pixels.compressed = zlib.compress(b"x" * 4096, level=0)
    sprite.frames[0][0] = pixels

    def unbounded_decompress(*args: object, **kwargs: object) -> bytes:
        pytest.fail("saving cached data must not use unbounded decompression")

    monkeypatch.setattr(zlib, "decompress", unbounded_decompress)
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.flatten() == bytes(4)


@pytest.mark.parametrize("data", [b"", b"abcd"])
def test_write_preserves_valid_cached_compression(data: bytes) -> None:
    compressed = zlib.compress(data, level=0)
    assert _compress(data, compressed) == compressed


@pytest.mark.parametrize(
    "cached", [b"broken", zlib.compress(b"abcd")[:-4], zlib.compress(b"different")]
)
def test_write_replaces_invalid_or_stale_compression(cached: bytes) -> None:
    assert zlib.decompress(_compress(b"abcd", cached)) == b"abcd"
