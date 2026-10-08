"""Bounded queues with local wait measurements; metadata never comes off the wire."""
import asyncio
import time


class BoundedQueue(asyncio.Queue):
    def __init__(self, capacity=128, stamp=None):
        if type(capacity) is not int or not 1 <= capacity <= 1024:
            raise ValueError("queue capacity must be 1..1024")
        super().__init__(maxsize=capacity)
        self.times = []
        self.high_water = 0
        self.max_wait_ms = 0.0
        self.stamp = stamp

    def _put(self, item):
        now = time.monotonic()
        if self.stamp:
            self.stamp(item, now)
        super()._put(item)
        self.times.append(now)
        self.high_water = max(self.high_water, self.qsize())

    def _get(self):
        elapsed = max(0.0, time.monotonic() - self.times.pop(0))
        self.max_wait_ms = max(self.max_wait_ms, elapsed * 1000)
        return super()._get()

    def stats(self):
        return {"depth": self.qsize(), "capacity": self.maxsize,
                "high_water": self.high_water, "max_wait_ms": self.max_wait_ms}
