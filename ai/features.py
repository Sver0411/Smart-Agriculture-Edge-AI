"""Versioned agriculture feature order shared by training and inference."""
import math
from common import config
FEATURE_NAMES=("soil_margin", "temperature_margin", "humidity", "log_light")
FEATURE_VERSION=1

class FeatureError(ValueError):
    pass

def extract_features(sample,policy=None):
    policy={**config.DEFAULT_POLICY,**(policy or {})}
    values=[]
    for name in ("soil_moisture","temperature","humidity","light"):
        v=sample.get(name)
        if type(v) not in (int,float) or not math.isfinite(v) or not config.SENSOR_RANGES[name][0]<=v<=config.SENSOR_RANGES[name][1]:
            raise FeatureError(f"invalid or missing {name}")
        values.append(v)
    soil,temp,humidity,light=values
    return [(soil-policy["soil_moisture_threshold"])/25,
            (temp-policy["temperature_threshold"])/10,humidity/100,math.log1p(light)/12]
