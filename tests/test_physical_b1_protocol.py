"""Wire-format compatibility for physical B1 without requiring a board in CI."""
import asyncio
import json
import socket

from common.messages import Message, NODE_REGISTER, SENSOR_DATA, ALERT, read_message, send_message
from gateway.gateway import Gateway
from server.database import Database
from server.server import Server


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_physical_partial_data_and_fault_evidence_reach_server(tmp_path):
    async def scenario():
        server_port, gateway_port, peer_port = free_port(), free_port(), free_port()
        server = Server(port=server_port, db_path=str(tmp_path / "server.db"))
        gateway = Gateway("A1", port=gateway_port, server_port=server_port,
                          peer_port=peer_port, queue_path=str(tmp_path / "queue.db"))
        await server.start()
        await gateway.start()
        await asyncio.sleep(0.3)
        reader, writer = await asyncio.open_connection("127.0.0.1", gateway_port)
        try:
            await send_message(writer, Message(
                type=NODE_REGISTER, source="B1", target="A1", timestamp=1.0,
                message_id="B1-boot-000001",
                payload={"node_id": "B1", "node_type": "SENSOR", "node_mode": "physical"}))
            reply = await asyncio.wait_for(read_message(reader), 2)
            assert reply.type == "NODE_REGISTER_ACK"
            assert reply.payload["generation"] == 1
            base = {"node_mode": "physical", "boot_id": "boot", "sample_seq": 1,
                    "device_monotonic_ms": 1234, "sampling": {"mode": "STABLE", "next_interval_ms": 5000},
                    "health": {"temperature": {"state": "HEALTHY", "score": 100, "flags": 0},
                               "humidity": {"state": "HEALTHY", "score": 100, "flags": 0}}}
            await send_message(writer, Message(
                type=SENSOR_DATA, source="B1", target="A1", timestamp=1.234,
                message_id="B1-boot-000002",
                payload={**base, "data": {"temperature": 27.31, "humidity": 61.2},
                         "usable_for_control": True}))
            await send_message(writer, Message(
                type=SENSOR_DATA, source="B1", target="A1", timestamp=2.234,
                message_id="B1-boot-000003",
                payload={**base, "sample_seq": 2, "data": {"temperature": 150, "humidity": 61.2},
                         "health_state": "FAULT", "usable_for_control": False,
                         "health": {"temperature": {"state": "FAULT", "score": 45, "flags": 1}}}))
            await send_message(writer, Message(
                type=ALERT, source="B1", target="A1", timestamp=2.234,
                message_id="B1-boot-000004",
                payload={"alert_type": "SENSOR_FAULT", "health_state": "FAULT",
                         "sensor_node_id": "B1", "message": "integration fault injection"}))
            await asyncio.sleep(0.8)
            assert gateway.metrics.get("sensor_control_skipped") >= 1
            assert gateway.metrics.get("insufficient_sensor_fields") == 0
            assert gateway.metrics.get("commands") == 0  # no soil or hot temperature
            assert server.metrics.get("sensor_messages") == 2
            assert server.metrics.get("alerts") == 1
        finally:
            writer.close()
            await gateway.stop()
            await server.stop()

    asyncio.run(scenario())
    db = Database(str(tmp_path / "server.db")).connect()
    try:
        rows = db.recent_sensor_data(2)
        assert all(row["soil_moisture"] is None for row in rows)
        assert all(row["timestamp"] > 1_000_000_000 for row in rows)
        metadata = [json.loads(row["metadata_json"]) for row in rows]
        assert {item["sample_seq"] for item in metadata} == {1, 2}
        assert all(item["node_mode"] == "physical" for item in metadata)
        assert any(item["health"]["temperature"]["state"] == "FAULT" for item in metadata)
    finally:
        db.close()
