"""Client timestamps are application data, never node-liveness time."""
import asyncio
import socket
import time

from common import config
from common.messages import (ALERT, CONTROL_RESULT, NODE_REGISTER, NODE_STATUS,
                             SENSOR_DATA, Message, read_message, send_message)
from gateway.gateway import Gateway


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_gateway_uses_receipt_time_for_register_status_data_alert_and_result(tmp_path):
    async def scenario():
        gateway_port, server_port, peer_port = free_port(), free_port(), free_port()
        gateway = Gateway("A1", port=gateway_port, server_port=server_port,
                          peer_port=peer_port, queue_path=str(tmp_path / "gateway.db"))
        await gateway.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", gateway_port)
        try:
            async def send_and_check(message):
                before = time.time()
                await send_message(writer, message)
                await asyncio.sleep(0.03)
                entry = gateway.registry.get(message.source)
                assert before <= entry.last_seen <= time.time()
                assert entry.last_seen != 123.0
                assert gateway.registry.expire(timeout=1.0) == []

            await send_and_check(Message(
                type=NODE_REGISTER, source="B1", target="A1", timestamp=123.0,
                payload={"node_id": "B1", "node_type": config.SENSOR}))
            assert (await read_message(reader)).type == "NODE_REGISTER_ACK"
            await send_and_check(Message(
                type=NODE_STATUS, source="B1", target="A1", timestamp=123.0,
                payload={"node_id": "B1", "status": config.ONLINE}))
            await send_and_check(Message(
                type=SENSOR_DATA, source="B1", target="A1", timestamp=123.0,
                payload={"data": {"temperature": 25, "humidity": 60,
                                  "soil_moisture": 40, "light": 800},
                         "health_state": "HEALTHY"}))
            await send_and_check(Message(
                type=ALERT, source="B1", target="A1", timestamp=123.0,
                payload={"alert_type": "SENSOR_FAULT", "reasons": ["test"]}))
            await send_and_check(Message(
                type=NODE_REGISTER, source="C1", target="A1", timestamp=123.0,
                payload={"node_id": "C1", "node_type": config.CONTROLLER}))
            assert (await read_message(reader)).type == "NODE_REGISTER_ACK"
            await send_and_check(Message(
                type=CONTROL_RESULT, source="C1", target="A1", timestamp=123.0,
                payload={"command_id": "test", "status": "REJECTED"}))
        finally:
            writer.close()
            await gateway.stop()

    asyncio.run(scenario())
