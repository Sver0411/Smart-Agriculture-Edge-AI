"""Store-and-forward queue used by a gateway while the cloud server is down.

The farm keeps working when the uplink is gone. Admitted messages stay in a
local SQLite file and replay oldest first; full capacity rejects new admission
explicitly, without evicting unacknowledged rows or stopping local control.

The original ``message_id`` is preserved, so the server can deduplicate the
replayed traffic.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common.messages import Message, ALERT, CONTROL_RESULT  # noqa: E402
from common.settings import SETTINGS

__all__ = ["OfflineQueue"]

class QueueCapacityError(ValueError):
    """New admission failed; existing unacknowledged rows stay intact."""

NORMAL, HIGH = 0, 1

def admission_priority(message):
    payload = message.payload
    record = payload.get('record')
    evidence = record if isinstance(record, dict) else payload
    if (message.type == CONTROL_RESULT or payload.get('severity') == 'CRITICAL' or
            evidence.get('severity') == 'CRITICAL' or evidence.get('health_state') == 'FAULT'):
        return HIGH
    if message.type == ALERT and payload.get('alert_type') in (
            'SENSOR_FAULT', 'COMMAND_DELIVERY_FAILED', 'CONTROL_RESULT_TIMEOUT', 'GATEWAY_FAILOVER'):
        return HIGH
    return NORMAL

SCHEMA = """
CREATE TABLE IF NOT EXISTS gateway_queue (
    queue_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  TEXT NOT NULL,
    message_type TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  REAL NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS gateway_queue_message ON gateway_queue(message_id);
"""


class OfflineQueue:
    """A durable FIFO of messages that still need to reach the server."""

    def __init__(self, path: str = ":memory:", max_messages=None, max_payload_bytes=None,
                 reserved_messages=None, reserved_payload_bytes=None):
        self.path = path
        self.conn: sqlite3.Connection | None = None
        self.enqueued = 0
        self.replayed = 0
        limits = SETTINGS["offline_queue"]
        self.max_messages = limits["max_messages"] if max_messages is None else max_messages
        self.max_payload_bytes = limits["max_payload_bytes"] if max_payload_bytes is None else max_payload_bytes
        if type(self.max_messages) is not int or self.max_messages < 1 or type(self.max_payload_bytes) is not int or self.max_payload_bytes < 1:
            raise ValueError("outbox limits must be positive integers")
        self.rejected = 0
        self.rejected_high = self.rejected_normal = 0
        # Scale configured reserve for small test/deployment limits unless explicit.
        self.reserved_messages = self.max_messages * limits['reserved_messages'] // limits['max_messages'] if reserved_messages is None else reserved_messages
        self.reserved_payload_bytes = self.max_payload_bytes * limits['reserved_payload_bytes'] // limits['max_payload_bytes'] if reserved_payload_bytes is None else reserved_payload_bytes
        for reserve,total in ((self.reserved_messages,self.max_messages),(self.reserved_payload_bytes,self.max_payload_bytes)):
            if type(reserve) is not int or not 0 <= reserve < total:raise ValueError('invalid critical reserve')

    def connect(self) -> "OfflineQueue":
        if self.conn is None:
            self.conn = sqlite3.connect(self.path, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript(SCHEMA)
            columns = {row[1] for row in self.conn.execute('PRAGMA table_info(gateway_queue)')}
            if 'priority' not in columns:
                self.conn.execute('ALTER TABLE gateway_queue ADD COLUMN priority INTEGER NOT NULL DEFAULT 0')
                for queue_id,raw in self.conn.execute('SELECT queue_id,payload FROM gateway_queue').fetchall():
                    self.conn.execute('UPDATE gateway_queue SET priority=? WHERE queue_id=?',
                                      (admission_priority(Message.from_json(raw)),queue_id))
            self.conn.commit()
        return self

    def close(self) -> None:
        if self.conn is not None:
            self.conn.commit()
            self.conn.close()
            self.conn = None

    # -- write side --------------------------------------------------------

    def enqueue(self, message: Message) -> int:
        """Store a message for later delivery. Returns its queue id."""
        self.connect()
        raw = message.to_json()
        # Repeated command-history uploads keep one outstanding logical row.
        row = self.conn.execute("SELECT queue_id FROM gateway_queue WHERE message_id=?", (message.message_id,)).fetchone()
        if row is not None:return int(row[0])
        count, size = self.conn.execute("SELECT COUNT(*), COALESCE(SUM(length(CAST(payload AS BLOB))),0) FROM gateway_queue").fetchone()
        priority = admission_priority(message)
        count_limit = self.max_messages if priority == HIGH else self.max_messages-self.reserved_messages
        byte_limit = self.max_payload_bytes if priority == HIGH else self.max_payload_bytes-self.reserved_payload_bytes
        if count >= count_limit or size + len(raw.encode()) > byte_limit:
            self.rejected += 1
            if priority == HIGH:self.rejected_high += 1
            else:self.rejected_normal += 1
            raise QueueCapacityError(f"outbox {'HIGH' if priority == HIGH else 'NORMAL'} capacity full; new upload was not admitted")
        cursor = self.conn.execute(
            """
            INSERT INTO gateway_queue (message_id, message_type, payload, created_at, retry_count, priority)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (message.message_id, message.type, raw, time.time(), priority),
        )
        self.conn.commit()
        self.enqueued += 1
        return int(cursor.lastrowid)

    # -- read side ---------------------------------------------------------

    def peek(self, limit: int = 20) -> list[tuple[int, Message]]:
        """Oldest ``limit`` queued messages, still in the queue."""
        self.connect()
        rows = self.conn.execute(
            "SELECT queue_id, payload FROM gateway_queue ORDER BY queue_id LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [(int(row[0]), Message.from_json(row[1])) for row in rows]

    def bump_retry(self, queue_id: int) -> None:
        self.connect()
        self.conn.execute(
            "UPDATE gateway_queue SET retry_count = retry_count + 1 WHERE queue_id = ?",
            (int(queue_id),),
        )
        self.conn.commit()

    def delete(self, queue_id: int) -> None:
        self.connect()
        self.conn.execute("DELETE FROM gateway_queue WHERE queue_id = ?", (int(queue_id),))
        self.conn.commit()
        self.replayed += 1

    def count(self) -> int:
        self.connect()
        return int(self.conn.execute("SELECT COUNT(*) FROM gateway_queue").fetchone()[0])

    def __len__(self) -> int:
        return self.count()

    def stats(self):
        self.connect()
        count, size, oldest = self.conn.execute("SELECT COUNT(*), COALESCE(SUM(length(CAST(payload AS BLOB))),0), MIN(created_at) FROM gateway_queue").fetchone()
        return {"depth":count, "payload_bytes":size, "oldest_age_s":None if oldest is None else max(0,time.time()-oldest),
                "max_messages":self.max_messages, "max_payload_bytes":self.max_payload_bytes,
                "reserved_messages":self.reserved_messages,"reserved_payload_bytes":self.reserved_payload_bytes,
                "admission_rejected":self.rejected,"admission_rejected_high":self.rejected_high,
                "admission_rejected_normal":self.rejected_normal}
