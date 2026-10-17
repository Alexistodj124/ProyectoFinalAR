"""Learned communication between neighboring traffic lights (E6, "comm").

Design (DIAL-style, Foerster et al. 2016, on top of the joint Q learner of qmix.py):

    m_j = tanh(f_msg([o_j, onehot(j)]))                   message of agent j, dim msg_dim (4-8)
    Q_i = f_q([o_i, onehot(i), m_{N(i)_1}, m_{N(i)_2}, ...])   N(i) = corridor neighbors of i

* Neighbors come from env.scenarios.get_topology(net_file) (chain along the corridor).
  Missing neighbor slots (ends of the corridor) receive a zero message.
* Messages are exchanged within the same decision step (all intersections observe
  at the same time and the message is a few floats, e.g. over V2I/fiber).
* End-to-end training: the replay stores raw observations, never messages. At
  training time the messages are RECOMPUTED from the stored o_j with the current
  encoder, so the TD loss of receiver i back-propagates through m_j into the
  sender's encoder (differentiable channel, DIAL). Optional Gaussian noise on the
  channel during training (``msg_noise``) plays the role of DIAL's regularizing unit.
* The learner is the joint Double-Q learner of qmix.py with ``mixer: none`` by
  default (independent TD losses on the team reward = IDQN-like, so E6 compares
  "hand-crafted neighbor queues" (idqn neighbor_obs) vs "learned messages");
  ``mixer: qmix`` gives QMIX + communication.
* Execution stays decentralized: each agent only needs its neighbors' messages.
"""
from __future__ import annotations

import torch
import torch.nn as nn

from agents.marl.common import MultiAgentSpec, mlp
from agents.marl.qmix import DEFAULTS as QMIX_DEFAULTS
from agents.marl.qmix import load_joint_policy, train_joint

DEFAULTS = {
    **QMIX_DEFAULTS,
    "mixer": "none",
    "reward": "team",  # same reward as IDQN / QMIX / MAPPO (local rewards let spillback go unpunished)
    "msg_dim": 6,
    "msg_hidden": 64,
    "msg_noise": 0.0,
}


class CommAgentNet(nn.Module):
    """Shared Q-network whose input includes the neighbors' learned messages."""

    def __init__(self, spec: MultiAgentSpec, h: dict):
        super().__init__()
        n, D, d = spec.n_agents, spec.obs_dim, h["msg_dim"]
        self.msg_dim, self.noise = d, h["msg_noise"]
        self.register_buffer("ids", torch.as_tensor(spec.agent_ids()))
        nbr = torch.as_tensor(spec.neighbor_index())
        self.register_buffer("nbr", torch.where(nbr < 0, torch.full_like(nbr, n), nbr))  # n -> zero message row
        self.encoder = nn.Sequential(nn.Linear(D + n, h["msg_hidden"]), nn.ReLU(), nn.Linear(h["msg_hidden"], d), nn.Tanh())
        self.q = mlp(D + n + spec.max_degree * d, h["hidden"], spec.max_actions)

    def messages(self, x: torch.Tensor) -> torch.Tensor:
        m = self.encoder(x)  # [B, n, d]
        if self.training and self.noise > 0:
            m = m + self.noise * torch.randn_like(m)
        return m

    def forward(self, obs: torch.Tensor) -> torch.Tensor:  # [B, n, D] -> [B, n, A]
        B = obs.shape[0]
        x = torch.cat([obs, self.ids.expand(B, -1, -1)], -1)
        m = self.messages(x)  # recomputed from observations => gradients reach the sender
        m = torch.cat([m, m.new_zeros(B, 1, self.msg_dim)], 1)
        inbox = m[:, self.nbr].flatten(2)  # [B, n, max_degree * d]: messages of N(i)
        return self.q(torch.cat([x, inbox], -1))


def train(cfg: dict) -> str:
    return train_joint(cfg, "comm", DEFAULTS, CommAgentNet)


def load_policy(run_dir: str):
    return load_joint_policy(run_dir, DEFAULTS, CommAgentNet, "comm")
