"""Pure preparation of sensor history and control inputs.

Gateway supplies ingress/decision clocks, registered boot and the result of its
sequence or receipt check. This module owns no clock, receipt ledger, policy,
ownership or transport. In particular, preparing a record never admits it or
authorizes a command; Gateway must recheck age and live ownership after awaits.
"""

from __future__ import annotations

from dataclasses import dataclass

from common.messages import Message
from common.protocol import number
from gateway import trust_gate


MAX_CONTROL_AGE_MS = 5000


@dataclass(frozen=True)
class PreparedSensor:
    """Per-message values, without changing the incoming payload or gateway state."""

    record: dict
    trusted: set[str]
    usable_for_control: bool
    physical: bool
    queue_wait_ms: float | None


def prepare_sensor_record(
    message: Message,
    *,
    engine_name: str,
    gateway_boot_id: str,
    received_boot_id: str,
    received_monotonic: float,
    received_wall: float,
    prepared_monotonic: float,
) -> PreparedSensor | None:
    """Copy history fields and assess channel trust; None means invalid data shape.

    Invalid individual readings remain in history, but trust_gate excludes them
    from control. Sample order and registered-boot freshness are evaluated only
    after Gateway performs its existing stateful freshness check.
    """
    payload = message.payload
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return None
    record = dict(data)
    trusted = trust_gate.trusted_channels(record, payload)
    usable = (bool(trusted & {"soil_moisture", "temperature"}) if engine_name == "rule"
              else trusted >= trust_gate.FEATURE_CHANNELS)
    wait_ms = ((prepared_monotonic - received_monotonic) * 1000
               if received_boot_id == gateway_boot_id and prepared_monotonic >= received_monotonic
               else None)
    physical = payload.get("node_mode") == "physical"
    record["control_trust"] = {action: trusted >= required for action, required in trust_gate.ACTION_CHANNELS.items()}
    record["trusted_channels"] = sorted(trusted)
    record["timestamp"] = received_wall if physical else message.timestamp
    record["received_at"] = received_wall
    record["gateway_received_monotonic"] = received_monotonic
    record["gateway_decision_monotonic"] = prepared_monotonic
    record["gateway_boot_id"] = gateway_boot_id
    record["gateway_queue_wait_ms"] = wait_ms
    for key in ("node_mode", "boot_id", "sample_seq", "device_monotonic_ms", "timestamp_source",
                "sampling", "health", "health_score", "fault_flags", "physical_read_ok",
                "test_injected", "severity", "sample_id", "importance", "policy_version", "delivery_contract"):
        if key in payload:
            record[key] = payload[key]
    return PreparedSensor(record, trusted, usable, physical, wait_ms)


def finalize_sensor_record(
    prepared: PreparedSensor,
    payload: dict,
    *,
    reliable: bool,
    registered_boot: str | None,
    fresh: bool,
) -> tuple[dict, tuple[str, ...]]:
    """Apply age/boot/order eligibility and return the original metric events.

    The caller applies these events and retains all stateful dedup/admission
    operations. A stored historical record may be valid even when ineligible
    for control. Legacy physical inputs retain their existing metric category.
    """
    record = dict(prepared.record)
    usable = prepared.usable_for_control
    wait_ms = prepared.queue_wait_ms
    events = []
    if reliable:
        age = payload.get("delivery_age_ms")
        effective_age = age + wait_ms if number(age) and age >= 0 and wait_ms is not None else None
        record["effective_delivery_age_ms"] = effective_age
        usable = usable and (effective_age is not None and effective_age <= MAX_CONTROL_AGE_MS and
                             payload.get("boot_id") == registered_boot)
        if effective_age is None:
            events.append("freshness_rejected_unknown")
        elif effective_age > MAX_CONTROL_AGE_MS:
            events.append("freshness_rejected_expired")
        elif payload.get("boot_id") != registered_boot:
            events.append("freshness_rejected_boot")
    elif wait_ms is None or wait_ms > MAX_CONTROL_AGE_MS or (prepared.physical and not (
            number(payload.get("delivery_age_ms")) and
            0 <= payload["delivery_age_ms"] + wait_ms <= MAX_CONTROL_AGE_MS and
            isinstance(payload.get("boot_id"), str) and payload["boot_id"] == registered_boot)):
        usable = False
        events.append("freshness_rejected_unknown" if wait_ms is None or prepared.physical
                      else "freshness_rejected_expired")
    if not fresh:
        usable = False
        events.append("reordered_or_duplicate_samples")
    record["usable_for_control"] = usable
    return record, tuple(events)


def fresh_at_decision(
    payload: dict,
    *,
    reliable: bool,
    received_monotonic: float,
    decision_monotonic: float,
) -> bool:
    """Recheck age using a caller-supplied clock at the post-admission boundary."""
    elapsed_ms = (decision_monotonic - received_monotonic) * 1000
    return not (elapsed_ms < 0 or elapsed_ms > MAX_CONTROL_AGE_MS or (reliable and
                (not number(payload.get("delivery_age_ms")) or
                 payload["delivery_age_ms"] + elapsed_ms > MAX_CONTROL_AGE_MS)))


def prepare_alert_upload(message: Message, *, reliable: bool) -> tuple[dict, list[str]]:
    """Build alert evidence; Message identity, logging and delivery stay in Gateway."""
    payload = message.payload
    raw_reasons = payload.get("reasons", [])
    reasons = (raw_reasons if isinstance(raw_reasons, list) and all(isinstance(r, str) for r in raw_reasons)
               else ["malformed sensor fault evidence"])
    upload_payload = {
        "alert_type": payload.get("alert_type", "SENSOR_FAULT"),
        "health": payload.get("health", {}), "health_score": payload.get("health_score"),
        "fault_flags": payload.get("fault_flags", []), "data": payload.get("data", {}),
        "fault_signature": payload.get("fault_signature"), "notification": payload.get("notification"),
        "sensor_node_id": message.source,
        "health_state": payload.get("health_state", "HEALTHY"),
        "severity": payload.get("severity"),
        "message": "; ".join(reasons) or payload.get("message", "sensor alert"),
    }
    if reliable:
        upload_payload.update({k: payload[k] for k in (
            "sample_id", "boot_id", "sample_seq", "device_monotonic_ms", "importance", "policy_version", "delivery_contract")})
    return upload_payload, reasons
