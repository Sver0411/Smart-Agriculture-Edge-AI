"""SensorTrust five-fault Python reference and legacy stateless validators.

Health is heuristic evidence; availability gates control independently of score.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import config  # noqa: E402

HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
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


# Python reference of SensorTrust core/sensor_trust.c (upstream revision in docs).
from collections import deque
from dataclasses import dataclass
import math
import time
from common.settings import node_settings

PENALTIES = {"RANGE":55, "STUCK":35, "SPIKE":25, "DRIFT":25, "MISSING":55}

def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)

class ChannelTrust:
    """Independent history; drift is measured per second, never per sample."""
    def __init__(self, cfg):
        self.cfg = dict(cfg)
        self.window = deque(maxlen=max(cfg["stuck_window"],cfg["drift_window"]))
        self.last = None
        self.spike_reference = None
        self.invalid = 0
        self.direction = 0
        self.streak = 0

    def update(self, value, timestamp, valid=True):
        c = self.cfg
        flags = []
        usable = valid and numeric(value)
        if not usable:
            self.invalid += 1
            self.streak = self.direction = 0
            if self.invalid >= c["missing_limit"]:
                flags.append("MISSING")
        else:
            self.invalid = 0
            if not c["min_value"] <= value <= c["max_value"]:
                flags.append("RANGE")
            returned = self.spike_reference is not None and abs(value-self.spike_reference) <= c["spike_threshold"]
            self.spike_reference = None
            if returned:
                flags.append("SPIKE")
            elif self.last is not None and abs(value-self.last) > c["spike_threshold"]:
                flags.append("SPIKE")
                self.spike_reference = self.last
            self.window.append((timestamp,value))
            if len(self.window) >= c["stuck_window"]:
                values = [v for _,v in list(self.window)[-c["stuck_window"]:]]
                if max(values)-min(values) < c["stuck_epsilon"]:
                    flags.append("STUCK")
            if len(self.window) >= c["drift_window"]:
                points = list(self.window)[-c["drift_window"]:]
                slope = 0
                if all(y[0]>x[0] for x,y in zip(points,points[1:])):
                    xs = [t-points[0][0] for t,_ in points]; ys = [v for _,v in points]
                    mx,my=sum(xs)/len(xs),sum(ys)/len(ys)
                    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sum((x-mx)**2 for x in xs)
                if abs(slope)>c["drift_threshold"]:
                    direction=1 if slope>0 else -1
                    self.streak=self.streak+1 if direction==self.direction else 1
                    self.direction=direction
                    if self.streak>=c["drift_window"]:
                        flags.append("DRIFT")
                else:
                    self.streak=self.direction=0
            self.last=value
        score=max(0,100-sum(PENALTIES[f] for f in flags))
        state=HEALTHY if score>=80 else DEGRADED if score>=50 else FAULT
        return {"health_score":score,"state":state,"fault_flags":flags,"valid":bool(usable)}

class SensorTrust:
    """Four-channel update(sample); detector state and availability are separate."""
    def __init__(self, channels=None):
        self.channels={k:ChannelTrust(c) for k,c in (channels or node_settings()["trust_channels"]).items()}

    def update(self, sample, timestamp=None, valid=None):
        timestamp=time.monotonic() if timestamp is None else timestamp
        if not numeric(timestamp):
            raise ValueError("timestamp must be finite")
        sample=sample if isinstance(sample,dict) else {}
        results={k:c.update(sample.get(k),timestamp,(valid or {}).get(k,True)) for k,c in self.channels.items()}
        score=min(r["health_score"] for r in results.values())
        state=HEALTHY if score>=80 else DEGRADED if score>=50 else FAULT
        flags=[f for f in PENALTIES if any(f in r["fault_flags"] for r in results.values())]
        return {"health_score":score,"state":state,"fault_flags":flags,"channels":results,
                "usable_for_control":state==HEALTHY and all(r["valid"] for r in results.values())}
