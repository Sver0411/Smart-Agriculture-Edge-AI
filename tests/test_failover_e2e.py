"""End to end reliability: failover, offline operation and idempotency.

These are the four claims the v0.2 README makes, exercised over real TCP
sockets with real nodes.  They are slower than the unit tests (a few seconds
each) but they are the only ones that would catch a protocol level mistake.
"""

import asyncio
import pathlib
import socket

import pytest

from common import config
from common.messages import (
    CONTROL_COMMAND,
    CONTROL_RESULT,
    NODE_REGISTER,
    NODE_REGISTER_ACK,
    SENSOR_DATA,
    Message,
    read_message,
    send_message,
)
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


class Harness:
    """Starts a small system (one or two gateways) and shuts it down again.

    Gateways use their real ports from ``config.GATEWAY_PORTS`` so that node
    fallback (B / C walking the candidate list) works exactly as in production.
    """

    def __init__(self, tmp_path, server_port: int | None = None):
        self.tmp_path = tmp_path
        self.db_path = str(tmp_path / "server.db")
        self.server_port = server_port or free_port()
        self.server = Server(port=self.server_port, db_path=self.db_path, policy_interval=0.5)
        self.gateways: dict[str, Gateway] = {}
        self.tasks: list[asyncio.Task] = []

    async def add_gateway(self, gateway_id: str, **kwargs) -> Gateway:
        peer_id = config.PEER_OF[gateway_id]
        gateway = Gateway(
            gateway_id,
            port=config.GATEWAY_PORTS[gateway_id],
            peer_port=config.GATEWAY_PORTS[peer_id],
            server_port=self.server_port,
            queue_path=str(self.tmp_path / f"queue_{gateway_id}.db"),
            heartbeat_interval=kwargs.pop("heartbeat_interval", 0.3),
            heartbeat_timeout=kwargs.pop("heartbeat_timeout", 1.0),
            **kwargs,
        )
        self.gateways[gateway_id] = gateway
        await gateway.start()
        return gateway

    def add_node(self, node) -> asyncio.Task:
        task = asyncio.create_task(node.run())
        self.tasks.append(task)
        return task

    async def stop(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        for gateway in list(self.gateways.values()):
            await gateway.stop()
        await self.server.stop()


def command_message(command_id: str, generation: int, source: str, target: str) -> Message:
    return Message(
        type=CONTROL_COMMAND,
        source=source,
        target=target,
        payload={
            "command_id": command_id,
            "type": "IRRIGATION",
            "duration": 5,
            "gateway_generation": generation,
        },
    )


# --------------------------------------------------------------------------
# 1. Node registration and ownership
# --------------------------------------------------------------------------


def test_a_node_registration_is_acknowledged_with_owner_and_epoch(tmp_path):
    async def scenario():
        harness = Harness(tmp_path)
        await harness.server.start()
        gateway = await harness.add_gateway("A1")

        reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
        try:
            await send_message(
                writer,
                Message(
                    type=NODE_REGISTER,
                    source="C1",
                    target="A1",
                    payload={"node_id": "C1", "node_type": config.CONTROLLER},
                ),
            )
            reply = await asyncio.wait_for(read_message(reader), timeout=3.0)
        finally:
            writer.close()
            await harness.stop()

        assert reply is not None
        return reply

    reply = asyncio.run(scenario())
    assert reply.type == NODE_REGISTER_ACK
    assert reply.payload["owner_gateway"] == "A1"
    assert reply.payload["generation"] == config.INITIAL_GENERATION
    assert reply.payload["accepted"] is True


def test_the_registry_learns_about_a_registered_node(tmp_path):
    async def scenario():
        harness = Harness(tmp_path)
        await harness.server.start()
        gateway = await harness.add_gateway("A1")

        reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
        try:
            await send_message(
                writer,
                Message(
                    type=NODE_REGISTER,
                    source="B1",
                    target="A1",
                    payload={"node_id": "B1", "node_type": config.SENSOR},
                ),
            )
            await asyncio.wait_for(read_message(reader), timeout=3.0)
            await asyncio.sleep(0.2)
        finally:
            writer.close()
            await harness.stop()

        return gateway.registry.get("B1")

    entry = asyncio.run(scenario())
    assert entry is not None
    assert entry.node_type == config.SENSOR
    assert entry.owner_gateway == "A1"
    assert entry.status == config.ONLINE


# --------------------------------------------------------------------------
# 2. Gateway failover
# --------------------------------------------------------------------------


def test_a_dead_gateway_loses_its_nodes_to_the_peer(tmp_path):
    """A2 must own B1 / C1 and move to a new epoch once A1 stops answering."""

    async def scenario():
        harness = Harness(tmp_path)
        await harness.server.start()
        a1 = await harness.add_gateway("A1")
        a2 = await harness.add_gateway("A2")

        sensor = SensorNode(
            "B1",
            simulator=SensorSimulator("B1", seed=3, start={"soil_moisture": 19.0}),
            slow_interval=0.4,
            fast_interval=0.3,
        )
        controller = ControllerNode("C1")
        harness.add_node(sensor)
        harness.add_node(controller)

        await asyncio.sleep(1.2)
        assert a1.registry.get("C1").owner_gateway == "A1"

        # A1 dies. B1 / C1 fall back to A2 on their own, and the watchdog in A2
        # then declares A1 dead and takes over formally (new epoch).
        await a1.stop()
        await asyncio.sleep(3.5)

        a2_generation = a2.ownership.generation
        owner_of_c1 = a2.registry.get("C1").owner_gateway
        c1_generation = a2.registry.get("C1").generation
        await harness.stop()
        return a2_generation, owner_of_c1, c1_generation

    generation, owner, c1_generation = asyncio.run(scenario())
    assert owner == "A2"
    assert generation > config.INITIAL_GENERATION, "the epoch must move on failover"
    assert c1_generation == generation, "the taken-over node carries the new epoch"


def test_a_deposed_gateway_can_no_longer_move_the_actuator(tmp_path):
    """The split-brain guard: a late command from the old epoch is refused."""

    async def scenario():
        harness = Harness(tmp_path)
        await harness.server.start()
        a1 = await harness.add_gateway("A1")
        await harness.add_gateway("A2")

        controller = ControllerNode("C1")
        harness.add_node(controller)
        await asyncio.sleep(0.8)
        assert controller.guard.current_generation == 1

        # C1 is told that A2 now owns it at epoch 2
        controller.guard.set_ownership("A2", 2)

        # ... and then a command from the deposed A1 arrives late
        stale = command_message("stale-1", generation=1, source="A1", target="C1")
        result = await controller.process_command(stale)

        await harness.stop()
        return result

    result = asyncio.run(scenario())
    assert result["status"] == "REJECTED"
    assert result["reason"] == "STALE_GENERATION"
    assert "executed" not in result


def test_a_recovering_gateway_does_not_take_control_back(tmp_path):
    """No automatic failback: the returning gateway becomes STANDBY."""

    async def scenario():
        harness = Harness(tmp_path)
        await harness.server.start()
        a1 = await harness.add_gateway("A1")
        a2 = await harness.add_gateway("A2")

        await asyncio.sleep(1.5)  # exchange a few heartbeats
        a2.ownership.takeover(["B1", "C1"])  # A2 took over while A1 was down
        await asyncio.sleep(1.5)  # A1 learns about the newer epoch

        role = a1.ownership.role
        await harness.stop()
        return role

    assert asyncio.run(scenario()) == config.STANDBY


# --------------------------------------------------------------------------
# 3. Controller idempotency
# --------------------------------------------------------------------------


def test_a_replayed_command_is_not_executed_twice(tmp_path):
    """At-least-once delivery is only safe because the receiver is idempotent."""

    async def scenario():
        harness = Harness(tmp_path)
        await harness.server.start()
        a1 = await harness.add_gateway("A1")

        controller = ControllerNode("C1")
        harness.add_node(controller)
        await asyncio.sleep(0.8)

        message = command_message("same-id", generation=1, source="A1", target="C1")
        first = await controller.process_command(message)
        second = await controller.process_command(message)

        await harness.stop()
        return first, second, controller.metrics.as_dict()

    first, second, metrics = asyncio.run(scenario())
    assert first["status"] == "EXECUTED"
    assert second["status"] == "DUPLICATE"
    assert second["reason"] == "DUPLICATE_COMMAND_ID"
    assert metrics["executed"] == 1
    assert metrics["duplicates"] == 1


def test_duplicate_command_injection_never_reaches_the_actuator(tmp_path):
    """``--duplicate-command`` sends every command twice on purpose."""

    async def scenario():
        harness = Harness(tmp_path)
        await harness.server.start()
        a1 = await harness.add_gateway("A1", duplicate_command=True)
        a1.registry.upsert("C1", config.CONTROLLER, "A1", generation=1)

        controller = ControllerNode("C1")
        harness.add_node(controller)

        sensor = SensorNode(
            "B1",
            simulator=SensorSimulator("B1", seed=5, start={"soil_moisture": 18.0}),
            slow_interval=0.4,
            fast_interval=0.3,
        )
        harness.add_node(sensor)

        await asyncio.sleep(2.5)
        metrics = dict(controller.metrics.as_dict())
        await harness.stop()
        return metrics

    metrics = asyncio.run(scenario())
    assert metrics.get("executed", 0) >= 1
    assert metrics.get("duplicates", 0) >= 1, "the injected copy must be recognised"


def test_an_unacknowledged_command_is_retried_then_declared_failed(tmp_path):
    """A lost frame must be retransmitted a bounded number of times.

    ``drop_command_rate=1.0`` loses every frame, so the delivery can never
    succeed: after ``MAX_RETRIES`` retransmissions the gateway must give up and
    raise an alert instead of silently forgetting the command.
    """

    async def scenario():
        harness = Harness(tmp_path)
        await harness.server.start()
        a1 = await harness.add_gateway("A1", drop_command_rate=1.0)
        # speed the retry policy up so the test does not wait ~9 seconds
        a1.tracker.timeout = 0.3

        controller = ControllerNode("C1")
        harness.add_node(controller)

        sensor = SensorNode(
            "B1",
            simulator=SensorSimulator("B1", seed=13, start={"soil_moisture": 17.0}),
            slow_interval=0.4,
            fast_interval=0.3,
        )
        harness.add_node(sensor)

        await asyncio.sleep(4.0)
        result = (
            a1.metrics.get("retries"),
            a1.metrics.get("delivery_failures"),
            dict(controller.metrics.as_dict()),
        )
        await harness.stop()
        return result

    retries, failures, controller_metrics = asyncio.run(scenario())
    assert retries >= config.MAX_RETRIES, "every lost frame must be retransmitted"
    assert failures >= 1, "a command that never got an ACK must be reported"
    assert controller_metrics.get("executed", 0) == 0, "nothing reached the actuator"


# --------------------------------------------------------------------------
# 4. Edge autonomy / offline operation
# --------------------------------------------------------------------------

def test_the_farm_keeps_working_while_the_server_is_down(tmp_path):
    """Store-and-forward: nothing is lost, and history is replayed later."""

    async def scenario():
        harness = Harness(tmp_path)
        await harness.server.start()
        gateway = await harness.add_gateway("A1")

        sensor = SensorNode(
            "B1",
            simulator=SensorSimulator("B1", seed=9, start={"soil_moisture": 18.0}),
            slow_interval=0.3,
            fast_interval=0.25,
        )
        controller = ControllerNode("C1", gateway_port=gateway.port)
        harness.add_node(sensor)
        harness.add_node(controller)

        await asyncio.sleep(1.5)
        # the uplink dies
        await harness.server.stop()
        await asyncio.sleep(2.0)

        queued = gateway.offline_queue.count()
        commands_while_offline = gateway.metrics.get("commands")
        executed_while_offline = controller.metrics.get("executed")

        # ... and comes back: everything queued must be replayed
        harness.server = Server(
            port=harness.server_port, db_path=harness.db_path, policy_interval=0.5
        )
        await harness.server.start()
        await asyncio.sleep(3.0)

        result = (queued, commands_while_offline, executed_while_offline,
                  gateway.metrics.get("queue_replayed"))
        await harness.stop()
        return result

    queued, commands, executed, replayed = asyncio.run(scenario())
    assert queued > 0, "uploads must be queued, never dropped"
    assert commands > 0, "the edge keeps deciding while the server is down"
    assert executed > 0, "the edge keeps acting while the server is down"
    assert replayed >= queued, "the whole queue has to be replayed"


def test_the_server_ignores_a_replayed_upload(tmp_path):
    """The same message_id may arrive twice; it is stored exactly once."""

    async def scenario():
        harness = Harness(tmp_path)
        await harness.server.start()
        await asyncio.sleep(0.2)

        reader, writer = await asyncio.open_connection("127.0.0.1", harness.server_port)
        try:
            message = Message(
                type=SENSOR_DATA,
                source="A1",
                target="SERVER",
                payload={"record": {"sensor_node_id": "B1", "soil_moisture": 20.0}},
            )
            await send_message(writer, message)
            await send_message(writer, message)  # replayed by the queue
            await asyncio.sleep(0.6)
        finally:
            writer.close()

        ignored = harness.server.dedup.ignored
        await harness.stop()
        return ignored

    assert asyncio.run(scenario()) >= 1

    db = Database(str(tmp_path / "server.db")).connect()
    try:
        assert db.count("sensor_data") == 1
    finally:
        db.close()


def test_a_policy_that_is_not_newer_is_ignored(tmp_path):
    """Policy versions are monotonic: an old policy must not win."""

    async def scenario():
        harness = Harness(tmp_path)
        await harness.server.start()
        gateway = await harness.add_gateway("A1")
        await asyncio.sleep(0.3)

        new = {"policy_version": 5, **config.DEFAULT_POLICY}
        old = {"policy_version": 3, **config.DEFAULT_POLICY}

        applied_new, _ = gateway.decider.update_policy(new)
        applied_old, _ = gateway.decider.update_policy(old)
        version = gateway.decider.policy_version

        await harness.stop()
        return applied_new, applied_old, version

    applied_new, applied_old, version = asyncio.run(scenario())
    assert applied_new is True
    assert applied_old is False
    assert version == 5
