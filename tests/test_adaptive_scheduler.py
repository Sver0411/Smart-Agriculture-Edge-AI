from copy import deepcopy
import pytest
from common.settings import node_settings
from sensor_node.adaptive_scheduler import transition, hysteresis_bounds, AdaptiveScheduler
from sensor_node.adaptive_sense import AdaptiveSense

HEALTHY={'state':'HEALTHY','usable_for_control':True}
BOUNDS=hysteresis_bounds(2,6,0.2)

@pytest.mark.parametrize('state,score,expected',[
 ('STABLE',0,'STABLE'),('STABLE',3,'ACTIVE'),('STABLE',8,'ALERT'),
 ('ALERT',5,'ALERT'),('ALERT',0,'ACTIVE'),('ACTIVE',2,'ACTIVE'),('ACTIVE',1,'STABLE')])
def test_hysteresis_immediate_escalation_and_one_step_relaxation(state,score,expected):
    assert transition(state,score,BOUNDS)==expected


def test_stable_ladder_and_heartbeat_upload():
    settings=node_settings();settings['adaptive']['upload']['heartbeat_s']=300
    s=AdaptiveScheduler(settings)
    intervals=[];uploads=[]
    for t in range(0,301,20):
        d=s.update(t,{'temperature':25,'humidity':60,'soil_moisture':40,'light':800})
        intervals.append(d.interval_s);uploads.append(d.upload_requested)
    assert intervals[:7]==[20,20,20,40,40,40,60]
    assert uploads[0] and uploads[3] and uploads[6]
    assert not uploads[7]
    d=s.update(420,{'temperature':25,'humidity':60,'soil_moisture':40,'light':800})
    assert d.upload_requested


def test_active_ladder_event_upload_and_normalized_score():
    settings=node_settings();settings['adaptive']['active_threshold']=100
    s=AdaptiveScheduler(settings)
    s.update(0,{'temperature':25})
    d=s.update(1,{'temperature':27})
    assert d.state=='ACTIVE' and d.interval_s==15 and d.channel_scores['temperature']==4
    assert d.upload_requested
    assert s.update(2,{'temperature':27}).interval_s==15
    assert s.update(3,{'temperature':27}).interval_s==10


def test_fault_spike_does_not_contaminate_score_and_recovery_baseline():
    s=AdaptiveSense()
    s.update({'temperature':25},HEALTHY,0)
    r=s.update({'temperature':999},{'state':'FAULT','usable_for_control':False},1)
    assert r['score'] is None and not r['detected_event'] and r['interval_s']==20
    assert s.core.analyzer.baseline('temperature')==25
    r=s.update({'temperature':26},HEALTHY,2)
    assert r['score']==0 and r['upload_requested']


def test_degraded_is_cautious_and_not_environment_alert():
    s=AdaptiveSense()
    r=s.update({'temperature':500},{'state':'DEGRADED','usable_for_control':False},0)
    assert r['state']=='ACTIVE' and r['interval_s']==10
    assert not r['detected_event'] and r['score'] is None


def test_fault_aware_replay_is_deterministic():
    def replay():
        s=AdaptiveSense()
        return [s.update({'temperature':v},HEALTHY,t) for t,v in [(0,25),(20,25.1),(40,30),(45,25)]]
    assert replay()==replay()
