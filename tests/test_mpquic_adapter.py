"""The live bridge must preserve the farm's original JSON and application receipts."""

import asyncio
import json
import socket
from types import SimpleNamespace

import pytest

from backhaul.bridge import MAX_LINE, METADATA, identify, pump


def frame(kind, identity, payload):
    message = {"type": kind, "source": "SERVER", "target": "A1", "timestamp": 1,
               "message_id": identity, "payload": payload}
    return (json.dumps(message, ensure_ascii=False, indent=None) + "\n").encode()


def test_envelope_requires_one_bounded_message():
    line = frame("SENSOR_DATA", "s1", {"text": "温室"})
    assert identify(line) == ("SENSOR_DATA", "s1")
    for invalid in (line.removesuffix(b"\n"), line + line, b"[]\n", b"{}\n", b" " * MAX_LINE + line):
        with pytest.raises(ValueError):
            identify(invalid)


def test_bridge_preserves_uplink_and_distinct_reverse_messages():
    async def scenario():
        # Datagram sockets preserve one-record framing for this isolated Python
        # adapter test. The Linux native bridge uses SOCK_SEQPACKET.
        bridge, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        bridge.setblocking(False)
        peer.setblocking(False)
        reader = asyncio.StreamReader()
        output = []
        flushed = asyncio.Event()

        class Writer:
            def write(self, line):
                output.append(line)

            async def drain(self):
                flushed.set()

        options = SimpleNamespace(role="gateway", event_budget_ms=1000, state_budget_ms=5000)
        task = asyncio.create_task(pump(reader, Writer(), bridge, options))
        loop = asyncio.get_running_loop()
        try:
            for kind, priority, budget in (("SENSOR_DATA", 1, 5000000), ("ALERT", 2, 1000000)):
                original = frame(kind, "s1", {"text": "温室", "v": 22.4})
                reader.feed_data(original)
                observed = await asyncio.wait_for(loop.sock_recv(peer, MAX_LINE + METADATA.size), 2)
                assert METADATA.unpack_from(observed) == (priority, budget)
                assert observed[METADATA.size:] == original
            for kind, body in (("PERSISTED_ACK", {"ack_message_id": "s1", "persisted": True}),
                               ("SERVER_POLICY", {"policy_version": 4})):
                flushed.clear()
                original = frame(kind, "r1", body)
                await loop.sock_sendall(peer, original)
                await asyncio.wait_for(flushed.wait(), 2)
                assert output[-1] == original
            reader.feed_eof()
            await asyncio.wait_for(task, 2)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            bridge.close()
            peer.close()

    asyncio.run(scenario())
