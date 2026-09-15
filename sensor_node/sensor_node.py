"""Sensor node B1 / B2.

The sensor node is the origin of every reading in the system.  It does three
things, in a loop:

1. sample ``temperature`` / ``humidity`` / ``soil_moisture`` / ``light``
   (simulated - no real hardware in v0.1),
2. run the basic SensorTrust check and report a ``FAULT`` as an ``ALERT``,
3. ask AdaptiveSense for the next sampling interval and sleep that long.

Both B and C are direct children of their gateway; the sensor node never talks
to a controller.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import config  # noqa: E402
from common.log import node_log  # noqa: E402
from common.messages import ALERT, SENSOR_DATA, Message, send_message  # noqa: E402
from sensor_node.adaptive_sense import next_sample_interval  # noqa: E402
from sensor_node.sensor_trust import HEALTHY, FAULT, check_sensor_health, health_reasons  # noqa: E402

# name -> (default start value, random walk step, hard clamp)
PROFILES = {
    "temperature": (25.0, 0.6, (-5.0, 45.0)),
    "humidity": (60.0, 4.0, (15.0, 95.0)),
    "soil_moisture": (22.0, 0.15, (5.0, 90.0)),
    "light": (800.0, 120.0, (0.0, 2000.0)),
}


class SensorSimulator:
    """Random-walk generator standing in for real sensors."""

    def __init__(
        self,
        node_id: str = "B?",
        seed: int | None = None,
        start: dict | None = None,
        inject_fault_at: int | None = None,
    ):
        self.node_id = node_id
        self.rng = random.Random(seed)
        self.inject_fault_at = inject_fault_at
        self.samples = 0
        self.values = {name: profile[0] for name, profile in PROFILES.items()}
        for name, value in (start or {}).items():
            if name in self.values:
                self.values[name] = float(value)

    def sample(self) -> dict:
        self.samples += 1

        for name, (_, step, (low, high)) in PROFILES.items():
            value = self.values[name] + self.rng.uniform(-step, step)
            self.values[name] = min(max(value, low), high)

        reading = {name: round(value, 1) for name, value in self.values.items()}

        if self.inject_fault_at is not None and self.samples == self.inject_fault_at:
            reading["soil_moisture"] = 999.0  # obviously broken on purpose

        return reading


class SensorNode:
    """B1 / B2."""

    def __init__(
        self,
        node_id: str,
        gateway_host: str = "127.0.0.1",
        gateway_port: int | None = None,
        simulator: SensorSimulator | None = None,
        slow_interval: float = config.SAMPLE_INTERVAL_SLOW,
        fast_interval: float = config.SAMPLE_INTERVAL_FAST,
        history_size: int = 8,
    ):
        if node_id not in config.GATEWAY_OF_SENSOR:
            raise ValueError(f"unknown sensor node id: {node_id!r}")

        self.node_id = node_id
        self.gateway_host = gateway_host
        self.gateway_port = (
            gateway_port
            if gateway_port is not None
            else config.GATEWAY_PORTS[config.GATEWAY_OF_SENSOR[node_id]]
        )
        self.gateway_id = config.GATEWAY_OF_SENSOR[node_id]
        self.simulator = simulator or SensorSimulator(node_id)
        self.slow_interval = slow_interval
        self.fast_interval = fast_interval
        self.history_size = history_size

        self.history: list[dict] = []
        self._stopping = False

    # -- main loop ---------------------------------------------------------

    async def run(self) -> None:
        while not self._stopping:
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.gateway_host, self.gateway_port), timeout=3.0
                )
            except (OSError, asyncio.TimeoutError):
                node_log(self.node_id, f"gateway {self.gateway_id} not reachable, retrying in 1s")
                await asyncio.sleep(1.0)
                continue

            node_log(self.node_id, f"connected to gateway {self.gateway_id} ({self.gateway_host}:{self.gateway_port})")
            try:
                await self._sample_loop(writer)
            except (ConnectionResetError, BrokenPipeError, OSError):
                node_log(self.node_id, f"connection to {self.gateway_id} lost, reconnecting")
            finally:
                await close_writer(writer)

    async def _sample_loop(self, writer) -> None:
        while not self._stopping:
            reading = self.simulator.sample()
            self.history.append(reading)
            del self.history[: -self.history_size]

            node_log(
                self.node_id,
                f"sample #{self.simulator.samples} soil moisture = {reading['soil_moisture']}% "
                f"(temp={reading['temperature']}C, hum={reading['humidity']}%, light={reading['light']})",
            )

            health = check_sensor_health(reading)
            if health == HEALTHY:
                node_log(self.node_id, f"sensor health = {HEALTHY}")
                await send_message(
                    writer,
                    Message(
                        type=SENSOR_DATA,
                        source=self.node_id,
                        target=self.gateway_id,
                        payload={"data": reading, "health_state": HEALTHY},
                    ),
                )
                node_log(self.node_id, f"SENSOR_DATA sent to {self.gateway_id}")
            else:
                reasons = health_reasons(reading)
                node_log(self.node_id, f"sensor health = {FAULT} ({'; '.join(reasons)})")
                await send_message(
                    writer,
                    Message(
                        type=ALERT,
                        source=self.node_id,
                        target=self.gateway_id,
                        payload={
                            "alert_type": "SENSOR_FAULT",
                            "sensor_node_id": self.node_id,
                            "health_state": FAULT,
                            "reasons": reasons,
                            "data": reading,
                        },
                    ),
                )
                node_log(self.node_id, f"ALERT sent to {self.gateway_id} (data never reached the decision stage)")

            interval = next_sample_interval(
                self.history, slow=self.slow_interval, fast=self.fast_interval
            )
            node_log(self.node_id, f"next sampling interval = {interval:g}s")
            await asyncio.sleep(interval)

    def stop(self) -> None:
        self._stopping = True


# --------------------------------------------------------------------------
# standalone entry point
# --------------------------------------------------------------------------


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart Agriculture Edge AI - sensor node")
    parser.add_argument("--id", required=True, choices=sorted(config.GATEWAY_OF_SENSOR))
    parser.add_argument("--gateway", default=None, choices=sorted(config.GATEWAY_PORTS), help="gateway id")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--inject-fault",
        type=int,
        default=None,
        metavar="N",
        help="emit one out-of-range reading at sample N (demonstrates SensorTrust)",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    gateway_id = args.gateway or config.GATEWAY_OF_SENSOR[args.id]
    port = args.port if args.port is not None else config.GATEWAY_PORTS[gateway_id]
    node = SensorNode(
        node_id=args.id,
        gateway_host=args.host,
        gateway_port=port,
        simulator=SensorSimulator(args.id, seed=args.seed, inject_fault_at=args.inject_fault),
    )
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
