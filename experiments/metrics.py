"""Unknown is null; observed zero requires an instrumented measurement."""
from collections import Counter, defaultdict, deque
import time

METRIC_NAMES=('sensor_samples','trusted_samples','degraded_samples','fault_samples',
 'messages_sent','messages_delivered','acks','retries','duplicates','delivery_failures',
 'control_commands','control_executed','control_rejected','duplicate_execution_prevented',
 'gateway_failovers','recovery_time','offline_queued','queue_replayed','server_duplicates_ignored',
 'decision_counts','decision_latency','sampling_interval_mean','sampling_interval_distribution',
 'dropped','deduplicated','attempt_transport_latency','logical_delivery_latency','ack_latency','persisted_ack_latency')

class Metrics:
    def __init__(self):self.values={k:None for k in METRIC_NAMES}
    def set(self,key,value):self.values[key]=value
    def as_dict(self):
        return {k:{'value':v,'status':'not measured' if v is None else 'observed'} for k,v in self.values.items()}

class TransportRecorder:
    def __init__(self):
        self.start = time.monotonic()
        self.end = None
        self.events = []
        self.counts = Counter()
        self.first_attempt = {}
        self.sent_attempts = defaultdict(deque)
        self.delivered_logical = set()
        self.attempt_latencies = []
        self.logical_latencies = []
        self.ack_latencies = []
        self.persisted_ack_latencies = []
        self.acked_logical = set()

    def freeze(self):
        """Close the measurement window before asynchronous teardown starts."""
        if self.end is None:self.end=time.monotonic()

    def __call__(self, event, message):
        if self.end is not None:return
        now = time.monotonic()
        key = (message.message_id, message.source, message.target)
        attempt_key = (*key, message.attempt)
        self.counts[event] += 1
        if event in ('send_attempt', 'sent'):
            self.first_attempt.setdefault(key, now)
        if event == 'sent':
            self.sent_attempts[attempt_key].append(now)
        if event == 'delivered':
            sends = self.sent_attempts.get(attempt_key)
            if sends:
                self.attempt_latencies.append(now-sends.popleft())
                if not sends:self.sent_attempts.pop(attempt_key, None)
            if key in self.first_attempt and key not in self.delivered_logical:
                self.logical_latencies.append(now-self.first_attempt[key])
                self.delivered_logical.add(key)
            if message.type in ('ACK', 'PERSISTED_ACK'):
                original = (message.payload.get('ack_message_id'), message.target, message.source)
                ack_key = (message.type, original)
                if original in self.first_attempt and ack_key not in self.acked_logical:
                    values = self.ack_latencies if message.type == 'ACK' else self.persisted_ack_latencies
                    values.append(now-self.first_attempt[original])
                    self.acked_logical.add(ack_key)
        self.events.append({'time_s': now-self.start, 'event': event, 'message': message.to_dict()})
