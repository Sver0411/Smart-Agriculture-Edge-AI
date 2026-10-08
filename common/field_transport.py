"""Field message contract. Mock only; an E220 driver is not implemented.

Adapters retain message identity, route, epoch and ACK/result distinction.
Radio framing/fragmentation, discovery and takeover handshake require RF tests.

Field B uplinks use ZoneUplink (source_node_id/zone_id/sequence/boot_id/payload)
from common.field_contract. B belongs to a Zone, not permanently to a Gateway.
Only the current zone owner processes control. B does not probe gateway health.
FieldFreshnessGuard models the future local command freshness contract; it does
not replace the existing TCP timestamp protocol. No E220 wire format exists yet.
"""
from typing import Protocol
from common.messages import Message

class FieldTransport(Protocol):
    async def wake(self) -> None: ...
    async def send(self, message: Message) -> None: ...
    async def sleep(self) -> None: ...

class MockFieldTransport:
    """Host test sink with observable radio lifecycle, no RF/energy claims."""
    def __init__(self):
        self.awake = False
        self.events = []
        self.messages = []

    async def wake(self):
        self.awake = True
        self.events.append('wake')

    async def send(self, message):
        if not self.awake:raise RuntimeError('radio asleep')
        self.messages.append(Message.from_json(message.to_json()))
        self.events.append('send')

    async def sleep(self):
        self.awake = False
        self.events.append('sleep')
