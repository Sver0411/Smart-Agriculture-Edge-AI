"""ACK tracking, retransmission and the counters behind the demo summary.

Delivery in v0.2 is "at least once": the sender keeps a message until it is
acknowledged and retries it a bounded number of times.  The receiver is
idempotent, so a duplicate is harmless - that combination is the whole point.
"""

import pytest

from common import config
from common.messages import CONTROL_COMMAND, Message
from common.reliability import AckTracker, COMMAND_DELIVERY_FAILED, Counters


def command(command_id: str = "cmd-1") -> Message:
    return Message(
        type=CONTROL_COMMAND,
        source="A1",
        target="C1",
        payload={"command_id": command_id, "type": "IRRIGATION", "duration": 10},
    )


# --------------------------------------------------------------------------
# AckTracker
# --------------------------------------------------------------------------


def test_a_tracked_message_waits_for_its_ack():
    tracker = AckTracker(timeout=2.0)
    message = command()
    tracker.track(message, now=1000.0)
    assert len(tracker) == 1
    assert tracker.acknowledge(message.message_id)
    assert len(tracker) == 0


def test_acknowledging_an_unknown_id_is_not_an_error():
    tracker = AckTracker()
    assert tracker.acknowledge("never-seen") is False


def test_a_message_is_due_only_after_its_timeout():
    tracker = AckTracker(timeout=2.0)
    tracker.track(command(), now=1000.0)

    assert tracker.due(now=1001.9) == []
    assert len(tracker.due(now=1002.0)) == 1


def test_a_message_is_retried_at_most_max_retries_times():
    tracker = AckTracker(timeout=2.0, max_retries=config.MAX_RETRIES)
    tracker.track(command(), now=1000.0)

    for attempt in range(1, config.MAX_RETRIES + 1):
        due = tracker.due(now=1000.0 + 2.0 * attempt)
        assert len(due) == 1, f"retry {attempt} should still be pending"
        tracker.mark_retry(due[0].message_id, now=1000.0 + 2.0 * attempt)

    assert tracker.due(now=1100.0) == []
    assert len(tracker.exhausted(now=1100.0)) == 1


def test_exhausted_messages_are_dropped_from_the_tracker():
    tracker = AckTracker(timeout=1.0, max_retries=1)
    message = command()
    tracker.track(message, now=0.0)
    tracker.mark_retry(message.message_id, now=1.0)
    tracker.mark_retry(message.message_id, now=2.0)

    assert len(tracker.exhausted(now=3.0)) == 1
    tracker.discard(message.message_id)
    assert len(tracker) == 0


def test_retry_reschedules_the_deadline():
    tracker = AckTracker(timeout=2.0)
    message = command()
    tracker.track(message, now=0.0)
    tracker.mark_retry(message.message_id, now=2.0)

    # the deadline moved, so the message is not due again immediately
    assert tracker.due(now=2.1) == []
    assert len(tracker.due(now=4.0)) == 1


def test_acks_are_matched_by_message_id_not_by_order():
    tracker = AckTracker(timeout=2.0)
    first = command("first")
    second = command("second")
    tracker.track(first, now=0.0)
    tracker.track(second, now=0.0)

    assert tracker.acknowledge(second.message_id)
    assert len(tracker) == 1
    assert tracker.pending[first.message_id].message is first


def test_delivery_failure_constant_is_stable():
    """The demo and the tests agree on one alert name."""
    assert COMMAND_DELIVERY_FAILED == "COMMAND_DELIVERY_FAILED"


# --------------------------------------------------------------------------
# Counters
# --------------------------------------------------------------------------


def test_counters_start_at_zero_and_increment():
    counters = Counters()
    assert counters.get("commands") == 0
    counters.inc("commands")
    counters.inc("commands", 4)
    assert counters.get("commands") == 5


def test_counters_as_dict_is_sorted_and_plain():
    counters = Counters(zebra=1, alpha=2)
    assert list(counters.as_dict()) == ["alpha", "zebra"]


def test_counters_merge_adds_the_other_side():
    totals = Counters(commands=2)
    totals.merge(Counters(commands=3, retries=1))
    assert totals.as_dict() == {"commands": 5, "retries": 1}


def test_tracker_defaults_follow_the_configuration():
    """The retry policy lives in one place: ``common.config``."""
    tracker = AckTracker()
    assert tracker.timeout == config.ACK_TIMEOUT
    assert tracker.max_retries == config.MAX_RETRIES
    assert config.ACK_TIMEOUT > 0
    assert config.MAX_RETRIES >= 1
