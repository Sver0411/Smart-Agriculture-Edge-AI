"""Minimal stdout logger.

Every process prints one line per event, prefixed with the node id so that the
interleaved output of a full demo run stays readable::

    01:15:14 [A1] received SENSOR_DATA from B1
"""

import time

__all__ = ["node_log"]


def node_log(node_id: str, message: str) -> None:
    """Print ``message`` tagged with ``node_id``."""
    print(f"{time.strftime('%H:%M:%S')} [{node_id}] {message}", flush=True)
