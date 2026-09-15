"""Safety Guard - a controller never executes a command directly.

Every ``CONTROL_COMMAND`` that arrives at C has to pass this check first.  If
anything is wrong the command is refused and the reason is sent back to the
gateway.

Checks performed by v0.1:

* the command type is one we know (``IRRIGATION`` / ``VENTILATION``)
* the ``command_id`` is present and has not been executed before
* the command is not expired (older than ``COMMAND_TTL``)
* ``duration`` is a positive number
* ``duration`` does not exceed the maximum allowed for that type
* the controller is not inside the cooldown window of that type
"""

from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import config  # noqa: E402

# rejection reasons
INVALID_TYPE = "INVALID_TYPE"
INVALID_COMMAND_ID = "INVALID_COMMAND_ID"
DUPLICATE_COMMAND_ID = "DUPLICATE_COMMAND_ID"
EXPIRED = "EXPIRED"
INVALID_DURATION = "INVALID_DURATION"
DURATION_EXCEEDED = "DURATION_EXCEEDED"
COOLDOWN = "COOLDOWN"


class SafetyGuard:
    """Stateful command validator (one instance per controller)."""

    def __init__(
        self,
        max_duration: dict | None = None,
        cooldown: dict | None = None,
        command_ttl: float = config.COMMAND_TTL,
    ):
        self.max_duration = {**config.MAX_DURATION, **(max_duration or {})}
        self.cooldown = {**config.COOLDOWN, **(cooldown or {})}
        self.command_ttl = command_ttl

        self.executed_command_ids: set[str] = set()
        self.last_executed: dict[str, float] = {}

    # -- checks ------------------------------------------------------------

    def check(
        self,
        command_id: str | None,
        command_type: str | None,
        duration,
        issued_at: float,
        now: float | None = None,
    ) -> tuple[bool, str | None]:
        """Return ``(True, None)`` when the command may be executed."""
        now = time.time() if now is None else now

        if command_type not in self.max_duration:
            return False, INVALID_TYPE

        if not command_id:
            return False, INVALID_COMMAND_ID

        if command_id in self.executed_command_ids:
            return False, DUPLICATE_COMMAND_ID

        if now - issued_at > self.command_ttl:
            return False, EXPIRED

        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
            return False, INVALID_DURATION

        if duration > self.max_duration[command_type]:
            return False, DURATION_EXCEEDED

        previous = self.last_executed.get(command_type)
        if previous is not None and now - previous < self.cooldown.get(command_type, 0.0):
            return False, COOLDOWN

        return True, None

    def commit(self, command_id: str, command_type: str, now: float | None = None) -> None:
        """Record a command that has just been executed."""
        self.executed_command_ids.add(command_id)
        self.last_executed[command_type] = time.time() if now is None else now
