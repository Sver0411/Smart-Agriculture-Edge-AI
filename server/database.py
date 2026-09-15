"""SQLite persistence for the cloud server.

Only the tables v0.1 needs are created: sensor history, gateway heartbeats,
controller commands / results, alerts and a generic log table.
"""

from __future__ import annotations

import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS sensor_data (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    gateway_id     TEXT    NOT NULL,
    sensor_node_id TEXT    NOT NULL,
    timestamp      REAL    NOT NULL,
    temperature    REAL,
    humidity       REAL,
    soil_moisture  REAL,
    light          REAL,
    health_state   TEXT    NOT NULL,
    created_at     REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS gateway_heartbeat (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    gateway_id TEXT    NOT NULL,
    peer_id    TEXT,
    timestamp  REAL    NOT NULL,
    status     TEXT    NOT NULL,
    peer_status TEXT,
    created_at REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS controller_command (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    gateway_id    TEXT    NOT NULL,
    controller_id TEXT    NOT NULL,
    command_id    TEXT    NOT NULL,
    command_type  TEXT    NOT NULL,
    duration      REAL,
    timestamp     REAL    NOT NULL,
    created_at    REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS controller_result (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    gateway_id    TEXT    NOT NULL,
    controller_id TEXT,
    command_id    TEXT    NOT NULL,
    command_type  TEXT,
    status        TEXT    NOT NULL,
    reason        TEXT,
    timestamp     REAL    NOT NULL,
    created_at    REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS alert (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
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
        self.path = path
        self.conn: sqlite3.Connection | None = None

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> "Database":
        if self.conn is None:
            self.conn = sqlite3.connect(self.path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
        return self

    def init_schema(self) -> "Database":
        self.connect()
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        return self

    def close(self) -> None:
        if self.conn is not None:
            self.conn.commit()
            self.conn.close()
            self.conn = None

    # -- writes ------------------------------------------------------------

    def insert_sensor_data(
        self,
        gateway_id: str,
        sensor_node_id: str,
        record: dict,
        health_state: str = "HEALTHY",
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO sensor_data (
                gateway_id, sensor_node_id, timestamp, temperature, humidity,
                soil_moisture, light, health_state, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                gateway_id,
                sensor_node_id,
                float(record.get("timestamp", time.time())),
                record.get("temperature"),
                record.get("humidity"),
                record.get("soil_moisture"),
                record.get("light"),
                health_state,
                time.time(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def insert_gateway_heartbeat(
        self,
        gateway_id: str,
        timestamp: float,
        status: str = "ONLINE",
        peer_id: str | None = None,
        peer_status: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO gateway_heartbeat (
                gateway_id, peer_id, timestamp, status, peer_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (gateway_id, peer_id, float(timestamp), status, peer_status, time.time()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def insert_controller_command(
        self,
        gateway_id: str,
        controller_id: str,
        command_id: str,
        command_type: str,
        duration,
        timestamp: float,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO controller_command (
                gateway_id, controller_id, command_id, command_type, duration,
                timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                gateway_id,
                controller_id,
                command_id,
                command_type,
                duration,
                float(timestamp),
                time.time(),
            ),
        )
        self.conn.commit()
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
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO controller_result (
                gateway_id, controller_id, command_id, command_type, status,
                reason, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                gateway_id,
                controller_id,
                command_id,
                command_type,
                status,
                reason,
                float(timestamp),
                time.time(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def insert_alert(
        self,
        gateway_id: str,
        timestamp: float,
        alert_type: str,
        message: str = "",
        sensor_node_id: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO alert (
                gateway_id, sensor_node_id, alert_type, message, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (gateway_id, sensor_node_id, alert_type, message, float(timestamp), time.time()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def insert_log(self, node_id: str, level: str, message: str, timestamp: float | None = None) -> int:
        now = time.time() if timestamp is None else timestamp
        cur = self.conn.execute(
            "INSERT INTO log (node_id, level, message, timestamp, created_at) VALUES (?, ?, ?, ?, ?)",
            (node_id, level, message, now, time.time()),
        )
        self.conn.commit()
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
