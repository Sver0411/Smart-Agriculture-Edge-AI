"""End to end: B -> A -> C -> A -> Server over real TCP sockets."""

import asyncio
import pathlib
import shutil
import socket
import tempfile

from controller_node.controller_node import ControllerNode
from gateway.gateway import Gateway
from sensor_node.sensor_node import SensorNode, SensorSimulator
from server.database import Database
from server.server import Server

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_full_chain_reaches_the_database():
    scratch = tempfile.mkdtemp(prefix=".pytest-tmp-", dir=PROJECT_ROOT)
    db_path = str(pathlib.Path(scratch) / "e2e.db")
    server_port = free_port()
    gateway_port = free_port()
    peer_port = free_port()  # nothing listens there: A1 simply has no peer in this test

    async def scenario() -> None:
        server = Server(port=server_port, db_path=db_path, policy_interval=0.5)
        gateway = Gateway("A1", port=gateway_port, server_port=server_port, peer_port=peer_port)
        sensor = SensorNode(
            "B1",
            gateway_port=gateway_port,
            simulator=SensorSimulator("B1", seed=7, start={"soil_moisture": 18.0}),
            slow_interval=0.3,
            fast_interval=0.2,
        )
        controller = ControllerNode("C1", gateway_port=gateway_port)

        await server.start()
        await gateway.start()
        tasks = [asyncio.create_task(sensor.run()), asyncio.create_task(controller.run())]
        try:
            await asyncio.sleep(2.5)
        finally:
            sensor.stop()
            controller.stop()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await gateway.stop()
            await server.stop()

    try:
        asyncio.run(scenario())

        db = Database(db_path).connect()
        try:
            assert db.count("sensor_data") >= 1
            assert db.count("controller_command") >= 1
            assert db.count("controller_result") >= 1

            results = db.recent_controller_results(20)
            assert "EXECUTED" in {row["status"] for row in results}
            # the second irrigation request arrives inside the 60 s cooldown
            assert "COOLDOWN" in {row["reason"] for row in results}

            stored = db.recent_sensor_data(1)[0]
            assert stored["gateway_id"] == "A1"
            assert stored["sensor_node_id"] == "B1"
            assert stored["health_state"] == "HEALTHY"
        finally:
            db.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
