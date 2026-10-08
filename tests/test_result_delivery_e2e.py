"""Real controller/gateway/cloud sockets with lost result ACKs."""
import asyncio
import time
import pytest
from common.messages import Message, transport_interceptor
from gateway.gateway import Gateway
from controller_node.controller_node import ControllerNode
from server.server import Server

@pytest.mark.parametrize('drop_ack',[False,True])
def test_one_execution_one_cloud_result_after_ack_loss_and_reconnect(tmp_path,drop_ack):
    async def scenario():
        dropped=[]
        async def fault(writer,message):
            if drop_ack and message.type=='PERSISTED_ACK' and message.target=='C1' and not dropped:
                dropped.append(message.to_dict());return True
            return False
        token=transport_interceptor.set(fault)
        server=Server(port=0,db_path=str(tmp_path/'s.db'));await server.start()
        sp=server._server.sockets[0].getsockname()[1]
        gateway=Gateway('A1',port=0,peer_port=1,server_port=sp,
            queue_path=str(tmp_path/'a.db'),heartbeat_timeout=100,receipt_timeout=.2)
        await gateway.start();port=gateway._server.sockets[0].getsockname()[1]
        controller=ControllerNode('C1',gateway_port=port,state_path=str(tmp_path/'c.db'),time_scale=0)
        task=asyncio.create_task(controller.run())
        async def until(predicate):
            deadline=time.monotonic()+6
            while not predicate():
                assert time.monotonic()<deadline,'state convergence timed out'
                await asyncio.sleep(.01)
        try:
            await until(lambda:'C1' in gateway.connections)
            command=Message(type='CONTROL_COMMAND',source='A1',target='C1',message_id='command',
                payload={'command_id':'command','type':'IRRIGATION','duration':1,'gateway_generation':1})
            await gateway._dispatch_command(command,first_attempt=True)
            await until(lambda:controller.metrics.get('executed')==1 and
                        not controller.recent_commands.pending_results and
                        server.db.conn.execute("SELECT COUNT(*) FROM controller_result WHERE command_id='command' AND status='EXECUTED'").fetchone()[0]==1)
            assert gateway.metrics.get('result_duplicates')==(1 if drop_ack else 0)
            assert len(dropped)==(1 if drop_ack else 0)
            controller.stop();task.cancel();await asyncio.gather(task,return_exceptions=True)
            controller=ControllerNode('C1',gateway_port=port,state_path=str(tmp_path/'c.db'),time_scale=0)
            controller.guard.cooldown['IRRIGATION']=0
            assert (await controller.process_command(command))['status']=='DUPLICATE'
            assert controller.metrics.get('executed')==0
        finally:
            controller.stop();task.cancel();await asyncio.gather(task,return_exceptions=True)
            transport_interceptor.reset(token)
            await gateway.stop();await server.stop()
    asyncio.run(scenario())
