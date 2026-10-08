"""Frame fault adapter on a host TCP carrier; never a physical RF measurement.

Use as common.messages.transport_interceptor. Real seven-role application
handlers and SQLite receipts run unchanged; only field links are fragmented.
One adapter invocation is one logical send attempt, not a durable receipt.
"""
import asyncio
import random
import uuid
from .codec import fragment, ROLES, FrameError
from .reassembly import Reassembler


class SimulatedLoRa:
    def __init__(self, seed=42, mtu=160, loss=0, ack_loss=0, duplication=0,
                 corruption=0, partial=0, reorder=False, latency=0, capacity=4):
        if any(not 0 <= x <= 1 for x in (loss,ack_loss,duplication,corruption,partial)) or not 0 <= latency <= 1:
            raise ValueError("fault bounds")
        self.rng=random.Random(seed);self.mtu=mtu;self.loss=loss;self.ack_loss=ack_loss
        self.duplication=duplication;self.corruption=corruption;self.partial=partial
        self.reorder=reorder;self.latency=latency;self.capacity=capacity
        self.receivers={};self.sessions={};self.events=[];self.outage=False
        self.metrics={"logical_attempts":0,"fragments_sent":0,"simulated_frame_bytes":0,
            "reassembled":0,"duplicates":0,"rejected":0,"dropped":0}

    def reset_receiver(self, destination):
        self.receivers.pop(destination,None)
        self.events.append({"event":"receiver_restart","destination":destination})

    async def __call__(self, writer, message):
        if "SERVER" in (message.source,message.target):
            return False
        session=self.sessions.setdefault(message.source,uuid.UUID(int=self.rng.getrandbits(128)).bytes)
        frames=fragment(message,session,self.mtu)
        receiver=self.receivers.setdefault(message.target,Reassembler(self.capacity))
        receiver.sessions[ROLES.index(message.source)]=session
        self.metrics["logical_attempts"]+=1
        if self.reorder:self.rng.shuffle(frames)
        delivered=None
        for i,wire in enumerate(frames):
            self.metrics["fragments_sent"]+=1;self.metrics["simulated_frame_bytes"]+=len(wire)
            event={"event":"frame_send","source":message.source,"destination":message.target,
                "logical_message_id":message.message_id,"bytes":len(wire),"index_in_attempt":i}
            drop=self.outage or self.rng.random()<self.loss or (message.type in ("ACK","PERSISTED_ACK") and self.rng.random()<self.ack_loss) or (i==len(frames)-1 and self.rng.random()<self.partial)
            if drop:
                event["outcome"]="DROPPED";self.metrics["dropped"]+=1
                self.events.append(event);continue
            if self.rng.random()<self.corruption:
                wire=wire[:-1]+bytes([wire[-1]^1]);event["corrupted"]=True
            if self.latency:await asyncio.sleep(self.rng.random()*self.latency)
            try:
                m=receiver.feed(wire,asyncio.get_running_loop().time())
                if m is not None:delivered=m
                event["outcome"]="MESSAGE_REASSEMBLED" if m else "FRAME_ACCEPTED"
                if self.rng.random()<self.duplication:
                    again=receiver.feed(wire,asyncio.get_running_loop().time())
                    if again is not None:delivered=again
                    self.metrics["duplicates"]+=1
            except FrameError as exc:
                event["outcome"]="REJECTED";event["reason"]=str(exc);self.metrics["rejected"]+=1
            self.events.append(event)
        if delivered is not None:
            writer.write(delivered.to_line().encode());await writer.drain()
            self.metrics["reassembled"]+=1
        return True
