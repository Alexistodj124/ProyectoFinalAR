"""Short MARL trainings on toy_grid2x2 (SUMO, 300 s x 2 episodes) + load_policy roundtrip.

Uses regular TraCI (not libsumo) so it can share the pytest process with other tests.
"""
from __future__ import annotations

import csv
import importlib

import numpy as np
import pytest

from env.reforma_env import get_sumo_env, make_parallel_env

CASES = [
    ("idqn", {}),
    ("idqn", {"neighbor_obs": True, "shared_params": True}),
    ("qmix", {}),
    ("mappo", {}),
    ("comm", {"msg_dim": 4}),
]


@pytest.mark.parametrize("algo,extra", CASES, ids=[f"{a}-{i}" for i, (a, _) in enumerate(CASES)])
def test_toy_grid_train_and_roundtrip(algo, extra, tmp_path):
    mod = importlib.import_module(f"agents.marl.{algo}")
    hparams = {"learning_starts": 30, "batch_size": 16, "device": "cpu", "hidden": [32], **extra}
    cfg = dict(exp="test", algo=algo, scenario="toy_grid2x2", seed=0, total_episodes=2, num_seconds=300,
               run_dir=str(tmp_path / algo), hparams=hparams)
    run_dir = mod.train(cfg)

    rows = list(csv.DictReader(open(f"{run_dir}/train_log.csv")))
    assert [int(r["episode"]) for r in rows] == [0, 1]
    assert int(rows[-1]["env_steps"]) == 2 * 300 // 5
    for k in ("return", "mean_waiting_time", "loss", "wall_time"):
        assert np.isfinite(float(rows[-1][k])), k
    assert ("entropy" if algo == "mappo" else "epsilon") in rows[0]

    pol = mod.load_policy(run_dir)
    penv = make_parallel_env("toy_grid2x2", seed=1000, num_seconds=60)
    obs, _ = penv.reset(seed=1000)
    se = get_sumo_env(penv)
    pol.reset(se)
    while penv.agents:
        acts = pol.act(obs)
        assert set(acts) == set(obs)
        assert all(0 <= acts[a] < se.traffic_signals[a].action_space.n for a in acts)
        obs, *_ = penv.step(acts)
    penv.close()
