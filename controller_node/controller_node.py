"""Controller node C1 / C2.

The controller owns the actuators (pump, solenoid valve, fan, humidifier) and a
local safety interlock.  It is a *sibling* of the sensor node: both hang off the
same gateway, and the controller only ever reacts to commands coming from the
gateway that currently owns it.

v0.2 flow for every command::

    CONTROL_COMMAND -> ACK -> Safety Guard -> execute (simulated) -> CONTROL_RESULT

``ACK`` only means "I received the command"; ``CONTROL_RESULT`` says what
happened to it.  Keeping the two apart is what lets the gateway retry delivery
without ever risking a second pump run - the Safety Guard is idempotent.
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
    NODE_REGISTER,
    NODE_REGISTER_ACK,
    NODE_STATUS,
    Message,
    close_writer,
    read_message,
    send_message,
)
from common.reliability import Counters  # noqa: E402
from controller_node.safety_guard import DUPLICATE_COMMAND_ID, SafetyGuard  # noqa: E402

EXECUTED = "EXECUTED"
REJECTED = "REJECTED"
DUPLICATE = "DUPLICATE"


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
        self.primary_gateway = config.GATEWAY_OF_CONTROLLER[node_id]
        self.gateway_id = self.primary_gateway
        # A fixed port pins the node to its current gateway (used by tests);
        # otherwise it walks the candidate list, current owner first.
        self.fixed_port = gateway_port
        self.guard = safety_guard or SafetyGuard()
        self.time_scale = time_scale
        self.metrics = Counters()

        self._stopping = False

    # -- candidate gateways ------------------------------------------------

    def _candidates(self) -> list[tuple[str, str, int]]:
        """Gateways to try, in order: current owner first, then the rest."""
        if self.fixed_port is not None:
            return [(self.gateway_id, self.gateway_host, self.fixed_port)]

        order = [self.guard.owner_gateway or self.primary_gateway]
        order += [name for name in sorted(config.GATEWAY_PORTS) if name not in order]
        return [(name, self.gateway_host, config.GATEWAY_PORTS[name]) for name in order]

    # -- main loop ---------------------------------------------------------

    async def run(self) -> None:
        while not self._stopping:
            connected = False
            for gateway_id, host, port in self._candidates():
                if self._stopping:
                    return
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port), timeout=1.5
                    )
                except (OSError, asyncio.TimeoutError):
                    continue
                connected = True
                await self._session(reader, writer, gateway_id)
                if self._stopping:
                    return
            await asyncio.sleep(1.0 if not connected else 0.2)

    async def _session(self, reader, writer, gateway_id: str) -> None:
        self.gateway_id = gateway_id
        node_log(self.node_id, f"connected to gateway {gateway_id} ({self.gateway_host})")
        try:
            if not await self._register(reader, writer, gateway_id):
                return

            keepalive = asyncio.create_task(self._keepalive(writer, gateway_id))
            try:
                while not self._stopping:
                    message = await read_message(reader)
                    if message is None:
                        break
                    if message.type == CONTROL_COMMAND:
                        await self.process_command(message, writer)
                    elif message.type == NODE_STATUS:
                        self._adopt_ownership(message)
                    else:
                        node_log(self.node_id, f"ignored unexpected {message.type}")
            finally:
                keepalive.cancel()
                await asyncio.gather(keepalive, return_exceptions=True)
        except (ConnectionResetError, BrokenPipeError, OSError):
            node_log(self.node_id, f"connection to {gateway_id} lost, re-registering elsewhere")
        finally:
            await close_writer(writer)

    async def _register(self, reader, writer, gateway_id: str) -> bool:
        """Send NODE_REGISTER until the gateway acknowledges it."""
        for attempt in range(1, config.MAX_RETRIES + 2):
            message = Message(
                type=NODE_REGISTER,
                source=self.node_id,
                target=gateway_id,
                payload={"node_id": self.node_id, "node_type": config.CONTROLLER},
            )
            await send_message(writer, message)
            node_log(self.node_id, f"NODE_REGISTER sent to {gateway_id} (attempt {attempt})")

            try:
                reply = await asyncio.wait_for(read_message(reader), timeout=config.ACK_TIMEOUT)
            except asyncio.TimeoutError:
                node_log(self.node_id, "NODE_REGISTER_ACK timeout")
                continue
            if reply is None:
                return False
            if reply.type != NODE_REGISTER_ACK:
                continue

            owner = reply.payload.get("owner_gateway", gateway_id)
            generation = int(reply.payload.get("generation", config.INITIAL_GENERATION))
            if not self.guard.set_ownership(owner, generation):
                node_log(
                    self.node_id,
                    f"refusing {gateway_id}: generation {generation} < {self.guard.current_generation}",
                )
                return False

            node_log(
                self.node_id,
                f"registered with {owner} (generation={generation})",
            )
            return True
        return False

    async def _keepalive(self, writer, gateway_id: str) -> None:
        while True:
            await asyncio.sleep(config.NODE_STATUS_INTERVAL)
            try:
                await send_message(
                    writer,
                    Message(
                        type=NODE_STATUS,
                        source=self.node_id,
                        target=gateway_id,
                        payload={
                            "node_id": self.node_id,
                            "status": config.ONLINE,
                            "owner_gateway": self.guard.owner_gateway,
                            "generation": self.guard.current_generation,
                        },
                    ),
                )
            except (ConnectionResetError, BrokenPipeError, RuntimeError):
                return

    def _adopt_ownership(self, message: Message) -> None:
        """Accept an ownership change pushed by the gateway."""
        owner = message.payload.get("owner_gateway")
        generation = message.payload.get("generation")
        if not owner or generation is None:
            return
        if self.guard.set_ownership(owner, int(generation)):
            node_log(self.node_id, f"owner_gateway = {owner} (generation={generation})")

    # -- command handling --------------------------------------------------

    async def process_command(self, message: Message, writer=None) -> dict:
        """Run one CONTROL_COMMAND through ACK + Safety Guard.

        Returns the ``CONTROL_RESULT`` payload.  ``writer`` may be ``None`` when
        a command is injected directly (fault injection in the demo).
        """
        payload = message.payload
        command_id = payload.get("command_id") or message.message_id
        command_type = payload.get("type")
        duration = payload.get("duration")
        generation = payload.get("gateway_generation")

        node_log(
            self.node_id,
            f"{command_type} command received (command_id={command_id}, "
            f"duration={duration}s, generation={generation})",
        )

        # 1. ACK immediately - delivery is confirmed, execution is not.
        if writer is not None:
            await send_message(writer, message.ack(self.node_id))
            node_log(self.node_id, f"ACK sent (command_id={command_id})")

        # 2. Safety Guard decides whether the actuator may move at all.
        allowed, reason = self.guard.check(
            command_id=command_id,
            command_type=command_type,
            duration=duration,
            issued_at=message.timestamp,
            gateway_generation=generation,
            source_gateway=message.source,
        )

        if allowed:
            node_log(self.node_id, "safety check passed")
            await asyncio.sleep(max(0.05, float(duration) * self.time_scale))
            self.guard.commit(
                command_id,
                command_type,
                gateway_generation=generation,
                source_gateway=message.source,
            )
            self.metrics.inc("executed")
            node_log(self.node_id, f"{str(command_type).lower()} executed")
            result = {
                "command_id": command_id,
                "command_type": command_type,
                "duration": duration,
                "generation": generation,
                "status": EXECUTED,
            }
        elif reason == DUPLICATE_COMMAND_ID:
            # Idempotency: a retried command must never run the actuator twice.
            self.metrics.inc("duplicates")
            node_log(
                self.node_id,
                f"{command_type} command is a duplicate (command_id={command_id}) - not executed again",
            )
            result = {
                "command_id": command_id,
                "command_type": command_type,
                "generation": generation,
                "status": DUPLICATE,
                "reason": reason,
            }
        else:
            self.metrics.inc("rejected")
            node_log(self.node_id, f"{command_type} command rejected: {reason}")
            result = {
                "command_id": command_id,
                "command_type": command_type,
                "generation": generation,
                "status": REJECTED,
                "reason": reason,
            }

        if writer is not None:
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
        else:
            extra = f" ({result['reason']})" if result.get("reason") else ""
            node_log(self.node_id, f"CONTROL_RESULT {result['status']}{extra}")
        return result

    def stop(self) -> None:
        self._stopping = True


# --------------------------------------------------------------------------
# standalone entry point
# --------------------------------------------------------------------------


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart Agriculture Edge AI - controller node")
    parser.add_argument("--id", required=True, choices=sorted(config.GATEWAY_OF_CONTROLLER))
    parser.add_argument("--gateway", default=None, choices=sorted(config.GATEWAY_PORTS), help="primary gateway id")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    node = ControllerNode(node_id=args.id, gateway_host=args.host, gateway_port=args.port)
    if args.gateway:
        node.primary_gateway = args.gateway
        node.gateway_id = args.gateway
        if args.port is None:
            node.fixed_port = config.GATEWAY_PORTS[args.gateway]
    await node.run()


def main(argv=None) -> None:
    args = parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        node_log(args.id, "shutdown")


if __name__ == "__main__":
    main()
