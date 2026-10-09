"""Bounded logical retry; lower-layer success never releases durable evidence."""
from enum import Enum
import math


class Stage(str, Enum):
    FRAME_ACCEPTED = "FRAME_ACCEPTED"
    MESSAGE_REASSEMBLED = "MESSAGE_REASSEMBLED"
    GATEWAY_DURABLE = "GATEWAY_DURABLE"
    SERVER_DURABLE = "SERVER_DURABLE"
    COMMAND_RECEIVED = "COMMAND_RECEIVED"
    COMMAND_EXECUTED = "COMMAND_EXECUTED"
    COMMAND_REJECTED = "COMMAND_REJECTED"
    COMMAND_UNKNOWN = "COMMAND_UNKNOWN"


class DeliveryWindow:
    def __init__(self, capacity=8, attempts=5, timeout=3.0, *, recovery_interval=None, max_recovery_interval=300.0):
        if type(capacity) is not int or type(attempts) is not int or not 1 <= capacity <= 64 or not 1 <= attempts <= 10 or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("delivery bounds")
        self.capacity, self.attempts, self.timeout = capacity, attempts, timeout
        if recovery_interval is not None and (type(recovery_interval) not in (int,float) or
                not math.isfinite(recovery_interval) or not timeout <= recovery_interval <= max_recovery_interval or
                type(max_recovery_interval) not in (int,float) or not math.isfinite(max_recovery_interval) or max_recovery_interval > 3600):
            raise ValueError('recovery bounds')
        # None is a finite experiment window: FAILED evidence stays retained,
        # and incomplete delivery remains incomplete. Long-lived adapters opt
        # into isolated low-frequency probes, without another rapid retry burst.
        self.recovery_interval = recovery_interval
        self.max_recovery_interval = max_recovery_interval
        self.pending = {}
        self.last_time = None

    def _time(self, now):
        if type(now) not in (int,float) or not math.isfinite(now) or now < 0 or (self.last_time is not None and now < self.last_time):
            raise ValueError('invalid or rolled back delivery clock')
        self.last_time = now

    def admit(self, message, now):
        self._time(now)
        from .codec import canonical
        canonical(message)
        if message.message_id in self.pending:
            # Updating an active logical identity with different business data
            # must be rejected by the application, never silently overwritten.
            if canonical(self.pending[message.message_id]["message"]) != canonical(message):
                raise ValueError("active logical identity conflict")
            return False
        if len(self.pending) == self.capacity:
            raise ValueError("delivery capacity")
        self.pending[message.message_id] = {"message":message,"attempts":0,"due":now,"failed":False,
            "probes":0, "probe_interval":self.recovery_interval}
        return True

    def due(self, now):
        self._time(now)
        messages = []
        for p in self.pending.values():
            if now < p["due"]:
                continue
            if p['failed']:
                if self.recovery_interval is None:continue
                p['probes'] += 1
                p['due'] = now + p['probe_interval']
                p['probe_interval'] = min(self.max_recovery_interval, p['probe_interval'] * 2)
                messages.append(p['message'])
                continue
            if p["attempts"] >= self.attempts:
                p["failed"] = True
                if self.recovery_interval is not None:p['due'] = now + self.recovery_interval
                continue
            p["attempts"] += 1; p["due"] = now+self.timeout
            messages.append(p["message"])
        return messages

    def confirm(self, ack, stage):
        key = ack.payload.get("ack_message_id")
        p = self.pending.get(key)
        if p is None or ack.source != p["message"].target or ack.target != p["message"].source:
            return False
        payload = ack.payload
        if stage == Stage.GATEWAY_DURABLE:
            valid = ack.type == "PERSISTED_ACK" and payload.get("persisted") is True and payload.get("scope") == "GATEWAY_OUTBOX" and payload.get("delivery_contract") == "gateway-durable-v1"
        elif stage == Stage.SERVER_DURABLE:
            valid = ack.type == "PERSISTED_ACK" and payload.get("persisted") is True and payload.get("scope") in (None, "SERVER_SQLITE")
        elif stage == Stage.COMMAND_RECEIVED:
            valid = ack.type == "ACK"
        else:
            valid = False
        if valid:
            del self.pending[key]
        return valid
