"""Action dependencies are distinct from aggregate sensor health.

Per-channel evidence permits independent rule actions. Legacy envelopes with
only aggregate state remain conservative. Learned predictors require all four
valid HEALTHY features. Availability is checked before confirmed fault state.
"""
from common import config
from common.protocol import number

ACTION_CHANNELS = {'IRRIGATION': {'soil_moisture'}, 'VENTILATION': {'temperature'}}
FEATURE_CHANNELS = {'soil_moisture', 'temperature', 'humidity', 'light'}

def trusted_channels(data, payload):
    if payload.get('health_state', 'HEALTHY') not in ('HEALTHY', 'DEGRADED', 'FAULT'):
        return set()
    health = payload.get('health')
    if health is not None and not isinstance(health, dict):
        return set()
    trusted = set()
    for field in FEATURE_CHANNELS:
        value = data.get(field)
        if not number(value) or not config.SENSOR_RANGES[field][0] <= value <= config.SENSOR_RANGES[field][1]:
            continue
        if health is not None:
            channel = health.get(field)
            if (not isinstance(channel, dict) or channel.get('state') != 'HEALTHY'
                    or channel.get('valid') is not True):
                continue
        elif (payload.get('health_state', 'HEALTHY') != 'HEALTHY' or
              payload.get('usable_for_control', True) is not True):
            continue
        trusted.add(field)
    return trusted
