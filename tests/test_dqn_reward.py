"""Training reward diff-waiting-time-pending (agents/rewards.py), used by every learner."""
from types import SimpleNamespace

import pytest

import functools

from agents.rewards import (
    DEFAULT_FAIR_LAMBDA,
    DEFAULT_TRAIN_REWARD,
    REWARD_FNS,
    diff_waiting_time_pending,
    diff_waiting_time_pending_fair,
    max_wait_per_approach,
    train_env_kwargs,
)


class _FakeTS:
    """Minimal stand-in for a sumo_rl TrafficSignal."""

    def __init__(self):
        self.lanes = ["in_A_0", "in_A_1", "in_B_0"]
        self.lane_wait = [0.0, 0.0, 0.0]
        self.pending = {"in_A": [], "in_B": []}
        self.on_lane = {lane: [] for lane in self.lanes}
        self.env = SimpleNamespace(sim_step=0.0, vehicles={})  # sumo-rl: vehicles[veh][lane] = wait on that lane
        self.sumo = SimpleNamespace(edge=SimpleNamespace(getPendingVehicles=lambda e: list(self.pending[e])),
                                    lane=SimpleNamespace(getLastStepVehicleIDs=lambda ln: list(self.on_lane[ln])))

    def get_accumulated_waiting_time_per_lane(self):
        return list(self.lane_wait)


def test_equals_diff_waiting_time_without_backlog():
    ts = _FakeTS()
    ts.lane_wait = [100.0, 50.0, 0.0]
    assert diff_waiting_time_pending(ts) == pytest.approx(-1.5)
    ts.env.sim_step, ts.lane_wait = 5.0, [100.0, 50.0, 50.0]
    assert diff_waiting_time_pending(ts) == pytest.approx(-0.5)
    ts.env.sim_step, ts.lane_wait = 10.0, [0.0, 0.0, 0.0]  # everybody crossed: refund
    assert diff_waiting_time_pending(ts) == pytest.approx(2.0)


def test_pending_vehicles_accumulate_and_are_refunded():
    ts = _FakeTS()
    assert diff_waiting_time_pending(ts) == 0.0
    ts.pending["in_A"] = ["v1", "v2"]  # first seen pending at t=5
    ts.env.sim_step = 5.0
    assert diff_waiting_time_pending(ts) == 0.0
    ts.env.sim_step = 10.0  # 2 vehicles x 5 s outside the network
    assert diff_waiting_time_pending(ts) == pytest.approx(-0.10)
    ts.env.sim_step = 15.0
    assert diff_waiting_time_pending(ts) == pytest.approx(-0.10)
    ts.pending["in_A"] = ["v2"]  # v1 inserted: its 10 s are refunded, v2 adds 5 s
    ts.env.sim_step = 20.0
    assert diff_waiting_time_pending(ts) == pytest.approx(0.10 - 0.05)
    ts.pending["in_A"] = []  # v2 inserted after 15 s
    ts.env.sim_step = 25.0
    assert diff_waiting_time_pending(ts) == pytest.approx(0.15)


def test_train_env_kwargs():
    assert train_env_kwargs({})["reward_fn"] is diff_waiting_time_pending
    assert train_env_kwargs(None)["reward_fn"] is diff_waiting_time_pending
    assert train_env_kwargs({"reward_fn": "scenario"}) == {}
    assert DEFAULT_TRAIN_REWARD == "diff-waiting-time-pending"


def test_max_wait_per_approach_lane_and_pending():
    ts = _FakeTS()
    ts.on_lane = {"in_A_0": ["a1", "a2"], "in_A_1": [], "in_B_0": ["b1"]}
    # a1 also waited on a lane of ANOTHER intersection ("up_0"): that part must not count
    ts.env.vehicles = {"a1": {"in_A_0": 30.0, "up_0": 500.0}, "a2": {"in_A_0": 10.0}, "b1": {"in_B_0": 70.0}}
    ts.pending["in_A"] = ["p1"]
    diff_waiting_time_pending(ts)  # t=0: p1 first seen pending
    ts.env.sim_step = 100.0
    diff_waiting_time_pending(ts)
    assert max_wait_per_approach(ts) == {"in_A": 100.0, "in_B": 70.0}  # pending p1 waited 100 s


def test_fair_reward_penalizes_increase_of_the_max_wait():
    ts = _FakeTS()
    ts.on_lane["in_B_0"] = ["b1"]
    ts.env.vehicles = {"b1": {"in_B_0": 0.0}}
    assert diff_waiting_time_pending_fair(ts, fair_lambda=0.5) == 0.0
    # b1 (alone on the cross street) waits 5 s more: plain = -0.05; fair adds -0.5 * 5 / 100
    ts.env.sim_step, ts.lane_wait, ts.env.vehicles["b1"]["in_B_0"] = 5.0, [0.0, 0.0, 5.0], 5.0
    assert diff_waiting_time_pending_fair(ts, fair_lambda=0.5) == pytest.approx(-0.05 - 0.025)
    ts.env.sim_step, ts.lane_wait, ts.env.vehicles["b1"]["in_B_0"] = 10.0, [0.0, 0.0, 10.0], 10.0
    assert diff_waiting_time_pending_fair(ts, fair_lambda=0.5) == pytest.approx(-0.05 - 0.025)
    # b1 is served: both terms are refunded (telescoping)
    ts.env.sim_step, ts.lane_wait, ts.on_lane["in_B_0"] = 15.0, [0.0, 0.0, 0.0], []
    assert diff_waiting_time_pending_fair(ts, fair_lambda=0.5) == pytest.approx(0.10 + 0.05)


def test_fair_reward_with_zero_lambda_equals_pending():
    a, b = _FakeTS(), _FakeTS()
    for t, waits in ((0.0, [10.0, 0.0, 0.0]), (5.0, [20.0, 5.0, 0.0]), (10.0, [0.0, 5.0, 40.0])):
        for ts in (a, b):
            ts.env.sim_step, ts.lane_wait = t, list(waits)
        assert diff_waiting_time_pending_fair(a, fair_lambda=0.0) == pytest.approx(diff_waiting_time_pending(b))


def test_fair_reward_registration_and_lambda_hparam():
    assert REWARD_FNS["diff-waiting-time-pending-fair"] is diff_waiting_time_pending_fair
    fn = train_env_kwargs({"reward_fn": "diff-waiting-time-pending-fair", "fair_lambda": 2.0})["reward_fn"]
    assert isinstance(fn, functools.partial) and fn.func is diff_waiting_time_pending_fair and fn.keywords == {"fair_lambda": 2.0}
    fn = train_env_kwargs({"reward_fn": "diff-waiting-time-pending-fair"})["reward_fn"]
    assert fn.keywords == {"fair_lambda": DEFAULT_FAIR_LAMBDA}


def test_e8_fair_configs_match_their_base_budget():
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[1] / "experiments" / "configs"
    for fair, base in (("E8/qmix_fair.yaml", "E5/qmix.yaml"), ("E8/comm_fair.yaml", "E6/comm.yaml")):
        f, b = (yaml.safe_load((root / p).read_text()) for p in (fair, base))
        assert f["exp"] == "E8" and f["algo"] == b["algo"] and f["scenario"] == b["scenario"]
        assert f["total_episodes"] == b["total_episodes"] and f["eval"] == b["eval"]
        assert f["hparams"]["reward_fn"] == "diff-waiting-time-pending-fair"
        rest = {k: v for k, v in f["hparams"].items() if k not in ("reward_fn", "fair_lambda")}
        assert rest == {k: v for k, v in b["hparams"].items() if k != "reward_fn"}


@pytest.mark.slow
def test_backlog_is_penalized_on_cruce():
    """Holding the cross-street green on the peak builds a Reforma backlog: the training
    reward must see it (plain diff-waiting-time does not)."""
    from env.reforma_env import get_sumo_env, make_parallel_env

    returns, pending = [], []
    for kw in ({}, train_env_kwargs({})):
        env = make_parallel_env("cruce_pico", 0, num_seconds=600, **kw)
        env.reset(seed=0)
        ret, done = 0.0, False
        while not done:
            _, rew, _, trunc, _ = env.step({"C12": 2})
            ret += rew["C12"]
            done = all(trunc.values()) or not env.agents
        pending.append(len(get_sumo_env(env).sumo.simulation.getPendingVehicles()))
        env.close()
        returns.append(ret)
    assert pending[0] == pending[1] > 0  # same simulation, only the reward differs
    assert returns[1] < returns[0]
