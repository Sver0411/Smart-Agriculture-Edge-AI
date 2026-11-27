"""Opt-in simulated B confirmation at the existing gateway SQLite boundary.

HIGH survives restart; NORMAL is RAM-only. A new boot never advances its
baseline from an old boot's ACK. Neither mode changes event detection history.
"""
from copy import deepcopy
from common.messages import Message
from common.state_store import StateError
from common.lora.delivery import DeliveryWindow, Stage
from gateway.sensor_delivery import CONTRACT, identity_and_digest

class SensorReportWindow:
    def __init__(self, node_id, boot_id, store, capacity=16):
        self.node_id, self.boot_id, self.store = node_id, boot_id, store
        self.window = DeliveryWindow(capacity=capacity, recovery_interval=60)
        self.evidence = {}
        saved = store.load('sensor_reports', validator=self.validate)
        if saved:
            if len(saved['reports']) > capacity:raise StateError('sensor delivery capacity')
            for row in saved['reports']:
                m=Message.from_dict(row['message'])
                self.window.admit(m, 0)
                self.evidence[m.message_id]=row

    def validate(self, saved):
        if saved['schema_version']!=1 or not isinstance(saved['reports'],list) or len(saved['reports'])>64:
            raise StateError('invalid sensor report checkpoint')
        seen=set()
        for row in saved['reports']:
            m=Message.from_dict(row['message'])
            identity_and_digest(m)
            if m.source!=self.node_id or m.message_id in seen or m.payload['importance']!='HIGH':
                raise StateError('invalid persisted sensor identity')
            seen.add(m.message_id)

    def _save(self, evidence):
        self.store.save('sensor_reports',{'schema_version':1,'reports':[
            row for row in evidence.values() if row['message']['payload']['importance']=='HIGH']})

    def admit(self, message, reading, trust, acquired_at):
        identity_and_digest(message)
        if message.message_id in self.evidence:return False
        if len(self.evidence)>=self.window.capacity:raise StateError('sensor outbox full')
        normals=sum(row['message']['payload']['importance']=='NORMAL' for row in self.evidence.values())
        if message.payload['importance']=='NORMAL' and normals>=self.window.capacity*3//4:
            raise StateError('sensor NORMAL reserve full')
        candidate=deepcopy(self.evidence)
        candidate[message.message_id]={'message':message.to_dict(),'reading':deepcopy(reading),
                                      'trust':deepcopy(trust),'acquired_at':acquired_at}
        self._save(candidate) # admission must commit before publication
        self.window.admit(message, max(acquired_at, self.window.last_time or 0))
        self.evidence=candidate
        return True

    def due(self, now, owner, scheduler=None):
        outgoing=[]
        on_timeout = getattr(scheduler, "report_timeout", None)
        if on_timeout:
            for entry in self.window.pending.values():
                if entry["attempts"] and now >= entry["due"] and not entry["failed"]:
                    on_timeout()
        for original in self.window.due(now):
            m=Message.from_dict(original.to_dict())
            m.target=owner
            row=self.evidence[m.message_id]
            m.payload['delivery_age_ms']=((now-row['acquired_at'])*1000
                if m.payload['boot_id']==self.boot_id and now>=row['acquired_at'] else None)
            outgoing.append(m)
        return outgoing

    def confirm(self, ack, scheduler, owner):
        row=self.evidence.get(ack.payload.get('ack_message_id'))
        if row is None or ack.source!=owner or ack.target!=self.node_id:return False
        # Bind the current socket owner for a pending historical report.
        original=self.window.pending[ack.payload['ack_message_id']]['message']
        # The TAIS link estimate requires an attempted report before receipt.
        if hasattr(scheduler, 'confirm_report') and not self.window.pending[original.message_id]['attempts']:
            return False
        prior=original.target;original.target=owner
        candidate=deepcopy(self.evidence);del candidate[original.message_id]
        p=ack.payload
        valid=(ack.type=='PERSISTED_ACK' and p.get('persisted') is True and
               p.get('scope')=='GATEWAY_OUTBOX' and p.get('delivery_contract')==CONTRACT)
        if not valid:
            original.target=prior;return False
        try:self._save(candidate)
        except Exception:
            original.target=prior;raise
        if not self.window.confirm(ack, Stage.GATEWAY_DURABLE):
            raise RuntimeError("validated gateway receipt did not match the delivery window")
        self.evidence=candidate
        if row['message']['payload']['boot_id']==self.boot_id:
            evidence = dict(timestamp=row['acquired_at'], sequence=row['message']['sequence'])
            if hasattr(scheduler, 'confirm_report'):
                scheduler.confirm_report(row['reading'], row['trust'], **evidence,
                                         schedule=row['message']['payload']['sampling'])
            else:
                scheduler.mark_reported(row['reading'], row['trust'], **evidence)
        return True


def prepare_report(message, acquired_at, *, high):
    p=message.payload
    if p.get("sampling", {}).get("sensing_policy") == "tais-jalc":
        critical = {"HEALTH_CHANGE", "VALIDITY_CHANGE", "SENSOR_FAULT", "SENSOR_RECOVERY", "EVENT"}
        high = high or bool(critical.intersection(p["sampling"]["upload_reasons"]))
    sample_id=f"{message.source}-{p['boot_id']}-{p['sample_seq']:08x}"
    message.message_id=sample_id+'-S'
    p.update(sample_id=sample_id,delivery_contract=CONTRACT,importance='HIGH' if high else 'NORMAL',
             policy_version=('tais-jalc-c751bd6' if p.get('sampling', {}).get('sensing_policy') == 'tais-jalc' else 'host-profile-v1'),device_monotonic_ms=acquired_at*1000)
    return message
