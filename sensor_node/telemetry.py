"""Sensor business payload construction independent of sockets/radio drivers."""
import math

def sensor_payload(reading, trust, schedule, boot_id, sequence):
    wire = {k:(v if type(v) in (int,float) and math.isfinite(v) else None) for k,v in reading.items()}
    return {'data':wire,'health_state':trust['state'],'boot_id':boot_id,'sample_seq':sequence,
            'health_score':trust['health_score'],'fault_flags':trust['fault_flags'],
            'health':trust['channels'],'sampling':schedule,'usable_for_control':trust['usable_for_control']}
