"""Application protocol contracts and logical-sample ordering."""
import math
from common.messages import MessageError

def integer(value, minimum=0):
    return type(value) is int and value>=minimum

def number(value):
    return type(value) in (int,float) and math.isfinite(value)

class SequenceGuard:
    """Reordered telemetry is auditable history, never a fresh control input.

    Boot ID scopes sequence; legacy messages without sequence stay compatible.
    """
    def __init__(self):self.latest={}
    def accept(self, message):
        if message.sequence is None:return True
        key=(message.source,message.payload.get('boot_id','legacy'))
        previous=self.latest.get(key,-1)
        if message.sequence<=previous:return False
        self.latest[key]=message.sequence
        return True

def validate_policy(payload, current):
    from common import config
    version=payload.get('policy_version')
    if version is not None and not integer(version):raise MessageError('invalid policy_version')
    candidate={**current,**{k:payload[k] for k in config.DEFAULT_POLICY if k in payload}}
    for key,value in candidate.items():
        if not number(value) or value<=0:raise MessageError(f'invalid policy {key}')
    for key in ('soil_moisture_threshold','temperature_threshold'):
        field='soil_moisture' if key.startswith('soil') else 'temperature'
        low,high=config.SENSOR_RANGES[field]
        if not low<=candidate[key]<=high:raise MessageError(f'policy threshold outside range {key}')
    for label,key in (('IRRIGATION','irrigation_duration'),('VENTILATION','ventilation_duration')):
        if candidate[key]>config.MAX_DURATION[label]:raise MessageError(f'policy duration exceeds safety {key}')
    return candidate
