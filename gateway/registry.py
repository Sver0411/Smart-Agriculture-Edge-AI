"""Lightweight node registry maintained by every gateway (v0.2).

There is no external database and no consensus cluster: each gateway keeps an
in-memory table of the nodes it knows about.  The interesting field is
``owner_gateway`` together with ``generation`` - they decide which gateway is
allowed to drive a node right now.
"""

from __future__ import annotations

import pathlib
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import config  # noqa: E402

__all__ = ["NodeEntry", "NodeRegistry"]


@dataclass
class NodeEntry:
    """One row of the registry."""

    node_id: str
    node_type: str
    owner_gateway: str
    status: str = config.OFFLINE
    last_seen: float = field(default_factory=time.time)
    generation: int = config.INITIAL_GENERATION

    def as_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "owner_gateway": self.owner_gateway,
            "status": self.status,
            "last_seen": self.last_seen,
            "generation": self.generation,
        }


class NodeRegistry:
    """``node_id -> NodeEntry`` with ownership helpers."""

    def __init__(self):
        self.entries: dict[str, NodeEntry] = {}

    # -- basic operations --------------------------------------------------

    def upsert(
        self,
        node_id: str,
        node_type: str,
        owner_gateway: str,
        generation: int = config.INITIAL_GENERATION,
        timestamp: float | None = None,
        status: str = config.ONLINE,
    ) -> NodeEntry:
        entry = self.entries.get(node_id)
        if entry is None:
            entry = NodeEntry(node_id=node_id, node_type=node_type, owner_gateway=owner_gateway)
            self.entries[node_id] = entry

        entry.node_type = node_type
        entry.owner_gateway = owner_gateway
        entry.generation = generation
        entry.status = status
        entry.last_seen = time.time() if timestamp is None else timestamp
        return entry

    def get(self, node_id: str) -> NodeEntry | None:
        return self.entries.get(node_id)

    def touch(self, node_id: str, timestamp: float | None = None) -> None:
        entry = self.entries.get(node_id)
        if entry is not None:
            entry.last_seen = time.time() if timestamp is None else timestamp
            entry.status = config.ONLINE

    def set_status(self, node_id: str, status: str) -> None:
        entry = self.entries.get(node_id)
        if entry is not None:
            entry.status = status

    def __len__(self) -> int:
        return len(self.entries)

    # -- ownership ---------------------------------------------------------

    def owned_by(self, gateway_id: str) -> list[NodeEntry]:
        return [entry for entry in self.entries.values() if entry.owner_gateway == gateway_id]

    def transfer(self, node_ids, new_owner: str, generation: int) -> list[NodeEntry]:
        """Move ownership of ``node_ids`` to ``new_owner`` at ``generation``."""
        moved = []
        for node_id in node_ids:
            entry = self.entries.get(node_id)
            if entry is None:
                continue
            entry.owner_gateway = new_owner
            entry.generation = generation
            moved.append(entry)
        return moved

    def generation_of(self, node_id: str) -> int:
        entry = self.entries.get(node_id)
        return entry.generation if entry else config.INITIAL_GENERATION

    # -- health ------------------------------------------------------------

    def expire(self, now: float | None = None, timeout: float = config.NODE_TIMEOUT) -> list[NodeEntry]:
        """Mark silent nodes OFFLINE and return the ones that just changed."""
        now = time.time() if now is None else now
        expired = []
        for entry in self.entries.values():
            if entry.status != config.OFFLINE and now - entry.last_seen > timeout:
                entry.status = config.OFFLINE
                expired.append(entry)
        return expired

    # -- introspection -----------------------------------------------------

    def snapshot(self) -> dict:
        return {node_id: entry.as_dict() for node_id, entry in self.entries.items()}
