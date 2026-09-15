"""Edge gateway A1 / A2 - the core of Smart Agriculture Edge AI v0.1.

A gateway talks to four different peers at the same time (sensor B, controller
C, the cloud server and the other gateway), so the work is split into six
independent :mod:`asyncio` tasks that never block each other::

    Task 1  task_sensor_data    receive SENSOR_DATA from B, run the edge decision
    Task 2  task_upload         upload sensor data / control results to the server
    Task 3  task_server_policy  receive SERVER_POLICY from the server
    Task 4  task_send_commands  send CONTROL_COMMAND to C
    Task 5  task_control_result process the CONTROL_RESULT coming back from C
    Task 6  task_heartbeat      exchange heartbeats with the peer gateway

Topology (B and C are siblings, C is *not* behind B)::

        A1
       /  \\
     B1    C1
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import config  # noqa: E402
from common.log import node_log  # noqa: E402
from common.messages import (  # noqa: E402
    ALERT,
    CONTROL_COMMAND,
    CONTROL_RESULT,
    HEARTBEAT,
    SENSOR_DATA,
    SERVER_POLICY,
    Message,
    MessageError,
    close_writer,
    read_message,
    send_message,
)
from gateway.edge_decision import EdgeDecider  # noqa: E402

ONLINE = "ONLINE"
OFFLINE = "OFFLINE"
UNKNOWN = "UNKNOWN"


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
    ):
        if gateway_id not in config.GATEWAY_PORTS:
            raise ValueError(f"unknown gateway id: {gateway_id!r}")

        self.gateway_id = gateway_id
        self.peer_id = config.PEER_OF[gateway_id]
        self.sensor_id = sensor_id or config.SENSOR_OF[gateway_id]
        self.controller_id = controller_id or config.CONTROLLER_OF[gateway_id]

        self.host = host
        self.port = port if port is not None else config.GATEWAY_PORTS[gateway_id]
        self.server_host = server_host
        self.server_port = server_port
        self.peer_host = peer_host
        self.peer_port = peer_port if peer_port is not None else config.GATEWAY_PORTS[self.peer_id]

        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout

        self.decider = EdgeDecider()

        # Connected B / C nodes, keyed by node id.
        self.connections: dict[str, asyncio.StreamWriter] = {}
        # Every socket handed to us by the TCP server (B, C and the peer).
        self.inbound_writers: set = set()
        self.server_writer: asyncio.StreamWriter | None = None
        self.peer_writer: asyncio.StreamWriter | None = None

        self.peer_last_seen: float | None = None
        self.peer_status = UNKNOWN

        # Internal message queues, one per task that consumes messages.
        self.sensor_queue: asyncio.Queue = asyncio.Queue()
        self.result_queue: asyncio.Queue = asyncio.Queue()
        self.upload_queue: asyncio.Queue = asyncio.Queue()
        self.command_queue: asyncio.Queue = asyncio.Queue()

        self._server: asyncio.AbstractServer | None = None
        self._tasks: list[asyncio.Task] = []
        self._stopping = False

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self._tasks = [
            asyncio.create_task(self.task_sensor_data(), name=f"{self.gateway_id}-1-sensor-data"),
            asyncio.create_task(self.task_upload(), name=f"{self.gateway_id}-2-upload"),
            asyncio.create_task(self.task_server_policy(), name=f"{self.gateway_id}-3-server-policy"),
            asyncio.create_task(self.task_send_commands(), name=f"{self.gateway_id}-4-send-commands"),
            asyncio.create_task(self.task_control_result(), name=f"{self.gateway_id}-5-control-result"),
            asyncio.create_task(self.task_heartbeat(), name=f"{self.gateway_id}-6-heartbeat"),
        ]
        node_log(
            self.gateway_id,
            f"gateway started on {self.host}:{self.port} "
            f"(sensor={self.sensor_id}, controller={self.controller_id}, peer={self.peer_id})",
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

    # -- inbound connections (B, C and the peer gateway) -------------------

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        source: str | None = None
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

                if source in (self.sensor_id, self.controller_id) and self.connections.get(source) is not writer:
                    self.connections[source] = writer
                    node_log(self.gateway_id, f"{source} connected")

                if message.type == HEARTBEAT:
                    if source == self.peer_id:
                        self.peer_last_seen = message.timestamp or time.time()
                    continue

                if message.type in (SENSOR_DATA, ALERT):
                    await self.sensor_queue.put(message)
                elif message.type == CONTROL_RESULT:
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

        decision = self.decider.decide(record)
        if decision is None:
            node_log(self.gateway_id, f"edge decision = NONE (soil={record.get('soil_moisture')}%, temp={record.get('temperature')}C)")
            return

        command = Message(
            type=CONTROL_COMMAND,
            source=self.gateway_id,
            target=self.controller_id,
            payload=dict(decision),
        )
        command.payload["command_id"] = command.message_id
        node_log(self.gateway_id, f"edge decision = {decision['type']} ({decision.get('reason')})")
        await self.command_queue.put(command)

    # -- Task 2: upload to the cloud server --------------------------------

    async def task_upload(self) -> None:
        while True:
            message = await self.upload_queue.get()
            writer = self.server_writer
            if writer is None:
                node_log(self.gateway_id, f"server offline, {message.type} not uploaded (v0.1 drops it)")
                continue
            try:
                await send_message(writer, message)
            except (ConnectionResetError, BrokenPipeError, RuntimeError):
                self.server_writer = None
                node_log(self.gateway_id, f"server link broken while uploading {message.type}")
                continue
            if message.type != HEARTBEAT:  # routine, would flood the console
                node_log(self.gateway_id, f"{message.type} uploaded to server")

    # -- Task 3: receive server policy -------------------------------------

    async def task_server_policy(self) -> None:
        while not self._stopping:
            writer = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.server_host, self.server_port), timeout=3.0
                )
            except (OSError, asyncio.TimeoutError):
                node_log(self.gateway_id, "server not reachable yet, retrying in 2s")
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
                        policy = self.decider.update_policy(message.payload)
                        node_log(
                            self.gateway_id,
                            "SERVER_POLICY received "
                            f"(soil<{policy['soil_moisture_threshold']} -> {policy['irrigation_duration']}s, "
                            f"temp>{policy['temperature_threshold']} -> {policy['ventilation_duration']}s)",
                        )
                    else:
                        node_log(self.gateway_id, f"unexpected {message.type} from server")
            except (OSError, MessageError) as exc:
                node_log(self.gateway_id, f"server link error: {exc}")
            finally:
                self.server_writer = None
                writer.close()

            await asyncio.sleep(2.0)

    # -- Task 4: send control commands to C --------------------------------

    async def task_send_commands(self) -> None:
        while True:
            message = await self.command_queue.get()
            writer = self.connections.get(self.controller_id)
            if writer is None:
                node_log(
                    self.gateway_id,
                    f"{self.controller_id} not connected, {message.payload.get('type')} command dropped",
                )
                continue
            try:
                await send_message(writer, message)
            except (ConnectionResetError, BrokenPipeError, RuntimeError):
                self.connections.pop(self.controller_id, None)
                node_log(self.gateway_id, f"failed to send command to {self.controller_id}")
                continue
            node_log(
                self.gateway_id,
                f"command sent to {self.controller_id} "
                f"({message.payload.get('type')} {message.payload.get('duration')}s, "
                f"command_id={message.payload.get('command_id')})",
            )
            # Keep the cloud server aware of the command we issued.
            await self.upload_queue.put(
                Message(
                    type=CONTROL_COMMAND,
                    source=self.gateway_id,
                    target="SERVER",
                    payload={**message.payload, "controller_id": self.controller_id},
                )
            )

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
                Message(type=CONTROL_RESULT, source=self.gateway_id, target="SERVER", payload=payload)
            )

    # -- Task 6: peer heartbeat --------------------------------------------

    async def task_heartbeat(self) -> None:
        while not self._stopping:
            if self.peer_writer is None:
                await self._connect_peer()

            status = self.evaluate_peer_status()
            payload = {
                "gateway_id": self.gateway_id,
                "status": ONLINE,
                "peer_id": self.peer_id,
                "peer_status": status,
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
        """Return the peer state and log the transition to ``OFFLINE``."""
        now = time.time() if now is None else now
        if self.peer_last_seen is None:
            status = UNKNOWN
        elif now - self.peer_last_seen > self.heartbeat_timeout:
            status = OFFLINE
        else:
            status = ONLINE

        if status != self.peer_status:
            if status == OFFLINE:
                node_log(self.gateway_id, f"{self.peer_id} detected offline")
            elif status == ONLINE:
                node_log(self.gateway_id, f"{self.peer_id} is online")
            self.peer_status = status
        return status


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
