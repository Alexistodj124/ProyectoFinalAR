"""Tests for agents/marl: heterogeneity utilities (fast, no SUMO) and short trainings
on toy_grid2x2 (300 s, 2 episodes) with a load_policy roundtrip."""
from __future__ import annotations

import importlib

import numpy as np
import pytest
import torch
from gymnasium import spaces

from agents.marl import common
from agents.marl.common import MultiAgentRunner, MultiAgentSpec, masked_argmax, masked_logits

ALGOS = ["idqn", "qmix", "mappo", "comm"]


# ------------------------------------------------------------- fake hetero env
class FakeHeteroEnv:
    """Parallel env with heterogeneous agents (different #phases and #lanes) using the
    sumo-rl observation layout. Asserts that no invalid action is ever applied and
    drops one agent from the step output from time to time."""

    def __init__(self, phases=(2, 4, 3), lanes=(4, 8, 6), horizon=25, seed=0):
        self.possible_agents = [f"tl{i}" for i in range(len(phases))]
        self.phases = dict(zip(self.possible_agents, phases))
        self.lanes = dict(zip(self.possible_agents, lanes))
        self.horizon, self.rng = horizon, np.random.default_rng(seed)
        self.agents, self.t, self.applied = [], 0, []

    def observation_space(self, a):
        return spaces.Box(0, 1, (self.phases[a] + 1 + 2 * self.lanes[a],), np.float32)

    def action_space(self, a):
        return spaces.Discrete(self.phases[a])

    def _obs(self, a):
        g, l = self.phases[a], self.lanes[a]
        one_hot = np.eye(g, dtype=np.float32)[self.rng.integers(g)]
        return np.concatenate([one_hot, [1.0], self.rng.random(l), self.rng.random(l)]).astype(np.float32)

    def reset(self, seed=None, options=None):
        self.agents, self.t = list(self.possible_agents), 0
        return {a: self._obs(a) for a in self.agents}, {a: {} for a in self.agents}

    def step(self, actions):
        for a, act in actions.items():
            assert 0 <= act < self.phases[a], f"invalid action {act} for {a}"
            self.applied.append((a, act))
        self.t += 1
        done = self.t >= self.horizon
        live = [a for a in self.agents if not (self.t % 7 == 0 and a == "tl1")]  # tl1 missing sometimes
        obs = {a: self._obs(a) for a in live}
        rew = {a: float(-self.rng.random()) for a in live}
        info = {a: {"system_mean_waiting_time": float(self.t)} for a in live}
        term = {a: False for a in live}
        trunc = {a: done for a in live}
        if done:
            self.agents = []
        return obs, rew, term, trunc, info

    def close(self):
        pass


def hetero_spec(env=None):
    env = env or FakeHeteroEnv()
    spec = MultiAgentSpec.from_env(env)
    spec.neighbors = {"tl0": ["tl1"], "tl1": ["tl0", "tl2"], "tl2": ["tl1"]}
    return env, spec


# ------------------------------------------------------------- unit tests
def test_padding_and_masks():
    env, spec = hetero_spec()
    assert spec.structured and spec.max_actions == 4 and spec.max_lanes == 8
    assert spec.obs_dim == 4 + 1 + 16
    obs, _ = env.reset()
    o = obs["tl0"]  # 2 phases, 4 lanes
    p = spec.pad_one(0, o)
    G, L = 4, 8
    np.testing.assert_array_equal(p[:2], o[:2])  # phase one-hot
    assert p[2:G].sum() == 0  # padded phases
    assert p[G] == o[2]  # min-green flag aligned for every agent
    np.testing.assert_array_equal(p[G + 1 : G + 5], o[3:7])  # density
    np.testing.assert_array_equal(p[G + 1 + L : G + 1 + L + 4], o[7:11])  # queue
    np.testing.assert_array_equal(spec.queue_of(0, o)[:4], o[-4:])
    mask = spec.action_mask()
    assert mask.tolist() == [[1, 1, 0, 0], [1, 1, 1, 1], [1, 1, 1, 0]]
    assert spec.global_state(obs).shape == (spec.state_dim(True),)
    nq = spec.neighbor_queues(obs)
    assert nq.shape == (3, spec.max_degree * spec.max_lanes)
    np.testing.assert_array_equal(nq[0, :8], spec.queue_of(1, obs["tl1"]))
    assert spec.neighbor_index().tolist() == [[1, -1], [0, 2], [1, -1]]
    # missing agent -> zeros, spec survives a dict roundtrip
    assert spec.obs_matrix({"tl0": o})[1].sum() == 0
    assert MultiAgentSpec.from_dict(spec.to_dict()) == spec


def test_masked_ops_never_choose_invalid():
    _, spec = hetero_spec()
    mask = torch.as_tensor(spec.action_mask())
    q = torch.full((256, 3, 4), 0.0)
    q[..., 3] = 1e6  # invalid action 3 of tl0/tl2 has the largest value
    q[..., 2] += 1e5
    a = masked_argmax(q, mask.expand_as(q))
    assert (a[:, 0] < 2).all() and (a[:, 2] < 3).all() and (a[:, 1] == 3).all()
    probs = torch.softmax(masked_logits(q, mask.expand_as(q)), -1)
    assert probs[..., 0, 2:].max() < 1e-12 and probs[..., 2, 3].max() < 1e-12
    rng = np.random.default_rng(0)
    for _ in range(200):
        acts = common.epsilon_greedy(np.random.randn(3, 4), spec.action_mask(), 1.0, rng)
        assert acts[0] < 2 and acts[2] < 3


def test_runner_handles_missing_agents():
    env, spec = hetero_spec()
    runner = MultiAgentRunner(env, spec)
    obs = runner.reset(seed=0)
    steps, done = 0, False
    while not done:
        obs, rew, term, done, info = runner.step({a: 0 for a in spec.agents})
        assert set(obs) == set(spec.agents) and rew.shape == (3,) and not term
        steps += 1
    assert steps == env.horizon and "system_mean_waiting_time" in info


def test_reward_scaler():
    assert common.RewardScaler(0.01)(np.array([100.0]))[0] == pytest.approx(1.0)
    rs = common.RewardScaler(1.0, normalize=True)
    out = [rs(np.array([1000.0 * np.sin(i)])) for i in range(200)]
    assert np.abs(out[-1]).max() < 1000.0


@pytest.mark.parametrize("algo", ALGOS)
def test_train_on_fake_heterogeneous_env(algo, tmp_path, monkeypatch):
    """Full train() + load_policy() on heterogeneous agents (no SUMO): actions are always valid."""
    mod = importlib.import_module(f"agents.marl.{algo}")
    env, spec = hetero_spec()
    learner = importlib.import_module("agents.marl.qmix") if algo == "comm" else mod  # comm reuses qmix.train_joint
    monkeypatch.setattr(learner, "make_env_and_spec", lambda cfg, seed: (env, spec))
    hparams = {"learning_starts": 10, "batch_size": 8, "n_steps": 10, "device": "cpu", "hidden": [16], "critic_hidden": [16]}
    if algo == "idqn":
        hparams["neighbor_obs"] = True
    cfg = dict(exp="test", algo=algo, scenario="toy_grid2x2", seed=0, total_episodes=2, num_seconds=125,
               run_dir=str(tmp_path / algo), hparams=hparams)
    run_dir = mod.train(cfg)
    assert len(env.applied) == 2 * env.horizon * 3  # every live agent acted every step (all valid)
    pol = mod.load_policy(run_dir)
    for _ in range(20):
        obs, _ = env.reset()
        acts = pol.act(obs)
        assert set(acts) == set(obs)
        assert all(0 <= acts[a] < env.phases[a] for a in acts)
    del obs["tl2"]  # policies must cope with a missing agent
    assert set(pol.act(obs)) == {"tl0", "tl1"}
