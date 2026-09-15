"""One-command demo of the whole Smart Agriculture Edge AI v0.1 system.

``python demo.py`` starts every node of the architecture inside a single
process (server, gateways A1 / A2, sensor nodes B1 / B2 and controller nodes
C1 / C2) and lets the full loop run for a while::

    B -> A -> C -> A -> Server

The nodes still talk to each other over real TCP sockets, so this is the same
code path as running every node in its own terminal.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from common import config  # noqa: E402
from common.log import node_log  # noqa: E402
from controller_node.controller_node import ControllerNode  # noqa: E402
from gateway.gateway import Gateway  # noqa: E402
from sensor_node.sensor_node import SensorNode, SensorSimulator  # noqa: E402
from server.database import Database  # noqa: E402
from server.server import Server  # noqa: E402

BANNER = """
================================================================================
 Smart Agriculture Edge AI  -  v0.1 demo
================================================================================
                              cloud server (:9100)
                                      |
                       +--------------+--------------+
                       |                             |
                  gateway A1                    gateway A2
                 (:9201) <-- heartbeat --> (:9202)
                       |                             |
                 +-----+-----+                 +-----+-----+
                 |           |                 |           |
               B1 (soil)   C1 (pump)         B2 (soil)   C2 (pump)

 full loop:  B -> A -> C -> A -> Server
================================================================================
"""


def build_nodes():
    """Create every node object of the v0.1 system."""
    server = Server(db_path=DEMO_DB)

    gateways = {gateway_id: Gateway(gateway_id) for gateway_id in ("A1", "A2")}

    sensors = {
        "B1": SensorNode(
            "B1",
            simulator=SensorSimulator("B1", seed=11, start={"soil_moisture": 21.5}, inject_fault_at=4),
        ),
        "B2": SensorNode(
            "B2",
            simulator=SensorSimulator("B2", seed=22, start={"temperature": 33.5, "soil_moisture": 41.0}),
        ),
    }

    controllers = {node_id: ControllerNode(node_id) for node_id in ("C1", "C2")}

    return server, gateways, sensors, controllers


async def run_demo(duration: float, kill_peer_at: float | None = None) -> None:
    server, gateways, sensors, controllers = build_nodes()

    await server.start()
    for gateway in gateways.values():
        await gateway.start()
    await asyncio.sleep(0.3)

    nodes = {**sensors, **controllers}
    tasks = {node_id: asyncio.create_task(node.run(), name=node_id) for node_id, node in nodes.items()}

    node_log("DEMO", f"running for {duration:g}s ...")
    try:
        if kill_peer_at is not None and kill_peer_at < duration:
            await asyncio.sleep(kill_peer_at)
            node_log("DEMO", "simulating an A2 failure (v0.1 only detects it, no takeover)")
            for node_id in ("B2", "C2"):
                nodes[node_id].stop()
                tasks[node_id].cancel()
            await gateways["A2"].stop()
            await asyncio.sleep(duration - kill_peer_at)
        else:
            await asyncio.sleep(duration)
    except asyncio.CancelledError:  # pragma: no cover - manual interrupt
        pass

    node_log("DEMO", "stopping nodes ...")
    for node in nodes.values():
        node.stop()
    for task in tasks.values():
        task.cancel()
    await asyncio.gather(*tasks.values(), return_exceptions=True)
    await asyncio.sleep(0.2)

    for gateway in gateways.values():
        await gateway.stop()
    await server.stop()


def report(db_path: str) -> None:
    if not os.path.exists(db_path):
        print("no database written")
        return

    db = Database(db_path).connect()
    try:
        print()
        print("=" * 60)
        print(" demo summary")
        print("=" * 60)
        print(f" sensor_data rows        : {db.count('sensor_data')}")
        print(f" controller_command rows : {db.count('controller_command')}")
        print(f" controller_result rows  : {db.count('controller_result')}")
        print(f" gateway_heartbeat rows  : {db.count('gateway_heartbeat')}")
        print(f" alert rows              : {db.count('alert')}")
        print(f" sqlite file             : {db_path}")
        print("=" * 60)
    finally:
        db.close()


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart Agriculture Edge AI - full v0.1 demo")
    parser.add_argument("--duration", type=float, default=30.0, help="how long to let the system run")
    parser.add_argument("--db", default="demo.db", help="sqlite file used by the demo")
    parser.add_argument(
        "--kill-peer-at",
        type=float,
        default=None,
        metavar="SECONDS",
        help="optional: drop gateway A2 after N seconds to show the peer offline detection",
    )
    return parser.parse_args(argv)


DEMO_DB = "demo.db"


def main(argv=None) -> None:
    global DEMO_DB
    args = parse_args(argv)
    DEMO_DB = args.db

    if os.path.exists(DEMO_DB):
        os.remove(DEMO_DB)
    for suffix in ("-wal", "-shm"):
        extra = DEMO_DB + suffix
        if os.path.exists(extra):
            os.remove(extra)

    print(BANNER)
    try:
        asyncio.run(run_demo(args.duration, args.kill_peer_at))
    except KeyboardInterrupt:
        pass
    report(DEMO_DB)


if __name__ == "__main__":
    main()
