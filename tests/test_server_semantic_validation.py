import pytest
from common.messages import Message
from server.server import Server
from server.dedup import Deduplicator

VALID = {
 'SENSOR_DATA': {'record':{'sensor_node_id':'B1','temperature':25}},
 'CONTROL_COMMAND': {'command_id':'c','controller_id':'C1','type':'IRRIGATION','duration':1,'gateway_generation':1},
 'CONTROL_RESULT': {'command_id':'c','controller_id':'C1','command_type':'IRRIGATION','status':'EXECUTED','generation':1},
 'ALERT': {'alert_type':'SENSOR_FAULT','message':'range','sensor_node_id':'B1'},
 'HEARTBEAT': {'gateway_id':'A1','status':'ONLINE','peer_id':'A2','peer_status':'ONLINE','generation':1,'role':'ACTIVE'},
}
TABLES={'SENSOR_DATA':'sensor_data','CONTROL_COMMAND':'controller_command','CONTROL_RESULT':'controller_result','ALERT':'alert','HEARTBEAT':'gateway_heartbeat'}
INVALID=[('SENSOR_DATA',{'record':{'sensor_node_id':'?','temperature':25}}),
 ('SENSOR_DATA',{'record':{'sensor_node_id':'B1','temperature':'hot'}}),
 ('SENSOR_DATA',{'record':{'sensor_node_id':'B1','temperature':float('nan')}}),
 ('CONTROL_COMMAND',{'command_id':'?'}),('CONTROL_COMMAND',{'duration':True}),
 ('CONTROL_COMMAND',{'controller_id':'B1'}),('CONTROL_COMMAND',{'gateway_generation':-1}),
 ('CONTROL_COMMAND',{'type':'PUMP'}),('CONTROL_RESULT',{'status':'OK'}),
 ('CONTROL_RESULT',{'command_id':''}),('CONTROL_RESULT',{'generation':True}),
 ('CONTROL_RESULT',{'reason':{}}),('CONTROL_RESULT',{'status':'NOT_DISPATCHED','reason':None}),
 ('ALERT',{'alert_type':''}),('ALERT',{'message':[]}),('ALERT',{'sensor_node_id':'C1'}),
 ('ALERT',{'metadata':{'invalid':object()}}),('HEARTBEAT',{'gateway_id':'A2'}),
 ('HEARTBEAT',{'status':'OK'}),('HEARTBEAT',{'peer_id':'A1'}),('HEARTBEAT',{'generation':1.5}),
 ('HEARTBEAT',{'role':'OWNER'})]

@pytest.mark.parametrize('kind,patch',INVALID)
def test_invalid_upload_does_not_consume_identity_and_corrected_replay_commits(kind,patch,tmp_path):
    s=Server(db_path=str(tmp_path/'db'));s.db.init_schema();s.dedup=Deduplicator(s.db.conn,auto_commit=False)
    try:
        m=Message(type=kind,source='A1',target='SERVER',message_id='same',payload={**VALID[kind],**patch})
        assert not s._store(m)
        assert s.db.count('processed_message')==s.db.count(TABLES[kind])==0
        m.payload=VALID[kind]
        assert s._store(m) and s._store(m)
        assert s.db.count(TABLES[kind])==s.db.count('processed_message')==1
    finally:s.db.close()

def test_db_failure_rolls_back_dedup_and_metrics(monkeypatch,tmp_path):
    import sqlite3
    s=Server(db_path=str(tmp_path/'db'));s.db.init_schema();s.dedup=Deduplicator(s.db.conn,auto_commit=False)
    def fail(**kw):raise sqlite3.OperationalError('simulated before business insert')
    monkeypatch.setattr(s.db,'insert_sensor_data',fail)
    assert not s._store(Message(type='SENSOR_DATA',source='A1',target='SERVER',payload=VALID['SENSOR_DATA']))
    assert s.db.count('processed_message')==s.dedup.processed==0
    assert s.metrics.get('sensor_messages')==0
    s.db.close()
