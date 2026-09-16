"""One-command demo of the whole Smart Agriculture Edge AI v0.2 system.

``python demo.py`` starts every node of the architecture inside a single process
(server, gateways A1 / A2, sensor nodes B1 / B2 and controller nodes C1 / C2)
and lets the full loop run::

    B -> A -> C -> A -> Server

The nodes still talk to each other over real TCP sockets, so this is the same
code path as running every node in its own terminal.

On top of the v0.1 loop the demo can inject faults, which is how the reliability
claims are actually verified rather than just asserted.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from common import config  # noqa: E402
from common.log import node_log  # noqa: E402
from common.messages import CONTROL_COMMAND, Message  # noqa: E402
from controller_node.controller_node import ControllerNode  # noqa: E402
from gateway.gateway import Gateway  # noqa: E402
from sensor_node.sensor_node import SensorNode, SensorSimulator  # noqa: E402
from server.database import Database  # noqa: E402
from server.server import Server  # noqa: E402

BANNER = """
================================================================================
 Smart Agriculture Edge AI  -  v0.2 demo (Engineering Hardening)
================================================================================
                              cloud server (:9100)
                                      |
                       +--------------+--------------+
                       |                             |
                  gateway A1 <-- heartbeat --> gateway A2
                 (:9201)                       (:9202)
                       |                             |
                 +-----+-----+                 +-----+-----+
                 |           |                 |           |
               B1 (soil)   C1 (pump)         B2 (soil)   C2 (pump)

 loop :  B -> A -> C -> A -> Server      (B and C are siblings)
================================================================================
"""


class Demo:
    """Owns every node of one demo run and the fault injection schedule."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.db_path = args.db
        self.servers: list[Server] = []
        self.server = Server(db_path=self.db_path, policy_interval=args.policy_interval)
        self.servers.append(self.server)

        self.gateways = {
            gateway_id: Gateway(
                gateway_id,
                queue_path=config.gateway_queue_path(gateway_id),
                drop_command_rate=args.drop_command_rate,
                duplicate_command=args.duplicate_command,
            )
            for gateway_id in ("A1", "A2")
        }

        inject_fault = None if args.scenario == "failover" else 4
        self.sensors = {
            "B1": SensorNode(
                "B1",
                simulator=SensorSimulator(
                    "B1", seed=11, start={"soil_moisture": 21.5}, inject_fault_at=inject_fault
                ),
            ),
            "B2": SensorNode(
                "B2",
                simulator=SensorSimulator(
                    "B2", seed=22, start={"temperature": 33.5, "soil_moisture": 41.0}
                ),
            ),
        }
        self.controllers = {node_id: ControllerNode(node_id) for node_id in ("C1", "C2")}

        self.tasks: dict[str, asyncio.Task] = {}
        self.started = 0.0
        # last command the doomed gateway put on the wire - replayed later to
        # prove that a deposed gateway can no longer move an actuator
        self.stale_command: Message | None = None

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        await self.server.start()
        for gateway in self.gateways.values():
            await gateway.start()
        await asyncio.sleep(0.3)

        for node_id, node in list(self.sensors.items()) + list(self.controllers.items()):
            self.tasks[node_id] = asyncio.create_task(node.run(), name=node_id)

    async def stop(self) -> None:
        node_log("DEMO", "stopping nodes ...")
        for node in list(self.sensors.values()) + list(self.controllers.values()):
            node.stop()
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        await asyncio.sleep(0.2)
        for gateway in self.gateways.values():
            await gateway.stop()
        for server in self.servers:
            await server.stop()

    # -- fault injection ---------------------------------------------------

    def events(self) -> list[tuple[float, object]]:
        """``(time_in_seconds, coroutine_factory)`` pairs."""
        args = self.args
        schedule: list[tuple[float, object]] = []

        if args.server_offline_at is not None:
            schedule.append((args.server_offline_at, self._server_down))
        if args.server_online_at is not None:
            schedule.append((args.server_online_at, self._server_up))
        if args.kill_gateway:
            schedule.append((args.at, self._kill(args.kill_gateway)))
        if args.revive_at is not None:
            schedule.append((args.revive_at, self._revive(args.kill_gateway or "A1")))
        if args.inject_stale_at is not None:
            schedule.append((args.inject_stale_at, self._inject_stale))
        return schedule

    async def run_events(self) -> None:
        for moment, action in sorted(self.events(), key=lambda item: item[0]):
            delay = moment - (time.monotonic() - self.started)
            if delay > 0:
                await asyncio.sleep(delay)
            await action()

    async def _server_down(self) -> None:
        node_log("DEMO", "=== SERVER OFFLINE (gateways must keep working) ===")
        await self.server.stop()

    async def _server_up(self) -> None:
        node_log("DEMO", "=== SERVER BACK ONLINE (expect queue replay) ===")
        self.server = Server(db_path=self.db_path, policy_interval=self.args.policy_interval)
        self.servers.append(self.server)
        await self.server.start()

    def _kill(self, gateway_id: str):
        async def kill() -> None:
            node_log("DEMO", f"=== simulating {gateway_id} crash ===")
            gateway = self.gateways.get(gateway_id)
            if gateway is not None:
                # keep the command it issued last: it is the one that will
                # arrive late in the split-brain check
                if gateway.last_command is not None:
                    self.stale_command = gateway.last_command
                await gateway.stop()

        return kill

    def _revive(self, gateway_id: str):
        async def revive() -> None:
            node_log("DEMO", f"=== {gateway_id} recovering ===")
            gateway = Gateway(
                gateway_id,
                queue_path=config.gateway_queue_path(gateway_id),
                drop_command_rate=self.args.drop_command_rate,
                duplicate_command=self.args.duplicate_command,
            )
            self.gateways[gateway_id] = gateway
            await gateway.start()

        return revive

    async def _inject_stale(self) -> None:
        """A command the deposed gateway issued before it died arrives late."""
        stale = self.stale_command
        if stale is None:
            stale = Message(
                type=CONTROL_COMMAND,
                source="A1",
                target="C1",
                payload={
                    "command_id": "stale-0001",
                    "type": "IRRIGATION",
                    "duration": 10,
                    "gateway_generation": 1,
                },
            )
        # fresh timestamp so only the epoch can be the reason for a rejection
        stale.timestamp = time.time()
        node_log(
            "DEMO",
            "=== split brain check: delayed command from A1 generation="
            f"{stale.payload.get('gateway_generation')} -> {stale.target} ===",
        )
        await self.controllers[stale.target].process_command(stale)

    # -- run ---------------------------------------------------------------

    async def run(self) -> None:
        self.started = time.monotonic()
        node_log("DEMO", f"running for {self.args.duration:g}s ...")
        scheduler = asyncio.create_task(self.run_events())
        try:
            await asyncio.sleep(self.args.duration)
        finally:
            scheduler.cancel()
            await asyncio.gather(scheduler, return_exceptions=True)

    # -- reporting ---------------------------------------------------------

    def metrics(self) -> dict:
        def total(objects, key):
            return sum(obj.metrics.get(key) for obj in objects)

        gateways = list(self.gateways.values())
        controllers = list(self.controllers.values())
        return {
            "sensor messages": total(gateways, "sensor_messages"),
            "control commands": total(gateways, "commands"),
            "executed": total(controllers, "executed"),
            "rejected": total(controllers, "rejected"),
            "duplicates": total(controllers, "duplicates"),
            "retries": total(gateways, "retries"),
            "delivery failures": total(gateways, "delivery_failures"),
            "failovers": total(gateways, "failovers"),
            "offline queued": total(gateways, "queue_enqueued"),
            "queue replayed": total(gateways, "queue_replayed"),
            "server duplicates ignored": sum(s.dedup.ignored for s in self.servers if s.dedup),
        }

    def report(self) -> None:
        metrics = self.metrics()
        print()
        print("=" * 62)
        print(" demo summary - metrics")
        print("=" * 62)
        width = max(len(name) for name in metrics)
        for name, value in metrics.items():
            print(f" {name.ljust(width)} : {value}")
        print("=" * 62)

        if not os.path.exists(self.db_path):
            return

        db = Database(self.db_path).connect()
        try:
            print()
            print("=" * 62)
            print(" demo summary - sqlite")
            print("=" * 62)
            print(f" sensor_data rows        : {db.count('sensor_data')}")
            print(f" controller_command rows : {db.count('controller_command')}")
            print(f" controller_result rows  : {db.count('controller_result')}")
            print(f" gateway_heartbeat rows  : {db.count('gateway_heartbeat')}")
            print(f" alert rows              : {db.count('alert')}")
            print(f" processed_message rows  : {db.count('processed_message')}")
            print(f" sqlite file             : {self.db_path}")
            print("=" * 62)
        finally:
            db.close()

        print()
        print(" gateway state")
        print(" ------------------------------")
        for gateway_id in sorted(self.gateways):
            gateway = self.gateways[gateway_id]
            ownership = gateway.ownership
            print(
                f" {gateway_id}: role={ownership.role:<7} health={ownership.health:<7} "
                f"generation={ownership.generation} peer={ownership.peer_health}"
            )
            for node_id in sorted(gateway.registry.snapshot()):
                entry = gateway.registry.get(node_id)
                print(
                    f"    {node_id}: owner={entry.owner_gateway} "
                    f"generation={entry.generation} status={entry.status}"
                )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart Agriculture Edge AI - v0.2 demo")
    parser.add_argument("--duration", type=float, default=30.0, help="how long to let the system run")
    parser.add_argument("--db", default="demo.db", help="sqlite file used by the demo")
    parser.add_argument("--policy-interval", type=float, default=config.SERVER_POLICY_INTERVAL)

    parser.add_argument(
        "--scenario",
        choices=("normal", "failover", "server-offline"),
        default=None,
        help="preset: normal | failover | server-offline",
    )

    # fault injection
    parser.add_argument("--kill-gateway", default=None, choices=sorted(config.GATEWAY_PORTS),
                        help="simulate this gateway crashing")
    parser.add_argument("--at", type=float, default=10.0, help="when to kill the gateway")
    parser.add_argument("--revive-at", type=float, default=None, help="when the killed gateway comes back")
    parser.add_argument("--inject-stale-at", type=float, default=None,
                        help="when to replay the deposed gateway's stale command")
    parser.add_argument("--server-offline-at", type=float, default=None, help="when the server goes down")
    parser.add_argument("--server-online-at", type=float, default=None, help="when the server comes back")
    parser.add_argument("--drop-command-rate", type=float, default=0.0,
                        help="fraction of CONTROL_COMMAND frames lost (0.0 - 1.0)")
    parser.add_argument("--duplicate-command", action="store_true",
                        help="re-send every command once to exercise idempotency")
    return parser.parse_args(argv)


def apply_scenario(args: argparse.Namespace) -> argparse.Namespace:
    if args.scenario == "failover":
        if args.duration == 30.0:
            args.duration = 46.0
        args.kill_gateway = args.kill_gateway or "A1"
        if args.at == 10.0:
            args.at = 14.0
        if args.revive_at is None:
            args.revive_at = 30.0
        if args.inject_stale_at is None:
            args.inject_stale_at = 38.0
    elif args.scenario == "server-offline":
        if args.duration == 30.0:
            args.duration = 40.0
        if args.server_offline_at is None:
            args.server_offline_at = 10.0
        if args.server_online_at is None:
            args.server_online_at = 25.0
    return args


def clean_previous_run(db_path: str) -> None:
    for candidate in (db_path, db_path + "-wal", db_path + "-shm"):
        if os.path.exists(candidate):
            os.remove(candidate)
    for gateway_id in config.GATEWAY_PORTS:
        for suffix in ("", "-wal", "-shm"):
            path = config.gateway_queue_path(gateway_id) + suffix
            if os.path.exists(path):
                os.remove(path)


async def _main(demo: Demo) -> None:
    await demo.start()
    try:
        await demo.run()
    finally:
        await demo.stop()


def main(argv=None) -> None:
    args = apply_scenario(parse_args(argv))
    clean_previous_run(args.db)

    print(BANNER)
    demo = Demo(args)
    try:
        asyncio.run(_main(demo))
    except KeyboardInterrupt:
        pass
    demo.report()


if __name__ == "__main__":
    main()
