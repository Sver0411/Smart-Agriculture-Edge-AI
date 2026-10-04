"""Reliability helpers shared by the nodes (v0.2).

Two small pieces:

* :class:`AckTracker` - used by the gateway for ``CONTROL_COMMAND`` delivery.
  Nodes retry ``NODE_REGISTER`` in their own registration loops. A
  ``SERVER_POLICY`` receipt ACK is not tracked for retry by the server.
* :class:`Counters` - a tiny metric holder used by the demo summary.

There is no queue broker here on purpose: delivery is "at least once" with an
idempotent receiver, which is the only combination that is safe for actuators.
"""

from __future__ import annotations

import pathlib
import sys
import time
from collections import Counter
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import config  # noqa: E402
from common.messages import Message  # noqa: E402

__all__ = ["PendingMessage", "AckTracker", "Counters", "COMMAND_DELIVERY_FAILED"]

COMMAND_DELIVERY_FAILED = "COMMAND_DELIVERY_FAILED"


@dataclass
class PendingMessage:
    """One message waiting for its ACK."""

    message: Message
    attempts: int = 1  # times it has been written to the socket
    retries: int = 0  # retransmissions after the first attempt
    expires_at: float = field(default=0.0)


class AckTracker:
    """Track unacknowledged messages and schedule their retries."""

    def __init__(
        self,
        timeout: float = config.ACK_TIMEOUT,
        max_retries: int = config.MAX_RETRIES,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.pending: dict[str, PendingMessage] = {}

    # -- bookkeeping -------------------------------------------------------

    def track(self, message: Message, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self.pending[message.message_id] = PendingMessage(
            message=message, expires_at=now + self.timeout
        )

    def acknowledge(self, ack_message_id: str) -> bool:
        """Return ``True`` when the id was still waiting for an ACK."""
        return self.pending.pop(ack_message_id, None) is not None

    def discard(self, message_id: str) -> None:
        self.pending.pop(message_id, None)

    def __len__(self) -> int:
        return len(self.pending)

    # -- retry scheduling --------------------------------------------------

    def due(self, now: float | None = None) -> list[Message]:
        """Messages whose ACK is overdue and that still have retries left."""
        now = time.monotonic() if now is None else now
        return [
            entry.message
            for entry in self.pending.values()
            if now >= entry.expires_at and entry.retries < self.max_retries
        ]

    def mark_retry(self, message_id: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        entry = self.pending.get(message_id)
        if entry is None:
            return
        entry.retries += 1
        entry.message.attempt = entry.retries + 1
        entry.attempts += 1
        entry.expires_at = now + self.timeout

    def exhausted(self, now: float | None = None) -> list[Message]:
        """Messages that ran out of retries - delivery has to be given up."""
        now = time.monotonic() if now is None else now
        return [
            entry.message
            for entry in self.pending.values()
            if now >= entry.expires_at and entry.retries >= self.max_retries
        ]


class Counters:
    """Named integer counters for the demo summary."""

    def __init__(self, **initial: int):
        self._values: Counter = Counter(initial)

    def inc(self, name: str, by: int = 1) -> None:
        self._values[name] += by

    def get(self, name: str) -> int:
        return int(self._values.get(name, 0))

    def as_dict(self) -> dict:
        return {key: int(value) for key, value in sorted(self._values.items())}

    def merge(self, other: "Counters") -> "Counters":
        self._values.update(other._values)
        return self


class CommandOutcomes:
    """Receipt and execution are independent. Missing results become UNKNOWN.

    Never issue a new actuator command to repair a missing result. Late results
    can resolve UNKNOWN; terminal result IDs are retained for this process.
    """
    def __init__(self, timeout=10):
        self.timeout=timeout;self.pending={};self.unknown=set();self.resolved=set()
    def track(self,message,now):
        self.pending[message.payload['command_id']]={'message':message,'deadline':now+self.timeout,'acked':False}
    def ack(self,command_id):
        if command_id in self.pending:self.pending[command_id]['acked']=True
    def result(self,command_id):
        if command_id in self.resolved:return 'duplicate'
        late=command_id in self.unknown
        self.pending.pop(command_id,None);self.unknown.discard(command_id);self.resolved.add(command_id)
        return 'late' if late else 'resolved'
    def expire(self,now):
        unknown=[]
        for key,entry in list(self.pending.items()):
            if entry['acked'] and now>=entry['deadline']:
                self.pending.pop(key);self.unknown.add(key);unknown.append(entry['message'])
        return unknown
