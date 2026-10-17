"""Training reward diff-waiting-time-pending (agents/rewards.py), used by every learner."""
from types import SimpleNamespace

import pytest

from agents.rewards import DEFAULT_TRAIN_REWARD, diff_waiting_time_pending, train_env_kwargs


class _FakeTS:
    """Minimal stand-in for a sumo_rl TrafficSignal."""

    def __init__(self):
        self.lanes = ["in_A_0", "in_A_1", "in_B_0"]
        self.lane_wait = [0.0, 0.0, 0.0]
        self.pending = {"in_A": [], "in_B": []}
        self.env = SimpleNamespace(sim_step=0.0)
        self.sumo = SimpleNamespace(edge=SimpleNamespace(getPendingVehicles=lambda e: list(self.pending[e])))

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
