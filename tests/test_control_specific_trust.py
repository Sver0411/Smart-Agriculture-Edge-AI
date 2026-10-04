import asyncio
import pytest
from common.messages import Message, SENSOR_DATA
from gateway.gateway import Gateway

@pytest.mark.parametrize('bad,soil,temp,expected',[
    ('light',10,25,'IRRIGATION'),('light',50,40,'VENTILATION'),
    ('soil_moisture',10,40,'VENTILATION'),('temperature',10,40,'IRRIGATION'),
    ('soil_moisture',10,25,None),('humidity',10,25,'IRRIGATION')])
def test_rule_uses_only_healthy_action_dependencies(bad,soil,temp,expected):
    async def run():
        g=Gateway('A1')
        health={k:{'state':'HEALTHY','valid':True} for k in ('soil_moisture','temperature','humidity','light')}
        health[bad]={'state':'FAULT','valid':False,'fault_flags':['STUCK']}
        await g._process_sensor_message(Message(type=SENSOR_DATA,source='B1',target='A1',payload={
            'data':{'soil_moisture':soil,'temperature':temp,'humidity':50,'light':800},
            'health':health,'health_state':'FAULT','usable_for_control':False}))
        if expected:assert (await g.command_queue.get())[0].payload['type']==expected
        else:assert g.command_queue.empty()
        record=(await g.upload_queue.get()).payload['record']
        assert record['health_state']=='FAULT' and bad not in record['trusted_channels']
    asyncio.run(run())

@pytest.mark.parametrize('engine',['logistic','tree','mlp'])
@pytest.mark.parametrize('bad',['light','soil_moisture','humidity','temperature'])
def test_learned_engine_never_runs_on_untrusted_feature(engine,bad):
    async def run():
        g=Gateway('A1',decision_engine=engine)
        h={k:{'state':'HEALTHY','valid':True} for k in ('soil_moisture','temperature','humidity','light')}
        h[bad]={'state':'DEGRADED','valid':True}
        await g._process_sensor_message(Message(type=SENSOR_DATA,source='B1',target='A1',payload={
            'data':{'soil_moisture':10,'temperature':40,'humidity':50,'light':800},'health':h,'health_state':'DEGRADED'}))
        assert g.command_queue.empty() and g.metrics.get('decision_calls')==0
    asyncio.run(run())


def test_legacy_physical_channel_health_without_valid_flag_can_ventilate():
    # Frozen physical B1 protocol: state/score/flags, no Python-only valid field.
    async def run():
        g=Gateway('A1')
        await g._process_sensor_message(Message(type=SENSOR_DATA,source='B1',target='A1',payload={
            'node_mode':'physical','data':{'temperature':40,'humidity':60},'usable_for_control':True,
            'health':{'temperature':{'state':'HEALTHY','score':100,'flags':0},
                      'humidity':{'state':'HEALTHY','score':100,'flags':0}}}))
        assert (await g.command_queue.get())[0].payload['type']=='VENTILATION'
    asyncio.run(run())
