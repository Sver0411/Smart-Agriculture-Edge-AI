"""Sensor ownership reception and liveness independent of sampling."""
import asyncio
import socket

from common import config
from common.messages import Message, NODE_STATUS
from gateway.gateway import Gateway
from sensor_node.sensor_node import SensorNode, SensorSimulator


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def status(source, owner, generation):
    return Message(
        type=NODE_STATUS, source=source, target="B1",
        payload={"node_id": "B1", "status": config.ONLINE,
                 "owner_gateway": owner, "generation": generation},
    )


def test_sensor_accepts_newer_status_and_rejects_stale_or_spoofed_owner(capsys):
    sensor = SensorNode("B1")
    assert sensor._adopt_ownership(status("A2", "A2", 2), "A2")
    assert (sensor.owner_gateway, sensor.generation) == ("A2", 2)
    assert not sensor._adopt_ownership(status("A2", "A2", 1), "A2")
    assert not sensor._adopt_ownership(status("A2", "A1", 3), "A2")
    assert not sensor._adopt_ownership(status("A1", "A2", 3), "A2")
    assert (sensor.owner_gateway, sensor.generation) == ("A2", 2)
    output = capsys.readouterr().out
    assert "owner_gateway=A2 generation=2" in output
    assert "ignored stale NODE_STATUS generation=1 < current=2" in output


def test_keepalive_keeps_sensor_online_during_silent_sampling(tmp_path):
    async def scenario():
        gateway_port, server_port, peer_port = free_port(), free_port(), free_port()
        gateway = Gateway("A1", port=gateway_port, server_port=server_port,
                          peer_port=peer_port, heartbeat_interval=0.05,
                          queue_path=str(tmp_path / "gateway.db"))
        sensor = SensorNode("B1", gateway_port=gateway_port,
                            simulator=SensorSimulator("B1", seed=7),
                            slow_interval=5.0, fast_interval=5.0,
                            keepalive_interval=0.05)
        await gateway.start()
        task = asyncio.create_task(sensor.run())
        try:
            await asyncio.sleep(0.8)  # > 0.3 s node timeout, < 5 s next sample
            assert sensor.simulator.samples == 1
            assert gateway.registry.expire(timeout=0.3) == []
            assert gateway.registry.get("B1").status == config.ONLINE
            assert gateway.registry.get("B1").last_seen > 0
        finally:
            sensor.stop()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await gateway.stop()

    asyncio.run(scenario())
