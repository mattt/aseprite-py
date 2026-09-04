import os
from pathlib import Path

import pytest

from aseprite import ColorMode, LayerType, Sprite

MALL_ART = Path.home() / "Code" / "mall-game" / "art"


def _files() -> list[Path]:
    if not MALL_ART.is_dir():
        return []
    return sorted(MALL_ART.rglob("*.aseprite"))


pytestmark = pytest.mark.skipif(not _files(), reason="mall-game art is not present")


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name)
def test_open_mall_game_file(path: Path) -> None:
    sprite = Sprite.open(path)
    assert sprite.width > 0
    assert sprite.height > 0
    assert sprite.color_mode is ColorMode.RGBA
    assert len(sprite.frames) >= 1
    again = Sprite.from_bytes(sprite.to_bytes())
    assert again.width == sprite.width
    assert again.height == sprite.height
    assert len(again.frames) == len(sprite.frames)
    assert [t.name for t in again.tags] == [t.name for t in sprite.tags]
    assert [ly.name for ly in again.layers] == [ly.name for ly in sprite.layers]
    assert sprite.flatten(0)


def test_odango_tags() -> None:
    path = MALL_ART / "characters" / "odango" / "odango.aseprite"
    if not path.is_file():
        pytest.skip("odango.aseprite is missing")
    sprite = Sprite.open(path)
    assert sprite.width == 112
    assert sprite.height == 112
    assert len(sprite.frames) == 217
    assert sprite.tags["idle_s"].from_frame == 4
    assert sprite.tags["walk_s"].from_frame == 40


def test_odango_face_groups() -> None:
    path = (
        MALL_ART
        / "characters"
        / "odango"
        / "source"
        / "face_rig"
        / "odango_face.aseprite"
    )
    if not path.is_file():
        pytest.skip("odango_face.aseprite is missing")
    sprite = Sprite.open(path)
    assert sprite.width == 341
    assert sprite.layers["neutral"].kind is LayerType.GROUP
    names = [ly.name for ly in sprite.layers]
    assert names.count("base") == 5
    assert [t.name for t in sprite.tags] == ["visemes", "blink"]


def test_flatten_matches_aseprite_cli(tmp_path) -> None:  # noqa: ANN001
    executable = os.environ.get("ASEPRITE_PATH")
    if not executable:
        pytest.skip("ASEPRITE_PATH is not set")
    path = MALL_ART / "items" / "corn.aseprite"
    if not path.is_file():
        pytest.skip("corn.aseprite is missing")
    import subprocess

    from PIL import Image

    dest = tmp_path / "corn.png"
    subprocess.run(  # noqa: S603
        [executable, "-b", "--frame-range", "0,0", str(path), "--save-as", str(dest)],
        check=True,
        capture_output=True,
    )
    expected = Image.open(dest).convert("RGBA")
    sprite = Sprite.open(path)
    actual = sprite.image(0)
    assert actual.size == expected.size
    assert actual.tobytes() == expected.tobytes()
