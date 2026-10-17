"""DQN family for ONE intersection, CleanRL-style: a single file, one training loop.

Ablation flags (PLAN §8, E3): vanilla -> +double -> +dueling -> +per, all in `hparams`:

    double:  Double DQN target (van Hasselt et al. 2016)
    dueling: Dueling network  Q = V + A - mean(A)   (agents/dqn/networks.py)
    per:     Prioritized Experience Replay           (agents/dqn/buffers.py)

Contract (docs/ARCHITECTURE.md §5): `train(cfg) -> run_dir` and `load_policy(run_dir) -> Policy`.
Runs on the 1-TLS gymnasium env (`make_gym_env`); device-agnostic (cuda if present).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from agents.base import Policy
from agents.rewards import DEFAULT_TRAIN_REWARD, train_env_kwargs
from agents.dqn.buffers import PrioritizedReplayBuffer, ReplayBuffer
from agents.dqn.networks import make_q_network
from env.reforma_env import make_gym_env
from env.scenarios import get_scenario
from experiments.common import TrainLogger, episode_seed, resolve_run_dir, save_config, set_seed

DEFAULTS = dict(
    lr=2.5e-4,  # 1e-3 forgot the good policy late in 200-episode runs (backlog came back)
    buffer_size=50_000,
    batch_size=64,
    target_update=2000,  # env steps between hard copies online -> target (~2.8 episodes)
    eps_start=1.0,
    eps_end=0.05,
    eps_fraction=0.5,  # epsilon decays linearly during this fraction of total steps
    gamma=0.99,
    learning_starts=1000,
    train_freq=1,
    grad_clip=10.0,
    hidden=64,
    double=False,
    dueling=False,
    per=False,
    per_alpha=0.6,
    per_beta0=0.4,  # beta is annealed beta0 -> 1 over the whole training
    obs_norm=False,
    reward_scale=0.1,  # r' = reward_scale * r in the TD target (logged return unscaled); 0.1 as in agents/marl
    device="auto",  # "auto" = cuda if available, "cpu" forces cpu
    save_every=10,  # episodes between model.pt checkpoints (0 = only at the end)
    reward_fn=DEFAULT_TRAIN_REWARD,  # training reward: diff-waiting-time + insertion backlog (agents/rewards.py)
)


class RunningNorm:
    """Running mean/std observation normalizer (off by default; sumo-rl obs are already ~[0, 1])."""

    def __init__(self, dim: int):
        self.mean = np.zeros(dim, np.float64)
        self.var = np.ones(dim, np.float64)
        self.count = 1e-4

    def update(self, x: np.ndarray) -> None:  # incremental mean/variance, one sample at a time
        self.count += 1
        d = x - self.mean
        self.mean += d / self.count
        self.var += (d * (x - self.mean) - self.var) / self.count

    def tensors(self, device):
        m = torch.as_tensor(self.mean, dtype=torch.float32, device=device)
        s = torch.as_tensor(np.sqrt(self.var) + 1e-6, dtype=torch.float32, device=device)
        return m, s


def _pick_device(name: str) -> torch.device:
    if name != "cpu" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _linear(start: float, end: float, frac: float) -> float:
    return start + (end - start) * min(max(frac, 0.0), 1.0)


def train(cfg: dict) -> str:
    hp = {**DEFAULTS, **cfg.get("hparams", {})}
    run_dir = resolve_run_dir(cfg)
    save_config(cfg, run_dir)
    seed = int(cfg.get("seed", 0))
    set_seed(seed)
    rng = np.random.default_rng(seed)
    device = _pick_device(hp["device"])

    sc = get_scenario(cfg["scenario"])
    num_seconds = int(cfg.get("num_seconds") or sc.num_seconds)
    steps_per_ep = math.ceil(num_seconds / sc.delta_time)
    total_episodes = int(cfg.get("total_episodes", 100))
    total_steps = total_episodes * steps_per_ep

    env = make_gym_env(sc, seed, num_seconds=num_seconds, **train_env_kwargs(hp))
    obs_dim = int(np.prod(env.observation_space.shape))
    n_actions = int(env.action_space.n)

    q_net = make_q_network(obs_dim, n_actions, hp["hidden"], hp["dueling"]).to(device)
    target_net = make_q_network(obs_dim, n_actions, hp["hidden"], hp["dueling"]).to(device)
    target_net.load_state_dict(q_net.state_dict())
    optimizer = torch.optim.Adam(q_net.parameters(), lr=hp["lr"])
    norm = RunningNorm(obs_dim) if hp["obs_norm"] else None
    if hp["per"]:
        buffer = PrioritizedReplayBuffer(hp["buffer_size"], obs_dim, alpha=hp["per_alpha"], rng=rng)
    else:
        buffer = ReplayBuffer(hp["buffer_size"], obs_dim, rng=rng)

    def prep(x: torch.Tensor) -> torch.Tensor:
        if norm is None:
            return x
        m, s = norm.tensors(x.device)
        return (x - m) / s

    def save(path: Path) -> None:
        torch.save(
            {
                "state_dict": q_net.state_dict(),
                "obs_dim": obs_dim,
                "n_actions": n_actions,
                "hidden": hp["hidden"],
                "dueling": hp["dueling"],
                "norm": None if norm is None else {"mean": norm.mean.tolist(), "var": norm.var.tolist()},
                "config": cfg,
            },
            path,
        )

    logger = TrainLogger(run_dir)
    global_step = 0
    for ep in range(total_episodes):
        obs, _ = env.reset(seed=episode_seed(seed, ep))
        ep_return, wait_sum, n_steps = 0.0, 0.0, 0
        losses: list[float] = []
        q_means: list[float] = []
        eps = hp["eps_end"]
        done = False
        while not done:
            # epsilon-greedy with linear decay over eps_fraction of the total budget
            eps = _linear(hp["eps_start"], hp["eps_end"], global_step / (hp["eps_fraction"] * total_steps))
            if norm is not None:
                norm.update(obs.astype(np.float64))
            if rng.random() < eps:
                action = int(rng.integers(n_actions))
            else:
                with torch.no_grad():
                    q = q_net(prep(torch.as_tensor(obs, dtype=torch.float32, device=device)[None]))
                action = int(q.argmax(dim=1).item())

            next_obs, reward, terminated, truncated, info = env.step(action)
            # Store only `terminated` as "done": a time-limit truncation is not a real
            # terminal state, so the target must still bootstrap from next_obs.
            buffer.add(obs, action, hp["reward_scale"] * reward, next_obs, terminated)
            obs = next_obs
            done = terminated or truncated
            ep_return += reward
            wait_sum += float(info.get("system_mean_waiting_time", 0.0))
            n_steps += 1
            global_step += 1

            if global_step > hp["learning_starts"] and len(buffer) >= hp["batch_size"]:
                if global_step % hp["train_freq"] == 0:
                    beta = _linear(hp["per_beta0"], 1.0, global_step / total_steps)
                    b = buffer.sample(hp["batch_size"], device, beta=beta)
                    s, s2 = prep(b["obs"]), prep(b["next_obs"])
                    with torch.no_grad():
                        if hp["double"]:
                            # Double DQN: online net CHOOSES a* = argmax_a Q_online(s',a),
                            # target net EVALUATES it -> y = r + g * Q_target(s', a*). Reduces overestimation.
                            a_star = q_net(s2).argmax(dim=1, keepdim=True)
                            q_next = target_net(s2).gather(1, a_star).squeeze(1)
                        else:
                            # Vanilla DQN: y = r + g * max_a Q_target(s', a)  (same net selects and evaluates)
                            q_next = target_net(s2).max(dim=1).values
                        y = b["rewards"] + hp["gamma"] * (1.0 - b["dones"]) * q_next  # TD target
                    q_sa = q_net(s).gather(1, b["actions"][:, None]).squeeze(1)
                    td = y - q_sa
                    # Huber loss, weighted by PER importance-sampling weights (all 1 without PER)
                    loss = (b["weights"] * F.smooth_l1_loss(q_sa, y, reduction="none")).mean()
                    optimizer.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(q_net.parameters(), hp["grad_clip"])
                    optimizer.step()
                    buffer.update_priorities(b["idx"], td.detach().abs().cpu().numpy())  # p = |delta| + eps
                    losses.append(float(loss.item()))
                    q_means.append(float(q_sa.mean().item()))
            if global_step % hp["target_update"] == 0:
                target_net.load_state_dict(q_net.state_dict())  # hard target update

        logger.log_episode(
            episode=ep,
            env_steps=global_step,
            **{"return": round(ep_return, 4)},
            mean_waiting_time=round(wait_sum / max(n_steps, 1), 4),
            epsilon=round(eps, 4),
            loss=float(np.mean(losses)) if losses else float("nan"),
            q_mean=float(np.mean(q_means)) if q_means else float("nan"),
        )
        if hp["save_every"] and (ep + 1) % hp["save_every"] == 0:
            save(run_dir / "model.pt")

    save(run_dir / "model.pt")
    logger.close()
    env.close()
    return str(run_dir)


class DQNPolicy(Policy):
    """Greedy policy argmax_a Q(s, a) for a single intersection."""

    def __init__(self, ckpt: dict, name: str = "dqn"):
        self.name = name
        self.net = make_q_network(ckpt["obs_dim"], ckpt["n_actions"], ckpt["hidden"], ckpt["dueling"])
        self.net.load_state_dict(ckpt["state_dict"])
        self.net.eval()
        n = ckpt.get("norm")
        self.mean = None if n is None else torch.tensor(n["mean"], dtype=torch.float32)
        self.std = None if n is None else torch.tensor(n["var"], dtype=torch.float32).sqrt() + 1e-6

    @torch.no_grad()
    def act(self, obs: dict[str, np.ndarray]) -> dict[str, int]:
        out = {}
        for agent, o in obs.items():
            x = torch.as_tensor(np.asarray(o), dtype=torch.float32)[None]
            if self.mean is not None:
                x = (x - self.mean) / self.std
            out[agent] = int(self.net(x).argmax(dim=1).item())
        return out


def load_policy(run_dir: str) -> DQNPolicy:
    ckpt = torch.load(Path(run_dir) / "model.pt", map_location="cpu", weights_only=False)
    cfg = ckpt.get("config", {})
    return DQNPolicy(ckpt, name=cfg.get("name", cfg.get("algo", "dqn")))
