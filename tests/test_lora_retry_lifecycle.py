import asyncio
import pytest
from common.messages import Message
from common.lora.delivery import DeliveryWindow, Stage
from common.lora.transport import SimulatedLoRa


def sample():
    return Message(type='SENSOR_DATA',source='B1',target='A1',message_id='stable-evidence',
        payload={'data':{'temperature':25},'padding':'x'*500})


def test_finite_window_preserves_failed_evidence_at_capacity():
    w=DeliveryWindow(capacity=1,attempts=2,timeout=1);m=sample();w.admit(m,0)
    assert w.due(0)==[m] and w.due(1)==[m]
    assert w.due(2)==[] and w.pending[m.message_id]['failed']
    assert w.due(100000)==[] and len(w.pending)==1
    other=sample();other.message_id='other'
    with pytest.raises(ValueError,match='capacity'):w.admit(other,100000)


def test_long_outage_receiver_restart_and_ack_loss():
    class Wire:
        def __init__(self):self.lines=[]
        def write(self,line):self.lines.append(line)
        async def drain(self):pass
    async def scenario():
        w=DeliveryWindow(capacity=1,attempts=2,timeout=1,recovery_interval=60)
        m=sample();w.admit(m,0);radio=SimulatedLoRa(seed=42);wire=Wire();radio.outage=True
        for now in (0,1):
            for message in w.due(now):await radio(wire,message)
        assert w.due(2)==[]
        assert w.due(61)==[]
        assert w.due(62)==[m]
        assert len(w.pending)==1 and not wire.lines
        radio.outage=False;radio.reset_receiver('A1')
        for message in w.due(122):await radio(wire,message)
        assert len(wire.lines)==1
        a=Message(type='PERSISTED_ACK',source='A1',target='B1',payload={'ack_message_id':m.message_id,
            'persisted':True,'scope':'GATEWAY_OUTBOX','delivery_contract':'gateway-durable-v1'})
        assert not w.confirm(a,Stage.FRAME_ACCEPTED)
        assert not w.confirm(a,Stage.MESSAGE_REASSEMBLED)
        # ACK is lost: the same identity reassembles after receiver restart.
        radio.reset_receiver('A1')
        for message in w.due(242):await radio(wire,message)
        assert len(wire.lines)==2 and wire.lines[0]==wire.lines[1]
        assert w.confirm(a,Stage.GATEWAY_DURABLE)
        assert not w.pending
    asyncio.run(scenario())


def test_probes_never_exceed_capped_rate():
    w=DeliveryWindow(attempts=1,timeout=1,recovery_interval=60,max_recovery_interval=300)
    m=sample();w.admit(m,0);w.due(0);w.due(1)
    now=61
    for _ in range(50):
        assert w.due(now)==[m]
        p=w.pending[m.message_id]
        assert 60<=p['due']-now<=300
        assert w.due(p['due']-1)==[]
        now=p['due']
    assert len(w.pending)==1
