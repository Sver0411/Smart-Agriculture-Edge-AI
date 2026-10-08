"""Cloud-only reconnect state; never participates in farm ownership/control."""
import asyncio
import time
from common.settings import profile_settings

ONLINE, DEGRADED, OFFLINE = 'ONLINE', 'DEGRADED', 'OFFLINE'

class Connectivity:
    def __init__(self, settings=None):
        self.settings = dict(settings or profile_settings()['connectivity'])
        self.backoff = tuple(self.settings['backoff_s'])
        if not self.backoff or any(type(v) not in (int,float) or v <= 0 for v in self.backoff):
            raise ValueError('reconnect backoff must be positive')
        self.failures = 0
        self.state = OFFLINE
        self.early = asyncio.Event()
        self.last_critical_attempt = None

    def failed(self):
        self.failures += 1
        self.state = DEGRADED if self.failures == 1 else OFFLINE
        return self.backoff[min(self.failures-1, len(self.backoff)-1)]

    def connected(self, backlog=False):
        self.state = DEGRADED if backlog else ONLINE

    def confirmed(self, backlog=False):
        self.failures = 0
        self.connected(backlog)

    def request_critical_retry(self, now=None):
        now = time.monotonic() if now is None else now
        if self.state == ONLINE or self.early.is_set():return False
        if self.last_critical_attempt is not None and now-self.last_critical_attempt < self.settings['critical_retry_cooldown_s']:
            return False
        self.last_critical_attempt = now
        self.early.set()
        return True

    async def wait_retry(self, delay):
        try:
            await asyncio.wait_for(self.early.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass
        finally:
            self.early.clear()
