"""Regression reproductions retained from the merged research baseline."""
import asyncio
from common.messages import Message, CONTROL_COMMAND
from common.state_store import StateStore
from controller_node.controller_node import ControllerNode
from controller_node.safety_guard import SafetyGuard
from server.server import Server
from gateway.edge_decision import EdgeDecider


def test_executed_result_survives_restart_before_send(tmp_path, monkeypatch):
    async def scenario():
        path=tmp_path/'controller.db'
        c=ControllerNode('C1', state_path=str(path),time_scale=0)
        assert c.guard.set_ownership('A1',1)
        async def lose_result(writer,message):
            if message.type == 'CONTROL_RESULT': raise BrokenPipeError('crash before send')
        monkeypatch.setattr('controller_node.controller_node.send_message',lose_result)
        command=Message(type=CONTROL_COMMAND,source='A1',target='C1',message_id='cmd',
            payload={'command_id':'cmd','type':'IRRIGATION','duration':1,'gateway_generation':1})
        try: await c.process_command(command,object())
        except BrokenPipeError: pass
        recovered=ControllerNode('C1',state_path=str(path),time_scale=0)
        assert recovered.recent_commands.pending_results
        assert next(iter(recovered.recent_commands.pending_results.values()))['payload']['status']=='EXECUTED'
    asyncio.run(scenario())


def test_server_restart_retains_version_100(tmp_path):
    async def scenario():
        path=str(tmp_path/'server.db')
        s=Server(port=0,db_path=path,policy_version=100)
        await s.start()
        d=EdgeDecider(store=StateStore(tmp_path/'gateway.db'))
        assert d.update_policy({'policy_version':100,**s.policy})[0]
        await s.stop()
        s=Server(port=0,db_path=path)
        await s.start()
        try:
            s.update_policy({'soil_moisture_threshold':18})
            assert s.policy_version==101
            assert d.update_policy({'policy_version':s.policy_version,**s.policy})[0]
        finally: await s.stop()
    asyncio.run(scenario())
