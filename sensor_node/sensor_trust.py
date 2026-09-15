"""SensorTrust - basic sensor data trust check for v0.1.

Only the interface is defined here::

    state = check_sensor_health(data)

The full SensorTrust project is *not* integrated yet.  v0.1 answers a single
question: "can this reading be trusted enough to drive a control decision?"

    HEALTHY -> yes, pass it on to the edge decision
    FAULT   -> no, report an alert instead
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import config  # noqa: E402

HEALTHY = "HEALTHY"
FAULT = "FAULT"

REQUIRED_FIELDS = ("temperature", "humidity", "soil_moisture", "light")


def health_reasons(data) -> list[str]:
    """Return the list of problems found in ``data`` (empty means HEALTHY)."""
    if not isinstance(data, dict):
        return ["payload is not an object"]

    reasons: list[str] = []

    for name in REQUIRED_FIELDS:
        value = data.get(name)
        if value is None:
            reasons.append(f"missing {name}")
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            reasons.append(f"{name} is not numeric")

    if reasons:
        return reasons

    for name, (low, high) in config.SENSOR_RANGES.items():
        value = data[name]
        if not low <= value <= high:
            reasons.append(f"{name} out of range: {value} (expected {low}..{high})")

    return reasons


def check_sensor_health(data) -> str:
    """Return :data:`HEALTHY` or :data:`FAULT` for a sensor reading."""
    return FAULT if health_reasons(data) else HEALTHY
