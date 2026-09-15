"""Safety Guard - the controller must refuse dangerous or stale commands."""

from controller_node.safety_guard import (
    COOLDOWN,
    DUPLICATE_COMMAND_ID,
    DURATION_EXCEEDED,
    EXPIRED,
    INVALID_TYPE,
    SafetyGuard,
)

NOW = 1_000_000.0


def guard() -> SafetyGuard:
    return SafetyGuard(max_duration={"IRRIGATION": 30, "VENTILATION": 30}, cooldown={"IRRIGATION": 60.0}, command_ttl=10.0)


def test_valid_command_passes():
    allowed, reason = guard().check("cmd-1", "IRRIGATION", 10, NOW, now=NOW)

    assert allowed is True
    assert reason is None


def test_unknown_command_type_is_rejected():
    allowed, reason = guard().check("cmd-2", "LASER", 10, NOW, now=NOW)

    assert allowed is False
    assert reason == INVALID_TYPE


def test_duration_above_the_limit_is_rejected():
    allowed, reason = guard().check("cmd-3", "IRRIGATION", 31, NOW, now=NOW)

    assert allowed is False
    assert reason == DURATION_EXCEEDED


def test_expired_command_is_rejected():
    allowed, reason = guard().check("cmd-4", "IRRIGATION", 10, NOW - 30.0, now=NOW)

    assert allowed is False
    assert reason == EXPIRED


def test_cooldown_is_enforced():
    guard_instance = guard()
    guard_instance.commit("cmd-5", "IRRIGATION", now=NOW)

    # 30 s later the command is fresh but still inside the 60 s cooldown
    allowed, reason = guard_instance.check("cmd-6", "IRRIGATION", 10, NOW + 30.0, now=NOW + 30.0)
    assert (allowed, reason) == (False, COOLDOWN)

    # after the cooldown window it is accepted again
    allowed, reason = guard_instance.check("cmd-7", "IRRIGATION", 10, NOW + 61.0, now=NOW + 61.0)
    assert (allowed, reason) == (True, None)


def test_duplicate_command_id_is_rejected():
    guard_instance = guard()
    guard_instance.commit("cmd-8", "IRRIGATION", now=NOW)

    allowed, reason = guard_instance.check("cmd-8", "IRRIGATION", 10, NOW, now=NOW + 120.0)

    assert allowed is False
    assert reason == DUPLICATE_COMMAND_ID
