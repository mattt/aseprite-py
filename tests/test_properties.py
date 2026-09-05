"""Property-based tests.

Random documents built from every chunk type must survive a write and read
unchanged, and corrupt bytes must fail with ``FormatError`` rather than
anything else. Run a longer search with ``HYPOTHESIS_PROFILE=long``.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aseprite import (
    BlendMode,
    CelExtra,
    Color,
    ColorMode,
    ColorProfile,
    ColorProfileType,
    ExternalFile,
    ExternalFileType,
    FormatError,
    Grid,
    LayerType,
    LoopDirection,
    Mask,
    NinePatch,
    Pixels,
    PropertiesMap,
    PropertyType,
    SliceKey,
    Sprite,
    Tilemap,
    Tileset,
    UnknownChunk,
    UserData,
    UserProperty,
)
from aseprite._limits import bytes_per_tile
from aseprite._model import (
    TILESET_FLAG_EMBEDDED,
    TILESET_FLAG_EMPTY_IS_ZERO,
    TILESET_FLAG_EXTERNAL,
)
from aseprite._render import _blend_normal

u8 = st.integers(0, 255)
u16 = st.integers(0, 0xFFFF)
u32 = st.integers(0, 0xFFFFFFFF)
i16 = st.integers(-0x8000, 0x7FFF)
i32 = st.integers(-0x80000000, 0x7FFFFFFF)
text = st.text(st.characters(codec="utf-8"), max_size=12)
names = st.text(st.characters(codec="utf-8"), min_size=1, max_size=12)
colors = st.builds(Color, u8, u8, u8, u8, name=st.none() | names)

_MASKS = {
    8: (0x1F, 0x20, 0x40, 0x80),
    16: (0x1FFF, 0x2000, 0x4000, 0x8000),
    32: (0x1FFFFFFF, 0x20000000, 0x40000000, 0x80000000),
}


def _value(kind: PropertyType, depth: int) -> st.SearchStrategy[object]:
    if kind is PropertyType.BOOL:
        return st.booleans()
    if kind is PropertyType.INT8:
        return st.integers(-128, 127)
    if kind is PropertyType.UINT8:
        return u8
    if kind is PropertyType.INT16:
        return i16
    if kind is PropertyType.UINT16:
        return u16
    if kind is PropertyType.INT32:
        return i32
    if kind is PropertyType.UINT32:
        return u32
    if kind is PropertyType.INT64:
        return st.integers(-(2**63), 2**63 - 1)
    if kind in (PropertyType.UINT64, PropertyType.FIXED):
        return st.integers(0, 2**64 - 1 if kind is PropertyType.UINT64 else 2**32 - 1)
    if kind is PropertyType.FLOAT:
        return st.floats(width=32, allow_nan=False)
    if kind is PropertyType.DOUBLE:
        return st.floats(allow_nan=False)
    if kind is PropertyType.STRING:
        return text
    if kind in (PropertyType.POINT, PropertyType.SIZE):
        return st.tuples(i32, i32)
    if kind is PropertyType.RECT:
        return st.tuples(i32, i32, i32, i32)
    if kind is PropertyType.UUID:
        return st.uuids()
    if kind is PropertyType.PROPERTIES:
        if depth >= 2:
            return st.just([])
        return st.lists(_property(depth + 1), max_size=2)
    if depth >= 2:
        return st.just((int(PropertyType.INT32), []))
    kinds = st.sampled_from(list(PropertyType))
    mixed = st.lists(
        kinds.flatmap(lambda k: st.tuples(st.just(k), _value(k, depth + 1))),
        max_size=3,
    ).map(lambda items: (0, items))
    uniform = kinds.flatmap(
        lambda k: st.lists(_value(k, depth + 1), max_size=3).map(
            lambda items: (int(k), items)
        )
    )
    return mixed | uniform


def _property(depth: int) -> st.SearchStrategy[UserProperty]:
    return st.sampled_from(list(PropertyType)).flatmap(
        lambda k: st.builds(UserProperty, names, st.just(k), _value(k, depth))
    )


user_data = st.none() | st.builds(
    UserData,
    text=st.none() | text,
    color=st.none() | st.builds(Color, u8, u8, u8, u8),
    properties=st.lists(
        st.builds(PropertiesMap, u32, st.lists(_property(0), max_size=3)),
        max_size=2,
    ),
).map(lambda data: data if data else None)


def _pixels(mode: ColorMode, width: int, height: int) -> st.SearchStrategy[Pixels]:
    size = width * height * mode.bytes_per_pixel
    return st.binary(min_size=size, max_size=size).map(
        lambda data: Pixels(width, height, data, mode)
    )


@st.composite
def color_profiles(draw: st.DrawFn) -> ColorProfile:
    kind = draw(st.sampled_from(list(ColorProfileType)))
    icc = draw(st.binary(max_size=16)) if kind is ColorProfileType.ICC else b""
    return ColorProfile(kind, draw(st.booleans()), draw(u32), icc)


@st.composite
def tilesets(draw: st.DrawFn, index: int, mode: ColorMode) -> Tileset:
    tile_width, tile_height = draw(st.integers(1, 3)), draw(st.integers(1, 3))
    count = draw(st.integers(1, 3))
    variant = draw(st.sampled_from(["embedded", "external", "none"]))
    tileset = Tileset(index, draw(names), count, tile_width, tile_height)
    tileset.base_index = draw(i16)
    if variant == "embedded":
        tileset.flags = TILESET_FLAG_EMBEDDED | (
            TILESET_FLAG_EMPTY_IS_ZERO if draw(st.booleans()) else 0
        )
        tileset.pixels = draw(_pixels(mode, tile_width, tile_height * count))
    elif variant == "external":
        tileset.flags = TILESET_FLAG_EXTERNAL
        tileset.external_file_id = draw(u32)
        tileset.external_tileset_id = draw(u32)
    else:
        tileset.flags = 0
    tileset.user_data = draw(user_data)
    tile_user_data = draw(st.lists(user_data, max_size=count))
    while tile_user_data and tile_user_data[-1] is None:
        tile_user_data.pop()
    tileset.tile_user_data = tile_user_data
    return tileset


@st.composite
def tilemaps(draw: st.DrawFn) -> Tilemap:
    width, height = draw(st.integers(1, 4)), draw(st.integers(1, 4))
    bits = draw(st.sampled_from([8, 16, 32]))
    size = width * height * bytes_per_tile(bits)
    tiles = draw(st.binary(min_size=size, max_size=size))
    return Tilemap(width, height, bits, *_MASKS[bits], tiles)


@st.composite
def sprites(draw: st.DrawFn) -> Sprite:
    mode = draw(st.sampled_from(list(ColorMode)))
    width, height = draw(st.integers(1, 8)), draw(st.integers(1, 8))
    sprite = Sprite(width, height, mode, empty=True)
    sprite.group_blend = draw(st.booleans())
    sprite.valid_layer_opacity = draw(st.booleans())
    sprite.transparent_index = draw(u8)
    sprite.pixel_width, sprite.pixel_height = draw(u8), draw(u8)
    sprite.grid = Grid(draw(i16), draw(i16), draw(u16), draw(u16))
    sprite.color_profile = draw(st.none() | color_profiles())
    sprite.palette.extend(draw(st.lists(colors, max_size=20)))
    sprite.user_data = draw(user_data)
    sprite.tilesets.extend(
        draw(tilesets(i, mode)) for i in range(draw(st.integers(0, 2)))
    )

    groups = []
    kinds = [LayerType.IMAGE, LayerType.GROUP]
    if sprite.tilesets:
        kinds.append(LayerType.TILEMAP)
    for _ in range(draw(st.integers(1, 5))):
        kind = draw(st.sampled_from(kinds))
        parent = (
            draw(st.sampled_from(groups)) if groups and draw(st.booleans()) else None
        )
        layer = sprite.add_layer(
            draw(names),
            parent=parent,
            kind=kind,
            blend_mode=draw(st.sampled_from(list(BlendMode))),
            opacity=draw(u8) if sprite.valid_layer_opacity else 255,
            tileset_index=(
                draw(st.integers(0, len(sprite.tilesets) - 1))
                if kind is LayerType.TILEMAP
                else None
            ),
        )
        for flag in (
            "visible",
            "editable",
            "lock_movement",
            "background",
            "prefer_linked_cels",
            "collapsed",
            "reference",
        ):
            setattr(layer, flag, draw(st.booleans()))
        layer.uuid = draw(st.none() | st.uuids(version=4))
        layer.user_data = draw(user_data)
        if kind is LayerType.GROUP:
            groups.append(layer)

    frame_count = draw(st.integers(1, 3))
    for frame_index in range(frame_count):
        frame = sprite.add_frame(draw(st.integers(1, 0xFFFF)))
        for layer in sprite.layers:
            if layer.kind is LayerType.GROUP or draw(st.booleans()):
                continue
            x, y = draw(st.integers(-4, width)), draw(st.integers(-4, height))
            opacity, z_index = draw(u8), draw(st.integers(-3, 3))
            if frame_index and draw(st.booleans()):
                cel = frame.set_linked_cel(
                    layer,
                    draw(st.integers(0, frame_index - 1)),
                    x=x,
                    y=y,
                    opacity=opacity,
                    z_index=z_index,
                )
            elif layer.kind is LayerType.TILEMAP:
                cel = frame.set_tilemap_cel(
                    layer, draw(tilemaps()), x, y, opacity=opacity, z_index=z_index
                )
            else:
                cel_width = draw(st.integers(0, width + 2))
                cel_height = draw(st.integers(0, height + 2))
                cel = frame.set_cel(
                    layer,
                    draw(_pixels(mode, cel_width, cel_height)),
                    x,
                    y,
                    opacity=opacity,
                    z_index=z_index,
                )
                cel.raw = draw(st.booleans())
            if draw(st.booleans()):
                cel.extra = CelExtra(draw(u32), draw(u32), draw(u32), draw(u32))
            cel.user_data = draw(user_data)

    for _ in range(draw(st.integers(0, 2))):
        first, last = sorted(
            (
                draw(st.integers(0, frame_count - 1)),
                draw(st.integers(0, frame_count - 1)),
            )
        )
        tag = sprite.add_tag(
            draw(names),
            first,
            last,
            direction=draw(st.sampled_from(list(LoopDirection))),
            repeat=draw(u16),
        )
        tag.color = (draw(u8), draw(u8), draw(u8))
        tag.user_data = draw(user_data)

    for _ in range(draw(st.integers(0, 2))):
        has_center, has_pivot = draw(st.booleans()), draw(st.booleans())
        keys = [
            SliceKey(
                draw(st.integers(0, frame_count - 1)),
                draw(i32),
                draw(i32),
                draw(u32),
                draw(u32),
                NinePatch(draw(i32), draw(i32), draw(u32), draw(u32))
                if has_center
                else None,
                (draw(i32), draw(i32)) if has_pivot else None,
            )
            for _ in range(draw(st.integers(0, 2)))
        ]
        sprite.add_slice(draw(names), keys).user_data = draw(user_data)

    if draw(st.booleans()):
        mask_width, mask_height = draw(st.integers(0, 10)), draw(st.integers(0, 10))
        size = mask_height * ((mask_width + 7) // 8)
        sprite.masks.append(
            Mask(
                draw(i16),
                draw(i16),
                mask_width,
                mask_height,
                draw(names),
                draw(st.binary(min_size=size, max_size=size)),
            )
        )
    for entry_id in range(draw(st.integers(0, 2))):
        sprite.external_files.append(
            ExternalFile(
                entry_id, draw(st.sampled_from(list(ExternalFileType))), draw(names)
            )
        )
    if draw(st.booleans()):
        sprite.unknown_chunks.append(
            UnknownChunk(
                draw(st.integers(0, frame_count - 1)),
                draw(st.sampled_from([0x2017, 0x2099])),
                draw(st.binary(max_size=16)),
            )
        )
    return sprite


@given(sprites())
def test_write_then_read_is_identity(sprite: Sprite) -> None:
    data = sprite.to_bytes()
    loaded = Sprite.from_bytes(data)
    assert loaded == sprite
    assert loaded.to_bytes() == data


@given(sprites())
def test_flatten_returns_canvas_sized_rgba(sprite: Sprite) -> None:
    for frame in range(len(sprite.frames)):
        assert len(sprite.flatten(frame)) == sprite.width * sprite.height * 4


@given(sprites(), st.floats(0, 1))
def test_truncated_file_is_format_error(sprite: Sprite, fraction: float) -> None:
    data = sprite.to_bytes()
    cut = int(fraction * (len(data) - 1))
    with pytest.raises(FormatError):
        Sprite.from_bytes(data[:cut])


@given(
    sprites(),
    st.lists(st.tuples(st.integers(0, 1 << 20), u8), min_size=1, max_size=8),
)
def test_corrupt_bytes_fail_cleanly(
    sprite: Sprite, edits: list[tuple[int, int]]
) -> None:
    data = bytearray(sprite.to_bytes())
    for offset, value in edits:
        data[offset % len(data)] = value
    try:
        loaded = Sprite.from_bytes(bytes(data))
    except FormatError:
        return
    if loaded.width * loaded.height <= 1 << 16:
        for frame in range(len(loaded.frames)):
            try:
                loaded.flatten(frame)
            except ValueError:
                pass
    if loaded.frames:
        try:
            loaded.to_bytes()
        except ValueError:
            pass


@given(st.binary(min_size=4, max_size=4), st.binary(min_size=4, max_size=4), u8)
def test_blend_normal_stays_in_range(dst: bytes, src: bytes, opacity: int) -> None:
    out = _blend_normal(dst, src, opacity)
    assert len(out) == 4
    if dst[3]:
        assert out[3] >= dst[3]


@given(st.lists(st.tuples(st.integers(0, 3), st.integers(0, 3), u8), max_size=6))
def test_indexed_pixel_writes_round_trip(edits: list[tuple[int, int, int]]) -> None:
    pixels = Pixels.blank(4, 4, ColorMode.INDEXED)
    for x, y, value in edits:
        pixels[x, y] = value
        assert pixels[x, y] == value
