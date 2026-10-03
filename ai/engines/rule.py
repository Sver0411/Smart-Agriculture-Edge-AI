"""Rule baseline remains the default and supports legacy partial readings."""
import math
from common import config

class RuleEngine:
    name="rule"
    def predict(self,sample,policy=None):
        p={**config.DEFAULT_POLICY,**(policy or {})}
        for field,label,threshold,below,duration in (
            ("soil_moisture","IRRIGATION","soil_moisture_threshold",True,"irrigation_duration"),
            ("temperature","VENTILATION","temperature_threshold",False,"ventilation_duration")):
            v=sample.get(field)
            if type(v) not in (int,float) or not math.isfinite(v):continue
            if not config.SENSOR_RANGES[field][0]<=v<=config.SENSOR_RANGES[field][1]:return None
            if (v<p[threshold]) if below else (v>p[threshold]):
                return {"type":label,"duration":p[duration],"reason":f"{field} {v} {'<' if below else '>'} {p[threshold]}"}
        return None
