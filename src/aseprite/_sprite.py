"""The public ``Sprite`` document."""

from __future__ import annotations

from pathlib import Path

from aseprite._errors import AsepriteError
from aseprite._model import (
    BlendMode,
    Cel,
    ColorMode,
    ColorProfile,
    ExternalFile,
    Frame,
    Grid,
    Layer,
    LayerList,
    LayerType,
    LoopDirection,
    Mask,
    Palette,
    Slice,
    Tag,
    TagList,
    Tileset,
    UnknownChunk,
    UserData,
    _reindex_layers,
    descendants_end,
)


class Sprite:
    """An Aseprite document: canvas, layers, frames, and related data.

    Construct an empty sprite, or open a ``.ase`` / ``.aseprite`` file.

    Args:
        width: Canvas width in pixels.
        height: Canvas height in pixels.
        color_mode: The pixel format. The default is RGBA.
    """

    def __init__(
        self,
        width: int,
        height: int,
        color_mode: ColorMode = ColorMode.RGBA,
    ) -> None:
        if width <= 0 or height <= 0:
            raise AsepriteError("sprite dimensions must be positive")
        self.width = width
        self.height = height
        self.color_mode = color_mode
        self.flags = 1
        self.deprecated_speed = 0
        self.transparent_index = 0
        self.num_colors = 0
        self.pixel_width = 1
        self.pixel_height = 1
        self.grid = Grid()
        self.color_profile: ColorProfile | None = ColorProfile()
        self.palette = Palette()
        self.layers = LayerList()
        self.frames: list[Frame] = []
        self.tags = TagList()
        self.slices: list[Slice] = []
        self.tilesets: list[Tileset] = []
        self.external_files: list[ExternalFile] = []
        self.masks: list[Mask] = []
        self.user_data: UserData | None = None
        self.unknown_chunks: list[UnknownChunk] = []
        self._file_size = 0
        self._had_old_palette_4 = False
        self._had_old_palette_11 = False

    @classmethod
    def open(cls, path: str | Path) -> Sprite:
        """Opens and returns the sprite at the given path.

        The file must be a valid ``.ase`` or ``.aseprite`` document.

        Args:
            path: The path to the sprite file.

        Returns:
            The parsed sprite.

        Raises:
            FormatError: If the file is not a valid Aseprite document.
            OSError: If the file cannot be read.
        """
        return cls.from_bytes(Path(path).read_bytes())

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

        result = read_sprite(data)
        if not isinstance(result, Sprite):
            raise AsepriteError("parser did not return a sprite")
        return result

    def save(self, path: str | Path) -> None:
        """Writes this sprite to the given path.

        Args:
            path: The destination path.

        Raises:
            AsepriteError: If the sprite cannot be encoded.
            OSError: If the file cannot be written.
        """
        Path(path).write_bytes(self.to_bytes())

    def to_bytes(self) -> bytes:
        """Returns this sprite encoded as Aseprite file bytes.

        Raises:
            AsepriteError: If the sprite cannot be encoded.
        """
        from aseprite._writer import write_sprite

        return write_sprite(self)

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
        layer_type: LayerType = LayerType.IMAGE,
        blend_mode: BlendMode = BlendMode.NORMAL,
        opacity: int = 255,
        tileset_index: int | None = None,
    ) -> Layer:
        """Appends a layer and returns it.

        Args:
            name: The layer name.
            parent: An optional group that contains the new layer.
            layer_type: Image, group, or tilemap.
            blend_mode: The layer blend mode.
            opacity: Layer opacity from 0 to 255.
            tileset_index: The tileset referenced by a tilemap layer.
        """
        layer = Layer(
            name=name,
            type=layer_type,
            blend_mode=blend_mode,
            opacity=opacity,
            tileset_index=tileset_index,
        )
        if parent is None:
            layer.child_level = 0
            self.layers.append(layer)
        else:
            layer.child_level = parent.child_level + 1
            insert_at = descendants_end(self.layers.as_list(), parent)
            self.layers.insert(insert_at, layer)
            self._remap_cels_after_insert(insert_at)
        _reindex_layers(self.layers.as_list())
        return layer

    def _remap_cels_after_insert(self, insert_at: int) -> None:
        for frame in self.frames:
            updated: dict[int, Cel] = {}
            for index, cel in list(frame._cels.items()):
                new_index = index + 1 if index >= insert_at else index
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

    def flatten(self, frame: int = 0) -> bytes:
        """Composites the given frame and returns RGBA8 bytes.

        Hidden layers are skipped.
        Linked cels are resolved.
        Group isolation follows header flag 2.
        Only the Normal blend mode is applied.

        Args:
            frame: The frame index to composite.

        Returns:
            ``width * height * 4`` bytes in RGBA order.

        Raises:
            AsepriteError: If the frame index is out of range.
        """
        from aseprite._render import flatten_frame

        return flatten_frame(self, frame)

    def image(self, frame: int = 0):  # noqa: ANN201
        """Composites the given frame and returns a Pillow image.

        Requires the ``aseprite[image]`` extra.

        Args:
            frame: The frame index to composite.

        Returns:
            A Pillow ``Image`` in RGBA mode.

        Raises:
            ImportError: If Pillow is not installed.
            AsepriteError: If the frame index is out of range.
        """
        try:
            from PIL import Image
        except ImportError as exc:
            raise ImportError(
                "Pillow is required for image(). Install aseprite[image]."
            ) from exc
        data = self.flatten(frame)
        return Image.frombytes("RGBA", (self.width, self.height), data)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Sprite):
            return NotImplemented
        return (
            self.width == other.width
            and self.height == other.height
            and self.color_mode == other.color_mode
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
