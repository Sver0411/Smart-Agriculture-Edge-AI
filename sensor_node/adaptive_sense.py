"""AdaptiveSense - adaptive sampling interval for v0.1.

Same idea as :mod:`sensor_node.sensor_trust`: only the interface matters.

    interval = next_sample_interval(history)

Rule used by v0.1::

    reading barely changed  ->  5 s between samples (save energy)
    reading changed a lot   ->  2 s between samples (watch it closely)

No state machine, no power model - this only proves that the sampling period
can react to the environment.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import config  # noqa: E402

TRACKED_FIELDS = ("temperature", "humidity", "soil_moisture", "light")

# Relative change above which the environment counts as "changing a lot".
CHANGE_THRESHOLD = 0.05


def relative_change(previous: dict, current: dict) -> float:
    """Largest relative change between two readings (0.0 if not comparable)."""
    worst = 0.0
    for name in TRACKED_FIELDS:
        before = previous.get(name)
        after = current.get(name)
        if before is None or after is None:
            continue
        worst = max(worst, abs(after - before) / max(abs(before), 1.0))
    return worst


def next_sample_interval(
    history: list[dict],
    slow: float | None = None,
    fast: float | None = None,
    threshold: float = CHANGE_THRESHOLD,
) -> float:
    """Return the next sampling interval in seconds."""
    slow = config.SAMPLE_INTERVAL_SLOW if slow is None else slow
    fast = config.SAMPLE_INTERVAL_FAST if fast is None else fast

    if len(history) < 2:
        return slow

    return fast if relative_change(history[-2], history[-1]) >= threshold else slow
