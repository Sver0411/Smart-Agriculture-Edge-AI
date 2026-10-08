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
import sqlite3
import hashlib
import json

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
    MessageError,
    close_writer,
    read_message,
    send_message,
)
from common.reliability import Counters  # noqa: E402
from controller_node.safety_guard import DUPLICATE_COMMAND_ID, SafetyGuard  # noqa: E402
from controller_node.recent_commands import RecentCommandStore, CONTRACT, ResultBackpressure
from common.state_store import StateError
from common.settings import SETTINGS

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
        state_path: str | None = None,
        profile: str = "simulation",
        emit_execution_events: bool = False,
    ):
        from common.deployment_security import require_lab_profile
        require_lab_profile(profile)
        if node_id not in config.GATEWAY_OF_CONTROLLER:
            raise ValueError(f"unknown controller node id: {node_id!r}")

        self.node_id = node_id
        self.gateway_host = gateway_host
        self.primary_gateway = config.GATEWAY_OF_CONTROLLER[node_id]
        self.gateway_id = self.primary_gateway
        # A fixed port pins the node to its current gateway (used by tests);
        # otherwise it walks the candidate list, current owner first.
        self.preferred_gateway = None
        self.fixed_port = gateway_port
        from common.state_store import StateStore
        self.guard = safety_guard or SafetyGuard(store=StateStore(state_path) if state_path else None)
        self.recent_commands = None
        try:
            self.recent_commands = RecentCommandStore(self.guard.store, SETTINGS['controller']['recent_command_capacity'],
                retention_s=self.guard.command_ttl)
            self.guard.executed_command_ids.update(self.recent_commands.entries)
        except (StateError, sqlite3.Error, OSError) as exc:
            self.guard.persistence_fault = True
            node_log(node_id, f'recent command state unavailable; DO NOT EXECUTE: {exc}')
        self.emit_execution_events = emit_execution_events
        self.time_scale = time_scale
        self.metrics = Counters()
        self._command_lock = asyncio.Lock()

        self._stopping = False
        self._recover_interrupted_results()

    # -- candidate gateways ------------------------------------------------

    def _candidates(self) -> list[tuple[str, str, int]]:
        """Gateways to try, in order: current owner first, then the rest."""
        if self.fixed_port is not None:
            return [(self.gateway_id, self.gateway_host, self.fixed_port)]

        order = [self.preferred_gateway or self.guard.owner_gateway or self.primary_gateway]
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
            resend = asyncio.create_task(self._retry_results(writer, gateway_id))
            try:
                while not self._stopping:
                    try:
                        message = await read_message(reader)
                    except MessageError:
                        self.metrics.inc("malformed_messages")
                        continue
                    if message is None:
                        break
                    if message.type == CONTROL_COMMAND:
                        await self.process_command(message, writer)
                    elif message.type == "PERSISTED_ACK":
                        self._accept_result_ack(message, gateway_id)
                    elif message.type == NODE_STATUS:
                        self._adopt_ownership(message)
                    else:
                        node_log(self.node_id, f"ignored unexpected {message.type}")
            finally:
                keepalive.cancel()
                resend.cancel()
                await asyncio.gather(keepalive, resend, return_exceptions=True)
        except (ConnectionResetError, BrokenPipeError, OSError, MessageError):
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
                payload={"node_id": self.node_id, "node_type": config.CONTROLLER, "generation": self.guard.current_generation},
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

            owner = reply.payload.get("owner_gateway")
            generation = reply.payload.get("generation")
            if (reply.source != gateway_id or reply.target != self.node_id or
                    not isinstance(owner, str) or owner not in config.GATEWAY_PORTS or type(generation) is not int or generation < 0):
                return False
            if reply.payload.get("accepted") is False:
                if generation >= self.guard.current_generation:
                    self.preferred_gateway = owner
                return False
            if (reply.payload.get("accepted") is not True or owner != gateway_id or
                    generation < self.guard.current_generation or
                    (generation == self.guard.current_generation and self.guard.owner_gateway not in (None, owner))):
                return False
            self.preferred_gateway = owner
            if not self.guard.set_ownership(owner, generation):
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
        if owner != self.gateway_id or message.source != self.gateway_id or message.target != self.node_id or type(generation) is not int or generation < 0:
            return
        if self.guard.set_ownership(owner, int(generation)):
            node_log(self.node_id, f"owner_gateway = {owner} (generation={generation})")

    # -- command handling --------------------------------------------------

    async def process_command(self, message: Message, writer=None) -> dict:
        async with self._command_lock:
            return await self._process_command(message,writer)

    async def _process_command(self, message: Message, writer=None) -> dict:
        """Run one CONTROL_COMMAND through ACK + Safety Guard.

        Returns the ``CONTROL_RESULT`` payload.  ``writer`` may be ``None`` when
        a command is injected directly (fault injection in the demo).
        """
        payload = message.payload
        command_id = payload.get("command_id")
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
            # Remember a higher accepted epoch before any actuator execution.
            if generation is not None and not self.guard.set_ownership(message.source, generation):
                allowed, reason = False, "STATE_UNAVAILABLE"
        if allowed:
            try:
                previous_ids = set(self.recent_commands.entries)
                self.recent_commands.begin(command_id, {"source": message.source,
                    "generation": generation, "command_type": command_type, "node_id": self.node_id,
                    "issued_at":message.timestamp})
                # Trim only IDs durably evicted as completed. Unresolved
                # intents stay in both guards, including across a reboot.
                self.guard.executed_command_ids.difference_update(
                    previous_ids - set(self.recent_commands.entries)
                )
                self.guard.executed_command_ids.add(command_id)
            except ResultBackpressure:
                allowed, reason = False, 'RESULT_BACKPRESSURE'
                self.metrics.inc('result_backpressure')
            except (StateError, sqlite3.Error, OSError) as exc:
                self.guard.persistence_fault = True
                allowed, reason = False, "STATE_UNAVAILABLE"
                self.metrics.inc('command_persistence_failures')
                node_log(self.node_id, f'command intent could not be persisted: {exc}')
        executed_now = allowed
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
            try:
                self.recent_commands.complete(command_id, result, self._result_message(result, message.source))
            except (StateError, sqlite3.Error, OSError) as exc:
                # Durable INTENT still guards against replay after reboot.
                self.guard.persistence_fault = True
                self.metrics.inc('command_persistence_failures')
                result.update(status='UNKNOWN',reason='STATE_UNAVAILABLE')
                node_log(self.node_id, f'command result could not be persisted: {exc}')
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

        outgoing = self._result_message(result, message.source)
        if self.recent_commands and self.recent_commands.store:
            # A repeated delivery of an admitted command reports the durable
            # original outcome, not a second execution or a new result identity.
            row = self.recent_commands.entries.get(command_id)
            if reason == DUPLICATE_COMMAND_ID and row:
                original = row.get('result') or {**result, 'status': 'UNKNOWN',
                    'reason': 'INTERRUPTED_EXECUTION'}
                outgoing = self._result_message(original, message.source)
            try:
                self.recent_commands.queue_result(outgoing)
            except ResultBackpressure:
                self.metrics.inc('result_backpressure')
                return result
            except (StateError, sqlite3.Error, OSError) as exc:
                self.guard.persistence_fault = True
                self.metrics.inc('result_persistence_failures')
                node_log(self.node_id, f'result retained as uncertain intent: {exc}')
                return {**result, 'status': 'UNKNOWN', 'reason': 'STATE_UNAVAILABLE'}
        if writer is not None:
            # Retarget only the transport copy; checkpointed original content
            # and timestamp remain immutable through takeover and restart.
            outgoing = Message.from_dict(outgoing.to_dict())
            outgoing.target = message.source
            if executed_now and self.emit_execution_events:
                # Host experiment observation of the actual execution branch.
                # It is deliberately separate from replayable durable results.
                await send_message(writer, Message(type=NODE_STATUS, source=self.node_id,
                    target=message.source, payload={'node_id':self.node_id, 'status':config.ONLINE,
                        'event':'ACTUATOR_EXECUTED', 'command_id':command_id,
                        'command_type':command_type, 'generation':generation,
                        'owner_gateway':self.guard.owner_gateway}))
            await send_message(writer, outgoing)
            node_log(self.node_id, f"CONTROL_RESULT sent to {message.source}")
        else:
            node_log(self.node_id, f"CONTROL_RESULT {result['status']}")
        return result

    def _result_message(self, result, target):
        reliable = self.recent_commands is not None and self.recent_commands.store is not None
        if not reliable:
            return Message(type=CONTROL_RESULT, source=self.node_id, target=target, payload=dict(result))
        key = json.dumps([self.node_id, result.get('command_id'), result.get('generation'),
                          result.get('status'), result.get('reason')], separators=(',', ':'))
        identity = 'result-' + hashlib.sha256(key.encode()).hexdigest()
        row = self.recent_commands.entries.get(result.get('command_id'))
        cached = row.get('result_message') if row else None
        if cached and cached['payload'] == {**result, 'delivery_contract':CONTRACT}:
            return Message.from_dict(cached)
        existing = self.recent_commands.pending_results.get(identity)
        if existing:
            return Message.from_dict(existing)
        return Message(type=CONTROL_RESULT, source=self.node_id, target=target,
            message_id=identity, payload={**result, 'delivery_contract': CONTRACT})

    def _recover_interrupted_results(self):
        if self.recent_commands is None or self.recent_commands.store is None:
            return
        try:
            for row in self.recent_commands.entries.values():
                ctx = row.get('context')
                if row['state'] == 'INTENT' and ctx and not any(
                        m['payload']['command_id'] == row['command_id']
                        for m in self.recent_commands.pending_results.values()):
                    result = {'command_id': row['command_id'], 'command_type':ctx['command_type'],
                              'generation':ctx['generation'], 'status':'UNKNOWN',
                              'reason':'INTERRUPTED_EXECUTION'}
                    self.recent_commands.queue_result(self._result_message(result, ctx['source']))
        except (StateError, sqlite3.Error, OSError):
            self.guard.persistence_fault = True

    def _accept_result_ack(self, message, gateway_id):
        p = message.payload
        if (self.recent_commands is None or message.type != "PERSISTED_ACK" or message.source != gateway_id or
                message.target != self.node_id or p.get('persisted') is not True or
                p.get('scope') != 'CONTROL_RESULTS' or p.get('delivery_contract') != CONTRACT or
                p.get('result_state') != 'RESULT_DURABLY_STORED'):
            return False
        try:
            return self.recent_commands.acknowledge_result(p.get('ack_message_id'))
        except (StateError, sqlite3.Error, OSError):
            self.metrics.inc('result_ack_persistence_failures')
            return False

    async def _retry_results(self, writer, gateway_id):
        delay = 1.0
        while True:
            if self.recent_commands:
                for raw in list(self.recent_commands.pending_results.values()):
                    message = Message.from_dict(raw)
                    # Historical results may follow a new owner. They remain
                    # audit evidence at the original epoch, never commands.
                    message.target = gateway_id
                    await send_message(writer, message)
                    self.metrics.inc('result_retries')
            await asyncio.sleep(delay)
            delay = min(30.0, delay * 2)

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
    parser.add_argument("--startup-delay", type=float, default=0, help="software experiment process startup delay")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--state-db", default=None, help="host generation checkpoint; default controller_ID.state.db")
    parser.add_argument("--emit-execution-events", action="store_true", help="host experiment execution-branch observations, independent of result replay")
    parser.add_argument("--profile", choices=("simulation", "lab", "deployment"), default="simulation")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    node = ControllerNode(node_id=args.id, gateway_host=args.host, gateway_port=args.port,
                          state_path=args.state_db or f"controller_{args.id}.state.db", profile=args.profile, emit_execution_events=args.emit_execution_events)
    if args.gateway:
        node.primary_gateway = args.gateway
        node.gateway_id = args.gateway

    if args.startup_delay < 0:raise ValueError("startup delay must be nonnegative")
    await asyncio.sleep(args.startup_delay)
    await node.run()


def main(argv=None) -> None:
    args = parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        node_log(args.id, "shutdown")


if __name__ == "__main__":
    main()
