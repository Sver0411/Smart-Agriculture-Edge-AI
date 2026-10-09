"""Production C telemetry → real TCP gateway → SQLite cloud with lost B ACK."""
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import time
import pytest
from common.messages import Message, NODE_REGISTER, PERSISTED_ACK, read_message, send_message, transport_observer
from experiments.metrics import TransportRecorder
from gateway.gateway import Gateway
from server.server import Server

ROOT=Path(__file__).resolve().parents[1]

def test_firmware_wire_lost_ack_retry_is_one_cloud_sample(tmp_path, monkeypatch):
    main=ROOT/'firmware/b1/main';trust=ROOT/'firmware/b1/components/sensor_trust';adaptive=ROOT/'firmware/b1/components/adaptive_sense'
    binary=tmp_path/'wire';cc=shutil.which('cc')
    if not cc:pytest.fail('C compiler required')
    subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-DB1_HOST_TEST','-DCONFIG_B1_LAB_MODE=1',
        '-I',str(ROOT/'third_party/cjson'),'-I',str(ROOT/'tests/c_host/stubs'),'-I',str(main),'-I',str(trust),'-I',str(adaptive),
        str(ROOT/'tests/c_host/b1_delivery_wire.c'),str(main/'b1_policy.c'),str(main/'b1_queue.c'),str(main/'b1_telemetry.c'),str(main/'b1_outbox.c'),
        str(trust/'sensor_trust.c'),str(adaptive/'adaptive_scheduler.c'),str(adaptive/'change_detector.c'),
        str(ROOT/'third_party/cjson/cJSON.c'),'-lm','-o',str(binary)],check=True)
    wire=subprocess.check_output([str(binary)],text=True)
    (tmp_path/'firmware-wire.jsonl').write_text(wire)
    messages=[Message.from_json(line) for line in wire.splitlines()]
    assert [m.type for m in messages]==['SENSOR_DATA','SENSOR_DATA','ALERT']
    async def run():
        recorder=TransportRecorder(); observer=transport_observer.set(recorder)
        s=Server(port=0,db_path=str(tmp_path/'server.db'));await s.start()
        g=Gateway('A1',port=0,server_port=s._server.sockets[0].getsockname()[1],peer_port=1,
                  queue_path=str(tmp_path/'gateway.db'))
        dropped=asyncio.Event()
        async def send(w,m):
            if m.type==PERSISTED_ACK and m.target=='B1' and not dropped.is_set():
                assert g.offline_queue.count()==1
                dropped.set();return
            await send_message(w,m)
        monkeypatch.setattr('gateway.gateway.send_message',send)
        await g.start();reader,writer=await asyncio.open_connection('127.0.0.1',g._server.sockets[0].getsockname()[1])
        try:
            await send_message(writer,Message(type=NODE_REGISTER,source='B1',target='A1',
                payload={'node_id':'B1','node_type':'SENSOR','node_mode':'physical','boot_id':'host-test'}))
            assert (await read_message(reader)).payload['accepted']
            for m in messages: m.payload['delivery_age_ms']=0
            await send_message(writer,messages[0]);await asyncio.wait_for(dropped.wait(),2)
            deadline=time.monotonic()+3
            while (s.db.count('sensor_data')<1 or g.offline_queue.count()) and time.monotonic()<deadline:
                await asyncio.sleep(.01)
            assert s.db.count('sensor_data')==1 and g.offline_queue.count()==0
            # Gateway's cloud row is gone; B still retries its exact logical data.
            await send_message(writer,messages[0]);ack=await asyncio.wait_for(read_message(reader),2)
            assert ack.type==PERSISTED_ACK and ack.payload['scope']=='GATEWAY_OUTBOX'
            for m in messages[1:]:
                await send_message(writer,m);ack=await asyncio.wait_for(read_message(reader),2)
                assert ack.payload['ack_message_id']==m.message_id
            deadline=time.monotonic()+3
            while (s.db.count('sensor_data')<2 or s.db.count('alert')<1) and time.monotonic()<deadline:await asyncio.sleep(.01)
            assert s.db.count('sensor_data')==2 and s.db.count('alert')==1
            assert g.metrics.get('sensor_durable_duplicates')==1 and g.command_queue.empty()
            rows=s.db.recent_sensor_data(2)
            assert {json.loads(row['metadata_json'])['sample_seq'] for row in rows}=={1,2}
        finally:
            writer.close();await g.stop();await s.stop()
            transport_observer.reset(observer)
            (tmp_path/'events.jsonl').write_text(''.join(json.dumps(e,sort_keys=True)+'\n' for e in recorder.events))
    asyncio.run(run())
