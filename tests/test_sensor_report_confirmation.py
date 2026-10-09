import asyncio
import pytest
from common.messages import Message
from common.state_store import StateStore
from sensor_node.sensor_node import SensorNode
from sensor_node.report_delivery import SensorReportWindow,prepare_report
from test_b1_gateway_receipts import sample
from gateway.gateway import Gateway


def ack(message):
    return Message(type='PERSISTED_ACK',source='A1',target='B1',payload={
        'ack_message_id':message.message_id,'scope':'GATEWAY_OUTBOX','persisted':True,
        'delivery_contract':'gateway-durable-v1'})


def setup(tmp_path):
    node=SensorNode('B1',delivery_mode='gateway-durable',state_path=str(tmp_path/'b.db'))
    reading={'soil_moisture':20,'temperature':25,'humidity':60,'light':500}
    trust=node.trust.update(reading,timestamp=1)
    node.scheduler.update(reading,trust,1)
    m=sample();m.payload['boot_id']=node.boot_id
    prepare_report(m,1,high=True)
    node.report_window.admit(m,reading,trust,1)
    return node,m


@pytest.mark.parametrize('fault',['drop','ack_loss','rejected'])
def test_network_write_does_not_advance_baseline(tmp_path,fault,monkeypatch):
    async def scenario():
        node,m=setup(tmp_path)
        outgoing=node.report_window.due(1,'A1')[0]
        g=Gateway('A1',queue_path=str(tmp_path/'a.db'));g.sensor_boots['B1']=node.boot_id
        replies=[]
        async def send(w,m):replies.append(m)
        monkeypatch.setattr('gateway.gateway.send_message',send)
        g.connections['B1']=object()
        if fault=='rejected':g.offline_queue.max_messages=1;g.offline_queue.reserved_messages=0;g.offline_queue.enqueue(Message(type='ALERT',source='A1',target='SERVER',payload={'severity':'CRITICAL'}))
        if fault!='drop':await g._process_sensor_message(outgoing)
        assert node.scheduler._confirmed_sequence is None
        retry=node.report_window.due(4,'A1')[0]
        assert retry.message_id==m.message_id
        assert node.report_window.evidence
        # Recovery of the same original sample changes no event history.
        if fault=='rejected':g.offline_queue.delete(g.offline_queue.peek()[0][0])
        await g._process_sensor_message(retry)
        assert node.report_window.confirm(ack(m),node.scheduler,'A1')
        assert node.scheduler._confirmed_sequence==m.sequence
        assert not node.report_window.evidence
        g.offline_queue.close()
    asyncio.run(scenario())


def test_restart_high_retained_old_boot_ack_does_not_advance_new_baseline(tmp_path):
    node,m=setup(tmp_path)
    recovered=SensorNode('B1',delivery_mode='gateway-durable',state_path=str(tmp_path/'b.db'))
    old=recovered.report_window.due(2,'A1')[0]
    assert old.message_id==m.message_id and old.payload['delivery_age_ms'] is None
    assert recovered.report_window.confirm(ack(m),recovered.scheduler,'A1')
    assert recovered.scheduler._confirmed_sequence is None


@pytest.mark.parametrize('change',[{'scope':'SERVER_SQLITE'},{'persisted':False},{'delivery_contract':'wrong'}])
def test_ack_scope_validated(tmp_path,change):
    node,m=setup(tmp_path);a=ack(m);a.payload.update(change)
    assert not node.report_window.confirm(a,node.scheduler,'A1')
    assert node.report_window.evidence and node.scheduler._confirmed_sequence is None


def test_normal_is_ram_only_and_events_keep_running(tmp_path):
    node,m=setup(tmp_path)
    assert node.report_window.confirm(ack(m),node.scheduler,'A1')
    m=sample(2);m.payload['boot_id']=node.boot_id;prepare_report(m,2,high=False)
    node.report_window.admit(m,{'temperature':25},{'state':'HEALTHY'},2)
    assert SensorNode('B1',delivery_mode='gateway-durable',state_path=str(tmp_path/'b.db')).report_window.evidence=={}
    assert node.report_window.evidence
