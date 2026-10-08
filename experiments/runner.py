"""Real TCP, software sources/actuators, machine assertions and raw evidence.

python -m experiments.runner --all --output results/software-v0.3
"""
import argparse
import asyncio
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
from common.settings import SETTINGS,config_hash
from common import config
from common.messages import (Message,SENSOR_DATA,CONTROL_COMMAND,transport_observer,transport_interceptor)
from controller_node.controller_node import ControllerNode
from controller_node.safety_guard import SafetyGuard
from gateway.gateway import Gateway
from sensor_node.sensor_node import SensorNode,SensorSimulator
from server.server import Server
from simulation.network_faults import FrameFaults
from experiments.metrics import Metrics,TransportRecorder

CATALOG=json.loads((Path(__file__).parent/'scenarios/catalog.json').read_text())

def ports(count):
    sockets=[]
    try:
        for _ in range(count):
            s=socket.socket();s.bind(('127.0.0.1',0));sockets.append(s)
        return [s.getsockname()[1] for s in sockets]
    finally:
        for s in sockets:s.close()

def write_json(path,data):
    path.write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+'\n')

async def run_scenario(name,output,seed=42,duration=None,transport="tcp",lora_options=None,extra_fault_rules=None):
    if name not in CATALOG:raise ValueError(f'unknown scenario {name}')
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    raw=out/'raw';raw.mkdir();results=out/'results';results.mkdir();truth=out/'truth';truth.mkdir()
    if transport not in ("tcp", "simulated-lora"):
        raise ValueError("host transport must be tcp or simulated-lora")
    radio = None
    if transport == "simulated-lora":
        from common.lora.transport import SimulatedLoRa
        radio = SimulatedLoRa(seed=seed, **(lora_options or {}))
    cfg=deepcopy(SETTINGS);cfg['experiment']['seed']=seed
    cfg['field_transport'] = {"mode": transport, "lora": lora_options or {}, "physical_RF": False}
    sp,p1,p2=ports(3);gateway_ports={'A1':p1,'A2':p2}
    cfg['system']['SERVER_PORT']=sp;cfg['system']['GATEWAY_PORTS']=gateway_ports
    cfg['runtime_overrides']={'gateway':{'heartbeat_interval':0.1,'heartbeat_timeout':0.6,
        'command_ack_timeout':0.12,'result_timeout':0.4,'server_receipt_timeout':0.25},
        'sensor':{'slow_interval':0.2,'fast_interval':0.1,'keepalive_interval':0.1,
                  'B1_start':{'soil_moisture':10,'temperature':25},'B2_start':{'soil_moisture':50,'temperature':36}},
        'controller':{'cooldown':{'IRRIGATION':0,'VENTILATION':0},'time_scale':0},
        'server':{'policy_interval':0.5},'settling_s':0.8,'observation_s':duration if duration is not None else 1.6,
        'replay_completion_timeout_s':10,
        'profile':'simulation', 'cloud_backoff_s':[0.2,0.5,1,2,5],
        'wrong_initial_gateway':'A2' if name=='registration-race' else None,
        'controller_initially_offline':'C1' if name=='controller-unavailable' else None}
    write_json(out/'config.json',cfg)
    recorder=TransportRecorder();obs=transport_observer.set(recorder)
    match={'type':'CONTROL_COMMAND','target':'C1'}
    rules=[]
    if name=='packet-loss':rules=[{'action':'drop','match':match}]
    if name=='ack-loss':rules=[{'action':'drop','match':{'type':'ACK','source':'C1'}}]
    if name=='duplicate-command':rules=[{'action':'duplicate','match':match}]
    if name=='delayed-result':rules=[{'action':'delay','delay_s':0.8,'match':{'type':'CONTROL_RESULT','source':'C1'}}]
    if name=='lost-result':rules=[{'action':'drop','count':1000,'match':{'type':'CONTROL_RESULT','source':'C1'}}]
    if name=='persisted-ack-loss':rules=[{'action':'drop','match':{'type':'PERSISTED_ACK','target':'A1'}}]
    if name=='reordered-messages':rules=[{'action':'reorder','count':2,'match':{'type':'SENSOR_DATA','source':'B1'}}]
    rules.extend(deepcopy(extra_fault_rules or []))
    cfg["additional_fault_rules"]=extra_fault_rules or []
    write_json(out/"config.json",cfg)
    faults=FrameFaults(rules,seed)
    async def inject(writer,message):
        handled=await faults(writer,message)
        if name=='persisted-ack-loss' and handled and message.type=='PERSISTED_ACK':
            ack_id=message.payload['ack_message_id']
            retained=any(m.message_id==ack_id for _,m in gateways['A1'].offline_queue.peek(1000))
            committed=server.db.conn.execute('SELECT COUNT(*) FROM processed_message WHERE message_id=?',(ack_id,)).fetchone()[0]==1
            faults.events[-1].update(queue_retained=retained,commit_observed=committed)
            recorder('persistence_boundary',Message(type='PERSISTED_ACK',source='SERVER',target='A1',
                payload={**message.payload,'queue_retained':retained,'commit_observed':committed}))
        if not handled and radio is not None:
            handled = await radio(writer, message)
        return handled
    inter=transport_interceptor.set(inject)
    server=Server(port=sp,db_path=str(out/'server.db'),policy_interval=0.5)
    servers=[server];gateways={};gateway_history=[];nodes={};tasks=[];node_tasks={};assertions=[];observations={};disruptions=[]
    def check(description,condition):assertions.append({'description':description,'passed':bool(condition)})
    def new_gateway(id):
        g=Gateway(id,port=gateway_ports[id],peer_port=gateway_ports['A2' if id=='A1' else 'A1'],server_port=sp,
                  heartbeat_interval=0.1,heartbeat_timeout=0.6,queue_path=str(out/(id+'.db')),random_seed=seed,result_timeout=0.4,receipt_timeout=0.25)
        g.tracker.timeout=0.12
        gateway_history.append(g)
        return g
    def command(id,source='A1',generation=1,timestamp=None):
        m=Message(type=CONTROL_COMMAND,source=source,target='C1',message_id=id,
           payload={'command_id':id,'type':'IRRIGATION','duration':1,'gateway_generation':generation})
        if timestamp is not None:m.timestamp=timestamp
        return m
    try:
        await server.start()
        for id in ('A1','A2'):
            gateways[id]=new_gateway(id);await gateways[id].start()
        for id in ('C1','C2'):
            n=ControllerNode(id,safety_guard=SafetyGuard(cooldown={'IRRIGATION':0,'VENTILATION':0}),time_scale=0)
            n._candidates=lambda n=n:[(x,'127.0.0.1',gateway_ports[x]) for x in [n.guard.owner_gateway or n.primary_gateway]+[x for x in ('A1','A2') if x!=(n.guard.owner_gateway or n.primary_gateway)]]
            if name=='registration-race' and id=='C1':n.primary_gateway='A2'
            nodes[id]=n
            if not (name=='controller-unavailable' and id=='C1'):
                task=asyncio.create_task(n.run());tasks.append(task);node_tasks[id]=task
        for index,id in enumerate(('B1','B2')):
            sim=SensorSimulator(id,seed=seed+index,start={'soil_moisture':10 if id=='B1' else 50,'temperature':25 if id=='B1' else 36})
            if name=='sensor-fault' and id=='B1':
                original=sim.sample
                def broken(original=original):return {**original(),'soil_moisture':999}
                sim.sample=broken
            n=SensorNode(id,simulator=sim,slow_interval=0.2,fast_interval=0.1,keepalive_interval=0.1)
            n._candidates=lambda n=n:[(x,'127.0.0.1',gateway_ports[x]) for x in [n.owner_gateway or n.primary_gateway]+[x for x in ('A1','A2') if x!=(n.owner_gateway or n.primary_gateway)]]
            if name=='registration-race' and id=='B1':n.primary_gateway='A2'
            nodes[id]=n;task=asyncio.create_task(n.run());tasks.append(task);node_tasks[id]=task
        await asyncio.sleep(0.8)
        if name=='registration-race':
            wrong=[e for e in recorder.events if e['event']=='delivered' and e['message']['type']=='NODE_REGISTER_ACK'
                   and e['message']['source']=='A2' and e['message']['target'] in ('B1','C1')]
            check('A2 explicitly rejects B1 and C1 before takeover',
                  {e['message']['target'] for e in wrong}=={'B1','C1'} and
                  all(e['message']['payload'].get('reason')=='NOT_OWNER' and
                      e['message']['payload'].get('accepted') is False for e in wrong))
            check('correct B1/C1 initial owner at A1',nodes['B1'].owner_gateway==nodes['C1'].guard.owner_gateway=='A1')
            check('registration does not bump initial epoch',all(g.ownership.generation==1 for g in gateways.values()))
        if name=='persisted-ack-loss':
            first=next((e for e in recorder.events if e['event']=='dropped' and e['message']['type']=='PERSISTED_ACK'),None)
            check('committed receipt was dropped',first is not None)
            if first:
                ack_id=first['message']['payload']['ack_message_id']
                deadline=time.monotonic()+3
                while (gateways['A1'].offline_queue.count() or server.dedup.ignored==0) and time.monotonic()<deadline:
                    await asyncio.sleep(0.01)
                check('server deduplicates replay after ACK loss',server.dedup.ignored>0)
                check('acknowledged row removed',all(m.message_id!=ack_id for _,m in gateways['A1'].offline_queue.peek(1000)))
                table=next((e['message']['type'] for e in recorder.events if e['message']['message_id']==ack_id),'SENSOR_DATA')
                table={'SENSOR_DATA':'sensor_data','CONTROL_COMMAND':'controller_command','CONTROL_RESULT':'controller_result','ALERT':'alert'}[table]
                count=server.db.conn.execute(f'SELECT COUNT(*) FROM {table} WHERE message_id=?',(ack_id,)).fetchone()[0]
                check('one committed business row for lost receipt',count==1)
                observations['replayed_message_id']=ack_id
                # The queue is sampled when the ACK is dropped, not inferred from a later empty queue.
                check('row retained at moment of dropped ACK',bool(faults.events[0].get('queue_retained')))
                check('dedup row committed before dropped ACK',bool(faults.events[0].get('commit_observed')))
        if name=='controller-unavailable':
            nodes['B1'].stop();node_tasks['B1'].cancel();await asyncio.gather(node_tasks['B1'],return_exceptions=True)
            # Wait for the stopped sensor's TCP EOF, then consume its already
            # decoded decisions while C1 is still deliberately offline.
            deadline=time.monotonic()+3
            while 'B1' in gateways['A1'].connections and time.monotonic()<deadline:
                await asyncio.sleep(0.01)
            await asyncio.wait_for(gateways['A1'].sensor_queue.join(),3)
            await asyncio.wait_for(gateways['A1'].command_queue.join(),3)
            expected=gateways['A1'].metrics.get('not_dispatched')
            while server.db.conn.execute("SELECT COUNT(*) FROM controller_result WHERE controller_id='C1' AND status='NOT_DISPATCHED'").fetchone()[0] < expected and time.monotonic()<deadline:
                await asyncio.sleep(0.01)
            rows=[dict(r) for r in server.db.conn.execute("SELECT * FROM controller_result WHERE controller_id='C1'")]
            failures=[r for r in rows if r['status']=='NOT_DISPATCHED' and r['reason']=='CONTROLLER_UNAVAILABLE']
            check('server records unavailable controller outcome',bool(failures))
            check('offline controller executes zero commands',nodes['C1'].metrics.get('executed')==0)
            observations['undispatched_ids']=[r['command_id'] for r in failures]
            task=asyncio.create_task(nodes['C1'].run());tasks.append(task);node_tasks['C1']=task
            deadline=time.monotonic()+3
            while (nodes['C1'].guard.owner_gateway!='A1' or 'C1' not in gateways['A1'].connections) and time.monotonic()<deadline:
                await asyncio.sleep(0.01)
        if name in ('gateway-failover','gateway-recovery','stale-generation'):
            await gateways['A1'].stop();disruptions.append({'action':'gateway_crash','time_s':time.monotonic()-recorder.start})
            failure_time=time.monotonic()
            deadline=failure_time+3
            while time.monotonic()<deadline:
                if nodes['B1'].owner_gateway=='A2' and nodes['B1'].generation>=2 and nodes['C1'].guard.current_generation>=2:break
                await asyncio.sleep(0.05)
            observations['recovery_time_s']=time.monotonic()-failure_time
            check('A2 peer A1 OFFLINE',gateways['A2'].peer_status=='OFFLINE')
            check('ownership epoch synchronized across A2/B1/C1',gateways['A2'].ownership.generation==nodes['B1'].generation==nodes['C1'].guard.current_generation>=2)
            check('B1 and C1 owner A2',nodes['B1'].owner_gateway==nodes['C1'].guard.owner_gateway=='A2')
            old=await nodes['C1'].process_command(command('stale-probe',generation=1))
            check('deposed command rejected',old.get('reason')=='STALE_GENERATION')
            observations['stale_result']=old
            if name=='gateway-recovery':
                g=new_gateway('A1');gateways['A1']=g;await g.start();await asyncio.sleep(0.5)
                check('recovered gateway standby',g.ownership.role=='STANDBY')
        if name in ('server-offline','queue-replay'):
            await server.stop();disruptions.append({'action':'server_outage','time_s':time.monotonic()-recorder.start})
            before=sum(n.metrics.get('executed') for id,n in nodes.items() if id.startswith('C'))
            await asyncio.sleep(0.8)
            g=gateways['A1']
            if name=='queue-replay':
                for i in range(250):g._queue_locally(Message(type=SENSOR_DATA,source='A1',target='SERVER',message_id=f'queue-{seed}-{i}',
                    payload={'record':{'sensor_node_id':'B1','temperature':25,'timestamp':time.time()}}),'experiment offline batch')
            check('history queued durably',sum(g.offline_queue.count() for g in gateways.values())>0)
            check('local control executes during outage',sum(n.metrics.get('executed') for id,n in nodes.items() if id.startswith('C'))>before)
            server=Server(port=sp,db_path=str(out/'server.db'),policy_interval=0.5);servers.append(server);await server.start()
            # Observe persisted completion, not an assumed host I/O throughput.
            deadline=time.monotonic()+cfg['runtime_overrides']['replay_completion_timeout_s']
            while time.monotonic()<deadline:
                drained=all(g.offline_queue.count()==0 for g in gateways.values())
                committed=(name!='queue-replay' or server.db.conn.execute(
                    "SELECT COUNT(*) FROM sensor_data WHERE message_id LIKE ?",(f'queue-{seed}-%',)).fetchone()[0]==250)
                if drained and committed:break
                await asyncio.sleep(0.01)
            check('all offline queues drained',all(g.offline_queue.count()==0 for g in gateways.values()))
            if name=='queue-replay':
                count=server.db.conn.execute("SELECT COUNT(*) FROM sensor_data WHERE message_id LIKE ?",(f'queue-{seed}-%',)).fetchone()[0]
                check('250 logical queued samples stored',count==250)
        if name=='policy-replay':
            d=gateways['A1'].decider;d.update_policy({'policy_version':100,'soil_moisture_threshold':18})
            applied,_=d.update_policy({'policy_version':99,'soil_moisture_threshold':30})
            check('old policy ignored',not applied and d.policy['soil_moisture_threshold']==18)
        if name=='split-brain':
            result=await nodes['C1'].process_command(command('non-owner','A2',nodes['C1'].guard.current_generation))
            observations['result']=result;check('non-owner cannot execute',result.get('reason')=='NOT_OWNER')
        if name=='expired-command':
            result=await nodes['C1'].process_command(command('expired',timestamp=time.time()-30))
            observations['result']=result;check('expired command rejected',result.get('reason')=='EXPIRED')
        await asyncio.sleep(duration if duration is not None else 1.6)
        recorder.freeze()
        observations['measurement_end_s']=recorder.end-recorder.start
        observations['measurement_scope']='scenario traffic before asynchronous teardown'
        delivered=[e for e in recorder.events if e['event']=='delivered']
        controls=[e['message'] for e in delivered if e['message']['type']=='CONTROL_COMMAND'
                  and e['message']['target'] in ('C1','C2')]
        check('every sensor command preserves fixed zone membership', any('sensor_node_id' in m['payload'] for m in controls) and all(
            config.CONTROLLER_OF_SENSOR[m['payload']['sensor_node_id']] == m['target']
            for m in controls if 'sensor_node_id' in m['payload']))
        if name in ('gateway-failover','gateway-recovery','stale-generation'):
            check('A2 drives C1 from B1 after takeover',any(m['source']=='A2' and m['target']=='C1'
                and m['payload'].get('sensor_node_id')=='B1' for m in controls))
            check('A2 continues driving C2 from B2',any(m['source']=='A2' and m['target']=='C2'
                and m['payload'].get('sensor_node_id')=='B2' for m in controls))
        executed=[e['message']['payload']['command_id'] for e in delivered if e['message']['type']=='CONTROL_RESULT' and e['message']['target'] in ('A1','A2') and e['message']['payload'].get('status')=='EXECUTED']
        check('no logical command reported executed twice on control link',len(executed)==len(set(executed)))
        check('both sensor zones sampled',all(nodes[x].metrics.get('sensor_samples')>0 for x in ('B1','B2')))
        if name=='sensor-fault':
            check('C1 never executes on faulty B1',nodes['C1'].metrics.get('executed')==0)
            check('fault evidence stored',server.db.count('alert')>0 and nodes['B1'].metrics.get('fault_samples')>0)
        elif name=='controller-unavailable':
            check('C1 really reconnects after offline decision',nodes['C1'].guard.owner_gateway=='A1' and 'C1' in gateways['A1'].connections)
            check('reconnected C1 never executes old undispatched command',nodes['C1'].metrics.get('executed')==0)
            sent_ids={e['message']['payload'].get('command_id') for e in recorder.events if e['event']=='sent' and e['message']['type']=='CONTROL_COMMAND' and e['message']['target']=='C1'}
            check('no unavailable command is later dispatched',not sent_ids.intersection(observations['undispatched_ids']))
        else:
            check('C1 executes trusted control',nodes['C1'].metrics.get('executed')>0)
        check('C2 zone continues',nodes['C2'].metrics.get('executed')>0)
        check('server records sensor history',server.db.count('sensor_data')>0)
        if rules:check('planned frame fault exercised',all(r['applied']>0 for r in faults.rules))
        if name in ('packet-loss','ack-loss'):check('bounded retry observed',sum(g.metrics.get('retries') for g in gateways.values())>0)
        if name=='ack-loss':check('duplicate execution prevented',nodes['C1'].metrics.get('duplicates')>0)
        if name=='delayed-result':check('late result resolves unknown outcome',gateways['A1'].metrics.get('late_results')>0)
        if name=='lost-result':check('missing result is UNKNOWN',gateways['A1'].metrics.get('unknown_execution_results')>0)
        if name=='reordered-messages':check('old telemetry skipped for control',gateways['A1'].metrics.get('reordered_or_duplicate_samples')>0)
        observations['gateway_states']={id:g.ownership.as_dict() for id,g in gateways.items()}
        observations['node_ownership']={id:{'owner':n.owner_gateway,'generation':n.generation} for id,n in nodes.items() if id.startswith('B')}
        m=Metrics()
        for k in ('sensor_samples','trusted_samples','degraded_samples','fault_samples'):
            m.set(k,sum(nodes[id].metrics.get(k) for id in ('B1','B2')))
        for target,source in [('acks','acks_received'),('retries','retries'),('delivery_failures','delivery_failures'),('control_commands','commands'),('gateway_failovers','failovers'),('offline_queued','queue_enqueued'),('queue_replayed','queue_replayed')]:
            m.set(target,sum(g.metrics.get(source) for g in gateway_history))
        for target,source in [('control_executed','executed'),('control_rejected','rejected'),('duplicate_execution_prevented','duplicates')]:
            m.set(target,sum(nodes[id].metrics.get(source) for id in ('C1','C2')))
        m.set('messages_sent',recorder.counts['sent']);m.set('messages_delivered',recorder.counts['delivered'])
        m.set('duplicates',recorder.counts['duplicated']);m.set('dropped',recorder.counts['dropped'])
        m.set('server_duplicates_ignored',sum(s.dedup.ignored for s in servers))
        m.set('deduplicated',sum(s.dedup.ignored for s in servers))
        for metric, values, scope in (
            ('attempt_transport_latency', recorder.attempt_latencies, 'successful socket write/drain to matching decode; attempt and FIFO matched; host only'),
            ('logical_delivery_latency', recorder.logical_latencies, 'first send request including dropped attempts to first receiver decode; includes retry/fault delay'),
            ('ack_latency', recorder.ack_latencies, 'first send request to first receipt ACK; includes retries; excludes execution outcome'),
            ('persisted_ack_latency', recorder.persisted_ack_latencies, 'first send request to first SQLite committed receipt; includes replay')):
            if values:m.set(metric, {'mean_s':sum(values)/len(values),'observations':len(values),'scope':scope})
        if 'recovery_time_s' in observations:m.set('recovery_time',observations['recovery_time_s'])
        interval_counts=Counter()
        for id in ('B1','B2'):interval_counts.update(nodes[id].interval_counts)
        if interval_counts:
            total=sum(interval_counts.values())
            m.set('sampling_interval_mean',sum(k*v for k,v in interval_counts.items())/total)
            m.set('sampling_interval_distribution',{str(k):v for k,v in interval_counts.items()})
        decisions={e['message']['message_id']:e['message']['payload'].get('type') for e in recorder.events if e['event']=='sent' and e['message']['type']=='CONTROL_COMMAND' and e['message']['target'] in ('C1','C2')}
        m.set('decision_counts',dict(Counter(decisions.values())))
        calls=sum(g.metrics.get('decision_calls') for g in gateway_history)
        if calls:m.set('decision_latency',{'mean_us':sum(g.metrics.get('decision_latency_us') for g in gateway_history)/calls,'calls':calls,'scope':'host inference'})
        write_json(results/'metrics.json',m.as_dict())
    except Exception as exc:
        check('scenario runs without exception',False);observations['error']=f'{type(exc).__name__}: {exc}'
    finally:
        recorder.freeze()
        await faults.close()
        for n in nodes.values():n.stop()
        for t in tasks:t.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        for g in gateways.values():await g.stop()
        for s in servers:
            if not s._stopping:await s.stop()
        transport_observer.reset(obs);transport_interceptor.reset(inter)
    (raw/'events.jsonl').write_text(''.join(json.dumps(e,sort_keys=True,allow_nan=False)+'\n' for e in recorder.events))
    write_json(truth/'injection_plan.json',{'scenario':name,'seed':seed,'frame_faults':rules,'disruptions':disruptions,'receipt_observations':faults.events,'sensor_fault':name=='sensor-fault'})
    if radio is not None:
        write_json(results/'lora_metrics.json', radio.metrics)
        (raw/'lora_events.jsonl').write_text(''.join(json.dumps(e,sort_keys=True)+'\n' for e in radio.events))
    code=0 if assertions and all(a['passed'] for a in assertions) else 1
    summary={'scenario':name,'question':CATALOG[name],'status':'PASS' if code==0 else 'FAIL','exit_code':code,'assertions':assertions,'observations':observations}
    write_json(results/'summary.json',summary)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    write_json(out/'manifest.json',{'schema_version':1,'scenario':name,'seed':seed,'input_mode':'software-simulation','verification':'host-tested',
        'revision':revision,'working_tree_dirty':any(not line[3:].startswith(('results/software-v0.3/','results/software-v0.3.1/')) for line in subprocess.check_output(['git','status','--porcelain'],text=True).splitlines()),
        'dirty_scope':'source files; generated software-v0.3 and software-v0.3.1 evidence excluded',
        'config_sha256':config_hash(cfg),'raw_sha256':hashlib.sha256((raw/'events.jsonl').read_bytes()).hexdigest(),'status':summary['status']})
    (results/'report.md').write_text(f"# {name}: {summary['status']}\n\n{CATALOG[name]}\n\n"+'\n'.join(f"- {'PASS' if a['passed'] else 'FAIL'}: {a['description']}" for a in assertions)+'\n')
    return summary

async def run_all(output,seed=42,names=None,transport="tcp",lora_options=None):
    summaries=[]
    for index,name in enumerate(names or CATALOG,1):
        summary=await run_scenario(name,Path(output)/f'EXP-{index:03}-{name}',seed,transport=transport,lora_options=lora_options)
        print(f"{name}: {summary['status']}",flush=True);summaries.append(summary)
    write_json(Path(output)/'suite_summary.json',{'scenarios':summaries,'passed':sum(s['exit_code']==0 for s in summaries),'total':len(summaries)})
    return 0 if all(s['exit_code']==0 for s in summaries) else 1

def main():
    p=argparse.ArgumentParser();p.add_argument('--scenario',choices=CATALOG);p.add_argument('--all',action='store_true');p.add_argument('--output',required=True);p.add_argument('--seed',type=int,default=42);p.add_argument('--transport',choices=['tcp','simulated-lora'],default='tcp');a=p.parse_args()
    if not a.all and not a.scenario:p.error('specify --all or --scenario')
    raise SystemExit(asyncio.run(run_all(a.output,a.seed,None if a.all else [a.scenario],transport=a.transport)))
if __name__=='__main__':main()
