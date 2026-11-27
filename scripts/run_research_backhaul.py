"""Run both live XQUIC bridges with the seven-role experiment on Linux."""
import argparse
from collections import Counter
from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def start(stack, command, log):
    stream = stack.enter_context(log.open("w"))
    proc = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=stream,
                            start_new_session=True)
    stack.callback(stop, proc)
    return proc


def stop(proc):
    if proc.poll() is not None:
        return
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def read_events(log):
    with log.open() as stream:
        return [json.loads(line) for line in stream if line.startswith('{"event":')]


def add_delay(stack):
    # Only run this optional impairment in a network namespace created for the experiment.
    if os.readlink("/proc/self/ns/net") == os.readlink("/proc/1/ns/net"):
        raise ValueError("--delay-path-a needs an isolated network namespace")
    def tc(*args, check=True):
        return subprocess.run(["tc", *args], check=check)
    tc("qdisc", "add", "dev", "lo", "root", "handle", "1:", "prio", "priomap", *(["0"] * 16))
    stack.callback(tc, "qdisc", "del", "dev", "lo", "root", "handle", "1:", check=False)
    tc("qdisc", "add", "dev", "lo", "parent", "1:3", "handle", "30:", "netem", "delay", "35ms")
    tc("filter", "add", "dev", "lo", "parent", "1:", "protocol", "ip", "prio", "1",
       "u32", "match", "ip", "dst", "127.0.0.21/32", "flowid", "1:3")


def bridge_evidence(out):
    evidence = {}
    for lane in ("A1", "A2"):
        gw = read_events(out / f"{lane}-gateway.log")
        cloud = read_events(out / f"{lane}-cloud.log")
        selected = [e for e in gw if e["event"] == "path_selected" and e["algorithm"] == "FAP-MPQUIC"]
        def received(events, kind):
            return {e["message_id"] for e in events if e["event"] == "frame"
                    and e["direction"] == "quic_to_tcp" and e["message_type"] == kind}
        fields = {k: sorted(received(cloud, k)) for k in ("SENSOR_DATA", "CONTROL_COMMAND", "CONTROL_RESULT")}
        evidence[lane] = {
            "both_paths_validated": any(e["event"] == "paths_validated" and e["count"] == 2 for e in gw),
            "fap_records_by_path": dict(Counter(str(e["path_id"]) for e in selected)),
            "choices_with_two_paths": sum(e["candidates"] == 2 for e in selected),
            "cloud_received": fields,
            "reverse_persisted_acks": len(received(gw, "PERSISTED_ACK")),
            "reverse_policies": len(received(gw, "SERVER_POLICY")),
        }
    return evidence


def run(binary, out, impair):
    out.mkdir(parents=True, exist_ok=False)
    marker = out / "nodes-ready"
    with tempfile.TemporaryDirectory() as certdir, ExitStack() as stack:
        cert, key = Path(certdir) / "cert.pem", Path(certdir) / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-subj", "/CN=agri-backhaul", "-addext", "subjectAltName=DNS:agri-backhaul",
                        "-keyout", key, "-out", cert], check=True, stderr=subprocess.DEVNULL)
        bridges = []
        for lane in (1, 2):
            port = str(34110 + lane)
            g = ["127.0.0.11:" + port, "127.0.0.12:" + port]
            c = ["127.0.0.21:" + port, "127.0.0.22:" + port]
            for role, local, peer, tcp in (("cloud", c, g, 9100), ("gateway", g, c, 19100 + lane)):
                command = [sys.executable, "-m", "backhaul.bridge", role, "--local", *local,
                           "--peer", *peer, "--tcp", f"127.0.0.1:{tcp}", "--binary", binary, "--cert", cert]
                if role == "cloud":
                    command.extend(["--key", key])
                bridges.append(start(stack, command, out / f"A{lane}-{role}.log"))

        command = [sys.executable, "-m", "experiments.research_chain", "--stage", "mpquic",
                   "--output", out / "summary.json", "--on-ready-file", marker,
                   "--backhaul-a1-port", "19101", "--backhaul-a2-port", "19102"]
        farm = start(stack, command, out / "farm.log")
        deadline = time.monotonic() + 140
        degraded = False
        while farm.poll() is None:
            if any(proc.poll() is not None for proc in bridges):
                raise RuntimeError("a bridge exited prematurely; inspect the lane logs")
            if time.monotonic() > deadline:
                raise TimeoutError("seven-role MPQUIC experiment timed out")
            if impair and marker.exists() and not degraded:
                add_delay(stack)
                degraded = True
            time.sleep(0.05)
        if farm.returncode:
            raise RuntimeError(f"seven-role experiment exited {farm.returncode}; inspect {out / 'farm.log'}")
    evidence = bridge_evidence(out)
    (out / "backhaul.json").write_text(json.dumps({"injected_path_a_delay_ms": 35 if degraded else 0,
                                                  "gateways": evidence}, indent=2) + "\n")
    proof = json.loads((out / "summary.json").read_text())["chain"]["cloud_sqlite"]
    required = {"SENSOR_DATA": proof["sample_id"], "CONTROL_COMMAND": proof["command_upload_id"],
                "CONTROL_RESULT": proof["result_id"]}
    for kind, identity in required.items():
        if identity not in evidence["A1"]["cloud_received"][kind]:
            raise RuntimeError(f"the verified {kind} did not cross A1's live QUIC connection")
    for lane, e in evidence.items():
        if not (e["both_paths_validated"] and e["choices_with_two_paths"] and e["cloud_received"]["SENSOR_DATA"]
                and e["reverse_persisted_acks"] and e["reverse_policies"]):
            raise RuntimeError(f"{lane} lacks required forward, reverse, or validated multipath evidence")
    if not evidence["A1"]["cloud_received"]["CONTROL_RESULT"] or (impair and not degraded):
        raise RuntimeError("missing A1 cloud control result or requested path impairment")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new output directory")
    parser.add_argument("--delay-path-a", action="store_true", help="add 35 ms to path A after all roles are ready")
    args = parser.parse_args()
    run(args.binary.resolve(strict=True), args.output.resolve(), args.delay_path_a)
