"""Cloud server for Smart Agriculture Edge AI v0.1.

The server is deliberately small.  It accepts one TCP connection per gateway
and then only does four things:

* store everything the gateways upload (sensor history, heartbeats,
  control commands / results, alerts),
* push a simple ``SERVER_POLICY`` down to every connected gateway,
* print what it stored,
* keep the SQLite file up to date.

It never talks to a sensor or a controller directly.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

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
    read_message,
    send_message,
)
from server.database import Database  # noqa: E402

NODE_ID = "SERVER"


class Server:
    """The cloud side of the system."""

    def __init__(
        self,
        host: str = config.SERVER_HOST,
        port: int = config.SERVER_PORT,
        db_path: str = config.DEFAULT_DB_PATH,
        policy_interval: float = config.SERVER_POLICY_INTERVAL,
    ):
        self.host = host
        self.port = port
        self.db = Database(db_path)
        self.policy_interval = policy_interval
        self.clients: dict[str, asyncio.StreamWriter] = {}

        self._server: asyncio.AbstractServer | None = None
        self._tasks: list[asyncio.Task] = []
        self._stopping = False

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        self.db.init_schema()
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

                self._store(message)
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

    def _store(self, message: Message) -> None:
        gateway_id = message.source
        payload = message.payload

        if message.type == SENSOR_DATA:
            record = payload.get("record", {})
            self.db.insert_sensor_data(
                gateway_id=gateway_id,
                sensor_node_id=record.get("sensor_node_id", "?"),
                record=record,
                health_state=record.get("health_state", "HEALTHY"),
            )
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
                controller_id=payload.get("controller_id", message.target),
                command_id=payload.get("command_id", message.message_id),
                command_type=payload.get("type", "UNKNOWN"),
                duration=payload.get("duration"),
                timestamp=message.timestamp,
            )

        elif message.type == CONTROL_RESULT:
            self.db.insert_controller_result(
                gateway_id=gateway_id,
                command_id=payload.get("command_id", "?"),
                status=payload.get("status", "UNKNOWN"),
                timestamp=message.timestamp,
                controller_id=payload.get("controller_id"),
                command_type=payload.get("command_type"),
                reason=payload.get("reason"),
            )
            node_log(
                NODE_ID,
                f"control result stored ({payload.get('command_type')} -> {payload.get('status')}"
                + (f", reason={payload.get('reason')}" if payload.get("reason") else "")
                + ")",
            )

        elif message.type == HEARTBEAT:
            self.db.insert_gateway_heartbeat(
                gateway_id=payload.get("gateway_id", gateway_id),
                timestamp=message.timestamp,
                status=payload.get("status", "ONLINE"),
                peer_id=payload.get("peer_id"),
                peer_status=payload.get("peer_status"),
            )

        elif message.type == ALERT:
            self.db.insert_alert(
                gateway_id=gateway_id,
                timestamp=message.timestamp,
                alert_type=payload.get("alert_type", "UNKNOWN"),
                message=payload.get("message", ""),
                sensor_node_id=payload.get("sensor_node_id"),
            )
            node_log(
                NODE_ID,
                f"alert stored ({payload.get('sensor_node_id')}: {payload.get('message')})",
            )

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
        if not self.clients:
            return
        policy = Message(type=SERVER_POLICY, source=NODE_ID, target="*", payload=dict(config.SERVER_POLICY))
        for gateway_id, writer in list(self.clients.items()):
            try:
                await send_message(writer, policy)
            except (ConnectionResetError, BrokenPipeError, RuntimeError):
                self.clients.pop(gateway_id, None)
        node_log(NODE_ID, f"SERVER_POLICY pushed to {', '.join(sorted(self.clients)) or 'no gateway'}")


# --------------------------------------------------------------------------
# standalone entry point
# --------------------------------------------------------------------------


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart Agriculture Edge AI - cloud server")
    parser.add_argument("--host", default=config.SERVER_HOST)
    parser.add_argument("--port", type=int, default=config.SERVER_PORT)
    parser.add_argument("--db", default=config.DEFAULT_DB_PATH)
    parser.add_argument("--policy-interval", type=float, default=config.SERVER_POLICY_INTERVAL)
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    server = Server(
        host=args.host,
        port=args.port,
        db_path=args.db,
        policy_interval=args.policy_interval,
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
