"""Algorithm registry. Every branch implements its module; nobody edits this table.

Each learning module exposes:
    train(cfg: dict) -> str            # returns run_dir (see docs/ARCHITECTURE.md)
    load_policy(run_dir: str) -> Policy
Each baseline module exposes:
    make_policy(cfg: dict | None = None) -> Policy
"""
from __future__ import annotations

import importlib

ALGOS = {
    # baselines (no learning)
    "fixed": "baselines.fixed_time",
    "actuated": "baselines.actuated",
    "max_pressure": "baselines.max_pressure",
    # single agent (cruce_* scenarios)
    "qlearning": "agents.tabular.q_learning",
    "dyna_q": "agents.tabular.dyna_q",
    "dqn": "agents.dqn.dqn",  # flags: double, dueling, per
    "ppo": "agents.ppo.ppo",
    # multi agent (reforma_* scenarios)
    "idqn": "agents.marl.idqn",  # flag: neighbor_obs (communication v1)
    "qmix": "agents.marl.qmix",
    "mappo": "agents.marl.mappo",
    "comm": "agents.marl.comm",  # learned messages between neighbors
}
BASELINES = {"fixed", "actuated", "max_pressure"}


def get_module(algo: str):
    return importlib.import_module(ALGOS[algo])


def train(cfg: dict) -> str:
    return get_module(cfg["algo"]).train(cfg)


def load_policy(algo: str, run_dir: str | None = None, cfg: dict | None = None):
    mod = get_module(algo)
    if algo in BASELINES:
        return mod.make_policy(cfg)
    return mod.load_policy(run_dir)
