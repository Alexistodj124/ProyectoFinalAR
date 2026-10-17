"""PPO (Stable-Baselines3) trains a few steps on toy_single and round-trips load_policy."""
import csv

import pytest

from agents.base import Policy
from agents.ppo.ppo import load_policy, train
from env.reforma_env import make_gym_env


@pytest.mark.slow
def test_ppo_trains_and_loads(tmp_path):
    cfg = dict(
        exp="test",
        algo="ppo",
        name="ppo_test",
        scenario="toy_single",
        seed=0,
        total_episodes=3,
        num_seconds=300,
        run_dir=str(tmp_path / "run"),
        hparams=dict(n_steps=60, batch_size=30, n_epochs=2),
    )
    run_dir = train(cfg)
    rows = list(csv.DictReader(open(f"{run_dir}/train_log.csv")))
    assert len(rows) == 3
    assert {"episode", "env_steps", "return", "mean_waiting_time"} <= set(rows[0])
    assert int(rows[-1]["env_steps"]) == 3 * 60
    assert (tmp_path / "run" / "model.zip").exists()

    pol = load_policy(run_dir)
    assert isinstance(pol, Policy) and pol.name == "ppo_test"
    env = make_gym_env("toy_single", seed=1, num_seconds=60)
    obs, _ = env.reset(seed=1)
    pol.reset(env.sumo_env)
    a = pol.act({env.agent: obs})
    assert env.action_space.contains(a[env.agent])
    env.close()
