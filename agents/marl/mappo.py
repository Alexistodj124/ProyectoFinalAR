"""MAPPO (Yu et al., 2022), CleanRL style, for heterogeneous traffic lights.

Actor-critic with CTDE (Deep RL II + MARL II):

* Actor: ONE policy network shared by all intersections,
  pi_theta(a_i | [padded o_i, onehot(i)]), invalid phases masked before softmax.
* Critic: centralized V_phi(s) on the global state (padded obs of the whole
  corridor + queue totals), trained on the TEAM reward r = sum_i r_i. It is only
  used during training; execution needs just the actor and o_i.
* Advantages with GAE(lambda) (Schulman et al. 2016):
      delta_t = r_t + gamma * V(s_{t+1}) - V(s_t)
      A_t     = sum_k (gamma * lambda)^k delta_{t+k}
  sumo-rl only truncates by time limit, so the end of a rollout bootstraps from
  V(s_T) instead of treating it as terminal.
* PPO clipped surrogate per agent (shared team advantage):
      L_clip = E[min(rho_i A, clip(rho_i, 1-eps, 1+eps) A)],  rho_i = pi(a_i|o_i)/pi_old(a_i|o_i)
  plus entropy bonus, value loss with optional clipping and running value
  normalization (PopArt-lite), as recommended by the MAPPO paper.
* One rollout = one episode (or ``n_steps`` env steps if set), then
  ``update_epochs`` epochs of minibatch SGD over that rollout.
"""
from __future__ import annotations

import time

import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Categorical

from agents.marl.common import (
    EpisodeStats,
    MARLPolicy,
    MultiAgentRunner,
    MultiAgentSpec,
    RewardScaler,
    get_device,
    hp,
    libsumo_hint,
    load_checkpoint,
    make_env_and_spec,
    masked_logits,
    mlp,
    save_checkpoint,
)
from env.scenarios import get_scenario
from experiments.common import TrainLogger, episode_seed, resolve_run_dir, save_config, set_seed

DEFAULTS = dict(
    lr=5e-4,
    anneal_lr=True,  # linear decay lr -> 0 over the run (CleanRL default); constant lr degraded late in training
    gamma=0.99,
    gae_lambda=0.95,
    clip_coef=0.2,
    ent_coef=0.01,
    vf_coef=0.5,
    update_epochs=5,
    num_minibatches=4,
    n_steps=None,  # None => one full episode per update
    max_grad_norm=10.0,
    norm_adv=True,
    clip_vloss=True,
    value_norm=True,
    hidden=[128, 128],
    critic_hidden=[256, 256],
    state_queues=True,
    reward_scale=0.1,
    reward_norm=False,
    device="auto",
    save_every=10,
    reward_fn="diff-waiting-time-pending",  # training reward (agents/rewards.py); "scenario" = plain sumo-rl
)


# ------------------------------------------------------------------ networks
class Actor(nn.Module):
    """Shared decentralized actor: logits over max_actions (to be masked)."""

    def __init__(self, spec: MultiAgentSpec, h: dict):
        super().__init__()
        self.register_buffer("ids", torch.as_tensor(spec.agent_ids()))
        self.register_buffer("mask", torch.as_tensor(spec.action_mask()))
        self.net = mlp(spec.obs_dim + spec.n_agents, h["hidden"], spec.max_actions, act=nn.Tanh)
        nn.init.orthogonal_(self.net[-1].weight, 0.01)  # near-uniform initial policy (CleanRL)

    def dist(self, obs: torch.Tensor) -> Categorical:  # obs [B, n, D]
        logits = self.net(torch.cat([obs, self.ids.expand(obs.shape[0], -1, -1)], -1))
        return Categorical(logits=masked_logits(logits, self.mask.expand_as(logits)))


class Critic(nn.Module):
    """Centralized value V(s) of the team (global state)."""

    def __init__(self, spec: MultiAgentSpec, h: dict):
        super().__init__()
        self.net = mlp(spec.state_dim(h["state_queues"]), h["critic_hidden"], 1, act=nn.Tanh)

    def forward(self, s: torch.Tensor) -> torch.Tensor:
        return self.net(s).squeeze(-1)


class ValueNorm:
    """Running mean/std of the value targets (critic predicts normalized values)."""

    def __init__(self, eps: float = 1e-5):
        self.mean, self.var, self.count, self.eps = 0.0, 1.0, eps, eps

    def update(self, x: np.ndarray):
        bm, bv, bc = float(x.mean()), float(x.var()), x.size
        d, tot = bm - self.mean, self.count + bc
        self.mean += d * bc / tot
        self.var = (self.var * self.count + bv * bc + d**2 * self.count * bc / tot) / tot
        self.count = tot

    def normalize(self, x):
        return (x - self.mean) / np.sqrt(self.var + self.eps)

    def denormalize(self, x):
        return x * np.sqrt(self.var + self.eps) + self.mean


# ------------------------------------------------------------------ training
def train(cfg: dict) -> str:
    h = hp(cfg, DEFAULTS)
    seed = int(cfg.get("seed", 0))
    run_dir = resolve_run_dir(cfg)
    save_config(cfg, run_dir)
    set_seed(seed)
    libsumo_hint()
    device = get_device(h["device"])

    penv, spec = make_env_and_spec(cfg, seed)
    runner = MultiAgentRunner(penv, spec)
    actor, critic = Actor(spec, h).to(device), Critic(spec, h).to(device)
    params = list(actor.parameters()) + list(critic.parameters())
    opt = torch.optim.Adam(params, lr=h["lr"], eps=1e-5)
    scaler = RewardScaler(h["reward_scale"], h["reward_norm"], h["gamma"])
    vnorm = ValueNorm() if h["value_norm"] else None
    T_max = h["n_steps"]
    sc = get_scenario(cfg["scenario"])
    total_steps = int(cfg["total_episodes"]) * int((cfg.get("num_seconds") or sc.num_seconds) // sc.delta_time)

    def value(s_t: torch.Tensor) -> np.ndarray:
        v = critic(s_t).cpu().numpy()
        return vnorm.denormalize(v) if vnorm else v

    def update(buf: dict, last_value: float) -> dict:
        T = len(buf["r"])
        obs = torch.as_tensor(np.array(buf["o"]), device=device)  # [T, n, D]
        st = torch.as_tensor(np.array(buf["s"]), device=device)  # [T, S]
        act = torch.as_tensor(np.array(buf["a"]), device=device)  # [T, n]
        logp_old = torch.as_tensor(np.array(buf["logp"]), device=device)  # [T, n]
        v_old = np.array(buf["v"], np.float32)  # denormalized V(s_t)
        r, term = np.array(buf["r"], np.float32), np.array(buf["term"], np.float32)

        # GAE(lambda) on the team reward, bootstrapping V(s_T) at truncation.
        adv, last = np.zeros(T, np.float32), 0.0
        for t in reversed(range(T)):
            next_v = last_value if t == T - 1 else v_old[t + 1]
            nonterm = 1.0 - term[t]
            delta = r[t] + h["gamma"] * next_v * nonterm - v_old[t]
            last = delta + h["gamma"] * h["gae_lambda"] * nonterm * last
            adv[t] = last
        ret = adv + v_old  # lambda-returns = critic targets
        if vnorm:
            vnorm.update(ret)
            ret_t, v_old_t = vnorm.normalize(ret), vnorm.normalize(v_old)
        else:
            ret_t, v_old_t = ret, v_old
        adv_t = torch.as_tensor(adv, device=device)
        ret_t = torch.as_tensor(ret_t, dtype=torch.float32, device=device)
        v_old_t = torch.as_tensor(v_old_t, dtype=torch.float32, device=device)

        mb = max(T // h["num_minibatches"], 1)
        info = {"pg": [], "v": [], "ent": [], "kl": []}
        for _ in range(h["update_epochs"]):
            perm = torch.randperm(T, device=device)
            for k in range(0, T, mb):
                idx = perm[k : k + mb]
                d = actor.dist(obs[idx])
                logp, ent = d.log_prob(act[idx]), d.entropy()  # [b, n]
                ratio = (logp - logp_old[idx]).exp()
                a = adv_t[idx]
                if h["norm_adv"] and len(idx) > 1:
                    a = (a - a.mean()) / (a.std() + 1e-8)
                a = a[:, None]  # same team advantage for every agent
                pg = torch.max(-a * ratio, -a * ratio.clamp(1 - h["clip_coef"], 1 + h["clip_coef"])).mean()
                v = critic(st[idx])
                if h["clip_vloss"]:
                    v_clip = v_old_t[idx] + (v - v_old_t[idx]).clamp(-h["clip_coef"], h["clip_coef"])
                    vloss = 0.5 * torch.max((v - ret_t[idx]) ** 2, (v_clip - ret_t[idx]) ** 2).mean()
                else:
                    vloss = 0.5 * ((v - ret_t[idx]) ** 2).mean()
                loss = pg - h["ent_coef"] * ent.mean() + h["vf_coef"] * vloss
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(params, h["max_grad_norm"])
                opt.step()
                with torch.no_grad():
                    info["kl"].append(((ratio - 1) - ratio.log()).mean().item())  # approx KL (CleanRL)
                info["pg"].append(pg.item())
                info["v"].append(vloss.item())
                info["ent"].append(ent.mean().item())
        return {k: float(np.mean(v)) for k, v in info.items()}

    def new_buf():
        return {k: [] for k in ("o", "s", "a", "logp", "v", "r", "term")}

    logger = TrainLogger(run_dir)
    global_step = 0
    for ep in range(int(cfg["total_episodes"])):
        t0 = time.time()
        obs = runner.reset(seed=episode_seed(seed, ep))
        scaler.reset_episode()
        o, s = spec.obs_matrix(obs), spec.global_state(obs, h["state_queues"])
        stats, upd, buf, done = EpisodeStats(), [], new_buf(), False
        while not done:
            with torch.no_grad():
                d = actor.dist(torch.as_tensor(o, device=device)[None])
                a = d.sample()
                logp = d.log_prob(a)[0].cpu().numpy()
                v = float(value(torch.as_tensor(s, device=device)[None])[0])
            acts = a[0].cpu().numpy()
            obs2, rew, term, done, info = runner.step({ag: acts[i] for i, ag in enumerate(spec.agents)})
            stats.add(rew, info)
            for k, x in zip(buf, (o, s, acts, logp, v, float(scaler(rew.sum())), float(term))):
                buf[k].append(x)
            o, s = spec.obs_matrix(obs2), spec.global_state(obs2, h["state_queues"])
            global_step += 1
            if done or (T_max and len(buf["r"]) >= T_max):
                with torch.no_grad():
                    last_v = 0.0 if term else float(value(torch.as_tensor(s, device=device)[None])[0])
                if h["anneal_lr"]:
                    for g in opt.param_groups:
                        g["lr"] = h["lr"] * max(1.0 - (global_step - len(buf["r"])) / total_steps, 0.0)
                upd.append(update(buf, last_v))
                buf = new_buf()

        mean = lambda k: round(float(np.mean([u[k] for u in upd])), 6) if upd else float("nan")
        logger.log_episode(
            episode=ep,
            env_steps=global_step,
            **{"return": round(stats.ret, 4)},
            mean_waiting_time=round(stats.mean_waiting_time, 4),
            entropy=mean("ent"),
            loss=mean("pg"),
            value_loss=mean("v"),
            approx_kl=mean("kl"),
            episode_time=round(time.time() - t0, 2),
        )
        if (ep + 1) % h["save_every"] == 0:
            save_checkpoint(run_dir, "mappo", spec, h, actor=actor, critic=critic)
    save_checkpoint(run_dir, "mappo", spec, h, actor=actor, critic=critic)
    logger.close()
    runner.close()
    return str(run_dir)


# ------------------------------------------------------------------ policy
class MAPPOPolicy(MARLPolicy):
    """Decentralized execution with the shared actor (greedy = argmax of masked logits)."""

    def __init__(self, spec: MultiAgentSpec, actor: Actor, deterministic: bool = True):
        super().__init__(spec, "mappo")
        self.actor, self.deterministic = actor.eval(), deterministic

    def select(self, obs: dict) -> np.ndarray:
        d = self.actor.dist(torch.as_tensor(self.spec.obs_matrix(obs))[None])
        a = d.probs.argmax(-1) if self.deterministic else d.sample()
        return a[0].numpy()


def load_policy(run_dir: str, deterministic: bool = True) -> MAPPOPolicy:
    ck = load_checkpoint(run_dir)
    h = {**DEFAULTS, **ck["hparams"]}
    actor = Actor(ck["spec"], h)
    actor.load_state_dict(ck["actor"])
    return MAPPOPolicy(ck["spec"], actor, deterministic)
