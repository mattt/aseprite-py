"""Parse Aseprite documents from bytes."""

from __future__ import annotations

import zlib
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from aseprite._binary import (
    CHUNK_HEADER_SIZE,
    FILE_MAGIC,
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    HEADER_SIZE,
    Reader,
)
from aseprite._errors import FormatError
from aseprite._limits import (
    MAX_PALETTE_COLORS,
    MAX_UNCOMPRESSED_BYTES,
    DocumentBudget,
    bytes_per_tile,
)
from aseprite._model import (
    HEADER_FLAG_GROUP_BLEND,
    HEADER_FLAG_LAYER_OPACITY,
    HEADER_FLAG_LAYER_UUID,
    BlendMode,
    Cel,
    CelExtra,
    CelType,
    Color,
    ColorMode,
    ColorProfile,
    ColorProfileType,
    ExternalFile,
    ExternalFileType,
    Grid,
    Layer,
    LayerType,
    LoopDirection,
    Mask,
    NinePatch,
    Palette,
    Pixels,
    Slice,
    SliceKey,
    Tag,
    Tilemap,
    Tileset,
    UnknownChunk,
)
from aseprite._userdata import read_user_data

if TYPE_CHECKING:
    from aseprite._sprite import Sprite

CHUNK_OLD_PALETTE_4 = 0x0004
CHUNK_OLD_PALETTE_11 = 0x0011
CHUNK_LAYER = 0x2004
CHUNK_CEL = 0x2005
CHUNK_CEL_EXTRA = 0x2006
CHUNK_COLOR_PROFILE = 0x2007
CHUNK_EXTERNAL_FILES = 0x2008
CHUNK_MASK = 0x2016
CHUNK_PATH = 0x2017
CHUNK_TAGS = 0x2018
CHUNK_PALETTE = 0x2019
CHUNK_USER_DATA = 0x2020
CHUNK_SLICE = 0x2022
CHUNK_TILESET = 0x2023


def read_sprite(data: bytes) -> Sprite:
    """Parses bytes and returns a ``Sprite``.

    Imported lazily from ``_sprite`` to avoid a cycle.
    """
    from aseprite._sprite import Sprite

    if len(data) < HEADER_SIZE:
        raise FormatError("file is shorter than the 128-byte header")

    header = Reader(data, 0, HEADER_SIZE)
    file_size = header.u32()
    magic = header.u16()
    if magic != FILE_MAGIC:
        raise FormatError(f"invalid file magic {magic:#06x}")
    nframes = header.u16()
    width = header.u16()
    height = header.u16()
    depth = header.u16()
    try:
        color_mode = ColorMode(depth)
    except ValueError as exc:
        raise FormatError(f"unsupported color depth {depth}") from exc
    flags = header.u32()
    speed = header.u16()
    header.skip(8)
    transparent_index = header.u8()
    header.skip(3)
    num_colors = header.u16()
    pixel_width = header.u8()
    pixel_height = header.u8()
    grid_x = header.i16()
    grid_y = header.i16()
    grid_w = header.u16()
    grid_h = header.u16()

    try:
        sprite = Sprite(width, height, color_mode, empty=True)
    except ValueError as exc:
        raise FormatError(str(exc)) from exc
    budget = DocumentBudget(MAX_UNCOMPRESSED_BYTES)
    sprite.color_profile = None
    sprite.valid_layer_opacity = bool(flags & HEADER_FLAG_LAYER_OPACITY)
    sprite.group_blend = bool(flags & HEADER_FLAG_GROUP_BLEND)
    sprite.deprecated_speed = speed
    sprite.transparent_index = transparent_index
    sprite.num_colors = num_colors or 256
    sprite.pixel_width = pixel_width
    sprite.pixel_height = pixel_height
    sprite.grid = Grid(grid_x, grid_y, grid_w, grid_h)
    sprite._file_size = file_size

    pos = HEADER_SIZE
    last_cel: Cel | None = None
    tag_user_data_left = 0
    tileset_user_mode: Tileset | None = None
    tileset_tile_index = -1
    last_layer: Layer | None = None
    last_slice: Slice | None = None
    current_palette = sprite.palette
    sprite_ud_pending = False

    for frame_index in range(nframes):
        previous_palette = current_palette
        old_palette = current_palette
        saw_palette = False
        if pos + FRAME_HEADER_SIZE > len(data):
            raise FormatError("truncated frame header")
        frame_r = Reader(data, pos, pos + FRAME_HEADER_SIZE)
        frame_size = frame_r.u32()
        frame_magic = frame_r.u16()
        if frame_magic != FRAME_MAGIC:
            raise FormatError(f"invalid frame magic {frame_magic:#06x}")
        old_chunks = frame_r.u16()
        duration = frame_r.u16()
        frame_r.skip(2)
        new_chunks = frame_r.u32()
        nchunks = new_chunks if new_chunks else old_chunks
        if duration == 0:
            duration = speed
        frame = sprite.add_frame(duration)

        chunk_pos = pos + FRAME_HEADER_SIZE
        frame_end = pos + frame_size
        for _ in range(nchunks):
            if (
                chunk_pos + CHUNK_HEADER_SIZE > frame_end
                or chunk_pos + CHUNK_HEADER_SIZE > len(data)
            ):
                raise FormatError("truncated chunk header")
            cr = Reader(data, chunk_pos, chunk_pos + CHUNK_HEADER_SIZE)
            chunk_size = cr.u32()
            chunk_type = cr.u16()
            if chunk_size < CHUNK_HEADER_SIZE:
                raise FormatError("chunk size is smaller than 6 bytes")
            if chunk_pos + chunk_size > frame_end:
                raise FormatError("chunk exceeds frame")
            payload = Reader(
                data, chunk_pos + CHUNK_HEADER_SIZE, chunk_pos + chunk_size
            )

            if chunk_type == CHUNK_OLD_PALETTE_4:
                if not saw_palette:
                    old_palette = _read_old_palette(
                        payload, scale=1, previous=old_palette
                    )
                sprite._had_old_palette_4 = True
            elif chunk_type == CHUNK_OLD_PALETTE_11:
                if not saw_palette:
                    old_palette = _read_old_palette(
                        payload, scale=4, previous=old_palette
                    )
                sprite._had_old_palette_11 = True
            elif chunk_type == CHUNK_PALETTE:
                current_palette = _read_palette(payload, current_palette)
                saw_palette = True
                if frame_index == 0:
                    sprite_ud_pending = True
            elif chunk_type == CHUNK_LAYER:
                layer = _read_layer(payload, bool(flags & HEADER_FLAG_LAYER_UUID))
                if not sprite.valid_layer_opacity:
                    # Aseprite ignores the stored byte unless the header
                    # flag says layer opacity is valid.
                    layer.opacity = 255
                layer.index = len(sprite.layers)
                sprite.layers.append(layer)
                last_layer = layer
                last_cel = None
                last_slice = None
                tileset_user_mode = None
                tag_user_data_left = 0
                sprite_ud_pending = False
            elif chunk_type == CHUNK_CEL:
                cel = _read_cel(payload, color_mode, budget)
                frame._cels[cel.layer_index] = cel
                last_cel = cel
                last_layer = None
                last_slice = None
                tileset_user_mode = None
                tag_user_data_left = 0
                sprite_ud_pending = False
            elif chunk_type == CHUNK_CEL_EXTRA:
                if last_cel is not None:
                    last_cel.extra = _read_cel_extra(payload)
            elif chunk_type == CHUNK_COLOR_PROFILE:
                sprite.color_profile = _read_color_profile(payload)
            elif chunk_type == CHUNK_EXTERNAL_FILES:
                sprite.external_files = _read_external_files(payload)
            elif chunk_type == CHUNK_MASK:
                sprite.masks.append(_read_mask(payload))
            elif chunk_type == CHUNK_PATH:
                sprite.unknown_chunks.append(
                    UnknownChunk(
                        frame_index, chunk_type, payload.raw(payload.remaining())
                    )
                )
            elif chunk_type == CHUNK_TAGS:
                tags = _read_tags(payload)
                for tag in tags:
                    sprite.tags.append(tag)
                tag_user_data_left = len(tags)
                last_cel = None
                last_layer = None
                last_slice = None
                tileset_user_mode = None
                sprite_ud_pending = False
            elif chunk_type == CHUNK_USER_DATA:
                user = read_user_data(payload)
                attached = user if user else None
                if tag_user_data_left > 0:
                    tag = sprite.tags[-tag_user_data_left]
                    tag.user_data = attached
                    tag_user_data_left -= 1
                elif tileset_user_mode is not None:
                    if tileset_tile_index < 0:
                        tileset_user_mode.user_data = attached
                        tileset_tile_index = 0
                    elif tileset_tile_index < tileset_user_mode.tile_count:
                        tile_ud = tileset_user_mode.tile_user_data
                        if tileset_tile_index >= len(tile_ud):
                            tile_ud.extend(
                                [None] * (tileset_tile_index + 1 - len(tile_ud))
                            )
                        tile_ud[tileset_tile_index] = attached
                        tileset_tile_index += 1
                        if tileset_tile_index >= tileset_user_mode.tile_count:
                            tileset_user_mode = None
                elif last_cel is not None:
                    last_cel.user_data = attached
                elif last_layer is not None:
                    last_layer.user_data = attached
                elif last_slice is not None:
                    last_slice.user_data = attached
                elif sprite_ud_pending:
                    sprite.user_data = attached
                    sprite_ud_pending = False
                else:
                    sprite.user_data = attached
            elif chunk_type == CHUNK_SLICE:
                sl = _read_slice(payload)
                sprite.slices.append(sl)
                last_slice = sl
                last_cel = None
                last_layer = None
                tileset_user_mode = None
                tag_user_data_left = 0
                sprite_ud_pending = False
            elif chunk_type == CHUNK_TILESET:
                tileset = _read_tileset(payload, color_mode, budget)
                sprite.tilesets.append(tileset)
                tileset_user_mode = tileset
                tileset_tile_index = -1
                last_cel = None
                last_layer = None
                last_slice = None
                tag_user_data_left = 0
                sprite_ud_pending = False
            else:
                sprite.unknown_chunks.append(
                    UnknownChunk(
                        frame_index, chunk_type, payload.raw(payload.remaining())
                    )
                )

            chunk_pos += chunk_size
        if not saw_palette:
            current_palette = old_palette
        if frame_index == 0:
            sprite.palette = current_palette
        elif current_palette != previous_palette:
            frame.palette = current_palette
        pos = frame_end

    for tileset in sprite.tilesets:
        # Aseprite writes an empty user-data chunk for every tile.
        # Trailing empty entries carry no information and are not written back.
        tile_ud = tileset.tile_user_data
        while tile_ud and tile_ud[-1] is None:
            tile_ud.pop()

    return sprite


def _read_old_palette(r: Reader, scale: int, previous: Palette) -> Palette:
    packets = r.u16()
    colors = [replace(color) for color in previous]
    index = 0
    for _ in range(packets):
        skip = r.u8()
        count = r.u8() or 256
        index += skip
        for _i in range(count):
            red = min(r.u8() * scale, 255)
            green = min(r.u8() * scale, 255)
            blue = min(r.u8() * scale, 255)
            if index >= MAX_PALETTE_COLORS:
                raise FormatError(f"palette size exceeds {MAX_PALETTE_COLORS}")
            while len(colors) <= index:
                colors.append(Color(0, 0, 0, 255))
            colors[index] = Color(red, green, blue, 255)
            index += 1
    return Palette(colors)


def _read_palette(r: Reader, previous: Palette) -> Palette:
    size = r.u32()
    first = r.u32()
    last = r.u32()
    r.skip(8)
    if size > MAX_PALETTE_COLORS:
        raise FormatError(f"palette size exceeds {MAX_PALETTE_COLORS}")
    if size == 0:
        return Palette()
    if first > last or last >= size:
        raise FormatError("palette index range is invalid")
    colors = [replace(color) for color in previous.colors[:size]]
    colors.extend(Color(0, 0, 0, 0) for _ in range(size - len(colors)))
    for index in range(first, last + 1):
        flags = r.u16()
        entry = Color(r.u8(), r.u8(), r.u8(), r.u8())
        if flags & 1:
            entry.name = r.string()
        if 0 <= index < size:
            colors[index] = entry
    return Palette(colors)


def _read_layer(r: Reader, has_uuid: bool) -> Layer:
    flags = r.u16()
    kind_value = r.u16()
    try:
        kind = LayerType(kind_value)
    except ValueError as exc:
        raise FormatError(f"unsupported layer type {kind_value}") from exc
    child_level = r.u16()
    r.skip(4)
    blend = BlendMode(r.u16())
    opacity = r.u8()
    r.skip(3)
    name = r.string()
    layer = Layer.from_flags(name, flags, kind, child_level, blend, opacity)
    if kind is LayerType.TILEMAP:
        layer.tileset_index = r.u32()
    if has_uuid and r.remaining() >= 16:
        raw = r.uuid()
        if any(raw):
            layer.uuid = UUID(bytes=raw)
    return layer


def _pixels(
    width: int,
    height: int,
    data: bytes,
    color_mode: ColorMode,
    compressed: bytes | None = None,
) -> Pixels:
    try:
        return Pixels(width, height, data, color_mode, compressed=compressed)
    except ValueError as exc:
        raise FormatError(str(exc)) from exc


def _decompress(raw: bytes, max_size: int, budget: DocumentBudget) -> bytes:
    if max_size > MAX_UNCOMPRESSED_BYTES:
        raise FormatError("decompressed data exceeds the size limit")
    budget.allow(max_size)
    try:
        decoder = zlib.decompressobj()
        # Request one extra byte so excess output is detected even when
        # it is still encoded in decoder.unconsumed_tail.
        out = decoder.decompress(raw, max_size + 1)
        if len(out) > max_size:
            raise FormatError("decompressed data exceeds the size limit")
        if not decoder.eof:
            raise FormatError("compressed image has an incomplete zlib stream")
        budget.charge(len(out))
        return out
    except zlib.error as exc:
        raise FormatError("cel image is not valid zlib data") from exc


def _read_cel(r: Reader, color_mode: ColorMode, budget: DocumentBudget) -> Cel:
    layer_index = r.u16()
    x = r.i16()
    y = r.i16()
    opacity = r.u8()
    cel_type_value = r.u16()
    try:
        cel_type = CelType(cel_type_value)
    except ValueError as exc:
        raise FormatError(f"unsupported cel type {cel_type_value}") from exc
    z_index = r.i16()
    r.skip(5)
    cel = Cel(layer_index=layer_index, x=x, y=y, opacity=opacity, z_index=z_index)
    if cel_type is CelType.RAW:
        width = r.u16()
        height = r.u16()
        data = r.raw(r.remaining())
        budget.charge(len(data))
        cel.pixels = _pixels(width, height, data, color_mode)
        cel.raw = True
    elif cel_type is CelType.LINKED:
        cel.link = r.u16()
    elif cel_type is CelType.COMPRESSED:
        width = r.u16()
        height = r.u16()
        compressed = r.raw(r.remaining())
        expected = width * height * color_mode.bytes_per_pixel
        data = _decompress(compressed, expected, budget)
        cel.pixels = _pixels(width, height, data, color_mode, compressed=compressed)
    elif cel_type is CelType.COMPRESSED_TILEMAP:
        width = r.u16()
        height = r.u16()
        bits = r.u16()
        tile_id = r.u32()
        x_flip = r.u32()
        y_flip = r.u32()
        d_flip = r.u32()
        r.skip(10)
        compressed = r.raw(r.remaining())
        expected = width * height * bytes_per_tile(bits)
        tiles = _decompress(compressed, expected, budget)
        cel.tilemap = Tilemap(
            width=width,
            height=height,
            bits_per_tile=bits,
            tile_id_mask=tile_id,
            x_flip_mask=x_flip,
            y_flip_mask=y_flip,
            d_flip_mask=d_flip,
            tiles=tiles,
            compressed=compressed,
        )
    else:
        raise FormatError(f"unsupported cel type {int(cel_type)}")
    return cel


def _read_cel_extra(r: Reader) -> CelExtra:
    flags = r.u32()
    extra = CelExtra(
        precise_x=r.u32(), precise_y=r.u32(), width=r.u32(), height=r.u32()
    )
    if r.remaining() >= 16:
        r.skip(16)
    _ = flags
    return extra


def _read_color_profile(r: Reader) -> ColorProfile:
    ptype = ColorProfileType(r.u16())
    flags = r.u16()
    gamma = r.u32()
    r.skip(8)
    icc = b""
    if ptype is ColorProfileType.ICC:
        length = r.u32()
        icc = r.raw(length)
    return ColorProfile(
        kind=ptype,
        use_fixed_gamma=bool(flags & 1),
        gamma=gamma,
        icc=icc,
    )


def _read_external_files(r: Reader) -> list[ExternalFile]:
    count = r.u32()
    r.skip(8)
    files: list[ExternalFile] = []
    for _ in range(count):
        entry_id = r.u32()
        ftype = ExternalFileType(r.u8())
        r.skip(7)
        name = r.string()
        files.append(ExternalFile(id=entry_id, kind=ftype, name=name))
    return files


def _read_mask(r: Reader) -> Mask:
    x = r.i16()
    y = r.i16()
    width = r.u16()
    height = r.u16()
    r.skip(8)
    name = r.string()
    size = height * ((width + 7) // 8)
    bitmap = r.raw(size)
    return Mask(x=x, y=y, width=width, height=height, name=name, bitmap=bitmap)


def _read_tags(r: Reader) -> list[Tag]:
    count = r.u16()
    r.skip(8)
    tags: list[Tag] = []
    for _ in range(count):
        frm = r.u16()
        to = r.u16()
        direction = LoopDirection(r.u8())
        repeat = r.u16()
        r.skip(6)
        color = (r.u8(), r.u8(), r.u8())
        r.skip(1)
        name = r.string()
        tags.append(
            Tag(
                name=name,
                from_frame=frm,
                to_frame=to,
                direction=direction,
                repeat=repeat,
                color=color,
            )
        )
    return tags


def _read_slice(r: Reader) -> Slice:
    nkeys = r.u32()
    flags = r.u32()
    r.skip(4)
    name = r.string()
    keys: list[SliceKey] = []
    for _ in range(nkeys):
        frame = r.u32()
        x = r.i32()
        y = r.i32()
        width = r.u32()
        height = r.u32()
        nine = None
        pivot = None
        if flags & 1:
            nine = NinePatch(r.i32(), r.i32(), r.u32(), r.u32())
        if flags & 2:
            pivot = (r.i32(), r.i32())
        keys.append(
            SliceKey(
                frame=frame,
                x=x,
                y=y,
                width=width,
                height=height,
                nine_patch=nine,
                pivot=pivot,
            )
        )
    return Slice(name=name, keys=keys)


def _read_tileset(r: Reader, color_mode: ColorMode, budget: DocumentBudget) -> Tileset:
    tileset_id = r.u32()
    flags = r.u32()
    tile_count = r.u32()
    tile_width = r.u16()
    tile_height = r.u16()
    base_index = r.i16()
    r.skip(14)
    name = r.string()
    external_file_id = None
    external_tileset_id = None
    pixels = None
    compressed = None
    if flags & 1:
        external_file_id = r.u32()
        external_tileset_id = r.u32()
    if flags & 2:
        length = r.u32()
        compressed = r.raw(length)
        expected = tile_width * tile_height * tile_count * color_mode.bytes_per_pixel
        raw = _decompress(compressed, expected, budget)
        if len(raw) < expected:
            # Aseprite itself writes and accepts tileset images shorter than
            # tile_count tiles; the missing tiles are transparent.
            budget.charge(expected - len(raw))
            raw += bytes(expected - len(raw))
        image_height = tile_height * tile_count
        pixels = _pixels(
            tile_width, image_height, raw, color_mode, compressed=compressed
        )
    return Tileset(
        id=tileset_id,
        name=name,
        tile_count=tile_count,
        tile_width=tile_width,
        tile_height=tile_height,
        base_index=base_index,
        flags=flags,
        pixels=pixels,
        compressed=compressed,
        external_file_id=external_file_id,
        external_tileset_id=external_tileset_id,
    )
