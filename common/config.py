"""Compatibility aliases from the validated software source of truth."""
from common.settings import SETTINGS
for _name, _value in SETTINGS["system"].items():
    globals()[_name] = _value
DEFAULT_POLICY = dict(SETTINGS["policy"])
SENSOR_RANGES = {name: (c["min_value"], c["max_value"]) for name,c in SETTINGS["node"]["trust_channels"].items()}
def gateway_queue_path(gateway_id):
    return GATEWAY_QUEUE_DB_TEMPLATE.format(gateway_id=gateway_id)
