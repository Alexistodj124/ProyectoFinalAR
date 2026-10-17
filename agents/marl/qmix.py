"""QMIX (Rashid et al., 2018), CleanRL style, for heterogeneous traffic lights.

Centralized Training with Decentralized Execution (CTDE, MARL II):

* Every agent i has a utility Q_i(o_i, a_i) computed by ONE shared network fed
  with the padded obs + agent-id one-hot (actions beyond the agent's phases masked).
* A mixing network combines them into Q_tot(s, a) conditioned on the global
  state s (padded obs of the whole corridor + queue totals) through hypernetworks.
* Monotonic factorization: dQ_tot / dQ_i >= 0 for every i (mixing weights pass
  through abs(), ELU is increasing). Hence
      argmax_a Q_tot(s, a) = (argmax_{a_1} Q_1, ..., argmax_{a_n} Q_n),
  so each intersection acts greedily on its own Q_i at execution time (IGM), while
  training uses the team reward r = sum_i r_i and the true joint value.
* TD target with Double-Q and masks (replay of joint transitions):
      a*_i = argmax_{a valid} Q_i(o'_i, a; theta)
      y    = r + gamma * (1 - terminated) * Q_tot(s', Q_i^-(o'_i, a*_i); theta^-)
      L    = (Q_tot(s, Q_i(o_i, a_i)) - y)^2

``train_joint`` is reused by agents/marl/comm.py with another agent network and
``mixer`` in {"qmix", "vdn", "none"} (none = independent per-agent TD losses).
The recurrent (GRU) agent of the paper is not used: sumo-rl's observation already
contains the min-green flag and current phase, and the MLP keeps the replay
transition-based (simpler and faster on Colab).
"""
from __future__ import annotations

import time
from typing import Callable

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from agents.marl.common import (
    EpisodeStats,
    MARLPolicy,
    MultiAgentRunner,
    MultiAgentSpec,
    RewardScaler,
    epsilon_greedy,
    get_device,
    hp,
    libsumo_hint,
    linear_schedule,
    load_checkpoint,
    make_env_and_spec,
    masked_argmax,
    mlp,
    save_checkpoint,
)
from env.scenarios import get_scenario
from experiments.common import TrainLogger, episode_seed, resolve_run_dir, save_config, set_seed

DEFAULTS = dict(
    lr=5e-4,
    gamma=0.99,
    hidden=[128, 128],
    mixer="qmix",  # qmix | vdn | none
    mixing_embed=32,
    hyper_hidden=64,
    state_queues=True,  # append total queue per intersection to the global state
    buffer_size=50_000,  # joint transitions
    batch_size=64,
    learning_starts=1_000,
    train_freq=1,
    target_update_interval=500,  # hard update every N env steps (when tau == 1)
    tau=1.0,  # < 1 => soft (Polyak) update every training step
    eps_start=1.0,
    eps_end=0.05,
    eps_fraction=0.3,
    grad_clip=10.0,
    reward="team",  # only used by mixer=none: local | team
    reward_scale=0.1,
    reward_norm=False,
    device="auto",
    save_every=10,
)


# ------------------------------------------------------------------ networks
class AgentMLP(nn.Module):
    """Shared agent utility network: Q_i = f([padded o_i, onehot(i)]) -> [max_actions]."""

    def __init__(self, spec: MultiAgentSpec, h: dict):
        super().__init__()
        self.register_buffer("ids", torch.as_tensor(spec.agent_ids()))
        self.net = mlp(spec.obs_dim + spec.n_agents, h["hidden"], spec.max_actions)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:  # obs [B, n, D] -> [B, n, A]
        ids = self.ids.expand(obs.shape[0], -1, -1)
        return self.net(torch.cat([obs, ids], -1))


class QMixer(nn.Module):
    """Monotonic mixing network with hypernetworks conditioned on the global state."""

    def __init__(self, n_agents: int, state_dim: int, embed: int = 32, hyper_hidden: int = 64):
        super().__init__()
        self.n, self.embed = n_agents, embed
        self.hyper_w1 = nn.Sequential(nn.Linear(state_dim, hyper_hidden), nn.ReLU(), nn.Linear(hyper_hidden, n_agents * embed))
        self.hyper_b1 = nn.Linear(state_dim, embed)
        self.hyper_w2 = nn.Sequential(nn.Linear(state_dim, hyper_hidden), nn.ReLU(), nn.Linear(hyper_hidden, embed))
        self.V = nn.Sequential(nn.Linear(state_dim, embed), nn.ReLU(), nn.Linear(embed, 1))  # state bias

    def forward(self, q: torch.Tensor, s: torch.Tensor) -> torch.Tensor:  # q [B, n], s [B, S] -> [B]
        B = q.shape[0]
        w1 = torch.abs(self.hyper_w1(s)).view(B, self.n, self.embed)  # abs => w >= 0 => monotonic in Q_i
        b1 = self.hyper_b1(s).view(B, 1, self.embed)  # biases may be negative (no effect on monotonicity)
        hidden = F.elu(torch.bmm(q.view(B, 1, self.n), w1) + b1)  # ELU is increasing
        w2 = torch.abs(self.hyper_w2(s)).view(B, self.embed, 1)
        return (torch.bmm(hidden, w2) + self.V(s).view(B, 1, 1)).view(B)


class VDNMixer(nn.Module):
    """Q_tot = sum_i Q_i (Sunehag et al. 2018): the simplest monotonic mixer."""

    def forward(self, q: torch.Tensor, s: torch.Tensor) -> torch.Tensor:
        return q.sum(-1)


def build_mixer(spec: MultiAgentSpec, h: dict) -> nn.Module | None:
    if h["mixer"] == "qmix":
        return QMixer(spec.n_agents, spec.state_dim(h["state_queues"]), h["mixing_embed"], h["hyper_hidden"])
    if h["mixer"] == "vdn":
        return VDNMixer()
    return None


# ------------------------------------------------------------------ replay
class JointReplay:
    """Replay of joint transitions (o, s, a, r, o', s', terminated) for all agents."""

    def __init__(self, cap: int, n: int, obs_dim: int, state_dim: int, rng: np.random.Generator):
        self.cap, self.rng, self.size, self.i = cap, rng, 0, 0
        self.o = np.zeros((cap, n, obs_dim), np.float32)
        self.o2 = np.zeros_like(self.o)
        self.s = np.zeros((cap, state_dim), np.float32)
        self.s2 = np.zeros_like(self.s)
        self.a = np.zeros((cap, n), np.int64)
        self.r = np.zeros((cap, n), np.float32)  # per-agent (scaled) rewards; team = sum
        self.d = np.zeros(cap, np.float32)

    def add(self, o, s, a, r, o2, s2, d):
        j = self.i
        self.o[j], self.s[j], self.a[j], self.r[j], self.o2[j], self.s2[j], self.d[j] = o, s, a, r, o2, s2, d
        self.i = (self.i + 1) % self.cap
        self.size = min(self.size + 1, self.cap)

    def sample(self, k: int, device):
        idx = self.rng.integers(0, self.size, size=k)
        return [torch.as_tensor(x[idx], device=device) for x in (self.o, self.s, self.a, self.r, self.o2, self.s2, self.d)]


# ------------------------------------------------------------------ training
def train_joint(cfg: dict, algo: str, defaults: dict, make_agent: Callable[[MultiAgentSpec, dict], nn.Module]) -> str:
    h = hp(cfg, defaults)
    seed = int(cfg.get("seed", 0))
    run_dir = resolve_run_dir(cfg)
    save_config(cfg, run_dir)
    set_seed(seed)
    libsumo_hint()
    device = get_device(h["device"])
    rng = np.random.default_rng(seed)

    penv, spec = make_env_and_spec(cfg, seed)
    runner = MultiAgentRunner(penv, spec)
    sc = get_scenario(cfg["scenario"])
    total_steps = int(cfg["total_episodes"]) * int((cfg.get("num_seconds") or sc.num_seconds) // sc.delta_time)

    agent, agent_tgt = make_agent(spec, h).to(device), make_agent(spec, h).to(device)
    agent_tgt.load_state_dict(agent.state_dict())
    agent_tgt.eval()  # no channel noise in the target network (comm)
    mixer, mixer_tgt = build_mixer(spec, h), build_mixer(spec, h)
    params = list(agent.parameters())
    if mixer is not None:
        mixer, mixer_tgt = mixer.to(device), mixer_tgt.to(device)
        mixer_tgt.load_state_dict(mixer.state_dict())
        params += list(mixer.parameters())
    opt = torch.optim.Adam(params, lr=h["lr"])
    online = [m for m in (agent, mixer) if m is not None]
    target = [m for m in (agent_tgt, mixer_tgt) if m is not None]

    sdim = spec.state_dim(h["state_queues"])
    replay = JointReplay(h["buffer_size"], spec.n_agents, spec.obs_dim, sdim, rng)
    mask_np = spec.action_mask()
    mask = torch.as_tensor(mask_np, device=device)
    scaler = RewardScaler(h["reward_scale"], h["reward_norm"], h["gamma"])
    use_team = mixer is not None or h["reward"] == "team"

    def update() -> float:
        o, s, a, r, o2, s2, d = replay.sample(h["batch_size"], device)
        q_taken = agent(o).gather(-1, a[..., None]).squeeze(-1)  # Q_i(o_i, a_i): [B, n]
        with torch.no_grad():
            m = mask.expand(o2.shape[0], -1, -1)
            a_star = masked_argmax(agent(o2), m)  # Double-Q: online selects valid a*
            q_next = agent_tgt(o2).gather(-1, a_star[..., None]).squeeze(-1)  # target evaluates
        if mixer is not None:
            q_tot = mixer(q_taken, s)
            with torch.no_grad():
                y = r.sum(-1) + h["gamma"] * (1.0 - d) * mixer_tgt(q_next, s2)  # team TD target
            loss = F.mse_loss(q_tot, y)
        else:  # independent TD losses (still a joint batch, so comm gradients flow)
            rr = r.sum(-1, keepdim=True).expand_as(r) if use_team else r
            y = rr + h["gamma"] * (1.0 - d[:, None]) * q_next
            loss = F.mse_loss(q_taken, y)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, h["grad_clip"])
        opt.step()
        if h["tau"] < 1.0:
            with torch.no_grad():
                for net, tgt in zip(online, target):
                    for p, tp in zip(net.parameters(), tgt.parameters()):
                        tp.lerp_(p, h["tau"])
        return loss.item()

    logger = TrainLogger(run_dir)
    global_step = 0
    for ep in range(int(cfg["total_episodes"])):
        t0 = time.time()
        obs = runner.reset(seed=episode_seed(seed, ep))
        scaler.reset_episode()
        o, s = spec.obs_matrix(obs), spec.global_state(obs, h["state_queues"])
        stats, losses, done = EpisodeStats(), [], False
        while not done:
            eps = linear_schedule(h["eps_start"], h["eps_end"], int(h["eps_fraction"] * total_steps), global_step)
            with torch.no_grad():
                q = agent(torch.as_tensor(o, device=device)[None])[0].cpu().numpy()
            acts = epsilon_greedy(q, mask_np, eps, rng)  # decentralized execution: each agent argmax Q_i
            obs2, rew, term, done, info = runner.step({ag: acts[i] for i, ag in enumerate(spec.agents)})
            stats.add(rew, info)
            o2, s2 = spec.obs_matrix(obs2), spec.global_state(obs2, h["state_queues"])
            replay.add(o, s, acts, scaler(rew), o2, s2, float(term))
            o, s = o2, s2
            global_step += 1
            if global_step > h["learning_starts"] and global_step % h["train_freq"] == 0:
                losses.append(update())
            if h["tau"] >= 1.0 and global_step % h["target_update_interval"] == 0:
                for net, tgt in zip(online, target):
                    tgt.load_state_dict(net.state_dict())

        logger.log_episode(
            episode=ep,
            env_steps=global_step,
            **{"return": round(stats.ret, 4)},
            mean_waiting_time=round(stats.mean_waiting_time, 4),
            epsilon=round(eps, 4),
            loss=round(float(np.mean(losses)), 6) if losses else float("nan"),
            episode_time=round(time.time() - t0, 2),
        )
        if (ep + 1) % h["save_every"] == 0:
            save_checkpoint(run_dir, algo, spec, h, agent=agent, **({"mixer": mixer} if mixer is not None else {}))
    save_checkpoint(run_dir, algo, spec, h, agent=agent, **({"mixer": mixer} if mixer is not None else {}))
    logger.close()
    runner.close()
    return str(run_dir)


# ------------------------------------------------------------------ policy
class JointQPolicy(MARLPolicy):
    """Greedy decentralized execution: a_i = argmax_{valid a} Q_i(o_i, a) (IGM)."""

    def __init__(self, spec: MultiAgentSpec, agent: nn.Module, name: str):
        super().__init__(spec, name)
        self.agent = agent.eval()
        self.mask = torch.as_tensor(spec.action_mask())

    def select(self, obs: dict) -> np.ndarray:
        q = self.agent(torch.as_tensor(self.spec.obs_matrix(obs))[None])[0]
        return masked_argmax(q, self.mask).numpy()


def load_joint_policy(run_dir: str, defaults: dict, make_agent, name: str) -> JointQPolicy:
    ck = load_checkpoint(run_dir)
    h = {**defaults, **ck["hparams"]}
    agent = make_agent(ck["spec"], h)
    agent.load_state_dict(ck["agent"])
    return JointQPolicy(ck["spec"], agent, name)


def train(cfg: dict) -> str:
    return train_joint(cfg, "qmix", DEFAULTS, AgentMLP)


def load_policy(run_dir: str) -> JointQPolicy:
    return load_joint_policy(run_dir, DEFAULTS, AgentMLP, "qmix")
