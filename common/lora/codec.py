"""AL v1: little-endian, 70-byte header, max 4096 bytes / 64 fragments.

Full logical identities remain in bounded canonical JSON. The header uses a
128-bit SHA256 prefix solely for reassembly lookup (birthday bound ~2**64);
completed messages must match the full original identity. CRC is not a MAC.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import struct
import zlib
from common.messages import Message, MessageError, MESSAGE_TYPES

HEADER = struct.Struct("<2s6B16s16sII5HIII")
HEADER_SIZE = HEADER.size
MAX_MESSAGE = 4096
MAX_FRAGMENTS = 64
MAX_FRAME = 256
ROLES = ("SERVER", "A1", "A2", "B1", "B2", "C1", "C2")
TYPES = MESSAGE_TYPES


class FrameError(ValueError):
    pass


def identity(value):
    if not isinstance(value, str) or not 1 <= len(value.encode()) <= 128:
        raise FrameError("identity length")
    return hashlib.sha256(value.encode()).digest()[:16]


def route(source, destination, kind):
    if source not in ROLES or destination not in ROLES or kind not in TYPES:
        raise FrameError("unknown endpoint/type")
    a = source in ("A1", "A2"); b = source in ("B1", "B2"); c = source in ("C1", "C2")
    da = destination in ("A1", "A2"); db = destination in ("B1", "B2"); dc = destination in ("C1", "C2")
    allowed = ((b and da and kind in ("SENSOR_DATA", "ALERT", "NODE_REGISTER", "NODE_STATUS")) or
               (a and db and kind in ("PERSISTED_ACK", "ACK", "NODE_REGISTER_ACK", "NODE_STATUS", "SERVER_POLICY")) or
               (c and da and kind in ("CONTROL_RESULT", "ACK", "NODE_REGISTER", "NODE_STATUS")) or
               (a and dc and kind in ("CONTROL_COMMAND", "NODE_REGISTER_ACK", "NODE_STATUS")) or
               (a and da and source != destination and kind in ("HEARTBEAT", "NODE_STATUS")))
    if not allowed:
        raise FrameError("unsupported link/type")
    node = source if b or c else destination if db or dc else None
    return int(node[-1]) if node else 0


def canonical(message):
    # Run the same application validator used by the existing TCP endpoints.
    Message.from_dict(message.to_dict())
    identity(message.message_id)
    raw = json.dumps(message.to_dict(), sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode()
    if not 1 <= len(raw) <= MAX_MESSAGE:
        raise FrameError("message capacity exceeded")
    return raw


@dataclass(frozen=True)
class Frame:
    kind: int
    source: int
    destination: int
    zone: int
    session: bytes
    logical: bytes
    sequence: int
    generation: int
    index: int
    count: int
    total: int
    chunk: int
    message_crc: int
    payload: bytes

    def encode(self):
        header = HEADER.pack(b"AL", 1, self.kind, self.source, self.destination, self.zone, 0,
            self.session, self.logical, self.sequence, self.generation,
            self.index, self.count, self.total, len(self.payload), self.chunk,
            self.message_crc, zlib.crc32(self.payload), 0)
        wire = header + self.payload
        wire = wire[:66] + struct.pack("<I", zlib.crc32(wire)) + wire[70:]
        decode(wire)
        return wire

    @property
    def key(self):
        # Different wire attempts of one business identity may differ in age.
        return (self.source, self.destination, self.session, self.logical, self.message_crc)

    @property
    def metadata(self):
        return (self.kind, self.source, self.destination, self.zone, self.session,
                self.logical, self.sequence, self.generation, self.count, self.total,
                self.chunk, self.message_crc)


def decode(wire):
    if not isinstance(wire, bytes) or not HEADER_SIZE < len(wire) <= MAX_FRAME:
        raise FrameError("frame length")
    values = HEADER.unpack(wire[:HEADER_SIZE])
    magic, version, kind, src, dst, zone, flags, session, logical, seq, gen, idx, count, total, plen, chunk, mcrc, pcrc, fcrc = values
    if magic != b"AL" or version != 1 or flags != 0:
        raise FrameError("version/magic/flags")
    if kind >= len(TYPES) or src >= len(ROLES) or dst >= len(ROLES) or zone != route(ROLES[src], ROLES[dst], TYPES[kind]):
        raise FrameError("source/destination/zone/type")
    if not (1 <= total <= MAX_MESSAGE and 1 <= chunk <= MAX_FRAME - HEADER_SIZE and
            1 <= count <= MAX_FRAGMENTS and count == math.ceil(total/chunk) and 0 <= idx < count):
        raise FrameError("fragment bounds")
    expected = min(chunk, total-idx*chunk)
    if plen != expected or len(wire) != HEADER_SIZE + plen:
        raise FrameError("fragment payload length")
    payload = wire[HEADER_SIZE:]
    zeroed = wire[:66] + b"\x00"*4 + payload
    if zlib.crc32(payload) != pcrc or zlib.crc32(zeroed) != fcrc:
        raise FrameError("CRC")
    return Frame(kind, src, dst, zone, session, logical, seq, gen, idx, count, total, chunk, mcrc, payload)


def fragment(message, session, mtu=160):
    if not isinstance(session, bytes) or len(session) != 16:
        raise FrameError("session length")
    if type(mtu) is not int or not HEADER_SIZE < mtu <= MAX_FRAME:
        raise FrameError("MTU")
    raw = canonical(message); chunk = mtu-HEADER_SIZE
    count = math.ceil(len(raw)/chunk)
    if count > MAX_FRAGMENTS:
        raise FrameError("fragment capacity exceeded")
    seq = message.sequence if message.sequence is not None else message.payload.get("sample_seq", 0)
    gen = message.generation if message.generation is not None else message.payload.get("gateway_generation", message.payload.get("generation", 0))
    if type(seq) is not int or not 0 <= seq <= 0xffffffff or type(gen) is not int or not 0 <= gen <= 0xffffffff:
        raise FrameError("sequence/generation width")
    zone = route(message.source, message.target, message.type)
    return [Frame(TYPES.index(message.type), ROLES.index(message.source), ROLES.index(message.target), zone,
        session, identity(message.message_id), seq, gen, i, count, len(raw), chunk,
        zlib.crc32(raw), raw[i*chunk:(i+1)*chunk]).encode() for i in range(count)]


def application(raw, frame):
    try:
        m = Message.from_json(raw.decode("utf-8"))
        if (identity(m.message_id) != frame.logical or ROLES[frame.source] != m.source or
            ROLES[frame.destination] != m.target or TYPES[frame.kind] != m.type):
            raise FrameError("application/header mismatch")
        seq = m.sequence if m.sequence is not None else m.payload.get("sample_seq", 0)
        gen = m.generation if m.generation is not None else m.payload.get("gateway_generation",m.payload.get("generation",0))
        if seq != frame.sequence or gen != frame.generation:
            raise FrameError("application epoch/sequence mismatch")
        return m
    except (UnicodeError, MessageError, ValueError, RecursionError) as exc:
        raise FrameError(str(exc)) from exc
