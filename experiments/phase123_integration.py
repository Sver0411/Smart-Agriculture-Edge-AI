"""Ten cross-phase cases with production C state and real application endpoints."""
import argparse
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
import tempfile
from common.messages import Message,send_message,read_message,transport_interceptor,transport_observer
from common.lora.transport import SimulatedLoRa
from common.lora.delivery import DeliveryWindow,Stage
from gateway.gateway import Gateway
from server.server import Server
from experiments.runner import run_scenario
from experiments.metrics import TransportRecorder
ROOT=Path(__file__).resolve().parents[1]
CASES=['stable-sleep','event-loss-ack','high-sleep-retry','failover-freshness','recovery-fencing','fragment-corruption','queue-age','corrupt-snapshot','server-replay','asymmetric-partition']
def build(exe):
    main=ROOT/'firmware/b1/main';trust=ROOT/'firmware/b1/components/sensor_trust';adaptive=ROOT/'firmware/b1/components/adaptive_sense';radio=ROOT/'firmware/b1/components/agri_lora'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-D_POSIX_C_SOURCE=200809L','-Wno-deprecated-declarations','-DB1_HOST_TEST','-DCONFIG_B1_LAB_MODE=1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(ROOT/'third_party/cjson'),'-I',str(ROOT/'tests/c_host/stubs'),'-I',str(main),'-I',str(trust),'-I',str(adaptive),'-I',str(radio),str(ROOT/'tests/c_host/b1_phase123.c'),*[str(main/n) for n in ('b1_policy.c','b1_queue.c','b1_telemetry.c','b1_outbox.c','b1_checkpoint.c','b1_snapshot.c')],str(trust/'sensor_trust.c'),str(adaptive/'change_detector.c'),str(adaptive/'adaptive_scheduler.c'),str(radio/'agri_lora.c'),str(ROOT/'third_party/cjson/cJSON.c'),'-lm','-o',str(exe)],check=True)
def c_run(exe,mode,directory,*acks):
    result=subprocess.run([str(exe),mode,str(directory),*acks],capture_output=True,text=True)
    (directory/(mode+'.stdout.jsonl')).write_text(result.stdout)
    (directory/(mode+'.stderr.jsonl')).write_text(result.stderr)
    assert result.returncode==0,result.stderr
    return [Message.from_json(line) for line in result.stdout.splitlines()]
async def basic_case(case,out,seed,exe):
    assertions=[];metrics={};wire=[];events=[];out.mkdir(parents=True,exist_ok=False)
    if case=='stable-sleep':
        c_run(exe,'stable',out);assertions.append({'description':'trusted elapsed restore avoids upload and synthetic onset in stable real C policy','passed':True})
    else:
        wire=c_run(exe,'prepare',out);original=wire[0];assert original.payload['importance']=='HIGH'
        if case=='corrupt-snapshot':
            restored=c_run(exe,'corrupt',out);assert [m.message_id for m in restored]==[m.message_id for m in wire]
            assertions.append({'description':'corrupt RTC rejected while real v2 HIGH checkpoint retains original identity','passed':True})
        radio=SimulatedLoRa(seed=seed);token=transport_interceptor.set(radio)
        server=Server(port=0,db_path=str(out/'server.db'));await server.start()
        g=Gateway('A1',port=0,server_port=server._server.sockets[0].getsockname()[1],peer_port=1,queue_path=str(out/'gateway.db'))
        await g.start();reader,writer=await asyncio.open_connection('127.0.0.1',g._server.sockets[0].getsockname()[1])
        try:
            async def register(boot):
                await send_message(writer,Message(type='NODE_REGISTER',source='B1',target='A1',payload={'node_type':'SENSOR','node_mode':'physical','boot_id':boot}))
                assert (await asyncio.wait_for(read_message(reader),2)).payload['accepted']
            await register('host-old');original.payload['delivery_age_ms']=0
            window=DeliveryWindow();window.admit(original,0)
            if case=='event-loss-ack':radio.loss=1
            if case=='fragment-corruption':radio.corruption=1
            if case=='high-sleep-retry':radio.ack_loss=1
            if case in ('event-loss-ack','fragment-corruption','high-sleep-retry'):
                await send_message(writer,original)
                try:
                    ack=await asyncio.wait_for(read_message(reader),.1)
                    raise AssertionError('failed attempt fabricated ACK '+ack.type)
                except asyncio.TimeoutError:pass
                if case!='high-sleep-retry':assert not g.offline_queue.export_receipts()['receipts'] and g.metrics.get('decision_calls')==0
                assertions.append({'description':'loss/damage has no fabricated durable confirmation or control admission','passed':True})
            if case=='high-sleep-retry':
                restored=c_run(exe,'restore',out);assert restored[0].message_id==original.message_id
                original=restored[0];original.payload['delivery_age_ms']=None
                radio.ack_loss=0;await register('host-new')
            if case=='corrupt-snapshot':original.payload['delivery_age_ms']=None
            if case=='queue-age':
                # Real gateway queue admission timestamp + delayed decision; no
                # wall-clock sleep needed to inject a 6s monotonic queue wait.
                import time
                await register('host-old')
                original.payload['data']['temperature']=36
                g.sensor_queue.put_nowait(original);queued=await g.sensor_queue.get()
                boot,received,wall=queued._gateway_ingress
                queued._gateway_ingress=(boot,received-6,wall)
                await g._process_sensor_message(queued);g.sensor_queue.task_done()
                ack=await asyncio.wait_for(read_message(reader),2)
            else:
                radio.loss=radio.corruption=0
                await send_message(writer,original);ack=await asyncio.wait_for(read_message(reader),2)
            assert ack.type=='PERSISTED_ACK' and ack.payload['scope']=='GATEWAY_OUTBOX' and ack.payload['persisted'] is True
            assert g.offline_queue.sensor_audit(original.message_id) is not None
            assert window.confirm(ack,Stage.GATEWAY_DURABLE)
            if case=='event-loss-ack':
                c_run(exe,'ack',out,ack.payload['ack_message_id'])
                assertions.append({'description':'real gateway committed receipt precedes ACK, actual C confirmed_seq advances to2 only after matching ACK','passed':True})
            if case=='high-sleep-retry':
                c_run(exe,'old-ack',out,ack.payload['ack_message_id'])
                assert len(g.offline_queue.export_receipts()['receipts'])==1 and g.metrics.get('sensor_durable_duplicates')==1
                assertions.append({'description':'old boot HIGH retry deduplicates and retires evidence without advancing fresh baseline','passed':True})
            if case in ('queue-age','corrupt-snapshot'):
                assert g.metrics.get('decision_calls')==0 and g.command_queue.empty()
                assertions.append({'description':'unknown/expired age is durably historical and cannot create a new controller command','passed':True})
            deadline=asyncio.get_running_loop().time()+3
            while server.db.count('sensor_data')!=1 and asyncio.get_running_loop().time()<deadline:await asyncio.sleep(.01)
            assert server.db.count('sensor_data')==1
            metrics={**radio.metrics,'gateway_receipts':len(g.offline_queue.export_receipts()['receipts']),'server_samples':server.db.count('sensor_data'),'decision_calls':g.metrics.get('decision_calls')}
            assertions.append({'description':'one immutable logical sample stored once at gateway and server','passed':True})
        finally:
            writer.close();await g.stop();await server.stop();transport_interceptor.reset(token);events=radio.events
    summary={'status':'PASS','case':case,'assertions':assertions,'metrics':metrics}
    (out/'config.json').write_text(json.dumps({'seed':seed,'case':case,'physical_hardware':False,'transport':'host fragmented LoRa on TCP carrier','units':{'time':'host seconds / logical C ms','bytes':'simulated frame bytes'}},indent=2)+'\n')
    (out/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');return summary
async def ownership_probe(out,exe):
    """C HIGH history vs explicit new physical-mode host sample after takeover."""
    import time
    from controller_node.controller_node import ControllerNode
    out.mkdir();wire=c_run(exe,'prepare',out);restored=c_run(exe,'restore',out)
    old=restored[0];old.target='A2';old.payload['delivery_age_ms']=None
    g=Gateway('A2',queue_path=str(out/'a2.db'));g._takeover();g.sensor_boots['B1']='host-new'
    c=ControllerNode('C1',time_scale=0);assert c.guard.set_ownership('A2',g.ownership.generation)
    events=[]
    try:
        g.sensor_queue.put_nowait(old);await g._process_sensor_message(await g.sensor_queue.get());g.sensor_queue.task_done()
        assert g.command_queue.empty() and g.metrics.get('decision_calls')==0
        # Explicit synthetic current acquisition: new boot/sample identity and
        # fresh age. It is not a measurement of a physical SHT30.
        fresh=Message.from_dict(old.to_dict());fresh.sequence=3;fresh.message_id='B1-host-new-00000003-S'
        fresh.payload.update(boot_id='host-new',sample_seq=3,sample_id='B1-host-new-00000003',device_monotonic_ms=100,delivery_age_ms=0)
        fresh.payload['data']['temperature']=36
        g.sensor_queue.put_nowait(fresh);await g._process_sensor_message(await g.sensor_queue.get());g.sensor_queue.task_done()
        command,retry=await asyncio.wait_for(g.command_queue.get(),1);g.command_queue.task_done()
        assert command.target=='C1' and command.source=='A2' and command.payload['gateway_generation']>=2
        class Writer:
            def __init__(self):self.lines=[]
            def write(self,line):self.lines.append(line)
            async def drain(self):pass
        carrier=Writer();radio=SimulatedLoRa(seed=42)
        await radio(carrier,command);assert len(carrier.lines)==1
        received=Message.from_json(carrier.lines[0].decode())
        executed=await c.process_command(received);assert executed['status']=='EXECUTED'
        stale=Message(type='CONTROL_COMMAND',source='A1',target='C1',payload={'command_id':'old-probe','type':'VENTILATION','duration':1,'gateway_generation':1})
        refused=await c.process_command(stale);assert refused['reason']=='STALE_GENERATION' and c.guard.owner_gateway=='A2'
        events=radio.events+[{'event':'HISTORICAL_SKIPPED','message_id':old.message_id},{'event':'FRESH_EXECUTED','result':executed},{'event':'STALE_REJECTED','result':refused}]
        assertions=[{'description':'C-restored HIGH history cannot control after A2 takeover','passed':True},{'description':'new boot fresh data passes A2→LoRa→C1 guard and executes once','passed':True},{'description':'old A1 epoch is rejected and C1 retains A2 owner','passed':True}]
        (out/'summary.json').write_text(json.dumps({'assertions':assertions,'physical_sensor':False},indent=2)+'\n')
        return assertions
    finally:
        g.offline_queue.close();(out/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))

def finalize_topology_summary(out, result):
    """Include integration assertions in the original run's evidence status."""
    result['status'] = 'PASS' if all(a['passed'] for a in result['assertions']) else 'FAIL'
    result['exit_code'] = 0 if result['status'] == 'PASS' else 1
    summary = out/'results'/'summary.json'
    summary.write_text(json.dumps(result,indent=2)+'\n')
    path = out/'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['status'] = result['status']
    manifest['summary_sha256'] = hashlib.sha256(summary.read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest,indent=2)+'\n')

async def run_all(output,seed=42):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);summaries=[]
    mapping={'failover-freshness':'gateway-failover','recovery-fencing':'gateway-recovery','server-replay':'queue-replay','asymmetric-partition':'normal'}
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'bridge';build(exe)
        for case in CASES:
            if case in mapping:
                extra=[{'action':'drop','count':10000,'match':{'type':'HEARTBEAT','source':'A1','target':'A2'}}] if case=='asymmetric-partition' else None
                result=await run_scenario(mapping[case],output/case,seed,transport='simulated-lora',extra_fault_rules=extra,duration=3 if extra else None);result['case']=case
                if case=='failover-freshness':
                    result['assertions'].extend(await ownership_probe(output/case/'history-probe',exe))
                if extra:
                    states=result['observations']['gateway_states']
                    check={'description':'one-way A1→A2 heartbeat loss forces A2 epoch advance and A1 standby via reverse link','passed':states['A1']['role']=='STANDBY' and states['A2']['generation']>=2}
                    result['assertions'].append(check)
                finalize_topology_summary(output/case,result)
            else:result=await basic_case(case,output/case,seed,exe)
            summaries.append(result);print(case,result['status'],flush=True)
    result={'total':len(summaries),'passed':sum(s['status']=='PASS' for s in summaries),'runs':summaries,'partition_scope':'tested fault schedule and controller epoch fencing; no arbitrary partition consensus guarantee'}
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return 0 if result['passed']==len(summaries) else 1
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--seed',type=int,default=42);a=p.parse_args();raise SystemExit(asyncio.run(run_all(a.output,a.seed)))
