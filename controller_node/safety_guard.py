"""Safety Guard - a controller never executes a command directly.

Every ``CONTROL_COMMAND`` that arrives at C has to pass this check first.  If
anything is wrong the command is refused and the reason is sent back to the
gateway.

Checks performed by v0.1:

* the command type is one we know (``IRRIGATION`` / ``VENTILATION``)
* the ``command_id`` is present and has not been executed before
* the command is not expired (older than ``COMMAND_TTL``)
* the command was issued by the gateway that currently owns this controller,
  at an epoch that is not older than the one we already accepted
  (``STALE_GENERATION`` / ``NOT_OWNER`` - the split-brain guard)
* ``duration`` is a positive number
* ``duration`` does not exceed the maximum allowed for that type
* the controller is not inside the cooldown window of that type
"""

from __future__ import annotations

import pathlib
import sys
import time
import math

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common.protocol import number
from common import config  # noqa: E402

# rejection reasons
INVALID_TYPE = "INVALID_TYPE"
INVALID_COMMAND_ID = "INVALID_COMMAND_ID"
DUPLICATE_COMMAND_ID = "DUPLICATE_COMMAND_ID"
EXPIRED = "EXPIRED"
STALE_GENERATION = "STALE_GENERATION"
NOT_OWNER = "NOT_OWNER"
INVALID_DURATION = "INVALID_DURATION"
DURATION_EXCEEDED = "DURATION_EXCEEDED"
COOLDOWN = "COOLDOWN"
STATE_UNAVAILABLE = "STATE_UNAVAILABLE"


class SafetyGuard:
    """Stateful command validator (one instance per controller)."""

    def __init__(
        self,
        max_duration: dict | None = None,
        cooldown: dict | None = None,
        command_ttl: float = config.COMMAND_TTL,
        store=None,
    ):
        self.max_duration = {**config.MAX_DURATION, **(max_duration or {})}
        self.cooldown = {**config.COOLDOWN, **(cooldown or {})}
        self.command_ttl = command_ttl

        self.executed_command_ids: set[str] = set()
        self.last_executed: dict[str, float] = {}

        # Ownership: which gateway may drive us, and at which epoch.
        self.owner_gateway: str | None = None
        self.current_generation: int = config.INITIAL_GENERATION
        self.store = store
        self.persistence_fault = False
        if store:
            from common.state_store import StateError
            import sqlite3
            def validate(saved):
                if type(saved["highest_generation"]) is not int or saved["highest_generation"] < 1:
                    raise StateError("invalid controller epoch")
                if saved["owner_gateway"] not in (None, *config.GATEWAY_PORTS):
                    raise StateError("invalid controller owner")
            try:
                saved = store.load("controller", validator=validate)
                if saved:
                    self.current_generation = saved["highest_generation"]
                    self.owner_gateway = saved["owner_gateway"]
                    # Monotonic timestamps cannot be restored across boots.
                    # Conservatively wait a full cooldown after a restart.
                    self.last_executed = {label:time.monotonic() for label in self.cooldown}
            except (StateError, sqlite3.Error, OSError):
                self.persistence_fault = True

    # -- ownership ---------------------------------------------------------

    def set_ownership(self, owner_gateway: str, generation: int) -> bool:
        """Adopt a new owner.  Older epochs are refused (no silent downgrade)."""
        if (type(generation) is not int or generation < self.current_generation or
                (generation == self.current_generation and self.owner_gateway not in (None, owner_gateway))):
            return False
        if self.persistence_fault:
            return False
        if self.store:
            import sqlite3
            try:
                self.store.save("controller", {"highest_generation":generation, "owner_gateway":owner_gateway,
                                                "restart_actuator_state":"OFF", "restart_cooldown":"full"})
            except (sqlite3.Error, OSError):
                self.persistence_fault = True
                return False
        self.owner_gateway = owner_gateway
        self.current_generation = int(generation)
        return True

    # -- checks ------------------------------------------------------------

    def check(
        self,
        command_id: str | None,
        command_type: str | None,
        duration,
        issued_at: float,
        now: float | None = None,
        gateway_generation: int | None = None,
        source_gateway: str | None = None,
        monotonic_now: float | None = None,
    ) -> tuple[bool, str | None]:
        """Return ``(True, None)`` when the command may be executed.

        The order below is deliberate: cheap and unambiguous rejections first,
        then the ownership/epoch checks that keep a deposed gateway out, and
        only then the actuator specific limits.
        """
        elapsed_now = (monotonic_now if monotonic_now is not None else
                       time.monotonic() if now is None else now)
        now = time.time() if now is None else now
        if self.persistence_fault:
            return False, STATE_UNAVAILABLE

        # 1. message / command validity
        if not isinstance(command_type,str) or command_type not in self.max_duration:
            return False, INVALID_TYPE
        if not isinstance(command_id,str) or not command_id:
            return False, INVALID_COMMAND_ID

        # 2. freshness
        if not number(issued_at) or issued_at > now + self.command_ttl or now - issued_at > self.command_ttl:
            return False, EXPIRED

        # 3. generation (epoch) - replay and split-brain protection
        if gateway_generation is not None and (type(gateway_generation) is not int or gateway_generation < self.current_generation):
            return False, STALE_GENERATION

        # 4. owner gateway - a gateway may only take over with a newer epoch
        if source_gateway and self.owner_gateway and source_gateway != self.owner_gateway:
            if gateway_generation is None or gateway_generation <= self.current_generation:
                return False, NOT_OWNER

        # 5. idempotency - a retry of an already executed command is refused
        if command_id in self.executed_command_ids:
            return False, DUPLICATE_COMMAND_ID

        # 6. duration
        if not number(duration) or duration <= 0:
            return False, INVALID_DURATION
        if duration > self.max_duration[command_type]:
            return False, DURATION_EXCEEDED

        # 7. cooldown
        previous = self.last_executed.get(command_type)
        if previous is not None and elapsed_now - previous < self.cooldown.get(command_type, 0.0):
            return False, COOLDOWN

        return True, None

    def commit(
        self,
        command_id: str,
        command_type: str,
        now: float | None = None,
        gateway_generation: int | None = None,
        source_gateway: str | None = None,
        monotonic_now: float | None = None,
    ) -> None:
        """Record a command that has just been executed."""
        self.executed_command_ids.add(command_id)
        self.last_executed[command_type] = (monotonic_now if monotonic_now is not None else
                                           time.monotonic() if now is None else now)
        if gateway_generation is not None and gateway_generation > self.current_generation:
            self.current_generation = int(gateway_generation)
        if source_gateway and (gateway_generation is not None and gateway_generation >= self.current_generation
                               or gateway_generation is None and self.owner_gateway in (None, source_gateway)):
            self.owner_gateway = source_gateway
