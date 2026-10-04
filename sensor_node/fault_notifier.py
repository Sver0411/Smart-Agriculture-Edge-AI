"""State/signature transitions and monotonic reminders, without sample floods."""
import json
import time
from common.settings import node_settings

class FaultNotifier:
    def __init__(self, reminder_s=None):
        self.reminder_s = node_settings()['fault_reminder_s'] if reminder_s is None else reminder_s
        if self.reminder_s <= 0:raise ValueError('reminder interval must be positive')
        self.signature = None
        self.last_notified = None
        self.was_suspect = False

    def update(self, trust, now=None):
        now = time.monotonic() if now is None else now
        suspect = trust['state'] != 'HEALTHY' or not trust['usable_for_control']
        signature = json.dumps({'state':trust['state'], 'channels':{
            name:{'state':r['state'],'valid':r['valid'],'fault_flags':sorted(r['fault_flags'])}
            for name,r in sorted(trust['channels'].items())}}, sort_keys=True)
        changed = signature != self.signature
        emit = (suspect and (changed or self.last_notified is None or now-self.last_notified >= self.reminder_s)
                or not suspect and self.was_suspect)
        previous_suspect = self.was_suspect
        self.signature = signature
        self.was_suspect = suspect
        if not emit:return None
        self.last_notified = now
        return {'alert_type':'SENSOR_RECOVERED' if not suspect else
                ('SENSOR_FAULT' if trust['state']=='FAULT' else 'SENSOR_DEGRADED'),
                'fault_signature':signature,
                'notification':'recovery' if previous_suspect and not suspect else 'transition' if changed else 'reminder',
                'message':'sensor channels recovered' if not suspect else 'sensor quality changed or remains suspect'}
