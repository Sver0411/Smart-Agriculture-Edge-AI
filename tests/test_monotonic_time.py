from common.reliability import AckTracker, CommandOutcomes
from common.messages import Message, CONTROL_COMMAND
from gateway.gateway import Gateway
from controller_node.safety_guard import SafetyGuard


def test_wall_clock_jumps_do_not_affect_ack_peer_node_and_result_deadlines(monkeypatch):
    elapsed=[100.0];wall=[1000.0]
    monkeypatch.setattr('time.monotonic',lambda:elapsed[0]);monkeypatch.setattr('time.time',lambda:wall[0])
    g=Gateway('A1');g.peer_last_seen=100;g.registry.touch('B1')
    m=Message(type=CONTROL_COMMAND,source='A1',target='C1',payload={'command_id':'one'})
    tracker=AckTracker(timeout=2);tracker.track(m)
    outcomes=CommandOutcomes(timeout=2);outcomes.track(m,100);outcomes.ack('one')
    for jump in (100000.0,-100000.0):
        wall[0]=jump
        assert tracker.due()==[] and g.evaluate_peer_status()=='ONLINE'
        assert g.registry.expire(timeout=2)==[] and outcomes.expire(elapsed[0])==[]
    elapsed[0]=103
    assert tracker.due()==[m] and outcomes.expire(elapsed[0])==[m]
    assert g.registry.expire(timeout=2)[0].node_id=='B1'
    elapsed[0]=111
    assert g.evaluate_peer_status()=='OFFLINE'


def test_cold_start_absent_peer_can_time_out_without_ever_receiving_heartbeat():
    g=Gateway('A2',heartbeat_timeout=1);g.peer_started_at=10
    assert g.evaluate_peer_status(10.5)=='UNKNOWN'
    assert g.evaluate_peer_status(11.1)=='OFFLINE'
    assert g.registry.get('C1').owner_gateway=='A2'
    assert g.ownership.generation==2


def test_cooldown_uses_monotonic_while_ttl_uses_wall_clock(monkeypatch):
    elapsed=[10];wall=[1000]
    monkeypatch.setattr('time.monotonic',lambda:elapsed[0]);monkeypatch.setattr('time.time',lambda:wall[0])
    g=SafetyGuard(cooldown={'IRRIGATION':60});g.commit('one','IRRIGATION')
    wall[0]=100000;elapsed[0]=20
    assert g.check('two','IRRIGATION',1,wall[0])[1]=='COOLDOWN'
    wall[0]=-100000;elapsed[0]=71
    assert g.check('three','IRRIGATION',1,wall[0])==(True,None)
    assert g.check('expired','IRRIGATION',1,wall[0]-100)[1]=='EXPIRED'
