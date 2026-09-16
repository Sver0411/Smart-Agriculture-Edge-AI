"""Edge gateway A1 / A2 - the core of Smart Agriculture Edge AI v0.2.

A gateway talks to four different peers at the same time (sensor B, controller
C, the cloud server and the other gateway), so the work is split into
independent :mod:`asyncio` tasks that never block each other::

    Task 1  task_sensor_data    receive SENSOR_DATA from B, run the edge decision
    Task 2  task_upload         upload to the server (store-and-forward when down)
    Task 3  task_server_policy  receive SERVER_POLICY from the server
    Task 4  task_send_commands  send CONTROL_COMMAND to C, wait for its ACK
    Task 5  task_control_result process the CONTROL_RESULT coming back from C
    Task 6  task_heartbeat      peer heartbeat, watchdog, failover
    Task 7  task_retry          retransmit messages whose ACK never arrived

Topology (B and C are siblings, C is *not* behind B)::

        A1
       /  \\
     B1    C1
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import config  # noqa: E402
from common.log import node_log  # noqa: E402
from common.messages import (  # noqa: E402
    ACK,
    ALERT,
    CONTROL_COMMAND,
    CONTROL_RESULT,
    HEARTBEAT,
    NODE_REGISTER,
    NODE_REGISTER_ACK,
    NODE_STATUS,
    SENSOR_DATA,
    SERVER_POLICY,
    Message,
    MessageError,
    close_writer,
    read_message,
    send_message,
)
from common.reliability import AckTracker, COMMAND_DELIVERY_FAILED, Counters  # noqa: E402
from gateway.edge_decision import EdgeDecider  # noqa: E402
from gateway.offline_queue import OfflineQueue  # noqa: E402
from gateway.ownership import OwnershipManager  # noqa: E402
from gateway.registry import NodeRegistry  # noqa: E402

# Message types worth keeping while the uplink is down.
QUEUEABLE_TYPES = (SENSOR_DATA, CONTROL_COMMAND, CONTROL_RESULT, ALERT)


class Gateway:
    """One edge gateway (``A1`` or ``A2``)."""

    def __init__(
        self,
        gateway_id: str,
        host: str = "127.0.0.1",
        port: int | None = None,
        server_host: str = config.SERVER_HOST,
        server_port: int = config.SERVER_PORT,
        peer_host: str = "127.0.0.1",
        peer_port: int | None = None,
        sensor_id: str | None = None,
        controller_id: str | None = None,
        heartbeat_interval: float = config.HEARTBEAT_INTERVAL,
        heartbeat_timeout: float = config.HEARTBEAT_TIMEOUT,
        queue_path: str | None = None,
        drop_command_rate: float = 0.0,
        duplicate_command: bool = False,
    ):
        if gateway_id not in config.GATEWAY_PORTS:
            raise ValueError(f"unknown gateway id: {gateway_id!r}")

        self.gateway_id = gateway_id
        self.peer_id = config.PEER_OF[gateway_id]
        self.sensor_id = sensor_id or config.SENSOR_OF[gateway_id]
        self.controller_id = controller_id or config.CONTROLLER_OF[gateway_id]
        self.peer_sensor_id = config.SENSOR_OF[self.peer_id]
        self.peer_controller_id = config.CONTROLLER_OF[self.peer_id]

        self.host = host
        self.port = port if port is not None else config.GATEWAY_PORTS[gateway_id]
        self.server_host = server_host
        self.server_port = server_port
        self.peer_host = peer_host
        self.peer_port = peer_port if peer_port is not None else config.GATEWAY_PORTS[self.peer_id]

        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout

        # fault injection knobs (demo only - they default to "no fault")
        self.drop_command_rate = drop_command_rate
        self.duplicate_command = duplicate_command

        self.decider = EdgeDecider()
        self.registry = NodeRegistry()
        self.ownership = OwnershipManager(gateway_id, self.peer_id, self.registry)
        self.tracker = AckTracker()
        self.offline_queue = OfflineQueue(queue_path or ":memory:")
        self.metrics = Counters()

        # Connected B / C nodes, keyed by node id.
        self.connections: dict[str, asyncio.StreamWriter] = {}
        # Every socket handed to us by the TCP server (B, C and the peer).
        self.inbound_writers: set = set()
        self.server_writer: asyncio.StreamWriter | None = None
        self.peer_writer: asyncio.StreamWriter | None = None

        self.peer_last_seen: float | None = None
        self.peer_status = config.UNKNOWN
        # last command we put on the wire (used to replay a stale command in
        # the split-brain demo: a delayed frame from a deposed gateway)
        self.last_command: Message | None = None

        # Internal message queues, one per task that consumes messages.
        self.sensor_queue: asyncio.Queue = asyncio.Queue()
        self.result_queue: asyncio.Queue = asyncio.Queue()
        self.upload_queue: asyncio.Queue = asyncio.Queue()
        self.command_queue: asyncio.Queue = asyncio.Queue()

        self._server: asyncio.AbstractServer | None = None
        self._tasks: list[asyncio.Task] = []
        self._stopping = False
        self._standby_logged = False

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        self._seed_registry()
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self._tasks = [
            asyncio.create_task(self.task_sensor_data(), name=f"{self.gateway_id}-1-sensor-data"),
            asyncio.create_task(self.task_upload(), name=f"{self.gateway_id}-2-upload"),
            asyncio.create_task(self.task_server_policy(), name=f"{self.gateway_id}-3-server-policy"),
            asyncio.create_task(self.task_send_commands(), name=f"{self.gateway_id}-4-send-commands"),
            asyncio.create_task(self.task_control_result(), name=f"{self.gateway_id}-5-control-result"),
            asyncio.create_task(self.task_heartbeat(), name=f"{self.gateway_id}-6-heartbeat"),
            asyncio.create_task(self.task_retry(), name=f"{self.gateway_id}-7-retry"),
        ]
        node_log(
            self.gateway_id,
            f"gateway started on {self.host}:{self.port} "
            f"(sensor={self.sensor_id}, controller={self.controller_id}, peer={self.peer_id}, "
            f"generation={self.ownership.generation}, role={self.ownership.role})",
        )

    def _seed_registry(self) -> None:
        """Pre-register the four known nodes so ownership works before boot."""
        self.registry.upsert(
            self.sensor_id, config.SENSOR, self.gateway_id,
            generation=self.ownership.generation, status=config.OFFLINE,
        )
        self.registry.upsert(
            self.controller_id, config.CONTROLLER, self.gateway_id,
            generation=self.ownership.generation, status=config.OFFLINE,
        )
        self.registry.upsert(
            self.peer_sensor_id, config.SENSOR, self.peer_id,
            generation=config.INITIAL_GENERATION, status=config.OFFLINE,
        )
        self.registry.upsert(
            self.peer_controller_id, config.CONTROLLER, self.peer_id,
            generation=config.INITIAL_GENERATION, status=config.OFFLINE,
        )

    async def stop(self) -> None:
        self._stopping = True
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Stop accepting, then close every socket we still hold so that the
        # ``_handle_client`` coroutines can finish.  (Since Python 3.12
        # ``Server.wait_closed()`` also waits for those handlers, so closing
        # the sockets first is what actually lets the shutdown complete.)
        if self._server is not None:
            self._server.close()
        for writer in list(self.inbound_writers):
            writer.close()
        for writer in list(self.connections.values()):
            writer.close()
        self.connections.clear()
        for writer in (self.server_writer, self.peer_writer):
            if writer is not None:
                writer.close()

        if self._server is not None:
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=2.0)
            except asyncio.TimeoutError:  # pragma: no cover - defensive
                pass
        self.offline_queue.close()

    # -- inbound connections (B, C and the peer gateway) -------------------

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.inbound_writers.add(writer)
        try:
            while True:
                try:
                    message = await read_message(reader)
                except MessageError as exc:
                    node_log(self.gateway_id, f"dropped malformed message: {exc}")
                    continue
                if message is None:
                    break

                source = message.source

                if message.type == NODE_REGISTER:
                    await self._handle_register(writer, message)
                    continue

                if message.type == ACK:
                    acked = message.payload.get("ack_message_id")
                    if self.tracker.acknowledge(acked):
                        self.metrics.inc("acks_received")
                        node_log(self.gateway_id, f"ACK received (message_id={acked})")
                    continue

                if source in (self.sensor_id, self.controller_id,
                              self.peer_sensor_id, self.peer_controller_id):
                    if self.connections.get(source) is not writer:
                        self.connections[source] = writer
                        node_log(self.gateway_id, f"{source} connected")

                if message.type == HEARTBEAT:
                    if source == self.peer_id:
                        self._on_peer_heartbeat(message)
                    continue

                if message.type == NODE_STATUS and source != self.peer_id:
                    self.registry.touch(source, message.timestamp)
                    continue

                if message.type in (SENSOR_DATA, ALERT):
                    self.registry.touch(source, message.timestamp)
                    await self.sensor_queue.put(message)
                elif message.type == CONTROL_RESULT:
                    self.registry.touch(source, message.timestamp)
                    await self.result_queue.put(message)
                else:
                    node_log(self.gateway_id, f"unexpected {message.type} from {source}")
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self.inbound_writers.discard(writer)
            for node_id, registered in list(self.connections.items()):
                if registered is writer:
                    del self.connections[node_id]
                    node_log(self.gateway_id, f"{node_id} disconnected")
            await close_writer(writer)

    async def _handle_register(self, writer, message: Message) -> None:
        """Answer a NODE_REGISTER with owner + generation."""
        node_id = message.source
        node_type = message.payload.get("node_type", config.SENSOR)
        entry = self.registry.upsert(
            node_id=node_id,
            node_type=node_type,
            owner_gateway=self.gateway_id,
            generation=self.ownership.generation,
            timestamp=message.timestamp,
            status=config.ONLINE,
        )
        self.connections[node_id] = writer
        node_log(
            self.gateway_id,
            f"{node_id} registered ({node_type}, owner={entry.owner_gateway}, generation={entry.generation})",
        )
        await send_message(
            writer,
            Message(
                type=NODE_REGISTER_ACK,
                source=self.gateway_id,
                target=node_id,
                payload={
                    "node_id": node_id,
                    "node_type": node_type,
                    "assigned_gateway": self.gateway_id,
                    "owner_gateway": self.gateway_id,
                    "generation": entry.generation,
                    "accepted": True,
                },
            ),
        )

    def _on_peer_heartbeat(self, message: Message) -> None:
        self.peer_last_seen = message.timestamp or time.time()
        role = self.ownership.observe_peer(
            config.ONLINE, message.payload.get("generation")
        )
        if role == config.STANDBY and not self._standby_logged:
            self._standby_logged = True
            node_log(
                self.gateway_id,
                f"peer ownership generation = {self.ownership.peer_generation} "
                f"(mine {self.ownership.generation}) - entering {config.STANDBY}",
            )

    # -- Task 1: receive sensor data ---------------------------------------

    async def task_sensor_data(self) -> None:
        while True:
            message = await self.sensor_queue.get()
            await self._process_sensor_message(message)

    async def _process_sensor_message(self, message: Message) -> None:
        payload = message.payload
        record = dict(payload.get("data", {}))
        health_state = payload.get("health_state", "HEALTHY")
        record.setdefault("timestamp", message.timestamp)

        node_log(self.gateway_id, f"received {message.type} from {message.source}")
        self.metrics.inc("sensor_messages")

        if message.type == ALERT or health_state != "HEALTHY":
            # Bad data must never reach the control decision.
            reasons = payload.get("reasons") or []
            node_log(
                self.gateway_id,
                f"sensor {message.source} health = {health_state} -> control decision skipped"
                + (f" ({'; '.join(reasons)})" if reasons else ""),
            )
            await self.upload_queue.put(
                Message(
                    type=ALERT,
                    source=self.gateway_id,
                    target="SERVER",
                    payload={
                        "alert_type": "SENSOR_FAULT",
                        "sensor_node_id": message.source,
                        "health_state": health_state,
                        "message": "; ".join(reasons) or "sensor reported FAULT",
                    },
                )
            )
            return

        # Server down or not: upload attempts continue, the farm keeps working.
        record.update(
            {
                "gateway_id": self.gateway_id,
                "sensor_node_id": message.source,
                "health_state": health_state,
            }
        )
        await self.upload_queue.put(
            Message(type=SENSOR_DATA, source=self.gateway_id, target="SERVER", payload={"record": record})
        )

        # Edge autonomy: this decision does not need the cloud server.
        # The actuator belongs to the *sensor's* zone, so a gateway that has
        # taken over a foreign sensor commands that zone's controller.
        target_controller = config.CONTROLLER_OF_SENSOR.get(message.source, self.controller_id)
        if not self.ownership.may_control(target_controller):
            if not self._standby_logged:
                self._standby_logged = True
                node_log(self.gateway_id, f"role={self.ownership.role} - local control disabled")
            return

        decision = self.decider.decide(record)
        if decision is None:
            node_log(
                self.gateway_id,
                f"edge decision = NONE (soil={record.get('soil_moisture')}%, temp={record.get('temperature')}C)",
            )
            return

        command = Message(
            type=CONTROL_COMMAND,
            source=self.gateway_id,
            target=target_controller,
            payload=dict(decision),
        )
        command.payload["command_id"] = command.message_id
        command.payload["gateway_generation"] = self.ownership.generation
        node_log(self.gateway_id, f"edge decision = {decision['type']} ({decision.get('reason')})")
        # the queue carries ``(message, is_retry)``: a retransmission must not
        # be mistaken for a new command, or it would reset its own retry budget
        await self.command_queue.put((command, False))

    # -- Task 2: upload to the cloud server --------------------------------

    async def task_upload(self) -> None:
        while True:
            message = await self.upload_queue.get()
            await self._flush_offline_queue()
            await self._deliver(message)

    async def _deliver(self, message: Message) -> None:
        writer = self.server_writer
        if writer is None:
            self._queue_locally(message, "server unavailable")
            return
        try:
            await send_message(writer, message)
        except (ConnectionResetError, BrokenPipeError, RuntimeError):
            self.server_writer = None
            self._queue_locally(message, "server link broken")
            return
        if message.type != HEARTBEAT:  # routine, would flood the console
            node_log(self.gateway_id, f"{message.type} uploaded to server")

    def _queue_locally(self, message: Message, cause: str) -> None:
        """Store-and-forward: never throw history away."""
        if message.type not in QUEUEABLE_TYPES:
            if message.type != HEARTBEAT:
                node_log(self.gateway_id, f"{cause}, {message.type} dropped")
            return
        self.offline_queue.enqueue(message)
        self.metrics.inc("queue_enqueued")
        node_log(
            self.gateway_id,
            f"{cause}, {message.type} queued locally (depth={self.offline_queue.count()})",
        )

    async def _flush_offline_queue(self) -> None:
        if self.server_writer is None or self.offline_queue.count() == 0:
            return
        pending = self.offline_queue.count()
        node_log(self.gateway_id, f"flushing offline queue ({pending} messages, oldest first)")
        for queue_id, message in self.offline_queue.peek(limit=100):
            try:
                await send_message(self.server_writer, message)
            except (ConnectionResetError, BrokenPipeError, RuntimeError):
                self.server_writer = None
                node_log(self.gateway_id, "server link broken during replay, stopping flush")
                return
            self.offline_queue.delete(queue_id)
            self.metrics.inc("queue_replayed")
        node_log(self.gateway_id, "offline queue empty")

    # -- Task 3: receive server policy -------------------------------------

    async def task_server_policy(self) -> None:
        while not self._stopping:
            writer = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.server_host, self.server_port), timeout=3.0
                )
            except (OSError, asyncio.TimeoutError):
                if self.server_writer is None:
                    node_log(self.gateway_id, "server not reachable, retrying in 2s")
                await asyncio.sleep(2.0)
                continue

            self.server_writer = writer
            node_log(self.gateway_id, f"connected to server {self.server_host}:{self.server_port}")
            try:
                while True:
                    message = await read_message(reader)
                    if message is None:
                        break
                    if message.type == SERVER_POLICY:
                        await send_message(writer, message.ack(self.gateway_id))
                        self._apply_policy(message)
                    else:
                        node_log(self.gateway_id, f"unexpected {message.type} from server")
            except (OSError, MessageError) as exc:
                node_log(self.gateway_id, f"server link error: {exc}")
            finally:
                self.server_writer = None
                writer.close()

            await asyncio.sleep(2.0)

    def _apply_policy(self, message: Message) -> None:
        version = int(message.payload.get("policy_version", 0))
        applied, policy = self.decider.update_policy(message.payload)
        if not applied:
            node_log(
                self.gateway_id,
                f"SERVER_POLICY v{version} ignored (already at v{self.decider.policy_version})",
            )
            return
        node_log(
            self.gateway_id,
            f"SERVER_POLICY v{version} applied "
            f"(soil<{policy['soil_moisture_threshold']} -> {policy['irrigation_duration']}s, "
            f"temp>{policy['temperature_threshold']} -> {policy['ventilation_duration']}s)",
        )
        node_log(self.gateway_id, "edge autonomy intact: policy is advisory, control stays local")

    # -- Task 4: send control commands to C --------------------------------

    async def task_send_commands(self) -> None:
        while True:
            message, is_retry = await self.command_queue.get()
            await self._dispatch_command(message, first_attempt=not is_retry)

    async def _dispatch_command(self, message: Message, first_attempt: bool) -> None:
        payload = message.payload
        command_id = payload.get("command_id")
        target = message.target

        if not self.ownership.may_control(target):
            node_log(
                self.gateway_id,
                f"role={self.ownership.role}, not owner of {target} - command {command_id} dropped",
            )
            return

        writer = self.connections.get(target)
        if writer is None:
            node_log(
                self.gateway_id,
                f"{target} not connected, {payload.get('type')} command {command_id} not delivered",
            )
            return

        if first_attempt:
            self.tracker.track(message)
            self.metrics.inc("commands")
            self.last_command = message

        # fault injection: silently lose the frame so the retry path is visible
        if self.drop_command_rate > 0.0 and random.random() < self.drop_command_rate:
            node_log(self.gateway_id, f"simulated command loss (command_id={command_id})")
            return

        try:
            await send_message(writer, message)
        except (ConnectionResetError, BrokenPipeError, RuntimeError):
            self.connections.pop(target, None)
            node_log(self.gateway_id, f"failed to send command to {target}")
            return

        node_log(
            self.gateway_id,
            f"command sent to {target} ({payload.get('type')} {payload.get('duration')}s, "
            f"command_id={command_id}, generation={payload.get('gateway_generation')})",
        )
        # Keep the cloud server aware of the command we issued (same message_id
        # so a retried upload is deduplicated instead of stored twice).
        await self.upload_queue.put(
            Message(
                type=CONTROL_COMMAND,
                source=self.gateway_id,
                target="SERVER",
                message_id=message.message_id,
                payload={**payload, "controller_id": target},
            )
        )

        if first_attempt and self.duplicate_command:
            node_log(self.gateway_id, f"duplicate command injected (command_id={command_id})")
            try:
                await send_message(writer, message)
            except (ConnectionResetError, BrokenPipeError, RuntimeError):
                pass

    # -- Task 5: process control results -----------------------------------

    async def task_control_result(self) -> None:
        while True:
            message = await self.result_queue.get()
            payload = dict(message.payload)
            node_log(
                self.gateway_id,
                f"controller result received ({payload.get('command_type')} -> {payload.get('status')}"
                + (f", reason={payload.get('reason')}" if payload.get("reason") else "")
                + ")",
            )
            payload["controller_id"] = message.source
            await self.upload_queue.put(
                Message(
                    type=CONTROL_RESULT,
                    source=self.gateway_id,
                    target="SERVER",
                    message_id=message.message_id,
                    payload=payload,
                )
            )

    # -- Task 6: peer heartbeat, watchdog, failover ------------------------

    async def task_heartbeat(self) -> None:
        while not self._stopping:
            if self.peer_writer is None:
                await self._connect_peer()

            status = self.evaluate_peer_status()
            payload = {
                "gateway_id": self.gateway_id,
                "status": config.ONLINE,
                "peer_id": self.peer_id,
                "peer_status": status,
                "generation": self.ownership.generation,
                "role": self.ownership.role,
            }

            if self.peer_writer is not None:
                message = Message(
                    type=HEARTBEAT,
                    source=self.gateway_id,
                    target=self.peer_id,
                    payload=payload,
                )
                try:
                    await send_message(self.peer_writer, message)
                    node_log(self.gateway_id, f"heartbeat -> {self.peer_id}")
                except (ConnectionResetError, BrokenPipeError, RuntimeError):
                    node_log(self.gateway_id, f"heartbeat to {self.peer_id} failed, reconnecting")
                    self.peer_writer = None

            # ... and let the cloud server keep a record of our liveness too.
            await self.upload_queue.put(
                Message(type=HEARTBEAT, source=self.gateway_id, target="SERVER", payload=dict(payload))
            )

            # watchdog: nodes that stopped talking are marked OFFLINE
            for entry in self.registry.expire():
                node_log(self.gateway_id, f"WATCHDOG {entry.node_id} -> {config.OFFLINE}")

            await asyncio.sleep(self.heartbeat_interval)

    async def _connect_peer(self) -> None:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(self.peer_host, self.peer_port), timeout=2.0
            )
        except (OSError, asyncio.TimeoutError):
            return
        self.peer_writer = writer
        node_log(self.gateway_id, f"peer link established with {self.peer_id}")

    def evaluate_peer_status(self, now: float | None = None) -> str:
        """Return the peer state; trigger the failover on the OFFLINE edge."""
        now = time.time() if now is None else now
        if self.peer_last_seen is None:
            status = config.UNKNOWN
        elif now - self.peer_last_seen > self.heartbeat_timeout:
            status = config.OFFLINE
        else:
            status = config.ONLINE

        if status != self.peer_status:
            if status == config.OFFLINE:
                node_log(self.gateway_id, f"FAILOVER {self.peer_id} -> {config.OFFLINE}")
                self._takeover()
            elif status == config.ONLINE:
                node_log(self.gateway_id, f"{self.peer_id} is online")
            self.peer_status = status
        return status

    def _takeover(self) -> int:
        """Take the peer's nodes and bump the ownership generation.

        The epoch is bumped even when the registry holds nothing that still
        belongs to the peer: the peer has been declared dead, so every command
        it may still emit - or that is still in flight - belongs to an older
        epoch and the controllers have to refuse it.  That is what turns a
        "dead gateway" into a "deposed gateway" for the rest of the system.
        """
        node_ids = [entry.node_id for entry in self.registry.owned_by(self.peer_id)]

        previous = self.ownership.generation
        generation = self.ownership.takeover(node_ids)
        self.metrics.inc("failovers")
        for node_id in node_ids:
            node_log(self.gateway_id, f"taking ownership of {node_id}")
        node_log(self.gateway_id, f"ownership generation = {previous} -> {generation}")

        # Everything we own now lives in the new epoch - including the nodes
        # that had already re-registered with us while the peer was dying.
        mine = sorted(entry.node_id for entry in self.registry.owned_by(self.gateway_id))
        self.registry.transfer(mine, self.gateway_id, generation)
        for node_id, writer in list(self.connections.items()):
            if node_id in mine:
                asyncio.create_task(self._notify_ownership(writer, node_id, generation))
        return generation

    async def _notify_ownership(self, writer, node_id: str, generation: int) -> None:
        try:
            await send_message(
                writer,
                Message(
                    type=NODE_STATUS,
                    source=self.gateway_id,
                    target=node_id,
                    payload={
                        "node_id": node_id,
                        "owner_gateway": self.gateway_id,
                        "generation": generation,
                        "status": config.ONLINE,
                    },
                ),
            )
        except (ConnectionResetError, BrokenPipeError, RuntimeError):
            pass

    # -- Task 7: retry unacknowledged critical messages ---------------------

    async def task_retry(self) -> None:
        while not self._stopping:
            await asyncio.sleep(config.RETRY_SCAN_INTERVAL)
            now = time.time()

            for message in self.tracker.due(now):
                self.tracker.mark_retry(message.message_id, now)
                entry = self.tracker.pending.get(message.message_id)
                attempt = entry.retries if entry else 0
                self.metrics.inc("retries")
                node_log(
                    self.gateway_id,
                    f"ACK timeout for command_id={message.payload.get('command_id')}, "
                    f"retry {attempt}/{config.MAX_RETRIES}",
                )
                await self.command_queue.put((message, True))

            for message in self.tracker.exhausted(now):
                self.tracker.discard(message.message_id)
                self.metrics.inc("delivery_failures")
                node_log(
                    self.gateway_id,
                    f"{COMMAND_DELIVERY_FAILED} command_id={message.payload.get('command_id')} "
                    f"after {config.MAX_RETRIES} retries",
                )
                await self.upload_queue.put(
                    Message(
                        type=ALERT,
                        source=self.gateway_id,
                        target="SERVER",
                        payload={
                            "alert_type": COMMAND_DELIVERY_FAILED,
                            "controller_id": message.target,
                            "command_id": message.payload.get("command_id"),
                            "message": f"command {message.payload.get('command_id')} not acknowledged",
                        },
                    )
                )


# --------------------------------------------------------------------------
# standalone entry point
# --------------------------------------------------------------------------


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart Agriculture Edge AI - edge gateway")
    parser.add_argument("--id", required=True, choices=sorted(config.GATEWAY_PORTS), help="gateway id, e.g. A1")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--server-host", default=config.SERVER_HOST)
    parser.add_argument("--server-port", type=int, default=config.SERVER_PORT)
    parser.add_argument("--peer-host", default="127.0.0.1")
    parser.add_argument("--peer-port", type=int, default=None)
    parser.add_argument("--queue-db", default=None, help="store-and-forward sqlite file")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    gateway = Gateway(
        gateway_id=args.id,
        host=args.host,
        port=args.port,
        server_host=args.server_host,
        server_port=args.server_port,
        peer_host=args.peer_host,
        peer_port=args.peer_port,
        queue_path=args.queue_db or config.gateway_queue_path(args.id),
    )
    await gateway.start()
    try:
        await asyncio.Event().wait()
    finally:
        await gateway.stop()


def main(argv=None) -> None:
    args = parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        node_log(args.id, "shutdown")


if __name__ == "__main__":
    main()
