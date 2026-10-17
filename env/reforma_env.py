"""Environment factory shared by training, evaluation and the web demo.

Minimal working version on main (toy scenarios with static routes). The
feat/env-reforma branch adds generated demand (env.demand), fixed/actuated
programs for Reforma and incidents (env.incidents) WITHOUT changing signatures.
"""
from __future__ import annotations

from pathlib import Path

import gymnasium as gym
import sumo_rl
from sumo_rl.environment.env import SumoEnvironment

from env.scenarios import Scenario, get_scenario


class _ArgList(str):
    """sumo-rl does additional_sumo_cmd.split(); this keeps paths with spaces intact
    (the repo lives under 'Proyecto Final/')."""

    def __new__(cls, args):
        obj = super().__new__(cls, " ".join(map(str, args)))
        obj._args = [str(a) for a in args]
        return obj

    def split(self, *_, **__):
        return list(self._args)


def _route_for(sc: Scenario, seed: int) -> str:
    if sc.route_file:
        return sc.route_file
    from env.demand import routes_for  # provided by feat/env-reforma

    return routes_for(sc, seed)


def get_sumo_env(env) -> SumoEnvironment:
    """Return the underlying sumo_rl.SumoEnvironment of any env built here."""
    e = env
    for _ in range(10):
        if isinstance(e, SumoEnvironment):
            return e
        for attr in ("sumo_env", "penv", "aec_env", "env"):
            if hasattr(e, attr):
                e = getattr(e, attr)
                break
        else:
            e = getattr(e, "unwrapped", e)
            if isinstance(e, SumoEnvironment):
                return e
            raise TypeError(f"no SumoEnvironment inside {type(env)}")
    raise TypeError(f"no SumoEnvironment inside {type(env)}")


class _DemandReseedWrapper:
    """Parallel-env wrapper: reset(seed=k) regenerates the demand for seed k when the
    scenario's demand is generated, so every training episode can see a different
    (but reproducible) realization of the same profile."""

    def __init__(self, penv, scenario: Scenario, seed: int):
        self.penv = penv
        self.scenario = scenario
        self.seed = seed

    def reset(self, seed=None, options=None):
        s = self.seed if seed is None else seed
        se = get_sumo_env(self.penv)
        if not self.scenario.route_file:
            se._route = _route_for(self.scenario, s)
        return self.penv.reset(seed=s, options=options)

    def step(self, actions):
        # With fixed_ts the actions are ignored, but sumo-rl's parallel wrapper raises
        # KeyError on {} / None: fill dummy actions so every consumer can pass {}.
        if not actions:
            actions = {a: 0 for a in self.penv.agents}
        return self.penv.step(actions)

    def __getattr__(self, name):
        return getattr(self.penv, name)


def make_parallel_env(
    scenario: str | Scenario,
    seed: int = 0,
    *,
    num_seconds: int | None = None,
    fixed_ts: bool = False,
    program: str | None = None,
    tripinfo_path: str | None = None,
    emissions: bool = False,
    incident: dict | None = None,
    use_gui: bool = False,
    out_csv: str | None = None,
    **overrides,
):
    sc = get_scenario(scenario)
    add: list[str] = []
    if tripinfo_path:
        Path(tripinfo_path).parent.mkdir(parents=True, exist_ok=True)
        add += ["--tripinfo-output", tripinfo_path, "--tripinfo-output.write-unfinished", "true"]
    if emissions:
        add += ["--device.emissions.probability", "1"]
    if incident:
        # a closed lane can leave some already-planned route without connection: drop that
        # vehicle with a warning instead of aborting the whole simulation
        add += ["--ignore-route-errors", "true"]
    if fixed_ts and program in ("fixed", "actuated"):
        f = sc.fixed_additional if program == "fixed" else sc.actuated_additional
        if f and Path(f).exists():
            add += ["--additional-files", f]
    kwargs = dict(
        net_file=sc.net_file,
        route_file=_route_for(sc, seed),
        num_seconds=num_seconds or sc.num_seconds,
        begin_time=sc.begin_time,
        delta_time=sc.delta_time,
        yellow_time=sc.yellow_time,
        min_green=sc.min_green,
        max_green=sc.max_green,
        reward_fn=sc.reward_fn,
        sumo_seed=seed,
        fixed_ts=fixed_ts,
        sumo_warnings=False,
        use_gui=use_gui,
        out_csv_name=out_csv,
        time_to_teleport=300,
        additional_sumo_cmd=_ArgList(add) if add else None,
    )
    kwargs.update(overrides)
    env = _DemandReseedWrapper(sumo_rl.parallel_env(**kwargs), sc, seed)
    if incident:
        from env.incidents import IncidentWrapper  # provided by feat/env-reforma

        env = IncidentWrapper(env, incident)
    return env


class SingleAgentGym(gym.Env):
    """Gymnasium view of a 1-TLS parallel env (for SB3 and single-agent code)."""

    metadata = {"render_modes": []}

    def __init__(self, penv):
        self.penv = penv
        agents = penv.possible_agents
        assert len(agents) == 1, f"make_gym_env needs a 1-TLS scenario, got {agents}"
        self.agent = agents[0]
        self.observation_space = penv.observation_space(self.agent)
        self.action_space = penv.action_space(self.agent)

    def reset(self, seed=None, options=None):
        obs, info = self.penv.reset(seed=seed, options=options)
        return obs[self.agent], info.get(self.agent, {})

    def step(self, action):
        obs, rew, term, trunc, info = self.penv.step({self.agent: int(action)})
        a = self.agent
        return obs[a], float(rew[a]), bool(term[a]), bool(trunc[a]), info.get(a, {})

    def close(self):
        self.penv.close()

    @property
    def sumo_env(self):
        return get_sumo_env(self.penv)


def make_gym_env(scenario: str | Scenario, seed: int = 0, **kw) -> SingleAgentGym:
    return SingleAgentGym(make_parallel_env(scenario, seed, **kw))
