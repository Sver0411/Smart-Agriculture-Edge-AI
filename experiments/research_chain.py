"""Run one seven-role host experiment and retain its SQLite and transport evidence."""
import argparse
import asyncio
from collections import Counter
from contextlib import closing
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from common import config
from common.messages import transport_observer
from demo import Demo, parse_args as demo_args


STAGES = {
    "baseline": ("adaptive-sense", "fifo"),
    "tais": ("tais-jalc", "fifo"),
    "netadapt": ("tais-jalc", "fud_ada"),
    "mpquic": ("tais-jalc", "fud_ada"),
}


class ClimateTrace:
    """The same continuous stimulus independent of when either policy samples."""

    def __init__(self):
        self.start = time.monotonic()
        self.ready = None

    def reading(self, zone):
        now = time.monotonic()
        phase = now - (self.start if self.ready is None else self.ready)
        drift = 0.12 * math.sin(phase * 2)
        elapsed = 0 if self.ready is None else phase
        ramp = min(1.0, max(0.0, (elapsed - 1.0) / 2.0))
        temperature = 30.4 + 3.4 * ramp if zone == "B1" else 24.0
        return {"temperature": round(temperature + drift, 3), "humidity": round(61 + drift, 3),
                "light": round(5000 + 100 * drift, 2), "soil_moisture": round(45 + drift, 3)}


class TraceSensor:
    def __init__(self, climate, node):
        self.climate = climate
        self.node = node

    def sample(self):
        return self.climate.reading(self.node)


class Observations:
    def __init__(self):
        self.start = time.monotonic()
        self.received = []
        self.bytes = Counter()
        self.by_type = Counter()

    def observe(self, event, message):
        if event != "delivered":
            return
        direction = ("server_to_gateway" if message.source == "SERVER" else
                     "gateway_to_server" if message.target == "SERVER" else "field")
        self.bytes[direction] += len(message.to_line().encode())
        self.by_type[(direction, message.type)] += 1
        payload = message.payload
        self.received.append({
            "s": round(time.monotonic() - self.start, 6),
            "id": message.message_id, "type": message.type, "source": message.source, "target": message.target,
            "ack_id": payload.get("ack_message_id"), "persisted": payload.get("persisted"),
            "policy_version": payload.get("policy_version"), "command_id": payload.get("command_id"),
            "status": payload.get("status"), "origin_sample": payload.get("sensor_receipt_identity"),
            "sensing_policy": (payload.get("sampling") or {}).get("sensing_policy"),
            "tais_mode": (payload.get("sampling") or {}).get("tais_mode"),
        })

    def find(self, **criteria):
        return next((row for row in self.received if all(row[k] == v for k, v in criteria.items())), None)


async def wait_for(check, timeout, label):
    deadline = time.monotonic() + timeout
    while True:
        value = check()
        if value:
            return value
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for {label}")
        await asyncio.sleep(0.05)


def committed_chain(db, durable):
    if durable:
        sample_join = "JOIN a1.sensor_control_audit a ON a.identity = s.message_id"
        cmd_join = "AND a.command_id = c.command_id"
        audit = "a.state AS audit_state,"
    else:
        sample_join = cmd_join = ""
        audit = "NULL AS audit_state,"
    sql = f"""
        SELECT s.message_id sample_id, s.temperature, {audit}
               c.command_id, c.message_id command_upload_id, r.message_id result_id,
               r.status, c.command_type, c.controller_id, c.gateway_id,
               s.created_at sample_commit, c.created_at command_commit, r.created_at result_commit
        FROM sensor_data s {sample_join}
        JOIN controller_command c ON c.gateway_id = s.gateway_id {cmd_join}
        JOIN controller_result r ON r.command_id = c.command_id AND r.controller_id = c.controller_id
        WHERE s.sensor_node_id='B1' AND s.temperature>32 AND c.controller_id='C1'
          AND c.command_type='VENTILATION' AND r.status='EXECUTED'
          AND s.timestamp <= c.timestamp
        ORDER BY r.id, s.timestamp DESC LIMIT 1
    """
    row = db.execute(sql).fetchone()
    return dict(row) if row else None


def policy_proof(obs, demo, version):
    ids = {r["id"] for r in obs.received if r["source"] == "SERVER"
           and r["type"] == "SERVER_POLICY" and r["policy_version"] == version}
    replies = {r["source"]: r for r in obs.received if r["type"] == "ACK"
               and r["target"] == "SERVER" and r["ack_id"] in ids}
    applied = {k: v.decider.policy_version for k, v in demo.gateways.items()}
    if set(replies) == {"A1", "A2"} and all(v == version for v in applied.values()):
        return {"applied_versions": applied, "acknowledgements": replies}


def accepted(db, obs, demo, durable, version):
    chain = committed_chain(db, durable)
    policy = policy_proof(obs, demo, version)
    if not chain or not policy:
        return
    sample = chain["sample_id"]
    cmd = chain["command_id"]
    records = {
        "b1_sample_at_a1": obs.find(type="SENSOR_DATA", id=sample, source="B1", target="A1"),
        "command_at_c1": obs.find(type="CONTROL_COMMAND", command_id=cmd, source="A1", target="C1"),
        "execution_at_a1": obs.find(type="CONTROL_RESULT", command_id=cmd, source="C1",
                                    target="A1", status="EXECUTED"),
        "cloud_sample_receipt_at_a1": obs.find(type="PERSISTED_ACK", source="SERVER", target="A1",
                                              ack_id=sample, persisted=True),
        "cloud_result_receipt_at_a1": obs.find(type="PERSISTED_ACK", source="SERVER", target="A1",
                                              ack_id=chain["result_id"], persisted=True),
    }
    if durable:
        records["gateway_sample_receipt_at_b1"] = obs.find(type="PERSISTED_ACK", source="A1",
                                                          target="B1", ack_id=sample, persisted=True)
    if not all(records.values()):
        return
    if db.execute("SELECT 1 FROM a1.gateway_queue WHERE message_id IN (?, ?)",
                  (sample, chain["result_id"])).fetchone():
        return
    if durable and (chain["audit_state"] != "RESULT_EXECUTED"
                    or records["command_at_c1"]["origin_sample"] != sample
                    or records["b1_sample_at_a1"]["sensing_policy"] != "tais-jalc"):
        return
    selections = {name: next((d for d in demo.field_transport.decisions
                              if d["message_id"] == records[name]["id"] and d["reassembled"]), None)
                  for name in ("b1_sample_at_a1", "command_at_c1", "execution_at_a1")}
    if not all(selections.values()):
        return
    if not db.execute("SELECT 1 FROM sensor_data WHERE sensor_node_id='B2'").fetchone():
        return
    if not demo.field_transport.metrics["contended_decisions"]:
        return
    if db.execute("SELECT 1 FROM controller_result WHERE controller_id='C2' AND status='EXECUTED'").fetchone():
        raise ValueError("the unheated control zone executed an unexpected command")
    return {
        "cloud_sqlite": chain, "observed_messages": records, "field_selections": selections,
        "policy_round_trip": policy,
        "correlation": ("B1 identity joined to A1 durable audit and command_id joined to C1 execution"
                        if durable else "B1 and C1 matched by zone and threshold; legacy has no durable causal join"),
        "elapsed_ms": {
            "sample_to_result_at_gateway": round(1000 * (records["execution_at_a1"]["s"]
                                                         - records["b1_sample_at_a1"]["s"]), 3),
            "command_to_result_at_gateway": round(1000 * (records["execution_at_a1"]["s"]
                                                          - records["command_at_c1"]["s"]), 3),
            "sample_to_cloud_receipt": round(1000 * (records["cloud_sample_receipt_at_a1"]["s"]
                                                      - records["b1_sample_at_a1"]["s"]), 3),
        },
    }


async def run(args, result):
    sense, scheduler = STAGES[args.stage]
    options = ["--db", "cloud.db", "--sensing-policy", sense, "--field-scheduler", scheduler,
               "--sample-interval", str(args.sample_interval), "--policy-interval", "1"]
    if args.stage == "mpquic":
        options += ["--backhaul-a1-port", str(args.backhaul_a1_port),
                    "--backhaul-a2-port", str(args.backhaul_a2_port)]
    demo = Demo(demo_args(options))
    climate, obs = ClimateTrace(), Observations()
    for node, sensor in demo.sensors.items():
        sensor.simulator = TraceSensor(climate, node)
    result.update(sensing_policy=sense, field_scheduler=scheduler, sample_interval_s=args.sample_interval,
                  observation_s=args.observation_seconds,
                  backhaul=("external MPQUIC bridge" if args.stage == "mpquic" else "direct TCP"),
                  climate="B1 rises 30.4 to 33.8 C between ready+1s and ready+3s; B2 stays near 24 C")
    token = transport_observer.set(obs.observe)
    try:
        await demo.start()
        await wait_for(lambda: set(demo.server.clients) == {"A1", "A2"}
                       and all({f"B{i}", f"C{i}"} <= set(demo.gateways[f"A{i}"].connections)
                               for i in (1, 2)), args.timeout, "all seven roles")
        climate.ready = time.monotonic()
        result["ready_s"] = round(climate.ready - obs.start, 6)
        if args.on_ready_file:
            args.on_ready_file.write_text("seven roles ready\n")
        demo.server.update_policy({"ventilation_duration": 4.0})
        version = demo.server.policy_version
        await demo.server._broadcast_policy()
        await asyncio.sleep(max(0, climate.ready + args.observation_seconds - time.monotonic()))
        with closing(sqlite3.connect(Path(demo.db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            queue_path = Path(config.gateway_queue_path("A1")).resolve().as_uri() + "?mode=ro"
            db.execute("ATTACH DATABASE ? AS a1", (queue_path,))
            result["chain"] = await wait_for(lambda: accepted(db, obs, demo, args.stage != "baseline", version),
                                             args.timeout, "causal execution, durable cloud receipts and policy ACKs")
            result["cloud_samples"] = dict(db.execute(
                "SELECT sensor_node_id, COUNT(*) FROM sensor_data GROUP BY sensor_node_id"))
        result["status"] = "passed"
    finally:
        try:
            await demo.stop()
        finally:
            transport_observer.reset(token)
            result["elapsed_s"] = round(time.monotonic() - obs.start, 6)
            result["received_envelope_bytes"] = dict(obs.bytes)
            result["received_messages"] = {f"{a}/{b}": count for (a, b), count in sorted(obs.by_type.items())}
            result["sensor_metrics"] = {k: v.metrics.as_dict() for k, v in demo.sensors.items()}
            result["field_metrics"] = dict(demo.field_transport.metrics)
            result["contended_example"] = next((r for r in demo.field_transport.decisions
                                                if len(r["candidates"]) > 1), None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--output", type=Path, required=True, help="JSON summary path")
    parser.add_argument("--on-ready-file", type=Path)
    parser.add_argument("--backhaul-a1-port", type=int)
    parser.add_argument("--backhaul-a2-port", type=int)
    parser.add_argument("--sample-interval", type=float, default=0.25)
    parser.add_argument("--observation-seconds", type=float, default=6.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    ports = (args.backhaul_a1_port, args.backhaul_a2_port)
    if args.stage == "mpquic" and (None in ports or len(set(ports)) < 2
                                   or any(p == config.SERVER_PORT or not 0 < p <= 65535 for p in ports)):
        parser.error("mpquic requires two distinct bridge listening ports separate from the cloud server")
    if args.stage != "mpquic" and any(p is not None for p in ports):
        parser.error("bridge ports apply only to the mpquic stage")
    if any(not math.isfinite(v) or v <= 0 for v in (args.sample_interval, args.observation_seconds, args.timeout)):
        parser.error("timing options must be positive and finite")
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.on_ready_file:
        args.on_ready_file = args.on_ready_file.resolve()
        if args.on_ready_file.exists():
            parser.error("use a fresh ready-marker path for each run")
    workdir = Path(tempfile.mkdtemp(prefix=f"{args.stage}-", dir=args.output.parent))
    result = {"stage": args.stage, "status": "failed", "evidence_directory": workdir.name}
    cwd = Path.cwd()
    os.chdir(workdir)
    try:
        asyncio.run(run(args, result))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        os.chdir(cwd)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"{args.stage} {result['status']} | {args.output}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
