import asyncio
from copy import deepcopy
import json
import sqlite3
import time
import pytest
from common.field_contract import ZoneUplink, FieldFreshnessGuard
from common.field_transport import MockFieldTransport
from common.messages import Message, SENSOR_DATA, ALERT, CONTROL_RESULT, CONTROL_COMMAND
from common.settings import node_settings, SETTINGS, validate_settings
from common.state_store import StateStore, StateError
from sensor_node.adaptive_sense import AdaptiveSense
from sensor_node.control_relevance import ControlRelevanceGate
from sensor_node.runtime import SensorRuntime
from sensor_node.sensor_trust import SensorTrust
from gateway.gateway import Gateway
from gateway.offline_queue import OfflineQueue, QueueCapacityError, admission_priority, HIGH, NORMAL
from controller_node.controller_node import ControllerNode
from controller_node.safety_guard import SafetyGuard
from controller_node.recent_commands import RecentCommandStore


def quiet_settings():
    cfg=node_settings('deployment');cfg['adaptive'].update(stable_threshold=1000,active_threshold=2000,event_threshold=3000)
    cfg['adaptive']['upload'].update(on_event=False,on_state_change=False,on_interval_change=False,heartbeat_s=0,delta_threshold=0)
    cfg['control_relevance']['margins']={'soil_moisture':0,'temperature':0}
    return cfg

def reading(**kw):return {'soil_moisture':26,'temperature':25,'humidity':60,'light':800,**kw}

@pytest.mark.parametrize('field,previous,current',[('soil_moisture',26,24.9),('soil_moisture',24,26),
    ('temperature',32,32.1),('temperature',32.1,32),('soil_moisture',24.9,25)])
def test_threshold_crossing_requests_upload_even_when_all_other_triggers_are_disabled(field,previous,current):
    cfg=quiet_settings();trust=SensorTrust(cfg['trust_channels']);b=AdaptiveSense(settings=cfg)
    before=reading(**{field:previous});health=trust.update(before,0);b.update(before,health,0);b.mark_reported(before,health)
    sample=reading(**{field:current});d=b.update(sample,trust.update(sample,60),60)
    assert d['upload_requested'] and d['control_relevant_change']
    assert d['upload_reasons']==['CONTROL_THRESHOLD_CROSSING']

def test_slow_soil_drift_crossing_uses_last_reported_value_and_fault_is_separate():
    cfg=quiet_settings();b=AdaptiveSense(settings=cfg);trust=SensorTrust(cfg['trust_channels'])
    sample=reading();health=trust.update(sample,0);b.update(sample,health,0);b.mark_reported(sample,health)
    for i,value in enumerate((25.8,25.5,25.2),1):
        sample=reading(soil_moisture=value)
        assert not b.update(sample,trust.update(sample,i*60),i*60)['upload_requested']
    sample=reading(soil_moisture=24.9);health=trust.update(sample,240)
    fault=deepcopy(health);fault.update(state='FAULT',usable_for_control=False)
    fault['channels']['soil_moisture'].update(state='FAULT',valid=False,fault_flags=['MISSING'])
    d=b.update(sample,fault,240)
    assert d['upload_requested'] and d['upload_reasons']==['SENSOR_FAULT'] and not d['control_relevant_change']

def test_margin_entry_is_configurable_and_does_not_flood_inside_the_band():
    gate=ControlRelevanceGate({'soil_moisture':2,'temperature':0})
    gate.mark_reported({'soil_moisture':28},{'soil_moisture'})
    assert gate.evaluate({'soil_moisture':27.1},{'soil_moisture'})['reasons']==[]
    assert gate.evaluate({'soil_moisture':27},{'soil_moisture'})['reasons']==['CONTROL_MARGIN_ENTRY']
    assert not gate.evaluate({'soil_moisture':27},set())['control_relevant_change']
    gate.mark_reported({'soil_moisture':27},{'soil_moisture'})
    assert not gate.evaluate({'soil_moisture':26.5},{'soil_moisture'})['control_relevant_change']
    gate.set_policy({**SETTINGS['policy'],'soil_moisture_threshold':26.8})
    assert gate.evaluate({'soil_moisture':26.5},{'soil_moisture'})['reasons']==['CONTROL_THRESHOLD_CROSSING']
    disabled=ControlRelevanceGate({'soil_moisture':0,'temperature':0})
    disabled.mark_reported({'soil_moisture':28},{'soil_moisture'})
    assert not disabled.evaluate({'soil_moisture':27},{'soil_moisture'})['control_relevant_change']

def test_failed_radio_report_does_not_consume_threshold_crossing():
    class Source:
        samples=iter((26,24.9,24.8))
        def sample(self):return reading(soil_moisture=next(self.samples))
    class Radio(MockFieldTransport):
        fail=False
        async def send(self,message):
            if self.fail:raise OSError('radio unavailable')
            await super().send(message)
    async def run():
        radio=Radio();b=SensorRuntime('B1',Source(),radio,'A1',1);b.scheduler=AdaptiveSense(settings=quiet_settings())
        await b.sample_once(0);radio.fail=True
        with pytest.raises(OSError):await b.sample_once(60)
        assert b.scheduler.relevance.reported['soil_moisture']==26 and not radio.awake
        radio.fail=False;d=await b.sample_once(120)
        assert d['upload_requested'] and 'CONTROL_THRESHOLD_CROSSING' in d['upload_reasons']
        assert b.scheduler.relevance.reported['soil_moisture']==24.8
    asyncio.run(run())


def telemetry(i):return Message(type=SENSOR_DATA,source='A1',target='SERVER',message_id=f'normal-{i}',
    payload={'record':{'sensor_node_id':'B1','temperature':25}})

def important(i,type=ALERT,**payload):return Message(type=type,source='A1',target='SERVER',message_id=f'high-{i}',payload=payload)

@pytest.mark.parametrize('message',[important(1,severity='CRITICAL'),important(2,CONTROL_RESULT),
    important(3,alert_type='COMMAND_DELIVERY_FAILED'),important(4,alert_type='GATEWAY_FAILOVER'),
    important(5,alert_type='SENSOR_FAULT')])
def test_required_important_records_use_high_admission(message):
    assert admission_priority(message)==HIGH and admission_priority(telemetry(0))==NORMAL

def test_normal_capacity_leaves_reserve_for_critical_and_control_results_without_eviction(tmp_path):
    path=str(tmp_path/'queue.db');q=OfflineQueue(path,max_messages=5,max_payload_bytes=10000,reserved_messages=2,reserved_payload_bytes=1000)
    for i in range(3):q.enqueue(telemetry(i))
    with pytest.raises(QueueCapacityError):q.enqueue(telemetry(3))
    q.enqueue(important(1,severity='CRITICAL'));q.enqueue(important(2,CONTROL_RESULT,status='EXECUTED'))
    assert q.enqueue(important(1,severity='CRITICAL'))==q.peek()[3][0]
    before=[m.message_id for _,m in q.peek()]
    with pytest.raises(QueueCapacityError):q.enqueue(important(3,CONTROL_RESULT))
    assert [m.message_id for _,m in q.peek()]==before
    assert q.stats()['admission_rejected_normal']==q.stats()['admission_rejected_high']==1
    q.close();q=OfflineQueue(path,max_messages=5,max_payload_bytes=10000,reserved_messages=2,reserved_payload_bytes=1000)
    try:
        assert [m.message_id for _,m in q.peek()]==before
        assert q.conn.execute('SELECT priority FROM gateway_queue ORDER BY queue_id').fetchall()==[(0,),(0,),(0,),(1,),(1,)]
    finally:q.close()

def test_byte_reserve_also_protects_high_records():
    n=telemetry(1);h=important(1,CONTROL_RESULT)
    size=len(n.to_json().encode());high_size=len(h.to_json().encode())
    q=OfflineQueue(max_messages=10,reserved_messages=0,max_payload_bytes=size+high_size,reserved_payload_bytes=high_size)
    try:
        q.enqueue(n)
        with pytest.raises(QueueCapacityError):q.enqueue(telemetry(2))
        q.enqueue(h);assert q.count()==2
    finally:q.close()

def test_legacy_queue_migrates_priority_without_changing_ids_or_fifo(tmp_path):
    path=str(tmp_path/'old.db');messages=[telemetry(1),important(1,CONTROL_RESULT)]
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE gateway_queue(queue_id INTEGER PRIMARY KEY AUTOINCREMENT,message_id TEXT,message_type TEXT,payload TEXT,created_at REAL,retry_count INTEGER DEFAULT 0)')
        for m in messages:conn.execute('INSERT INTO gateway_queue(message_id,message_type,payload,created_at) VALUES(?,?,?,?)',(m.message_id,m.type,m.to_json(),time.time()))
    q=OfflineQueue(path)
    try:
        assert [m.message_id for _,m in q.peek()]==[m.message_id for m in messages]
        assert q.conn.execute('SELECT priority FROM gateway_queue ORDER BY queue_id').fetchall()==[(0,),(1,)]
    finally:q.close()

def test_entire_queue_full_sets_gateway_local_alert_state():
    async def run():
        g=Gateway('A1');g.offline_queue=OfflineQueue(max_messages=2,reserved_messages=1,max_payload_bytes=10000,reserved_payload_bytes=1000)
        worker=asyncio.create_task(g.task_upload())
        try:
            for m in (telemetry(1),important(1,CONTROL_RESULT),important(2,severity='CRITICAL')):await g.upload_queue.put(m)
            await asyncio.wait_for(g.upload_queue.join(),1)
            assert g.offline_queue.count()==2 and g.metrics.get('outbox_admission_rejected')==1
            assert g.outbox_alert_state=={'state':'CAPACITY_REJECTED','message_id':'high-2','priority':'HIGH'}
        finally:
            worker.cancel();await asyncio.gather(worker,return_exceptions=True);g.offline_queue.close()
    asyncio.run(run())


def cmd(cid='CMD-001'):
    return Message(type=CONTROL_COMMAND,source='A1',target='C1',payload={'command_id':cid,'type':'IRRIGATION','duration':1,'gateway_generation':1})

def controller(path):
    return ControllerNode('C1',safety_guard=SafetyGuard(store=StateStore(path),cooldown={'IRRIGATION':0,'VENTILATION':0}),time_scale=0)

def test_command_intent_precedes_actuation_and_duplicate_survives_controller_restart(tmp_path,monkeypatch):
    async def run():
        path=tmp_path/'c.db';c=controller(path);original=asyncio.sleep;actuations=[]
        async def actuator(delay):
            saved=StateStore(path).load('recent_commands')
            assert saved['entries'][0]['state']=='INTENT'
            actuations.append('CMD-001');await original(0)
        monkeypatch.setattr('controller_node.controller_node.asyncio.sleep',actuator)
        assert (await c.process_command(cmd()))['status']=='EXECUTED'
        reboot=controller(path)
        assert (await reboot.process_command(cmd()))['status']=='DUPLICATE'
        assert actuations==['CMD-001'] and reboot.metrics.get('executed')==0
    asyncio.run(run())

def test_crash_with_unfinished_intent_cannot_execute_same_command_on_reboot(tmp_path,monkeypatch):
    async def run():
        path=tmp_path/'c.db';c=controller(path)
        async def crash(delay):raise asyncio.CancelledError()
        monkeypatch.setattr('controller_node.controller_node.asyncio.sleep',crash)
        with pytest.raises(asyncio.CancelledError):await c.process_command(cmd())
        reboot=controller(path)
        assert (await reboot.process_command(cmd()))['status']=='DUPLICATE'
        assert reboot.metrics.get('executed')==0
    asyncio.run(run())

def test_recent_command_corruption_and_failed_intent_write_fail_closed(tmp_path,monkeypatch):
    async def run():
        path=tmp_path/'c.db';c=controller(path)
        with sqlite3.connect(path) as conn:conn.execute("UPDATE checkpoints SET checksum='bad' WHERE namespace='recent_commands' AND slot=0")
        reboot=controller(path);assert (await reboot.process_command(cmd()))['reason']=='STATE_UNAVAILABLE'
        healthy=controller(tmp_path/'healthy.db');save=healthy.guard.store.save
        def fail(namespace,value):
            if namespace=='recent_commands':raise sqlite3.OperationalError('disk full')
            save(namespace,value)
        monkeypatch.setattr(healthy.guard.store,'save',fail)
        assert (await healthy.process_command(cmd()))['reason']=='STATE_UNAVAILABLE'
        assert healthy.metrics.get('executed')==reboot.metrics.get('executed')==0
    asyncio.run(run())

def test_failed_result_write_retains_intent_and_reboot_cannot_repeat_actuation(tmp_path,monkeypatch):
    async def run():
        path=tmp_path/'c.db';c=controller(path);save=c.guard.store.save
        def fail_result(namespace,value):
            if namespace=='recent_commands' and any(r['state']=='COMPLETED' for r in value['entries']):raise sqlite3.OperationalError('disk full')
            save(namespace,value)
        monkeypatch.setattr(c.guard.store,'save',fail_result)
        assert (await c.process_command(cmd()))['status']=='UNKNOWN'
        reboot=controller(path);assert (await reboot.process_command(cmd()))['status']=='DUPLICATE'
        assert c.metrics.get('executed')==1 and reboot.metrics.get('executed')==0
    asyncio.run(run())

def test_recent_window_is_bounded_and_unfinished_intents_are_not_evicted(tmp_path):
    s=RecentCommandStore(StateStore(tmp_path/'c.db'),capacity=2)
    s.begin('unfinished');s.begin('done');s.complete('done',{'status':'EXECUTED'})
    s.begin('new');assert list(s.entries)==['unfinished','new']
    with pytest.raises(StateError):s.begin('overflow')
    assert list(RecentCommandStore(StateStore(tmp_path/'c.db'),capacity=2).entries)==['unfinished','new']


def test_zone_uplink_is_constant_when_gateway_ownership_changes():
    uplink=ZoneUplink('B1','Zone1',1,'b-boot',reading())
    a1,a2=Gateway('A1'),Gateway('A2')
    assert uplink.may_process(a1.ownership) and not uplink.may_process(a2.ownership)
    a2._takeover()
    assert uplink.may_process(a2.ownership) and uplink.zone_id=='Zone1'
    assert not ZoneUplink('B1','Zone2',1,'b-boot',reading()).may_process(a2.ownership)
    assert ZoneUplink('B2','Zone2',1,'b2-boot',reading()).may_process(a2.ownership)

def fresh_contract():
    guard=FieldFreshnessGuard('c-boot',max_ttl_s=10,retry_window_s=5)
    assert guard.bind('A1',2,'a1-boot')
    window=guard.open_window(100)
    message={'source':'A1','generation':2,'gateway_session':'a1-boot','receiver_session':'c-boot',
        'receive_window':window,'command_id':'field-1','command_sequence':1,'ttl_s':10}
    return guard,message

def test_field_freshness_works_without_wall_clock_and_sequence_replay_is_rejected():
    guard,m=fresh_contract();m['wall_clock']=None
    assert guard.accept(m,101)==(True,None)
    assert guard.accept(m,102)==(False,'STALE_SEQUENCE')

@pytest.mark.parametrize('patch,now,reason',[({'generation':1},101,'STALE_GENERATION'),
    ({'gateway_session':'old-boot'},101,'STALE_SESSION'),({'receiver_session':'old-c'},101,'STALE_SESSION'),
    ({'source':'A2'},101,'NOT_OWNER'),({},106,'EXPIRED_LOCAL_TTL'),({'ttl_s':1},102,'EXPIRED_LOCAL_TTL'),
    ({'receive_window':'old-window'},101,'STALE_WINDOW')])
def test_field_freshness_refuses_old_context_and_expired_local_windows(patch,now,reason):
    guard,m=fresh_contract();assert guard.accept({**m,**patch},now)==(False,reason)

def test_receiver_reboot_requires_new_session_and_new_window_not_a_fresh_timestamp():
    guard,m=fresh_contract();new_window=guard.open_window(200)
    assert new_window!=m['receive_window'] and guard.accept(m,200)==(False,'STALE_WINDOW')
    reboot=FieldFreshnessGuard('new-c-boot');assert reboot.bind('A1',2,'a1-boot');reboot.open_window(0)
    assert reboot.accept(m,1)==(False,'STALE_SESSION')

def test_patch_capacity_and_margin_config_rejects_invalid_values():
    for field,value in [('reserved_messages',10000),('reserved_payload_bytes',-1)]:
        cfg=deepcopy(SETTINGS);cfg['offline_queue'][field]=value
        with pytest.raises(ValueError):validate_settings(cfg)
    cfg=deepcopy(SETTINGS);cfg['controller']['recent_command_capacity']=0
    with pytest.raises(ValueError):validate_settings(cfg)
    cfg=deepcopy(SETTINGS);cfg['node']['control_relevance']['margins']['temperature']=-1
    with pytest.raises(ValueError):validate_settings(cfg)
