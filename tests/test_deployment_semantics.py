import asyncio
from copy import deepcopy
import json
import math
import sqlite3
import time
import pytest
from common import config
from common.field_transport import MockFieldTransport
from common.messages import Message, SENSOR_DATA, CONTROL_COMMAND, HEARTBEAT, SERVER_POLICY, PERSISTED_ACK
from common.settings import node_settings, profile_settings
from common.state_store import StateStore, StateError
from sensor_node.adaptive_scheduler import AdaptiveScheduler
from sensor_node.runtime import SensorRuntime
from sensor_node.sensor_node import SensorNode
from gateway.connectivity import Connectivity
from gateway.gateway import Gateway
from gateway.edge_decision import EdgeDecider
from gateway.offline_queue import OfflineQueue, QueueCapacityError
from controller_node.safety_guard import SafetyGuard
from controller_node.controller_node import ControllerNode


def test_deployment_timing_is_explicit_and_separate():
    simulation=node_settings('simulation');lab=node_settings('lab');deployment=node_settings('deployment')
    assert simulation['adaptive']['ladders']['stable']==[20,40,60]
    assert lab['adaptive']['ladders']['stable']==[2,4,5]
    assert deployment['adaptive']['ladders']=={'stable':[1200,2400],'active':[600,300],'alert':[300,120,60]}
    assert deployment['adaptive']['upload']['heartbeat_s']==21600
    assert profile_settings('deployment')['connectivity']['backoff_s']==[5,15,30,60,300]
    assert node_settings()['sampling']==simulation['sampling']
    with pytest.raises(ValueError):SensorNode('B1',profile='deployment')
    with pytest.raises(ValueError):profile_settings('unknown')


def test_stable_onset_recovery_delta_and_periodic_upload_triggers():
    cfg=node_settings('deployment');up=cfg['adaptive']['upload']
    cfg['adaptive'].update(stable_threshold=100,active_threshold=200,event_threshold=300)
    up.update(on_interval_change=False,on_state_change=False,on_event=False,heartbeat_s=3600)
    scheduler=AdaptiveScheduler(cfg)
    assert scheduler.update(0,{'temperature':25}).upload_requested
    for t in (60,120,180,3599):assert not scheduler.update(t,{'temperature':25}).upload_requested
    assert scheduler.update(3600,{'temperature':25}).upload_requested
    assert scheduler.update(3660,{'temperature':26.1}).upload_requested  # normalized meaningful delta only
    # Event upload must happen even with state/interval/delta upload disabled.
    cfg['adaptive'].update(event_threshold=1,event_min_duration_s=60)
    up.update(on_event=True,delta_threshold=0,heartbeat_s=0)
    scheduler=AdaptiveScheduler(cfg);scheduler.update(0,{'temperature':25})
    assert not scheduler.update(60,{'temperature':27}).upload_requested
    event=scheduler.update(120,{'temperature':27})
    assert event.detected_event and event.upload_requested
    cfg['adaptive']['analyzer']['variety_window_s']=30
    # Explicit quiet measurement after EMA relaxation / history expiry.
    for t in range(180,30000,60):
        d=scheduler.update(t,{'temperature':27})
        if not d.detected_event:
            assert d.upload_requested
            break
    else:pytest.fail('event recovery never observed')


def test_deployment_runtime_preserves_state_and_never_wakes_radio_for_suppressed_samples():
    class Source:
        i=0
        def sample(self):
            self.i+=1
            return {'temperature':25+(self.i%2)*.04,'humidity':60+(self.i%2)*.2,
                    'soil_moisture':40+(self.i%2)*.1,'light':800+(self.i%2)*2}
    async def run():
        transport=MockFieldTransport();runtime=SensorRuntime('B1',Source(),transport,'A1',1)
        core=runtime.scheduler.core;t=0
        suppressed=0
        for _ in range(20):
            before=len(transport.events);d=await runtime.sample_once(t)
            if not d['upload_requested']:
                suppressed+=1;assert len(transport.events)==before
            assert not transport.awake and runtime.scheduler.core is core
            t+=d['interval_s']
        assert runtime.samples==20 and runtime.messages<runtime.samples/2 and suppressed>10
        assert all(m.type==SENSOR_DATA for m in transport.messages)
        assert all(m.source=='B1' and m.target=='A1' and m.generation==1 for m in transport.messages)
    asyncio.run(run())


def test_radio_is_put_back_to_sleep_if_transmission_fails():
    class Source:
        def sample(self):return {'temperature':25,'humidity':60,'soil_moisture':40,'light':800}
    class Broken(MockFieldTransport):
        async def send(self,m):raise OSError('radio unavailable')
    async def run():
        radio=Broken();node=SensorRuntime('B1',Source(),radio,'A1',1)
        with pytest.raises(OSError):await node.sample_once(0)
        assert radio.events==['wake','sleep'] and not radio.awake
        assert node.scheduler.core.n_samples==1
    asyncio.run(run())


def test_cloud_backoff_is_bounded_and_critical_retry_is_rate_limited():
    c=Connectivity(profile_settings('deployment')['connectivity'])
    assert c.state=='OFFLINE'
    assert [c.failed() for _ in range(8)]==[5,15,30,60,300,300,300,300]
    assert c.state=='OFFLINE'
    c.connected(backlog=True);assert c.state=='DEGRADED'
    assert c.request_critical_retry(100) and not c.request_critical_retry(101)
    asyncio.run(c.wait_retry(300))  # already-set event: returns immediately
    assert not c.request_critical_retry(399)
    assert c.request_critical_retry(400)
    c.confirmed();assert c.state=='ONLINE' and c.failures==0


def test_policy_checkpoint_loads_offline_and_rejects_invalid_or_older_policy(tmp_path):
    path=str(tmp_path/'state.db');g=Gateway('A1',state_path=path)
    g._apply_policy(Message(type=SERVER_POLICY,source='SERVER',target='A1',payload={'policy_version':10,'temperature_threshold':35}))
    restored=Gateway('A1',state_path=path)
    assert restored.server_writer is None and restored.decider.policy_version==10
    assert restored.decider.policy['temperature_threshold']==35
    assert not restored.decider.update_policy({'policy_version':9,'temperature_threshold':40})[0]
    before=deepcopy(restored.decider.policy)
    with pytest.raises(ValueError):restored.decider.update_policy({'policy_version':11,'ventilation_duration':1000})
    assert restored.decider.policy==before and restored.decider.policy_version==10
    with sqlite3.connect(path) as conn:
        row=conn.execute("SELECT payload,checksum,updated_at FROM checkpoints WHERE namespace='policy' AND slot=0").fetchone()
        assert json.loads(row[0])['policy_version']==10 and len(row[1])==64 and row[2]>0


def test_policy_corruption_falls_back_to_previous_valid_or_safe_default(tmp_path):
    store=StateStore(tmp_path/'state.db');d=EdgeDecider(store=store)
    d.update_policy({'policy_version':2,'temperature_threshold':34})
    d.update_policy({'policy_version':3,'temperature_threshold':36})
    with sqlite3.connect(store.path) as conn:conn.execute("UPDATE checkpoints SET checksum='bad' WHERE namespace='policy' AND slot=0")
    restored=EdgeDecider(store=store);assert restored.policy_version==2 and restored.policy['temperature_threshold']==34
    with sqlite3.connect(store.path) as conn:conn.execute("UPDATE checkpoints SET checksum='bad' WHERE namespace='policy'")
    restored=EdgeDecider(store=store);assert restored.policy==config.DEFAULT_POLICY and restored.policy_version==0


def test_failed_policy_commit_cannot_activate(tmp_path,monkeypatch):
    store=StateStore(tmp_path/'state.db');d=EdgeDecider(store=store);before=deepcopy(d.policy)
    def fail(*args):raise sqlite3.OperationalError('storage full')
    monkeypatch.setattr(store,'save',fail)
    with pytest.raises(sqlite3.Error):d.update_policy({'policy_version':2,'temperature_threshold':34})
    assert d.policy==before and d.policy_version==0


def peer(generation=2):
    return Message(type=HEARTBEAT,source='A2',target='A1',payload={'generation':generation,
        'ownership':{n:{'owner_gateway':'A2','generation':generation} for n in ('B1','C1','B2','C2')}})


def test_gateway_restart_retains_epoch_zone_ownership_and_standby(tmp_path):
    path=str(tmp_path/'state.db');g=Gateway('A2',state_path=path)
    assert g._takeover()==2
    restored=Gateway('A2',state_path=path)
    assert restored.ownership.generation==2 and restored.ownership.role=='STANDBY'
    assert all(restored.registry.get(n).owner_gateway=='A2' for n in ('B1','C1','B2','C2'))
    restored._on_peer_heartbeat(Message(type=HEARTBEAT,source='A1',target='A2',payload={'generation':1}))
    assert restored.ownership.role=='ACTIVE'
    a1_path=str(tmp_path/'a1.db');a1=Gateway('A1',state_path=a1_path);a1._on_peer_heartbeat(peer())
    reboot=Gateway('A1',state_path=a1_path);reboot._on_peer_heartbeat(peer())
    assert reboot.ownership.role=='STANDBY'
    # Even stale/equal observations cannot automatically fail back.
    reboot._on_peer_heartbeat(peer(1));assert reboot.ownership.role=='STANDBY'
    assert reboot.registry.get('B1').owner_gateway==reboot.registry.get('C1').owner_gateway=='A2'


def test_corrupt_or_failed_epoch_storage_disables_control_not_rolls_back(tmp_path,monkeypatch):
    path=str(tmp_path/'state.db');g=Gateway('A2',state_path=path);g._takeover()
    with sqlite3.connect(path) as conn:conn.execute("UPDATE checkpoints SET checksum='bad' WHERE namespace='ownership' AND slot=0")
    reboot=Gateway('A2',state_path=path)
    assert reboot.persistence_fault and reboot.ownership.role=='STANDBY'
    assert not reboot.ownership.may_control('C1') and reboot._takeover()==1
    healthy=Gateway('A1',state_path=str(tmp_path/'healthy.db'))
    def fail(*args):raise sqlite3.OperationalError('storage full')
    monkeypatch.setattr(healthy.state_store,'save',fail);healthy._takeover()
    assert healthy.persistence_fault and not healthy.ownership.may_control('C1')


def test_controller_reboot_remembers_highest_generation_before_execution(tmp_path):
    async def run():
        path=str(tmp_path/'c1.db');c=ControllerNode('C1',state_path=path,time_scale=0)
        m=Message(type=CONTROL_COMMAND,source='A2',target='C1',payload={'command_id':'new','type':'IRRIGATION','duration':1,'gateway_generation':5})
        # Intercept the simulated actuator wait and check persisted state first.
        original=asyncio.sleep
        async def actuator_wait(delay):
            guard=SafetyGuard(store=StateStore(path))
            assert guard.current_generation==5 and guard.owner_gateway=='A2'
            await original(0)
        import unittest.mock
        with unittest.mock.patch('controller_node.controller_node.asyncio.sleep',actuator_wait):
            assert (await c.process_command(m))['status']=='EXECUTED'
        reboot=ControllerNode('C1',state_path=path,time_scale=0)
        stale=Message(type=CONTROL_COMMAND,source='A1',target='C1',payload={'command_id':'stale','type':'IRRIGATION','duration':1,'gateway_generation':1})
        assert (await reboot.process_command(stale))['reason']=='STALE_GENERATION'
        assert not reboot.guard.set_ownership('A1',1)
        assert reboot.guard.check('fresh','IRRIGATION',1,time.time(),gateway_generation=5,source_gateway='A2')[1]=='COOLDOWN'
    asyncio.run(run())


def test_corrupt_controller_checkpoint_fails_closed(tmp_path):
    store=StateStore(tmp_path/'c.db');g=SafetyGuard(store=store);g.set_ownership('A2',7)
    with sqlite3.connect(store.path) as conn:conn.execute("UPDATE checkpoints SET checksum='bad' WHERE namespace='controller' AND slot=0")
    reboot=SafetyGuard(store=store)
    assert reboot.persistence_fault and not reboot.set_ownership('A1',1)
    assert reboot.check('bad','IRRIGATION',1,time.time(),gateway_generation=1,source_gateway='A1')[1]=='STATE_UNAVAILABLE'


def upload(i):
    return Message(type=SENSOR_DATA,source='A1',target='SERVER',message_id=f'outbox-{i}',payload={'record':{'sensor_node_id':'B1','temperature':25}})


def test_bounded_outbox_keeps_unacknowledged_rows_and_reports_rejection(tmp_path):
    q=OfflineQueue(str(tmp_path/'q.db'),max_messages=2,max_payload_bytes=10000)
    try:
        q.enqueue(upload(1));q.enqueue(upload(2));assert q.enqueue(upload(1))==q.peek()[0][0]
        with pytest.raises(QueueCapacityError):q.enqueue(upload(3))
        assert [m.message_id for _,m in q.peek()]==['outbox-1','outbox-2']
        assert q.stats()['admission_rejected']==1 and q.stats()['depth']==2
        q.delete(q.peek()[0][0]);q.enqueue(upload(3));assert q.count()==2
    finally:q.close()
    q=OfflineQueue(str(tmp_path/'q.db'),max_messages=2,max_payload_bytes=10000)
    try:assert [m.message_id for _,m in q.peek()]==['outbox-2','outbox-3']
    finally:q.close()
    q=OfflineQueue(max_messages=100,max_payload_bytes=1)
    try:
        with pytest.raises(QueueCapacityError):q.enqueue(upload(4))
        assert q.count()==0
    finally:q.close()


def test_cloud_stalled_receipt_never_blocks_upload_staging_or_local_control(monkeypatch):
    async def run():
        g=Gateway('A1',receipt_timeout=30)
        class Writer:
            def close(self):pass
        g.server_writer=Writer();sent=asyncio.Event()
        async def stall(w,m):sent.set()
        monkeypatch.setattr('gateway.gateway.send_message',stall)
        for i in range(5):await g._deliver(upload(i))
        await sent.wait()
        assert g.offline_queue.count()==5
        await asyncio.wait_for(g._process_sensor_message(Message(type=SENSOR_DATA,source='B1',target='A1',
            payload={'data':{'soil_moisture':10,'temperature':25}})),.2)
        command,_=g.command_queue.get_nowait();assert command.target=='C1'
        g._stopping=True;g._cloud_flush.cancel();await asyncio.gather(g._cloud_flush,return_exceptions=True)
        g.offline_queue.close()
    asyncio.run(run())


def test_gateway_reports_critical_event_and_outbox_full_without_stopping_control():
    async def run():
        g=Gateway('A1');g.offline_queue.max_messages=1
        await g._process_sensor_message(Message(type='ALERT',source='B1',target='A1',payload={
            'alert_type':'CRITICAL_CONDITION','severity':'CRITICAL','message':'test critical event'}))
        forwarded=await g.upload_queue.get();g.upload_queue.task_done()
        await g._deliver(forwarded)
        assert g.connectivity.early.is_set()
        worker=asyncio.create_task(g.task_upload())
        for i in range(3):await g.upload_queue.put(upload(i))
        await asyncio.wait_for(g.upload_queue.join(),1)
        assert g.metrics.get('outbox_admission_rejected')==3
        await g._process_sensor_message(Message(type=SENSOR_DATA,source='B1',target='A1',
            payload={'data':{'soil_moisture':10,'temperature':25}}))
        command,_=g.command_queue.get_nowait()
        c=ControllerNode('C1',time_scale=0)
        assert (await c.process_command(command))['status']=='EXECUTED'
        g._stopping=True;worker.cancel();await asyncio.gather(worker,return_exceptions=True)
        assert g.offline_queue.peek()[0][1].message_id==forwarded.message_id
        g.offline_queue.close()
    asyncio.run(run())


def test_gateway_ownership_connectivity_and_queue_metadata_survive_cloud_storage(tmp_path):
    from server.server import Server
    from server.dedup import Deduplicator
    server=Server(db_path=str(tmp_path/'cloud.db'));server.db.init_schema()
    server.dedup=Deduplicator(server.db.conn,auto_commit=False)
    payload={'gateway_id':'A2','peer_id':'A1','status':'ONLINE','peer_status':'OFFLINE',
        'generation':2,'role':'ACTIVE','ownership':{'B1':{'owner_gateway':'A2','generation':2}},
        'connectivity':'DEGRADED','offline_queue':{'depth':40,'payload_bytes':9000,'oldest_age_s':600}}
    try:
        assert server._store(Message(type=HEARTBEAT,source='A2',target='SERVER',payload=payload))
        row=server.db.conn.execute('SELECT metadata_json FROM gateway_heartbeat').fetchone()
        assert json.loads(row[0])==payload
    finally:server.db.close()


def test_physical_read_failure_null_channels_receive_persisted_cloud_ack(tmp_path):
    from server.server import Server
    from server.dedup import Deduplicator
    async def run():
        g=Gateway('A1');s=Server(db_path=str(tmp_path/'db'));s.db.init_schema();s.dedup=Deduplicator(s.db.conn,auto_commit=False)
        try:
            await g._process_sensor_message(Message(type=SENSOR_DATA,source='B1',target='A1',payload={
                'node_mode':'physical','data':{'temperature':None,'humidity':None},
                'health_state':'FAULT','physical_read_ok':False,'usable_for_control':False}))
            history=await g.upload_queue.get()
            assert s._store(history)  # this is the gate for PERSISTED_ACK
            assert s.db.count('sensor_data')==1 and g.command_queue.empty()
            row=s.db.recent_sensor_data()[0]
            assert row['temperature'] is None and row['humidity'] is None
        finally:s.db.close()
    asyncio.run(run())
