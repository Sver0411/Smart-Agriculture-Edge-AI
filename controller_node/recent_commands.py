"""One bounded checkpoint for command intents, outcomes and result delivery.

Unfinished intents and unconfirmed results cannot be evicted. An interrupted
physical execution is UNKNOWN; recovery never executes it again.
"""
from collections import OrderedDict
from copy import deepcopy
from common.state_store import StateError
from common.messages import Message

CONTRACT = 'controller-result-durable-v1'

class ResultBackpressure(StateError):
    pass

class RecentCommandStore:
    def __init__(self, store=None, capacity=64):
        if type(capacity) is not int or not 1 <= capacity <= 1024:
            raise ValueError('invalid recent command capacity')
        self.store, self.capacity = store, capacity
        self.entries = OrderedDict()
        self.pending_results = {}
        if store:
            saved = store.load('recent_commands', validator=self.validate)
            if saved:
                self.entries = OrderedDict((row['command_id'], row) for row in saved['entries'])
                self.pending_results = saved.get('pending_results', {})
                self._trim(self.entries)
                if len(self.pending_results) > capacity:
                    raise StateError('pending results exceed configured capacity')
            self._save(self.entries, self.pending_results)

    @staticmethod
    def validate(saved):
        if type(saved['schema_version']) is not int or saved['schema_version'] not in (1,2) or type(saved['capacity']) is not int or not 1 <= saved['capacity'] <= 1024:
            raise StateError('invalid recent command schema')
        rows = saved['entries']
        if not isinstance(rows,list) or len(rows) > saved['capacity']:
            raise StateError('invalid recent command window')
        ids = set()
        for row in rows:
            cid = row['command_id']
            if not isinstance(cid,str) or not 1 <= len(cid) <= 256 or cid in ids:
                raise StateError('invalid/duplicate recent command id')
            ids.add(cid)
            if row['state'] not in ('INTENT','COMPLETED'):
                raise StateError('invalid command state')
            if row['state'] == 'INTENT' and row['result'] is not None:
                raise StateError('intent has result')
            if row['state'] == 'COMPLETED' and (not isinstance(row['result'],dict) or row['result'].get('status') != 'EXECUTED'):
                raise StateError('invalid persisted command result')
        pending = saved.get('pending_results', {})
        if not isinstance(pending, dict) or len(pending) > saved['capacity']:
            raise StateError('invalid result delivery window')
        for key, raw in pending.items():
            message = Message.from_dict(raw)
            if (message.message_id != key or message.type != 'CONTROL_RESULT' or
                    message.payload.get('delivery_contract') != CONTRACT):
                raise StateError('invalid pending result')

    def _trim(self, entries):
        protected = {m['payload']['command_id'] for m in self.pending_results.values()}
        while len(entries) > self.capacity:
            victim = next((cid for cid,row in entries.items() if row['state'] == 'COMPLETED' and cid not in protected), None)
            if victim is None:raise ResultBackpressure('recent command window full of unconfirmed outcomes')
            del entries[victim]

    def _save(self, entries, pending):
        if self.store:
            self.store.save('recent_commands', {'schema_version':2,'capacity':self.capacity,
                'entries':list(entries.values()), 'pending_results':pending})

    def begin(self, command_id, context=None):
        if not isinstance(command_id,str) or not 1 <= len(command_id) <= 256:
            raise StateError('invalid durable command id')
        if command_id in self.entries:raise StateError('command already admitted')
        # Reserve result capacity before permitting an actuator execution.
        if self.store and len(self.pending_results) >= self.capacity:
            raise ResultBackpressure('result delivery capacity full')
        candidate = deepcopy(self.entries)
        candidate[command_id] = {'command_id':command_id,'state':'INTENT','result':None,
                                 'context': context}
        self._trim(candidate)
        self._save(candidate, self.pending_results)
        self.entries = candidate

    def complete(self, command_id, result, message=None):
        candidate = deepcopy(self.entries)
        candidate[command_id].update(state='COMPLETED',result=dict(result))
        pending = self._with_result(message)
        self._save(candidate, pending)
        self.entries, self.pending_results = candidate, pending

    def _with_result(self, message):
        pending = deepcopy(self.pending_results)
        if message is not None and self.store:
            raw = message.to_dict()
            if message.message_id in pending and pending[message.message_id] != raw:
                raise StateError('result identity conflict')
            if message.message_id not in pending and len(pending) >= self.capacity:
                raise ResultBackpressure('result delivery capacity full')
            pending[message.message_id] = raw
        return pending

    def queue_result(self, message):
        pending = self._with_result(message)
        self._save(self.entries, pending)
        self.pending_results = pending

    def acknowledge_result(self, identity):
        if identity not in self.pending_results:return False
        pending = deepcopy(self.pending_results)
        del pending[identity]
        self._save(self.entries, pending)
        self.pending_results = pending
        return True
