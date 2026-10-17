"""Dyna-Q: Q-Learning + a learned model used for n planning updates per real step.

Also `value_iteration_on_model`: dynamic programming (value iteration) on the empirical model,
as the model-based contrast to the sample-based updates.
"""
from __future__ import annotations

import pickle
from collections import deque
from pathlib import Path

import numpy as np

from agents.tabular.common import TabularPolicy, load_qtable, policy_from_npz, save_qtable, train_loop
from agents.tabular.q_learning import QLearningAgent


class DynaQAgent(QLearningAgent):
    def __init__(self, hp, n_actions, rng):
        super().__init__(hp, n_actions, rng)
        self.n_planning = int(hp.get("n_planning", 10))
        self.max_outcomes = int(hp.get("model_max_outcomes", 20))
        # model[(s, a)] = recent observed outcomes (r, s', terminated); sampled uniformly.
        self.model: dict[tuple, deque] = {}
        self.visited: list[tuple] = []  # (s, a) pairs seen so far, for O(1) uniform sampling

    def learn(self, s, a, r, s2, terminated):
        self.update(s, a, r, s2, terminated)  # (d) direct RL
        key = (s, a)
        if key not in self.model:
            self.model[key] = deque(maxlen=self.max_outcomes)
            self.visited.append(key)
        self.model[key].append((r, s2, terminated))  # (e) model learning
        for _ in range(self.n_planning):  # (f) planning with simulated experience
            ps, pa = self.visited[self.rng.integers(len(self.visited))]
            outcomes = self.model[(ps, pa)]
            pr, ps2, pterm = outcomes[self.rng.integers(len(outcomes))]
            self.update(ps, pa, pr, ps2, pterm)

    def info(self):
        return {"model_size": len(self.visited)}

    def save(self, run_dir, hp):
        super().save(run_dir, hp)
        with (Path(run_dir) / "model.pkl").open("wb") as f:
            pickle.dump({k: list(v) for k, v in self.model.items()}, f)
        if hp.get("vi_eval", True):
            q_vi = value_iteration_on_model(self.model, hp["gamma"], self.n_actions)
            save_qtable(q_vi, Path(run_dir) / "qtable_vi.npz", hp["thresholds"], hp["agg"])


def value_iteration_on_model(model, gamma: float, n_actions: int, theta: float = 1e-4, max_iters: int = 500):
    """Value iteration on the empirical model {(s, a): [(r, s', terminated), ...]}.

    Bellman optimality backup: Q(s,a) = E[r] + gamma * E[max_a' Q(s',a')] with the empirical
    distribution of outcomes. Actions never tried in a state stay at -inf (unknown); next states
    never visited as a source state take the mean value of the known ones. Returns the Q-table
    (greedy policy = argmax per state), wrap it with TabularPolicy or use `greedy_policy`.
    """
    states = sorted({s for s, _ in model})
    idx = {s: i for i, s in enumerate(states)}
    trans = {k: [(r, idx.get(s2), t) for r, s2, t in v] for k, v in model.items()}
    q = np.full((len(states), n_actions), -np.inf)
    v = np.zeros(len(states))
    for _ in range(max_iters):
        v_unknown = v.mean() if len(v) else 0.0
        delta = 0.0
        for (s, a), outs in trans.items():
            i = idx[s]
            tot = sum(r + (0.0 if t else gamma * (v[j] if j is not None else v_unknown)) for r, j, t in outs)
            q[i, a] = tot / len(outs)
        v_new = q.max(axis=1)
        delta = float(np.abs(v_new - v).max()) if len(v) else 0.0
        v = v_new
        if delta < theta:
            break
    return {s: q[i].copy() for s, i in idx.items()}


def greedy_policy(q_vi: dict, thresholds, agg: str = "mean") -> TabularPolicy:
    """Greedy policy of a Q-table; -inf (untried) actions are never chosen when others exist."""
    return TabularPolicy(q_vi, thresholds, agg, name="dyna_q_vi")


def vi_policy_from_run(run_dir, gamma: float | None = None) -> TabularPolicy:
    """Re-run value iteration on the saved model of `run_dir` and return its greedy policy."""
    import yaml

    run_dir = Path(run_dir)
    hp = (yaml.safe_load((run_dir / "config.yaml").read_text()).get("hparams") or {})
    _, thr, agg = load_qtable(run_dir / "qtable.npz")
    model = pickle.loads((run_dir / "model.pkl").read_bytes())
    q0, _, _ = load_qtable(run_dir / "qtable.npz")
    n_actions = len(next(iter(q0.values())))
    q_vi = value_iteration_on_model(model, gamma if gamma is not None else hp.get("gamma", 0.99), n_actions)
    return greedy_policy(q_vi, thr, agg)


def train(cfg: dict) -> str:
    return train_loop(cfg, DynaQAgent, "dyna_q")


def load_policy(run_dir: str, which: str = "q") -> TabularPolicy:
    """which="q": greedy on the Dyna-Q table; which="vi": greedy on value iteration over the model."""
    f = "qtable_vi.npz" if which == "vi" else "qtable.npz"
    return policy_from_npz(Path(run_dir) / f, "dyna_q_vi" if which == "vi" else "dyna_q")
