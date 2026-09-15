"""The unified message envelope: serialise, validate, deserialise."""

import pytest

from common.messages import (
    CONTROL_COMMAND,
    HEARTBEAT,
    SENSOR_DATA,
    Message,
    MessageError,
)


def test_message_json_roundtrip_keeps_every_field():
    original = Message(
        type=SENSOR_DATA,
        source="B1",
        target="A1",
        payload={"data": {"soil_moisture": 22.3}, "health_state": "HEALTHY"},
        timestamp=1234567890.5,
        message_id="abc123abc123",
    )

    restored = Message.from_json(original.to_json())

    assert restored.to_dict() == original.to_dict()
    assert restored.payload["data"]["soil_moisture"] == 22.3


def test_missing_required_field_is_rejected():
    with pytest.raises(MessageError):
        Message.from_dict(
            {
                "type": SENSOR_DATA,
                "source": "B1",
                "target": "A1",
                "timestamp": 1.0,
                "message_id": "id-1",
                # payload intentionally missing
            }
        )


def test_unknown_message_type_is_rejected():
    with pytest.raises(MessageError):
        Message.from_dict(
            {
                "type": "TELEPORT",
                "source": "B1",
                "target": "A1",
                "timestamp": 1.0,
                "message_id": "id-2",
                "payload": {},
            }
        )

    # every type the protocol does define is accepted
    for message_type in (SENSOR_DATA, CONTROL_COMMAND, HEARTBEAT):
        message = Message.from_dict(
            {
                "type": message_type,
                "source": "A1",
                "target": "A2",
                "timestamp": 1.0,
                "message_id": "id-3",
                "payload": {},
            }
        )
        assert message.type == message_type
