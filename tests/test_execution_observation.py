"""Execution-branch observations must distinguish replay from a second action."""
import asyncio
import pytest
from common.messages import Message
from controller_node.controller_node import ControllerNode
from controller_node.safety_guard import SafetyGuard
from common.state_store import StateStore
from experiments.edgefaultlab import adapt

@pytest.mark.parametrize('simulate_broken_fencing',[False,True])
def test_replay_and_actual_second_execution_are_distinguishable(tmp_path,monkeypatch,simulate_broken_fencing):
    async def scenario():
        c=ControllerNode('C1',time_scale=0,emit_execution_events=True,
            safety_guard=SafetyGuard(store=StateStore(tmp_path/'c.db'),cooldown={'IRRIGATION':0}))
        messages=[]
        async def send(w,m):messages.append(m.to_dict())
        monkeypatch.setattr('controller_node.controller_node.send_message',send)
        m=Message(type='CONTROL_COMMAND',source='A1',target='C1',payload={
            'command_id':'once','type':'IRRIGATION','duration':1,'gateway_generation':1})
        await c.process_command(m,object())
        if simulate_broken_fencing:
            # A fault model of the prohibited second action, while its durable
            # result may reuse the very same cached wire identity/content.
            monkeypatch.setattr(c.guard,'check',lambda **kwargs:(True,None))
            monkeypatch.setattr(c.recent_commands,'begin',lambda *args:None)
        await c.process_command(m,object())
        events=[x for x in messages if x['payload'].get('event')=='ACTUATOR_EXECUTED']
        results=[x for x in messages if x['type']=='CONTROL_RESULT']
        assert len(results)==2 and results[0]==results[1]
        assert len(events)==(2 if simulate_broken_fencing else 1)
        unique=len({e['payload']['command_id'] for e in events})==len(events)
        assert unique is (not simulate_broken_fencing)
        assert c.metrics.get('executed')==len(events)
    asyncio.run(scenario())


def test_external_adapter_preserves_intent_and_requires_actual_events(tmp_path):
    template={'processes':[],'links':[],'faults':[], 'assertions':[
        {'assert':'unique','link':'nodes_to_gateway_a1','match':{'type':'CONTROL_RESULT','payload.status':'EXECUTED'},
         'key':'payload.command_id','description':'a command is executed at most once'}]}
    spec=adapt(template,tmp_path,tmp_path/'run')
    import json
    assert json.loads((tmp_path/'run/original_assertions.json').read_text())[0]==template['assertions'][0]
    assert 'original_assertions' not in spec
    assert spec['assertions'][0]['assert']=='unique'
    assert spec['assertions'][0]['key']=='payload.command_id'
    assert spec['assertions'][0]['match']=={'type':'NODE_STATUS','payload.event':'ACTUATOR_EXECUTED'}
    assert spec['assertions'][1]['min']==1
    assert '--emit-execution-events' in spec['processes'][-1]['command']
