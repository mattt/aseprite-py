"""Document types for an Aseprite sprite."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, MutableSequence, Sequence
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from typing import Protocol, Self, cast, overload
from uuid import UUID


class _OpenIntEnum(IntEnum):
    """An ``IntEnum`` that keeps values this library does not know about.

    Newer Aseprite versions may add members. An unknown value is preserved
    as an ``UNKNOWN_<value>`` pseudo-member so the file still opens and
    writes back unchanged.
    """

    @classmethod
    def _missing_(cls, value: object) -> Self | None:
        if not isinstance(value, int) or value < 0:
            return None
        member = int.__new__(cls, value)
        member._name_ = f"UNKNOWN_{value}"
        member._value_ = value
        return member


class ColorMode(IntEnum):
    """The pixel format of a sprite."""

    RGBA = 32
    GRAYSCALE = 16
    INDEXED = 8

    @property
    def bytes_per_pixel(self) -> int:
        """Returns the number of bytes that store one pixel."""
        return {ColorMode.RGBA: 4, ColorMode.GRAYSCALE: 2, ColorMode.INDEXED: 1}[self]


class BlendMode(_OpenIntEnum):
    """A layer blend mode from the Aseprite spec."""

    NORMAL = 0
    MULTIPLY = 1
    SCREEN = 2
    OVERLAY = 3
    DARKEN = 4
    LIGHTEN = 5
    COLOR_DODGE = 6
    COLOR_BURN = 7
    HARD_LIGHT = 8
    SOFT_LIGHT = 9
    DIFFERENCE = 10
    EXCLUSION = 11
    HUE = 12
    SATURATION = 13
    COLOR = 14
    LUMINOSITY = 15
    ADDITION = 16
    SUBTRACT = 17
    DIVIDE = 18


class LayerType(IntEnum):
    """The kind of a layer."""

    IMAGE = 0
    GROUP = 1
    TILEMAP = 2


class CelType(IntEnum):
    """The kind of pixel data stored in a cel."""

    RAW = 0
    LINKED = 1
    COMPRESSED = 2
    COMPRESSED_TILEMAP = 3


class LoopDirection(_OpenIntEnum):
    """How an animation tag plays."""

    FORWARD = 0
    REVERSE = 1
    PING_PONG = 2
    PING_PONG_REVERSE = 3


class ColorProfileType(_OpenIntEnum):
    """The kind of color profile stored in the file."""

    NONE = 0
    SRGB = 1
    ICC = 2


class ExternalFileType(_OpenIntEnum):
    """The kind of an external file reference."""

    PALETTE = 0
    TILESET = 1
    EXTENSION_PROPS = 2
    EXTENSION_TILE_MGMT = 3


class HeaderFlags(IntFlag):
    """Header flag bits from the Aseprite spec."""

    LAYER_OPACITY = 1
    GROUP_BLEND = 2
    LAYER_UUID = 4


class PropertyType(IntEnum):
    """A typed user-data property from the Aseprite spec."""

    BOOL = 0x0001
    INT8 = 0x0002
    UINT8 = 0x0003
    INT16 = 0x0004
    UINT16 = 0x0005
    INT32 = 0x0006
    UINT32 = 0x0007
    INT64 = 0x0008
    UINT64 = 0x0009
    FIXED = 0x000A
    FLOAT = 0x000B
    DOUBLE = 0x000C
    STRING = 0x000D
    POINT = 0x000E
    SIZE = 0x000F
    RECT = 0x0010
    VECTOR = 0x0011
    PROPERTIES = 0x0012
    UUID = 0x0013


HEADER_FLAG_LAYER_OPACITY = HeaderFlags.LAYER_OPACITY
HEADER_FLAG_GROUP_BLEND = HeaderFlags.GROUP_BLEND
HEADER_FLAG_LAYER_UUID = HeaderFlags.LAYER_UUID

LAYER_FLAG_VISIBLE = 1
LAYER_FLAG_EDITABLE = 2
LAYER_FLAG_LOCK_MOVEMENT = 4
LAYER_FLAG_BACKGROUND = 8
LAYER_FLAG_PREFER_LINKED = 16
LAYER_FLAG_COLLAPSED = 32
LAYER_FLAG_REFERENCE = 64

TILESET_FLAG_EXTERNAL = 1
TILESET_FLAG_EMBEDDED = 2
TILESET_FLAG_EMPTY_IS_ZERO = 4
TILESET_FLAG_AUTO_X_FLIP = 8
TILESET_FLAG_AUTO_Y_FLIP = 16
TILESET_FLAG_AUTO_D_FLIP = 32


@dataclass(slots=True)
class Pixels:
    """Uncompressed pixel bytes for one cel or tileset image.

    The layout is row by row, top to bottom, left to right.
    RGBA uses 4 bytes per pixel, grayscale uses 2, and indexed uses 1.
    """

    width: int
    height: int
    data: bytes | bytearray
    color_mode: ColorMode
    compressed: bytes | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        expected = self.width * self.height * self.color_mode.bytes_per_pixel
        if self.width < 0 or self.height < 0:
            raise ValueError("pixel dimensions must be non-negative")
        if len(self.data) != expected:
            raise ValueError(
                f"pixel data length {len(self.data)} does not match {expected}"
            )

    @classmethod
    def blank(cls, width: int, height: int, color_mode: ColorMode) -> Pixels:
        """Returns a transparent (or zero) buffer of the given size."""
        return cls(
            width,
            height,
            b"\x00" * (width * height * color_mode.bytes_per_pixel),
            color_mode,
        )

    def _offset(self, key: object) -> int:
        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError("pixel index must be (x, y)")
        x, y = key
        if not isinstance(x, int) or not isinstance(y, int):
            raise TypeError("pixel index must be (x, y)")
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            raise IndexError(f"pixel ({x}, {y}) is out of range")
        return (y * self.width + x) * self.color_mode.bytes_per_pixel

    def __getitem__(self, key: tuple[int, int]) -> Color | int:
        i = self._offset(key)
        bpp = self.color_mode.bytes_per_pixel
        pixel = self.data[i : i + bpp]
        if self.color_mode is ColorMode.RGBA:
            return Color(pixel[0], pixel[1], pixel[2], pixel[3])
        if self.color_mode is ColorMode.GRAYSCALE:
            return Color(pixel[0], pixel[0], pixel[0], pixel[1])
        return pixel[0]

    def __setitem__(
        self, key: tuple[int, int], value: Color | Sequence[int] | int
    ) -> None:
        i = self._offset(key)
        packed = _pack_pixel(self.color_mode, value)
        data = self.data
        if not isinstance(data, bytearray):
            data = bytearray(data)
            self.data = data
        data[i : i + len(packed)] = packed

    def __buffer__(self, _flags: int) -> memoryview:
        return memoryview(self.data)


def _check_color_mode(pixels: Pixels, color_mode: ColorMode, what: str) -> None:
    """Raises ``ValueError`` if ``pixels`` are not in the sprite's color mode."""
    if pixels.color_mode is not color_mode:
        raise ValueError(
            f"{what} pixels are {pixels.color_mode.name} "
            f"but the sprite is {color_mode.name}"
        )


def _channel(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError("pixel channel values must be integers")
    if not 0 <= value <= 255:
        raise ValueError(f"pixel channel value {value} is out of range 0..255")
    return value


def _pack_pixel(color_mode: ColorMode, value: Color | Sequence[int] | int) -> bytes:
    if color_mode is ColorMode.INDEXED:
        if isinstance(value, int):
            return bytes((_channel(value),))
        if isinstance(value, Color):
            return bytes((_channel(value.r),))
        if isinstance(value, Sequence) and len(value) >= 1:
            return bytes((_channel(value[0]),))
        raise TypeError("indexed pixel must be an integer")
    if color_mode is ColorMode.GRAYSCALE:
        if isinstance(value, Color):
            return bytes((_channel(value.r), _channel(value.a)))
        if isinstance(value, Sequence) and len(value) >= 2:
            return bytes((_channel(value[0]), _channel(value[1])))
        raise TypeError("grayscale pixel must be (value, alpha)")
    if isinstance(value, Color):
        return bytes(_channel(component) for component in value)
    if isinstance(value, Sequence) and len(value) >= 3:
        alpha = value[3] if len(value) > 3 else 255
        return bytes(
            (
                _channel(value[0]),
                _channel(value[1]),
                _channel(value[2]),
                _channel(alpha),
            )
        )
    raise TypeError("RGBA pixel must be a Color or (r, g, b, a)")


@dataclass(slots=True)
class Color:
    """One palette entry or RGBA color."""

    r: int
    g: int
    b: int
    a: int = 255
    name: str | None = None

    def __iter__(self) -> Iterator[int]:
        yield self.r
        yield self.g
        yield self.b
        yield self.a


@dataclass(slots=True)
class Palette:
    """The sprite color palette."""

    colors: list[Color] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.colors)

    def __getitem__(self, index: int) -> Color:
        return self.colors[index]

    def __setitem__(self, index: int, color: Color) -> None:
        self.colors[index] = color

    def __iter__(self) -> Iterator[Color]:
        return iter(self.colors)

    def append(self, color: Color) -> None:
        """Adds a color at the end of the palette."""
        self.colors.append(color)

    def extend(self, colors: Iterable[Color]) -> None:
        """Adds colors at the end of the palette."""
        self.colors.extend(colors)


@dataclass(slots=True)
class Grid:
    """The editor grid overlay."""

    x: int = 0
    y: int = 0
    width: int = 16
    height: int = 16


@dataclass(slots=True)
class ColorProfile:
    """The color profile for RGB or grayscale values."""

    kind: ColorProfileType = ColorProfileType.SRGB
    use_fixed_gamma: bool = False
    gamma: int = 0
    icc: bytes = b""


@dataclass(slots=True)
class UserProperty:
    """One named, typed value in a user-data property map."""

    name: str
    kind: PropertyType
    value: object


@dataclass(slots=True)
class PropertiesMap:
    """A map of named properties.

    A key of ``0`` is user properties.
    A non-zero key is an extension entry ID.
    """

    key: int
    properties: list[UserProperty] = field(default_factory=list)


@dataclass(slots=True)
class UserData:
    """User-defined text, color, and properties on a document object."""

    text: str | None = None
    color: Color | None = None
    properties: list[PropertiesMap] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.text is not None or self.color is not None or bool(self.properties)


@dataclass(slots=True)
class Layer:
    """A layer in the sprite.

    Layers are stored in file order.
    ``child_level`` describes the group tree as specified in NOTE.1 of the format.
    """

    name: str
    index: int = 0
    kind: LayerType = LayerType.IMAGE
    child_level: int = 0
    blend_mode: BlendMode = BlendMode.NORMAL
    opacity: int = 255
    visible: bool = True
    editable: bool = True
    lock_movement: bool = False
    background: bool = False
    prefer_linked_cels: bool = False
    collapsed: bool = False
    reference: bool = False
    tileset_index: int | None = None
    uuid: UUID | None = None
    user_data: UserData | None = None

    @property
    def flags(self) -> int:
        """Returns the layer flag bits from the file format."""
        value = 0
        if self.visible:
            value |= LAYER_FLAG_VISIBLE
        if self.editable:
            value |= LAYER_FLAG_EDITABLE
        if self.lock_movement:
            value |= LAYER_FLAG_LOCK_MOVEMENT
        if self.background:
            value |= LAYER_FLAG_BACKGROUND
        if self.prefer_linked_cels:
            value |= LAYER_FLAG_PREFER_LINKED
        if self.collapsed:
            value |= LAYER_FLAG_COLLAPSED
        if self.reference:
            value |= LAYER_FLAG_REFERENCE
        return value

    @classmethod
    def from_flags(
        cls,
        name: str,
        flags: int,
        kind: LayerType,
        child_level: int,
        blend_mode: BlendMode,
        opacity: int,
    ) -> Layer:
        """Returns a layer decoded from file flag bits."""
        return cls(
            name=name,
            kind=kind,
            child_level=child_level,
            blend_mode=blend_mode,
            opacity=opacity,
            visible=bool(flags & LAYER_FLAG_VISIBLE),
            editable=bool(flags & LAYER_FLAG_EDITABLE),
            lock_movement=bool(flags & LAYER_FLAG_LOCK_MOVEMENT),
            background=bool(flags & LAYER_FLAG_BACKGROUND),
            prefer_linked_cels=bool(flags & LAYER_FLAG_PREFER_LINKED),
            collapsed=bool(flags & LAYER_FLAG_COLLAPSED),
            reference=bool(flags & LAYER_FLAG_REFERENCE),
        )


@dataclass(slots=True)
class CelExtra:
    """Precise floating-point bounds for a cel."""

    precise_x: int = 0
    precise_y: int = 0
    width: int = 0
    height: int = 0


@dataclass(slots=True)
class Tilemap:
    """Compressed-tilemap cel payload.

    Aseprite 1.3 reads only tilemaps with 32 bits per tile. Other widths
    are valid in the file format but the editor drops those cels.
    """

    width: int
    height: int
    bits_per_tile: int
    tile_id_mask: int
    x_flip_mask: int
    y_flip_mask: int
    d_flip_mask: int
    tiles: bytes
    compressed: bytes | None = field(default=None, compare=False, repr=False)


@dataclass(slots=True)
class Cel:
    """The content of one layer in one frame."""

    layer_index: int
    x: int = 0
    y: int = 0
    opacity: int = 255
    z_index: int = 0
    pixels: Pixels | None = None
    link: int | None = None
    tilemap: Tilemap | None = None
    extra: CelExtra | None = None
    user_data: UserData | None = None
    raw: bool = False


@dataclass(slots=True)
class Frame:
    """One animation frame.

    ``palette`` optionally replaces the palette from this frame onward.
    ``None`` inherits the previous palette, initially ``Sprite.palette``.
    """

    duration_ms: int = 100
    _cels: dict[int, Cel] = field(default_factory=dict, compare=True)
    palette: Palette | None = None

    @property
    def cels(self) -> list[Cel]:
        """Returns cels in layer-index order."""
        return [self._cels[i] for i in sorted(self._cels)]

    def cel(self, layer: Layer | int) -> Cel | None:
        """Returns the cel on the given layer, if one exists.

        Args:
            layer: The layer object or layer index.
        """
        return self._cels.get(_layer_index(layer))

    def __getitem__(self, layer: Layer | int) -> Cel:
        cel = self.cel(layer)
        if cel is None:
            raise KeyError(_layer_index(layer))
        return cel

    def __setitem__(self, layer: Layer | int, pixels: Pixels) -> None:
        self.set_cel(layer, pixels)

    def set_cel(
        self,
        layer: Layer | int,
        pixels: Pixels,
        x: int = 0,
        y: int = 0,
        *,
        opacity: int = 255,
        z_index: int = 0,
    ) -> Cel:
        """Places image pixels on the given layer.

        Args:
            layer: The layer object or layer index.
            pixels: Uncompressed pixel data in the sprite color mode.
            x: The cel origin X, in pixels.
            y: The cel origin Y, in pixels.
            opacity: Cel opacity from 0 to 255.
            z_index: A z-index offset from the layer order.

        Returns:
            The created cel.
        """
        index = _layer_index(layer)
        cel = Cel(
            layer_index=index,
            x=x,
            y=y,
            opacity=opacity,
            z_index=z_index,
            pixels=pixels,
        )
        self._cels[index] = cel
        return cel

    def set_linked_cel(
        self,
        layer: Layer | int,
        source_frame: int,
        *,
        x: int = 0,
        y: int = 0,
        opacity: int = 255,
        z_index: int = 0,
    ) -> Cel:
        """Links this cel to the same layer in another frame.

        Args:
            layer: The layer object or layer index.
            source_frame: The frame that holds the source cel.
            x: The cel origin X, in pixels.
            y: The cel origin Y, in pixels.
            opacity: Cel opacity from 0 to 255.
            z_index: A z-index offset from the layer order.

        Returns:
            The created cel.
        """
        index = _layer_index(layer)
        cel = Cel(
            layer_index=index,
            x=x,
            y=y,
            opacity=opacity,
            z_index=z_index,
            link=source_frame,
        )
        self._cels[index] = cel
        return cel

    def set_tilemap_cel(
        self,
        layer: Layer | int,
        tilemap: Tilemap,
        x: int = 0,
        y: int = 0,
        *,
        opacity: int = 255,
        z_index: int = 0,
    ) -> Cel:
        """Places a tilemap on the given layer.

        Args:
            layer: The layer object or layer index.
            tilemap: Tile indices and flip masks.
            x: The cel origin X, in pixels.
            y: The cel origin Y, in pixels.
            opacity: Cel opacity from 0 to 255.
            z_index: A z-index offset from the layer order.

        Returns:
            The created cel.
        """
        index = _layer_index(layer)
        cel = Cel(
            layer_index=index,
            x=x,
            y=y,
            opacity=opacity,
            z_index=z_index,
            tilemap=tilemap,
        )
        self._cels[index] = cel
        return cel


@dataclass(slots=True)
class Tag:
    """A named animation range."""

    name: str
    from_frame: int
    to_frame: int
    direction: LoopDirection = LoopDirection.FORWARD
    repeat: int = 0
    color: tuple[int, int, int] = (0, 0, 0)
    user_data: UserData | None = None


class _HasName(Protocol):
    name: str


class _NamedList[T: _HasName](MutableSequence[T]):
    """A mutable sequence that also looks up items by ``name``."""

    def __init__(self, items: Iterable[T] | None = None) -> None:
        self._items: list[T] = list(items) if items is not None else []
        self._after_mutate()

    def _after_mutate(self) -> None:
        return None

    def _name_of(self, item: T) -> str:
        return item.name

    @overload
    def __getitem__(self, key: int) -> T: ...
    @overload
    def __getitem__(self, key: slice) -> list[T]: ...
    @overload
    def __getitem__(self, key: str) -> T: ...
    def __getitem__(self, key: int | slice | str) -> T | list[T]:
        if isinstance(key, str):
            for item in self._items:
                if self._name_of(item) == key:
                    return item
            raise KeyError(key)
        return self._items[key]

    def __setitem__(self, key: int | slice, value: T | Iterable[T]) -> None:
        if isinstance(key, slice):
            self._items[key] = list(cast(Iterable[T], value))
        else:
            self._items[key] = cast(T, value)
        self._after_mutate()

    def __delitem__(self, key: int | slice) -> None:
        del self._items[key]
        self._after_mutate()

    def __len__(self) -> int:
        return len(self._items)

    def insert(self, index: int, value: T) -> None:
        self._items.insert(index, value)
        self._after_mutate()

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            return any(self._name_of(item) == key for item in self._items)
        return any(item == key for item in self._items)

    def get(self, name: str, default: T | None = None) -> T | None:
        """Returns the first item with this name, or ``default``."""
        try:
            return self[name]
        except KeyError:
            return default

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _NamedList):
            return self._items == other._items
        return NotImplemented

    def __iter__(self) -> Iterator[T]:
        return iter(self._items)


class TagList(_NamedList[Tag]):
    """A sequence of tags that supports lookup by name or index."""


class LayerList(_NamedList[Layer]):
    """Layers in file order, with lookup by name or index.

    To reorder layers, assign the complete order in one slice operation,
    e.g. ``layers[:] = [second, first]``. Assigning a layer that would appear
    twice raises ``ValueError`` before any cels are changed; this includes
    the intermediate assignment in a tuple swap. Keep each group's
    descendants immediately after it, with their existing ``child_level``.
    """

    def __init__(
        self,
        items: Iterable[Layer] | None = None,
        *,
        on_remap: Callable[[dict[int, int | None]], None] | None = None,
    ) -> None:
        self._on_remap = on_remap
        self._prev: list[Layer] = []
        super().__init__(items)

    @staticmethod
    def _check_unique(items: list[Layer]) -> None:
        if len({id(layer) for layer in items}) != len(items):
            raise ValueError(
                "the same layer cannot appear twice; reorder with slice assignment"
            )

    def __setitem__(self, key: int | slice, value: Layer | Iterable[Layer]) -> None:
        items = list(self._items)
        if isinstance(key, slice):
            items[key] = list(cast(Iterable[Layer], value))
        else:
            items[key] = cast(Layer, value)
        self._check_unique(items)
        self._items = items
        self._after_mutate()

    def insert(self, index: int, value: Layer) -> None:
        if any(layer is value for layer in self._items):
            raise ValueError(
                "the same layer cannot appear twice; reorder with slice assignment"
            )
        super().insert(index, value)

    def _after_mutate(self) -> None:
        self._check_unique(self._items)
        old_index = {id(layer): i for i, layer in enumerate(self._prev)}
        mapping: dict[int, int | None] = dict.fromkeys(range(len(self._prev)))
        for new_index, layer in enumerate(self._items):
            previous = old_index.get(id(layer))
            if previous is not None:
                mapping[previous] = new_index
            layer.index = new_index
        previous_len = len(self._prev)
        self._prev = list(self._items)
        if self._on_remap is not None and previous_len:
            self._on_remap(mapping)

    def reverse(self) -> None:
        """Reverses top-level layers, keeping each group's subtree intact.

        Child order and cel associations are preserved. Calling twice
        restores the original order, including nested groups.
        """
        blocks: list[list[Layer]] = []
        for layer in self._items:
            if layer.child_level == 0:
                blocks.append([])
            if not blocks:
                raise ValueError("cannot reverse layers with an orphaned child")
            blocks[-1].append(layer)
        self._items = [layer for block in reversed(blocks) for layer in block]
        self._after_mutate()

    def children(self, group: Layer) -> list[Layer]:
        """Returns the direct child layers of a group."""
        level = group.child_level + 1
        return [
            layer for layer in self.descendants(group) if layer.child_level == level
        ]

    def descendants(self, group: Layer) -> list[Layer]:
        """Returns every descendant of a group, in file order."""
        return list(self._items[group.index + 1 : self._descendants_end(group)])

    def _descendants_end(self, group: Layer) -> int:
        i = group.index + 1
        while i < len(self._items) and self._items[i].child_level > group.child_level:
            i += 1
        return i


@dataclass(slots=True)
class NinePatch:
    """The center rectangle of a nine-patch slice."""

    x: int
    y: int
    width: int
    height: int


@dataclass(slots=True)
class SliceKey:
    """Slice bounds that apply from a given frame onward."""

    frame: int
    x: int
    y: int
    width: int
    height: int
    nine_patch: NinePatch | None = None
    pivot: tuple[int, int] | None = None


@dataclass(slots=True)
class Slice:
    """A named rectangular region, optionally with nine-patch and pivot data."""

    name: str
    keys: list[SliceKey] = field(default_factory=list)
    user_data: UserData | None = None


@dataclass(slots=True)
class Tileset:
    """A tileset referenced by tilemap layers."""

    id: int
    name: str
    tile_count: int
    tile_width: int
    tile_height: int
    base_index: int = 1
    flags: int = TILESET_FLAG_EMBEDDED | TILESET_FLAG_EMPTY_IS_ZERO
    pixels: Pixels | None = None
    compressed: bytes | None = field(default=None, compare=False, repr=False)
    external_file_id: int | None = None
    external_tileset_id: int | None = None
    user_data: UserData | None = None
    tile_user_data: list[UserData | None] = field(default_factory=list)


class SliceList(_NamedList[Slice]):
    """A sequence of slices that supports lookup by name or index."""


class TilesetList(_NamedList[Tileset]):
    """A sequence of tilesets that supports lookup by name or index."""


@dataclass(slots=True)
class ExternalFile:
    """A file or extension linked from this sprite."""

    id: int
    kind: ExternalFileType
    name: str


@dataclass(slots=True)
class Mask:
    """A deprecated mask chunk, preserved for round-trip."""

    x: int
    y: int
    width: int
    height: int
    name: str
    bitmap: bytes


@dataclass(slots=True)
class UnknownChunk:
    """A chunk type this library does not interpret."""

    frame_index: int
    chunk_type: int
    data: bytes


def _layer_index(layer: Layer | int) -> int:
    return layer.index if isinstance(layer, Layer) else layer
