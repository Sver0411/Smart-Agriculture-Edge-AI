"""Socket-bound challenge sessions. Lab enrollment is NOT authentication.

HMAC mode needs an out-of-band shared random key (>=32 bytes). Nonces bind the
proof to this socket; heartbeat sequence and session reject replay. No general
network-partition consensus is provided by authentication.
"""
import hashlib
import hmac
import json
import secrets


def nonce():
    return secrets.token_hex(16)


def tag(key, body):
    return hmac.new(key, json.dumps(body, sort_keys=True, separators=(",", ":"),
                                   allow_nan=False).encode(), hashlib.sha256).hexdigest()


def verify(key, body, supplied):
    return isinstance(supplied, str) and hmac.compare_digest(tag(key, body), supplied)


def proof(source, target, client, session):
    return {"source": source, "target": target, "client": client, "session": session}
