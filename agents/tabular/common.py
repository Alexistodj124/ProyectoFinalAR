"""Shared pieces of the tabular agents: epsilon schedule, Policy, persistence, training loop."""
from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("LIBSUMO_AS_TRACI", "1")  # one simulation per process when training

import numpy as np

from agents.base import Policy
from agents.tabular.discretize import DEFAULT_THRESHOLDS, Discretizer
from experiments.common import TrainLogger, episode_seed, resolve_run_dir, save_config, set_seed

DEFAULT_HP = dict(
    alpha=0.1,
    gamma=0.99,
    eps_start=1.0,
    eps_end=0.05,
    eps_schedule="linear",  # "linear" | "exp"
    eps_decay_frac=0.7,  # fraction of total_episodes over which epsilon decays
    q_init=0.0,
    thresholds=list(DEFAULT_THRESHOLDS),
    agg="mean",
)


def epsilon_at(episode: int, total: int, hp: dict) -> float:
    """Annealed epsilon (bandits topic: epsilon-greedy trades exploration for exploitation;
    decaying it makes the policy asymptotically greedy, like a decaying-epsilon bandit)."""
    horizon = max(1.0, hp["eps_decay_frac"] * total)
    frac = min(1.0, episode / horizon)
    lo, hi = hp["eps_end"], hp["eps_start"]
    if hp["eps_schedule"] == "exp":
        return float(max(lo, hi * (lo / hi) ** frac))  # geometric from hi to lo
    return float(hi + (lo - hi) * frac)


class TabularPolicy(Policy):
    """Greedy policy over a dict Q-table {state tuple: np.ndarray(n_actions)}."""

    def __init__(self, q: dict, thresholds=DEFAULT_THRESHOLDS, agg: str = "mean", name: str = "qlearning"):
        self.q, self.thresholds, self.agg, self.name = q, tuple(thresholds), agg, name
        self.disc: dict[str, Discretizer] = {}

    def reset(self, sumo_env) -> None:
        super().reset(sumo_env)
        self.disc = {k: Discretizer.from_ts(ts, self.thresholds, self.agg) for k, ts in sumo_env.traffic_signals.items()}

    def act(self, obs):
        out = {}
        for a, o in obs.items():
            s = self.disc[a].encode(o)
            q = self.q.get(s)
            # Unseen state: keep the current green phase (a safe default).
            out[a] = int(np.argmax(q)) if q is not None else int(s[0])
        return out


def save_qtable(q: dict, path: Path, thresholds, agg: str) -> None:
    states = np.array(list(q), dtype=np.int16).reshape(len(q), -1)
    vals = np.array([q[s] for s in q], dtype=np.float64).reshape(len(q), -1)
    np.savez(path, states=states, q=vals, thresholds=np.array(thresholds, dtype=float), agg=np.array(agg))


def load_qtable(path: Path):
    z = np.load(path, allow_pickle=False)
    q = {tuple(int(x) for x in s): v.copy() for s, v in zip(z["states"], z["q"])}
    return q, tuple(float(t) for t in z["thresholds"]), str(z["agg"])


def policy_from_npz(path: str | Path, name: str) -> TabularPolicy:
    q, thr, agg = load_qtable(Path(path))
    return TabularPolicy(q, thr, agg, name=name)


def train_loop(cfg: dict, make_agent, algo: str) -> str:
    """Generic episodic loop shared by Q-Learning and Dyna-Q.

    make_agent(hp, n_actions, rng) -> agent with .q, .act(s, eps), .learn(s, a, r, s2, terminated),
    .info() (extra log columns) and .save(run_dir).
    """
    from env.reforma_env import get_sumo_env, make_parallel_env

    hp = {**DEFAULT_HP, **cfg.get("hparams", {})}
    seed, total = int(cfg.get("seed", 0)), int(cfg.get("total_episodes", 100))
    run_dir = resolve_run_dir(cfg)
    save_config(cfg, run_dir)
    set_seed(seed)
    rng = np.random.default_rng(seed)

    env = make_parallel_env(cfg["scenario"], seed, num_seconds=cfg.get("num_seconds"))
    logger = TrainLogger(run_dir)
    agent, env_steps, save_every = None, 0, int(cfg.get("save_every", 10))
    try:
        for ep in range(total):
            obs, _ = env.reset(seed=episode_seed(seed, ep))
            se = get_sumo_env(env)
            ids = list(obs)
            assert len(ids) == 1, f"tabular agents need a 1-TLS scenario, got {ids}"
            a_id = ids[0]
            disc = Discretizer.from_ts(se.traffic_signals[a_id], hp["thresholds"], hp["agg"])
            if agent is None:
                agent = make_agent(hp, int(se.traffic_signals[a_id].num_green_phases), rng)
            eps = epsilon_at(ep, total, hp)
            s, ret, waits, done = disc.encode(obs[a_id]), 0.0, [], False
            while not done:
                a = agent.act(s, eps)
                obs, rew, term, trunc, info = env.step({a_id: a})
                s2 = disc.encode(obs[a_id])
                agent.learn(s, a, float(rew[a_id]), s2, bool(term[a_id]))  # time-limit truncation still bootstraps
                ret += float(rew[a_id])
                waits.append(info[a_id].get("system_mean_waiting_time", 0.0))
                env_steps += 1
                s = s2
                done = bool(term[a_id] or trunc[a_id]) or not env.agents
            logger.log_episode(
                episode=ep, env_steps=env_steps, **{"return": round(ret, 4)},
                mean_waiting_time=round(float(np.mean(waits)), 4), epsilon=round(eps, 4),
                n_states=len(agent.q), **agent.info(),
            )
            if (ep + 1) % save_every == 0 or ep == total - 1:
                agent.save(run_dir, hp)
    finally:
        env.close()
        logger.close()
    return str(run_dir)
