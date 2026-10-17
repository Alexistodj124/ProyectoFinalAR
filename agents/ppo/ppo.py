"""PPO for ONE intersection with Stable-Baselines3 (PLAN §4 "Policy Gradient", "Deep RL II").

Why PPO (and not SAC / TD3): the action is DISCRETE (index of the next green phase,
`Discrete(n_green)`). TD3 is a deterministic-policy-gradient method and SAC (original
form) is built on the reparameterisation trick; both need a continuous action space
to differentiate Q through the action. PPO works for discrete actions and gives the
policy-based contrast against value-based DQN (E4).

Key formulas (SB3 implements them; hparams below map to them):
    GAE:      A_t = sum_l (gamma * lambda)^l * delta_{t+l},  delta_t = r_t + gamma V(s_{t+1}) - V(s_t)
    Clipped:  L = E[ min(r_t A_t, clip(r_t, 1-eps, 1+eps) A_t) ],  r_t = pi(a|s) / pi_old(a|s)
    Total:    L_total = -L + vf_coef * L_value - ent_coef * H[pi]

Contract (docs/ARCHITECTURE.md §5): `train(cfg) -> run_dir` and `load_policy(run_dir) -> Policy`.
"""
from __future__ import annotations

import math
from pathlib import Path

import gymnasium as gym
import numpy as np
import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import DummyVecEnv

from agents.base import Policy
from env.reforma_env import make_gym_env
from env.scenarios import get_scenario
from experiments.common import TrainLogger, episode_seed, resolve_run_dir, save_config, set_seed

DEFAULTS = dict(
    n_steps=None,  # None = one episode (num_seconds / delta_time = 720 for 3600 s at 5 s)
    batch_size=64,
    n_epochs=10,
    gamma=0.99,
    gae_lambda=0.95,
    clip_range=0.2,
    ent_coef=0.01,
    vf_coef=0.5,
    learning_rate=3e-4,
    max_grad_norm=0.5,
    net_arch=[64, 64],
    device="cpu",  # SB3 recommends CPU for small MLP policies; "auto"/"cuda" also work
)


class EpisodeSeedWrapper(gym.Wrapper):
    """Every reset() draws a new demand realization: seed = episode_seed(seed, ep).

    SB3 passes its own seed only on the first reset (or none), so it is ignored on
    purpose: demand reproducibility is controlled here, like in the DQN loop.
    """

    def __init__(self, env: gym.Env, seed: int):
        super().__init__(env)
        self.run_seed = seed
        self.episode = 0

    def reset(self, *, seed=None, options=None):
        s = episode_seed(self.run_seed, self.episode)
        self.episode += 1
        return self.env.reset(seed=s, options=options)


class EpisodeLogCallback(BaseCallback):
    """Writes one TrainLogger row per finished episode (same columns as DQN)."""

    def __init__(self, logger: TrainLogger):
        super().__init__()
        self.tlog = logger
        self.episode = 0
        self.ep_return = 0.0
        self.wait_sum = 0.0
        self.n = 0

    def _on_step(self) -> bool:
        reward = float(self.locals["rewards"][0])
        info = self.locals["infos"][0]
        self.ep_return += reward
        self.wait_sum += float(info.get("system_mean_waiting_time", 0.0))
        self.n += 1
        if self.locals["dones"][0]:
            vals = self.model.logger.name_to_value  # values of the last PPO update
            self.tlog.log_episode(
                episode=self.episode,
                env_steps=self.num_timesteps,
                **{"return": round(self.ep_return, 4)},
                mean_waiting_time=round(self.wait_sum / max(self.n, 1), 4),
                loss=float(vals.get("train/loss", float("nan"))),
                entropy=-float(vals.get("train/entropy_loss", float("nan"))),
                explained_variance=float(vals.get("train/explained_variance", float("nan"))),
            )
            self.episode += 1
            self.ep_return, self.wait_sum, self.n = 0.0, 0.0, 0
        return True


def train(cfg: dict) -> str:
    hp = {**DEFAULTS, **cfg.get("hparams", {})}
    run_dir = resolve_run_dir(cfg)
    save_config(cfg, run_dir)
    seed = int(cfg.get("seed", 0))
    set_seed(seed)

    sc = get_scenario(cfg["scenario"])
    num_seconds = int(cfg.get("num_seconds") or sc.num_seconds)
    steps_per_ep = math.ceil(num_seconds / sc.delta_time)
    total_episodes = int(cfg.get("total_episodes", 100))
    n_steps = int(hp["n_steps"] or steps_per_ep)
    batch_size = min(int(hp["batch_size"]), n_steps)

    env = DummyVecEnv([lambda: EpisodeSeedWrapper(make_gym_env(sc, seed, num_seconds=num_seconds), seed)])
    model = PPO(
        "MlpPolicy",
        env,
        n_steps=n_steps,
        batch_size=batch_size,
        n_epochs=hp["n_epochs"],
        gamma=hp["gamma"],
        gae_lambda=hp["gae_lambda"],
        clip_range=hp["clip_range"],
        ent_coef=hp["ent_coef"],
        vf_coef=hp["vf_coef"],
        learning_rate=hp["learning_rate"],
        max_grad_norm=hp["max_grad_norm"],
        policy_kwargs=dict(net_arch=dict(pi=list(hp["net_arch"]), vf=list(hp["net_arch"]))),
        seed=seed,
        device=hp["device"],
        verbose=0,
    )
    logger = TrainLogger(run_dir)
    # Same env-step budget as DQN: total_episodes * steps_per_episode.
    model.learn(total_timesteps=total_episodes * steps_per_ep, callback=EpisodeLogCallback(logger))
    model.save(str(run_dir / "model.zip"))
    logger.close()
    env.close()
    return str(run_dir)


class PPOPolicy(Policy):
    """Deterministic (mode of the categorical) PPO policy for a single intersection."""

    def __init__(self, model: PPO, name: str = "ppo"):
        self.name = name
        self.model = model

    def act(self, obs: dict[str, np.ndarray]) -> dict[str, int]:
        out = {}
        for agent, o in obs.items():
            action, _ = self.model.predict(np.asarray(o, dtype=np.float32), deterministic=True)
            out[agent] = int(action)
        return out


def load_policy(run_dir: str) -> PPOPolicy:
    model = PPO.load(str(Path(run_dir) / "model.zip"), device="cpu")
    cfg_path = Path(run_dir) / "config.yaml"
    name = yaml.safe_load(cfg_path.read_text()).get("name", "ppo") if cfg_path.exists() else "ppo"
    return PPOPolicy(model, name=name)
