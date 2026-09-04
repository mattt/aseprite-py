"""Read and write Aseprite ``.ase`` / ``.aseprite`` files.

This package implements the
`Aseprite file format <https://github.com/aseprite/aseprite/blob/main/docs/ase-file-specs.md>`_.
It does not run the Aseprite application or execute Lua.
"""

from aseprite._errors import AsepriteError, FormatError
from aseprite._model import (
    BlendMode,
    Cel,
    CelExtra,
    Color,
    ColorMode,
    ColorProfile,
    ColorProfileType,
    ExternalFile,
    ExternalFileType,
    Frame,
    Grid,
    Layer,
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
    Tag,
    Tilemap,
    Tileset,
    UserData,
    UserProperty,
)
from aseprite._sprite import Sprite

__all__ = [
    "AsepriteError",
    "BlendMode",
    "Cel",
    "CelExtra",
    "Color",
    "ColorMode",
    "ColorProfile",
    "ColorProfileType",
    "ExternalFile",
    "ExternalFileType",
    "FormatError",
    "Frame",
    "Grid",
    "Layer",
    "LayerType",
    "LoopDirection",
    "Mask",
    "NinePatch",
    "Palette",
    "Pixels",
    "PropertiesMap",
    "PropertyType",
    "Slice",
    "SliceKey",
    "Sprite",
    "Tag",
    "Tilemap",
    "Tileset",
    "UserData",
    "UserProperty",
]
