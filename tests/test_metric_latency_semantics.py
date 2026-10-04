import pytest
from experiments.metrics import TransportRecorder
from common.messages import Message, CONTROL_COMMAND, ACK, PERSISTED_ACK

def test_retry_attempt_latency_and_logical_latency_have_distinct_origins(monkeypatch):
    now=[0.0];monkeypatch.setattr('experiments.metrics.time.monotonic',lambda:now[0])
    r=TransportRecorder();m=Message(type=CONTROL_COMMAND,source='A1',target='C1',message_id='cmd',attempt=1)
    r('send_attempt',m);r('dropped',m)
    now[0]=2;m.attempt=2;r('send_attempt',m);r('sent',m)
    now[0]=2.1;r('delivered',m)
    assert r.attempt_latencies==pytest.approx([0.1])
    assert r.logical_latencies==pytest.approx([2.1])
    now[0]=2.2;r('delivered',Message(type=ACK,source='C1',target='A1',payload={'ack_message_id':'cmd'}))
    assert r.ack_latencies==[2.2]
    now[0]=2.3;r('sent',m);now[0]=2.4;r('delivered',m)
    assert r.attempt_latencies==pytest.approx([0.1,0.1]) and len(r.logical_latencies)==1
    assert r.events[0]['message']['attempt']==1

def test_replayed_upload_persisted_ack_latency_is_logical_and_duplicates_do_not_add_observations(monkeypatch):
    now=[0.0];monkeypatch.setattr('experiments.metrics.time.monotonic',lambda:now[0])
    r=TransportRecorder();m=Message(type='SENSOR_DATA',source='A1',target='SERVER',message_id='sample')
    r('send_attempt',m);r('sent',m);now[0]=0.1;r('delivered',m)
    now[0]=3;r('send_attempt',m);r('sent',m);now[0]=3.1;r('delivered',m)
    ack=Message(type=PERSISTED_ACK,source='SERVER',target='A1',payload={'ack_message_id':'sample','persisted':True})
    now[0]=3.2;r('delivered',ack);r('delivered',ack)
    assert r.persisted_ack_latencies==[3.2] and len(r.logical_latencies)==1
    assert len(r.attempt_latencies)==2
