"""Fault boundaries use real file-backed SQLite and the public protocol."""
import asyncio
import sqlite3
import pytest
from common.messages import Message, CONTROL_COMMAND, PERSISTED_ACK
from common.state_store import StateStore, StateError
from controller_node.controller_node import ControllerNode
from controller_node.recent_commands import RecentCommandStore, CONTRACT
from gateway.gateway import Gateway


def command():
    return Message(type=CONTROL_COMMAND,source='A1',target='C1',message_id='cmd',
        payload={'command_id':'cmd','type':'IRRIGATION','duration':1,'gateway_generation':1})


def controller(tmp_path):
    c=ControllerNode('C1',state_path=str(tmp_path/'c.db'),time_scale=0)
    c.guard.set_ownership('A1',1)
    return c


def pending(c):
    return Message.from_dict(next(iter(c.recent_commands.pending_results.values())))


def test_commit_ack_duplicate_and_both_restarts(tmp_path,monkeypatch):
    async def scenario():
        c=controller(tmp_path);await c.process_command(command())
        original=pending(c);g=Gateway('A1',queue_path=str(tmp_path/'a.db'))
        replies=[]
        async def send(w,m):replies.append(m)
        monkeypatch.setattr('gateway.gateway.send_message',send)
        original._result_writer=object()
        assert await g._process_control_result(original)
        assert [m.payload['result_state'] for m in replies]==['RESULT_RECEIVED','RESULT_DURABLY_STORED']
        # Drop the ACK after commit, then restart the gateway and replay.
        g.offline_queue.delete(g.offline_queue.peek()[0][0]);g.offline_queue.close()
        g=Gateway('A1',queue_path=str(tmp_path/'a.db'))
        assert await g._process_control_result(original)
        assert g.offline_queue.count()==0 and g.metrics.get('result_duplicates')==1
        c=controller(tmp_path)
        assert pending(c).to_dict()==original.to_dict()
        assert c._accept_result_ack(replies[-1],'A1')
        assert not c.recent_commands.pending_results
        assert not controller(tmp_path).recent_commands.pending_results
        result=await c.process_command(command())
        assert result['status']=='DUPLICATE' and c.metrics.get('executed')==0
    asyncio.run(scenario())


@pytest.mark.parametrize('fault',['database','capacity','identity_conflict'])
def test_reject_without_false_durable_ack(tmp_path,monkeypatch,fault):
    async def scenario():
        c=controller(tmp_path);await c.process_command(command());m=pending(c)
        g=Gateway('A1',queue_path=str(tmp_path/'a.db'));replies=[];m._result_writer=object()
        async def send(w,m):replies.append(m)
        monkeypatch.setattr('gateway.gateway.send_message',send)
        if fault=='database':
            def fail(*a):raise sqlite3.OperationalError('disk fault')
            monkeypatch.setattr(g.offline_queue,'admit_result',fail)
        elif fault=='capacity':
            g.offline_queue.max_messages=1
            g.offline_queue.enqueue(Message(type='ALERT',source='A1',target='SERVER',payload={'severity':'CRITICAL'}))
        else:
            assert await g._process_control_result(m)
            replies.clear();m.payload['duration']=2
        assert not await g._process_control_result(m)
        assert all(r.type!=PERSISTED_ACK for r in replies)
        assert replies[-1].payload['result_state']=='RESULT_REJECTED'
        assert c.recent_commands.pending_results
    asyncio.run(scenario())


def test_queue_full_retains_controller_outcome(tmp_path,monkeypatch):
    async def scenario():
        c=controller(tmp_path);await c.process_command(command());m=pending(c)
        g=Gateway('A1',queue_path=str(tmp_path/'a.db'),queue_capacity=1)
        g.result_queue.put_nowait(m);replies=[]
        async def send(w,m):replies.append(m)
        monkeypatch.setattr('gateway.gateway.send_message',send)
        await g._ingress_put(g.result_queue,m,object())
        assert replies[-1].payload['result_state']=='RESULT_REJECTED'
        assert controller(tmp_path).recent_commands.pending_results
        g.result_queue.get_nowait();g.result_queue.task_done()
        assert await g._process_control_result(pending(c))
        assert g.offline_queue.count()==1
    asyncio.run(scenario())


def test_intent_recovery_unknown_and_no_reexecution(tmp_path):
    async def scenario():
        c=controller(tmp_path)
        c.recent_commands.begin('cmd',{'source':'A1','generation':1,'command_type':'IRRIGATION','node_id':'C1'})
        c=controller(tmp_path)
        assert pending(c).payload['status']=='UNKNOWN'
        await c.process_command(command())
        assert c.metrics.get('executed')==0
        assert pending(c).payload['status']=='UNKNOWN'
    asyncio.run(scenario())


@pytest.mark.parametrize('field,value',[('scope','SERVER_SQLITE'),('persisted',False),('delivery_contract','bad'),('result_state','RESULT_RECEIVED')])
def test_wrong_ack_never_releases_result(tmp_path,field,value):
    async def scenario():
        c=controller(tmp_path);await c.process_command(command())
        p={'ack_message_id':pending(c).message_id,'scope':'CONTROL_RESULTS','persisted':True,
           'delivery_contract':CONTRACT,'result_state':'RESULT_DURABLY_STORED'}
        p[field]=value
        assert not c._accept_result_ack(Message(type=PERSISTED_ACK,source='A1',target='C1',payload=p),'A1')
        assert c.recent_commands.pending_results
    asyncio.run(scenario())


@pytest.mark.parametrize('generation,valid',[(1,True),(2,False),(0,False)])
def test_result_generation_is_audit_evidence_not_authority(tmp_path,generation,valid):
    async def scenario():
        c=controller(tmp_path);await c.process_command(command());m=pending(c)
        m.payload['generation']=generation
        g=Gateway('A1',queue_path=str(tmp_path/'a.db'))
        assert await g._process_control_result(m) is valid
        assert g.ownership.generation==1
    asyncio.run(scenario())


def test_unconfirmed_results_cannot_be_evicted(tmp_path):
    store=RecentCommandStore(StateStore(tmp_path/'window.db'),capacity=1)
    store.begin('a')
    m=Message(type='CONTROL_RESULT',source='C1',target='A1',payload={'command_id':'a','status':'EXECUTED','delivery_contract':CONTRACT})
    store.complete('a',{'status':'EXECUTED'},m)
    with pytest.raises(StateError):store.begin('b')
    assert store.acknowledge_result(m.message_id)
    store.begin('b')
    assert list(store.entries)==['b']


def test_capacity_backpressure_can_recover_after_real_ack(tmp_path,monkeypatch):
    from common import settings
    monkeypatch.setitem(settings.SETTINGS['controller'],'recent_command_capacity',1)
    async def scenario():
        c=controller(tmp_path);await c.process_command(command())
        second=command();second.message_id='second';second.payload['command_id']='second'
        assert (await c.process_command(second))['status']=='REJECTED'
        assert c.metrics.get('executed')==1 and not c.guard.persistence_fault
        m=pending(c)
        p={'ack_message_id':m.message_id,'scope':'CONTROL_RESULTS','persisted':True,
           'delivery_contract':CONTRACT,'result_state':'RESULT_DURABLY_STORED'}
        assert not c._accept_result_ack(Message(type='ACK',source='A1',target='C1',payload=p),'A1')
        assert c._accept_result_ack(Message(type=PERSISTED_ACK,source='A1',target='C1',payload=p),'A1')
        c.guard.cooldown['IRRIGATION']=0
        assert (await c.process_command(second))['status']=='EXECUTED'
        assert c.metrics.get('executed')==2
    asyncio.run(scenario())

def test_confirmed_result_replay_keeps_original_wire_after_controller_restart(tmp_path):
    async def scenario():
        c=controller(tmp_path);await c.process_command(command());original=pending(c)
        g=Gateway('A1',queue_path=str(tmp_path/'a.db'))
        assert await g._process_control_result(original)
        assert c.recent_commands.acknowledge_result(original.message_id)
        c=controller(tmp_path);await c.process_command(command());replayed=pending(c)
        assert replayed.to_dict()==original.to_dict()
        assert await g._process_control_result(replayed)
        assert g.offline_queue.count()==1 and g.metrics.get('result_duplicates')==1
        assert c.metrics.get('executed')==0
    asyncio.run(scenario())
