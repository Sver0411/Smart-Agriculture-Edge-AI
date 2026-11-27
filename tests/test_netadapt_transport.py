import asyncio
import hashlib
import random
from dataclasses import dataclass

from common.lora.scheduled_transport import ScheduledLoRa
from common.messages import Message
from third_party.netadapt import fud_ada


@dataclass
class Head:
    flow: int
    spec: fud_ada.Flow
    generated: int


def choice_cases():
    rng = random.Random(2907)
    for _ in range(256):
        t = rng.randrange(2, 140)
        delay = rng.randrange(6)
        tokens = rng.randrange(10)
        heads, states = [], {}
        for i in range(6):
            event = i % 3 == 1
            spec = fud_ada.Flow("event" if event else "status", rng.randrange(1, 7),
                                rng.randrange(1, 40), rng.randrange(1, 24) if event else None,
                                rng.randrange(1, 13))
            states[i] = fud_ada.Feedback(rng.randrange(t), rng.uniform(0.1, 1), rng.uniform(0, 50))
            heads.append(Head(i, spec, rng.randrange(1, t)))
        yield t, delay, tokens, heads, states


def test_selection_matches_pinned_upstream_c11():
    # Each byte is 1 + the selected C flow or 0 if no head is eligible.
    choices = []
    for t, delay, tokens, heads, states in choice_cases():
        chosen = fud_ada.choose(t, heads, states, delay=delay, tokens=tokens)
        choices.append(0 if chosen is None else chosen.flow + 1)
    assert set(choices) == set(range(7))
    assert hashlib.sha256(bytes(choices)).hexdigest() == "7026bc3f5f491cc4a556e767575679aca04dd02bf703bc255246ed7680243525"


class Writer:
    def __init__(self):
        self.messages = []

    def write(self, raw):
        self.messages.append(Message.from_json(raw))

    async def drain(self):
        pass


def sample(source, ident, high=False):
    return Message(type="SENSOR_DATA", source=source, target="A1", timestamp=100.0,
                   message_id=ident, payload={"importance": "HIGH" if high else "NORMAL"})


def test_contended_field_application_flows_and_repeatability():
    async def run(policy):
        writer = Writer()
        radio = ScheduledLoRa(policy=policy)
        messages = [sample("B1", "sample-1"), sample("B2", "sample-2"), sample("B1", "urgent-1", True)]
        assert await asyncio.gather(*(radio(writer, msg) for msg in messages)) == [True] * 3
        await radio.close()
        assert radio.metrics["scheduler_decisions"] == radio.metrics["reassembled"] == 3
        assert radio.metrics["contended_decisions"] == 2
        assert [msg.message_id for msg in writer.messages] == [row["message_id"] for row in radio.decisions]
        assert radio.decisions[0]["candidates"] == ["B1>A1/event", "B1>A1/telemetry", "B2>A1/telemetry"]
        return radio.decisions

    fud = asyncio.run(run("fud_ada"))
    assert fud[0]["message_id"] == "urgent-1"
    assert asyncio.run(run("fud_ada")) == fud
    assert asyncio.run(run("fifo"))[0]["message_id"] == "sample-1"


def test_outlet_preserves_receipts_control_and_observes_link_loss():
    async def run():
        radio, writer = ScheduledLoRa(queue_capacity=2), Writer()
        assert not await radio(writer, Message("ACK", "SERVER", "A1"))
        for kind, src, dst in (("CONTROL_COMMAND", "A1", "C1"), ("ACK", "C1", "A1"),
                               ("CONTROL_RESULT", "C1", "A1"), ("PERSISTED_ACK", "A1", "B1")):
            msg = Message(kind, src, dst, {"marker": kind}, message_id=kind)
            assert await radio(writer, msg)
            assert writer.messages[-1].to_dict() == msg.to_dict()
        radio.outage = True
        assert await radio(writer, sample("B1", "lost-record"))
        assert not radio.decisions[-1]["reassembled"]
        radio.outage = False
        assert await radio(writer, sample("B1", "lost-record"))
        assert radio.decisions[-1]["reassembled"]
        assert radio.metrics["reassembled"] == 5
        await radio.close()

    asyncio.run(run())


def test_backpressure_close_and_failure_do_not_leak_callers():
    class PausedWriter(Writer):
        def __init__(self):
            super().__init__()
            self.writing = asyncio.Event()
            self.release = asyncio.Event()

        async def drain(self):
            self.writing.set()
            await self.release.wait()
            raise OSError("disconnected")

    async def run():
        radio = ScheduledLoRa(queue_capacity=1)
        writer = PausedWriter()
        first = asyncio.create_task(radio(writer, sample("B1", "running")))
        await writer.writing.wait()
        blocked = asyncio.create_task(radio(Writer(), sample("B2", "awaiting-capacity")))
        await asyncio.sleep(0)
        assert not blocked.done()
        close = asyncio.create_task(radio.close())
        await asyncio.sleep(0)
        writer.release.set()
        first_error, blocked_error, closed = await asyncio.gather(first, blocked, close, return_exceptions=True)
        assert isinstance(first_error, OSError)
        assert isinstance(blocked_error, RuntimeError)
        assert closed is None
        assert radio.metrics["max_queue_depth"] == 1
        assert radio.metrics["scheduler_decisions"] == 1
        assert not radio.decisions[0]["reassembled"]
    asyncio.run(run())
