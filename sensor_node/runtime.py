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
    def __init__(self, node_id, source, transport, owner_gateway, generation, profile='deployment', *, physical=False, delivery_mode="legacy-write", state_path=None):
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
        self.report_window = None
        if delivery_mode not in ('legacy-write','gateway-durable'):raise ValueError('unknown delivery mode')
        if delivery_mode == 'gateway-durable':
            if not state_path or not callable(getattr(transport,'receive_confirmation',None)):
                raise ValueError('reliable runtime requires state database and explicit confirmation adapter')
            from common.state_store import StateStore
            from sensor_node.report_delivery import SensorReportWindow
            self.report_window = SensorReportWindow(node_id,self.boot_id,StateStore(state_path))


    async def sample_once(self, timestamp):
        reading = self.source.sample()
        self.samples += 1
        trust = self.trust.update(reading, timestamp)
        schedule = self.scheduler.update(reading, trust, timestamp)
        notification = self.notifications.update(trust, now=timestamp)
        payload = sensor_payload(reading, trust, schedule, self.boot_id, self.samples)
        outgoing=[]
        if self.report_window:
            from sensor_node.report_delivery import prepare_report
            from common.state_store import StateError
            if schedule['upload_requested']:
                m=Message(type=SENSOR_DATA,source=self.node_id,target=self.owner_gateway,payload=payload,
                    sequence=self.samples,generation=self.generation,protocol_version=1)
                high=bool(schedule.get('detected_event') or schedule.get('control_relevant_change') or
                          'HEALTH_CHANGE' in schedule['upload_reasons'] or 'FIRST_SAMPLE' in schedule['upload_reasons'])
                try:self.report_window.admit(prepare_report(m,timestamp,high=high),reading,trust,timestamp)
                except StateError:pass # baseline stays unconfirmed; next sample can retry the change
            outgoing=self.report_window.due(timestamp,self.owner_gateway)
        if schedule['upload_requested'] and not self.report_window or outgoing or notification is not None:
            try:
                await self.transport.wake()
                if self.report_window:
                    import asyncio
                    for message in outgoing:
                        await self.transport.send(message)
                        self.messages += 1
                        try:
                            ack=await self.transport.receive_confirmation(timeout=3)
                        except asyncio.TimeoutError:
                            ack=None
                        if ack is not None:self.report_window.confirm(ack,self.scheduler,self.owner_gateway)
                elif schedule['upload_requested']:
                    await self.transport.send(Message(type=SENSOR_DATA,source=self.node_id,target=self.owner_gateway,
                        payload=payload,sequence=self.samples,generation=self.generation,protocol_version=1))
                    self.messages += 1
                    # Legacy contract: attempted write, never called durable.
                    self.scheduler.mark_reported(reading, trust)
                if notification is not None:
                    await self.transport.send(Message(type=ALERT,source=self.node_id,target=self.owner_gateway,
                        payload={**payload,**notification,'sensor_node_id':self.node_id}))
            finally:
                await self.transport.sleep()
        return schedule
