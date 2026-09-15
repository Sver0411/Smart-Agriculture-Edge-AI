"""Controller node C1 / C2.

The controller owns the actuators (pump, solenoid valve, fan, humidifier) and a
local safety interlock.  It is a *sibling* of the sensor node: both hang off the
same gateway, and the controller only ever reacts to commands coming from that
gateway.

Flow for every command::

    CONTROL_COMMAND -> Safety Guard -> execute (simulated) -> CONTROL_RESULT

A command that fails the safety check is never executed; the rejection reason
travels back to the gateway with status ``REJECTED``.
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
    CONTROL_COMMAND,
    CONTROL_RESULT,
    HEARTBEAT,
    Message,
    close_writer,
    read_message,
    send_message,
)
from controller_node.safety_guard import SafetyGuard  # noqa: E402

EXECUTED = "EXECUTED"
REJECTED = "REJECTED"


class ControllerNode:
    """C1 / C2."""

    def __init__(
        self,
        node_id: str,
        gateway_host: str = "127.0.0.1",
        gateway_port: int | None = None,
        safety_guard: SafetyGuard | None = None,
        time_scale: float = config.SIMULATION_TIME_SCALE,
    ):
        if node_id not in config.GATEWAY_OF_CONTROLLER:
            raise ValueError(f"unknown controller node id: {node_id!r}")

        self.node_id = node_id
        self.gateway_host = gateway_host
        self.gateway_port = (
            gateway_port
            if gateway_port is not None
            else config.GATEWAY_PORTS[config.GATEWAY_OF_CONTROLLER[node_id]]
        )
        self.gateway_id = config.GATEWAY_OF_CONTROLLER[node_id]
        self.guard = safety_guard or SafetyGuard()
        self.time_scale = time_scale

        self.executed = 0
        self.rejected = 0
        self._stopping = False

    # -- main loop ---------------------------------------------------------

    async def run(self) -> None:
        while not self._stopping:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.gateway_host, self.gateway_port), timeout=3.0
                )
            except (OSError, asyncio.TimeoutError):
                node_log(self.node_id, f"gateway {self.gateway_id} not reachable, retrying in 1s")
                await asyncio.sleep(1.0)
                continue

            node_log(self.node_id, f"connected to gateway {self.gateway_id} ({self.gateway_host}:{self.gateway_port})")
            try:
                # Registration: a plain HEARTBEAT tells the gateway which
                # connection belongs to this controller.
                await send_message(
                    writer,
                    Message(
                        type=HEARTBEAT,
                        source=self.node_id,
                        target=self.gateway_id,
                        payload={
                            "gateway_id": self.node_id,
                            "role": "controller",
                            "status": "ONLINE",
                        },
                    ),
                )

                while True:
                    message = await read_message(reader)
                    if message is None:
                        break
                    if message.type == CONTROL_COMMAND:
                        await self._handle_command(writer, message)
                    else:
                        node_log(self.node_id, f"ignored unexpected {message.type}")
            except (ConnectionResetError, BrokenPipeError, OSError):
                node_log(self.node_id, f"connection to {self.gateway_id} lost, reconnecting")
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:  # pragma: no cover - best effort cleanup
                    pass

    # -- command handling --------------------------------------------------

    async def _handle_command(self, writer, message: Message) -> None:
        payload = message.payload
        command_id = payload.get("command_id") or message.message_id
        command_type = payload.get("type")
        duration = payload.get("duration")

        node_log(
            self.node_id,
            f"{command_type} command received (command_id={command_id}, duration={duration}s)",
        )

        allowed, reason = self.guard.check(
            command_id=command_id,
            command_type=command_type,
            duration=duration,
            issued_at=message.timestamp,
        )

        if allowed:
            node_log(self.node_id, "safety check passed")
            await asyncio.sleep(max(0.05, float(duration) * self.time_scale))
            self.guard.commit(command_id, command_type)
            self.executed += 1
            node_log(self.node_id, f"{str(command_type).lower()} executed")
            result = {
                "command_id": command_id,
                "command_type": command_type,
                "duration": duration,
                "status": EXECUTED,
            }
        else:
            self.rejected += 1
            node_log(self.node_id, f"{command_type} command rejected: {reason}")
            result = {
                "command_id": command_id,
                "command_type": command_type,
                "status": REJECTED,
                "reason": reason,
            }

        await send_message(
            writer,
            Message(
                type=CONTROL_RESULT,
                source=self.node_id,
                target=message.source,
                payload=result,
            ),
        )
        node_log(self.node_id, f"CONTROL_RESULT sent to {message.source}")

    def stop(self) -> None:
        self._stopping = True


# --------------------------------------------------------------------------
# standalone entry point
# --------------------------------------------------------------------------


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart Agriculture Edge AI - controller node")
    parser.add_argument("--id", required=True, choices=sorted(config.GATEWAY_OF_CONTROLLER))
    parser.add_argument("--gateway", default=None, choices=sorted(config.GATEWAY_PORTS), help="gateway id")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    gateway_id = args.gateway or config.GATEWAY_OF_CONTROLLER[args.id]
    port = args.port if args.port is not None else config.GATEWAY_PORTS[gateway_id]
    node = ControllerNode(node_id=args.id, gateway_host=args.host, gateway_port=port)
    node.gateway_id = gateway_id
    await node.run()


def main(argv=None) -> None:
    args = parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        node_log(args.id, "shutdown")


if __name__ == "__main__":
    main()
