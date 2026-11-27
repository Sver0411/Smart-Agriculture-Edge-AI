"""TAIS-JALC Full for B nodes, driven by confirmed gateway report identity."""
import ctypes as ct
from functools import lru_cache
from pathlib import Path
import subprocess
import sys
import tempfile

from sensor_node.adaptive_sense import AdaptiveSense
from sensor_node.sensor_trust import numeric

CHANNELS = 4
MODES = ("QUIET_ECO", "PROBE", "TRACK", "SAFE_FALLBACK", "DIAG_VERIFY")
HEALTH = {"HEALTHY": 0, "DEGRADED": 1, "FAULT": 2}
FLAGS = {"RANGE": 1, "STUCK": 2, "SPIKE": 4, "DRIFT": 8, "MISSING": 16}
REASONS = ("FIRST_SAMPLE", "VALIDITY_CHANGE", "DEADBAND", "EVENT", "HEALTH_CHANGE",
           "AOI_CAP", "HEARTBEAT")
SAFETY_REASONS = {"SENSOR_FAULT", "SENSOR_RECOVERY", "HEALTH_CHANGE",
                  "CONTROL_THRESHOLD_CROSSING", "CONTROL_MARGIN_ENTRY"}


class Snapshot(ct.Structure):
    _fields_ = [("present", ct.c_bool), ("valid", ct.c_bool * CHANNELS),
                ("value", ct.c_double * CHANNELS), ("active", ct.c_bool * CHANNELS),
                ("health", ct.c_int * CHANNELS), ("flags", ct.c_uint32 * CHANNELS)]


class Decision(ct.Structure):
    _fields_ = [("t", ct.c_double), ("mode", ct.c_int), ("obs_interval", ct.c_double),
                ("next_sample", ct.c_double), ("interval", ct.c_double), ("cap", ct.c_double),
                ("margin", ct.c_double), ("upload", ct.c_bool), ("reasons", ct.c_uint32),
                ("redundancy", ct.c_int), ("score", ct.c_double), ("fast_used", ct.c_int),
                ("fast_blocked", ct.c_bool), ("diagnostic", ct.c_bool)]


@lru_cache(maxsize=1)
def load_kernel():
    """Load only when selected. A private build avoids shared writable libraries."""
    bridge = Path(__file__).resolve().parent / "jalc_bridge"
    source = bridge.parents[1] / "third_party" / "tais"
    with tempfile.TemporaryDirectory(prefix="agri-jalc-") as build:
        library = Path(build) / "libjalc.so"
        flag = "-dynamiclib" if sys.platform == "darwin" else "-shared"
        subprocess.run(["cc", "-std=c11", "-O2", "-fPIC", flag, "-I", str(source),
                        str(source / "tais_jalc.c"), str(bridge / "agri_jalc.c"),
                        "-lm", "-o", str(library)], check=True)
        lib = ct.CDLL(str(library))
    void, double = ct.c_void_p, ct.c_double
    declarations = {
        "agri_jalc_size": ([], ct.c_size_t),
        "agri_jalc_init": ([void, ct.c_int, ct.POINTER(double)], ct.c_bool),
        "agri_jalc_step": ([void, double, ct.POINTER(Snapshot), ct.POINTER(Decision)], ct.c_bool),
        "agri_jalc_confirm": ([void, double, ct.POINTER(Snapshot)], None),
        "agri_jalc_feedback": ([void, ct.c_bool], None),
        "tais_jalc_sizeof_decision": ([], ct.c_size_t),
    }
    for name, (args, result) in declarations.items():
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = args, result
    if lib.tais_jalc_sizeof_decision() != ct.sizeof(Decision):
        raise RuntimeError("TAIS C decision ABI mismatch")
    return lib


class TaisPolicy:
    def __init__(self, settings, nominal_seconds=None):
        self.guard = AdaptiveSense(settings=settings)
        self.channels = tuple(settings["trust_channels"])
        floors = [settings["adaptive"]["channels"][c]["noise_floor"] for c in self.channels]
        if nominal_seconds is not None and (not numeric(nominal_seconds) or nominal_seconds <= 0):
            raise ValueError("positive nominal interval required")
        self.time_scale = 1.0 if nominal_seconds is None else 30.0 / nominal_seconds
        self.origin = None
        self.next_due = 0.0
        self.lib = load_kernel()
        self.ctx = ct.create_string_buffer(self.lib.agri_jalc_size())
        if not self.lib.agri_jalc_init(self.ctx, len(floors), (ct.c_double * len(floors))(*floors)):
            raise ValueError("invalid TAIS channel configuration")

    def _snapshot(self, sample, trust, active):
        s = Snapshot(present=True)
        for i, name in enumerate(self.channels):
            evidence = trust["channels"][name]
            value = sample.get(name)
            s.valid[i] = numeric(value) and evidence["valid"]
            s.value[i] = value if s.valid[i] else 0.0
            s.active[i] = active and evidence["state"] == "HEALTHY" and s.valid[i]
            s.health[i] = HEALTH[evidence["state"]]
            s.flags[i] = sum(FLAGS[f] for f in evidence["fault_flags"])
        return s

    def update(self, sample, trust, timestamp):
        if self.origin is None:
            self.origin = timestamp
        policy_t = (timestamp - self.origin) * self.time_scale
        guard = self.guard.update(sample, trust, timestamp)
        # AdaptiveSense reports a node-wide event. Preserve that attribution
        # rather than labeling a single channel as its independently known cause.
        active = bool(guard.get("detected_event"))
        snap = self._snapshot(sample, trust, active)
        decision = Decision()
        if not self.lib.agri_jalc_step(self.ctx, policy_t, ct.byref(snap), ct.byref(decision)):
            raise ValueError("TAIS acquisition preceded its due time or supplied invalid evidence")
        reasons = [r for i, r in enumerate(REASONS) if decision.reasons & (1 << i)]
        for r in guard["upload_reasons"]:
            if r in SAFETY_REASONS and r not in reasons:
                reasons.append(r)
        interval = decision.interval / self.time_scale
        self.next_due = timestamp + interval
        return {**guard, "sensing_policy": "tais-jalc", "tais_mode": MODES[decision.mode],
                "policy_interval_s": decision.interval, "interval_s": interval,
                "time_scale": self.time_scale, "upload_requested": bool(reasons),
                "upload_reasons": reasons, "score": decision.score}

    def report_timeout(self):
        self.lib.agri_jalc_feedback(self.ctx, True)

    def confirm_report(self, sample, trust, *, timestamp, sequence, schedule):
        self.lib.agri_jalc_feedback(self.ctx, False)
        if not self.guard.mark_reported(sample, trust, timestamp=timestamp, sequence=sequence):
            return False
        snap = self._snapshot(sample, trust, bool(schedule.get("detected_event")))
        acquired = (timestamp - self.origin) * self.time_scale
        self.lib.agri_jalc_confirm(self.ctx, acquired, ct.byref(snap))
        return True


def make_sensing_policy(name, settings, delivery_mode, slow=None, fast=None):
    if name == "adaptive-sense":
        return AdaptiveSense(settings=settings, slow=slow, fast=fast)
    if name != "tais-jalc":
        raise ValueError(f"unknown sensing policy {name!r}")
    if delivery_mode != "gateway-durable":
        raise ValueError("tais-jalc requires gateway-durable receipts and a state database")
    if fast is not None and slow != fast:
        raise ValueError("TAIS uses one nominal simulation interval for clock scaling")
    return TaisPolicy(settings, slow)
