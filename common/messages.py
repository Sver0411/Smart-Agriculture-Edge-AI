"""The unified message protocol of Smart Agriculture Edge AI v0.1.

Every module speaks exactly the same envelope, so no component has to know how
another component serialises its data::

    {
        "type": "SENSOR_DATA",
        "source": "B1",
        "target": "A1",
        "timestamp": 123456789.0,
        "message_id": "9f2c1ab34d5e",
        "payload": {}
    }

Messages travel as newline delimited JSON over TCP.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field

__all__ = [
    "SENSOR_DATA",
    "CONTROL_COMMAND",
    "CONTROL_RESULT",
    "HEARTBEAT",
    "ALERT",
    "SERVER_POLICY",
    "MESSAGE_TYPES",
    "REQUIRED_FIELDS",
    "Message",
    "MessageError",
    "new_message_id",
    "send_message",
    "read_message",
    "close_writer",
]

SENSOR_DATA = "SENSOR_DATA"
CONTROL_COMMAND = "CONTROL_COMMAND"
CONTROL_RESULT = "CONTROL_RESULT"
HEARTBEAT = "HEARTBEAT"
ALERT = "ALERT"
SERVER_POLICY = "SERVER_POLICY"

MESSAGE_TYPES = (
    SENSOR_DATA,
    CONTROL_COMMAND,
    CONTROL_RESULT,
    HEARTBEAT,
    ALERT,
    SERVER_POLICY,
)

REQUIRED_FIELDS = ("type", "source", "target", "timestamp", "message_id", "payload")


class MessageError(ValueError):
    """Raised when a raw message does not follow the protocol."""


def new_message_id() -> str:
    """Return a short unique id used for ``message_id`` / ``command_id``."""
    return uuid.uuid4().hex[:12]


@dataclass
class Message:
    """A single protocol message."""

    type: str
    source: str
    target: str
    payload: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=new_message_id)

    # -- serialisation -----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "source": self.source,
            "target": self.target,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def to_line(self) -> str:
        """JSON text plus the newline that delimits messages on the wire."""
        return self.to_json() + "\n"

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        if not isinstance(data, dict):
            raise MessageError("message must be a JSON object")

        missing = [name for name in REQUIRED_FIELDS if name not in data]
        if missing:
            raise MessageError(f"missing required field(s): {', '.join(missing)}")

        if data["type"] not in MESSAGE_TYPES:
            raise MessageError(f"unknown message type: {data['type']!r}")

        if not isinstance(data["timestamp"], (int, float)) or isinstance(data["timestamp"], bool):
            raise MessageError("timestamp must be a number")

        if not isinstance(data["payload"], dict):
            raise MessageError("payload must be an object")

        for name in ("source", "target", "message_id"):
            if not isinstance(data[name], str) or not data[name]:
                raise MessageError(f"{name} must be a non-empty string")

        return cls(
            type=data["type"],
            source=data["source"],
            target=data["target"],
            payload=data["payload"],
            timestamp=float(data["timestamp"]),
            message_id=data["message_id"],
        )

    @classmethod
    def from_json(cls, raw: str) -> "Message":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MessageError(f"malformed JSON message: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def from_line(cls, raw: str) -> "Message":
        return cls.from_json(raw.strip())

    # -- helpers -----------------------------------------------------------

    def reply(self, type: str, payload: dict) -> "Message":
        """Build a message that answers this one (source/target swapped)."""
        return Message(type=type, source=self.target, target=self.source, payload=payload)


# --------------------------------------------------------------------------
# asyncio stream helpers
# --------------------------------------------------------------------------


async def send_message(writer, message: Message) -> None:
    """Write one message to an ``asyncio`` stream writer."""
    writer.write(message.to_line().encode("utf-8"))
    await writer.drain()


async def read_message(reader):
    """Read one message from an ``asyncio`` stream reader.

    Returns ``None`` when the peer closed the connection.
    """
    line = await reader.readline()
    if not line:
        return None
    text = line.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    return Message.from_line(text)


async def close_writer(writer) -> None:
    """Close a stream writer without ever blocking a shutdown path.

    ``StreamWriter.wait_closed()`` can wait forever on a half open socket, and
    during cancellation it may never return at all, so it gets a hard timeout.
    """
    if writer is None:
        return
    try:
        writer.close()
    except Exception:  # pragma: no cover - already closed
        return
    try:
        await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
    except Exception:  # pragma: no cover - timeout or already closed
        pass
