"""FUD-Ada selection and feedback adapted from NetAdapt-IoT (see SOURCE.md)."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Flow:
    kind: str
    weight: int
    tau: int
    deadline: int | None
    service: int


@dataclass
class Feedback:
    last: int = 0
    prob: float = 0.8
    debt: float = 0.0


def choose(t, heads, states, *, delay=0, tokens=math.inf):
    """Select an eligible head by the upstream FUD-Ada score and tie breaks."""
    eligible = [p for p in heads if p.spec.service <= tokens + 1e-9]
    if not eligible:
        return None

    def score(p):
        f = p.spec
        state = states[p.flow]
        s = f.service
        age = t - state.last
        wait = t - p.generated
        lag = s + delay
        if f.kind == "event":
            slack = p.generated + (f.deadline or f.tau) - (t + lag)
            fresh_term = 0.0
            urg_term = f.weight * (1.0 + wait / f.tau) * (
                1.0 + 1.0 / (1.0 + max(0, slack))
            )
        else:
            raw_gain = max(0.0, (age + lag) ** 2 - (wait + lag) ** 2) / (2.0 * f.tau ** 2)
            fresh_term = f.weight * math.sqrt(raw_gain)
            urg_term = 0.0
        debt_term = 2.5 * f.weight * math.log1p(state.debt)
        return state.prob * (fresh_term + urg_term + debt_term) / s

    return max(eligible, key=lambda p: (score(p), -p.generated, -p.flow))


def update(heads, selected, states, arrival, delivered):
    """Advance backlogged service debt and consume one observed link outcome."""
    total_weight = sum(p.spec.weight for p in heads)
    elapsed = selected.spec.service
    state = states[selected.flow]
    state.prob = 0.9 * state.prob + 0.1 * int(delivered)
    credit = 0
    if delivered:
        spec = selected.spec
        fresh = selected.generated > state.last
        timely = spec.deadline is None or arrival <= selected.generated + spec.deadline
        state.last = max(state.last, selected.generated)
        credit = int(timely and (spec.kind == "event" or fresh))

    for p in heads:
        state = states[p.flow]
        target = 0.5 * 0.8 * p.spec.weight / (total_weight * p.spec.service)
        # Intermediate busy slots have no service credit, the last slot may have one.
        carried = min(50.0, state.debt + (elapsed - 1) * target)
        served = credit if p.flow == selected.flow else 0
        state.debt = min(50.0, max(0.0, carried + target - served))
