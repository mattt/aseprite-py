import pytest

from aseprite import ColorMode, LayerType, Pixels, Sprite
from aseprite.__main__ import main
from tests.helpers import rgba_sprite


def test_info(tmp_path, capsys) -> None:  # noqa: ANN001
    path = tmp_path / "n.aseprite"
    sprite = rgba_sprite()
    sprite.add_tag("idle", 0, 0)
    sprite.save(path)
    assert main(["info", str(path)]) == 0
    out = capsys.readouterr().out
    assert "2x2" in out
    assert "idle" in out
    assert "RGBA" in out


def test_export(tmp_path) -> None:  # noqa: ANN001
    src = tmp_path / "n.aseprite"
    dst = tmp_path / "n.png"
    rgba_sprite().save(src)
    assert main(["export", str(src), str(dst)]) == 0
    assert dst.is_file()
    from PIL import Image

    image = Image.open(dst)
    assert image.size == (2, 2)


def test_missing_file(tmp_path) -> None:  # noqa: ANN001
    assert main(["info", str(tmp_path / "missing.aseprite")]) == 1


def test_export_frame(tmp_path) -> None:  # noqa: ANN001
    src = tmp_path / "n.aseprite"
    dst = tmp_path / "n.png"
    sprite = rgba_sprite()
    sprite.add_frame(100).set_cel(
        sprite.layers[0],
        Pixels(2, 2, b"\x00\xff\x00\xff" * 4, ColorMode.RGBA),
    )
    sprite.save(src)
    assert main(["export", str(src), str(dst), "--frame", "1"]) == 0
    from PIL import Image

    image = Image.open(dst)
    assert image.getpixel((0, 0)) == (0, 255, 0, 255)


def test_export_bad_frame(tmp_path) -> None:  # noqa: ANN001
    src = tmp_path / "n.aseprite"
    dst = tmp_path / "n.png"
    rgba_sprite().save(src)
    assert main(["export", str(src), str(dst), "--frame", "9"]) == 1


def test_info_corrupt_file(tmp_path) -> None:  # noqa: ANN001
    path = tmp_path / "bad.aseprite"
    path.write_bytes(b"not a sprite")
    assert main(["info", str(path)]) == 1


def test_info_nested_group_indent(tmp_path, capsys) -> None:  # noqa: ANN001
    path = tmp_path / "n.aseprite"
    sprite = Sprite(1, 1, empty=True)
    group = sprite.add_layer("group", kind=LayerType.GROUP)
    sprite.add_layer("child", parent=group)
    sprite.add_frame(100)
    sprite.save(path)
    assert main(["info", str(path)]) == 0
    out = capsys.readouterr().out
    assert "  group (GROUP)" in out
    assert "    child (IMAGE)" in out


def test_export_import_error(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    src = tmp_path / "n.aseprite"
    dst = tmp_path / "n.png"
    rgba_sprite().save(src)

    def fail(self, frame: int = 0) -> None:  # noqa: ARG001
        raise ImportError("Pillow is required")

    monkeypatch.setattr(Sprite, "image", fail)
    assert main(["export", str(src), str(dst)]) == 1
