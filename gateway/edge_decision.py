"""Edge AI decision interface.

v0.1 does **not** train a real model.  What matters here is that the interface
is already the final one::

    decision = edge_decision(sensor_data)

``decision`` is either ``None`` (nothing to do) or a command description such
as ``{"type": "IRRIGATION", "duration": 10}``.  The gateway only ever calls
this function, so the rule based body can later be replaced by a logistic
regression, a decision tree or a TinyML model without touching the gateway.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import config  # noqa: E402

IRRIGATION = "IRRIGATION"
VENTILATION = "VENTILATION"

POLICY_KEYS = (
    "soil_moisture_threshold",
    "temperature_threshold",
    "irrigation_duration",
    "ventilation_duration",
)


def edge_decision(sensor_data: dict, policy: dict | None = None) -> dict | None:
    """Turn one sensor reading into a control command suggestion.

    Rules used by v0.1::

        soil_moisture < 25  ->  IRRIGATION
        temperature   > 32  ->  VENTILATION

    Thresholds and durations come from ``policy`` (the cloud server pushes them
    down), falling back to :data:`common.config.DEFAULT_POLICY`.
    """
    policy = {**config.DEFAULT_POLICY, **(policy or {})}

    soil = sensor_data.get("soil_moisture")
    if soil is not None and soil < policy["soil_moisture_threshold"]:
        return {
            "type": IRRIGATION,
            "duration": policy["irrigation_duration"],
            "reason": f"soil_moisture {soil} < {policy['soil_moisture_threshold']}",
        }

    temperature = sensor_data.get("temperature")
    if temperature is not None and temperature > policy["temperature_threshold"]:
        return {
            "type": VENTILATION,
            "duration": policy["ventilation_duration"],
            "reason": f"temperature {temperature} > {policy['temperature_threshold']}",
        }

    return None


class EdgeDecider:
    """Stateful wrapper around :func:`edge_decision`.

    The gateway keeps one instance; ``SERVER_POLICY`` messages update its
    thresholds in place.
    """

    def __init__(self, policy: dict | None = None, policy_version: int = 0):
        self.policy = {**config.DEFAULT_POLICY, **(policy or {})}
        self.policy_version = policy_version

    def update_policy(self, payload: dict) -> tuple[bool, dict]:
        """Apply a policy push; return ``(applied, policy)``.

        A policy whose ``policy_version`` is not newer than the version we
        already hold is ignored - it is a replay or an out-of-order delivery.
        """
        version = payload.get("policy_version")
        if version is not None:
            version = int(version)
            if version <= self.policy_version:
                return False, dict(self.policy)
            self.policy_version = version

        for key in POLICY_KEYS:
            if key in payload:
                self.policy[key] = payload[key]
        return True, dict(self.policy)

    def decide(self, sensor_data: dict) -> dict | None:
        return edge_decision(sensor_data, self.policy)
