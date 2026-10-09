"""Host field adapter contract, with explicit hardware boundaries.

Host LoRa framing, bounded reassembly and retry live in common.lora. ESP32 B1
has an E220 UART/AUX/mode driver in firmware/b1/main/b1_e220.c and a bounded
radio window. Gateway/controller physical RF endpoints are still missing.
Physical RF/current/latency, reset and GPIO sleep behavior await validation.

Adapters preserve identity, route, epoch and ACK/result distinctions. The mock
below records attempted writes; it provides neither reception nor durability.
A reliable runtime must supply an explicit receive_confirmation(timeout) method
and validate the scoped gateway SQLite receipt. CRC is not authentication.
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
