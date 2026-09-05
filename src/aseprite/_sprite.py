"""The public ``Sprite`` document."""

from __future__ import annotations

from os import PathLike, fspath
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from aseprite._model import (
    TILESET_FLAG_EMBEDDED,
    TILESET_FLAG_EMPTY_IS_ZERO,
    BlendMode,
    Cel,
    ColorMode,
    ColorProfile,
    ExternalFile,
    Frame,
    Grid,
    HeaderFlags,
    Layer,
    LayerList,
    LayerType,
    LoopDirection,
    Mask,
    Palette,
    Pixels,
    Slice,
    SliceKey,
    SliceList,
    Tag,
    TagList,
    Tileset,
    TilesetList,
    UnknownChunk,
    UserData,
    _check_color_mode,
)

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


def _read_source(source: str | PathLike[str] | BinaryIO) -> bytes:
    if isinstance(source, (str, PathLike)):
        return Path(fspath(source)).read_bytes()
    data = source.read()
    if not isinstance(data, bytes | bytearray):
        raise TypeError("open() requires a binary file object")
    return bytes(data)


def _write_dest(dest: str | PathLike[str] | BinaryIO, data: bytes) -> None:
    if isinstance(dest, (str, PathLike)):
        Path(fspath(dest)).write_bytes(data)
        return
    dest.write(data)


class Sprite:
    """An Aseprite document: canvas, layers, frames, and related data.

    Construct a sprite, or open a ``.ase`` / ``.aseprite`` file.
    A new sprite has one layer named ``Layer 1`` and one frame.
    Pass ``empty=True`` to start with no layers or frames.

    Args:
        width: Canvas width in pixels.
        height: Canvas height in pixels.
        color_mode: The pixel format. The default is RGBA.
        empty: If true, do not add a default layer or frame.
    """

    def __init__(
        self,
        width: int,
        height: int,
        color_mode: ColorMode = ColorMode.RGBA,
        *,
        empty: bool = False,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("sprite dimensions must be positive")
        if width > 0xFFFF or height > 0xFFFF:
            raise ValueError("sprite dimensions exceed 65535")
        self.width = width
        self.height = height
        self.color_mode = color_mode
        self.valid_layer_opacity = True
        self.group_blend = False
        self.deprecated_speed = 0
        self.transparent_index = 0
        self.num_colors = 256
        self.pixel_width = 1
        self.pixel_height = 1
        self.grid = Grid()
        self.color_profile: ColorProfile | None = ColorProfile()
        self.palette = Palette()
        self.frames: list[Frame] = []
        self.layers = LayerList(on_remap=self._remap_cels)
        self.tags = TagList()
        self.slices = SliceList()
        self.tilesets = TilesetList()
        self.external_files: list[ExternalFile] = []
        self.masks: list[Mask] = []
        self.user_data: UserData | None = None
        self.unknown_chunks: list[UnknownChunk] = []
        self._file_size = 0
        self._had_old_palette_4 = False
        self._had_old_palette_11 = False
        if not empty:
            self.add_layer("Layer 1")
            self.add_frame()

    @property
    def size(self) -> tuple[int, int]:
        """Returns ``(width, height)`` in pixels."""
        return (self.width, self.height)

    @property
    def flags(self) -> int:
        """Returns the header flag bits from the file format."""
        value = 0
        if self.valid_layer_opacity:
            value |= HeaderFlags.LAYER_OPACITY
        if self.group_blend:
            value |= HeaderFlags.GROUP_BLEND
        if any(layer.uuid is not None for layer in self.layers):
            value |= HeaderFlags.LAYER_UUID
        return int(value)

    @classmethod
    def open(cls, source: str | PathLike[str] | BinaryIO) -> Sprite:
        """Opens and returns a sprite from a path or binary file object.

        The file must be a valid ``.ase`` or ``.aseprite`` document.

        Args:
            source: A path or a binary file object.

        Returns:
            The parsed sprite.

        Raises:
            FormatError: If the file is not a valid Aseprite document.
            OSError: If the file cannot be read.
        """
        return cls.from_bytes(_read_source(source))

    @classmethod
    def from_bytes(cls, data: bytes) -> Sprite:
        """Parses and returns a sprite from file bytes.

        Args:
            data: The contents of an ``.ase`` or ``.aseprite`` file.

        Returns:
            The parsed sprite.

        Raises:
            FormatError: If the bytes are not a valid Aseprite document.
        """
        from aseprite._reader import read_sprite

        return read_sprite(data)

    def save(self, dest: str | PathLike[str] | BinaryIO) -> None:
        """Writes this sprite to a path or binary file object.

        Args:
            dest: The destination path or a binary file object.

        Raises:
            ValueError: If the sprite cannot be encoded.
            OSError: If the file cannot be written.
        """
        _write_dest(dest, self.to_bytes())

    def to_bytes(self) -> bytes:
        """Returns this sprite encoded as Aseprite file bytes.

        Raises:
            ValueError: If the sprite cannot be encoded.
        """
        from aseprite._writer import write_sprite

        return write_sprite(self)

    def blank_pixels(
        self, width: int | None = None, height: int | None = None
    ) -> Pixels:
        """Returns a transparent buffer in this sprite's color mode.

        For an indexed sprite the buffer is filled with ``transparent_index``.

        Args:
            width: Buffer width. The default is the canvas width.
            height: Buffer height. The default is the canvas height.
        """
        width = self.width if width is None else width
        height = self.height if height is None else height
        if self.color_mode is ColorMode.INDEXED:
            data = bytes((self.transparent_index,)) * (width * height)
            return Pixels(width, height, data, ColorMode.INDEXED)
        return Pixels.blank(width, height, self.color_mode)

    def add_frame(self, duration_ms: int = 100) -> Frame:
        """Appends a frame and returns it.

        Args:
            duration_ms: The frame duration in milliseconds.
        """
        frame = Frame(duration_ms=duration_ms)
        self.frames.append(frame)
        return frame

    def add_layer(
        self,
        name: str,
        *,
        parent: Layer | None = None,
        kind: LayerType = LayerType.IMAGE,
        blend_mode: BlendMode = BlendMode.NORMAL,
        opacity: int = 255,
        tileset_index: int | None = None,
    ) -> Layer:
        """Appends a layer and returns it.

        Args:
            name: The layer name.
            parent: An optional group that contains the new layer.
            kind: Image, group, or tilemap.
            blend_mode: The layer blend mode.
            opacity: Layer opacity from 0 to 255.
            tileset_index: The tileset referenced by a tilemap layer.

        Raises:
            ValueError: If ``parent`` is not a group layer.
        """
        if parent is not None and parent.kind is not LayerType.GROUP:
            raise ValueError(f"parent layer {parent.name!r} is not a group")
        layer = Layer(
            name=name,
            kind=kind,
            blend_mode=blend_mode,
            opacity=opacity,
            tileset_index=tileset_index,
        )
        if parent is None:
            layer.child_level = 0
            self.layers.append(layer)
        else:
            layer.child_level = parent.child_level + 1
            self.layers.insert(self.layers._descendants_end(parent), layer)
        return layer

    def _remap_cels(self, mapping: dict[int, int | None]) -> None:
        for frame in self.frames:
            updated: dict[int, Cel] = {}
            for index, cel in frame._cels.items():
                new_index = mapping.get(index)
                if new_index is None:
                    continue
                cel.layer_index = new_index
                updated[new_index] = cel
            frame._cels = updated

    def add_tag(
        self,
        name: str,
        from_frame: int,
        to_frame: int,
        *,
        direction: LoopDirection = LoopDirection.FORWARD,
        repeat: int = 0,
    ) -> Tag:
        """Adds an animation tag and returns it.

        Args:
            name: The tag name.
            from_frame: The first frame index in the range.
            to_frame: The last frame index in the range.
            direction: How the tag plays.
            repeat: Repeat count from the file format.
                ``0`` means the UI default.
        """
        tag = Tag(
            name=name,
            from_frame=from_frame,
            to_frame=to_frame,
            direction=direction,
            repeat=repeat,
        )
        self.tags.append(tag)
        return tag

    def add_slice(self, name: str, keys: list[SliceKey] | None = None) -> Slice:
        """Adds a slice and returns it.

        Args:
            name: The slice name.
            keys: Optional slice keys. The default is an empty list.
        """
        sl = Slice(name=name, keys=list(keys or []))
        self.slices.append(sl)
        return sl

    def add_tileset(
        self,
        name: str,
        tile_width: int,
        tile_height: int,
        tile_count: int,
        *,
        pixels: Pixels | None = None,
        tileset_id: int | None = None,
    ) -> Tileset:
        """Adds a tileset and returns it.

        Aseprite treats tile 0 as the empty tile, so leave the first
        ``tile_height`` rows of ``pixels`` blank.

        Args:
            name: The tileset name.
            tile_width: Width of one tile, in pixels.
            tile_height: Height of one tile, in pixels.
            tile_count: The number of tiles.
            pixels: The embedded tile image.
                Width must be ``tile_width``.
                Height must be ``tile_height * tile_count``.
                The default is a transparent image, because Aseprite drops
                tilemap layers whose tileset has no image.
            tileset_id: File-format tileset ID. The default is the next index.
        """
        expected_height = tile_height * tile_count
        if pixels is None:
            pixels = self.blank_pixels(tile_width, expected_height)
        if pixels.width != tile_width or pixels.height != expected_height:
            raise ValueError("tileset image size does not match tile dimensions")
        _check_color_mode(pixels, self.color_mode, "tileset")
        flags = TILESET_FLAG_EMBEDDED | TILESET_FLAG_EMPTY_IS_ZERO
        tileset = Tileset(
            id=len(self.tilesets) if tileset_id is None else tileset_id,
            name=name,
            tile_count=tile_count,
            tile_width=tile_width,
            tile_height=tile_height,
            flags=flags,
            pixels=pixels,
        )
        self.tilesets.append(tileset)
        return tileset

    def flatten(self, frame: int = 0) -> bytes:
        """Composites the given frame and returns RGBA8 bytes.

        Hidden layers are skipped.
        Linked cels are resolved.
        Group isolation follows ``group_blend``.
        Only the Normal blend mode is applied.

        Args:
            frame: The frame index to composite.

        Returns:
            ``width * height * 4`` bytes in RGBA order.

        Raises:
            IndexError: If the frame index is out of range.
        """
        from aseprite._render import flatten_frame

        return flatten_frame(self, frame)

    def image(self, frame: int = 0) -> PILImage:
        """Composites the given frame and returns a Pillow image.

        Requires the ``aseprite[image]`` extra.

        Args:
            frame: The frame index to composite.

        Returns:
            A Pillow ``Image`` in RGBA mode.

        Raises:
            ImportError: If Pillow is not installed.
            IndexError: If the frame index is out of range.
        """
        try:
            from PIL import Image
        except ImportError as exc:
            raise ImportError(
                "Pillow is required for image(). Install aseprite[image]."
            ) from exc
        data = self.flatten(frame)
        return Image.frombytes("RGBA", (self.width, self.height), data)

    def __repr__(self) -> str:
        return (
            f"Sprite(width={self.width}, height={self.height}, "
            f"color_mode={self.color_mode.name}, "
            f"frames={len(self.frames)}, layers={len(self.layers)})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Sprite):
            return NotImplemented
        return (
            self.width == other.width
            and self.height == other.height
            and self.color_mode == other.color_mode
            and self.valid_layer_opacity == other.valid_layer_opacity
            and self.group_blend == other.group_blend
            and self.transparent_index == other.transparent_index
            and self.pixel_width == other.pixel_width
            and self.pixel_height == other.pixel_height
            and self.grid == other.grid
            and self.color_profile == other.color_profile
            and self.palette == other.palette
            and self.layers == other.layers
            and self.frames == other.frames
            and self.tags == other.tags
            and self.slices == other.slices
            and self.tilesets == other.tilesets
            and self.external_files == other.external_files
            and self.masks == other.masks
            and self.user_data == other.user_data
            and self.unknown_chunks == other.unknown_chunks
        )
