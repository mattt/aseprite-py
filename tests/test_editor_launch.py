import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import _editor


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    contents = tmp_path / "Aseprite Test.app" / "Contents"
    macos = contents / "MacOS"
    macos.mkdir(parents=True)
    executable = macos / "aseprite"
    executable.write_bytes(b"original executable")
    executable.chmod(0o755)
    (contents / "Info.plist").write_text("bundle metadata")
    for name in ("Resources", "PlugIns", "Frameworks"):
        (contents / name).mkdir()
        (contents / name / "data").write_bytes(b"original resource")
    return executable


@pytest.fixture
def signing_calls(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    monkeypatch.setattr(_editor, "sys", SimpleNamespace(platform="darwin"))
    calls: list[Path] = []

    def sign(command: list[str], **kwargs: object) -> None:
        assert command[:4] == ["/usr/bin/codesign", "--force", "--sign", "-"]
        assert kwargs["check"] is True
        prepared = Path(command[4])
        calls.append(prepared)
        prepared.write_bytes(b"ad-hoc signed executable")

    monkeypatch.setattr(_editor.subprocess, "run", sign)
    return calls


@pytest.mark.parametrize("through_symlink", [False, True])
def test_quiet_copy_preserves_bundle_and_cleans_up(
    bundle: Path, signing_calls: list[Path], through_symlink: bool, tmp_path: Path
) -> None:
    selected = bundle
    if through_symlink:
        selected = tmp_path / "aseprite-link"
        selected.symlink_to(bundle)
    with _editor.batch_executable(selected) as prepared:
        assert signing_calls == [prepared]
        assert not prepared.samefile(bundle)
        assert prepared.read_bytes() == b"ad-hoc signed executable"
        assert prepared.stat().st_mode == bundle.stat().st_mode
        temporary = prepared.parent.parent
        assert not (temporary / "Info.plist").exists()
        assert temporary.suffix != ".app"
        for name in ("Resources", "PlugIns", "Frameworks"):
            resource = temporary / name
            assert resource.is_symlink()
            assert resource.resolve() == bundle.parent.parent / name

    assert not temporary.exists()
    assert bundle.read_bytes() == b"original executable"
    assert (bundle.parent.parent / "Info.plist").read_text() == "bundle metadata"
    for name in ("Resources", "PlugIns", "Frameworks"):
        assert (
            bundle.parent.parent / name / "data"
        ).read_bytes() == b"original resource"


@pytest.mark.parametrize(
    ("platform", "quiet", "bundled"),
    [
        ("darwin", False, True),
        ("linux", True, True),
        ("win32", True, True),
        ("darwin", True, False),
    ],
)
def test_other_launches_use_selected_executable(
    bundle: Path,
    signing_calls: list[Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    platform: str,
    quiet: bool,
    bundled: bool,
) -> None:
    monkeypatch.setattr(_editor, "sys", SimpleNamespace(platform=platform))
    selected = bundle if bundled else tmp_path / "standalone"
    if not bundled:
        selected.write_bytes(b"standalone executable")
    with _editor.batch_executable(selected, quiet=quiet) as prepared:
        assert prepared == selected
    assert signing_calls == []


def test_signing_failure_cleans_up_without_launching_bundle(
    bundle: Path, signing_calls: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(command: list[str], **kwargs: object) -> None:
        signing_calls.append(Path(command[4]))
        raise subprocess.CalledProcessError(1, command, stderr="signature rejected")

    monkeypatch.setattr(_editor.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        with _editor.batch_executable(bundle):
            pytest.fail("must not fall back to a bundled launch")
    assert len(signing_calls) == 1
    assert not signing_calls[0].parent.parent.exists()
    assert bundle.read_bytes() == b"original executable"


def test_export_failure_still_removes_quiet_copy(
    bundle: Path, signing_calls: list[Path]
) -> None:
    with pytest.raises(RuntimeError, match="export failed"):
        with _editor.batch_executable(bundle) as prepared:
            raise RuntimeError("export failed")
    assert signing_calls == [prepared]
    assert not prepared.parent.parent.exists()
    assert bundle.read_bytes() == b"original executable"


def test_bundle_without_optional_resource_directories(
    bundle: Path, signing_calls: list[Path]
) -> None:
    for name in ("Resources", "PlugIns", "Frameworks"):
        path = bundle.parent.parent / name
        (path / "data").unlink()
        path.rmdir()
    with _editor.batch_executable(bundle) as prepared:
        assert prepared.is_file()
        assert signing_calls == [prepared]
