"""Independent Double DQN (IDQN): one Double-DQN learner per traffic light.

MARL I baseline of the plan (E5) and, with ``neighbor_obs: true``, the
"communication v1" of E6 (each agent also sees its corridor neighbors' queues).

Each agent i learns Q_i(o_i, a_i) with its own replay buffer and target network,
treating the other intersections as part of the environment. This makes the
environment NON-STATIONARY from agent i's point of view: P(o'_i | o_i, a_i) depends
on the neighbors' policies, which change while they learn, so (a) the Markov
assumption behind the TD target is violated and (b) old transitions in the replay
buffer describe neighbors that no longer exist. Small replay buffers, slow epsilon
decay and target networks mitigate it; CTDE methods (QMIX, MAPPO) address it
directly. IDQN is still a strong baseline in traffic control (Chu et al. 2019).

Double DQN target (van Hasselt et al. 2016), with invalid phases masked:
    a* = argmax_{a valid} Q_online(o', a)
    y  = r + gamma * (1 - terminated) * Q_target(o', a*)
sumo-rl only truncates by time limit (never terminates), so the last step keeps
bootstrapping.
"""
from __future__ import annotations

import time

import numpy as np
import torch
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
    buffer_size=50_000,
    batch_size=64,
    learning_starts=1_000,  # env steps before the first update
    train_freq=1,
    target_update_interval=500,  # hard copy every N env steps (used when tau == 1)
    tau=1.0,  # < 1 => Polyak averaging every step instead
    eps_start=1.0,
    eps_end=0.05,
    eps_fraction=0.3,  # fraction of the total env steps used to decay epsilon
    grad_clip=10.0,
    reward="local",  # local: r_i of the own intersection | team: sum_i r_i to everyone
    reward_scale=0.1,
    reward_norm=False,
    neighbor_obs=False,  # append neighbors' per-lane queues (communication v1)
    shared_params=False,  # one network for all agents (+ agent id) instead of one per agent
    device="auto",
    save_every=10,
)


# ------------------------------------------------------------------ features
def build_features(spec: MultiAgentSpec, obs: dict, neighbor_obs: bool, add_id: bool) -> np.ndarray:
    """[n_agents, in_dim] = padded own obs (+ neighbors' queues) (+ agent id)."""
    parts = [spec.obs_matrix(obs)]
    if neighbor_obs:
        parts.append(spec.neighbor_queues(obs))
    if add_id:
        parts.append(spec.agent_ids())
    return np.concatenate(parts, axis=1).astype(np.float32)


def feature_dim(spec: MultiAgentSpec, neighbor_obs: bool, add_id: bool) -> int:
    d = spec.obs_dim
    if neighbor_obs:
        d += spec.max_degree * max(spec.max_lanes, 1)
    if add_id:
        d += spec.n_agents
    return d


def build_nets(spec: MultiAgentSpec, h: dict) -> torch.nn.ModuleList:
    in_dim = feature_dim(spec, h["neighbor_obs"], h["shared_params"])
    n_nets = 1 if h["shared_params"] else spec.n_agents
    return torch.nn.ModuleList([mlp(in_dim, h["hidden"], spec.max_actions) for _ in range(n_nets)])


# ------------------------------------------------------------------ replay
class ReplayBuffer:
    """Uniform replay of one agent's transitions (o, a, r, o', terminated)."""

    def __init__(self, capacity: int, obs_dim: int, rng: np.random.Generator):
        self.cap, self.rng, self.n, self.i = capacity, rng, 0, 0
        self.o = np.zeros((capacity, obs_dim), np.float32)
        self.o2 = np.zeros((capacity, obs_dim), np.float32)
        self.a = np.zeros(capacity, np.int64)
        self.r = np.zeros(capacity, np.float32)
        self.d = np.zeros(capacity, np.float32)

    def add(self, o, a, r, o2, d):
        j = self.i
        self.o[j], self.a[j], self.r[j], self.o2[j], self.d[j] = o, a, r, o2, d
        self.i = (self.i + 1) % self.cap
        self.n = min(self.n + 1, self.cap)

    def sample(self, k: int, device) -> tuple[torch.Tensor, ...]:
        idx = self.rng.integers(0, self.n, size=k)
        return tuple(torch.as_tensor(x[idx], device=device) for x in (self.o, self.a, self.r, self.o2, self.d))


# ------------------------------------------------------------------ train
def train(cfg: dict) -> str:
    h = hp(cfg, DEFAULTS)
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
    steps_per_ep = int((cfg.get("num_seconds") or sc.num_seconds) // sc.delta_time)
    total_steps = int(cfg["total_episodes"]) * steps_per_ep

    nets = build_nets(spec, h).to(device)
    targets = build_nets(spec, h).to(device)
    targets.load_state_dict(nets.state_dict())
    opts = [torch.optim.Adam(n.parameters(), lr=h["lr"]) for n in nets]
    in_dim = feature_dim(spec, h["neighbor_obs"], h["shared_params"])
    buffers = [ReplayBuffer(h["buffer_size"], in_dim, rng) for _ in spec.agents]  # separate replay per agent
    mask = torch.as_tensor(spec.action_mask(), device=device)
    mask_np = spec.action_mask()
    scaler = RewardScaler(h["reward_scale"], h["reward_norm"], h["gamma"])
    net_of = (lambda i: 0) if h["shared_params"] else (lambda i: i)

    def q_all(x: np.ndarray) -> np.ndarray:
        xt = torch.as_tensor(x, device=device)
        return torch.stack([nets[net_of(i)](xt[i]) for i in range(spec.n_agents)]).cpu().numpy()

    def td_loss(i: int) -> torch.Tensor:
        net, tgt = nets[net_of(i)], targets[net_of(i)]
        o, a, r, o2, d = buffers[i].sample(h["batch_size"], device)
        m = mask[i].expand(len(a), -1)
        with torch.no_grad():
            a_star = masked_argmax(net(o2), m)  # Double DQN: online net selects ...
            q_next = tgt(o2).gather(1, a_star[:, None]).squeeze(1)  # ... target net evaluates
            y = r + h["gamma"] * (1.0 - d) * q_next  # TD target
        q = net(o).gather(1, a[:, None]).squeeze(1)
        return F.smooth_l1_loss(q, y)

    logger = TrainLogger(run_dir)
    global_step = 0
    for ep in range(int(cfg["total_episodes"])):
        t0 = time.time()
        obs = runner.reset(seed=episode_seed(seed, ep))
        scaler.reset_episode()
        x = build_features(spec, obs, h["neighbor_obs"], h["shared_params"])
        stats, losses, done = EpisodeStats(), [], False
        while not done:
            eps = linear_schedule(h["eps_start"], h["eps_end"], int(h["eps_fraction"] * total_steps), global_step)
            with torch.no_grad():
                acts = epsilon_greedy(q_all(x), mask_np, eps, rng)
            obs2, rew, term, done, info = runner.step({a: acts[i] for i, a in enumerate(spec.agents)})
            stats.add(rew, info)
            r = scaler(rew if h["reward"] == "local" else np.full_like(rew, rew.sum()))
            x2 = build_features(spec, obs2, h["neighbor_obs"], h["shared_params"])
            for i in range(spec.n_agents):
                buffers[i].add(x[i], acts[i], r[i], x2[i], float(term))
            x = x2
            global_step += 1

            if global_step > h["learning_starts"] and global_step % h["train_freq"] == 0:
                if h["shared_params"]:  # one optimizer, loss averaged over agents
                    loss = torch.stack([td_loss(i) for i in range(spec.n_agents)]).mean()
                    opts[0].zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(nets[0].parameters(), h["grad_clip"])
                    opts[0].step()
                    losses.append(loss.item())
                else:  # fully independent learners
                    for i in range(spec.n_agents):
                        loss = td_loss(i)
                        opts[i].zero_grad()
                        loss.backward()
                        torch.nn.utils.clip_grad_norm_(nets[i].parameters(), h["grad_clip"])
                        opts[i].step()
                        losses.append(loss.item())
                if h["tau"] < 1.0:  # Polyak: theta' <- tau theta + (1 - tau) theta'
                    with torch.no_grad():
                        for p, tp in zip(nets.parameters(), targets.parameters()):
                            tp.lerp_(p, h["tau"])
            if h["tau"] >= 1.0 and global_step % h["target_update_interval"] == 0:
                targets.load_state_dict(nets.state_dict())

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
            save_checkpoint(run_dir, "idqn", spec, h, nets=nets)
    save_checkpoint(run_dir, "idqn", spec, h, nets=nets)
    logger.close()
    runner.close()
    return str(run_dir)


# ------------------------------------------------------------------ policy
class IDQNPolicy(MARLPolicy):
    def __init__(self, spec: MultiAgentSpec, nets: torch.nn.ModuleList, h: dict):
        super().__init__(spec, "idqn_neighbor_obs" if h["neighbor_obs"] else "idqn")
        self.nets, self.h = nets.eval(), h
        self.mask = torch.as_tensor(spec.action_mask())

    def select(self, obs: dict) -> np.ndarray:
        x = torch.as_tensor(build_features(self.spec, obs, self.h["neighbor_obs"], self.h["shared_params"]))
        q = torch.stack([self.nets[0 if self.h["shared_params"] else i](x[i]) for i in range(self.spec.n_agents)])
        return masked_argmax(q, self.mask).numpy()


def load_policy(run_dir: str) -> IDQNPolicy:
    ck = load_checkpoint(run_dir)
    h = {**DEFAULTS, **ck["hparams"]}
    nets = build_nets(ck["spec"], h)
    nets.load_state_dict(ck["nets"])
    return IDQNPolicy(ck["spec"], nets, h)
