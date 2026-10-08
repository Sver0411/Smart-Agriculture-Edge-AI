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


def test_one_way_partition_recovers_after_actual_event_loop_pause(tmp_path, monkeypatch):
    import time
    from gateway.gateway import Gateway
    from experiments.runner import run_scenario
    original = Gateway._observe_peer_monitor_tick
    paused = False
    def pause_once(gateway, now=None):
        nonlocal paused
        if (not paused and gateway.gateway_id == 'A1' and
                gateway._peer_monitor_last_tick is not None and
                gateway.peer_status == 'ONLINE'):
            paused = True
            time.sleep(.65)  # Deliberate shared-loop suspension, not a network delay.
        return original(gateway, now)
    monkeypatch.setattr(Gateway, '_observe_peer_monitor_tick', pause_once)
    result = asyncio.run(run_scenario('normal', tmp_path/'paused-partition',
        transport='simulated-lora', duration=3, extra_fault_rules=[
            {'action':'drop','count':10000,'match':{
                'type':'HEARTBEAT','source':'A1','target':'A2'}}]))
    assert paused and result['status'] == 'PASS'
    states = result['observations']['gateway_states']
    assert states['A1']['role'] == 'STANDBY'
    assert states['A1']['generation'] == 1
    assert states['A2']['generation'] == 2


def test_integration_failure_updates_manifest_and_summary_hash(tmp_path):
    import json
    import hashlib
    from experiments.phase123_integration import finalize_topology_summary
    (tmp_path/'results').mkdir()
    (tmp_path/'manifest.json').write_text(json.dumps({'status':'PASS','revision':'tested-source'}))
    result = {'status':'PASS','exit_code':0,'assertions':[
        {'description':'base scenario','passed':True},
        {'description':'integration ownership','passed':False}]}
    finalize_topology_summary(tmp_path,result)
    manifest = json.loads((tmp_path/'manifest.json').read_text())
    assert result['status'] == manifest['status'] == 'FAIL'
    assert result['exit_code'] == 1
    assert manifest['revision'] == 'tested-source'
    assert manifest['summary_sha256'] == hashlib.sha256(
        (tmp_path/'results/summary.json').read_bytes()).hexdigest()


def test_slow_peer_connect_does_not_suspend_failure_detection(monkeypatch):
    import time
    from gateway.gateway import Gateway
    async def scenario():
        g = Gateway('A2', heartbeat_interval=.01, heartbeat_timeout=.2)
        g.peer_last_seen = time.monotonic() - .5
        g._peer_monitor_last_tick = time.monotonic()
        async def slow_connect():
            await asyncio.sleep(.25)  # Task awaits; the event loop is running.
        async def observe_upload(message):
            if g.peer_status == 'OFFLINE':
                g._stopping = True
        monkeypatch.setattr(g, '_connect_peer', slow_connect)
        monkeypatch.setattr(g, '_submit_upload', observe_upload)
        await asyncio.wait_for(g.task_heartbeat(), 1)
        assert g.ownership.generation == 2
        assert g.metrics.get('failovers') == 1
        assert g.metrics.get('peer_monitor_stalls') == 0
        g.offline_queue.close()
    asyncio.run(scenario())
