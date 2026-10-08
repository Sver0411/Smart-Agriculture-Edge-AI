import asyncio
import time
import pytest
from common.messages import Message, HEARTBEAT, NODE_STATUS
from gateway.gateway import Gateway
from test_b1_gateway_receipts import sample


def test_unenrolled_heartbeat_cannot_change_ownership():
    async def run():
        g=Gateway("A1",port=0,peer_port=1,server_port=1)
        await g.start()
        r,w=await asyncio.open_connection("127.0.0.1",g._server.sockets[0].getsockname()[1])
        from common.messages import send_message
        await send_message(w,Message(type=HEARTBEAT,source="A2",target="A1",payload={"generation":99}))
        await asyncio.sleep(.03)
        assert g.ownership.generation==1 and g.ownership.role=="ACTIVE" and g.peer_last_seen is None
        w.close();await g.stop()
    asyncio.run(run())


def test_queue_wait_is_added_to_sample_age(tmp_path,monkeypatch):
    async def run():
        g=Gateway("A1",queue_path=str(tmp_path/"q.db"))
        g.sensor_boots["B1"]="device-boot";g.connections["B1"]=object()
        async def send(*args):pass
        monkeypatch.setattr("gateway.gateway.send_message",send)
        m=sample();m.payload["data"]["temperature"]=36
        g.sensor_queue.put_nowait(m)
        monkeypatch.setattr("gateway.gateway.time.monotonic",lambda:time.perf_counter()+10)
        await g._process_sensor_message(await g.sensor_queue.get())
        assert g.command_queue.empty()
        assert g.offline_queue.count()==1
        assert not g.offline_queue.peek()[0][1].payload["record"]["usable_for_control"]
        g.offline_queue.close()
    asyncio.run(run())


def test_all_internal_queues_are_bounded():
    g=Gateway("A1")
    for q in [g.sensor_queue,g.result_queue,g.upload_queue,g.command_queue]:
        assert 0<q.maxsize<=1024
    g.offline_queue.close()


@pytest.mark.parametrize("bad", ["replay", "auth", "session", "target", "generation", "pair"])
def test_deployment_hmac_rejects_invalid_heartbeats(bad):
    from gateway import peer_security as ps
    from common.messages import send_message, read_message
    async def run():
        key=b"laboratory-public-test-key-only!!"
        g=Gateway("A1",peer_security_mode="hmac",peer_key=key)
        server=await asyncio.start_server(g._handle_client,"127.0.0.1",0)
        r,w=await asyncio.open_connection("127.0.0.1",server.sockets[0].getsockname()[1])
        try:
            client=ps.nonce()
            await send_message(w,Message(type=NODE_STATUS,source="A2",target="A1",payload={"peer_handshake":"HELLO","client":client}))
            challenge=await read_message(r);session=challenge.payload["session"]
            proof=ps.proof("A2","A1",client,session)
            assert ps.verify(key,{"purpose":"CHALLENGE",**proof},challenge.payload["server_auth"])
            await send_message(w,Message(type=NODE_STATUS,source="A2",target="A1",payload={"peer_handshake":"AUTH","mode":"hmac","session":session,"auth":ps.tag(key,proof)}))
            assert (await read_message(r)).payload["accepted"]
            def heartbeat(seq,gen=2):
                m=Message(type=HEARTBEAT,source="A2",target="A1",payload={"generation":gen,"peer_session":session,"peer_sequence":seq})
                m.payload["peer_auth"]=ps.tag(key,m.to_dict());return m
            await send_message(w,heartbeat(1));await asyncio.sleep(.01)
            seen=g.peer_last_seen
            assert seen is not None and g.ownership.role=="STANDBY"
            m=heartbeat(1 if bad=="replay" else 2,1 if bad=="generation" else 2)
            if bad=="auth":m.payload["peer_auth"]="0"*64
            if bad=="session":m.payload["peer_session"]="0"*32
            if bad=="target":m.target="SERVER"
            if bad=="pair":m.payload["ownership"]={"B1":{"owner_gateway":"A2","generation":2}}
            if bad in ("generation","pair"):
                m.payload.pop("peer_auth");m.payload["peer_auth"]=ps.tag(key,m.to_dict())
            await send_message(w,m);await asyncio.sleep(.01)
            assert g.peer_last_seen==seen and g.ownership.role=="STANDBY"
        finally:
            w.close();await w.wait_closed();server.close();await server.wait_closed();g.offline_queue.close()
    asyncio.run(run())


def test_wrong_shared_key_cannot_enroll_peer():
    from common.messages import send_message,read_message
    async def run():
        g=Gateway("A1",peer_security_mode="hmac",peer_key=b"x"*32)
        server=await asyncio.start_server(g._handle_client,"127.0.0.1",0)
        r,w=await asyncio.open_connection("127.0.0.1",server.sockets[0].getsockname()[1])
        await send_message(w,Message(type=NODE_STATUS,source="A2",target="A1",payload={"peer_handshake":"HELLO","client":"a"*32}))
        session=(await read_message(r)).payload["session"]
        await send_message(w,Message(type=NODE_STATUS,source="A2",target="A1",payload={"peer_handshake":"AUTH","mode":"hmac","session":session,"auth":"0"*64}))
        assert not (await read_message(r)).payload["accepted"]
        assert not g.peer_sessions and g.peer_last_seen is None
        w.close();await w.wait_closed();server.close();await server.wait_closed();g.offline_queue.close()
    asyncio.run(run())


def test_congested_high_ingress_is_explicitly_rejected(tmp_path):
    from common.messages import NODE_REGISTER,send_message,read_message
    async def run():
        g=Gateway("A1",queue_capacity=1,queue_path=str(tmp_path/"q.db"))
        server=await asyncio.start_server(g._handle_client,"127.0.0.1",0)
        r,w=await asyncio.open_connection("127.0.0.1",server.sockets[0].getsockname()[1])
        await send_message(w,Message(type=NODE_REGISTER,source="B1",target="A1",payload={"node_type":"SENSOR","boot_id":"device-boot"}))
        assert (await read_message(r)).payload["accepted"]
        await send_message(w,sample(1));await send_message(w,sample(2))
        rejected=await asyncio.wait_for(read_message(r),1)
        assert rejected.type==NODE_STATUS and rejected.payload["reason"]=="QUEUE_FULL"
        assert not rejected.payload["persisted"] and g.sensor_queue.qsize()==1
        assert g.offline_queue.count()==0
        w.close();await w.wait_closed();server.close();await server.wait_closed();g.offline_queue.close()
    asyncio.run(run())


def test_congested_cloud_queue_preserves_high_without_blocking_control(tmp_path):
    from common.messages import ALERT
    async def run():
        g=Gateway("A1",queue_capacity=1,queue_path=str(tmp_path/"q.db"))
        g.upload_queue.put_nowait(Message(type=ALERT,source="A1",target="SERVER"))
        alert=Message(type=ALERT,source="A1",target="SERVER",payload={"severity":"CRITICAL"})
        assert await asyncio.wait_for(g._submit_upload(alert),.1)
        assert g.offline_queue.count()==1 and g.upload_queue.qsize()==1
        assert g.upload_queue.stats()["high_water"]==1
        g.offline_queue.close()
    asyncio.run(run())


def test_gateway_restart_invalidates_received_monotonic(tmp_path,monkeypatch):
    async def run():
        g=Gateway("A1",queue_path=str(tmp_path/"q.db"));g.sensor_boots["B1"]="device-boot"
        m=sample();m.payload["data"]["temperature"]=36
        m._gateway_ingress=("previous-gateway-boot",time.monotonic(),time.time())
        await g._process_sensor_message(m)
        assert g.command_queue.empty() and g.offline_queue.count()==1
        assert g.metrics.get("freshness_rejected_unknown")==1
        g.offline_queue.close()
    asyncio.run(run())


def test_ack_wait_cannot_extend_control_freshness(tmp_path,monkeypatch):
    async def run():
        g=Gateway("A1",queue_path=str(tmp_path/"q.db"));g.sensor_boots["B1"]="device-boot";g.connections["B1"]=object()
        clock=[1.0];monkeypatch.setattr("gateway.gateway.time.monotonic",lambda:clock[0])
        async def send(*args):clock[0]+=6
        monkeypatch.setattr("gateway.gateway.send_message",send)
        m=sample();m.payload["data"]["temperature"]=36
        await g._process_sensor_message(m)
        assert g.command_queue.empty() and g.offline_queue.count()==1
        assert g.metrics.get("freshness_rejected_at_decision")==1
        g.offline_queue.close()
    asyncio.run(run())
