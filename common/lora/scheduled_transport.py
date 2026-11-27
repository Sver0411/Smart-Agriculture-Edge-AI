"""Serialize a host field channel and choose among queued application flows."""
import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
import math

from common.lora.codec import HEADER_SIZE, MAX_FRAME, MAX_FRAGMENTS, ROLES, FrameError, canonical, route
from common.lora.transport import SimulatedLoRa
from common.messages import ALERT, HEARTBEAT, NODE_STATUS, SENSOR_DATA, Message
from third_party.netadapt import fud_ada


# Relative service targets and deadline budgets in simulated fragment slots.
# Command, result, and receipt traffic share a FIFO per directed route.
CLASSES = {
    "telemetry": ("telemetry", 1, 32, None),
    "status": ("status", 2, 16, None),
    "event": ("event", 4, 8, 16),
    "control": ("event", 6, 6, 12),
}
CLASS_NAMES = tuple(CLASSES)


def _classify(message):
    if message.type == ALERT:
        return "event"
    if message.type == SENSOR_DATA:
        if (message.payload.get("importance") == "HIGH"
                or message.payload.get("health_state") == "FAULT"
                or message.payload.get("severity") == "CRITICAL"):
            return "event"
        return "telemetry"
    if message.type in (NODE_STATUS, HEARTBEAT):
        return "status"
    return "control"


@dataclass
class _Pending:
    flow: int
    name: str
    spec: fud_ada.Flow
    generated: int
    order: int
    writer: object
    message: object
    completion: asyncio.Future


class ScheduledLoRa(SimulatedLoRa):
    """Host simulation of one shared field outlet; overload backpressures senders."""

    def __init__(self, *, policy="fud_ada", queue_capacity=128, trace_capacity=8192, **radio_options):
        super().__init__(**radio_options)
        if policy not in ("fifo", "fud_ada"):
            raise ValueError("field policy must be fifo or fud_ada")
        if type(self.mtu) is not int or not HEADER_SIZE < self.mtu <= MAX_FRAME:
            raise ValueError("invalid field MTU")
        if any(type(n) is not int or n < 1 for n in (queue_capacity, trace_capacity)):
            raise ValueError("queue and trace capacities must be positive integers")
        self.policy = policy
        self._capacity = asyncio.BoundedSemaphore(queue_capacity)
        self._queues = defaultdict(deque)
        self._feedback = defaultdict(fud_ada.Feedback)
        self._decisions = deque(maxlen=trace_capacity)
        self._worker = None
        self._closed = False
        self._slot = 1
        self._order = 0
        self._depth = 0
        self.metrics.update(scheduler_decisions=0, contended_decisions=0, max_queue_depth=0)

    @property
    def decisions(self):
        return list(self._decisions)

    async def __call__(self, writer, message):
        if "SERVER" in (message.source, message.target):
            return False
        if self._closed:
            raise RuntimeError("field outlet closed")
        await self._capacity.acquire()
        try:
            if self._closed:
                raise RuntimeError("field outlet closed")
            route(message.source, message.target, message.type)
            raw = canonical(message)
            message = Message.from_json(raw)
            category = _classify(message)
            flow = ((ROLES.index(message.source) * len(ROLES) + ROLES.index(message.target))
                    * len(CLASS_NAMES) + CLASS_NAMES.index(category))
            name = f"{message.source}>{message.target}/{category}"
            fragments = math.ceil(len(raw) / (self.mtu - HEADER_SIZE))
            if fragments > MAX_FRAGMENTS:
                raise FrameError("fragment capacity exceeded")
            spec = fud_ada.Flow(*CLASSES[category], service=fragments)
            completion = asyncio.get_running_loop().create_future()
            self._order += 1
            pending = _Pending(flow, name, spec, self._slot, self._order, writer, message, completion)
        except Exception:
            self._capacity.release()
            raise
        self._queues[flow].append(pending)
        self._depth += 1
        self.metrics["max_queue_depth"] = max(self.metrics["max_queue_depth"], self._depth)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._drain())
        return await completion

    async def _drain(self):
        while self._queues:
            heads = [q[0] for q in self._queues.values()]
            if self.policy == "fifo":
                selected = min(heads, key=lambda p: p.order)
            else:
                selected = fud_ada.choose(self._slot, heads, self._feedback)
            queue = self._queues[selected.flow]
            queue.popleft()
            if not queue:
                del self._queues[selected.flow]
            try:
                if not selected.completion.cancelled():
                    await self._transmit(selected, heads)
            except Exception as exc:
                if not selected.completion.done():
                    selected.completion.set_exception(exc)
            finally:
                self._depth -= 1
                self._capacity.release()
            # Let active producers refill the outlet even on zero-latency links.
            await asyncio.sleep(0)

    async def _transmit(self, selected, heads):
        started = self._slot
        before = self.metrics["reassembled"]
        try:
            await super().__call__(selected.writer, selected.message)
        finally:
            self._slot += selected.spec.service
            delivered = self.metrics["reassembled"] > before
            fud_ada.update(heads, selected, self._feedback, self._slot, delivered)
            self.metrics["scheduler_decisions"] += 1
            self.metrics["contended_decisions"] += int(len(heads) > 1)
            self._decisions.append({
                "slot": started, "end_slot": self._slot, "ingress_slot": selected.generated,
                "flow": selected.name, "candidates": sorted(p.name for p in heads),
                "message_id": selected.message.message_id, "type": selected.message.type,
                "service_slots": selected.spec.service, "reassembled": delivered,
            })
        if not selected.completion.done():
            selected.completion.set_result(True)

    async def close(self):
        """Stop admissions and finish already admitted sends."""
        self._closed = True
        if self._worker is not None:
            await asyncio.shield(self._worker)
