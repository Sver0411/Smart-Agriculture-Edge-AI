"""Server side deduplication of gateway uploads (v0.2).

Gateways upload "at least once": a message can arrive twice after a retry, a
reconnect or a queue replay.  The server therefore remembers every
``message_id`` it has already processed and silently ignores repeats instead of
writing a second copy into the history tables.

The storage is one SQLite table with ``message_id`` as a UNIQUE key - no Redis,
no bloom filter, nothing clever.
"""

from __future__ import annotations

import sqlite3
import time

__all__ = ["Deduplicator"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_message (
    message_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL
);
"""


class Deduplicator:
    """Remembers the ``message_id`` of every processed upload."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.ignored = 0
        self.processed = 0
        conn.executescript(SCHEMA)
        conn.commit()

    def is_new(self, message_id: str | None) -> bool:
        """Return ``True`` the first time a ``message_id`` is seen."""
        if not message_id:
            # nothing to deduplicate on - treat as new
            return True

        cursor = self.conn.execute(
            "INSERT OR IGNORE INTO processed_message (message_id, created_at) VALUES (?, ?)",
            (message_id, time.time()),
        )
        if cursor.rowcount == 0:
            self.ignored += 1
            return False

        self.processed += 1
        self.conn.commit()
        return True
