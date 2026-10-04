"""Validated software configuration; JSON is the source of truth."""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config/software.json"

def positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")

def validate_settings(cfg):
    if cfg.get("schema_version") != 1:
        raise ValueError("unsupported configuration schema")
    for section in ("system", "node", "policy", "experiment"):
        if not isinstance(cfg.get(section), dict):
            raise ValueError(f"missing configuration section {section}")
    def finite(obj):
        if isinstance(obj,float) and not math.isfinite(obj):raise ValueError("configuration contains nonfinite value")
        if isinstance(obj,dict):
            for value in obj.values():finite(value)
        if isinstance(obj,list):
            for value in obj:finite(value)
    finite(cfg)
    system=cfg["system"]
    for key in ("HEARTBEAT_INTERVAL","HEARTBEAT_TIMEOUT","NODE_TIMEOUT","NODE_STATUS_INTERVAL","ACK_TIMEOUT","COMMAND_TTL","SERVER_RECEIPT_TIMEOUT"):
        positive(system[key],key)
    if system["NODE_STATUS_INTERVAL"] >= system["NODE_TIMEOUT"]:raise ValueError("node keepalive must be shorter than timeout")
    for port in [system["SERVER_PORT"],*system["GATEWAY_PORTS"].values()]:
        if type(port) is not int or not 1<=port<=65535:raise ValueError("invalid network port")
    if set(system["GATEWAY_PORTS"])!={"A1","A2"}:raise ValueError("complete gateway topology required")
    n = cfg["node"]
    for name, c in n["trust_channels"].items():
        for key, value in c.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(f"invalid trust {name}.{key}")
        if c["min_value"] >= c["max_value"] or c["stuck_epsilon"] < 0 or c["spike_threshold"] < 0 or c["drift_threshold"] <= 0:
            raise ValueError(f"invalid trust bounds {name}")
        for key in ("stuck_window", "drift_window"):
            if type(c[key]) is not int or not 2 <= c[key] <= 64:
                raise ValueError(f"invalid {key}")
        if type(c["missing_limit"]) is not int or c["missing_limit"] < 1:
            raise ValueError("invalid missing_limit")
    a = n["adaptive"]
    lo, default, hi = (n["sampling"][k] for k in ("min_interval", "default_interval", "max_interval"))
    positive(lo, "min_interval")
    if not lo <= default <= hi:
        raise ValueError("sampling bounds")
    if not 0 < a["stable_threshold"] < a["active_threshold"] or not 0 <= a["hysteresis_fraction"] < 1:
        raise ValueError("adaptive thresholds")
    for name, ladder in a["ladders"].items():
        if not ladder or any(type(v) not in (int,float) or not math.isfinite(v) or not lo <= v <= hi for v in ladder):
            raise ValueError(f"invalid {name} ladder")
        pairs = list(zip(ladder, ladder[1:]))
        if name == "stable" and any(y < x for x,y in pairs) or name == "active" and any(y > x for x,y in pairs):
            raise ValueError("ladder direction")
    if a["ladders"]["active"][0] >= a["ladders"]["stable"][-1] or min(a["ladders"]["alert"]) > min(a["ladders"]["active"]):
        raise ValueError("ladder escalation")
    for c in a["channels"].values():
        positive(c["noise_floor"], "noise_floor")
    for key,v in a["analyzer"].items():
        positive(v, key)
    if a["analyzer"]["roc_window_s"] > a["analyzer"]["variety_window_s"]:
        raise ValueError("ROC exceeds history window")
    for v in a["ladder_confirmations"].values():
        if type(v) is not int or v < 1:
            raise ValueError("invalid ladder confirmations")
    for key in ("fault_interval_s", "degraded_interval_s", "fault_reminder_s"):
        positive(n[key], key)
    for key,v in cfg["policy"].items():
        positive(v,key)
    return cfg

def load_settings(path=None):
    path=path or os.environ.get("SMART_AGRICULTURE_CONFIG",CONFIG_PATH)
    return validate_settings(json.loads(Path(path).read_text()))

def config_hash(cfg):
    return hashlib.sha256(json.dumps(cfg,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

SETTINGS = load_settings()

def node_settings():
    return deepcopy(SETTINGS["node"])
