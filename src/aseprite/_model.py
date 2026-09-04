"""Document types for an Aseprite sprite."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import IntEnum
from uuid import UUID

from aseprite._errors import AsepriteError


class ColorMode(IntEnum):
    """The pixel format of a sprite."""

    RGBA = 32
    GRAYSCALE = 16
    INDEXED = 8

    @property
    def bytes_per_pixel(self) -> int:
        """Returns the number of bytes that store one pixel."""
        return {ColorMode.RGBA: 4, ColorMode.GRAYSCALE: 2, ColorMode.INDEXED: 1}[self]


class BlendMode(IntEnum):
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


class LoopDirection(IntEnum):
    """How an animation tag plays."""

    FORWARD = 0
    REVERSE = 1
    PING_PONG = 2
    PING_PONG_REVERSE = 3


class ColorProfileType(IntEnum):
    """The kind of color profile stored in the file."""

    NONE = 0
    SRGB = 1
    ICC = 2


class ExternalFileType(IntEnum):
    """The kind of an external file reference."""

    PALETTE = 0
    TILESET = 1
    EXTENSION_PROPS = 2
    EXTENSION_TILE_MGMT = 3


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


HEADER_FLAG_LAYER_OPACITY = 1
HEADER_FLAG_GROUP_BLEND = 2
HEADER_FLAG_LAYER_UUID = 4

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
    data: bytes
    color_mode: ColorMode
    compressed: bytes | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        expected = self.width * self.height * self.color_mode.bytes_per_pixel
        if self.width < 0 or self.height < 0:
            raise AsepriteError("pixel dimensions must be non-negative")
        if len(self.data) != expected:
            raise AsepriteError(
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


@dataclass(slots=True)
class Color:
    """One palette entry."""

    r: int
    g: int
    b: int
    a: int = 255
    name: str | None = None


@dataclass(slots=True)
class Palette:
    """The sprite color palette."""

    colors: list[Color] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.colors)

    def __getitem__(self, index: int) -> Color:
        return self.colors[index]

    def __iter__(self) -> Iterator[Color]:
        return iter(self.colors)


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

    type: ColorProfileType = ColorProfileType.SRGB
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
    color: tuple[int, int, int, int] | None = None
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
    type: LayerType = LayerType.IMAGE
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
        layer_type: LayerType,
        child_level: int,
        blend_mode: BlendMode,
        opacity: int,
    ) -> Layer:
        """Returns a layer decoded from file flag bits."""
        return cls(
            name=name,
            type=layer_type,
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
    """Compressed-tilemap cel payload."""

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
    """One animation frame."""

    duration_ms: int = 100
    _cels: dict[int, Cel] = field(default_factory=dict, compare=True)

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


class TagList:
    """A sequence of tags that supports lookup by name or index."""

    def __init__(self, tags: list[Tag] | None = None) -> None:
        self._tags = list(tags or [])

    def __getitem__(self, key: int | str) -> Tag:
        if isinstance(key, str):
            for tag in self._tags:
                if tag.name == key:
                    return tag
            raise KeyError(key)
        return self._tags[key]

    def __iter__(self) -> Iterator[Tag]:
        return iter(self._tags)

    def __len__(self) -> int:
        return len(self._tags)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TagList):
            return self._tags == other._tags
        return NotImplemented

    def append(self, tag: Tag) -> None:
        self._tags.append(tag)

    def as_list(self) -> list[Tag]:
        return self._tags


class LayerList:
    """A sequence of layers that supports lookup by name or index."""

    def __init__(self, layers: list[Layer] | None = None) -> None:
        self._layers = list(layers or [])

    def __getitem__(self, key: int | str) -> Layer:
        if isinstance(key, str):
            for layer in self._layers:
                if layer.name == key:
                    return layer
            raise KeyError(key)
        return self._layers[key]

    def __iter__(self) -> Iterator[Layer]:
        return iter(self._layers)

    def __len__(self) -> int:
        return len(self._layers)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LayerList):
            return self._layers == other._layers
        return NotImplemented

    def as_list(self) -> list[Layer]:
        return self._layers

    def insert(self, index: int, layer: Layer) -> None:
        self._layers.insert(index, layer)

    def append(self, layer: Layer) -> None:
        self._layers.append(layer)


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
    pixels: bytes = b""
    compressed: bytes | None = field(default=None, compare=False, repr=False)
    external_file_id: int | None = None
    external_tileset_id: int | None = None
    user_data: UserData | None = None
    tile_user_data: list[UserData | None] = field(default_factory=list)


@dataclass(slots=True)
class ExternalFile:
    """A file or extension linked from this sprite."""

    id: int
    type: ExternalFileType
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


def _reindex_layers(layers: Sequence[Layer]) -> None:
    for index, layer in enumerate(layers):
        layer.index = index


def children_of(layers: Sequence[Layer], group: Layer) -> list[Layer]:
    """Returns the direct child layers of a group."""
    start = group.index + 1
    out: list[Layer] = []
    i = start
    while i < len(layers) and layers[i].child_level > group.child_level:
        if layers[i].child_level == group.child_level + 1:
            out.append(layers[i])
        i += 1
    return out


def descendants_end(layers: Sequence[Layer], group: Layer) -> int:
    """Returns the index after the last descendant of a group."""
    i = group.index + 1
    while i < len(layers) and layers[i].child_level > group.child_level:
        i += 1
    return i
