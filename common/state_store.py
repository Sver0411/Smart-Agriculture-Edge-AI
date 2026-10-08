"""Small host checkpoint interface. ESP32 NVS is a future backend.

Only policy may fall back to a previous slot. A corrupt epoch must fail closed:
falling back could forget a higher generation already published to the field.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from contextlib import closing

class StateError(ValueError):
    pass

class StateStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute('CREATE TABLE IF NOT EXISTS checkpoints (namespace TEXT, slot INTEGER, payload TEXT NOT NULL, checksum TEXT NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(namespace,slot))')

    @staticmethod
    def digest(raw):
        return hashlib.sha256(raw.encode()).hexdigest()

    def load(self, namespace, *, validator=None, allow_previous=False):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            rows = conn.execute('SELECT slot, payload, checksum, updated_at FROM checkpoints WHERE namespace=? ORDER BY slot', (namespace,)).fetchall()
        if not rows:return None
        # Losing slot 0 must not silently promote a stale epoch/intent window.
        # Only policy explicitly opts into recovery from the previous slot.
        candidates = [row for row in rows if row[0] in ((0, 1) if allow_previous else (0,))]
        for slot, raw, checksum, updated_at in candidates:
            try:
                if checksum != self.digest(raw):raise StateError('checksum mismatch')
                value = json.loads(raw)
                if validator:validator(value)
                return value
            except (ValueError, TypeError, KeyError, OverflowError):
                continue
        raise StateError(f'no valid checkpoint for {namespace}')

    def save(self, namespace, value):
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute('PRAGMA synchronous=FULL')
            current = conn.execute('SELECT payload, checksum, updated_at FROM checkpoints WHERE namespace=? AND slot=0', (namespace,)).fetchone()
            if current and current[0] == raw and current[1] == self.digest(raw):return
            # Never overwrite the previous good slot with corrupt current bytes.
            if current and self.digest(current[0]) == current[1]:
                conn.execute('INSERT OR REPLACE INTO checkpoints VALUES (?,1,?,?,?)', (namespace,*current))
            conn.execute('INSERT OR REPLACE INTO checkpoints VALUES (?,0,?,?,?)', (namespace,raw,self.digest(raw),time.time()))
