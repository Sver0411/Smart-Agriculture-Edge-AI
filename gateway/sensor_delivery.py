"""Opt-in B→A contract. A committed outbox is not a cloud receipt.

Identities and canonical content survive ACK loss and gateway restart. This
is a trusted TCP lab contract, not cryptographic device authentication.
"""
import hashlib
import json
from common.messages import SENSOR_DATA, ALERT, MessageError
from common.protocol import integer, number

CONTRACT = 'gateway-durable-v1'


def identity_and_digest(message):
    p = message.payload
    boot, seq = p.get('boot_id'), p.get('sample_seq')
    if (message.type not in (SENSOR_DATA, ALERT) or
            not isinstance(boot, str) or not 1 <= len(boot) <= 80 or
            any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-' for c in boot) or
            not integer(seq, 1) or seq > 0xffffffff or message.sequence != seq):
        raise MessageError('invalid reliable sample identity')
    sample_id = f'{message.source}-{boot}-{seq:08x}'
    suffix = '-S' if message.type == SENSOR_DATA else '-A'
    if p.get('sample_id') != sample_id or message.message_id != sample_id + suffix:
        raise MessageError('retry must preserve canonical identity')
    if (p.get('importance') not in ('HIGH', 'NORMAL') or
            not isinstance(p.get('policy_version'), str) or not p['policy_version'] or
            not number(p.get('device_monotonic_ms')) or p['device_monotonic_ms'] < 0):
        raise MessageError('invalid reliable sample metadata')
    # Local transport age can change; sampled evidence must remain identical.
    evidence = {k: v for k, v in p.items() if k != 'delivery_age_ms'}
    raw = json.dumps(evidence, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return message.message_id, hashlib.sha256(raw.encode()).hexdigest()
