"""SensorTrust - the basic data trust check of v0.1."""

from sensor_node.sensor_trust import FAULT, HEALTHY, check_sensor_health, health_reasons

GOOD_READING = {
    "temperature": 24.5,
    "humidity": 61.0,
    "soil_moisture": 33.0,
    "light": 850.0,
}


def test_healthy_reading_passes():
    assert check_sensor_health(GOOD_READING) == HEALTHY
    assert health_reasons(GOOD_READING) == []


def test_missing_field_is_a_fault():
    broken = dict(GOOD_READING)
    broken.pop("soil_moisture")

    assert check_sensor_health(broken) == FAULT
    assert "missing soil_moisture" in health_reasons(broken)


def test_out_of_range_reading_is_a_fault():
    assert check_sensor_health({**GOOD_READING, "soil_moisture": 999.0}) == FAULT
    assert check_sensor_health({**GOOD_READING, "temperature": 120.0}) == FAULT
    assert check_sensor_health({**GOOD_READING, "humidity": -3.0}) == FAULT
    assert check_sensor_health({**GOOD_READING, "light": -5.0}) == FAULT
