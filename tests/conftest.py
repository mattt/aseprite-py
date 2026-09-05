"""Hypothesis profiles.

Select one with ``HYPOTHESIS_PROFILE``. The default keeps the suite fast,
``ci`` runs more examples, and ``long`` is for extended local runs.
"""

import os

from hypothesis import HealthCheck, settings

for name, examples in (("default", 50), ("ci", 250), ("long", 5000)):
    settings.register_profile(
        name,
        max_examples=examples,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
