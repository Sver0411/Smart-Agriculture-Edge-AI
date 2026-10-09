"""Force the PR #7 startup interleavings without changing failure windows."""
import asyncio
import time

import pytest

from common import config
from common.messages import HEARTBEAT, Message, transport_interceptor
from gateway.gateway import Gateway


@pytest.mark.parametrize('mode', ['lab', 'hmac'])
def test_recovery_reconciles_epoch_in_delayed_handshake_before_timeout(tmp_path, mode):
    async def scenario():
        key = b'p' * 32 if mode == 'hmac' else None
        path = str(tmp_path / 'a1.db')
        before = Gateway('A1', queue_path=path)
        before.offline_queue.close()
        recovered = Gateway('A1', queue_path=path, heartbeat_interval=.01,
                            heartbeat_timeout=.6, peer_security_mode=mode, peer_key=key)
        survivor = Gateway('A2', port=0, peer_port=0, heartbeat_interval=.01,
                           heartbeat_timeout=10, peer_security_mode=mode, peer_key=key)
        survivor._takeover()
        frames = []

        async def delay_ack(writer, message):
            if message.payload.get('peer_handshake') == 'AUTH_ACK':
                # No reverse link exists yet: the old implementation would
                # time out after this successful handshake and claim epoch 2.
                await asyncio.sleep(.7)
            return False

        async def first_upload(message):
            frames.append(message.payload)
            recovered._stopping = True

        recovered._submit_upload = first_upload
        token = transport_interceptor.set(delay_ack)
        try:
            await survivor.start()
            recovered.peer_port = survivor._server.sockets[0].getsockname()[1]
            recovered.peer_started_at = time.monotonic()
            await asyncio.wait_for(recovered.task_heartbeat(), 2)
            assert recovered.ownership.generation == 1
            assert recovered.ownership.role == config.STANDBY
            assert recovered.peer_last_seen is not None
            assert not recovered._recovery_pending
            assert frames[0]['generation'] == 1
            assert frames[0]['role'] == config.STANDBY
            assert frames[0]['ownership'] == {}
            assert recovered.metrics.get('failovers') == 0
            assert survivor.ownership.role == config.ACTIVE
            for node in ('B1', 'C1', 'B2', 'C2'):
                assert recovered.registry.get(node).owner_gateway == 'A2'
                assert recovered.registry.get(node).generation == 2
                assert survivor.ownership.may_control(node)
        finally:
            transport_interceptor.reset(token)
            await recovered.stop()
            await survivor.stop()
    asyncio.run(scenario())


def test_equal_epoch_active_overlap_fails_closed_and_cannot_resume(tmp_path):
    path = str(tmp_path / 'a1.db')
    previous = Gateway('A1', queue_path=path)
    previous._takeover()
    previous.offline_queue.close()
    recovered = Gateway('A1', queue_path=path)
    peer = Message(type=HEARTBEAT, source='A2', target='A1', payload={
        'generation': 2, 'role': config.ACTIVE,
        'ownership': {node: {'owner_gateway': 'A2', 'generation': 2}
                      for node in ('B1', 'C1', 'B2', 'C2')}})
    try:
        assert recovered._on_peer_heartbeat(peer)
        assert recovered.ownership.role == config.STANDBY
        assert not recovered._recovery_pending
        assert all(not recovered.ownership.may_control(node)
                   for node in ('B1', 'C1', 'B2', 'C2'))
        assert recovered._on_peer_heartbeat(peer)
        assert recovered.ownership.role == config.STANDBY
        assert recovered.ownership.generation == 2
    finally:
        recovered.offline_queue.close()


@pytest.mark.parametrize('peer_role,expected_role', [
    (config.ACTIVE, config.STANDBY), (config.STANDBY, config.ACTIVE)])
def test_equal_epoch_overlap_only_active_peer_can_demote_incumbent(peer_role, expected_role):
    gateway = Gateway('A2')
    gateway._takeover()
    try:
        assert gateway._on_peer_heartbeat(Message(type=HEARTBEAT, source='A1', target='A2',
            payload={'generation': 2, 'role': peer_role, 'ownership': {
                node: {'owner_gateway': 'A1', 'generation': 2}
                for node in ('B1', 'C1')}}))
        assert gateway.ownership.role == expected_role
        # Equal-epoch evidence cannot transfer ownership, even when demoting.
        assert gateway.registry.get('B1').owner_gateway == 'A2'
    finally:
        gateway.offline_queue.close()


@pytest.mark.parametrize('bad', ['signature', 'state', 'missing_state'])
def test_handshake_rejects_untrusted_or_invalid_epoch_without_adopting(tmp_path, bad):
    async def scenario():
        from gateway import peer_security
        key = b'p' * 32
        survivor = Gateway('A2', port=0, peer_port=0, heartbeat_timeout=10,
                           peer_security_mode='hmac', peer_key=key)
        survivor._takeover()
        recovered = Gateway('A1', peer_security_mode='hmac', peer_key=key)
        async def tamper(writer, message):
            if message.payload.get('peer_handshake') == 'AUTH_ACK':
                if bad == 'signature':
                    message.payload['ownership_state']['generation'] = 20
                elif bad == 'state':
                    message.payload['ownership_state']['role'] = 'INVALID'
                else:
                    del message.payload['ownership_state']
                if bad != 'signature':
                    unsigned = {k: v for k, v in message.payload.items() if k != 'server_auth'}
                    message.payload['server_auth'] = peer_security.tag(key, unsigned)
            return False
        token = transport_interceptor.set(tamper)
        try:
            await survivor.start()
            recovered.peer_port = survivor._server.sockets[0].getsockname()[1]
            await recovered._connect_peer()
            assert recovered.peer_writer is None
            assert recovered.peer_last_seen is None
            assert recovered.ownership.peer_generation == 0
            assert recovered.ownership.generation == 1
            assert recovered.registry.get('B1').owner_gateway == 'A1'
        finally:
            transport_interceptor.reset(token)
            await recovered.stop()
            await survivor.stop()
    asyncio.run(scenario())


def test_unreachable_peer_still_allows_formal_recovery_timeout(tmp_path):
    path = str(tmp_path / 'a1.db')
    original = Gateway('A1', queue_path=path)
    original.offline_queue.close()
    recovered = Gateway('A1', queue_path=path, heartbeat_timeout=.6)
    try:
        recovered.peer_started_at = 0
        assert recovered.evaluate_peer_status(.61) == config.OFFLINE
        assert not recovered._recovery_pending
        assert recovered.ownership.generation == 2
        assert recovered.ownership.role == config.ACTIVE
        assert all(recovered.ownership.may_control(node)
                   for node in ('B1', 'C1', 'B2', 'C2'))
    finally:
        recovered.offline_queue.close()
