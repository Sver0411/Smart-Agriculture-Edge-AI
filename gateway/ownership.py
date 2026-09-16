"""Gateway ownership: which gateway may drive which node, and at which epoch.

v0.1 only *detected* that the peer gateway had gone quiet.  v0.2 adds the
takeover itself, protected by a monotonically increasing ``generation``
(sometimes called an epoch):

* the gateway that owns a node stamps its commands with its current generation;
* a controller remembers the highest generation it has accepted and refuses
  anything older with ``STALE_GENERATION``.

That is what keeps a deposed gateway - one that is still running but has been
replaced - from acting on the same actuator as its successor.  No Raft, no
Paxos, no etcd: heartbeat + timeout + ownership + generation is enough for two
gateways in one field.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import config  # noqa: E402

__all__ = ["OwnershipManager"]


class OwnershipManager:
    """Ownership state of a single gateway."""

    def __init__(
        self,
        gateway_id: str,
        peer_id: str,
        registry,
        generation: int = config.INITIAL_GENERATION,
    ):
        self.gateway_id = gateway_id
        self.peer_id = peer_id
        self.registry = registry

        self.generation = generation
        self.role = config.ACTIVE  # ACTIVE or STANDBY
        self.health = config.ONLINE  # ONLINE or OFFLINE

        # what we last heard from the peer
        self.peer_health = config.UNKNOWN
        self.peer_generation = 0

    # -- owning ------------------------------------------------------------

    def claim(self, node_ids, node_type: str = config.SENSOR) -> int:
        """Take (or refresh) ownership of ``node_ids`` at the current epoch."""
        for node_id in node_ids:
            self.registry.upsert(
                node_id=node_id,
                node_type=node_type,
                owner_gateway=self.gateway_id,
                generation=self.generation,
            )
        return self.generation

    def takeover(self, node_ids, node_type: str = config.SENSOR) -> int:
        """Move ``node_ids`` away from the peer and bump the epoch."""
        self.generation = max(self.generation, self.peer_generation) + 1
        self.role = config.ACTIVE
        for node_id in node_ids:
            known = self.registry.get(node_id)
            self.registry.upsert(
                node_id=node_id,
                node_type=known.node_type if known else node_type,
                owner_gateway=self.gateway_id,
                generation=self.generation,
            )
        return self.generation

    def owns(self, node_id: str) -> bool:
        entry = self.registry.get(node_id)
        return entry is not None and entry.owner_gateway == self.gateway_id

    def may_control(self, node_id: str) -> bool:
        """``True`` when this gateway is allowed to drive ``node_id`` now."""
        return self.role == config.ACTIVE and self.owns(node_id)

    # -- peer observation --------------------------------------------------

    def observe_peer(self, health: str, generation: int | None = None) -> str:
        """Record what the peer told us and return our resulting role.

        A recovering gateway whose epoch is behind the peer gives up control
        instead of fighting for it: it becomes ``STANDBY``.  Automatic failback
        is deliberately not implemented.  A peer that is simply *offline* never
        demotes us - that case is handled by :meth:`OwnershipManager.takeover`.
        """
        self.peer_health = health
        if generation is not None:
            self.peer_generation = max(self.peer_generation, int(generation))

        if health == config.OFFLINE:
            return self.role
        if self.peer_generation > self.generation:
            self.role = config.STANDBY
        else:
            self.role = config.ACTIVE
        return self.role

    def as_dict(self) -> dict:
        return {
            "gateway_id": self.gateway_id,
            "role": self.role,
            "health": self.health,
            "generation": self.generation,
            "peer_id": self.peer_id,
            "peer_health": self.peer_health,
            "peer_generation": self.peer_generation,
        }
