"""Opt-in TAIS through the B node, durable receiver and actual B1 C policy."""
import asyncio
from pathlib import Path
import subprocess

from common.messages import Message
from common.settings import node_settings
from gateway.gateway import Gateway
from sensor_node.sensor_node import SensorNode
from sensor_node.sensor_trust import SensorTrust
from sensor_node.tais_policy import TaisPolicy

ROOT = Path(__file__).resolve().parents[1]


def receipt(message, scope="GATEWAY_OUTBOX"):
    return Message(type="PERSISTED_ACK", source="A1", target="B1",
                   payload={"ack_message_id": message.message_id, "scope": scope,
                            "persisted": True, "delivery_contract": "gateway-durable-v1"})


def test_real_sensor_loop_durable_gateway_and_delayed_ack(tmp_path, monkeypatch):
    async def run():
        class Source:
            def sample(self):
                temp = 31.0 if node.sample_sequence == 0 else 33.0
                if node.sample_sequence == 1:
                    node.stop()
                return {"temperature": temp, "humidity": 65.0, "light": 500, "soil_moisture": 30}

        node = SensorNode("B1", simulator=Source(), sensing_policy="tais-jalc",
                          delivery_mode="gateway-durable", state_path=str(tmp_path / "node.db"),
                          slow_interval=0.02, fast_interval=0.02)
        gateway = Gateway("A1", queue_path=str(tmp_path / "gateway.db"))
        gateway.sensor_boots["B1"] = node.boot_id
        gateway.connections["B1"] = object()
        replies = []

        async def send(_writer, m):
            replies.append(m)

        monkeypatch.setattr("gateway.gateway.send_message", send)
        try:
            await node._sample_loop(None, None)
            window = node.report_window
            row = next(iter(window.evidence.values()))
            t = max(r["acquired_at"] for r in window.evidence.values())
            first = Message.from_dict(row["message"])
            assert not window.confirm(receipt(first), node.scheduler, "A1")
            older, newer = window.due(t, "A1", node.scheduler)
            assert all(m.payload["sampling"]["sensing_policy"] == "tais-jalc" for m in [older, newer])
            assert older.payload["sampling"]["tais_mode"] == "QUIET_ECO"
            assert not window.confirm(receipt(older, "SERVER_SQLITE"), node.scheduler, "A1")
            await gateway._process_sensor_message(newer)
            ack = next(r for r in replies if r.type == "PERSISTED_ACK")
            assert window.confirm(ack, node.scheduler, "A1")
            assert node.scheduler.guard.relevance.reported["temperature"] == 33.0
            assert window.confirm(receipt(older), node.scheduler, "A1")
            assert not window.confirm(receipt(older), node.scheduler, "A1")
            assert node.scheduler.guard.relevance.reported["temperature"] == 33.0
            # The kernel uses the confirmed report's acquisition (and content).
            clean = {"temperature": 33.0, "humidity": 65.0, "light": 500, "soil_moisture": 30}
            nxt = node.scheduler.next_due + 0.001
            result = node.scheduler.update(clean, node.trust.update(clean, nxt), nxt)
            assert "FIRST_SAMPLE" not in result["upload_reasons"]
            assert "DEADBAND" not in result["upload_reasons"]
        finally:
            gateway.offline_queue.close()

    asyncio.run(run())


def test_selected_b1_kernel_matches_host_and_preserves_faults(tmp_path):
    main = ROOT / "firmware/b1/main"
    comp = main.parent / "components"
    trust, adaptive = comp / "sensor_trust", comp / "adaptive_sense"
    tais, bridge = ROOT / "third_party/tais", ROOT / "sensor_node/jalc_bridge"
    cjson = ROOT / "third_party/cjson"
    flags = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-DB1_HOST_TEST",
             "-DCONFIG_B1_LAB_MODE=1", "-DCONFIG_B1_TAIS_JALC=1"]
    includes = [main, trust, adaptive, tais, bridge, cjson, ROOT / "tests/c_host/stubs"]
    sources = [main / n for n in ("b1_policy.c", "b1_queue.c", "b1_telemetry.c", "b1_outbox.c")]
    sources += [trust / "sensor_trust.c", adaptive / "adaptive_scheduler.c",
                adaptive / "change_detector.c", tais / "tais_jalc.c", bridge / "agri_jalc.c",
                cjson / "cJSON.c", ROOT / "tests/c_host/b1_policy_trace.c"]
    exe = tmp_path / "b1"
    subprocess.run(["cc", *flags, *["-I" + str(i) for i in includes], *sources,
                    "-lm", "-o", exe], check=True)
    samples = [(0, 31., 60.), (30, 33., 60.), (60, 33., 157.), (90, 33., 60.)]
    stdin = "".join(f"{t*1000} {temp} {humidity} 1\n" for t, temp, humidity in samples)
    c_rows = subprocess.check_output([exe], input=stdin, text=True).splitlines()
    settings = node_settings("lab", physical=True)
    policy, health = TaisPolicy(settings), SensorTrust(settings["trust_channels"])
    for seq, ((t, temp, hum), line) in enumerate(zip(samples, c_rows, strict=True), 1):
        sample = {"temperature": temp, "humidity": hum}
        evidence = health.update(sample, t)
        schedule = policy.update(sample, evidence, t)
        mode, ms, _, upload, *_ = line.split()
        assert (mode, int(ms), bool(int(upload))) == (
            schedule["tais_mode"], round(schedule["interval_s"] * 1000), schedule["upload_requested"])
        if t == 30:
            assert "CONTROL_THRESHOLD_CROSSING" in schedule["upload_reasons"]
        if t == 60:
            assert "SENSOR_FAULT" in schedule["upload_reasons"]
        if schedule["upload_requested"]:
            policy.confirm_report(sample, evidence, timestamp=t, sequence=seq, schedule=schedule)


def test_confirmed_snapshot_is_the_older_report_even_when_newer_is_pending():
    settings = node_settings("lab", physical=True)
    policy = TaisPolicy(settings)
    health = SensorTrust(settings["trust_channels"])
    older = {"temperature": 25.0, "humidity": 60.0}
    newer = {"temperature": 26.0, "humidity": 62.0}
    old_health = health.update(older, 0)
    old_schedule = policy.update(older, old_health, 0)
    policy.update(newer, health.update(newer, 30), 30)
    assert policy.confirm_report(older, old_health, timestamp=0, sequence=1, schedule=old_schedule)
    decision = policy.update(older, health.update(older, 60), 60)
    assert "DEADBAND" not in decision["upload_reasons"]
    assert "AOI_CAP" in decision["upload_reasons"]  # acquisition at 0, not receipt at 30
