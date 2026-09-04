from uuid import UUID

import pytest

from aseprite import (
    BlendMode,
    CelExtra,
    Color,
    ColorMode,
    ColorProfile,
    ColorProfileType,
    ExternalFile,
    ExternalFileType,
    Grid,
    HeaderFlags,
    LayerType,
    LoopDirection,
    Mask,
    NinePatch,
    Palette,
    Pixels,
    PropertiesMap,
    PropertyType,
    Slice,
    SliceKey,
    Sprite,
    Tilemap,
    Tileset,
    UnknownChunk,
    UserData,
    UserProperty,
)
from aseprite._binary import Writer
from aseprite._model import TILESET_FLAG_EMBEDDED, TILESET_FLAG_EXTERNAL
from aseprite._reader import CHUNK_OLD_PALETTE_11, CHUNK_PATH
from tests.helpers import _chunk, _document, chunk_types, rgba_sprite


def test_construct_open_save_equals(tmp_path) -> None:  # noqa: ANN001
    sprite = rgba_sprite()
    sprite.add_tag("idle", 0, 0)
    path = tmp_path / "sprite.aseprite"
    sprite.save(path)
    loaded = Sprite.open(path)
    assert loaded.width == 2
    assert loaded.height == 2
    assert loaded.color_mode is ColorMode.RGBA
    assert len(loaded.frames) == 1
    assert loaded.frames[0].duration_ms == 100
    assert loaded.layers[0].name == "Layer 1"
    assert loaded.tags["idle"].from_frame == 0
    cel = loaded.frames[0].cel(0)
    assert cel is not None
    assert cel.pixels is not None
    assert cel.pixels.data == b"\xff\x00\x00\xff" * 4


def test_semantic_roundtrip() -> None:
    sprite = rgba_sprite(4, 4)
    sprite.add_tag("walk", 0, 0, direction=LoopDirection.REVERSE, repeat=2)
    again = Sprite.from_bytes(sprite.to_bytes())
    assert again == Sprite.from_bytes(again.to_bytes())
    assert again.tags["walk"].direction is LoopDirection.REVERSE
    assert again.tags["walk"].repeat == 2


def test_grayscale_and_indexed() -> None:
    gray = Sprite(2, 1, ColorMode.GRAYSCALE)
    gray.layers[0].name = "g"
    gray.frames[0].duration_ms = 50
    gray.frames[0].set_cel(
        gray.layers[0], Pixels(2, 1, b"\x10\xff\x20\x80", ColorMode.GRAYSCALE)
    )
    loaded = Sprite.from_bytes(gray.to_bytes())
    assert loaded.color_mode is ColorMode.GRAYSCALE
    gray_cel = loaded.frames[0].cel(0)
    assert gray_cel is not None and gray_cel.pixels is not None
    assert gray_cel.pixels.data == b"\x10\xff\x20\x80"

    indexed = Sprite(2, 1, ColorMode.INDEXED)
    indexed.palette = Palette([Color(1, 2, 3), Color(4, 5, 6, 200, name="x")])
    indexed.transparent_index = 0
    indexed.layers[0].name = "i"
    indexed.frames[0].set_cel(
        indexed.layers[0], Pixels(2, 1, b"\x00\x01", ColorMode.INDEXED)
    )
    loaded = Sprite.from_bytes(indexed.to_bytes())
    assert loaded.color_mode is ColorMode.INDEXED
    assert loaded.palette[1].name == "x"
    assert loaded.palette[1].a == 200


def test_cel_extra() -> None:
    sprite = rgba_sprite()
    cel = sprite.frames[0].cel(0)
    assert cel is not None
    cel.extra = CelExtra(precise_x=1, precise_y=2, width=3, height=4)
    loaded = Sprite.from_bytes(sprite.to_bytes())
    extra = loaded.frames[0].cel(0)
    assert extra is not None and extra.extra is not None
    assert extra.extra.precise_x == 1
    assert extra.extra.height == 4


def test_linked_cel() -> None:
    sprite = Sprite(1, 1, ColorMode.RGBA, empty=True)
    layer = sprite.add_layer("L")
    first = sprite.add_frame(100)
    first.set_cel(layer, Pixels(1, 1, b"\x01\x02\x03\xff", ColorMode.RGBA))
    second = sprite.add_frame(120)
    second.set_linked_cel(layer, 0)
    loaded = Sprite.from_bytes(sprite.to_bytes())
    linked = loaded.frames[1].cel(0)
    assert linked is not None
    assert linked.link == 0


def test_group_layers() -> None:
    sprite = Sprite(1, 1, ColorMode.RGBA, empty=True)
    group = sprite.add_layer("group", kind=LayerType.GROUP)
    child = sprite.add_layer("child", parent=group)
    sprite.add_layer("other")
    sprite.add_frame(100)
    assert child.child_level == 1
    assert sprite.layers[0].name == "group"
    assert sprite.layers[1].name == "child"
    assert sprite.layers[2].name == "other"
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert [ly.name for ly in loaded.layers] == ["group", "child", "other"]
    assert loaded.layers[1].child_level == 1
    assert loaded.layers[0].kind is LayerType.GROUP


def test_slice_nine_patch_and_pivot() -> None:
    sprite = rgba_sprite()
    sprite.slices.append(
        Slice(
            name="box",
            keys=[
                SliceKey(
                    frame=0,
                    x=1,
                    y=2,
                    width=3,
                    height=4,
                    nine_patch=NinePatch(0, 0, 1, 1),
                    pivot=(1, 1),
                )
            ],
        )
    )
    loaded = Sprite.from_bytes(sprite.to_bytes())
    key = loaded.slices[0].keys[0]
    assert key.nine_patch == NinePatch(0, 0, 1, 1)
    assert key.pivot == (1, 1)


def test_tileset_and_tilemap() -> None:
    sprite = Sprite(8, 8, ColorMode.RGBA, empty=True)
    tileset = Tileset(
        id=0,
        name="tiles",
        tile_count=1,
        tile_width=8,
        tile_height=8,
        pixels=Pixels(8, 8, b"\xff\x00\x00\xff" * 64, ColorMode.RGBA),
    )
    sprite.tilesets.append(tileset)
    layer = sprite.add_layer("map", kind=LayerType.TILEMAP, tileset_index=0)
    tiles = (1).to_bytes(4, "little")
    sprite.add_frame(100).set_tilemap_cel(
        layer,
        Tilemap(
            width=1,
            height=1,
            bits_per_tile=32,
            tile_id_mask=0x1FFFFFFF,
            x_flip_mask=0x20000000,
            y_flip_mask=0x40000000,
            d_flip_mask=0x80000000,
            tiles=tiles,
        ),
    )
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.tilesets[0].name == "tiles"
    assert loaded.layers[0].kind is LayerType.TILEMAP
    cel = loaded.frames[0].cel(0)
    assert cel is not None
    assert cel.tilemap is not None
    assert cel.tilemap.width == 1


def test_user_data_property_types() -> None:
    props = [
        UserProperty("b", PropertyType.BOOL, True),
        UserProperty("i8", PropertyType.INT8, -2),
        UserProperty("u8", PropertyType.UINT8, 3),
        UserProperty("i16", PropertyType.INT16, -300),
        UserProperty("u16", PropertyType.UINT16, 400),
        UserProperty("i32", PropertyType.INT32, -40000),
        UserProperty("u32", PropertyType.UINT32, 40000),
        UserProperty("i64", PropertyType.INT64, -(2**40)),
        UserProperty("u64", PropertyType.UINT64, 2**40),
        UserProperty("fix", PropertyType.FIXED, 0x00010000),
        UserProperty("s", PropertyType.STRING, "hi"),
        UserProperty("pt", PropertyType.POINT, (1, 2)),
        UserProperty("sz", PropertyType.SIZE, (3, 4)),
        UserProperty("rc", PropertyType.RECT, (1, 2, 3, 4)),
        UserProperty("vec", PropertyType.VECTOR, (PropertyType.INT32, [1, 2, 3])),
        UserProperty(
            "map",
            PropertyType.PROPERTIES,
            [UserProperty("n", PropertyType.STRING, "x")],
        ),
        UserProperty("fl", PropertyType.FLOAT, 1.5),
        UserProperty("db", PropertyType.DOUBLE, 2.25),
        UserProperty(
            "mix",
            PropertyType.VECTOR,
            (0, [(PropertyType.INT32, 1), (PropertyType.STRING, "a")]),
        ),
        UserProperty("id", PropertyType.UUID, UUID(int=1)),
        UserProperty("idb", PropertyType.UUID, UUID(int=2).bytes),
    ]
    sprite = rgba_sprite()
    sprite.layers[0].user_data = UserData(
        text="note",
        color=Color(1, 2, 3, 4),
        properties=[
            PropertiesMap(0, props),
            PropertiesMap(7, [UserProperty("e", PropertyType.STRING, "ext")]),
        ],
    )
    loaded = Sprite.from_bytes(sprite.to_bytes())
    data = loaded.layers[0].user_data
    assert data is not None
    assert data.text == "note"
    assert data.color == Color(1, 2, 3, 4)
    values = {p.name: p.value for p in data.properties[0].properties}
    assert values["b"] is True
    assert values["i8"] == -2
    assert values["s"] == "hi"
    vec = values["vec"]
    assert isinstance(vec, tuple)
    assert vec[1] == [1, 2, 3]
    assert values["fl"] == pytest.approx(1.5)
    assert values["db"] == pytest.approx(2.25)
    mix = values["mix"]
    assert isinstance(mix, tuple)
    assert mix[0] == 0
    assert mix[1][0] == (PropertyType.INT32, 1)
    assert mix[1][1] == (PropertyType.STRING, "a")
    assert values["id"] == UUID(int=1)
    assert values["idb"] == UUID(int=2)
    assert data.properties[1].key == 7
    assert data.properties[1].properties[0].value == "ext"


def test_mask_and_external_file() -> None:
    sprite = rgba_sprite()
    sprite.masks.append(Mask(0, 0, 8, 1, "m", b"\xff"))
    sprite.external_files.append(ExternalFile(1, ExternalFileType.PALETTE, "ext.ase"))
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.masks[0].name == "m"
    assert loaded.external_files[0].name == "ext.ase"


def test_color_profile_icc() -> None:
    sprite = rgba_sprite()
    sprite.color_profile = ColorProfile(
        kind=ColorProfileType.ICC,
        icc=b"icc-bytes",
    )
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.color_profile is not None
    assert loaded.color_profile.icc == b"icc-bytes"


def test_layer_flags_and_blend() -> None:
    sprite = Sprite(1, 1, ColorMode.RGBA, empty=True)
    layer = sprite.add_layer("L", blend_mode=BlendMode.MULTIPLY, opacity=128)
    layer.visible = False
    layer.background = True
    sprite.add_frame(100)
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.layers[0].blend_mode is BlendMode.MULTIPLY
    assert loaded.layers[0].opacity == 128
    assert loaded.layers[0].visible is False
    assert loaded.layers[0].background is True
    layer.editable = False
    layer.lock_movement = True
    layer.prefer_linked_cels = True
    layer.collapsed = True
    layer.reference = True
    layer.uuid = UUID(int=42)
    loaded = Sprite.from_bytes(sprite.to_bytes())
    again = loaded.layers[0]
    assert again.editable is False
    assert again.lock_movement is True
    assert again.prefer_linked_cels is True
    assert again.collapsed is True
    assert again.reference is True
    assert again.uuid == UUID(int=42)
    assert loaded.flags & HeaderFlags.LAYER_UUID


def test_user_data_attachment_points() -> None:
    sprite = rgba_sprite()
    sprite.user_data = UserData(text="sprite")
    sprite.add_tag("idle", 0, 0)
    sprite.tags[0].user_data = UserData(text="tag")
    cel = sprite.frames[0].cel(0)
    assert cel is not None
    cel.user_data = UserData(text="cel")
    sprite.slices.append(
        Slice(
            name="box",
            keys=[SliceKey(0, 0, 0, 2, 2)],
            user_data=UserData(text="slice"),
        )
    )
    sprite.tilesets.append(
        Tileset(
            id=0,
            name="t",
            tile_count=1,
            tile_width=2,
            tile_height=2,
            flags=TILESET_FLAG_EMBEDDED,
            pixels=Pixels(2, 2, b"\x00" * 16, ColorMode.RGBA),
            user_data=UserData(text="tileset"),
            tile_user_data=[UserData(text="tile")],
        )
    )
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.user_data is not None and loaded.user_data.text == "sprite"
    assert (
        loaded.tags[0].user_data is not None and loaded.tags[0].user_data.text == "tag"
    )
    loaded_cel = loaded.frames[0].cel(0)
    assert loaded_cel is not None and loaded_cel.user_data is not None
    assert loaded_cel.user_data.text == "cel"
    assert loaded.slices[0].user_data is not None
    assert loaded.slices[0].user_data.text == "slice"
    assert loaded.tilesets[0].user_data is not None
    assert loaded.tilesets[0].user_data.text == "tileset"
    assert loaded.tilesets[0].tile_user_data[0] is not None
    assert loaded.tilesets[0].tile_user_data[0].text == "tile"


def test_tag_color_and_ping_pong() -> None:
    sprite = rgba_sprite()
    sprite.add_tag("pp", 0, 0, direction=LoopDirection.PING_PONG)
    sprite.tags[0].color = (9, 8, 7)
    sprite.add_tag("ppr", 0, 0, direction=LoopDirection.PING_PONG_REVERSE)
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.tags["pp"].direction is LoopDirection.PING_PONG
    assert loaded.tags["pp"].color == (9, 8, 7)
    assert loaded.tags["ppr"].direction is LoopDirection.PING_PONG_REVERSE


def test_header_grid_and_color_profile() -> None:
    sprite = rgba_sprite()
    sprite.grid = Grid(1, 2, 8, 8)
    sprite.pixel_width = 2
    sprite.pixel_height = 3
    sprite.color_profile = ColorProfile(
        kind=ColorProfileType.SRGB,
        use_fixed_gamma=True,
        gamma=0x10000,
    )
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.grid == Grid(1, 2, 8, 8)
    assert loaded.pixel_width == 2
    assert loaded.pixel_height == 3
    assert loaded.color_profile is not None
    assert loaded.color_profile.kind is ColorProfileType.SRGB
    assert loaded.color_profile.use_fixed_gamma is True
    assert loaded.color_profile.gamma == 0x10000
    sprite.color_profile = ColorProfile(kind=ColorProfileType.NONE)
    none = Sprite.from_bytes(sprite.to_bytes())
    assert none.color_profile is not None
    assert none.color_profile.kind is ColorProfileType.NONE


def test_raw_cel_roundtrip() -> None:
    sprite = rgba_sprite(1, 1)
    cel = sprite.frames[0].cel(0)
    assert cel is not None
    cel.raw = True
    loaded = Sprite.from_bytes(sprite.to_bytes())
    again = loaded.frames[0].cel(0)
    assert again is not None
    assert again.raw is True
    assert again.pixels is not None
    assert bytes(again.pixels.data) == b"\xff\x00\x00\xff"


def test_unknown_chunk_roundtrip() -> None:
    sprite = rgba_sprite()
    sprite.unknown_chunks.append(UnknownChunk(0, CHUNK_PATH, b"path-data"))
    loaded = Sprite.from_bytes(sprite.to_bytes())
    assert loaded.unknown_chunks[0].chunk_type == CHUNK_PATH
    assert loaded.unknown_chunks[0].data == b"path-data"


def test_old_palette_4_roundtrip() -> None:
    sprite = Sprite(1, 1, ColorMode.INDEXED)
    sprite.palette = Palette([Color(1, 2, 3)])
    sprite._had_old_palette_4 = True
    data = sprite.to_bytes()
    assert 0x0004 in chunk_types(data)
    loaded = Sprite.from_bytes(data)
    assert loaded.palette[0] == Color(1, 2, 3)
    assert loaded._had_old_palette_4 is True


def test_old_palette_11_reads_scaled_and_writes_old_4() -> None:
    payload = Writer()
    payload.u16(1)
    payload.u8(0)
    payload.u8(1)
    payload.u8(16)
    payload.u8(32)
    payload.u8(48)
    data = _document(_chunk(CHUNK_OLD_PALETTE_11, bytes(payload.buf)))
    sprite = Sprite.from_bytes(data)
    assert sprite.palette[0] == Color(64, 128, 192)
    assert sprite._had_old_palette_11 is True
    written = sprite.to_bytes()
    types = chunk_types(written)
    assert 0x0004 in types
    assert 0x0011 not in types


def test_external_tileset_and_base_index() -> None:
    sprite = rgba_sprite()
    sprite.external_files.append(ExternalFile(3, ExternalFileType.TILESET, "tiles.ase"))
    sprite.tilesets.append(
        Tileset(
            id=0,
            name="ext",
            tile_count=4,
            tile_width=8,
            tile_height=8,
            flags=TILESET_FLAG_EXTERNAL,
            base_index=7,
            external_file_id=3,
            external_tileset_id=2,
        )
    )
    loaded = Sprite.from_bytes(sprite.to_bytes())
    tileset = loaded.tilesets[0]
    assert tileset.flags & TILESET_FLAG_EXTERNAL
    assert tileset.base_index == 7
    assert tileset.external_file_id == 3
    assert tileset.external_tileset_id == 2
    assert loaded.external_files[0].kind is ExternalFileType.TILESET


def test_slice_multiple_keys() -> None:
    sprite = rgba_sprite()
    sprite.slices.append(
        Slice(
            name="box",
            keys=[
                SliceKey(
                    frame=0,
                    x=0,
                    y=0,
                    width=2,
                    height=2,
                    nine_patch=NinePatch(0, 0, 1, 1),
                    pivot=(1, 1),
                ),
                SliceKey(frame=1, x=1, y=1, width=1, height=1),
            ],
        )
    )
    loaded = Sprite.from_bytes(sprite.to_bytes())
    keys = loaded.slices[0].keys
    assert keys[0].nine_patch == NinePatch(0, 0, 1, 1)
    assert keys[0].pivot == (1, 1)
    assert keys[1].width == 1
    assert keys[1].nine_patch == NinePatch(0, 0, 0, 0)
    assert keys[1].pivot == (0, 0)


def test_zero_duration_uses_header_speed() -> None:
    sprite = Sprite.from_bytes(_document(duration=0, speed=50))
    assert sprite.frames[0].duration_ms == 50
