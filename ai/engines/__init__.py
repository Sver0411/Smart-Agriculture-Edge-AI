from .rule import RuleEngine
from .logistic import LogisticEngine
from .tree import TreeEngine
from .mlp import MLPEngine
ENGINES={e.name:e for e in (RuleEngine,LogisticEngine,TreeEngine,MLPEngine)}
def create_engine(name="rule",artifact=None):
    if name not in ENGINES:raise ValueError(f"unknown engine {name}")
    return ENGINES[name]() if name=="rule" else ENGINES[name](artifact)
