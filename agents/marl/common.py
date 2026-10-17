"""Shared utilities for the multi-agent algorithms (IDQN, QMIX, MAPPO, comm).

The Reforma corridor is HETEROGENEOUS: every intersection has its own number of
green phases (actions) and incoming lanes (obs features). Parameter sharing needs a
common input/output size, so we use:

* Structured padding. sumo-rl's default observation is
  ``[one-hot phase (n_green)] + [min_green flag] + [density (n_lanes)] + [queue (n_lanes)]``.
  Each block is zero-padded on its own to ``max_green`` / ``max_lanes``, so feature
  k always means the same thing for every agent (plain tail padding would mix the
  phase one-hot of one agent with the densities of another).
* Agent-id one-hot appended to the padded obs (a shared network can still behave
  differently per intersection).
* Action masks: actions ``>= n_green`` of an agent are invalid. They are masked in
  argmax / softmax and in the bootstrap max, so they are never selected.
* Global state for CTDE = concat of padded obs (+ corridor-wide queues).

Everything here depends only on observation/action spaces (not on TraCI), so a
saved ``MultiAgentSpec`` is enough to rebuild a policy for evaluation.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field

import numpy as np
import torch

from agents.base import Policy
from env.scenarios import get_scenario, get_topology

NEG_INF = -1e9  # logit / Q value given to masked actions


# --------------------------------------------------------------------------- spec
@dataclass
class MultiAgentSpec:
    """Static description of the agents of one network (picklable as a dict)."""

    agents: list[str]  # fixed order (corridor order when the topology gives one)
    n_actions: list[int]  # green phases per agent
    obs_dims: list[int]  # raw sumo-rl obs size per agent
    neighbors: dict[str, list[str]] = field(default_factory=dict)

    # ---- derived sizes
    @property
    def n_agents(self) -> int:
        return len(self.agents)

    @property
    def n_lanes(self) -> list[int]:
        # obs = n_green + 1 + 2 * n_lanes  (sumo-rl default observation)
        return [max((d - a - 1) // 2, 0) for d, a in zip(self.obs_dims, self.n_actions)]

    @property
    def structured(self) -> bool:
        """True when every obs follows the default sumo-rl layout (else tail padding)."""
        return all(d == a + 1 + 2 * l for d, a, l in zip(self.obs_dims, self.n_actions, self.n_lanes))

    @property
    def max_actions(self) -> int:
        return max(self.n_actions)

    @property
    def max_lanes(self) -> int:
        return max(self.n_lanes)

    @property
    def obs_dim(self) -> int:
        """Padded obs size (without agent id)."""
        if self.structured:
            return self.max_actions + 1 + 2 * self.max_lanes
        return max(self.obs_dims)

    @property
    def max_degree(self) -> int:
        return max([len(self.neighbors.get(a, [])) for a in self.agents] + [1])

    def state_dim(self, with_queues: bool = True) -> int:
        return self.n_agents * self.obs_dim + (self.n_agents if with_queues else 0)

    # ---- (de)serialization
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MultiAgentSpec":
        return cls(**d)

    @classmethod
    def from_env(cls, penv, net_file: str | None = None) -> "MultiAgentSpec":
        agents = list(penv.possible_agents)
        neighbors = {a: [] for a in agents}
        if net_file:
            try:
                topo = get_topology(net_file)
                order = [a for a in topo["order"] if a in agents]
                if set(order) == set(agents):
                    agents = order
                neighbors = {a: [b for b in topo["neighbors"].get(a, []) if b in agents] for a in agents}
            except Exception:  # topology is a nicety, never a hard requirement
                pass
        return cls(
            agents=agents,
            n_actions=[int(penv.action_space(a).n) for a in agents],
            obs_dims=[int(np.prod(penv.observation_space(a).shape)) for a in agents],
            neighbors=neighbors,
        )

    # ---- per-agent feature helpers
    def pad_one(self, i: int, o: np.ndarray | None) -> np.ndarray:
        """Pad the raw obs of agent i to ``obs_dim`` (zeros if the agent is missing)."""
        out = np.zeros(self.obs_dim, dtype=np.float32)
        if o is None:
            return out
        o = np.asarray(o, dtype=np.float32).ravel()
        if not self.structured:
            out[: len(o)] = o
            return out
        g, l, G, L = self.n_actions[i], self.n_lanes[i], self.max_actions, self.max_lanes
        out[:g] = o[:g]  # phase one-hot
        out[G] = o[g]  # min-green flag
        out[G + 1 : G + 1 + l] = o[g + 1 : g + 1 + l]  # density per lane
        out[G + 1 + L : G + 1 + L + l] = o[g + 1 + l :]  # queue per lane
        return out

    def queue_of(self, i: int, o: np.ndarray | None) -> np.ndarray:
        """Per-lane queue vector of agent i padded to ``max_lanes``."""
        out = np.zeros(max(self.max_lanes, 1), dtype=np.float32)
        if o is None or not self.structured or self.n_lanes[i] == 0:
            return out
        q = np.asarray(o, dtype=np.float32).ravel()[-self.n_lanes[i] :]
        out[: len(q)] = q
        return out

    # ---- batched views used by the learners (rows follow self.agents)
    def obs_matrix(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        """[n_agents, obs_dim] padded observations (missing agents -> zeros)."""
        return np.stack([self.pad_one(i, obs.get(a)) for i, a in enumerate(self.agents)])

    def agent_ids(self) -> np.ndarray:
        return np.eye(self.n_agents, dtype=np.float32)

    def action_mask(self) -> np.ndarray:
        """[n_agents, max_actions] boolean, True = valid action."""
        m = np.zeros((self.n_agents, self.max_actions), dtype=bool)
        for i, n in enumerate(self.n_actions):
            m[i, :n] = True
        return m

    def neighbor_queues(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        """[n_agents, max_degree * max_lanes]: queue vectors of each agent's neighbors
        (communication v1 of the plan: neighbors' queues appended to the obs)."""
        L = max(self.max_lanes, 1)
        out = np.zeros((self.n_agents, self.max_degree * L), dtype=np.float32)
        idx = {a: i for i, a in enumerate(self.agents)}
        for i, a in enumerate(self.agents):
            for k, b in enumerate(self.neighbors.get(a, [])):
                out[i, k * L : (k + 1) * L] = self.queue_of(idx[b], obs.get(b))
        return out

    def neighbor_index(self) -> np.ndarray:
        """[n_agents, max_degree] index of each neighbor in self.agents, -1 = no neighbor."""
        idx = {a: i for i, a in enumerate(self.agents)}
        out = -np.ones((self.n_agents, self.max_degree), dtype=np.int64)
        for i, a in enumerate(self.agents):
            for k, b in enumerate(self.neighbors.get(a, [])):
                out[i, k] = idx[b]
        return out

    def global_state(self, obs: dict[str, np.ndarray], with_queues: bool = True) -> np.ndarray:
        """Centralized state s_t: padded obs of all agents (+ total queue per intersection)."""
        parts = [self.obs_matrix(obs).ravel()]
        if with_queues:
            parts.append(np.array([self.queue_of(i, obs.get(a)).sum() for i, a in enumerate(self.agents)], np.float32))
        return np.concatenate(parts).astype(np.float32)


# ------------------------------------------------------------------ masked ops
def masked_argmax(q: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """argmax over valid actions only (mask True = valid)."""
    return q.masked_fill(~mask, NEG_INF).argmax(-1)


def masked_logits(logits: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Invalid actions get probability ~0 under softmax."""
    return logits.masked_fill(~mask, NEG_INF)


def epsilon_greedy(q: np.ndarray, mask: np.ndarray, eps: float, rng: np.random.Generator) -> np.ndarray:
    """Per-agent epsilon-greedy restricted to valid actions. q, mask: [n_agents, A]."""
    acts = np.where(mask, q, NEG_INF).argmax(-1)
    for i in range(len(acts)):
        if rng.random() < eps:
            acts[i] = rng.choice(np.flatnonzero(mask[i]))
    return acts


def linear_schedule(start: float, end: float, duration: int, t: int) -> float:
    return start + min(t / max(duration, 1), 1.0) * (end - start)


# ------------------------------------------------------------------- rewards
class RewardScaler:
    """r' = scale * r, optionally divided by a running std of the discounted return
    (diff-waiting-time is large and grows with the number of agents)."""

    def __init__(self, scale: float = 1.0, normalize: bool = False, gamma: float = 0.99):
        self.scale, self.normalize, self.gamma = scale, normalize, gamma
        self.ret, self.count, self.mean, self.m2 = 0.0, 0, 0.0, 0.0

    def __call__(self, r: np.ndarray | float):
        r = np.asarray(r, dtype=np.float64) * self.scale
        if not self.normalize:
            return r.astype(np.float32)
        self.ret = self.gamma * self.ret + float(np.mean(r))
        self.count += 1  # Welford update of the return variance
        d = self.ret - self.mean
        self.mean += d / self.count
        self.m2 += d * (self.ret - self.mean)
        std = np.sqrt(self.m2 / self.count) if self.count > 1 else 1.0
        return (r / max(std, 1e-4)).astype(np.float32)

    def reset_episode(self):
        self.ret = 0.0


# --------------------------------------------------------------------- env loop
class MultiAgentRunner:
    """Robust wrapper around the PettingZoo parallel env.

    * Observations/rewards always come back for every agent of ``spec.agents``
      (an agent missing from a step keeps its last obs and gets reward 0).
    * ``done`` is True when all agents are truncated/terminated or the agent list
      empties (sumo-rl truncates everyone at ``num_seconds``).
    * ``terminated`` is reported separately: sumo-rl never terminates, it only
      truncates by time limit, so learners should keep bootstrapping
      (y = r + gamma * V(s')) at the last step.
    """

    def __init__(self, penv, spec: MultiAgentSpec):
        self.penv, self.spec = penv, spec
        self.last_obs: dict[str, np.ndarray] = {}

    def reset(self, seed: int | None = None) -> dict[str, np.ndarray]:
        obs, _ = self.penv.reset(seed=seed)
        self.last_obs = {a: np.asarray(obs.get(a, np.zeros(d, np.float32)), np.float32)
                         for a, d in zip(self.spec.agents, self.spec.obs_dims)}
        return dict(self.last_obs)

    def step(self, actions: dict[str, int]):
        live = set(getattr(self.penv, "agents", self.spec.agents))
        act = {a: int(actions[a]) for a in self.spec.agents if a in live and a in actions}
        obs, rew, term, trunc, info = self.penv.step(act)
        for a in self.spec.agents:
            if a in obs:
                self.last_obs[a] = np.asarray(obs[a], np.float32)
        rewards = np.array([float(rew.get(a, 0.0)) for a in self.spec.agents], np.float32)
        terminated = bool(act) and all(term.get(a, False) for a in act)
        done = (not getattr(self.penv, "agents", True)) or all(
            term.get(a, False) or trunc.get(a, False) for a in act
        )
        sys_info = next((v for v in info.values() if isinstance(v, dict) and "system_mean_waiting_time" in v), {})
        return dict(self.last_obs), rewards, terminated, bool(done), sys_info

    def close(self):
        self.penv.close()


def make_env_and_spec(cfg: dict, seed: int):
    """Build the parallel env of cfg['scenario'] and its MultiAgentSpec."""
    from env.reforma_env import make_parallel_env

    sc = get_scenario(cfg["scenario"])
    penv = make_parallel_env(sc, seed=seed, num_seconds=cfg.get("num_seconds"))
    spec = MultiAgentSpec.from_env(penv, sc.net_file)
    return penv, spec


def get_device(name: str | None = "auto") -> torch.device:
    """'auto' -> cuda if available, else cpu (small MLPs are slower on MPS)."""
    if name in (None, "auto"):
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(name)


def mlp(in_dim: int, hidden: list[int], out_dim: int, act=torch.nn.ReLU) -> torch.nn.Sequential:
    layers, d = [], in_dim
    for h in hidden:
        layers += [torch.nn.Linear(d, h), act()]
        d = h
    layers.append(torch.nn.Linear(d, out_dim))
    return torch.nn.Sequential(*layers)


def hp(cfg: dict, defaults: dict) -> dict:
    """Merge cfg['hparams'] over the algorithm defaults (and store the result back)."""
    out = {**defaults, **(cfg.get("hparams") or {})}
    cfg["hparams"] = out
    return out


# ------------------------------------------------------------ logging & policy
class EpisodeStats:
    """Accumulates the per-episode numbers every MARL learner logs."""

    def __init__(self):
        self.ret, self.steps, self.waits = 0.0, 0, []

    def add(self, rewards: np.ndarray, info: dict):
        self.ret += float(np.sum(rewards))  # team return, unscaled (sum over agents)
        self.steps += 1
        if "system_mean_waiting_time" in info:
            self.waits.append(float(info["system_mean_waiting_time"]))

    @property
    def mean_waiting_time(self) -> float:
        return float(np.mean(self.waits)) if self.waits else float("nan")


def save_checkpoint(run_dir, algo: str, spec: MultiAgentSpec, hparams: dict, **state) -> None:
    payload = {"algo": algo, "spec": spec.to_dict(), "hparams": dict(hparams)}
    payload.update({k: v.state_dict() if hasattr(v, "state_dict") else v for k, v in state.items()})
    torch.save(payload, os.path.join(str(run_dir), "model.pt"))


def load_checkpoint(run_dir) -> dict:
    ck = torch.load(os.path.join(str(run_dir), "model.pt"), map_location="cpu", weights_only=False)
    ck["spec"] = MultiAgentSpec.from_dict(ck["spec"])
    return ck


class MARLPolicy(Policy):
    """Base for the greedy policies returned by load_policy (agents.base.Policy API).

    Subclasses implement ``select(obs_full) -> np.ndarray[n_agents]`` on a dict that
    contains every agent of the spec (missing agents are None -> zero padding).
    """

    def __init__(self, spec: MultiAgentSpec, name: str):
        self.spec, self.name = spec, name

    @torch.no_grad()
    def act(self, obs: dict[str, np.ndarray]) -> dict[str, int]:
        acts = self.select({a: obs.get(a) for a in self.spec.agents})
        return {a: int(acts[i]) for i, a in enumerate(self.spec.agents) if a in obs}

    def select(self, obs: dict) -> np.ndarray:
        raise NotImplementedError


def libsumo_hint() -> None:
    if os.environ.get("LIBSUMO_AS_TRACI") != "1":
        print("[marl] tip: export LIBSUMO_AS_TRACI=1 for ~5-10x faster training")
