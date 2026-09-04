"""Serialize a sprite to Aseprite bytes."""

from __future__ import annotations

import zlib
from typing import TYPE_CHECKING

from aseprite._binary import (
    FILE_MAGIC,
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    HEADER_SIZE,
    Writer,
)
from aseprite._errors import AsepriteError
from aseprite._model import (
    HEADER_FLAG_LAYER_OPACITY,
    HEADER_FLAG_LAYER_UUID,
    TILESET_FLAG_EMBEDDED,
    TILESET_FLAG_EXTERNAL,
    ColorMode,
    ColorProfileType,
    LayerType,
    Palette,
    Pixels,
    UserData,
)
from aseprite._userdata import write_user_data

if TYPE_CHECKING:
    from aseprite._sprite import Sprite

CHUNK_OLD_PALETTE_4 = 0x0004
CHUNK_LAYER = 0x2004
CHUNK_CEL = 0x2005
CHUNK_CEL_EXTRA = 0x2006
CHUNK_COLOR_PROFILE = 0x2007
CHUNK_EXTERNAL_FILES = 0x2008
CHUNK_MASK = 0x2016
CHUNK_TAGS = 0x2018
CHUNK_PALETTE = 0x2019
CHUNK_USER_DATA = 0x2020
CHUNK_SLICE = 0x2022
CHUNK_TILESET = 0x2023


def write_sprite(sprite: Sprite) -> bytes:
    """Returns the Aseprite file bytes for ``sprite``."""
    if not sprite.frames:
        raise AsepriteError("a sprite must have at least one frame")

    w = Writer()
    _write_header(w, sprite, file_size=0)

    unknown_by_frame: dict[int, list] = {}
    for chunk in sprite.unknown_chunks:
        unknown_by_frame.setdefault(chunk.frame_index, []).append(chunk)

    for frame_index, frame in enumerate(sprite.frames):
        frame_start = w.tell()
        w.u32(0)
        w.u16(FRAME_MAGIC)
        old_count_at = w.tell()
        w.u16(0)
        w.u16(frame.duration_ms)
        w.pad(2)
        new_count_at = w.tell()
        w.u32(0)
        nchunks = 0

        def emit(chunk_type: int, payload: bytes) -> None:
            nonlocal nchunks
            w.u32(6 + len(payload))
            w.u16(chunk_type)
            w.raw(payload)
            nchunks += 1

        def emit_built(chunk_type: int, build) -> None:  # noqa: ANN001
            inner = Writer()
            build(inner)
            emit(chunk_type, bytes(inner.buf))

        if frame_index == 0:
            if sprite.color_profile is not None:
                emit_built(
                    CHUNK_COLOR_PROFILE, lambda iw: _write_color_profile(iw, sprite)
                )
            if sprite.external_files:
                emit_built(
                    CHUNK_EXTERNAL_FILES, lambda iw: _write_external_files(iw, sprite)
                )
            emit_built(CHUNK_PALETTE, lambda iw: _write_palette(iw, sprite.palette))
            if _should_write_old_palette(sprite):
                emit_built(
                    CHUNK_OLD_PALETTE_4,
                    lambda iw: _write_old_palette(iw, sprite.palette),
                )
            sprite_ud = sprite.user_data
            if sprite_ud:
                emit_built(
                    CHUNK_USER_DATA, lambda iw, u=sprite_ud: write_user_data(iw, u)
                )
            for tileset in sprite.tilesets:
                emit_built(
                    CHUNK_TILESET,
                    lambda iw, t=tileset: _write_tileset(iw, t, sprite.color_mode),
                )
                if tileset.user_data or any(tileset.tile_user_data):
                    emit_built(
                        CHUNK_USER_DATA,
                        lambda iw, t=tileset: write_user_data(
                            iw, t.user_data or UserData()
                        ),
                    )
                    ntiles = tileset.tile_count
                    uds = list(tileset.tile_user_data) + [None] * max(
                        0, ntiles - len(tileset.tile_user_data)
                    )
                    for tile_ud in uds[:ntiles]:
                        emit_built(
                            CHUNK_USER_DATA,
                            lambda iw, u=tile_ud: write_user_data(iw, u or UserData()),
                        )
            for layer in sprite.layers:
                emit_built(
                    CHUNK_LAYER, lambda iw, ly=layer: _write_layer(iw, ly, sprite)
                )
                layer_ud = layer.user_data
                if layer_ud:
                    emit_built(
                        CHUNK_USER_DATA,
                        lambda iw, u=layer_ud: write_user_data(iw, u),
                    )

        for cel in frame.cels:
            emit_built(CHUNK_CEL, lambda iw, c=cel: _write_cel(iw, c))
            if cel.extra is not None:
                emit_built(CHUNK_CEL_EXTRA, lambda iw, c=cel: _write_cel_extra(iw, c))
            cel_ud = cel.user_data
            if cel_ud:
                emit_built(CHUNK_USER_DATA, lambda iw, u=cel_ud: write_user_data(iw, u))

        if frame_index == 0:
            if len(sprite.tags):
                emit_built(CHUNK_TAGS, lambda iw: _write_tags(iw, sprite))
                if any(tag.user_data for tag in sprite.tags):
                    for tag in sprite.tags:
                        emit_built(
                            CHUNK_USER_DATA,
                            lambda iw, t=tag: write_user_data(
                                iw, t.user_data or UserData()
                            ),
                        )
            for sl in sprite.slices:
                emit_built(CHUNK_SLICE, lambda iw, s=sl: _write_slice(iw, s))
                slice_ud = sl.user_data
                if slice_ud:
                    emit_built(
                        CHUNK_USER_DATA,
                        lambda iw, u=slice_ud: write_user_data(iw, u),
                    )
            for mask in sprite.masks:
                emit_built(CHUNK_MASK, lambda iw, m=mask: _write_mask(iw, m))

        for chunk in unknown_by_frame.get(frame_index, []):
            emit(chunk.chunk_type, chunk.data)

        frame_size = w.tell() - frame_start
        w.patch_u32(frame_start, frame_size)
        if nchunks >= 0xFFFF:
            w.patch_u16(old_count_at, 0xFFFF)
            w.patch_u32(new_count_at, nchunks)
        else:
            w.patch_u16(old_count_at, nchunks)
            w.patch_u32(new_count_at, nchunks)

    w.patch_u32(0, w.tell())
    if w.tell() < HEADER_SIZE + FRAME_HEADER_SIZE:
        raise AsepriteError("written file is truncated")
    return bytes(w.buf)


def _write_header(w: Writer, sprite: Sprite, file_size: int) -> None:
    flags = sprite.flags | HEADER_FLAG_LAYER_OPACITY
    if any(layer.uuid is not None for layer in sprite.layers):
        flags |= HEADER_FLAG_LAYER_UUID
    w.u32(file_size)
    w.u16(FILE_MAGIC)
    w.u16(len(sprite.frames))
    w.u16(sprite.width)
    w.u16(sprite.height)
    w.u16(int(sprite.color_mode))
    w.u32(flags)
    speed = sprite.deprecated_speed or (
        sprite.frames[0].duration_ms if sprite.frames else 100
    )
    w.u16(speed)
    w.pad(8)
    w.u8(sprite.transparent_index)
    w.pad(3)
    ncolors = len(sprite.palette) or sprite.num_colors or 0
    w.u16(ncolors)
    w.u8(sprite.pixel_width)
    w.u8(sprite.pixel_height)
    w.i16(sprite.grid.x)
    w.i16(sprite.grid.y)
    w.u16(sprite.grid.width)
    w.u16(sprite.grid.height)
    w.pad(84)


def _should_write_old_palette(sprite: Sprite) -> bool:
    if sprite._had_old_palette_4:
        return True
    if not sprite.palette.colors:
        return False
    if len(sprite.palette) > 256:
        return False
    return all(c.a == 255 for c in sprite.palette)


def _write_old_palette(w: Writer, palette: Palette) -> None:
    colors = palette.colors[:256]
    w.u16(1)
    w.u8(0)
    w.u8(0 if len(colors) == 256 else len(colors))
    for color in colors:
        w.u8(color.r)
        w.u8(color.g)
        w.u8(color.b)


def _write_palette(w: Writer, palette: Palette) -> None:
    colors = palette.colors
    w.u32(len(colors))
    w.u32(0)
    w.u32(len(colors) - 1 if colors else 0)
    w.pad(8)
    for color in colors:
        flags = 1 if color.name else 0
        w.u16(flags)
        w.u8(color.r)
        w.u8(color.g)
        w.u8(color.b)
        w.u8(color.a)
        if color.name:
            w.string(color.name)


def _write_layer(w: Writer, layer, sprite: Sprite) -> None:  # noqa: ANN001
    w.u16(layer.flags)
    w.u16(int(layer.type))
    w.u16(layer.child_level)
    w.u16(0)
    w.u16(0)
    w.u16(int(layer.blend_mode))
    w.u8(layer.opacity)
    w.pad(3)
    w.string(layer.name)
    if layer.type is LayerType.TILEMAP:
        w.u32(layer.tileset_index or 0)
    if layer.uuid is not None:
        w.uuid(layer.uuid.bytes)
    elif sprite.flags & HEADER_FLAG_LAYER_UUID:
        w.pad(16)


def _compress(data: bytes, original: bytes | None) -> bytes:
    if original is not None:
        try:
            if zlib.decompress(original) == data:
                return original
        except zlib.error:
            pass
    return zlib.compress(data, 9)


def _write_cel(w: Writer, cel) -> None:  # noqa: ANN001
    w.u16(cel.layer_index)
    w.i16(cel.x)
    w.i16(cel.y)
    w.u8(cel.opacity)
    if cel.link is not None:
        w.u16(1)
        w.i16(cel.z_index)
        w.pad(5)
        w.u16(cel.link)
        return
    if cel.tilemap is not None:
        tm = cel.tilemap
        w.u16(3)
        w.i16(cel.z_index)
        w.pad(5)
        w.u16(tm.width)
        w.u16(tm.height)
        w.u16(tm.bits_per_tile)
        w.u32(tm.tile_id_mask)
        w.u32(tm.x_flip_mask)
        w.u32(tm.y_flip_mask)
        w.u32(tm.d_flip_mask)
        w.pad(10)
        w.raw(_compress(tm.tiles, tm.compressed))
        return
    pixels: Pixels | None = cel.pixels
    if pixels is None:
        raise AsepriteError("cel has no pixel data")
    if cel.raw:
        w.u16(0)
        w.i16(cel.z_index)
        w.pad(5)
        w.u16(pixels.width)
        w.u16(pixels.height)
        w.raw(pixels.data)
        return
    w.u16(2)
    w.i16(cel.z_index)
    w.pad(5)
    w.u16(pixels.width)
    w.u16(pixels.height)
    w.raw(_compress(pixels.data, pixels.compressed))


def _write_cel_extra(w: Writer, cel) -> None:  # noqa: ANN001
    extra = cel.extra
    w.u32(1)
    w.u32(extra.precise_x)
    w.u32(extra.precise_y)
    w.u32(extra.width)
    w.u32(extra.height)
    w.pad(16)


def _write_color_profile(w: Writer, sprite: Sprite) -> None:
    profile = sprite.color_profile
    if profile is None:
        raise AsepriteError("color profile is missing")
    w.u16(int(profile.type))
    w.u16(1 if profile.use_fixed_gamma else 0)
    w.u32(profile.gamma)
    w.pad(8)
    if profile.type is ColorProfileType.ICC:
        w.u32(len(profile.icc))
        w.raw(profile.icc)


def _write_external_files(w: Writer, sprite: Sprite) -> None:
    w.u32(len(sprite.external_files))
    w.pad(8)
    for entry in sprite.external_files:
        w.u32(entry.id)
        w.u8(int(entry.type))
        w.pad(7)
        w.string(entry.name)


def _write_tags(w: Writer, sprite: Sprite) -> None:
    w.u16(len(sprite.tags))
    w.pad(8)
    for tag in sprite.tags:
        w.u16(tag.from_frame)
        w.u16(tag.to_frame)
        w.u8(int(tag.direction))
        w.u16(tag.repeat)
        w.pad(6)
        w.u8(tag.color[0])
        w.u8(tag.color[1])
        w.u8(tag.color[2])
        w.u8(0)
        w.string(tag.name)


def _write_slice(w: Writer, sl) -> None:  # noqa: ANN001
    flags = 0
    if any(k.nine_patch for k in sl.keys):
        flags |= 1
    if any(k.pivot for k in sl.keys):
        flags |= 2
    w.u32(len(sl.keys))
    w.u32(flags)
    w.u32(0)
    w.string(sl.name)
    for key in sl.keys:
        w.u32(key.frame)
        w.i32(key.x)
        w.i32(key.y)
        w.u32(key.width)
        w.u32(key.height)
        if flags & 1:
            nine = key.nine_patch
            if nine is None:
                w.i32(0)
                w.i32(0)
                w.u32(0)
                w.u32(0)
            else:
                w.i32(nine.x)
                w.i32(nine.y)
                w.u32(nine.width)
                w.u32(nine.height)
        if flags & 2:
            pivot = key.pivot or (0, 0)
            w.i32(pivot[0])
            w.i32(pivot[1])


def _write_mask(w: Writer, mask) -> None:  # noqa: ANN001
    w.i16(mask.x)
    w.i16(mask.y)
    w.u16(mask.width)
    w.u16(mask.height)
    w.pad(8)
    w.string(mask.name)
    w.raw(mask.bitmap)


def _write_tileset(w: Writer, tileset, color_mode: ColorMode) -> None:  # noqa: ANN001
    w.u32(tileset.id)
    w.u32(tileset.flags)
    w.u32(tileset.tile_count)
    w.u16(tileset.tile_width)
    w.u16(tileset.tile_height)
    w.i16(tileset.base_index)
    w.pad(14)
    w.string(tileset.name)
    if tileset.flags & TILESET_FLAG_EXTERNAL:
        w.u32(tileset.external_file_id or 0)
        w.u32(tileset.external_tileset_id or 0)
    if tileset.flags & TILESET_FLAG_EMBEDDED:
        compressed = _compress(tileset.pixels, tileset.compressed)
        w.u32(len(compressed))
        w.raw(compressed)
