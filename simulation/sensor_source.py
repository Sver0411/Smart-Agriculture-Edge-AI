"""Source contract allows deterministic replay without changing SensorNode."""
from typing import Protocol

class SensorSource(Protocol):
    def sample(self) -> dict: ...

class ReplaySource:
    def __init__(self,samples,repeat_last=True):
        self._samples=iter(samples);self.last=None;self.repeat_last=repeat_last
    def sample(self):
        try:self.last=dict(next(self._samples))
        except StopIteration:
            if not self.repeat_last or self.last is None:raise
        return dict(self.last)
