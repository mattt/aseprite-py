"""Prepare Aseprite for batch tests without activating the macOS Dock."""

import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


@contextmanager
def batch_executable(executable: Path, *, quiet: bool = True) -> Iterator[Path]:
    """Yields a batch executable, cleaning up any temporary copy afterward.

    On macOS, a bundled Aseprite registers with the Dock before processing
    ``--batch``. An unbundled executable starts with prohibited activation.
    Copy its bytes and mode, then ad-hoc sign the copy: the original signature
    depends on bundle metadata that is absent outside the app. Resource and
    library directories remain available through symlinks.

    The installed executable is never changed. Copies are deliberately
    temporary rather than cached across sessions, so app updates are picked
    up immediately. Non-macOS and standalone executables pass through, as
    does any executable when ``quiet=False``. Preparation failures propagate
    instead of silently falling back to a launch that animates the Dock.
    """
    if not quiet or sys.platform != "darwin":
        yield executable
        return

    source = executable.resolve()
    macos = source.parent
    contents = macos.parent
    if (
        macos.name != "MacOS"
        or contents.name != "Contents"
        or contents.parent.suffix != ".app"
        or not (contents / "Info.plist").is_file()
    ):
        yield executable
        return

    with TemporaryDirectory(prefix="aseprite-batch-") as temporary:
        directory = Path(temporary)
        (directory / "MacOS").mkdir()
        prepared = directory / "MacOS" / source.name
        shutil.copy2(source, prepared)
        for name in ("Resources", "PlugIns", "Frameworks"):
            bundled = contents / name
            if bundled.is_dir():
                (directory / name).symlink_to(bundled, target_is_directory=True)
        subprocess.run(  # noqa: S603
            ["/usr/bin/codesign", "--force", "--sign", "-", str(prepared)],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        yield prepared
