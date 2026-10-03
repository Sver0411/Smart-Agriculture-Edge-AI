import asyncio
from copy import deepcopy
import math
import pytest
from common.settings import node_settings, load_settings, validate_settings
from common.messages import SENSOR_DATA, Message
from gateway.gateway import Gateway
from sensor_node.sensor_trust import SensorTrust, ChannelTrust


def cfg(**updates):
    return {**node_settings()['trust_channels']['temperature'], **updates}


def test_range_and_recovery():
    c=ChannelTrust(cfg())
    r=c.update(100,0)
    assert r['state']=='FAULT' and r['fault_flags']==['RANGE'] and r['health_score']==45
    assert c.update(25,1)['fault_flags']==['SPIKE']


def test_stuck_is_window_spread():
    c=ChannelTrust(cfg(stuck_window=3))
    assert not c.update(25,0)['fault_flags']
    assert not c.update(25,1)['fault_flags']
    assert c.update(25,2)['fault_flags']==['STUCK']
    assert 'STUCK' not in c.update(26,3)['fault_flags']


def test_spike_reports_excursion_and_return():
    c=ChannelTrust(cfg())
    c.update(25,0)
    assert c.update(33,1)['fault_flags']==['SPIKE']
    assert c.update(25,2)['fault_flags']==['SPIKE']
    assert not c.update(25.2,3)['fault_flags']


@pytest.mark.parametrize('dt',[1,5])
def test_drift_is_per_second_and_requires_confirmation(dt):
    c=ChannelTrust(cfg(drift_window=3,drift_threshold=0.1,spike_threshold=50))
    for i in range(4):
        assert 'DRIFT' not in c.update(20+i*dt*0.2,i*dt)['fault_flags']
    assert 'DRIFT' in c.update(20+4*dt*0.2,4*dt)['fault_flags']


@pytest.mark.parametrize('value',[None,float('nan'),float('inf'),True,'bad'])
def test_missing_confirmation_never_makes_invalid_measurement_usable(value):
    t=SensorTrust()
    sample={'temperature':value,'humidity':60,'soil_moisture':40,'light':800}
    assert not t.update(sample,0)['usable_for_control']
    t.update(sample,1)
    r=t.update(sample,2)
    assert r['state']=='FAULT' and 'MISSING' in r['fault_flags']
    assert r['channels']['humidity']['state']=='HEALTHY'


def test_channels_have_independent_history():
    t=SensorTrust()
    sample={'temperature':25,'humidity':60,'soil_moisture':40,'light':800}
    t.update(sample,0)
    r=t.update({**sample,'temperature':35},1)
    assert r['state']=='DEGRADED'
    assert r['channels']['temperature']['fault_flags']==['SPIKE']
    assert not r['channels']['soil_moisture']['fault_flags']


@pytest.mark.parametrize('state',['FAULT','DEGRADED'])
def test_unhealthy_data_is_uploaded_but_blocks_commands(state):
    async def run():
        g=Gateway('A1');g._seed_registry()
        await g._process_sensor_message(Message(type=SENSOR_DATA,source='B1',target='A1',
            payload={'data':{'soil_moisture':10,'temperature':40},'health_state':state,'usable_for_control':True}))
        assert g.command_queue.empty()
        assert (await g.upload_queue.get()).payload['record']['health_state']==state
    asyncio.run(run())


def test_config_rejects_incoherent_ladder_and_nonfinite_trust():
    settings=load_settings()
    assert settings['system']['GATEWAY_PORTS']=={'A1':9201,'A2':9202}
    bad=deepcopy(settings);bad['node']['adaptive']['ladders']['stable']=[60,20]
    with pytest.raises(ValueError):validate_settings(bad)
    bad=deepcopy(settings);bad['node']['trust_channels']['temperature']['spike_threshold']=math.inf
    with pytest.raises(ValueError):validate_settings(bad)
