"""Store-and-forward queue used by a gateway while the cloud server is down.

The farm keeps working when the uplink is gone. Admitted messages stay in a
local SQLite file and replay oldest first; full capacity rejects new admission
explicitly, without evicting unacknowledged rows or stopping local control.

The original ``message_id`` is preserved, so the server can deduplicate the
replayed traffic.
"""

from __future__ import annotations

import hashlib
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
            evidence.get('importance') == 'HIGH' or evidence.get('severity') == 'CRITICAL' or evidence.get('health_state') == 'FAULT'):
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
CREATE TABLE IF NOT EXISTS sensor_receipts (
    identity TEXT PRIMARY KEY,
    digest TEXT NOT NULL,
    received_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sensor_control_audit (
    identity TEXT PRIMARY KEY REFERENCES sensor_receipts(identity),
    state TEXT NOT NULL,
    command_id TEXT,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sensor_audit_command ON sensor_control_audit(command_id);
CREATE TABLE IF NOT EXISTS result_receipts (
    identity TEXT PRIMARY KEY,
    digest TEXT NOT NULL,
    received_at REAL NOT NULL
);
"""


class OfflineQueue:
    """A durable FIFO of messages that still need to reach the server."""

    def __init__(self, path: str = ":memory:", max_messages=None, max_payload_bytes=None,
                 reserved_messages=None, reserved_payload_bytes=None, max_sensor_receipts=100000, max_result_receipts=100000):
        if type(max_sensor_receipts) is not int or max_sensor_receipts < 1:
            raise ValueError("receipt limit must be positive")
        if type(max_result_receipts) is not int or max_result_receipts < 1:
            raise ValueError('result receipt limit must be positive')
        self.max_result_receipts = max_result_receipts
        self.max_sensor_receipts = max_sensor_receipts
        self.receipt_capacity_rejected = 0
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
            self.conn.execute("PRAGMA synchronous=FULL")
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
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            queue_id, inserted = self._enqueue(message)
        self.enqueued += inserted
        return queue_id

    def _enqueue(self, message):
        raw = message.to_json()
        # Repeated command-history uploads keep one outstanding logical row.
        row = self.conn.execute("SELECT queue_id FROM gateway_queue WHERE message_id=?", (message.message_id,)).fetchone()
        if row is not None:return int(row[0]), False
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
        return int(cursor.lastrowid), True

    def sensor_is_fresh(self, identity):
        """Persisted high-water check for this device boot, including after replay."""
        self.connect()
        prefix = identity.rsplit('-', 2)[0] + '-'
        latest = self.conn.execute(
            'SELECT MAX(identity) FROM sensor_receipts WHERE identity BETWEEN ? AND ?',
            (prefix + '00000000-S', prefix + 'ffffffff-S')).fetchone()[0]
        return latest is None or identity > latest

    def admit_sensor(self, message, identity, digest):
        """Commit receipt and cloud outbox together; duplicates never requeue.

        Returns False for an identical retry even after cloud replay cleanup.
        Refuse new receipts when the bounded ledger is full; never age out an
        identity while a rebooted B might still retry it.
        """
        self.connect()
        with self.conn:
            # Reserve the writer before capacity/dedup reads across processes.
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute(
                'SELECT digest FROM sensor_receipts WHERE identity=?', (identity,)).fetchone()
            if row is not None:
                if row[0] != digest:
                    raise ValueError('sample identity reused for different evidence')
                return False
            count = self.conn.execute('SELECT COUNT(*) FROM sensor_receipts').fetchone()[0]
            if count >= self.max_sensor_receipts:
                self.receipt_capacity_rejected += 1
                raise QueueCapacityError('sensor receipt ledger full; identities retained')
            if self.conn.execute('SELECT 1 FROM gateway_queue WHERE message_id=?', (identity,)).fetchone():
                raise ValueError('outbox identity exists without a matching receipt')
            self._enqueue(message)
            self.conn.execute('INSERT INTO sensor_receipts VALUES (?,?,?)',
                              (identity, digest, time.time()))
            self.conn.execute("INSERT INTO sensor_control_audit VALUES (?,'RECEIVED',NULL,?)",
                              (identity, time.time()))
        self.enqueued += 1
        return True

    def receipt_stats(self):
        self.connect()
        count, size = self.conn.execute(
            "SELECT COUNT(*),COALESCE(SUM(length(CAST(identity AS BLOB))+length(CAST(digest AS BLOB))+8),0) FROM sensor_receipts").fetchone()
        # Logical content bytes, not SQLite file/WAL/allocator overhead.
        return {"count": count, "logical_bytes": size, "limit": self.max_sensor_receipts,
                "free": max(0, self.max_sensor_receipts-count),
                "near_capacity": count*5 >= self.max_sensor_receipts*4,
                "capacity_rejected": self.receipt_capacity_rejected}

    def admit_result(self, message, digest):
        """One transaction commits audit receipt and cloud outbox.

        Receipts survive cloud dequeue and gateway restart. Their bounded
        ledger rejects admission at capacity rather than forget dedup history.
        """
        self.connect()
        with self.conn:
            self.conn.execute('BEGIN IMMEDIATE')
            row = self.conn.execute('SELECT digest FROM result_receipts WHERE identity=?',
                                    (message.message_id,)).fetchone()
            if row:
                if row[0] != digest:raise ValueError('result identity conflict')
                return False
            if self.conn.execute('SELECT COUNT(*) FROM result_receipts').fetchone()[0] >= self.max_result_receipts:
                raise QueueCapacityError('result receipt ledger full')
            self._enqueue(message)
            self.conn.execute('INSERT INTO result_receipts VALUES (?,?,?)',
                              (message.message_id, digest, time.time()))
        self.enqueued += 1
        return True

    def export_receipts(self):
        """Read-only archive snapshot. No retirement handshake exists with B.

        Backup is not proof a device cannot retry: this API never deletes rows.
        Keep the database (including WAL) or use SQLite backup for recovery.
        """
        self.connect()
        with self.conn:
            rows = self.conn.execute('SELECT identity,digest,received_at FROM sensor_receipts ORDER BY identity').fetchall()
        raw = json.dumps(rows, separators=(',', ':'), ensure_ascii=True)
        return {"version": 1, "receipts": rows, "sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "retirement_allowed": False}

    def sensor_audit(self, identity):
        self.connect()
        row = self.conn.execute('SELECT state,command_id,updated_at FROM sensor_control_audit WHERE identity=?', (identity,)).fetchone()
        return {"state": "LEGACY_UNTRACKED"} if row is None else dict(zip(('state','command_id','updated_at'),row))

    def audit_sensor_control(self, identity, state, command_id=None):
        """Durable progress evidence only; never used to replay control."""
        self.connect()
        with self.conn:
            cursor = self.conn.execute('UPDATE sensor_control_audit SET state=?,command_id=COALESCE(?,command_id),updated_at=? WHERE identity=?',
                                       (state, command_id, time.time(), identity))
            if cursor.rowcount != 1:
                raise ValueError('control audit requires a new durable sensor receipt')

    def audit_command_outcome(self, command_id, state):
        self.connect()
        with self.conn:
            self.conn.execute('UPDATE sensor_control_audit SET state=?,updated_at=? WHERE command_id=?',
                              (state,time.time(),command_id))

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
                "admission_rejected_normal":self.rejected_normal,"sensor_receipts":self.receipt_stats(),
                "result_receipts":{"count":self.conn.execute("SELECT COUNT(*) FROM result_receipts").fetchone()[0],
                                   "limit":self.max_result_receipts}}
