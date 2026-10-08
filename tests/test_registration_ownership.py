"""Deterministic ownership races: registration never creates authority."""
import asyncio
import pytest
from common.messages import Message, NODE_REGISTER, NODE_REGISTER_ACK, HEARTBEAT
from gateway.gateway import Gateway
from sensor_node.sensor_node import SensorNode
from controller_node.controller_node import ControllerNode
from common import config

@pytest.mark.parametrize('node,gateway',[('B1','A2'),('C1','A2'),('B2','A1'),('C2','A1')])
def test_wrong_gateway_rejects_without_changing_owner(node,gateway,monkeypatch):
    g=Gateway(gateway);replies=[]
    async def send(w,m):replies.append(m)
    monkeypatch.setattr('gateway.gateway.send_message',send)
    before=g.registry.get(node).as_dict()
    asyncio.run(g._handle_register(object(),Message(type=NODE_REGISTER,source=node,target=gateway,
        payload={'node_type':config.SENSOR if node.startswith('B') else config.CONTROLLER})))
    assert replies[0].payload['accepted'] is False
    assert replies[0].payload['reason']=='NOT_OWNER'
    assert g.registry.get(node).as_dict()==before
    assert node not in g.connections

@pytest.mark.parametrize('node',['B1','C1'])
def test_takeover_authorizes_registration_and_recovery_cannot_steal(node,monkeypatch):
    a2=Gateway('A2');a2._takeover();replies=[]
    async def send(w,m):replies.append(m)
    monkeypatch.setattr('gateway.gateway.send_message',send)
    asyncio.run(a2._handle_register(object(),Message(type=NODE_REGISTER,source=node,target='A2',
        payload={'node_type':config.SENSOR if node.startswith('B') else config.CONTROLLER,'generation':1})))
    assert replies[-1].payload['accepted'] and replies[-1].payload['generation']==2
    old=Gateway('A1');old._on_peer_heartbeat(Message(type=HEARTBEAT,source='A2',target='A1',
        payload={'generation':2,'ownership':{n:{'owner_gateway':'A2','generation':2} for n in ['B1','C1']}}))
    asyncio.run(old._handle_register(object(),Message(type=NODE_REGISTER,source=node,target='A1',
        payload={'node_type':config.SENSOR if node.startswith('B') else config.CONTROLLER,'generation':2})))
    assert replies[-1].payload['accepted'] is False
    assert old.registry.get(node).owner_gateway=='A2'

@pytest.mark.parametrize('cls,node',[(SensorNode,'B1'),(ControllerNode,'C1')])
def test_redirect_then_same_epoch_competitor_rejected_new_epoch_accepted(cls,node,monkeypatch):
    n=cls(node)
    async def send(w,m):pass
    module='sensor_node.sensor_node' if cls is SensorNode else 'controller_node.controller_node'
    monkeypatch.setattr(module+'.send_message',send)
    replies=[]
    async def read(r):return replies.pop(0)
    monkeypatch.setattr(module+'.read_message',read)
    def reply(source,owner,epoch,accepted):return Message(type=NODE_REGISTER_ACK,source=source,target=node,
        payload={'owner_gateway':owner,'generation':epoch,'accepted':accepted})
    replies.append(reply('A2','A1',1,False))
    assert not asyncio.run(n._register(None,None,'A2'))
    assert n._candidates()[0][0]=='A1'
    replies.append(reply('A1','A1',1,True));assert asyncio.run(n._register(None,None,'A1'))
    replies.append(reply('A2','A2',1,True));assert not asyncio.run(n._register(None,None,'A2'))
    replies.append(reply('A2','A2',2,True));assert asyncio.run(n._register(None,None,'A2'))

@pytest.mark.parametrize('cls,node',[(SensorNode,'B1'),(ControllerNode,'C1')])
def test_malformed_registration_owner_is_rejected_without_crashing(cls,node,monkeypatch):
    n=cls(node);module='sensor_node.sensor_node' if cls is SensorNode else 'controller_node.controller_node'
    async def send(w,m):pass
    async def read(r):return Message(type=NODE_REGISTER_ACK,source='A1',target=node,
        payload={'owner_gateway':[],'generation':1,'accepted':True})
    monkeypatch.setattr(module+'.send_message',send);monkeypatch.setattr(module+'.read_message',read)
    assert not asyncio.run(n._register(None,None,'A1'))

def test_deposed_peer_late_heartbeat_timeout_does_not_repeat_takeover():
    g = Gateway('A2', heartbeat_timeout=1)
    g.peer_last_seen = 0
    assert g.evaluate_peer_status(now=10) == config.OFFLINE
    assert g.ownership.generation == 2
    assert g._on_peer_heartbeat(Message(type=HEARTBEAT, source='A1', target='A2',
        payload={'generation': 1, 'ownership': {}}))
    assert g.evaluate_peer_status(now=g.peer_last_seen) == config.ONLINE
    assert g.evaluate_peer_status(now=g.peer_last_seen + 10) == config.OFFLINE
    assert g.ownership.generation == 2
    assert g.metrics.get('failovers') == 1


def test_local_monitor_pause_does_not_create_equal_epoch_takeovers(monkeypatch):
    a1, a2 = [Gateway(name, heartbeat_timeout=.6) for name in ['A1', 'A2']]
    for g, last_seen in [(a1, .458), (a2, .321)]:
        g.peer_last_seen = last_seen
        g._observe_peer_monitor_tick(.457)
        g._observe_peer_monitor_tick(1.060)
        assert g.evaluate_peer_status(1.060) == config.UNKNOWN
        assert g.ownership.generation == 1
        assert g.peer_last_seen == last_seen
    # Only A1 receives the resumed reverse heartbeat. A1->A2 stays dropped.
    monkeypatch.setattr('gateway.gateway.time.monotonic', lambda: 1.065)
    assert a1._on_peer_heartbeat(Message(type=HEARTBEAT, source='A2', target='A1',
        payload={'generation':1,'ownership':{}}))
    assert a1.evaluate_peer_status(1.065) == config.ONLINE
    for tick in [1.160, 1.260, 1.360, 1.460, 1.560, 1.661]:
        a2._observe_peer_monitor_tick(tick)
    assert a2.evaluate_peer_status(1.661) == config.OFFLINE
    assert a2.ownership.generation == 2
    assert a1._on_peer_heartbeat(Message(type=HEARTBEAT, source='A2', target='A1',
        payload={'generation':2,'ownership':{n:{'owner_gateway':'A2','generation':2}
                                             for n in ['B1','C1','B2','C2']}}))
    assert a1.ownership.role == config.STANDBY
    assert a1.registry.get('C1').owner_gateway == 'A2'


def test_resumed_monitor_still_times_out_without_valid_peer():
    g = Gateway('A2', heartbeat_timeout=.6)
    g.peer_last_seen = .321
    g._observe_peer_monitor_tick(.457)
    g._observe_peer_monitor_tick(1.060)
    assert g.evaluate_peer_status(1.060) == config.UNKNOWN
    assert not g._on_peer_heartbeat(Message(type=HEARTBEAT, source='B1', target='A2',
        payload={'generation':1,'ownership':{}}))
    for tick in [1.160, 1.260, 1.360, 1.460, 1.560, 1.661]:
        g._observe_peer_monitor_tick(tick)
    assert g.evaluate_peer_status(1.661) == config.OFFLINE
    assert g.ownership.generation == 2
    assert g.metrics.get('peer_monitor_stalls') == 1
    assert g.metrics.get('failovers') == 1
