import math
import zlib
from .codec import decode, application, FrameError, MAX_MESSAGE


class Reassembler:
    def __init__(self, capacity=4, timeout=3.0, sessions=None):
        if type(capacity) is not int or not 1 <= capacity <= 16 or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("reassembly bounds")
        self.capacity, self.timeout = capacity, timeout
        self.sessions = dict(sessions or {})
        self.slots = {}
        self.last_now = None
        self.expired = self.duplicates = self.rejected = 0

    def expire(self, now):
        if not math.isfinite(now) or now < 0 or self.last_now is not None and now < self.last_now:
            self.slots.clear()
            raise FrameError("receiver clock rollback")
        self.last_now = now
        for key, slot in list(self.slots.items()):
            if now >= slot["deadline"]:
                del self.slots[key]; self.expired += 1

    def feed(self, wire, now):
        self.expire(now)
        f = decode(wire)
        if f.source in self.sessions and self.sessions[f.source] != f.session:
            self.rejected += 1
            raise FrameError("session mismatch")
        slot = self.slots.get(f.key)
        if slot is None:
            if len(self.slots) >= self.capacity:
                self.rejected += 1
                raise FrameError("reassembly capacity")
            slot = self.slots[f.key] = {"frame": f, "deadline": now+self.timeout,
                "payload": bytearray(f.total), "seen": set(), "quarantined": False}
        if slot["quarantined"] or f.metadata != slot["frame"].metadata:
            slot["quarantined"] = True
            raise FrameError("fragment metadata conflict")
        start = f.index*f.chunk
        if f.index in slot["seen"]:
            if slot["payload"][start:start+len(f.payload)] != f.payload:
                slot["quarantined"] = True
                raise FrameError("duplicate fragment conflict")
            self.duplicates += 1
        else:
            slot["payload"][start:start+len(f.payload)] = f.payload
            slot["seen"].add(f.index)
        if len(slot["seen"]) != f.count:
            return None
        raw = bytes(slot["payload"])
        del self.slots[f.key]
        if zlib.crc32(raw) != f.message_crc:
            raise FrameError("message CRC")
        return application(raw, f)

    @property
    def reserved_bytes(self):
        return sum(len(s["payload"]) for s in self.slots.values())
