import asyncio
import pytest
from gateway.gateway import Gateway
from gateway.offline_queue import OfflineQueue, QueueCapacityError
from gateway.sensor_delivery import identity_and_digest
from test_b1_gateway_receipts import sample

def test_capacity_observable_and_read_only_archive(tmp_path):
    q=OfflineQueue(str(tmp_path/'q.db'),max_sensor_receipts=10)
    for i in range(1,9):
        m=sample(i);assert q.admit_sensor(m,*identity_and_digest(m))
        q.delete(q.peek()[0][0])
    stats=q.receipt_stats()
    assert stats['count']==8 and stats['near_capacity'] and stats['logical_bytes']>0
    archive=q.export_receipts()
    assert len(archive['receipts'])==8 and archive['retirement_allowed'] is False
    for i in (9,10):
        m=sample(i);assert q.admit_sensor(m,*identity_and_digest(m))
    with pytest.raises(QueueCapacityError):
        m=sample(11);q.admit_sensor(m,*identity_and_digest(m))
    assert q.receipt_stats()['capacity_rejected']==1
    m=sample();assert not q.admit_sensor(m,*identity_and_digest(m))
    assert q.receipt_stats()['count']==10
    q.close()

def test_crash_after_persist_before_ack_never_redecides(tmp_path,monkeypatch):
    async def run():
        path=str(tmp_path/'q.db');g=Gateway('A1',queue_path=path)
        g.connections['B1']=object();g.sensor_boots['B1']='device-boot'
        async def fail(w,m):raise BrokenPipeError('crash at ACK')
        monkeypatch.setattr('gateway.gateway.send_message',fail)
        m=sample();m.payload['data']['temperature']=36
        with pytest.raises(BrokenPipeError):await g._process_sensor_message(m)
        assert g.offline_queue.sensor_audit(m.message_id)['state']=='RECEIVED'
        g.offline_queue.close();g=Gateway('A1',queue_path=path)
        g.sensor_boots['B1']='device-boot';g.connections['B1']=object()
        async def ok(w,m):pass
        monkeypatch.setattr('gateway.gateway.send_message',ok)
        await g._process_sensor_message(m)
        assert g.command_queue.empty()
        assert g.offline_queue.sensor_audit(m.message_id)['state']=='RECEIVED'
        g.offline_queue.close()
    asyncio.run(run())

@pytest.mark.parametrize('dispatch', [False,True])
def test_crash_planned_or_sent_command_is_auditable_and_not_replayed(tmp_path,monkeypatch,dispatch):
    async def run():
        path=str(tmp_path/'q.db');g=Gateway('A1',queue_path=path)
        g.connections['B1']=object();g.sensor_boots['B1']='device-boot'
        async def send(w,m):
            if m.type=='CONTROL_COMMAND':raise BrokenPipeError('uncertain delivery')
        monkeypatch.setattr('gateway.gateway.send_message',send)
        m=sample();m.payload['data']['temperature']=36
        await g._process_sensor_message(m)
        command,_=g.command_queue.get_nowait()
        assert g.offline_queue.sensor_audit(m.message_id)['state']=='COMMAND_PLANNED'
        if dispatch:
            g.connections['C1']=object()
            await g._dispatch_command(command,True)
            assert g.offline_queue.sensor_audit(m.message_id)['state']=='DISPATCH_UNCERTAIN'
        g.offline_queue.close();g=Gateway('A1',queue_path=path)
        g.connections['B1']=object();g.sensor_boots['B1']='device-boot'
        await g._process_sensor_message(m)
        assert g.command_queue.empty()
        audit=g.offline_queue.sensor_audit(m.message_id)
        assert audit['command_id']==command.message_id
        assert audit['state']==('DISPATCH_UNCERTAIN' if dispatch else 'COMMAND_PLANNED')
        g.offline_queue.close()
    asyncio.run(run())

def test_long_running_receipt_growth_survives_cloud_cleanup_and_restart(tmp_path):
    path=str(tmp_path/'q.db');q=OfflineQueue(path,max_sensor_receipts=512)
    for i in range(1,513):
        m=sample(i);assert q.admit_sensor(m,*identity_and_digest(m));q.delete(q.peek()[0][0])
    q.close();q=OfflineQueue(path,max_sensor_receipts=512)
    assert q.receipt_stats()['count']==512 and q.count()==0
    for i in range(1,513):
        m=sample(i);assert not q.admit_sensor(m,*identity_and_digest(m))
    assert len(q.export_receipts()['receipts'])==512
    q.close()

def test_failover_stale_sample_is_history_even_in_independent_ledger(tmp_path):
    async def run():
        g=Gateway('A2',queue_path=str(tmp_path/'a2.db'))
        g.sensor_boots['B1']='device-boot'
        m=sample();m.target='A2';m.payload['delivery_age_ms']=6000;m.payload['data']['temperature']=36
        await g._process_sensor_message(m)
        assert g.command_queue.empty() and g.offline_queue.count()==1
        assert g.offline_queue.sensor_audit(m.message_id)['state']=='SKIPPED_UNTRUSTED_OR_STALE'
        g.offline_queue.close()
    asyncio.run(run())

def test_concurrent_receipt_admission_cannot_exceed_limit(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    path=str(tmp_path/'q.db');OfflineQueue(path).connect().close()
    barrier=Barrier(2)
    def worker(seq):
        q=OfflineQueue(path,max_sensor_receipts=1).connect()
        # Force both unprotected preflight readers into the original race;
        # serialized admission reads have already acquired their write lock.
        def trace(sql):
            if sql=='SELECT COUNT(*) FROM sensor_receipts' and not q.conn.in_transaction:
                barrier.wait(timeout=5)
        q.conn.set_trace_callback(trace)
        m=sample(seq)
        try:return q.admit_sensor(m,*identity_and_digest(m))
        except QueueCapacityError:return False
        finally:q.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(worker,[1,2]))
    assert sum(results)==1
    q=OfflineQueue(path);assert q.receipt_stats()['count']==1;q.close()

def test_audit_storage_failure_does_not_drop_controller_result(tmp_path,monkeypatch):
    import sqlite3
    from common.messages import Message,CONTROL_RESULT
    async def run():
        g=Gateway('A1',queue_path=str(tmp_path/'q.db'))
        def fail(*args):raise sqlite3.OperationalError('audit disk failure')
        monkeypatch.setattr(g.offline_queue,'audit_command_outcome',fail)
        task=asyncio.create_task(g.task_control_result())
        try:
            await g.result_queue.put(Message(type=CONTROL_RESULT,source='C1',target='A1',
                payload={'command_id':'known','status':'EXECUTED'}))
            result=await asyncio.wait_for(g.upload_queue.get(),.5)
            assert result.type==CONTROL_RESULT and result.payload['status']=='EXECUTED'
            assert g.metrics.get('sensor_audit_failures')==1
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True);g.offline_queue.close()
    asyncio.run(run())
