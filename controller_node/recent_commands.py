"""Bounded durable intent/result window. A future MCU backend uses NVS.

Unfinished intents are never evicted. Their outcome may be unknown after a
crash, but they must never authorize a second actuator run.
"""
from collections import OrderedDict
from copy import deepcopy
from common.state_store import StateError

class RecentCommandStore:
    def __init__(self, store=None, capacity=64):
        if type(capacity) is not int or not 1 <= capacity <= 1024:
            raise ValueError('invalid recent command capacity')
        self.store, self.capacity = store, capacity
        self.entries = OrderedDict()
        if store:
            saved = store.load('recent_commands', validator=self.validate)
            if saved:
                self.entries = OrderedDict((row['command_id'], row) for row in saved['entries'])
                self._trim(self.entries)
            self._save(self.entries)

    @staticmethod
    def validate(saved):
        if type(saved['schema_version']) is not int or saved['schema_version'] != 1 or type(saved['capacity']) is not int or not 1 <= saved['capacity'] <= 1024:
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

    def _trim(self, entries):
        while len(entries) > self.capacity:
            victim = next((cid for cid,row in entries.items() if row['state'] == 'COMPLETED'), None)
            if victim is None:raise StateError('recent command window full of unresolved intents')
            del entries[victim]

    def _save(self, entries):
        if self.store:
            self.store.save('recent_commands', {'schema_version':1,'capacity':self.capacity,'entries':list(entries.values())})

    def begin(self, command_id):
        if not isinstance(command_id,str) or not 1 <= len(command_id) <= 256:
            raise StateError('invalid durable command id')
        if command_id in self.entries:raise StateError('command already admitted')
        candidate = deepcopy(self.entries)
        candidate[command_id] = {'command_id':command_id,'state':'INTENT','result':None}
        self._trim(candidate)
        self._save(candidate)  # Never publish in-memory intent before commit.
        self.entries = candidate

    def complete(self, command_id, result):
        candidate = deepcopy(self.entries)
        candidate[command_id].update(state='COMPLETED',result=dict(result))
        self._save(candidate)
        self.entries = candidate
