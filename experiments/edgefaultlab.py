"""Adapter to the independently maintained EdgeFaultLab runner.

No EdgeFaultLab code is vendored. A checkout root is supplied explicitly.
Original smart_agriculture templates are adapted for paths, ports and timing.
"""
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from common.settings import SETTINGS,config_hash
from experiments.runner import ports,write_json

TEMPLATES=('gateway_failover','server_outage','duplicate_control_command','stale_command','lost_command')


def adapt(template,project,output,seed=42):
    spec=deepcopy(template);root=Path(project).resolve();out=Path(output).resolve()
    out.mkdir(parents=True,exist_ok=True)
    old=(9100,9201,9202,9301,9400,9302);mapping=dict(zip(old,ports(len(old))))
    spec['seed']=seed;spec['duration']=12
    cfg=deepcopy(SETTINGS)
    cfg['system']['SERVER_PORT']=mapping[9100];cfg['system']['GATEWAY_PORTS']={'A1':mapping[9201],'A2':mapping[9202]}
    cfg['system']['COOLDOWN']={'IRRIGATION':0,'VENTILATION':0}
    cfg['system'].update(HEARTBEAT_INTERVAL=0.1,HEARTBEAT_TIMEOUT=0.6,ACK_TIMEOUT=0.15,
                         RETRY_SCAN_INTERVAL=0.05,NODE_STATUS_INTERVAL=0.2,SIMULATION_TIME_SCALE=0.01)
    config_path=out/'config.json';write_json(config_path,cfg)
    spec['links'].append({'name':'nodes_to_gateway_a2','listen':f'127.0.0.1:{mapping[9202]}','upstream':f'127.0.0.1:{mapping[9302]}'})
    for link in spec['links']:
        for key in ('listen','upstream'):
            host,port=link[key].rsplit(':',1)
            if int(port) in mapping:link[key]=f'{host}:{mapping[int(port)]}'
    for proc in spec['processes']:
        command=proc['command'];command[0]=sys.executable;command.insert(1,'-u')
        for index,item in enumerate(command):
            if item in ('--port','--server-port','--peer-port'):
                command[index+1]=str(mapping[int(command[index+1])])
            if item in ('--db','--queue-db'):
                command[index+1]=str(out/Path(command[index+1]).name)
        if proc['name']=='gateway_a2':
            i=command.index('--port');command[i+1]=str(mapping[9302])
        if proc['name'].startswith('sensor'):
            command+=['--sample-interval','0.2','--seed',str(seed)]
        if proc['name'].startswith('controller'):
            command+=['--state-db',str(out/(proc['name']+'.state.db')),'--emit-execution-events']
        proc['cwd']=str(root);proc['env']={'SMART_AGRICULTURE_CONFIG':str(config_path)}
    for id,module,gateway in [('B2','sensor_node.sensor_node','A2'),('C2','controller_node.controller_node','A2')]:
        command=[sys.executable,'-u','-m',module,'--id',id,'--gateway',gateway]
        if id=='B2':command+=['--sample-interval','0.2','--seed',str(seed+1)]
        if id=='C2':command+=['--state-db',str(out/'controller_c2.state.db'),'--emit-execution-events']
        spec['processes'].append({'name':'sensor_b2' if id=='B2' else 'controller_c2','command':command,'cwd':str(root),'env':{'SMART_AGRICULTURE_CONFIG':str(config_path)}})
    for fault in spec['faults']:
        fault['at']=0 if fault['at']==0 else 2
        if 'duration' in fault:fault['duration']=2
    for assertion in spec['assertions']:
        if 'after' in assertion:assertion['after']=0 if assertion['after']==0 else (4 if assertion['after']>=20 else 2)
        if 'within' in assertion:assertion['within']=8
    # A durable EXECUTED outcome is replayable after ACK loss or duplicate
    # command delivery. Observe the execution branch to retain the stronger
    # at-most-once actuator assertion, rather than prohibit result retransmit.
    write_json(out/'original_assertions.json', spec['assertions'])
    for assertion in spec['assertions']:
        match = assertion.get('match', {})
        if assertion.get('assert') == 'unique' and match.get('type') == 'CONTROL_RESULT' and match.get('payload.status') == 'EXECUTED':
            assertion['match'] = {'type':'NODE_STATUS', 'payload.event':'ACTUATOR_EXECUTED'}
    if any(a.get('assert') == 'unique' and a.get('match', {}).get('payload.event') == 'ACTUATOR_EXECUTED' for a in spec['assertions']):
        spec['assertions'].append({'assert':'message_count','link':'nodes_to_gateway_a1',
            'match':{'type':'NODE_STATUS','payload.event':'ACTUATOR_EXECUTED'},'min':1,
            'description':'actual actuator execution events are nonvacuously observed'})
    # Nonvacuous failover assertion must observe traffic from the successor.
    if any(f['action']=='process_kill' for f in spec['faults']):
        spec['assertions'].append({'assert':'eventually','after':2,'within':8,'link':'gateways_to_server',
            'match':{'type':'SENSOR_DATA','source':'A2'},'description':'A2 uploads after A1 crash'})
        spec['assertions'].append({'assert':'eventually','after':2,'within':8,'link':'nodes_to_gateway_a2',
            'match':{'type':'NODE_REGISTER','source':'B1'},'description':'B1 reconnects to A2'})
    return spec

async def run_templates(efl_root,output,seed=42):
    efl=Path(efl_root).resolve()
    if not (efl/'edgefaultlab/runner.py').exists():raise ValueError('EdgeFaultLab checkout required')
    sys.path.insert(0,str(efl))
    from edgefaultlab.runner import ScenarioRunner
    from edgefaultlab.scenario import load_scenario
    revision=subprocess.check_output(['git','-C',str(efl),'rev-parse','HEAD'],text=True).strip()
    summaries=[]
    for name in TEMPLATES:
        out=Path(output).resolve()/name
        template=json.loads((efl/'examples/smart_agriculture'/(name+'.json')).read_text())
        spec=adapt(template,Path(__file__).resolve().parents[1],out,seed)
        path=out/'scenario.json';write_json(path,spec)
        scenario=load_scenario(path)
        runner=ScenarioRunner(scenario,output=out/'run')
        code=await runner.run()
        summary={'scenario':name,'status':'PASS' if code==0 else 'FAIL','exit_code':code,
                 'external_revision':revision,'assertions':[{'description':r.description,'passed':r.passed,'detail':r.detail} for r in runner.results]}
        # Supplement execution uniqueness with replay-content consistency.
        wires={};conflicts=[];executed=set();observed_actions=set()
        for event in runner.recorder.observations:
            message=event.get('message') or {}
            if message.get('source') not in ('C1','C2'):continue
            payload=message.get('payload',{})
            if message.get('type')=='NODE_STATUS' and payload.get('event')=='ACTUATOR_EXECUTED':
                observed_actions.add((message['source'],payload.get('command_id')))
            if message.get('type')=='CONTROL_RESULT' and payload.get('status')=='EXECUTED':
                executed.add((message['source'],payload.get('command_id')))
                identity=message['message_id']
                canonical=json.dumps({k:v for k,v in message.items() if k!='target'},sort_keys=True,separators=(',',':'))
                if identity in wires and wires[identity]!=canonical:conflicts.append(identity)
                wires[identity]=canonical
        checks=[{'description':'replayed execution results preserve immutable content (transport target may follow takeover)',
                 'passed':not conflicts,'detail':f'{len(wires)} identities; {len(conflicts)} conflicts'}]
        if name=='duplicate_control_command':
            checks.append({'description':'duplicate-command execution outcomes have independently observed actual execution',
                 'passed':executed<=observed_actions,
                 'detail':f'{len(executed)} outcomes; {len(observed_actions)} execution identities'})
        summary['execution_observation']={'outcomes':len(executed),'execution_identities':len(observed_actions),
            'scope':'observations can be lost during endpoint outages; result replay is not a second action'}
        summary['assertions'].extend(checks)
        if not all(r['passed'] for r in checks):code=1
        summary.update(status='PASS' if code==0 else 'FAIL',exit_code=code)
        write_json(out/'integration_summary.json',summary);summaries.append(summary)
        print(f"EdgeFaultLab {name}: {summary['status']}",flush=True)
    write_json(Path(output)/'suite_summary.json',{'scenarios':summaries,'passed':sum(s['exit_code']==0 for s in summaries),'total':len(summaries)})
    return 0 if all(s['exit_code']==0 for s in summaries) else 1

def main():
    p=argparse.ArgumentParser();p.add_argument('--edgefaultlab-root',required=True);p.add_argument('--output',required=True);p.add_argument('--seed',type=int,default=42);a=p.parse_args()
    raise SystemExit(asyncio.run(run_templates(a.edgefaultlab_root,a.output,a.seed)))
if __name__=='__main__':main()
