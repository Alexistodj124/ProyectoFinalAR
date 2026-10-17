"""Replay buffers: uniform and Prioritized Experience Replay (Schaul et al. 2016)."""
from __future__ import annotations

import numpy as np
import torch


class ReplayBuffer:
    """Circular uniform replay buffer stored in preallocated numpy arrays.

    `done` must be the *terminal* flag only (not time-limit truncation), so the TD
    target keeps bootstrapping at the end of a truncated episode.
    """

    def __init__(self, capacity: int, obs_dim: int, rng: np.random.Generator | None = None):
        self.capacity = int(capacity)
        self.obs = np.zeros((self.capacity, obs_dim), np.float32)
        self.next_obs = np.zeros((self.capacity, obs_dim), np.float32)
        self.actions = np.zeros(self.capacity, np.int64)
        self.rewards = np.zeros(self.capacity, np.float32)
        self.dones = np.zeros(self.capacity, np.float32)
        self.pos = 0
        self.size = 0
        self.rng = rng or np.random.default_rng()

    def __len__(self) -> int:
        return self.size

    def add(self, obs, action, reward, next_obs, done) -> int:
        i = self.pos
        self.obs[i], self.next_obs[i] = obs, next_obs
        self.actions[i], self.rewards[i], self.dones[i] = action, reward, float(done)
        self.pos = (self.pos + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)
        return i

    def _gather(self, idx: np.ndarray, weights: np.ndarray, device) -> dict:
        t = lambda a: torch.as_tensor(a, device=device)  # noqa: E731
        return {
            "obs": t(self.obs[idx]),
            "actions": t(self.actions[idx]),
            "rewards": t(self.rewards[idx]),
            "next_obs": t(self.next_obs[idx]),
            "dones": t(self.dones[idx]),
            "weights": t(weights.astype(np.float32)),
            "idx": idx,
        }

    def sample(self, batch_size: int, device="cpu", beta: float = 1.0) -> dict:
        idx = self.rng.integers(0, self.size, size=batch_size)
        return self._gather(idx, np.ones(batch_size, np.float32), device)

    def update_priorities(self, idx, td_errors) -> None:  # uniform buffer: no-op
        pass


class SumTree:
    """Binary tree whose leaves hold priorities and whose internal nodes hold sums.

    O(log n) update and O(log n) retrieval of the leaf whose cumulative-priority
    interval contains a value `s` in [0, total): sampling proportional to priority.
    """

    def __init__(self, capacity: int):
        self.capacity = int(capacity)
        self.tree = np.zeros(2 * self.capacity, np.float64)  # leaves: [capacity, 2*capacity)

    @property
    def total(self) -> float:
        return float(self.tree[1])

    def __getitem__(self, leaf: int) -> float:
        return float(self.tree[self.capacity + leaf])

    def update(self, leaf: int, priority: float) -> None:
        i = self.capacity + int(leaf)
        delta = priority - self.tree[i]
        while i >= 1:
            self.tree[i] += delta
            i //= 2

    def find(self, s: float) -> int:
        """Return the leaf index whose cumulative interval contains s."""
        i = 1
        while i < self.capacity:
            left = 2 * i
            if s < self.tree[left]:
                i = left
            else:
                s -= self.tree[left]
                i = left + 1
        return i - self.capacity

    def max_leaf(self, n: int) -> float:
        return float(self.tree[self.capacity : self.capacity + n].max()) if n else 0.0


class PrioritizedReplayBuffer(ReplayBuffer):
    """Proportional PER: P(i) = p_i^alpha / sum_k p_k^alpha, p_i = |TD error| + eps.

    Sampling uses stratified segments over the SumTree. The bias this introduces is
    corrected with importance-sampling weights w_i = (N * P(i))^-beta / max_j w_j,
    where beta is annealed from beta0 to 1 by the training loop (`beta` argument).
    """

    def __init__(self, capacity, obs_dim, alpha: float = 0.6, eps: float = 1e-6, rng=None):
        super().__init__(capacity, obs_dim, rng)
        self.alpha, self.eps = alpha, eps
        self.tree = SumTree(self.capacity)
        self.max_priority = 1.0  # new transitions get the max priority so they are seen at least once

    def add(self, obs, action, reward, next_obs, done) -> int:
        i = super().add(obs, action, reward, next_obs, done)
        self.tree.update(i, self.max_priority**self.alpha)
        return i

    def sample(self, batch_size: int, device="cpu", beta: float = 0.4) -> dict:
        total = self.tree.total
        seg = total / batch_size
        s = (np.arange(batch_size) + self.rng.random(batch_size)) * seg
        idx = np.array([self.tree.find(v) for v in s])
        idx = np.minimum(idx, self.size - 1)  # guards float round-off at the right edge
        probs = np.array([self.tree[i] for i in idx]) / total
        weights = (self.size * probs) ** (-beta)
        weights /= weights.max()
        return self._gather(idx, weights, device)

    def update_priorities(self, idx, td_errors) -> None:
        p = np.abs(np.asarray(td_errors, np.float64)) + self.eps
        self.max_priority = max(self.max_priority, float(p.max()))
        for i, pi in zip(idx, p):
            self.tree.update(int(i), float(pi) ** self.alpha)
