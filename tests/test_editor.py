import subprocess
from pathlib import Path

import pytest

from aseprite import ColorMode, Sprite
from tests.helpers import aseprite_cli

FIXTURE = Path(__file__).parent / "fixtures" / "editor.aseprite"


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


@pytest.mark.skipif(aseprite_cli() is None, reason="Aseprite CLI is not available")
def test_flatten_matches_aseprite_cli(tmp_path: Path) -> None:
    executable = aseprite_cli()
    assert executable is not None
    dest = tmp_path / "editor.png"
    subprocess.run(  # noqa: S603
        [
            executable,
            "-b",
            "--frame-range",
            "0,0",
            str(FIXTURE),
            "--save-as",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    from PIL import Image

    expected = Image.open(dest).convert("RGBA")
    actual = Sprite.open(FIXTURE).image(0)
    assert actual.size == expected.size
    assert actual.tobytes() == expected.tobytes()
