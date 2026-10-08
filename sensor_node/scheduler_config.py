"""Translate validated agriculture settings into the upstream scheduler API."""
from .change_detector import AnalyzerConfig, ChannelConfig

def ladder(cfg,state):
    return list(cfg["adaptive"]["ladders"][state.lower()])
def confirmations(cfg,state):
    return cfg["adaptive"]["ladder_confirmations"].get(state.lower(),1)
def analyzer_config(cfg):
    a=cfg["adaptive"]
    return AnalyzerConfig(channels=tuple(ChannelConfig(name=k,**c) for k,c in a["channels"].items()),
        history_capacity=min(64, int(a["analyzer"]["variety_window_s"] / cfg["sampling"]["min_interval"]) + 2),
        **a["analyzer"], event_threshold=a["event_threshold"], event_min_duration_s=a["event_min_duration_s"])
