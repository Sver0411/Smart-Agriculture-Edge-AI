"""Regressions found while reviewing development branches for main."""
import asyncio
import json
import sqlite3

import pytest

from common import settings
from common.messages import CONTROL_COMMAND, Message
from common.state_store import StateError, StateStore
from controller_node.controller_node import ControllerNode
from controller_node.recent_commands import RecentCommandStore
from controller_node.safety_guard import SafetyGuard
from gateway.edge_decision import EdgeDecider
from gateway.gateway import Gateway


def remove_current(store, namespace):
    with sqlite3.connect(store.path) as conn:
        conn.execute("DELETE FROM checkpoints WHERE namespace=? AND slot=0", (namespace,))


def test_missing_current_epoch_never_implicitly_loads_previous_slot(tmp_path):
    store = StateStore(tmp_path / "state.db")
    store.save("epoch", {"generation": 2})
    store.save("epoch", {"generation": 3})
    remove_current(store, "epoch")
    with pytest.raises(StateError):
        store.load("epoch")
    assert store.load("epoch", allow_previous=True) == {"generation": 2}


def test_missing_controller_epoch_disables_execution(tmp_path):
    store = StateStore(tmp_path / "controller.db")
    guard = SafetyGuard(store=store)
    assert guard.set_ownership("A1", 1)
    assert guard.set_ownership("A2", 2)
    remove_current(store, "controller")
    reboot = SafetyGuard(store=store)
    assert reboot.persistence_fault
    assert not reboot.set_ownership("A1", 1)


def test_missing_gateway_epoch_disables_control(tmp_path):
    path = tmp_path / "gateway.db"
    gateway = Gateway("A2", state_path=str(path))
    gateway._takeover()
    remove_current(gateway.state_store, "ownership")
    reboot = Gateway("A2", state_path=str(path))
    assert reboot.persistence_fault
    assert not reboot.ownership.may_control("C2")


def test_missing_current_command_window_cannot_forget_recent_intent(tmp_path):
    store = StateStore(tmp_path / "commands.db")
    recent = RecentCommandStore(store)
    recent.begin("unresolved-command")
    remove_current(store, "recent_commands")
    with pytest.raises(StateError):
        RecentCommandStore(store)


def test_policy_can_explicitly_restore_previous_slot(tmp_path):
    store = StateStore(tmp_path / "policy.db")
    engine = EdgeDecider(store=store)
    engine.update_policy({"policy_version": 2, "temperature_threshold": 34})
    engine.update_policy({"policy_version": 3, "temperature_threshold": 36})
    remove_current(store, "policy")
    restored = EdgeDecider(store=store)
    assert restored.policy_version == 2
    assert restored.policy["temperature_threshold"] == 34


def test_controller_live_id_window_matches_durable_bound(tmp_path, monkeypatch):
    monkeypatch.setitem(settings.SETTINGS["controller"], "recent_command_capacity", 2)

    async def run():
        guard = SafetyGuard(store=StateStore(tmp_path / "controller.db"),
                            cooldown={"IRRIGATION": 0, "VENTILATION": 0})
        controller = ControllerNode("C1", safety_guard=guard, time_scale=0)
        for i in range(5):
            command = Message(type=CONTROL_COMMAND, source="A1", target="C1",
                              payload={"command_id": f"bounded-{i}", "type": "IRRIGATION",
                                       "duration": 1, "gateway_generation": 1})
            assert (await controller.process_command(command))["status"] == "EXECUTED"
        assert guard.executed_command_ids == set(controller.recent_commands.entries)
        assert guard.executed_command_ids == {"bounded-3", "bounded-4"}
        assert (await controller.process_command(command))["status"] == "DUPLICATE"
        assert controller.metrics.get("executed") == 5

    asyncio.run(run())


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "slow", None])
def test_invalid_replay_interval_is_rejected_at_config_load(tmp_path, monkeypatch, value):
    profile = settings.profile_settings("simulation")
    profile["connectivity"]["replay_interval_s"] = value
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "simulation.json").write_text(json.dumps(profile))
    monkeypatch.setattr(settings, "CONFIG_PATH", tmp_path / "software.json")
    with pytest.raises(ValueError):
        settings.profile_settings("simulation")


def test_zero_replay_interval_remains_supported():
    assert settings.profile_settings("simulation")["connectivity"]["replay_interval_s"] == 0
