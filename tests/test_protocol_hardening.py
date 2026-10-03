import asyncio
import time
import pytest
from common.messages import Message, MessageError, CONTROL_COMMAND, SENSOR_DATA
from common.protocol import SequenceGuard
from common.reliability import CommandOutcomes
from controller_node.controller_node import ControllerNode
from controller_node.safety_guard import SafetyGuard
from gateway.edge_decision import EdgeDecider
from server.server import Server
from server.dedup import Deduplicator


def command(id='one',**payload):
    return Message(type=CONTROL_COMMAND,source='A1',target='C1',payload={
        'command_id':id,'type':'IRRIGATION','duration':1,'gateway_generation':1,**payload})


@pytest.mark.parametrize('key,value',[('timestamp',float('inf')),('timestamp',float('nan')),('sequence',True),('attempt',0),('generation',-1),('protocol_version',2)])
def test_envelope_rejects_invalid_optional_fields(key,value):
    raw=command().to_dict();raw[key]=value
    with pytest.raises(MessageError):Message.from_dict(raw)


def test_legacy_envelope_and_optional_roundtrip():
    m=command();assert 'sequence' not in m.to_dict()
    m.sequence=1;m.attempt=2;m.protocol_version=1;m.generation=3
    assert Message.from_json(m.to_json()).to_dict()==m.to_dict()


def test_sequence_reorder_duplicate_and_new_boot():
    s=SequenceGuard()
    def m(seq,boot):return Message(type=SENSOR_DATA,source='B1',target='A1',sequence=seq,payload={'boot_id':boot})
    assert s.accept(m(2,'a'))
    assert not s.accept(m(1,'a')) and not s.accept(m(2,'a'))
    assert s.accept(m(1,'b'))


def test_lost_result_becomes_unknown_late_result_resolves_without_reexecution():
    o=CommandOutcomes(timeout=1);m=command()
    o.track(m,0);o.ack('one')
    assert o.expire(1)==[m]
    assert 'one' in o.unknown and not o.pending
    assert o.expire(2)==[]
    assert o.result('one')=='late'
    assert o.result('one')=='duplicate'


def test_concurrent_duplicate_commands_execute_once():
    async def run():
        c=ControllerNode('C1',time_scale=0)
        results=await asyncio.gather(c.process_command(command()),c.process_command(command()))
        assert [r['status'] for r in results]==['EXECUTED','DUPLICATE']
        assert c.metrics.get('executed')==1
    asyncio.run(run())


def test_missing_command_id_and_invalid_values_are_safe():
    c=ControllerNode('C1');m=command();m.payload.pop('command_id')
    assert asyncio.run(c.process_command(m))['reason']=='INVALID_COMMAND_ID'
    g=SafetyGuard()
    for value in (float('nan'),float('inf')):
        assert g.check('one','IRRIGATION',value,time.time())[1]=='INVALID_DURATION'
    assert g.check('one',[] ,1,time.time())[1]=='INVALID_TYPE'
    assert g.check('one','IRRIGATION',1,time.time(),gateway_generation='bad')[1]=='STALE_GENERATION'


def test_invalid_policy_is_atomic_and_old_policy_replay_ignored():
    d=EdgeDecider();old=dict(d.policy)
    with pytest.raises(MessageError):d.update_policy({'policy_version':3,'irrigation_duration':float('nan')})
    assert d.policy_version==0 and d.policy==old
    d.update_policy({'policy_version':2,'soil_moisture_threshold':20})
    assert not d.update_policy({'policy_version':1,'soil_moisture_threshold':30})[0]
    assert d.policy['soil_moisture_threshold']==20


def test_rejected_upload_does_not_poison_dedup(tmp_path):
    s=Server(db_path=str(tmp_path/'db'));s.db.init_schema();s.dedup=Deduplicator(s.db.conn,auto_commit=False)
    bad=Message(type=SENSOR_DATA,source='A1',target='SERVER',message_id='bad',payload={'record':[]})
    s._store(bad)
    assert s.db.count('processed_message')==0
    bad.payload={'record':{'sensor_node_id':'B1','timestamp':1,'temperature':25}}
    s._store(bad);s._store(bad)
    assert s.db.count('sensor_data')==1 and s.dedup.ignored==1
    s.db.close()
