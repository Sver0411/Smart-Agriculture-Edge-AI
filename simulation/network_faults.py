"""Small deterministic frame faults for host simulation; no RF/OS packet claims."""
import asyncio
import random
from common.messages import observe_transport

class FrameFaults:
    def __init__(self,rules=(),seed=42):
        self.rules=[dict(rule,applied=0) for rule in rules]
        self.rng=random.Random(seed)
        self.held={}
        self.tasks=[]
        self.events=[]

    async def __call__(self,writer,message):
        rule=next((r for r in self.rules if r['applied']<r.get('count',1)
                   and all(getattr(message,k)==v for k,v in r.get('match',{}).items())),None)
        if rule is None:return False
        if self.rng.random()>rule.get('probability',1):return False
        rule['applied']+=1
        action=rule['action'];self.events.append({'action':action,'message_id':message.message_id})
        if action=='drop':
            observe_transport('dropped',message)
            return True
        if action=='delay':
            async def later():
                await asyncio.sleep(rule['delay_s'])
                writer.write(message.to_line().encode());await writer.drain()
                observe_transport('sent',message)
            self.tasks.append(asyncio.create_task(later()))
            return True
        if action=='duplicate':
            writer.write(message.to_line().encode());await writer.drain()
            observe_transport('sent',message);observe_transport('duplicated',message)
            return False
        if action=='reorder':
            key=id(rule)
            if key not in self.held:
                self.held[key]=(writer,message)
                return True
            oldwriter,oldmessage=self.held.pop(key)
            writer.write(message.to_line().encode());await writer.drain();observe_transport('sent',message)
            oldwriter.write(oldmessage.to_line().encode());await oldwriter.drain();observe_transport('sent',oldmessage)
            observe_transport('reordered',oldmessage)
            return True
        raise ValueError(f'unknown frame fault {action}')

    async def close(self):
        for task in self.tasks:
            if not task.done():task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
