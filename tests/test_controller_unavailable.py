import asyncio
import time
import pytest
from common.messages import Message, CONTROL_COMMAND
from gateway.gateway import Gateway
from server.server import Server
from server.dedup import Deduplicator
from controller_node.controller_node import ControllerNode

@pytest.mark.parametrize('case,reason',[
    ('never','CONTROLLER_UNAVAILABLE'),('disconnected','CONTROLLER_UNAVAILABLE'),
    ('ownership','NOT_OWNER'),('expired','EXPIRED')])
def test_unsent_command_has_persisted_failure_without_late_execution(case,reason,tmp_path):
    async def run():
        g=Gateway('A1');c=ControllerNode('C1',time_scale=0)
        s=Server(db_path=str(tmp_path/'server.db'));s.db.init_schema();s.dedup=Deduplicator(s.db.conn,auto_commit=False)
        m=Message(type=CONTROL_COMMAND,source='A1',target='C1',payload={
            'command_id':'unsent','type':'IRRIGATION','duration':1,'gateway_generation':1})
        if case=='disconnected':g.connections['C1']=object();g.connections.pop('C1')
        if case=='ownership':g.registry.transfer(['C1'],'A2',2)
        if case=='expired':m.timestamp=time.time()-100
        await g._dispatch_command(m,True)
        result=await g.upload_queue.get();assert result.payload['status']=='NOT_DISPATCHED'
        assert result.payload['reason']==reason;s._store(result)
        assert s.db.recent_controller_results()[0]['reason']==reason
        assert not g.tracker.pending and g.command_queue.empty()
        # Reconnection cannot resurrect this command; only historical outcome remains.
        g.connections['C1']=object()
        assert not g.tracker.due(now=time.time()+100) and c.metrics.get('executed')==0
        s.db.close()
    asyncio.run(run())

def test_retry_unavailability_is_unknown_not_false_claim_of_no_execution():
    async def run():
        g=Gateway('A1');m=Message(type=CONTROL_COMMAND,source='A1',target='C1',payload={
            'command_id':'maybe-executed','type':'IRRIGATION','duration':1,'gateway_generation':1})
        g.tracker.track(m);await g._dispatch_command(m,False)
        assert (await g.upload_queue.get()).payload['status']=='UNKNOWN'
        assert not g.tracker.pending
    asyncio.run(run())
