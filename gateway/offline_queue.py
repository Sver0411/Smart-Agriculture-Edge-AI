"""Store-and-forward queue used by a gateway while the cloud server is down.

The farm must keep working when the uplink is gone, so the gateway never drops
an upload: it writes it into a small local SQLite file and replays it (oldest
first) once the server answers again.  No Redis, no broker - just a file.

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

from common.messages import Message  # noqa: E402

__all__ = ["OfflineQueue"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS gateway_queue (
    queue_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  TEXT NOT NULL,
    message_type TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  REAL NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0
);
"""


class OfflineQueue:
    """A durable FIFO of messages that still need to reach the server."""

    def __init__(self, path: str = ":memory:"):
        self.path = path
        self.conn: sqlite3.Connection | None = None
        self.enqueued = 0
        self.replayed = 0

    def connect(self) -> "OfflineQueue":
        if self.conn is None:
            self.conn = sqlite3.connect(self.path, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript(SCHEMA)
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
        cursor = self.conn.execute(
            """
            INSERT INTO gateway_queue (message_id, message_type, payload, created_at, retry_count)
            VALUES (?, ?, ?, ?, 0)
            """,
            (message.message_id, message.type, message.to_json(), time.time()),
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
