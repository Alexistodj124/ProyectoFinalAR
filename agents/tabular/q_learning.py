"""Tabular Q-Learning (off-policy TD control) on the discretized intersection state."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from agents.tabular.common import policy_from_npz, save_qtable, train_loop


class QLearningAgent:
    def __init__(self, hp: dict, n_actions: int, rng: np.random.Generator):
        self.hp, self.n_actions, self.rng = hp, n_actions, rng
        self.q: dict[tuple, np.ndarray] = {}

    def values(self, s) -> np.ndarray:
        if s not in self.q:
            self.q[s] = np.full(self.n_actions, self.hp["q_init"], dtype=np.float64)
        return self.q[s]

    def act(self, s, eps: float) -> int:
        """Epsilon-greedy (same rule as in the bandits topic; ties broken at random)."""
        if self.rng.random() < eps:
            return int(self.rng.integers(self.n_actions))
        q = self.values(s)
        return int(self.rng.choice(np.flatnonzero(q == q.max())))

    def update(self, s, a, r, s2, terminated: bool) -> None:
        # TD target: r + gamma * max_a' Q(s', a'); Q(s,a) += alpha * (target - Q(s,a))
        target = r + (0.0 if terminated else self.hp["gamma"] * self.values(s2).max())
        q = self.values(s)
        q[a] += self.hp["alpha"] * (target - q[a])

    def learn(self, s, a, r, s2, terminated: bool) -> None:
        self.update(s, a, r, s2, terminated)

    def info(self) -> dict:
        return {}

    def save(self, run_dir, hp) -> None:
        save_qtable(self.q, Path(run_dir) / "qtable.npz", hp["thresholds"], hp["agg"])


def train(cfg: dict) -> str:
    return train_loop(cfg, QLearningAgent, "qlearning")


def load_policy(run_dir: str):
    return policy_from_npz(Path(run_dir) / "qtable.npz", "qlearning")
