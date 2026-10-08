"""Host models of future field contracts, not a LoRa codec or TCP replacement.

Owner/session bindings and receiver windows come from a confirmed local
handshake, never from an untrusted command's claimed timestamp or session.
"""
from dataclasses import dataclass
from common import config
from common.protocol import integer, number

ZONE_OF_SENSOR = {'B1':'Zone1', 'B2':'Zone2'}

@dataclass(frozen=True)
class ZoneUplink:
    source_node_id: str
    zone_id: str
    sequence: int
    boot_id: str
    payload: dict

    def valid(self):
        return (ZONE_OF_SENSOR.get(self.source_node_id) == self.zone_id and integer(self.sequence,1)
                and isinstance(self.boot_id,str) and bool(self.boot_id) and isinstance(self.payload,dict))

    def may_process(self, ownership):
        return (self.valid() and ownership.may_control(self.source_node_id)
                and ownership.may_control(config.CONTROLLER_OF_SENSOR[self.source_node_id]))

class FieldFreshnessGuard:
    """Receiver-initiated local window + confirmed owner/epoch/session + sequence.

    Opening a window only after a packet arrives would make an arbitrarily
    delayed packet fresh again. The receiver must issue a new, unique challenge
    *before* arrival. A boot changes receiver_session and requires rebinding.
    Wall time is deliberately not an input to this model.
    """
    def __init__(self, receiver_session, max_ttl_s=10, retry_window_s=10):
        if not isinstance(receiver_session,str) or not receiver_session:
            raise ValueError('receiver session required')
        if any(not number(v) or v <= 0 for v in (max_ttl_s,retry_window_s)):
            raise ValueError('invalid freshness bounds')
        self.receiver_session = receiver_session
        self.max_ttl_s, self.retry_window_s = max_ttl_s,retry_window_s
        self.owner = self.gateway_session = None
        self.generation = 0
        self.sequence = 0
        self.window_sequence = 0
        self.window = None

    def bind(self, owner, generation, gateway_session):
        if (owner not in config.GATEWAY_PORTS or not integer(generation,1) or
                generation < self.generation or not isinstance(gateway_session,str) or not gateway_session):
            return False
        if generation == self.generation and self.owner not in (None,owner):return False
        if (owner,generation,gateway_session) != (self.owner,self.generation,self.gateway_session):
            self.sequence = 0
            self.window = None
        self.owner,self.generation,self.gateway_session = owner,generation,gateway_session
        return True

    def open_window(self, local_now):
        if self.owner is None or not number(local_now):
            raise ValueError('confirmed binding and local receive window required')
        self.window_sequence += 1
        challenge = f'{self.receiver_session}:{self.window_sequence}'
        self.window = (challenge,local_now)
        return challenge

    def accept(self, command, local_now):
        if command.get('generation') != self.generation or not integer(command.get('generation'),1):
            return False,'STALE_GENERATION'
        if command.get('source') != self.owner:return False,'NOT_OWNER'
        if (command.get('gateway_session') != self.gateway_session or
                command.get('receiver_session') != self.receiver_session):return False,'STALE_SESSION'
        if not self.window or command.get('receive_window') != self.window[0]:return False,'STALE_WINDOW'
        ttl = command.get('ttl_s')
        if not number(ttl) or not 0 < ttl <= self.max_ttl_s or not number(local_now):return False,'EXPIRED_LOCAL_TTL'
        elapsed = local_now-self.window[1]
        if not 0 <= elapsed <= min(ttl,self.retry_window_s):return False,'EXPIRED_LOCAL_TTL'
        if not isinstance(command.get('command_id'),str) or not command['command_id']:return False,'INVALID_COMMAND_ID'
        seq = command.get('command_sequence')
        if not integer(seq,1) or seq <= self.sequence:return False,'STALE_SEQUENCE'
        self.sequence = seq
        return True,None
