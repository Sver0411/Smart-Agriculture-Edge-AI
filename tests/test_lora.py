import asyncio
from dataclasses import replace
import json
from pathlib import Path
import random
import struct
import subprocess
import zlib
import pytest
from common.messages import Message
from common.lora.codec import *
from common.lora.reassembly import Reassembler
from common.lora.delivery import DeliveryWindow,Stage
from common.lora.transport import SimulatedLoRa
ROOT=Path(__file__).resolve().parents[1]
SESSION=bytes(range(16))


def message(kind="SENSOR_DATA",source="B1",target="A1",size=350):
    return Message(type=kind,source=source,target=target,message_id="B1-long-original-logical-identity-S",
        timestamp=1.0,sequence=8,payload={"data":{"temperature":25},"padding":"x"*size})


@pytest.mark.parametrize("kind,source,target",[("SENSOR_DATA","B1","A2"),("ALERT","B2","A1"),
    ("NODE_REGISTER","B1","A1"),("NODE_REGISTER_ACK","A2","B1"),("NODE_STATUS","A1","B2"),
    ("PERSISTED_ACK","A1","B1"),("ACK","C1","A2"),("CONTROL_COMMAND","A2","C1"),
    ("CONTROL_RESULT","C2","A1"),("HEARTBEAT","A1","A2"),("SERVER_POLICY","A1","B1")])
def test_every_required_field_link_is_fragmented_and_reassembled(kind,source,target):
    m=message(kind,source,target);wires=fragment(m,SESSION)
    random.Random(42).shuffle(wires);r=Reassembler(sessions={ROLES.index(source):SESSION})
    output=None
    for n,wire in enumerate(wires):
        f=decode(wire);assert f.sequence==8 and f.zone==route(source,target,kind)
        if n==0:assert r.feed(wire,n/100) is None;assert r.feed(wire,n/100) is None
        result=r.feed(wire,n/100)
        if result:output=result
    assert output.to_dict()==m.to_dict() and r.duplicates>=1


@pytest.mark.parametrize("index",list(range(70)))
def test_each_header_byte_is_integrity_protected(index):
    wire=bytearray(fragment(message(),SESSION)[0]);wire[index]^=1
    with pytest.raises(FrameError):decode(bytes(wire))


@pytest.mark.parametrize("data",[b"",b"AL",b"x"*257])
def test_bad_frame_lengths(data):
    with pytest.raises(FrameError):decode(data)


def test_oversized_message_fragment_budget_and_id_reject():
    for m in [message(size=4096),replace(message(),message_id="x"*129)]:
        with pytest.raises(FrameError):fragment(m,SESSION)
    with pytest.raises(FrameError):fragment(message(size=2000),SESSION,96)


def test_slots_timeout_session_conflict_and_message_crc():
    wires=fragment(message(),SESSION);r=Reassembler(capacity=1)
    assert r.feed(wires[-1],0) is None
    other=fragment(replace(message(),message_id="other"),SESSION)
    with pytest.raises(FrameError,match="capacity"):r.feed(other[0],.1)
    r.expire(3);assert not r.slots and r.expired==1
    r.sessions[3]=b"z"*16
    with pytest.raises(FrameError,match="session"):r.feed(wires[0],3)
    r.sessions.clear();r.feed(wires[0],3)
    f=decode(wires[0]);bad=replace(f,payload=b"y"+f.payload[1:]).encode()
    with pytest.raises(FrameError,match="conflict"):r.feed(bad,3)
    r.expire(6)
    for i,wire in enumerate(wires):
        f=decode(wire);f=replace(f,message_crc=f.message_crc^1)
        if i+1==len(wires):
            with pytest.raises(FrameError,match="message CRC"):r.feed(f.encode(),6)
        else:assert r.feed(f.encode(),6) is None
    with pytest.raises(FrameError,match="clock"):r.feed(wires[0],5)


@pytest.mark.parametrize("field,value",[("count",65),("count",0),("total",65535),("index",63),("chunk",0),("zone",2),("source",0),("generation",0x100000000)])
def test_invalid_frame_fields(field,value):
    f=replace(decode(fragment(message(),SESSION)[0]),**{field:value})
    with pytest.raises((FrameError,struct.error)):f.encode()


def test_application_header_identity_mismatch_rejected():
    m=message();wires=fragment(m,SESSION);r=Reassembler()
    for i,wire in enumerate(wires):
        f=replace(decode(wire),logical=b"x"*16)
        if i+1==len(wires):
            with pytest.raises(FrameError,match="mismatch"):r.feed(f.encode(),0)
        else:r.feed(f.encode(),0)


def test_c_codec_reassembly_uart_stream_and_python_wire_parity(tmp_path):
    d=ROOT/"firmware/b1/components/agri_lora";exe=tmp_path/"codec"
    subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-fsanitize=address,undefined","-I",str(d),
        str(ROOT/"tests/c_host/lora_vectors.c"),str(d/"agri_lora.c"),"-o",str(exe)],check=True)
    wires=fragment(message(size=1800),SESSION,160)
    bad=bytearray(wires[0]);bad[-1]^=1
    sequence=[bytes(bad),*reversed(wires)]
    result=subprocess.check_output([str(exe)],input="".join(w.hex()+"\n" for w in sequence),text=True)
    lines=result.splitlines();assert lines[0]=="REJECTED"
    assert json.loads(lines[-1])==message(size=1800).to_dict()
    # Seeded random malformed frames go through the real sanitizer decoder.
    rng=random.Random(42);fuzz=[bytes(rng.randrange(256) for _ in range(rng.randrange(1,257))) for _ in range(1000)]
    subprocess.run([str(exe)],input="".join(w.hex()+"\n" for w in fuzz),text=True,stdout=subprocess.DEVNULL,check=True)


def test_delivery_retains_identity_until_matching_durable_scope():
    window=DeliveryWindow(attempts=2);m=message();window.admit(m,0)
    assert window.due(0)[0].message_id==m.message_id
    ack=Message(type="PERSISTED_ACK",source="A1",target="B1",payload={"ack_message_id":m.message_id,"persisted":True,"scope":"FRAME_ACCEPTED"})
    assert not window.confirm(ack,Stage.GATEWAY_DURABLE) and m.message_id in window.pending
    assert window.due(3)[0].message_id==m.message_id
    assert not window.due(6) and window.pending[m.message_id]["failed"]
    ack.payload.update(scope="GATEWAY_OUTBOX",delivery_contract="gateway-durable-v1")
    assert window.confirm(ack,Stage.GATEWAY_DURABLE) and not window.pending


def test_simulated_fragment_damage_and_outage_never_deliver_application():
    class Writer:
        def __init__(self):self.lines=[]
        def write(self,line):self.lines.append(line)
        async def drain(self):pass
    async def run():
        w=Writer();radio=SimulatedLoRa(corruption=1,seed=42)
        assert await radio(w,message());assert not w.lines and radio.metrics["rejected"]>0
        radio=SimulatedLoRa(partial=1);await radio(w,message());assert not w.lines
        radio=SimulatedLoRa();radio.outage=True;await radio(w,message());assert not w.lines
        radio.outage=False;await radio(w,message());assert len(w.lines)==1
    asyncio.run(run())

@pytest.mark.parametrize('now',[float('nan'),float('inf'),-1,True])
def test_retry_clock_rejects_unknown_age(now):
    window=DeliveryWindow()
    with pytest.raises(ValueError):window.admit(message(),now)


def test_retry_clock_rollback_preserves_pending_identity():
    window=DeliveryWindow();m=message();window.admit(m,10)
    with pytest.raises(ValueError):window.due(9)
    assert m.message_id in window.pending
