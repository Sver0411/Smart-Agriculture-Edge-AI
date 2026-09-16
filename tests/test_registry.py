"""Node registry and gateway ownership - the two pieces that stop split brain.

The tests here are deliberately pure: no sockets, no asyncio.  Both classes are
plain state machines, so the interesting properties (monotonic epoch, refusing
an older epoch, no automatic failback) can be checked directly.
"""

import time

import pytest

from common import config
from gateway.ownership import OwnershipManager
from gateway.registry import NodeRegistry


@pytest.fixture
def registry() -> NodeRegistry:
    reg = NodeRegistry()
    reg.upsert("B1", config.SENSOR, "A1", generation=1)
    reg.upsert("C1", config.CONTROLLER, "A1", generation=1)
    reg.upsert("B2", config.SENSOR, "A2", generation=1)
    reg.upsert("C2", config.CONTROLLER, "A2", generation=1)
    return reg


# --------------------------------------------------------------------------
# NodeRegistry
# --------------------------------------------------------------------------


def test_registry_upsert_creates_then_updates(registry):
    assert len(registry) == 4
    registry.upsert("B1", config.SENSOR, "A2", generation=7)
    assert registry.get("B1").owner_gateway == "A2"
    assert registry.get("B1").generation == 7
    assert len(registry) == 4  # updated, not duplicated


def test_registry_owned_by_filters_on_owner(registry):
    assert sorted(e.node_id for e in registry.owned_by("A1")) == ["B1", "C1"]
    assert sorted(e.node_id for e in registry.owned_by("A2")) == ["B2", "C2"]
    assert registry.owned_by("A3") == []


def test_registry_transfer_moves_nodes_and_epoch(registry):
    moved = registry.transfer(["B1", "C1"], "A2", 2)
    assert sorted(e.node_id for e in moved) == ["B1", "C1"]
    assert registry.get("B1").owner_gateway == "A2"
    assert registry.get("B1").generation == 2
    # untouched nodes keep their old epoch
    assert registry.get("B2").generation == 1


def test_registry_transfer_ignores_unknown_nodes(registry):
    assert registry.transfer(["B9"], "A2", 5) == []


def test_registry_generation_of_unknown_node_is_the_initial_one(registry):
    assert registry.generation_of("B1") == 1
    assert registry.generation_of("nope") == config.INITIAL_GENERATION


def test_registry_expire_marks_silent_nodes_offline(registry):
    now = time.time()
    registry.touch("B1", now)
    registry.touch("C1", now - 100.0)

    expired = registry.expire(now=now, timeout=config.NODE_TIMEOUT)
    assert [e.node_id for e in expired] == ["C1"]
    assert registry.get("C1").status == config.OFFLINE
    assert registry.get("B1").status == config.ONLINE


def test_registry_expire_reports_a_node_only_once(registry):
    now = time.time()
    registry.touch("B1", now - 100.0)
    assert [e.node_id for e in registry.expire(now=now)] == ["B1"]
    assert registry.expire(now=now) == []


def test_registry_snapshot_is_serialisable(registry):
    snapshot = registry.snapshot()
    assert set(snapshot) == {"B1", "B2", "C1", "C2"}
    assert snapshot["B1"]["owner_gateway"] == "A1"
    assert snapshot["B1"]["node_type"] == config.SENSOR


# --------------------------------------------------------------------------
# OwnershipManager
# --------------------------------------------------------------------------


def test_claim_registers_nodes_at_the_current_epoch(registry):
    owner = OwnershipManager("A1", "A2", registry)
    assert owner.claim(["B1", "C1"]) == 1
    assert registry.generation_of("B1") == 1
    assert owner.owns("B1")
    assert not owner.owns("B2")


def test_takeover_bumps_the_epoch_above_the_peer(registry):
    a2 = OwnershipManager("A2", "A1", registry)
    a2.observe_peer(config.ONLINE, generation=4)  # peer claims epoch 4
    assert a2.takeover(["B1", "C1"]) == 5
    assert a2.generation == 5
    assert registry.get("B1").owner_gateway == "A2"
    assert registry.get("B1").generation == 5


def test_takeover_without_nodes_still_bumps_the_epoch(registry):
    """A deposed gateway must lose authority even if it owns nothing.

    Nodes that fell back to us on their own are already registered; the epoch
    still has to move so that commands the dead peer may still emit are stale.
    """
    a2 = OwnershipManager("A2", "A1", registry)
    assert a2.takeover([]) == 2
    assert a2.generation == 2
    assert a2.role == config.ACTIVE


def test_takeover_keeps_the_known_node_type(registry):
    a2 = OwnershipManager("A2", "A1", registry)
    a2.takeover(["C1"])
    assert registry.get("C1").node_type == config.CONTROLLER


def test_may_control_needs_both_role_and_ownership(registry):
    a2 = OwnershipManager("A2", "A1", registry)
    assert not a2.may_control("B1")  # still owned by A1

    a2.takeover(["B1", "C1"])
    assert a2.may_control("B1")

    a2.role = config.STANDBY
    assert not a2.may_control("B1")  # owned, but demoted

    a2.role = config.ACTIVE
    assert not a2.may_control("B9")  # unknown node


def test_observing_a_newer_peer_demotes_us_to_standby(registry):
    """This is the no-failback rule: the recovering gateway stays STANDBY."""
    a1 = OwnershipManager("A1", "A2", registry, generation=1)
    assert a1.role == config.ACTIVE
    assert a1.observe_peer(config.ONLINE, generation=2) == config.STANDBY
    assert a1.role == config.STANDBY
    assert not a1.may_control("B1")


def test_an_offline_peer_never_demotes_us(registry):
    a1 = OwnershipManager("A1", "A2", registry, generation=3)
    assert a1.observe_peer(config.OFFLINE, generation=1) == config.ACTIVE
    assert a1.role == config.ACTIVE


def test_a_peer_at_the_same_epoch_does_not_demote_us(registry):
    a1 = OwnershipManager("A1", "A2", registry, generation=3)
    assert a1.observe_peer(config.ONLINE, generation=3) == config.ACTIVE


def test_peer_generation_is_monotonic(registry):
    a1 = OwnershipManager("A1", "A2", registry, generation=5)
    a1.observe_peer(config.ONLINE, generation=9)
    a1.observe_peer(config.ONLINE, generation=2)  # stale news must not lower it
    assert a1.peer_generation == 9
    assert a1.role == config.STANDBY


def test_as_dict_exposes_the_ownership_state(registry):
    a1 = OwnershipManager("A1", "A2", registry)
    state = a1.as_dict()
    assert state["gateway_id"] == "A1"
    assert state["peer_id"] == "A2"
    assert state["generation"] == 1
    assert state["role"] == config.ACTIVE
