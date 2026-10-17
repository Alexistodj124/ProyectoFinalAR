"""Common policy interface used by evaluation (experiments/evaluate.py) and the web demo.

A Policy maps the per-agent observation dict of a sumo-rl PettingZoo parallel env
to a per-agent action dict. Single-intersection policies receive a dict with one key.
"""
from __future__ import annotations

from typing import Any

import numpy as np


class Policy:
    name: str = "policy"
    # Baselines that let SUMO run its own program (fixed time / actuated) set this to
    # True and set `program` to "fixed" or "actuated"; evaluate.py then builds the env
    # with fixed_ts=True plus the scenario's matching additional file, and act() is
    # never called.
    fixed_ts: bool = False
    program: str | None = None

    def reset(self, sumo_env: Any) -> None:
        """Called right after env.reset(). `sumo_env` is the sumo_rl.SumoEnvironment
        (gives access to .traffic_signals and the TraCI connection .sumo)."""
        self.sumo_env = sumo_env

    def act(self, obs: dict[str, np.ndarray]) -> dict[str, int]:
        raise NotImplementedError


class RandomPolicy(Policy):
    name = "random"

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)

    def act(self, obs):
        ts = self.sumo_env.traffic_signals
        return {a: int(self.rng.integers(ts[a].action_space.n)) for a in obs}
