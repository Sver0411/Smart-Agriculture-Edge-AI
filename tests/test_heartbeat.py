"""Gateway heartbeat, watchdog and node expiry."""

from common import config
from gateway.gateway import Gateway


def test_peer_is_marked_offline_after_the_timeout():
    gateway = Gateway("A1")
    gateway.peer_last_seen = 1_000.0

    assert gateway.evaluate_peer_status(now=1_000.0 + config.HEARTBEAT_TIMEOUT) == config.ONLINE
    assert gateway.evaluate_peer_status(now=1_000.0 + config.HEARTBEAT_TIMEOUT + 0.5) == config.OFFLINE
    assert gateway.peer_status == config.OFFLINE


def test_peer_stays_online_while_heartbeats_keep_arriving():
    gateway = Gateway("A2")
    gateway.peer_last_seen = 1_000.0

    for offset in (config.HEARTBEAT_INTERVAL, 2 * config.HEARTBEAT_INTERVAL, 3 * config.HEARTBEAT_INTERVAL):
        gateway.peer_last_seen = 1_000.0 + offset
        assert gateway.evaluate_peer_status(now=1_000.0 + offset) == config.ONLINE

    assert gateway.peer_status == config.ONLINE


def test_registry_entries_of_silent_nodes_expire():
    gateway = Gateway("A1")
    gateway.registry.upsert("B1", config.SENSOR, "A1", timestamp=1_000.0, status=config.ONLINE)

    assert gateway.registry.expire(now=1_000.0 + config.NODE_TIMEOUT - 1) == []
    expired = gateway.registry.expire(now=1_000.0 + config.NODE_TIMEOUT + 1)

    assert [entry.node_id for entry in expired] == ["B1"]
    assert gateway.registry.get("B1").status == config.OFFLINE
