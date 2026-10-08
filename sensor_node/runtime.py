"""Host-tested wake/read/evaluate/upload/radio-sleep cycle for deployment logic.

The caller owns the MCU sleep mechanism and next monotonic timestamp. This
object and all algorithm contexts must remain in RAM through light sleep.
It is not an ESP32/E220 adapter and never uses always-on NODE_STATUS keepalive.
"""
import uuid
from common.messages import Message, SENSOR_DATA, ALERT
from common.settings import node_settings
from sensor_node.adaptive_sense import AdaptiveSense
from sensor_node.sensor_trust import SensorTrust
from sensor_node.fault_notifier import FaultNotifier
from sensor_node.telemetry import sensor_payload

class SensorRuntime:
    def __init__(self, node_id, source, transport, owner_gateway, generation, profile='deployment', *, physical=False):
        if physical:
            from common.deployment_security import DeploymentUnavailable
            raise DeploymentUnavailable("physical runtime requires authenticated field transport; current adapter is host-only")
        self.node_id = node_id
        self.source = source
        self.transport = transport
        self.owner_gateway = owner_gateway
        self.generation = generation
        self.boot_id = uuid.uuid4().hex[:12]
        settings = node_settings(profile, physical=physical)
        self.trust = SensorTrust(settings['trust_channels'])
        self.scheduler = AdaptiveSense(settings=settings)
        self.notifications = FaultNotifier(settings['fault_reminder_s'])
        self.samples = self.messages = 0

    async def sample_once(self, timestamp):
        reading = self.source.sample()
        self.samples += 1
        trust = self.trust.update(reading, timestamp)
        schedule = self.scheduler.update(reading, trust, timestamp)
        notification = self.notifications.update(trust, now=timestamp)
        payload = sensor_payload(reading, trust, schedule, self.boot_id, self.samples)
        if schedule['upload_requested'] or notification is not None:
            try:
                await self.transport.wake()
                if schedule['upload_requested']:
                    await self.transport.send(Message(type=SENSOR_DATA,source=self.node_id,target=self.owner_gateway,
                        payload=payload,sequence=self.samples,generation=self.generation,protocol_version=1))
                    self.messages += 1
                    self.scheduler.mark_reported(reading, trust)
                if notification is not None:
                    await self.transport.send(Message(type=ALERT,source=self.node_id,target=self.owner_gateway,
                        payload={**payload,**notification,'sensor_node_id':self.node_id}))
            finally:
                await self.transport.sleep()
        return schedule
