"""edge_decision - the swappable edge AI interface."""

from common import config
from gateway.edge_decision import IRRIGATION, VENTILATION, EdgeDecider, edge_decision


def test_dry_soil_triggers_irrigation():
    decision = edge_decision({"soil_moisture": 22.3, "temperature": 25.0})

    assert decision is not None
    assert decision["type"] == IRRIGATION
    assert decision["duration"] == config.DEFAULT_POLICY["irrigation_duration"]


def test_hot_temperature_triggers_ventilation():
    decision = edge_decision({"soil_moisture": 40.0, "temperature": 33.1})

    assert decision is not None
    assert decision["type"] == VENTILATION
    assert decision["duration"] == config.DEFAULT_POLICY["ventilation_duration"]


def test_normal_conditions_trigger_nothing():
    assert edge_decision({"soil_moisture": 40.0, "temperature": 25.0}) is None


def test_server_policy_changes_the_thresholds():
    decider = EdgeDecider()
    decider.update_policy({"soil_moisture_threshold": 15.0, "temperature_threshold": 40.0})

    assert decider.decide({"soil_moisture": 20.0, "temperature": 25.0}) is None
    assert decider.decide({"soil_moisture": 20.0, "temperature": 41.0})["type"] == VENTILATION
