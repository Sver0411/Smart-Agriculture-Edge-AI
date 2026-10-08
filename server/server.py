"""Cloud server for Smart Agriculture Edge AI v0.2.

The server is deliberately small, and deliberately *not* on the control path.
It accepts one TCP connection per gateway and then only does five things:

* store everything the gateways upload (sensor history, heartbeats, control
  commands / results, alerts) while ignoring duplicates,
* push a versioned ``SERVER_POLICY`` down to every connected gateway,
* print what it stored,
* keep the SQLite file up to date,
* collect a few counters for the demo summary.

It never talks to a sensor or a controller directly, and the farm keeps working
while it is down - the gateways simply queue what they cannot upload.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
import sqlite3
from copy import copy

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import config  # noqa: E402
from common.log import node_log  # noqa: E402
from common.messages import (  # noqa: E402
    ACK,
    PERSISTED_ACK,
    ALERT,
    CONTROL_COMMAND,
    CONTROL_RESULT,
    HEARTBEAT,
    SENSOR_DATA,
    SERVER_POLICY,
    Message,
    MessageError,
    read_message,
    send_message,
)
from common.reliability import Counters  # noqa: E402
from server.database import Database  # noqa: E402
from server.validation import validate_server_upload
from server.dedup import Deduplicator  # noqa: E402

NODE_ID = "SERVER"


class Server:
    """The cloud side of the system."""

    def __init__(
        self,
        host: str = config.SERVER_HOST,
        port: int = config.SERVER_PORT,
        db_path: str = config.DEFAULT_DB_PATH,
        policy_interval: float = config.SERVER_POLICY_INTERVAL,
        policy_version: int = config.INITIAL_POLICY_VERSION,
        profile: str = "simulation",
    ):
        from common.deployment_security import require_lab_profile
        require_lab_profile(profile)
        self.host = host
        self.port = port
        self.db = Database(db_path)
        self.policy_interval = policy_interval
        self.policy_version = policy_version
        self.policy = dict(config.DEFAULT_POLICY)
        self.policy_available = False
        self.policy_error = None
        self.clients: dict[str, asyncio.StreamWriter] = {}
        self.metrics = Counters()
        self.dedup: Deduplicator | None = None

        self._server: asyncio.AbstractServer | None = None
        self._tasks: list[asyncio.Task] = []
        self._stopping = False

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        try:
            self.policy_version, self.policy = self.db.load_policy(self.policy_version, self.policy)
            self.policy_available = True
        except (ValueError, sqlite3.Error) as exc:
            self.policy_error = str(exc)
            node_log(NODE_ID, f'policy publication disabled: {exc}')
        self.db.init_schema()
        self.dedup = Deduplicator(self.db.conn,auto_commit=False)
        self._server = await asyncio.start_server(self._handle_gateway, self.host, self.port)
        self._tasks.append(asyncio.create_task(self._policy_loop(), name="server-policy"))
        node_log(NODE_ID, f"listening on {self.host}:{self.port} (sqlite: {self.db.path})")

    async def serve_forever(self) -> None:
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        self._stopping = True
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Close the gateway sockets first: since Python 3.12
        # ``Server.wait_closed()`` also waits for the connection handlers, and
        # those handlers only end once their socket is gone.
        if self._server is not None:
            self._server.close()
        for writer in list(self.clients.values()):
            writer.close()
        self.clients.clear()
        if self._server is not None:
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=2.0)
            except asyncio.TimeoutError:  # pragma: no cover - defensive
                pass
        self.db.close()

    # -- connections -------------------------------------------------------

    async def _handle_gateway(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        gateway_id: str | None = None
        try:
            while True:
                try:
                    message = await read_message(reader)
                except MessageError as exc:
                    node_log(NODE_ID, f"dropped malformed message: {exc}")
                    continue
                if message is None:
                    break

                if gateway_id is None:
                    gateway_id = message.source
                    self.clients[gateway_id] = writer
                    node_log(NODE_ID, f"gateway {gateway_id} connected")

                if message.source != gateway_id:
                    self.metrics.inc("invalid_uploads")
                    continue
                if self._store(message) and message.type in (SENSOR_DATA, CONTROL_COMMAND, CONTROL_RESULT, ALERT):
                    await send_message(writer, Message(type=PERSISTED_ACK, source=NODE_ID,
                        target=gateway_id, payload={"ack_message_id": message.message_id,
                                                   "persisted": True}))
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            if gateway_id is not None and self.clients.get(gateway_id) is writer:
                del self.clients[gateway_id]
                node_log(NODE_ID, f"gateway {gateway_id} disconnected")
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

    # -- storage -----------------------------------------------------------

    def _store(self, message: Message) -> bool:
        before = (self.dedup.processed, self.dedup.ignored)
        metrics_before = copy(self.metrics._values)
        try:
            validate_server_upload(message)
            if message.type == ACK:
                self.metrics.inc("acks_received")
                return False  # policy receipt is not a durable business upload
            with self.db.transaction():
                self._store_validated(message)
            return True  # transaction exit committed, including duplicate receipts
        except (ValueError, TypeError, OverflowError, sqlite3.Error) as exc:
            self.dedup.processed, self.dedup.ignored = before
            self.metrics._values = metrics_before
            self.metrics.inc("invalid_uploads")
            node_log(NODE_ID, f"upload rejected: {exc}")
            return False

    def _store_validated(self, message: Message) -> None:
        # Gateways upload "at least once".  Replays and retries carry the same
        # message_id, so anything we have already processed is dropped here.
        if not self.dedup.is_new(message.message_id):
            node_log(NODE_ID, f"duplicate {message.type} ignored (message_id={message.message_id})")
            return

        gateway_id = message.source
        payload = message.payload
        message_id = message.message_id

        if message.type == SENSOR_DATA:
            record = dict(payload["record"])
            record.setdefault("timestamp", message.timestamp)
            self.db.insert_sensor_data(
                gateway_id=gateway_id,
                sensor_node_id=record["sensor_node_id"],
                record=record,
                health_state=record.get("health_state", "HEALTHY"),
                message_id=message_id,
            )
            self.metrics.inc("sensor_messages")
            node_log(
                NODE_ID,
                "sensor data stored "
                f"({record.get('sensor_node_id')} "
                f"soil={record.get('soil_moisture')}% "
                f"temp={record.get('temperature')}C)",
            )

        elif message.type == CONTROL_COMMAND:
            self.db.insert_controller_command(
                gateway_id=gateway_id,
                controller_id=payload["controller_id"],
                command_id=payload["command_id"],
                command_type=payload["type"],
                duration=payload.get("duration"),
                timestamp=message.timestamp,
                generation=payload.get("gateway_generation"),
                message_id=message_id,
            )
            self.metrics.inc("control_commands")

        elif message.type == CONTROL_RESULT:
            self.db.insert_controller_result(
                gateway_id=gateway_id,
                command_id=payload["command_id"],
                status=payload["status"],
                timestamp=message.timestamp,
                controller_id=payload.get("controller_id"),
                command_type=payload.get("command_type"),
                reason=payload.get("reason"),
                generation=payload.get("generation"),
                message_id=message_id,
            )
            self.metrics.inc("control_results")
            node_log(
                NODE_ID,
                f"control result stored ({payload.get('command_type')} -> {payload.get('status')}"
                + (f", reason={payload.get('reason')}" if payload.get("reason") else "")
                + ")",
            )

        elif message.type == HEARTBEAT:
            self.db.insert_gateway_heartbeat(
                gateway_id=payload["gateway_id"],
                timestamp=message.timestamp,
                status=payload["status"],
                peer_id=payload.get("peer_id"),
                peer_status=payload.get("peer_status"),
                message_id=message_id,
                metadata=payload,
            )
            self.metrics.inc("heartbeats")

        elif message.type == ALERT:
            self.db.insert_alert(
                gateway_id=gateway_id,
                timestamp=message.timestamp,
                alert_type=payload["alert_type"],
                message=payload["message"],
                sensor_node_id=payload.get("sensor_node_id"),
                message_id=message_id,
                metadata=payload,
            )
            self.metrics.inc("alerts")
            node_log(
                NODE_ID,
                f"alert stored ({payload.get('alert_type')}: {payload.get('message')})",
            )

        elif message.type == ACK:
            self.metrics.inc("acks_received")

        elif message.type == SERVER_POLICY:  # pragma: no cover - gateways never send this
            node_log(NODE_ID, "ignoring SERVER_POLICY sent by a gateway")

        else:  # pragma: no cover - protocol layer already rejects unknown types
            node_log(NODE_ID, f"unhandled message type {message.type}")

    # -- policy push -------------------------------------------------------

    async def _policy_loop(self) -> None:
        delay = config.SERVER_POLICY_FIRST_DELAY
        while not self._stopping:
            await asyncio.sleep(delay)
            delay = self.policy_interval
            await self._broadcast_policy()

    async def _broadcast_policy(self) -> None:
        if not self.clients or not self.policy_available:
            return
        policy = Message(
            type=SERVER_POLICY,
            source=NODE_ID,
            target="*",
            payload={"policy_version": self.policy_version, **self.policy},
        )
        for gateway_id, writer in list(self.clients.items()):
            try:
                await send_message(writer, policy)
            except (ConnectionResetError, BrokenPipeError, RuntimeError):
                self.clients.pop(gateway_id, None)
        node_log(NODE_ID, f"SERVER_POLICY v{policy.payload['policy_version']} pushed to "
                          f"{', '.join(sorted(self.clients)) or 'no gateway'}")

    def update_policy(self, changes):
        """Commit a real configuration change before publishing its new version."""
        from common.protocol import validate_policy
        if not self.policy_available:raise ValueError(self.policy_error or 'policy state unavailable')
        if 'policy_version' in changes:raise ValueError('version is allocated by the durable policy store')
        candidate = validate_policy(changes, self.policy)
        if candidate == self.policy:return False
        version = self.policy_version + 1
        self.db.update_policy(version, candidate, self.policy_version)
        self.policy_version, self.policy = version, candidate
        return True


# --------------------------------------------------------------------------
# standalone entry point
# --------------------------------------------------------------------------


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart Agriculture Edge AI - cloud server")
    parser.add_argument("--host", default=config.SERVER_HOST)
    parser.add_argument("--port", type=int, default=config.SERVER_PORT)
    parser.add_argument("--db", default=config.DEFAULT_DB_PATH)
    parser.add_argument("--policy-interval", type=float, default=config.SERVER_POLICY_INTERVAL)
    parser.add_argument("--profile", choices=("simulation", "lab", "deployment"), default="simulation")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    server = Server(
        host=args.host,
        port=args.port,
        db_path=args.db,
        policy_interval=args.policy_interval,
        profile=args.profile,
    )
    await server.start()
    try:
        await server.serve_forever()
    finally:
        await server.stop()


def main(argv=None) -> None:
    args = parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        node_log(NODE_ID, "shutdown")


if __name__ == "__main__":
    main()
