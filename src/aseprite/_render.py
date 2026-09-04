"""Composite a frame to RGBA8."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from aseprite._limits import MAX_GROUP_DEPTH, MAX_PIXELS, bytes_per_tile
from aseprite._model import (
    BlendMode,
    Cel,
    ColorMode,
    Layer,
    LayerType,
    Pixels,
)

if TYPE_CHECKING:
    from aseprite._sprite import Sprite


def flatten_frame(sprite: Sprite, frame_index: int) -> bytes:
    """Returns RGBA8 bytes for one composited frame."""
    if frame_index < 0 or frame_index >= len(sprite.frames):
        raise IndexError(f"frame {frame_index} is out of range")
    if sprite.width * sprite.height > MAX_PIXELS:
        raise ValueError(f"canvas exceeds {MAX_PIXELS} pixels")
    dest = bytearray(sprite.width * sprite.height * 4)
    isolate_groups = sprite.group_blend
    _composite_layers(
        sprite,
        frame_index,
        [layer for layer in sprite.layers if layer.child_level == 0],
        dest,
        isolate_groups,
    )
    return bytes(dest)


def _composite_layers(
    sprite: Sprite,
    frame_index: int,
    layers: list[Layer],
    dest: bytearray,
    isolate_groups: bool,
    depth: int = 0,
) -> None:
    if depth > MAX_GROUP_DEPTH:
        raise ValueError(f"layer group nesting exceeds {MAX_GROUP_DEPTH} levels")
    entries: list[tuple[int, int, Layer, Cel]] = []
    for layer in layers:
        if not layer.visible:
            continue
        if layer.kind is LayerType.GROUP:
            if isolate_groups:
                child_buf = bytearray(sprite.width * sprite.height * 4)
                _composite_layers(
                    sprite,
                    frame_index,
                    sprite.layers.children(layer),
                    child_buf,
                    isolate_groups,
                    depth + 1,
                )
                _blend_buffer(dest, child_buf, layer.opacity, layer.blend_mode)
            else:
                _composite_layers(
                    sprite,
                    frame_index,
                    sprite.layers.children(layer),
                    dest,
                    isolate_groups,
                    depth + 1,
                )
            continue
        cel = _resolve_cel(sprite, layer, frame_index)
        if cel is None:
            continue
        order = layer.index + cel.z_index
        entries.append((order, cel.z_index, layer, cel))
    entries.sort(key=lambda item: (item[0], item[1]))
    for _order, _z, layer, cel in entries:
        _blit_cel(sprite, layer, cel, dest)


def _resolve_cel(sprite: Sprite, layer: Layer, frame_index: int) -> Cel | None:
    seen: set[int] = set()
    current = frame_index
    while current not in seen:
        seen.add(current)
        if current < 0 or current >= len(sprite.frames):
            return None
        cel = sprite.frames[current].cel(layer)
        if cel is None:
            return None
        if cel.link is None:
            return cel
        current = cel.link
    return None


def _cel_pixels(sprite: Sprite, layer: Layer, cel: Cel) -> Pixels | None:
    if cel.pixels is not None:
        return cel.pixels
    if cel.tilemap is None:
        return None
    return _tiles_to_pixels(sprite, layer, cel)


def _tiles_to_pixels(sprite: Sprite, layer: Layer, cel: Cel) -> Pixels | None:
    tm = cel.tilemap
    if tm is None or layer.tileset_index is None:
        return None
    if layer.tileset_index >= len(sprite.tilesets):
        return None
    tileset = sprite.tilesets[layer.tileset_index]
    bpp = sprite.color_mode.bytes_per_pixel
    tw, th = tileset.tile_width, tileset.tile_height
    out_w = tm.width * tw
    out_h = tm.height * th
    if out_w < 0 or out_h < 0 or out_w * out_h > MAX_PIXELS:
        raise ValueError(f"tilemap exceeds {MAX_PIXELS} pixels")
    out = bytearray(out_w * out_h * bpp)
    tile_bytes = tw * th * bpp
    stride = bytes_per_tile(tm.bits_per_tile)
    pixel_data = tileset.pixels.data if tileset.pixels is not None else b""
    for ty in range(tm.height):
        for tx in range(tm.width):
            offset = (ty * tm.width + tx) * stride
            if offset + stride > len(tm.tiles):
                continue
            if stride == 4:
                value = struct.unpack_from("<I", tm.tiles, offset)[0]
            elif stride == 2:
                value = struct.unpack_from("<H", tm.tiles, offset)[0]
            else:
                value = tm.tiles[offset]
            tile_id = value & tm.tile_id_mask
            if tileset.flags & 4 and tile_id == 0:
                continue
            src = tile_id * tile_bytes
            if src + tile_bytes > len(pixel_data):
                continue
            tile = pixel_data[src : src + tile_bytes]
            x_flip = bool(value & tm.x_flip_mask)
            y_flip = bool(value & tm.y_flip_mask)
            d_flip = bool(value & tm.d_flip_mask)
            tile = _flip_tile(bytes(tile), tw, th, bpp, x_flip, y_flip, d_flip)
            for row in range(th):
                dest_row = ((ty * th + row) * out_w + tx * tw) * bpp
                src_row = row * tw * bpp
                out[dest_row : dest_row + tw * bpp] = tile[src_row : src_row + tw * bpp]
    return Pixels(out_w, out_h, bytes(out), sprite.color_mode)


def _flip_tile(
    data: bytes,
    width: int,
    height: int,
    bpp: int,
    x_flip: bool,
    y_flip: bool,
    d_flip: bool,
) -> bytes:
    pixels = [
        data[(y * width + x) * bpp : (y * width + x) * bpp + bpp]
        for y in range(height)
        for x in range(width)
    ]

    def at(x: int, y: int) -> bytes:
        return pixels[y * width + x]

    w, h = width, height
    if d_flip:
        flipped = []
        for y in range(w):
            for x in range(h):
                flipped.append(at(y, x))
        pixels = flipped
        w, h = h, w
    if x_flip:
        pixels = [pixels[y * w + (w - 1 - x)] for y in range(h) for x in range(w)]
    if y_flip:
        pixels = [pixels[(h - 1 - y) * w + x] for y in range(h) for x in range(w)]
    return b"".join(pixels)


def _blit_cel(sprite: Sprite, layer: Layer, cel: Cel, dest: bytearray) -> None:
    pixels = _cel_pixels(sprite, layer, cel)
    if pixels is None:
        return
    opacity = (layer.opacity * cel.opacity + 127) // 255
    for py in range(pixels.height):
        for px in range(pixels.width):
            dx = cel.x + px
            dy = cel.y + py
            if dx < 0 or dy < 0 or dx >= sprite.width or dy >= sprite.height:
                continue
            src = _pixel_rgba(sprite, layer, pixels, px, py)
            di = (dy * sprite.width + dx) * 4
            dest[di : di + 4] = _blend_normal(bytes(dest[di : di + 4]), src, opacity)


def _pixel_rgba(sprite: Sprite, layer: Layer, pixels: Pixels, x: int, y: int) -> bytes:
    i = (y * pixels.width + x) * pixels.color_mode.bytes_per_pixel
    if pixels.color_mode is ColorMode.RGBA:
        return bytes(pixels.data[i : i + 4])
    if pixels.color_mode is ColorMode.GRAYSCALE:
        value, alpha = pixels.data[i], pixels.data[i + 1]
        return bytes((value, value, value, alpha))
    index = pixels.data[i]
    if not layer.background and index == sprite.transparent_index:
        return b"\x00\x00\x00\x00"
    if index < len(sprite.palette):
        color = sprite.palette[index]
        return bytes((color.r, color.g, color.b, color.a))
    return b"\x00\x00\x00\x00"


def _blend_buffer(
    dest: bytearray, src: bytearray, opacity: int, blend_mode: BlendMode
) -> None:
    if blend_mode is not BlendMode.NORMAL:
        blend_mode = BlendMode.NORMAL
    for i in range(0, len(dest), 4):
        dest[i : i + 4] = _blend_normal(
            bytes(dest[i : i + 4]), bytes(src[i : i + 4]), opacity
        )


def _blend_normal(dst: bytes, src: bytes, opacity: int) -> bytes:
    sa = (src[3] * opacity + 127) // 255
    if sa == 0:
        if dst[3] == 0:
            return bytes((src[0], src[1], src[2], 0))
        return dst
    da = dst[3]
    if da == 0:
        return bytes((src[0], src[1], src[2], sa))
    out_a = sa + (da * (255 - sa) + 127) // 255
    if out_a == 0:
        return b"\x00\x00\x00\x00"
    out = []
    for c in range(3):
        num = src[c] * sa + dst[c] * da * (255 - sa) // 255
        out.append((num + out_a // 2) // out_a)
    out.append(out_a)
    return bytes(out)
