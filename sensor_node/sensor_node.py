"""Sensor node B1 / B2.

The sensor node is the origin of every reading in the system.  It does four
things, in a loop:

1. sample ``temperature`` / ``humidity`` / ``soil_moisture`` / ``light``
   (simulated - no real hardware in v0.2),
2. run the basic SensorTrust check and report a ``FAULT`` as an ``ALERT``,
3. ask AdaptiveSense for the next sampling interval and sleep that long,
4. stay registered with one gateway, falling back to the other one when the
   owner disappears.

Both B and C are direct children of their gateway; the sensor node never talks
to a controller.

Unlike the controller, the sensor is **send-only**: nothing ever flows back to
it except the ``NODE_REGISTER_ACK`` it waits for, so it does not run an inbound
reader.  It learns its owner and epoch from that ACK and refuses a gateway whose
epoch is older than the one it already holds.  A gateway that dies is noticed on
the write path (the socket errors out) and it then walks its candidate list.
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
from common.messages import (  # noqa: E402
    ALERT,
    NODE_REGISTER,
    NODE_REGISTER_ACK,
    SENSOR_DATA,
    Message,
    close_writer,
    read_message,
    send_message,
)
from common.reliability import Counters  # noqa: E402
from sensor_node.adaptive_sense import next_sample_interval  # noqa: E402
from sensor_node.sensor_trust import FAULT, HEALTHY, check_sensor_health, health_reasons  # noqa: E402

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
        self.primary_gateway = config.GATEWAY_OF_SENSOR[node_id]
        self.gateway_id = self.primary_gateway
        self.fixed_port = gateway_port

        self.owner_gateway: str | None = None
        self.generation = config.INITIAL_GENERATION

        self.simulator = simulator or SensorSimulator(node_id)
        self.slow_interval = slow_interval
        self.fast_interval = fast_interval
        self.history_size = history_size
        self.metrics = Counters()

        self.history: list[dict] = []
        self._stopping = False

    # -- candidate gateways ------------------------------------------------

    def _candidates(self) -> list[tuple[str, str, int]]:
        """Gateways to try, in order: current owner first, then the rest."""
        if self.fixed_port is not None:
            return [(self.gateway_id, self.gateway_host, self.fixed_port)]

        order = [self.owner_gateway or self.primary_gateway]
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
            await self._sample_loop(reader, writer)
        except (ConnectionResetError, BrokenPipeError, OSError):
            node_log(self.node_id, f"connection to {gateway_id} lost, re-registering elsewhere")
        finally:
            await close_writer(writer)

    async def _register(self, reader, writer, gateway_id: str) -> bool:
        """Send NODE_REGISTER until the gateway acknowledges it."""
        for attempt in range(1, config.MAX_RETRIES + 2):
            await send_message(
                writer,
                Message(
                    type=NODE_REGISTER,
                    source=self.node_id,
                    target=gateway_id,
                    payload={"node_id": self.node_id, "node_type": config.SENSOR},
                ),
            )
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
            if generation < self.generation:
                node_log(
                    self.node_id,
                    f"refusing {gateway_id}: generation {generation} < {self.generation}",
                )
                return False

            self.owner_gateway = owner
            self.generation = generation
            node_log(self.node_id, f"registered with {owner} (generation={generation})")
            return True
        return False

    # -- sampling ----------------------------------------------------------

    async def _sample_loop(self, reader, writer) -> None:
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
                        target=self.owner_gateway or self.gateway_id,
                        payload={"data": reading, "health_state": HEALTHY},
                    ),
                )
                self.metrics.inc("sensor_messages")
                node_log(self.node_id, f"SENSOR_DATA -> {self.owner_gateway or self.gateway_id}")
            else:
                reasons = health_reasons(reading)
                node_log(self.node_id, f"sensor health = {FAULT} ({'; '.join(reasons)})")
                await send_message(
                    writer,
                    Message(
                        type=ALERT,
                        source=self.node_id,
                        target=self.owner_gateway or self.gateway_id,
                        payload={
                            "alert_type": "SENSOR_FAULT",
                            "sensor_node_id": self.node_id,
                            "health_state": FAULT,
                            "reasons": reasons,
                            "data": reading,
                        },
                    ),
                )
                node_log(self.node_id, "ALERT sent (data never reached the decision stage)")

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
    parser.add_argument("--gateway", default=None, choices=sorted(config.GATEWAY_PORTS), help="primary gateway id")
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
    node = SensorNode(
        node_id=args.id,
        gateway_host=args.host,
        gateway_port=args.port,
        simulator=SensorSimulator(args.id, seed=args.seed, inject_fault_at=args.inject_fault),
    )
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
