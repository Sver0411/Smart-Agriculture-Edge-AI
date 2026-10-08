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
    for key in ("max_messages", "max_payload_bytes"):
        if type(cfg["offline_queue"][key]) is not int or cfg["offline_queue"][key] < 1:
            raise ValueError("invalid outbox bound")
    for reserve, total in (("reserved_messages", "max_messages"), ("reserved_payload_bytes", "max_payload_bytes")):
        value = cfg["offline_queue"][reserve]
        if type(value) is not int or not 0 <= value < cfg["offline_queue"][total]:
            raise ValueError("invalid critical reserve")
    capacity = cfg["controller"]["recent_command_capacity"]
    if type(capacity) is not int or not 1 <= capacity <= 1024:
        raise ValueError("invalid recent command window")
    if set(n["control_relevance"]["margins"]) != {"soil_moisture", "temperature"}:
        raise ValueError("control threshold margins require soil and temperature")
    for value in n["control_relevance"]["margins"].values():
        if type(value) not in (int,float) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid control threshold margin")
    for key in ("upload_first_sample", "on_event", "on_state_change", "on_interval_change"):
        if type(a["upload"][key]) is not bool:raise ValueError("invalid upload switch")
    for key in ("heartbeat_s", "delta_threshold"):
        value = a["upload"][key]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid upload threshold")
    return cfg

def load_settings(path=None):
    path=path or os.environ.get("SMART_AGRICULTURE_CONFIG",CONFIG_PATH)
    return validate_settings(json.loads(Path(path).read_text()))

def config_hash(cfg):
    return hashlib.sha256(json.dumps(cfg,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

SETTINGS = load_settings()

def merge_settings(base, overrides):
    result = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_settings(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def profile_settings(profile="simulation"):
    if profile not in ("simulation", "lab", "deployment"):
        raise ValueError("unknown runtime profile")
    path = CONFIG_PATH.parent / "profiles" / (profile + ".json")
    profile_cfg = json.loads(path.read_text())
    candidate = merge_settings(SETTINGS, {"node": profile_cfg["node"]})
    validate_settings(candidate)
    cloud = profile_cfg["connectivity"]
    if not cloud["backoff_s"]:
        raise ValueError("empty reconnect backoff")
    for value in cloud["backoff_s"]:
        positive(value, "reconnect backoff")
    positive(cloud["connect_timeout_s"], "connect timeout")
    positive(cloud["critical_retry_cooldown_s"], "critical retry cooldown")
    return {**profile_cfg, "node": candidate["node"]}


def node_settings(profile=None, *, physical=False):
    result = deepcopy(SETTINGS["node"]) if profile is None else profile_settings(profile)["node"]
    if physical:
        overrides = json.loads((CONFIG_PATH.parent / "physical_b1.json").read_text())
        result = merge_settings(result, overrides)
        result["trust_channels"] = {k: result["trust_channels"][k] for k in ("temperature", "humidity")}
    return result
