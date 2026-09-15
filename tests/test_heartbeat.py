"""Gateway heartbeat: A1 and A2 watch each other."""

from common import config
from gateway.gateway import OFFLINE, ONLINE, Gateway


def test_peer_is_marked_offline_after_the_timeout():
    gateway = Gateway("A1")
    gateway.peer_last_seen = 1_000.0

    assert gateway.evaluate_peer_status(now=1_000.0 + config.HEARTBEAT_TIMEOUT) == ONLINE
    assert gateway.evaluate_peer_status(now=1_000.0 + config.HEARTBEAT_TIMEOUT + 0.5) == OFFLINE
    assert gateway.peer_status == OFFLINE


def test_peer_stays_online_while_heartbeats_keep_arriving():
    gateway = Gateway("A2")
    gateway.peer_last_seen = 1_000.0

    for offset in (config.HEARTBEAT_INTERVAL, 2 * config.HEARTBEAT_INTERVAL, 3 * config.HEARTBEAT_INTERVAL):
        gateway.peer_last_seen = 1_000.0 + offset
        assert gateway.evaluate_peer_status(now=1_000.0 + offset) == ONLINE

    assert gateway.peer_status == ONLINE
