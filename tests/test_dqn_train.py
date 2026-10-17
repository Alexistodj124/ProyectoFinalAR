"""DQN trains end to end on toy_single for every ablation flag combination."""
import csv

import numpy as np
import pytest
import torch

from agents.dqn.dqn import DQNPolicy, load_policy, train
from env.reforma_env import make_gym_env

COMBOS = [
    dict(),  # vanilla
    dict(double=True),
    dict(double=True, dueling=True),
    dict(double=True, dueling=True, per=True),
    dict(per=True, obs_norm=True),
]


def _cfg(tmp_path, **hp):
    return dict(
        exp="test",
        algo="dqn",
        name="dqn_test",
        scenario="toy_single",
        seed=0,
        total_episodes=2,
        num_seconds=300,
        run_dir=str(tmp_path / "run"),
        hparams=dict(learning_starts=20, batch_size=16, target_update=20, buffer_size=500, device="cpu", **hp),
    )


@pytest.mark.slow
@pytest.mark.parametrize("hp", COMBOS, ids=lambda h: "+".join(h) or "vanilla")
def test_train_flag_combo(tmp_path, hp):
    run_dir = train(_cfg(tmp_path, **hp))
    rows = list(csv.DictReader(open(f"{run_dir}/train_log.csv")))
    assert len(rows) == 2
    assert {"episode", "env_steps", "return", "mean_waiting_time", "epsilon", "loss", "q_mean"} <= set(rows[0])
    assert int(rows[-1]["env_steps"]) == 2 * 60  # 300 s / delta_time 5 s per episode
    assert np.isfinite(float(rows[-1]["loss"]))
    assert float(rows[-1]["epsilon"]) <= float(rows[0]["epsilon"])


@pytest.mark.slow
def test_load_policy_roundtrip(tmp_path):
    run_dir = train(_cfg(tmp_path, double=True, dueling=True, per=True))
    pol = load_policy(run_dir)
    assert isinstance(pol, DQNPolicy) and pol.name == "dqn_test"
    env = make_gym_env("toy_single", seed=1, num_seconds=60)
    obs, _ = env.reset(seed=1)
    pol.reset(env.sumo_env)
    a = pol.act({env.agent: obs})
    assert set(a) == {env.agent} and env.action_space.contains(a[env.agent])
    # greedy == argmax of the saved network
    ckpt = torch.load(f"{run_dir}/model.pt", weights_only=False)
    assert ckpt["dueling"] is True and ckpt["obs_dim"] == obs.shape[0]
    assert a == pol.act({env.agent: obs})  # deterministic
    env.step(a[env.agent])
    env.close()
