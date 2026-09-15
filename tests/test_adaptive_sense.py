"""AdaptiveSense - the sampling interval must follow the environment."""

from common import config
from sensor_node.adaptive_sense import next_sample_interval, relative_change


def reading(soil, temperature=25.0):
    return {"temperature": temperature, "humidity": 60.0, "soil_moisture": soil, "light": 800.0}


def test_stable_history_keeps_the_slow_interval():
    history = [reading(30.0), reading(30.2)]

    assert relative_change(*history) < 0.05
    assert next_sample_interval(history) == config.SAMPLE_INTERVAL_SLOW


def test_changing_history_switches_to_the_fast_interval():
    history = [reading(30.0), reading(22.0)]

    assert next_sample_interval(history) == config.SAMPLE_INTERVAL_FAST


def test_short_history_uses_the_slow_interval():
    assert next_sample_interval([]) == config.SAMPLE_INTERVAL_SLOW
    assert next_sample_interval([reading(30.0)]) == config.SAMPLE_INTERVAL_SLOW
