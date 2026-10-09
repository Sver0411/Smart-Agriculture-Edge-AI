"""Pure product preparation; stateful admission/ACK tests remain on Gateway."""
from copy import deepcopy

import pytest

from common.messages import ALERT, Message, SENSOR_DATA
from gateway.sensor_pipeline import (
    finalize_sensor_record, fresh_at_decision, prepare_alert_upload, prepare_sensor_record,
)


def prepare(payload, *, engine="rule", received_boot="gateway", now=2.0):
    message = Message(type=SENSOR_DATA, source="B1", target="A1", timestamp=100, payload=payload)
    return prepare_sensor_record(
        message, engine_name=engine, gateway_boot_id="gateway", received_boot_id=received_boot,
        received_monotonic=0.0, received_wall=200.0, prepared_monotonic=now,
    )


def test_normalization_preserves_input_and_separates_history_from_control():
    payload = {"data": {"soil_moisture": 10, "temperature": 25}, "boot_id": "b",
               "sampling": {"interval_s": 20}, "delivery_age_ms": 1000}
    original = deepcopy(payload)
    prepared = prepare(payload)
    record, events = finalize_sensor_record(prepared, payload, reliable=True, registered_boot="b", fresh=True)
    assert prepared.trusted == {"soil_moisture", "temperature"}
    assert record["control_trust"] == {"IRRIGATION": True, "VENTILATION": True}
    assert record["effective_delivery_age_ms"] == 3000
    assert record["gateway_queue_wait_ms"] == 2000
    assert record["usable_for_control"] and events == ()
    assert record["timestamp"] == 100 and record["received_at"] == 200
    assert record["sampling"] == {"interval_s": 20}
    assert "effective_delivery_age_ms" not in prepared.record
    assert payload == original


@pytest.mark.parametrize("data", [None, [], "invalid"])
def test_invalid_data_shape_is_rejected_without_state(data):
    assert prepare({"data": data}) is None


def test_missing_data_remains_history_but_cannot_control():
    prepared = prepare({})
    record, events = finalize_sensor_record(prepared, {}, reliable=False, registered_boot=None, fresh=True)
    assert not record["usable_for_control"] and prepared.trusted == set()
    assert events == ()  # Missing fields do not invent a freshness error.


@pytest.mark.parametrize("value", [True, "10", float("nan"), float("inf"), -1, 101])
def test_invalid_reading_is_retained_in_history_and_excluded_from_trust(value):
    prepared = prepare({"data": {"soil_moisture": value}})
    assert prepared.record["soil_moisture"] is value
    assert not prepared.usable_for_control
    assert prepared.record["control_trust"]["IRRIGATION"] is False


@pytest.mark.parametrize("engine,usable", [("rule", True), ("tree", False)])
def test_existing_trust_gate_keeps_action_and_learned_requirements(engine, usable):
    prepared = prepare({
        "data": {"soil_moisture": 10, "temperature": 36, "humidity": 60, "light": 800},
        "health_state": "FAULT", "health": {
            "soil_moisture": {"state": "FAULT"}, "temperature": {"state": "HEALTHY"},
            "humidity": {"state": "HEALTHY"}, "light": {"state": "HEALTHY"},
        },
    }, engine=engine)
    assert prepared.usable_for_control is usable
    assert prepared.trusted == {"temperature", "humidity", "light"}
    assert prepared.record["control_trust"] == {"IRRIGATION": False, "VENTILATION": True}


def test_legacy_aggregate_untrusted_channel_is_not_control_input():
    prepared = prepare({"data": {"soil_moisture": 10}, "health_state": "FAULT"})
    assert not prepared.usable_for_control and prepared.trusted == set()


def test_trust_gate_fault_injection_still_uses_existing_module(monkeypatch):
    from gateway import trust_gate
    monkeypatch.setattr(trust_gate, "trusted_channels", lambda data, payload: set())
    prepared = prepare({"data": {"soil_moisture": 10, "temperature": 36}})
    assert not prepared.usable_for_control and prepared.trusted == set()


@pytest.mark.parametrize("age,boot,fresh,usable,events", [
    (3000, "b", True, True, ()),  # Exact 5 s boundary includes the queue's 2 s.
    (3001, "b", True, False, ("freshness_rejected_expired",)),
    (1000, "previous-boot", True, False, ("freshness_rejected_boot",)),
    (None, "b", True, False, ("freshness_rejected_unknown",)),
    (-1, "b", True, False, ("freshness_rejected_unknown",)),
    (True, "b", True, False, ("freshness_rejected_unknown",)),
    (1000, "b", False, False, ("reordered_or_duplicate_samples",)),
    (3001, "b", False, False, ("freshness_rejected_expired", "reordered_or_duplicate_samples")),
])
def test_reliable_age_boot_and_order_are_explicit_inputs(age, boot, fresh, usable, events):
    payload = {"data": {"soil_moisture": 10}, "boot_id": boot, "delivery_age_ms": age}
    record, actual_events = finalize_sensor_record(
        prepare(payload), payload, reliable=True, registered_boot="b", fresh=fresh,
    )
    assert record["usable_for_control"] is usable and actual_events == events


@pytest.mark.parametrize("received_boot,now", [("old-gateway-boot", 2.0), ("gateway", -1.0)])
def test_unknown_or_backward_ingress_clock_fails_closed(received_boot, now):
    payload = {"data": {"temperature": 36}, "delivery_age_ms": 0, "boot_id": "b"}
    prepared = prepare(payload, received_boot=received_boot, now=now)
    for reliable in (False, True):
        record, events = finalize_sensor_record(prepared, payload, reliable=reliable, registered_boot="b", fresh=True)
        assert not record["usable_for_control"] and events == ("freshness_rejected_unknown",)
        assert record["gateway_queue_wait_ms"] is None


@pytest.mark.parametrize("age,boot,usable", [(1000, "b", True), (3001, "b", False),
                                          (1000, "old", False), (None, "b", False)])
def test_physical_legacy_clock_boot_and_metric_semantics(age, boot, usable):
    payload = {"data": {"temperature": 36}, "node_mode": "physical",
               "boot_id": boot, "delivery_age_ms": age}
    record, events = finalize_sensor_record(prepare(payload), payload, reliable=False, registered_boot="b", fresh=True)
    assert record["timestamp"] == 200  # Physical wall time comes from Gateway ingress.
    assert record["usable_for_control"] is usable
    assert events == (() if usable else ("freshness_rejected_unknown",))


def test_legacy_queue_expiry_and_duplicate_are_both_reported():
    payload = {"data": {"soil_moisture": 10}}
    record, events = finalize_sensor_record(prepare(payload, now=6), payload,
                                            reliable=False, registered_boot=None, fresh=False)
    assert not record["usable_for_control"]
    assert events == ("freshness_rejected_expired", "reordered_or_duplicate_samples")


@pytest.mark.parametrize("reliable,age,now,expected", [
    (True, 1000, 4.0, True), (True, 1000, 4.001, False),
    (True, None, 1.0, False), (False, None, 5.0, True),
    (False, None, 5.001, False), (False, None, -1.0, False),
])
def test_decision_recheck_uses_new_clock_after_admission(reliable, age, now, expected):
    assert fresh_at_decision({"delivery_age_ms": age}, reliable=reliable,
                             received_monotonic=0.0, decision_monotonic=now) is expected


def test_reliable_alert_preserves_delivery_identity_without_mutation():
    from test_b1_gateway_receipts import sample
    message = sample(kind=ALERT)
    message.message_id = message.payload["sample_id"] + "-A"
    original = deepcopy(message.to_dict())
    payload, reasons = prepare_alert_upload(message, reliable=True)
    for key in ("sample_id", "boot_id", "sample_seq", "device_monotonic_ms",
                "importance", "policy_version", "delivery_contract"):
        assert payload[key] == message.payload[key]
    assert payload["sensor_node_id"] == "B1" and reasons == []
    assert message.to_dict() == original
