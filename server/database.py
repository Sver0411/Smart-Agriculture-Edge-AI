"""SQLite persistence for the cloud server.

Tables kept by v0.2: sensor history, gateway heartbeats, controller commands /
results, alerts, a generic log table and the ``processed_message`` dedup table
(see :mod:`server.dedup`).

Every row also stores the ``message_id`` of the upload that produced it, so any
record can be traced back to the exact message that created it.
"""

from __future__ import annotations

import sqlite3
import time
import json
import hashlib
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS sensor_data (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id     TEXT,
    gateway_id     TEXT    NOT NULL,
    sensor_node_id TEXT    NOT NULL,
    timestamp      REAL    NOT NULL,
    temperature    REAL,
    humidity       REAL,
    soil_moisture  REAL,
    light          REAL,
    health_state   TEXT    NOT NULL,
    metadata_json  TEXT,
    created_at     REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS gateway_heartbeat (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  TEXT,
    gateway_id  TEXT    NOT NULL,
    peer_id     TEXT,
    timestamp   REAL    NOT NULL,
    status      TEXT    NOT NULL,
    peer_status TEXT,
    created_at  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS controller_command (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id    TEXT,
    gateway_id    TEXT    NOT NULL,
    controller_id TEXT    NOT NULL,
    command_id    TEXT    NOT NULL,
    command_type  TEXT    NOT NULL,
    duration      REAL,
    generation    INTEGER,
    timestamp     REAL    NOT NULL,
    created_at    REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS controller_result (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id    TEXT,
    gateway_id    TEXT    NOT NULL,
    controller_id TEXT,
    command_id    TEXT    NOT NULL,
    command_type  TEXT,
    status        TEXT    NOT NULL,
    reason        TEXT,
    generation    INTEGER,
    timestamp     REAL    NOT NULL,
    created_at    REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS alert (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id     TEXT,
    gateway_id     TEXT    NOT NULL,
    sensor_node_id TEXT,
    alert_type     TEXT    NOT NULL,
    message        TEXT,
    timestamp      REAL    NOT NULL,
    created_at     REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id    TEXT    NOT NULL,
    level      TEXT    NOT NULL,
    message    TEXT    NOT NULL,
    timestamp  REAL    NOT NULL,
    created_at REAL    NOT NULL
);
"""


class Database:
    """A very thin wrapper around :mod:`sqlite3`."""

    def __init__(self, path: str = ":memory:"):
        self._transaction_depth = 0
        self.path = path
        self.conn: sqlite3.Connection | None = None

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> "Database":
        if self.conn is None:
            self.conn = sqlite3.connect(self.path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=FULL")
        return self

    def init_schema(self) -> "Database":
        self.connect()
        self.conn.executescript(SCHEMA)
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(sensor_data)")}
        if "metadata_json" not in columns:
            self.conn.execute("ALTER TABLE sensor_data ADD COLUMN metadata_json TEXT")
        alert_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(alert)")}
        if "metadata_json" not in alert_columns:
            self.conn.execute("ALTER TABLE alert ADD COLUMN metadata_json TEXT")
        heartbeat_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(gateway_heartbeat)")}
        if "metadata_json" not in heartbeat_columns:
            self.conn.execute("ALTER TABLE gateway_heartbeat ADD COLUMN metadata_json TEXT")
        self._commit()
        return self

    def close(self) -> None:
        if self.conn is not None:
            self._commit()
            self.conn.close()
            self.conn = None

    # -- writes ------------------------------------------------------------

    def load_policy(self, initial_version, initial_policy):
        """Recover the exact head. Never invent a version for an old database.

        Old schemas have no persisted publication high-water mark. They can
        keep accepting history, but policy publication requires an explicitly
        restored authoritative checkpoint (see deployment migration guide).
        """
        self.connect()
        tables = {row[0] for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'server_policy' not in tables:
            with self.conn:
                self.conn.execute('CREATE TABLE server_policy (singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL, content TEXT NOT NULL, checksum TEXT NOT NULL)')
                if not tables:
                    self._write_policy(initial_version, initial_policy, insert=True)
        row = self.conn.execute('SELECT version,content,checksum FROM server_policy WHERE singleton=1').fetchone()
        if row is None:raise ValueError('policy version unavailable: authoritative restoration required')
        version, raw, checksum = row
        from common.protocol import integer, validate_policy
        if not integer(version, 1) or hashlib.sha256(f'{version}:{raw}'.encode()).hexdigest() != checksum:
            raise ValueError('corrupt policy head; refusing version rollback')
        policy = json.loads(raw)
        if set(policy) != set(initial_policy):raise ValueError('incomplete policy head')
        return version, validate_policy({**policy, 'policy_version':version}, initial_policy)

    def _write_policy(self, version, policy, *, insert=False, expected_version=None):
        raw = json.dumps(policy, sort_keys=True, separators=(',', ':'), allow_nan=False)
        digest = hashlib.sha256(f'{version}:{raw}'.encode()).hexdigest()
        if insert:
            self.conn.execute('INSERT INTO server_policy VALUES (1,?,?,?)', (version, raw, digest))
        else:
            cursor = self.conn.execute('UPDATE server_policy SET version=?,content=?,checksum=? WHERE singleton=1 AND version=?',
                                       (version, raw, digest, expected_version))
            if cursor.rowcount != 1:raise ValueError('policy head changed or lost; reload required')

    def update_policy(self, version, policy, expected_version):
        with self.conn:
            self.conn.execute('BEGIN IMMEDIATE')
            self._write_policy(version, policy, expected_version=expected_version)

    def insert_sensor_data(
        self,
        gateway_id: str,
        sensor_node_id: str,
        record: dict,
        health_state: str = "HEALTHY",
        message_id: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO sensor_data (
                message_id, gateway_id, sensor_node_id, timestamp, temperature, humidity,
                soil_moisture, light, health_state, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                gateway_id,
                sensor_node_id,
                float(record.get("timestamp", time.time())),
                record.get("temperature"),
                record.get("humidity"),
                record.get("soil_moisture"),
                record.get("light"),
                health_state,
                json.dumps({key: record[key] for key in (
                    "node_mode", "boot_id", "sample_seq", "device_monotonic_ms",
                    "sampling", "health", "health_score", "fault_flags", "usable_for_control", "received_at",
                    "control_trust", "trusted_channels",
                    "physical_read_ok", "test_injected", "timestamp_source",
                ) if key in record}),
                time.time(),
            ),
        )
        self._commit()
        return int(cur.lastrowid)

    def insert_gateway_heartbeat(
        self,
        gateway_id: str,
        timestamp: float,
        status: str = "ONLINE",
        peer_id: str | None = None,
        peer_status: str | None = None,
        message_id: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO gateway_heartbeat (
                message_id, gateway_id, peer_id, timestamp, status, peer_status, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                gateway_id,
                peer_id,
                float(timestamp),
                status,
                peer_status,
                time.time(),
                json.dumps(metadata or {}, allow_nan=False),
            ),
        )
        self._commit()
        return int(cur.lastrowid)

    def insert_controller_command(
        self,
        gateway_id: str,
        controller_id: str,
        command_id: str,
        command_type: str,
        duration,
        timestamp: float,
        generation: int | None = None,
        message_id: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO controller_command (
                message_id, gateway_id, controller_id, command_id, command_type, duration,
                generation, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                gateway_id,
                controller_id,
                command_id,
                command_type,
                duration,
                generation,
                float(timestamp),
                time.time(),
            ),
        )
        self._commit()
        return int(cur.lastrowid)

    def insert_controller_result(
        self,
        gateway_id: str,
        command_id: str,
        status: str,
        timestamp: float,
        controller_id: str | None = None,
        command_type: str | None = None,
        reason: str | None = None,
        generation: int | None = None,
        message_id: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO controller_result (
                message_id, gateway_id, controller_id, command_id, command_type, status,
                reason, generation, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                gateway_id,
                controller_id,
                command_id,
                command_type,
                status,
                reason,
                generation,
                float(timestamp),
                time.time(),
            ),
        )
        self._commit()
        return int(cur.lastrowid)

    def insert_alert(
        self,
        gateway_id: str,
        timestamp: float,
        alert_type: str,
        message: str = "",
        sensor_node_id: str | None = None,
        message_id: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO alert (
                message_id, gateway_id, sensor_node_id, alert_type, message, timestamp, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (message_id, gateway_id, sensor_node_id, alert_type, message, float(timestamp), time.time(), json.dumps(metadata or {},allow_nan=False)),
        )
        self._commit()
        return int(cur.lastrowid)

    def insert_log(self, node_id: str, level: str, message: str, timestamp: float | None = None) -> int:
        now = time.time() if timestamp is None else timestamp
        cur = self.conn.execute(
            "INSERT INTO log (node_id, level, message, timestamp, created_at) VALUES (?, ?, ?, ?, ?)",
            (node_id, level, message, now, time.time()),
        )
        self._commit()
        return int(cur.lastrowid)

    # -- reads -------------------------------------------------------------

    def count(self, table: str) -> int:
        allowed = {
            "sensor_data",
            "gateway_heartbeat",
            "controller_command",
            "controller_result",
            "alert",
            "log",
            "processed_message",
        }
        if table not in allowed:
            raise ValueError(f"unknown table: {table!r}")
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def recent_sensor_data(self, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM sensor_data ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(row) for row in rows]

    def recent_controller_results(self, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM controller_result ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(row) for row in rows]


    def _commit(self):
        if not self._transaction_depth:self.conn.commit()

    @contextmanager
    def transaction(self):
        self._transaction_depth += 1
        try:
            yield
        except Exception:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()
        finally:
            self._transaction_depth -= 1
