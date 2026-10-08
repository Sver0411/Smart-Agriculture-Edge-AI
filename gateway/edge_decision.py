"""Pluggable edge decision API; rule is the compatibility/default baseline.

Small exported models are synthetic software references, not deployment models.
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
    from ai.engines.rule import RuleEngine
    return RuleEngine().predict(sensor_data, policy)


class EdgeDecider:
    """Stateful wrapper around :func:`edge_decision`.

    The gateway keeps one instance; ``SERVER_POLICY`` messages update its
    thresholds in place.
    """

    def __init__(self, policy: dict | None = None, policy_version: int = 0, engine="rule", artifact=None, store=None):
        from ai.engines import create_engine
        self.engine = create_engine(engine, artifact)
        self.policy = {**config.DEFAULT_POLICY, **(policy or {})}
        self.policy_version = policy_version
        self.store = store
        self.policy_recovery = "compiled-default"
        if store:
            from common.state_store import StateError
            from common.protocol import validate_policy
            def validate(saved):
                if type(saved["policy_version"]) is not int or saved["policy_version"] < 0:
                    raise StateError("invalid saved policy version")
                if set(saved["policy"]) != set(config.DEFAULT_POLICY):
                    raise StateError("incomplete saved policy")
                validate_policy({**saved["policy"], "policy_version": saved["policy_version"]}, config.DEFAULT_POLICY)
            try:
                saved = store.load("policy", validator=validate, allow_previous=True)
            except StateError:
                saved = None
                self.policy_recovery = "invalid-checkpoint; compiled-default"
            if saved:
                self.policy = dict(saved["policy"])
                self.policy_version = saved["policy_version"]
                self.policy_recovery = "last-known-good"

    def update_policy(self, payload: dict) -> tuple[bool, dict]:
        """Apply a policy push; return ``(applied, policy)``.

        A policy whose ``policy_version`` is not newer than the version we
        already hold is ignored - it is a replay or an out-of-order delivery.
        """
        from common.protocol import validate_policy
        candidate = validate_policy(payload,self.policy)
        version = payload.get("policy_version")
        if version is not None and version <= self.policy_version:
            return False, dict(self.policy)
        if self.store:
            # Validate -> commit checkpoint -> activate. Failed writes leave
            # the in-memory last-known-good policy untouched.
            self.store.save("policy", {"policy_version": self.policy_version if version is None else version,
                                       "policy": candidate})
        self.policy = candidate
        if version is not None:self.policy_version = version
        return True, dict(self.policy)

    def decide(self, sensor_data: dict, trusted_channels=None) -> dict | None:
        if trusted_channels is not None:
            from gateway.trust_gate import FEATURE_CHANNELS
            if self.engine.name == "rule":
                sensor_data = {k: v for k, v in sensor_data.items() if k in trusted_channels}
            elif not set(trusted_channels) >= FEATURE_CHANNELS:
                return None
        return self.engine.predict(sensor_data, self.policy)
