"""Validate business semantics before consuming an upload's dedup identity.

Sensor faults remain history (including out-of-range and missing values);
malformed field types are not valid evidence. Legacy partial sensor records
and envelope timestamp fallback remain supported.
"""
import json
from common import config
from common.messages import Message, MessageError, SENSOR_DATA, CONTROL_COMMAND, CONTROL_RESULT, ALERT, HEARTBEAT, ACK
from common.protocol import integer, number

STATUSES = {'EXECUTED', 'REJECTED', 'DUPLICATE', 'UNKNOWN', 'NOT_DISPATCHED'}

def require(condition, reason):
    if not condition:
        raise MessageError(reason)

def text(value):
    return isinstance(value, str) and bool(value.strip()) and value != '?'

def validate_server_upload(message):
    Message.from_dict(message.to_dict())
    require(message.source in config.GATEWAY_PORTS and message.target == 'SERVER', 'invalid upload route')
    p = message.payload
    if message.type == SENSOR_DATA:
        r = p.get('record')
        require(isinstance(r, dict), 'record must be object')
        require(r.get('sensor_node_id') in config.GATEWAY_OF_SENSOR, 'invalid sensor_node_id')
        require(number(r.get('timestamp', message.timestamp)), 'invalid sensor timestamp')
        require(r.get('health_state', 'HEALTHY') in ('HEALTHY', 'DEGRADED', 'FAULT'), 'invalid health state')
        fields = ('temperature', 'humidity', 'soil_moisture', 'light')
        require(any(k in r for k in fields), 'sensor record has no channels')
        for k in fields:
            if k in r:
                require(r[k] is None or number(r[k]), f'invalid sensor field {k}')
        json.dumps(r, allow_nan=False)
    elif message.type == CONTROL_COMMAND:
        require(text(p.get('command_id')), 'invalid command_id')
        require(p.get('controller_id') in config.GATEWAY_OF_CONTROLLER, 'invalid controller_id')
        require(isinstance(p.get('type'),str) and p['type'] in config.MAX_DURATION, 'invalid command type')
        require(number(p.get('duration')) and p['duration'] > 0, 'invalid duration')
        require(integer(p.get('gateway_generation')), 'invalid command generation')
    elif message.type == CONTROL_RESULT:
        require(text(p.get('command_id')), 'invalid result command_id')
        require(p.get('controller_id') in config.GATEWAY_OF_CONTROLLER, 'invalid result controller_id')
        require(isinstance(p.get('status'),str) and p['status'] in STATUSES, 'invalid result status')
        require(integer(p.get('generation')), 'invalid result generation')
        if p['status'] in ('EXECUTED', 'DUPLICATE', 'NOT_DISPATCHED') or p.get('command_type') is not None:
            require(isinstance(p.get('command_type'),str) and p['command_type'] in config.MAX_DURATION, 'invalid result command_type')
        require(p.get('reason') is None or isinstance(p['reason'], str), 'invalid result reason')
        if p['status'] in ('REJECTED', 'NOT_DISPATCHED', 'UNKNOWN'):
            require(text(p.get('reason')), 'failure requires reason')
    elif message.type == ALERT:
        require(text(p.get('alert_type')), 'invalid alert_type')
        require(text(p.get('message')), 'invalid alert message')
        if 'sensor_node_id' in p:
            require(p['sensor_node_id'] in config.GATEWAY_OF_SENSOR, 'invalid alert sensor_node_id')
        json.dumps(p, allow_nan=False)
    elif message.type == HEARTBEAT:
        require(p.get('gateway_id') == message.source, 'invalid heartbeat gateway')
        require(p.get('status') in ('ONLINE', 'OFFLINE', 'UNKNOWN'), 'invalid heartbeat status')
        require(p.get('peer_id') == config.PEER_OF[message.source], 'invalid heartbeat peer')
        require(p.get('peer_status') in ('ONLINE', 'OFFLINE', 'UNKNOWN'), 'invalid peer_status')
        if 'generation' in p:require(integer(p['generation']), 'invalid heartbeat generation')
        if 'role' in p:require(p['role'] in ('ACTIVE','STANDBY'), 'invalid heartbeat role')
    elif message.type == ACK:
        require(text(p.get('ack_message_id')), 'invalid policy ACK')
    else:
        raise MessageError('not a server upload')
