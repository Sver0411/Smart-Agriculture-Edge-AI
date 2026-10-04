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
import math
from contextvars import ContextVar
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
    "NODE_REGISTER",
    "NODE_REGISTER_ACK",
    "NODE_STATUS",
    "ACK",
    "PERSISTED_ACK",
    "RETRY_TRACKED_TYPES",
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
NODE_REGISTER = "NODE_REGISTER"
NODE_REGISTER_ACK = "NODE_REGISTER_ACK"
NODE_STATUS = "NODE_STATUS"
ACK = "ACK"
PERSISTED_ACK = "PERSISTED_ACK"

MESSAGE_TYPES = (
    SENSOR_DATA,
    CONTROL_COMMAND,
    CONTROL_RESULT,
    HEARTBEAT,
    ALERT,
    SERVER_POLICY,
    NODE_REGISTER,
    NODE_REGISTER_ACK,
    NODE_STATUS,
    ACK,
    PERSISTED_ACK,
)

# Messages with an implemented retry path: gateway AckTracker for commands,
# node registration retry loop for NODE_REGISTER. SERVER_POLICY receives a
# receipt ACK, but the server does not track that ACK or retry the policy.
RETRY_TRACKED_TYPES = (CONTROL_COMMAND, NODE_REGISTER)

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
    protocol_version: int | None = None
    sequence: int | None = None
    attempt: int | None = None
    generation: int | None = None

    # -- serialisation -----------------------------------------------------

    def to_dict(self) -> dict:
        envelope = {
            "type": self.type,
            "source": self.source,
            "target": self.target,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
            "payload": self.payload,
        }

        for key in ("protocol_version", "sequence", "attempt", "generation"):
            value = getattr(self,key)
            if value is not None: envelope[key] = value
        return envelope

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False)

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

        if not isinstance(data["timestamp"], (int, float)) or isinstance(data["timestamp"], bool) or not math.isfinite(data["timestamp"]):
            raise MessageError("timestamp must be a number")

        if not isinstance(data["payload"], dict):
            raise MessageError("payload must be an object")

        for name in ("source", "target", "message_id"):
            if not isinstance(data[name], str) or not data[name]:
                raise MessageError(f"{name} must be a non-empty string")

        optional = {}
        for key in ("protocol_version", "sequence", "attempt", "generation"):
            if key in data:
                value=data[key]
                if type(value) is not int or value < (1 if key in ("protocol_version", "attempt") else 0):
                    raise MessageError(f"invalid {key}")
                if key == "protocol_version" and value != 1:
                    raise MessageError("unsupported protocol version")
                optional[key]=value
        if not finite_json(data["payload"]):
            raise MessageError("payload contains nonfinite number")
        return cls(
            **optional,
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
            return cls.from_dict(data)
        except MessageError:
            raise
        except (ValueError, RecursionError) as exc:
            raise MessageError(f"malformed JSON message: {exc}") from exc

    @classmethod
    def from_line(cls, raw: str) -> "Message":
        return cls.from_json(raw.strip())

    # -- helpers -----------------------------------------------------------

    def reply(self, type: str, payload: dict) -> "Message":
        """Build a message that answers this one (source/target swapped)."""
        return Message(type=type, source=self.target, target=self.source, payload=payload)

    def ack(self, source: str | None = None) -> "Message":
        """Build the ACK that acknowledges this specific message."""
        return Message(
            type=ACK,
            source=source or self.target,
            target=self.source,
            payload={"ack_message_id": self.message_id},
        )


# --------------------------------------------------------------------------
# asyncio stream helpers
# --------------------------------------------------------------------------


async def send_message(writer, message: Message) -> None:
    """Write one message to an ``asyncio`` stream writer."""
    interceptor = transport_interceptor.get()
    if interceptor is not None and await interceptor(writer, message):
        return
    writer.write(message.to_line().encode("utf-8"))
    await writer.drain()
    observe_transport("sent", message)


async def read_message(reader):
    """Read one message from an ``asyncio`` stream reader.

    Returns ``None`` when the peer closed the connection.
    """
    try:
        line = await reader.readline()
    except (ValueError, asyncio.LimitOverrunError) as exc:
        raise MessageError("message frame exceeds stream limit") from exc
    if not line:
        return None
    text = line.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    message = Message.from_line(text)
    observe_transport("delivered", message)
    return message


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


transport_observer = ContextVar("transport_observer", default=None)
transport_interceptor = ContextVar("transport_interceptor", default=None)

def observe_transport(event,message):
    observer=transport_observer.get()
    if observer is not None:observer(event,message)

def finite_json(obj):
    if isinstance(obj,float):return math.isfinite(obj)
    if isinstance(obj,dict):return all(finite_json(v) for v in obj.values())
    if isinstance(obj,list):return all(finite_json(v) for v in obj)
    return True
