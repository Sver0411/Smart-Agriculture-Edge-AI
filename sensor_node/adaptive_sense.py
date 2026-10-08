"""Trust-aware AdaptiveSense adapter, with legacy relative-change helpers.

Runtime scheduling uses the upstream normalized detector and state machine.
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


from copy import deepcopy
from dataclasses import asdict
from common.settings import node_settings
from sensor_node.adaptive_scheduler import AdaptiveScheduler
from sensor_node.sensor_trust import numeric
from sensor_node.fault_notifier import FaultNotifier
from sensor_node.control_relevance import ControlRelevanceGate

class AdaptiveSense:
    """Trust-aware adapter. Untrusted values never enter change-detector history."""
    def __init__(self, settings=None, slow=None, fast=None, profile=None):
        self.settings=deepcopy(settings or node_settings(profile))
        if slow is not None or fast is not None:
            slow=config.SAMPLE_INTERVAL_SLOW if slow is None else slow
            fast=config.SAMPLE_INTERVAL_FAST if fast is None else fast
            if not numeric(slow) or not numeric(fast) or not 0 < fast <= slow:
                raise ValueError("require 0 < fast <= slow")
            self.settings["sampling"]={"min_interval":fast,"default_interval":slow,"max_interval":slow*3}
            self.settings["adaptive"]["ladders"]={"stable":[slow,slow*2,slow*3],"active":[fast],"alert":[fast]}
            self.settings["fault_interval_s"]=slow
            self.settings["degraded_interval_s"]=slow
        self.core=AdaptiveScheduler(self.settings)
        self._confirmed_time=None
        self._confirmed_sequence=None
        self._untrusted=False
        self._health=None
        self.notifier = FaultNotifier(self.settings["fault_reminder_s"])
        self.relevance = ControlRelevanceGate(self.settings['control_relevance']['margins'])

    def mark_reported(self, sample, trust, *, timestamp=None, sequence=None):
        # Call only at the transport's declared confirmation/admission boundary.
        # Async reliable callers supply acquisition time and sequence; legacy
        # synchronous runtime uses the current sample time. New boot = new adapter.
        timestamp=self.core.now if timestamp is None else timestamp
        if not numeric(timestamp) or (sequence is not None and (type(sequence) is not int or not 1 <= sequence <= 0xffffffff)):
            raise ValueError("invalid confirmed sample identity/time")
        if self._confirmed_time is not None and timestamp < self._confirmed_time:
            return False
        if sequence is not None and self._confirmed_sequence is not None and sequence <= self._confirmed_sequence:
            return False
        self._confirmed_time=timestamp
        if sequence is not None:self._confirmed_sequence=sequence
        self.relevance.mark_reported(sample, self.relevance.trusted_channels(trust))
        if trust.get('state') == 'HEALTHY' and trust.get('usable_for_control'):
            self.core.record_reported(timestamp, {k:float(v) for k,v in sample.items() if numeric(v)})
        return True

    def update(self, sample, trust, timestamp):
        if not numeric(timestamp):
            raise ValueError("timestamp must be finite")
        healthy=trust.get("state")=="HEALTHY" and trust.get("usable_for_control",False)
        changed=trust.get("state")!=self._health
        # Minimal legacy trust dictionaries remain supported by this adapter.
        evidence = {**trust, "channels": trust.get("channels", {})}
        notification = self.notifier.update(evidence, now=timestamp)
        relevant = self.relevance.evaluate(sample, self.relevance.trusted_channels(trust))
        self._health=trust.get("state")
        if not healthy:
            self._untrusted=True
            state="ACTIVE" if trust.get("state")=="DEGRADED" else "STABLE"
            interval=self.settings["degraded_interval_s"] if state=="ACTIVE" else self.settings["fault_interval_s"]
            return {"state":state,"interval_s":interval,"score":None,"detected_event":False,
                    "upload_requested":notification is not None or relevant['control_relevant_change'],"health_state":trust.get("state"),"reason":"untrusted_measurement",
                    "control_relevant_change":relevant['control_relevant_change'],
                    "upload_reasons":(["SENSOR_FAULT"] if notification is not None else [])+relevant['reasons']}
        if self._untrusted:
            baseline=(self.core._last_upload_t,dict(self.core._last_upload_values))
            self.core=AdaptiveScheduler(self.settings, time=timestamp)
            self.core._last_upload_t,self.core._last_upload_values=baseline
            self._untrusted=False
        values={k:v for k,v in sample.items() if k in self.settings["adaptive"]["channels"] and numeric(v)}
        baseline=(self.core._last_upload_t,dict(self.core._last_upload_values))
        decision=asdict(self.core.update(timestamp,values))
        self.core._last_upload_t,self.core._last_upload_values=baseline
        if baseline[0] is None and self.core.up_first_sample:
            decision["upload_requested"]=True
            if "FIRST_SAMPLE" not in decision["upload_reasons"]:decision["upload_reasons"].append("FIRST_SAMPLE")
        decision['control_relevant_change'] = relevant['control_relevant_change']
        decision['upload_reasons'].extend(relevant['reasons'])
        if changed:decision['upload_reasons'].append('HEALTH_CHANGE')
        if notification is not None:decision['upload_reasons'].append('SENSOR_RECOVERY')
        decision["upload_requested"] |= changed or notification is not None
        decision['upload_requested'] |= relevant['control_relevant_change']
        decision["health_state"]=trust["state"]
        return decision
