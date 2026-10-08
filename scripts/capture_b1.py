"""Finite serial capture for physical B1. Requires pyserial from the ESP-IDF env."""
import argparse
import csv
import hashlib
import json
import pathlib
import re
import subprocess
import time

import serial

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLE_FIELDS = ("seq", "monotonic_ms", "read_ok", "temperature", "humidity",
                 "injected", "temp_health", "temp_flags", "hum_health", "hum_flags",
                 "usable", "score", "mode", "upload_requested", "detected_event", "next_interval_ms", "reason", "min_free_heap")
NET_FIELDS = ("event", "gateway", "generation", "monotonic_ms", "address", "sda", "scl", "ok")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sanitize(line):
    line = re.sub(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", "<MAC>", line)
    line = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<LAN_HOST>", line)
    line = re.sub(r"/(?:Users|home)/[^/\s]+", "<USER_HOME>", line)
    line = re.sub(r"/dev/cu\.[^\s]+", "<SERIAL_PORT>", line)
    return line


def write_csv(path, rows, fields):
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="local serial port; never recorded")
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--seconds", type=int, default=210)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    dirty = bool(git("status", "--porcelain"))
    if dirty and not args.allow_dirty:
        parser.error("working tree is dirty; commit code first or use --allow-dirty (experimental only)")
    out = ROOT / "results" / ("experimental" if dirty else "v0.3")
    (out / "raw").mkdir(parents=True, exist_ok=True)
    samples, events, raw = [], [], []
    start = time.monotonic()
    with serial.Serial(args.port, 115200, timeout=1) as port:
        port.dtr = False
        port.rts = True
        time.sleep(0.1)
        port.rts = False
        while len(samples) < args.samples and time.monotonic() - start < args.seconds:
            line = sanitize(port.readline().decode("utf-8", errors="replace").strip())
            if not line:
                continue
            raw.append(line)
            if line.startswith("B1_SAMPLE "):
                try:
                    samples.append(json.loads(line[len("B1_SAMPLE "):]))
                except json.JSONDecodeError:
                    pass
            elif line.startswith("B1_NET "):
                try:
                    events.append(json.loads(line[len("B1_NET "):]))
                except json.JSONDecodeError:
                    pass
    (out / "raw" / "b1_serial.log").write_text("\n".join(raw) + "\n")
    write_csv(out / "physical_samples.csv", samples, SAMPLE_FIELDS)
    write_csv(out / "network_events.csv", events, NET_FIELDS)
    config = ROOT / "firmware" / "b1" / "sdkconfig"
    metadata = {
        "git_commit": git("rev-parse", "HEAD"), "git_dirty": dirty,
        "firmware_config_sha256": hashlib.sha256(config.read_bytes()).hexdigest() if config.exists() else None,
        "sensor_trust_commit": "fad43a495abddb9029ef005d16a0909ca1de957c",
        "adaptive_sense_commit": "6e0d086cf14c81d2fb5dba8305e13a7dff2dae3b",
        "physical_samples": len(samples), "capture_complete": len(samples) >= args.samples,
        "serial_duration_s": round(time.monotonic() - start, 3),
    }
    (out / "hardware_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"output": str(out), "samples": len(samples), "complete": metadata["capture_complete"]}))
    if not metadata["capture_complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
