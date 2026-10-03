"""Unknown is null; observed zero requires an instrumented measurement."""
from collections import Counter
import time

METRIC_NAMES=('sensor_samples','trusted_samples','degraded_samples','fault_samples',
 'messages_sent','messages_delivered','acks','retries','duplicates','delivery_failures',
 'control_commands','control_executed','control_rejected','duplicate_execution_prevented',
 'gateway_failovers','recovery_time','offline_queued','queue_replayed','server_duplicates_ignored',
 'decision_counts','decision_latency','sampling_interval_mean','sampling_interval_distribution',
 'dropped','deduplicated','latency')

class Metrics:
    def __init__(self):self.values={k:None for k in METRIC_NAMES}
    def set(self,key,value):self.values[key]=value
    def as_dict(self):
        return {k:{'value':v,'status':'not measured' if v is None else 'observed'} for k,v in self.values.items()}

class TransportRecorder:
    def __init__(self):
        self.start=time.monotonic();self.events=[];self.counts=Counter();self.sent={};self.latencies=[]
    def __call__(self,event,message):
        now=time.monotonic();key=(message.message_id,message.source,message.target)
        self.counts[event]+=1
        if event=='sent':self.sent.setdefault(key,now)
        if event=='delivered' and key in self.sent:self.latencies.append(now-self.sent[key])
        self.events.append({'time_s':now-self.start,'event':event,'message':message.to_dict()})
