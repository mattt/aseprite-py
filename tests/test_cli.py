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
