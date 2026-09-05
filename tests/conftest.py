"""Hypothesis profiles and session setup for editor comparisons.

Select one with ``HYPOTHESIS_PROFILE``. The default keeps the suite fast,
``ci`` runs more examples, and ``long`` is for extended local runs.
"""

import os
import subprocess
from collections.abc import Iterator

import pytest
from hypothesis import HealthCheck, settings

from tests._editor import batch_executable
from tests.helpers import aseprite_cli

for name, examples in (("default", 50), ("ci", 250), ("long", 5000)):
    settings.register_profile(
        name,
        max_examples=examples,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.getgroup("aseprite").addoption(
        "--aseprite-launch",
        choices=("quiet", "direct"),
        default="quiet",
        help="Use a quiet temporary CLI copy of macOS app bundles (default), "
        "or launch the selected executable directly.",
    )


@pytest.fixture(scope="session")
def aseprite_environment(pytestconfig: pytest.Config) -> Iterator[None]:
    """Selects one CLI for editor tests and restores the environment on teardown.

    Requested only by editor comparisons, so collection and ordinary unit
    tests do not copy or sign an executable. A missing editor skips those
    comparisons; a failed preparation is an error with a direct-launch escape
    hatch. The temporary executable is shared across comparisons in a session.
    """
    executable = aseprite_cli()
    if executable is None:
        pytest.skip("Aseprite CLI is not available")
    quiet = pytestconfig.getoption("--aseprite-launch") == "quiet"
    try:
        with batch_executable(executable, quiet=quiet) as prepared:
            with pytest.MonkeyPatch.context() as environment:
                environment.setenv("ASEPRITE_PATH", str(prepared))
                yield
    except (OSError, subprocess.SubprocessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else None
        pytest.fail(
            f"Could not prepare Aseprite for batch tests: {detail or exc}\n"
            "Use --aseprite-launch=direct to launch the selected executable directly.",
            pytrace=False,
        )
