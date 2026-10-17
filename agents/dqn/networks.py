"""Q-networks for the DQN family (PLAN §4 "Deep RL I")."""
from __future__ import annotations

import torch
import torch.nn as nn


def _mlp(in_dim: int, hidden: int, n_layers: int = 2) -> nn.Sequential:
    layers: list[nn.Module] = []
    d = in_dim
    for _ in range(n_layers):
        layers += [nn.Linear(d, hidden), nn.ReLU()]
        d = hidden
    return nn.Sequential(*layers)


class QNetwork(nn.Module):
    """Plain MLP (2 x hidden) that outputs Q(s, .) for every discrete action."""

    def __init__(self, obs_dim: int, n_actions: int, hidden: int = 64):
        super().__init__()
        self.body = _mlp(obs_dim, hidden)
        self.q = nn.Linear(hidden, n_actions)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.q(self.body(x))


class DuelingQNetwork(nn.Module):
    """Dueling architecture (Wang et al. 2016): shared body, then two streams.

        Q(s,a) = V(s) + A(s,a) - mean_a' A(s,a')

    Subtracting the mean advantage makes the V/A decomposition identifiable.
    """

    def __init__(self, obs_dim: int, n_actions: int, hidden: int = 64):
        super().__init__()
        self.body = _mlp(obs_dim, hidden)
        self.value = nn.Linear(hidden, 1)
        self.advantage = nn.Linear(hidden, n_actions)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.body(x)
        v, a = self.value(h), self.advantage(h)
        return v + a - a.mean(dim=1, keepdim=True)


def make_q_network(obs_dim: int, n_actions: int, hidden: int = 64, dueling: bool = False) -> nn.Module:
    cls = DuelingQNetwork if dueling else QNetwork
    return cls(obs_dim, n_actions, hidden)
