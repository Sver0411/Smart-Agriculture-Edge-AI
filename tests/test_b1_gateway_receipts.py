"""B→A durable receipt, reboot and lost-ACK fault injection."""
import asyncio
import pytest
from common.messages import Message, SENSOR_DATA, PERSISTED_ACK
from gateway.gateway import Gateway
from gateway.offline_queue import OfflineQueue, QueueCapacityError


def sample(seq=1, *, boot='device-boot', kind=SENSOR_DATA):
    sample_id = f'B1-{boot}-{seq:08x}'
    return Message(type=kind, source='B1', target='A1', message_id=sample_id + '-S',
                   sequence=seq, payload={
                       'node_mode': 'physical', 'boot_id': boot, 'sample_seq': seq,
                       'sample_id': sample_id, 'delivery_contract': 'gateway-durable-v1',
                       'importance': 'HIGH', 'policy_version': 'lab-v1',
                       'device_monotonic_ms': 100, 'delivery_age_ms': 0,
                       'data': {'temperature': 25, 'humidity': 60},
                       'health_state': 'HEALTHY'})


def test_ack_after_commit_lost_ack_retry_and_gateway_restart(tmp_path, monkeypatch):
    async def run():
        path = str(tmp_path/'queue.db')
        g = Gateway('A1', queue_path=path)
        writer = object(); g.connections['B1'] = writer
        receipts = []
        async def send(w, m):
            if m.type == PERSISTED_ACK:
                disk = OfflineQueue(path).connect()
                assert disk.count() == (1 if not receipts else 0)
                disk.close()
                receipts.append(m)
        monkeypatch.setattr('gateway.gateway.send_message', send)
        await g._process_sensor_message(sample())
        assert len(receipts) == 1
        assert receipts[0].payload['scope'] == 'GATEWAY_OUTBOX'
        assert receipts[0].payload['ack_message_id'] == sample().message_id
        # Simulate cloud ACK cleanup before B has received the gateway ACK.
        row = g.offline_queue.peek()[0][0]; g.offline_queue.delete(row)
        g.offline_queue.close()
        g = Gateway('A1', queue_path=path); g.connections['B1'] = writer
        await g._process_sensor_message(sample())
        assert len(receipts) == 2 and g.offline_queue.count() == 0
        assert g.metrics.get('sensor_messages') == 0
        g.offline_queue.close()
    asyncio.run(run())


def test_capacity_or_storage_failure_never_acknowledges(tmp_path, monkeypatch):
    async def run():
        g = Gateway('A1', queue_path=str(tmp_path/'queue.db'))
        g.connections['B1'] = object()
        sent = []
        async def send(w, m): sent.append(m)
        monkeypatch.setattr('gateway.gateway.send_message', send)
        def fail(*args, **kwargs): raise QueueCapacityError('full')
        monkeypatch.setattr(g.offline_queue, 'admit_sensor', fail, raising=False)
        await g._process_sensor_message(sample())
        assert not sent and g.command_queue.empty()
        assert g.metrics.get('sensor_durable_rejected') == 1
        g.offline_queue.close()
    asyncio.run(run())


@pytest.mark.parametrize('change', ['message_id', 'sample_id', 'sample_seq'])
def test_invalid_identity_is_not_acked(change, tmp_path, monkeypatch):
    async def run():
        g = Gateway('A1', queue_path=str(tmp_path/'queue.db')); g.connections['B1'] = object()
        sent = []
        async def send(w, m): sent.append(m)
        monkeypatch.setattr('gateway.gateway.send_message', send)
        m = sample()
        if change == 'message_id': m.message_id = 'new-id-on-retry'
        else: m.payload[change] = 'bad'
        await g._process_sensor_message(m)
        assert not sent and g.offline_queue.count() == 0
        g.offline_queue.close()
    asyncio.run(run())


def test_identity_content_conflict_receipt_limit_and_rollback(tmp_path):
    from gateway.sensor_delivery import identity_and_digest
    q = OfflineQueue(str(tmp_path/'queue.db'), max_sensor_receipts=1).connect()
    m = sample(); identity, digest = identity_and_digest(m)
    # A trigger aborts *after* queue insertion. Neither receipt nor queue survives.
    q.conn.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON sensor_receipts BEGIN SELECT RAISE(ABORT,'injected disk failure'); END")
    import sqlite3
    with pytest.raises(sqlite3.Error): q.admit_sensor(m, identity, digest)
    assert q.count() == q.conn.execute('SELECT COUNT(*) FROM sensor_receipts').fetchone()[0] == 0
    assert q.enqueued == 0
    q.conn.execute('DROP TRIGGER fail_receipt')
    assert q.admit_sensor(m, identity, digest)
    assert not q.admit_sensor(m, identity, digest)
    with pytest.raises(ValueError): q.admit_sensor(m, identity, 'changed-evidence')
    m = sample(2); identity, digest = identity_and_digest(m)
    with pytest.raises(QueueCapacityError): q.admit_sensor(m, identity, digest)
    assert q.count() == 1
    q.close()


def test_reordered_data_after_restart_is_history_not_control(tmp_path, monkeypatch):
    async def run():
        path = str(tmp_path/'queue.db')
        async def send(w, m): pass
        monkeypatch.setattr('gateway.gateway.send_message', send)
        g = Gateway('A1', queue_path=path); g.connections['B1'] = object()
        g.sensor_boots['B1'] = 'device-boot'
        await g._process_sensor_message(sample(5))
        g.offline_queue.close()
        g = Gateway('A1', queue_path=path); g.connections['B1'] = object()
        g.sensor_boots['B1'] = 'device-boot'
        old = sample(4); old.payload['data']['temperature'] = 36
        await g._process_sensor_message(old)
        assert g.command_queue.empty() and g.metrics.get('reordered_or_duplicate_samples') == 1
        assert g.offline_queue.count() == 2
        assert not g.offline_queue.peek()[1][1].payload['record']['usable_for_control']
        g.offline_queue.close()
    asyncio.run(run())


@pytest.mark.parametrize('boot,age', [('older-boot', 0), ('device-boot', None), ('device-boot', 6000)])
def test_old_buffer_cannot_trigger_control(boot, age, tmp_path, monkeypatch):
    async def run():
        async def send(w, m): pass
        monkeypatch.setattr('gateway.gateway.send_message', send)
        g = Gateway('A1', queue_path=str(tmp_path/'queue.db')); g.connections['B1'] = object()
        g.sensor_boots['B1'] = 'device-boot'
        m = sample(boot=boot); m.payload['delivery_age_ms'] = age
        m.payload['data']['temperature'] = 36
        await g._process_sensor_message(m)
        assert g.command_queue.empty() and g.offline_queue.count() == 1
        g.offline_queue.close()
    asyncio.run(run())


def test_memory_only_gateway_does_not_claim_durable_ack(monkeypatch):
    async def run():
        async def send(w, m): pytest.fail('RAM is not durable')
        monkeypatch.setattr('gateway.gateway.send_message', send)
        g = Gateway('A1'); g.connections['B1'] = object()
        await g._process_sensor_message(sample())
        assert g.metrics.get('sensor_durable_rejected') == 1
        g.offline_queue.close()
    asyncio.run(run())
