"""Seeded limited-message delivery comparison; host RF model, not energy.

Real firmware C serializer -> bounded radio codec -> real TCP application
endpoints -> gateway SQLite receipt -> server durable ACK. The delivery window
is a host retry model; the firmware's independent NVS/outbox tests still apply.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile
from common.messages import Message, read_message, send_message, transport_interceptor
from common.lora.transport import SimulatedLoRa
from common.lora.codec import ROLES, fragment, FrameError
from common.lora.reassembly import Reassembler
from gateway.gateway import Gateway
from server.server import Server
ROOT=Path(__file__).resolve().parents[1]
CASES={
    "normal":{},"packet-loss":{"loss":.05},"ack-loss":{"ack_loss":.3},
    "duplication":{"duplication":.5},"reordering":{"reorder":True},
    "latency":{"latency":.002},"fragment-corruption":{"corruption":.05},
    "partial-delivery":{"partial":.7},"receiver-restart":{},"link-outage":{},
    "gateway-failover":{},"queue-saturation":{},"old-generation":{},"session-mismatch":{}}
SCHEMES={"reliable":5,"no-retry":1,"fixed-retry":3,"event-priority":5}


def c_messages(directory):
    main=ROOT/'firmware/b1/main';trust=ROOT/'firmware/b1/components/sensor_trust';adaptive=ROOT/'firmware/b1/components/adaptive_sense'
    exe=Path(directory)/'b1-wire'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations','-DB1_HOST_TEST','-DCONFIG_B1_LAB_MODE=1',
        '-I',str(ROOT/'third_party/cjson'),'-I',str(ROOT/'tests/c_host/stubs'),'-I',str(main),'-I',str(trust),'-I',str(adaptive),
        str(ROOT/'tests/c_host/b1_delivery_wire.c'),*[str(main/n) for n in ['b1_policy.c','b1_queue.c','b1_telemetry.c','b1_outbox.c']],
        str(trust/'sensor_trust.c'),str(adaptive/'adaptive_scheduler.c'),str(adaptive/'change_detector.c'),
        str(ROOT/'third_party/cjson/cJSON.c'),'-lm','-o',str(exe)],check=True)
    raw=subprocess.check_output([str(exe)],text=True)
    return raw


async def run_case(case,scheme,seed,out,wire_source):
    out.mkdir(parents=True,exist_ok=False)
    radio=SimulatedLoRa(seed=seed,**CASES[case]);token=transport_interceptor.set(radio)
    server=Server(port=0,db_path=str(out/'server.db'),policy_interval=30)
    await server.start()
    g=Gateway('A1',port=0,peer_port=1,server_port=server._server.sockets[0].getsockname()[1],
        queue_path=str(out/'gateway.db'),heartbeat_timeout=60,queue_capacity=1 if case=='queue-saturation' else 128)
    await g.start();reader,writer=await asyncio.open_connection('127.0.0.1',g._server.sockets[0].getsockname()[1])
    originals=[Message.from_json(line) for line in wire_source.splitlines()]
    for m in originals:m.payload['delivery_age_ms']=0
    if scheme=='event-priority':originals.sort(key=lambda m:m.payload['importance']!='HIGH')
    config={'seed':seed,'scheme':scheme,'case':case,'faults':CASES[case], 'transport':'fragmented host radio model on TCP carrier',
        'mtu':160,'message_bound_bytes':4096,'fragment_bound':64,'attempt_limit':SCHEMES[scheme],
        'ACK_wait_s':.05,'units':{'latency':'host seconds','bytes':'simulated UART/frame payload bytes'},'physical_RF':False}
    (out/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    acks=set();errors=[];attempts=0;start=asyncio.get_running_loop().time();assertions=[]
    async def drain():
        while True:
            try:m=await asyncio.wait_for(read_message(reader),.05)
            except asyncio.TimeoutError:return
            if m is None:return
            if m.type=='PERSISTED_ACK' and m.payload.get('scope')=='GATEWAY_OUTBOX' and m.payload.get('persisted') is True:
                assert g.offline_queue.sensor_audit(m.payload['ack_message_id']) is not None
                acks.add(m.payload['ack_message_id'])
            elif m.payload.get('reason'):errors.append(m.payload['reason'])
    try:
        # Commissioning/registration is common to all delivery policies. Keep
        # its fault-free setup separate from the measured data/ACK window.
        radio.loss,radio.ack_loss,radio.corruption,radio.partial=0,0,0,0
        await send_message(writer,Message(type='NODE_REGISTER',source='B1',target='A1',payload={'node_type':'SENSOR','boot_id':'host-test'}))
        reply=await asyncio.wait_for(read_message(reader),1)
        assert reply.payload['accepted']
        for key in ('loss','ack_loss','corruption','partial'):setattr(radio,key,CASES[case].get(key,0))
        radio.metrics={k:0 for k in radio.metrics};radio.events.clear()
        if case=='session-mismatch':
            # The rejection uses the production decoder, never reaches the
            # application handler and cannot generate a durable receipt.
            r=Reassembler(sessions={3:b'z'*16});rejected=False
            try:r.feed(fragment(originals[0],b'x'*16)[0],0)
            except FrameError:rejected=True
            assert rejected
            assertions.append({'assertion':'old session rejected before business admission','passed':rejected})
        if case=='gateway-failover':
            # Exercise real takeover and explicit re-registration over the
            # same radio adapter. Full A1/A2/C fencing is also in topology run.
            writer.close();await writer.wait_closed();await g.stop()
            g=Gateway('A2',port=0,peer_port=1,server_port=server._server.sockets[0].getsockname()[1],queue_path=str(out/'a2.db'),heartbeat_timeout=60)
            g._takeover();await g.start()
            reader,writer=await asyncio.open_connection('127.0.0.1',g._server.sockets[0].getsockname()[1])
            await send_message(writer,Message(type='NODE_REGISTER',source='B1',target='A2',payload={'node_type':'SENSOR','boot_id':'host-test','generation':2}))
            assert (await asyncio.wait_for(read_message(reader),1)).payload['accepted']
            for m in originals:m.target='A2';m.payload['delivery_age_ms']=None
        if case=='old-generation':
            from controller_node.safety_guard import SafetyGuard
            import time
            guard=SafetyGuard();assert guard.set_ownership('A2',2)
            allowed,reason=guard.check('old-radio-command','VENTILATION',1,time.time(),gateway_generation=1,source_gateway='A1')
            assertions.append({'assertion':'controller rejects old epoch before execution (guard subcase)','passed':not allowed and reason=='STALE_GENERATION'})
        for attempt in range(SCHEMES[scheme]):
            if case=='link-outage':radio.outage=attempt==0
            if case=='receiver-restart' and attempt==1:radio.reset_receiver(g.gateway_id)
            pending=originals if scheme=='fixed-retry' else [m for m in originals if m.message_id not in acks]
            for m in pending:
                await send_message(writer,m);attempts+=1
                if case!='queue-saturation':await drain()
            await drain()
            if len(acks)==len(originals) and scheme!='fixed-retry':break
        await asyncio.sleep(.1)
        rows=g.offline_queue.export_receipts()['receipts']
        ids={row[0] for row in rows}
        # Retry identities match the real C source; application evidence never
        # duplicates rows. Delivery shortfall is an observed result, not PASS.
        assertions += [{'assertion':'only original logical identities admitted','passed':ids <= {m.message_id for m in originals}},
            {'assertion':'receipt identities unique','passed':len(rows)==len(ids)},
            {'assertion':'unknown/failed delivery has no fabricated ACK','passed':acks <= ids}]
        if case=='gateway-failover':assertions.append({'assertion':'restored historical samples do not control','passed':g.command_queue.empty() and g.metrics.get('decision_calls')==0})
        metrics={**radio.metrics,'logical_messages':len(originals),'application_send_attempts':attempts,
            'gateway_durable_messages':len(ids),'B_confirmed_messages':len(acks),'effective_delivery_ratio':len(ids)/len(originals),
            'confirmed_delivery_ratio':len(acks)/len(originals),'host_elapsed_s':asyncio.get_running_loop().time()-start,
            'server_samples':server.db.count('sensor_data'),'server_alerts':server.db.count('alert'),
            'failure_reasons':errors,'gateway_queues':{n:getattr(g,n+'_queue').stats() for n in ('sensor','command','result','upload')}}
        summary={'status':'PASS' if all(a['passed'] for a in assertions) else 'FAIL','assertions':assertions,
            'delivery_status':'COMPLETE' if len(acks)==len(originals) else 'INCOMPLETE','case':case,'scheme':scheme}
        (out/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
        (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        (out/'events.jsonl').write_text(''.join(json.dumps(e,sort_keys=True)+'\n' for e in radio.events))
        (out/'firmware-wire.jsonl').write_text(wire_source)
        return {**summary,'metrics':metrics}
    finally:
        writer.close();await g.stop();await server.stop();transport_interceptor.reset(token)


async def run_all(output,seed=42):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory() as directory:wire=c_messages(directory)
    summaries=[]
    for case in CASES:
        for scheme in SCHEMES:
            result=await run_case(case,scheme,seed,output/case/scheme,wire)
            summaries.append(result);print(case,scheme,result['status'],result['delivery_status'],flush=True)
    (output/'summary.json').write_text(json.dumps({'seed':seed,'total':len(summaries),'passed':sum(s['status']=='PASS' for s in summaries),'runs':summaries},indent=2)+'\n')
    files=[p for base in ('common','firmware/b1','gateway','experiments','tests/c_host') for p in (ROOT/base).rglob('*') if p.is_file() and p.suffix in ('.py','.c','.h') and '__pycache__' not in p.parts]
    (output/'source_manifest.json').write_text(json.dumps({'base_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'git_dirty':bool(subprocess.check_output(['git','status','--porcelain'],text=True)), 'python':platform.python_version(),
        'C':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],
        'sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n')
    return 0 if all(s['status']=='PASS' for s in summaries) else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--seed',type=int,default=42);a=p.parse_args()
    raise SystemExit(asyncio.run(run_all(a.output,a.seed)))
if __name__=='__main__':main()
