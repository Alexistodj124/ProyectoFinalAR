"""Tabular agents: discretizer, Q-Learning and Dyna-Q on toy_single (short runs)."""
import os

os.environ.setdefault("LIBSUMO_AS_TRACI", "1")

import numpy as np
import pandas as pd
import pytest

from agents.tabular.discretize import Discretizer, lane_groups_by_edge
from agents.tabular.dyna_q import greedy_policy, value_iteration_on_model
from agents.tabular.common import epsilon_at, DEFAULT_HP


def test_lane_groups_and_state_count():
    lanes = [f"{e}_{k}" for e in ("n", "s", "e", "w") for k in range(2)]
    d = Discretizer(4, lane_groups_by_edge(lanes))
    assert d.n_approaches == 4 and d.n_lanes == 8
    assert d.n_states_total == 4 * 2 * 3**4  # 648 as in the plan


def test_encode_levels_and_heterogeneous():
    d = Discretizer(2, [[0, 1], [2]])  # 2 phases, 3 lanes, 2 approaches
    obs = np.concatenate([[0, 1], [1], np.zeros(3), [0.0, 0.2, 0.9]])
    assert d.encode(obs) == (1, 1, 0, 2)  # approach 1: mean(0, .2)=.1 baja; approach 2: .9 alta
    d3 = Discretizer(3, [[0], [1], [2]], agg="max")
    assert d3.n_states_total == 3 * 2 * 27


def test_epsilon_schedule():
    hp = dict(DEFAULT_HP)
    assert epsilon_at(0, 100, hp) == 1.0
    assert abs(epsilon_at(100, 100, hp) - hp["eps_end"]) < 1e-9
    hp["eps_schedule"] = "exp"
    assert epsilon_at(35, 100, hp) < 1.0


def test_value_iteration_simple_chain():
    # state 0: action 1 gives +1 and stays, action 0 gives 0 -> greedy must pick 1
    model = {(0, 0): [(0.0, 0, False)], (0, 1): [(1.0, 0, False)]}
    q = value_iteration_on_model(model, 0.9, 2)
    assert int(np.argmax(q[(0,)] if (0,) in q else q[0])) == 1
    assert abs(q[0][1] - 10.0) < 1e-2


def _cfg(tmp_path, algo, **hp):
    return dict(exp="t", algo=algo, name=algo, scenario="toy_single", seed=0, total_episodes=2,
                num_seconds=300, run_dir=str(tmp_path / algo), save_every=1, hparams=hp)


@pytest.mark.parametrize("algo", ["qlearning", "dyna_q"])
def test_train_and_roundtrip(tmp_path, algo):
    from agents.registry import get_module, load_policy
    from env.reforma_env import get_sumo_env, make_parallel_env

    cfg = _cfg(tmp_path, algo, **({"n_planning": 5} if algo == "dyna_q" else {}))
    run_dir = get_module(algo).train(cfg)
    log = pd.read_csv(os.path.join(run_dir, "train_log.csv"))
    assert len(log) == 2
    for col in ["episode", "env_steps", "return", "mean_waiting_time", "epsilon", "n_states"]:
        assert col in log.columns
    assert log.env_steps.iloc[-1] == 2 * 300 // 5 and log.n_states.iloc[-1] > 0
    assert os.path.exists(os.path.join(run_dir, "qtable.npz"))
    assert os.path.exists(os.path.join(run_dir, "config.yaml"))

    pol = load_policy(algo, run_dir)
    env = make_parallel_env("toy_single", 1, num_seconds=120)
    obs, _ = env.reset(seed=1)
    pol.reset(get_sumo_env(env))
    n = get_sumo_env(env).traffic_signals["t"].num_green_phases
    done = False
    while not done:
        act = pol.act(obs)
        assert set(act) == {"t"} and 0 <= act["t"] < n
        obs, _, term, trunc, _ = env.step(act)
        done = all(trunc.values()) or not env.agents
    env.close()
    if algo == "dyna_q":
        from agents.tabular.dyna_q import load_policy as lp

        assert lp(run_dir, "vi") is not None and lp(run_dir, "vi").q
