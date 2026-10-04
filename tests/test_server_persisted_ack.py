"""Durable receipt regressions using both controlled writes and real TCP."""
import asyncio
import time
from contextlib import contextmanager
from common.messages import Message, SENSOR_DATA, PERSISTED_ACK, ACK, read_message, send_message
from gateway.gateway import Gateway
from server.server import Server

def upload():return Message(type=SENSOR_DATA,source='A1',target='SERVER',message_id='durable-one',
    payload={'record':{'sensor_node_id':'B1','temperature':25}})

def receipt(kind=PERSISTED_ACK,source='SERVER'):
    return Message(type=kind,source=source,target='A1',payload={'ack_message_id':'durable-one','persisted':True})

def test_queue_drain_requires_persisted_ack_not_write_or_controller_ack(monkeypatch):
    async def run():
        g=Gateway('A1');g.server_writer=object();sent=asyncio.Event()
        async def fake(w,m):sent.set()
        monkeypatch.setattr('gateway.gateway.send_message',fake)
        g.offline_queue.enqueue(upload());task=asyncio.create_task(g._flush_offline_queue())
        await sent.wait()
        assert g.offline_queue.count()==1
        assert not g._handle_persisted_ack(receipt(ACK),g.server_writer)
        assert not g._handle_persisted_ack(receipt(source='C1'),g.server_writer)
        assert g.offline_queue.count()==1
        assert g._handle_persisted_ack(receipt(),g.server_writer)
        assert not g._handle_persisted_ack(receipt(),g.server_writer)
        await task
        assert g.offline_queue.count()==0
        assert not g._handle_persisted_ack(receipt(),g.server_writer)
        g.offline_queue.close()
    asyncio.run(run())

def test_timeout_late_ack_and_connection_failure_retain_rows(monkeypatch):
    async def run():
        g=Gateway('A1',receipt_timeout=0.01);old=object();g.server_writer=old
        async def drain_only(w,m):pass
        monkeypatch.setattr('gateway.gateway.send_message',drain_only)
        g.offline_queue.enqueue(upload());await g._flush_offline_queue()
        assert g.offline_queue.count()==1 and g.server_writer is None
        assert not g._handle_persisted_ack(receipt(),old)
        g.server_writer=object()
        async def broken(w,m):raise ConnectionResetError()
        monkeypatch.setattr('gateway.gateway.send_message',broken);await g._flush_offline_queue()
        assert g.offline_queue.count()==1
        g.offline_queue.close()
    asyncio.run(run())

def test_server_unavailable_before_send_still_persists_outbox():
    async def run():
        g=Gateway('A1');await g._deliver(upload())
        assert g.offline_queue.count()==1
        g.offline_queue.close()
    asyncio.run(run())

def test_commit_success_ack_lost_then_reconnect_replays_once(tmp_path,monkeypatch):
    async def run():
        s=Server(port=0,db_path=str(tmp_path/'server.db'));await s.start()
        g=Gateway('A1',server_port=s._server.sockets[0].getsockname()[1],
                  queue_path=str(tmp_path/'queue.db'),receipt_timeout=0.2)
        dropped=asyncio.Event();committed=[]
        transaction=s.db.transaction
        @contextmanager
        def commit_marked():
            with transaction():yield
            committed.append(True)
        monkeypatch.setattr(s.db,'transaction',commit_marked)
        async def send(w,m):
            if m.type==PERSISTED_ACK:
                assert committed and s.db.count('sensor_data')==1
                if not dropped.is_set():
                    dropped.set();w.close();return
            await send_message(w,m)
        monkeypatch.setattr('server.server.send_message',send)
        g.offline_queue.enqueue(upload());task=asyncio.create_task(g.task_server_policy())
        try:
            await asyncio.wait_for(dropped.wait(),2)
            assert g.offline_queue.count()==1
            deadline=time.monotonic()+5
            while g.offline_queue.count() and time.monotonic()<deadline:await asyncio.sleep(0.01)
            assert g.offline_queue.count()==0
            assert s.db.count('sensor_data')==s.db.count('processed_message')==1
            assert s.dedup.ignored>=1
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True)
            g.offline_queue.close();await s.stop()
    asyncio.run(run())

def test_disconnect_before_commit_keeps_outbox():
    async def run():
        got=asyncio.Event()
        async def crash(reader,writer):
            await read_message(reader);got.set();writer.close()
        server=await asyncio.start_server(crash,'127.0.0.1',0)
        g=Gateway('A1',server_port=server.sockets[0].getsockname()[1],receipt_timeout=0.1)
        g.offline_queue.enqueue(upload());task=asyncio.create_task(g.task_server_policy())
        try:
            await asyncio.wait_for(got.wait(),1)
            assert g.offline_queue.count()==1
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True)
            g.offline_queue.close();server.close();await server.wait_closed()
    asyncio.run(run())
