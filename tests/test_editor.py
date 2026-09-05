import subprocess
from pathlib import Path

import pytest

from aseprite import ColorMode, LayerType, Pixels, Sprite
from tests.helpers import aseprite_cli, blend_sprite, indexed_overlap_sprite

FIXTURE = Path(__file__).parent / "fixtures" / "editor.aseprite"

needs_cli = pytest.mark.skipif(
    aseprite_cli() is None, reason="Aseprite CLI is not available"
)


def _cli_export(source: Path, tmp_path: Path) -> bytes:
    """Returns the RGBA bytes Aseprite exports for frame 0 of ``source``."""
    executable = aseprite_cli()
    assert executable is not None
    dest = tmp_path / "expected.png"
    subprocess.run(  # noqa: S603
        [
            executable,
            "-b",
            "--frame-range",
            "0,0",
            str(source),
            "--save-as",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    from PIL import Image

    return Image.open(dest).convert("RGBA").tobytes()


def _assert_flatten_matches_cli(sprite: Sprite, tmp_path: Path) -> None:
    source = tmp_path / "sprite.aseprite"
    sprite.save(source)
    assert Sprite.open(source).flatten(0) == _cli_export(source, tmp_path)


def test_open_editor_written_fixture() -> None:
    sprite = Sprite.open(FIXTURE)
    assert sprite.size == (8, 8)
    assert sprite.color_mode is ColorMode.RGBA
    assert [layer.name for layer in sprite.layers] == ["base", "overlay"]
    assert sprite.tags["idle"].from_frame == 0
    again = Sprite.from_bytes(sprite.to_bytes())
    assert [layer.name for layer in again.layers] == ["base", "overlay"]
    assert again.tags["idle"].name == "idle"
    data = sprite.flatten(0)
    assert data[36:40] == b"\xff\x00\x00\xff"
    assert data[40:44] == b"\x00\xff\x00\xff"
    assert data[68:72] == b"\x00\x00\xff\xff"


@needs_cli
def test_flatten_matches_aseprite_cli(tmp_path: Path) -> None:
    assert Sprite.open(FIXTURE).flatten(0) == _cli_export(FIXTURE, tmp_path)


@needs_cli
def test_blend_matches_cli(tmp_path: Path) -> None:
    _assert_flatten_matches_cli(blend_sprite(), tmp_path)


@needs_cli
def test_indexed_overlap_matches_cli(tmp_path: Path) -> None:
    _assert_flatten_matches_cli(indexed_overlap_sprite(), tmp_path)


@needs_cli
def test_invalid_layer_opacity_flag_matches_cli(tmp_path: Path) -> None:
    sprite = Sprite(2, 2)
    sprite.valid_layer_opacity = False
    sprite.layers[0].opacity = 0
    pixels = sprite.blank_pixels()
    pixels[0, 0] = (255, 0, 0, 255)
    sprite.frames[0][sprite.layers[0]] = pixels
    _assert_flatten_matches_cli(sprite, tmp_path)


@needs_cli
def test_z_index_across_group_matches_cli(tmp_path: Path) -> None:
    sprite = Sprite(1, 1, ColorMode.RGBA, empty=True)
    group = sprite.add_layer("g", kind=LayerType.GROUP)
    child = sprite.add_layer("child", parent=group)
    plain = sprite.add_layer("plain")
    frame = sprite.add_frame(100)
    frame.set_cel(child, Pixels(1, 1, b"\xff\x00\x00\xa0", ColorMode.RGBA), z_index=2)
    frame.set_cel(plain, Pixels(1, 1, b"\x00\xff\x00\xa0", ColorMode.RGBA))
    _assert_flatten_matches_cli(sprite, tmp_path)


@needs_cli
def test_group_above_layer_matches_cli(tmp_path: Path) -> None:

    sprite = Sprite(2, 2)
    base = sprite.layers[0]
    pixels = sprite.blank_pixels()
    for x in range(2):
        for y in range(2):
            pixels[x, y] = (200, 40, 40, 255)
    sprite.frames[0][base] = pixels
    group = sprite.add_layer("group", kind=LayerType.GROUP)
    child = sprite.add_layer("child", parent=group)
    top = sprite.blank_pixels(1, 1)
    top[0, 0] = (10, 220, 30, 255)
    sprite.frames[0].set_cel(child, top, 1, 1)
    _assert_flatten_matches_cli(sprite, tmp_path)
