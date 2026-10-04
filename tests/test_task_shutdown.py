"""Deterministic regression for legacy asyncio timeout/cancellation races."""
import asyncio
from common.messages import Message, SENSOR_DATA
from gateway.gateway import Gateway


def test_upload_worker_exits_if_in_flight_wait_swallows_cancellation(monkeypatch):
    async def run():
        g=Gateway('A1');entered=asyncio.Event()
        async def legacy_timeout_race(message):
            entered.set()
            try:await asyncio.Future()
            except asyncio.CancelledError:return  # completed wait won the cancellation race
        monkeypatch.setattr(g,'_deliver',legacy_timeout_race)
        await g.upload_queue.put(Message(type=SENSOR_DATA,source='A1',target='SERVER'))
        task=asyncio.create_task(g.task_upload());await entered.wait()
        g._stopping=True;task.cancel()
        await asyncio.wait_for(task,0.5)
        assert task.done()
    asyncio.run(run())
