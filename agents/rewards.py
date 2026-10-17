"""Training reward used by every learner (single agent and MARL).

sumo-rl's ``diff-waiting-time`` is r_t = -(W_t - W_{t-1}) / 100, with W_t the waiting
time accumulated by the vehicles that are currently ON the incoming lanes of the
intersection. Vehicles that SUMO cannot insert because their entry lane is full are
invisible to it. On the calibrated Reforma peak this is a loophole: a learner can keep
one approach full (its penalty is bounded by the lane capacity) while the rest of its
demand piles up outside the network at zero cost. In the sanity runs DQN, PPO, Q-Learning
and IDQN all learned to do that (5-13 % of the peak demand never entered the network),
which makes their mean waiting time per *inserted* vehicle look very good while the total
delay is 3-4x the fixed-time plan's (docs/ajuste_aprendizaje.md).

``diff-waiting-time-pending`` closes it: vehicles waiting to be inserted on an entry edge
of the intersection (TraCI ``edge.getPendingVehicles``) also accumulate waiting time, so

    W_t = sum_{v on incoming lanes} acc_wait(v) + sum_{v pending on incoming edges} (t - t_v)
    r_t = -(W_t - W_{t-1}) / 100

where t_v is the step in which v was first seen pending. Its pending time is "refunded"
when it is inserted, exactly like the lane waiting time of a vehicle that crosses the stop
line, so both parts follow the same telescoping logic. On intersections without pending
vehicles (no backlog, toy nets, inner corridor intersections) it equals diff-waiting-time.
Evaluation is unchanged: it uses the tripinfo metrics, never the reward.
"""
from __future__ import annotations

DEFAULT_TRAIN_REWARD = "diff-waiting-time-pending"


def diff_waiting_time_pending(ts) -> float:
    """sumo-rl reward function (receives the sumo_rl TrafficSignal)."""
    lane_wait = sum(ts.get_accumulated_waiting_time_per_lane())
    if not hasattr(ts, "_pending_edges"):  # TrafficSignal objects are rebuilt on every reset
        ts._pending_edges = sorted({lane.rsplit("_", 1)[0] for lane in ts.lanes})
        ts._pending_since = {}
        ts._last_total_wait = 0.0
    now = float(ts.env.sim_step)
    pending = set()
    for edge in ts._pending_edges:
        pending.update(ts.sumo.edge.getPendingVehicles(edge))
    since = ts._pending_since
    for v in list(since):
        if v not in pending:
            del since[v]  # inserted: its outside waiting time is refunded (as at the stop line)
    for v in pending:
        since.setdefault(v, now)
    total = (lane_wait + sum(now - t for t in since.values())) / 100.0
    reward = ts._last_total_wait - total
    ts._last_total_wait = total
    return reward


REWARD_FNS = {"diff-waiting-time-pending": diff_waiting_time_pending}


def train_env_kwargs(hparams: dict | None = None) -> dict:
    """Extra make_parallel_env / make_gym_env kwargs for TRAINING envs.

    hparams["reward_fn"]: "diff-waiting-time-pending" (default) or "scenario" (keep the
    scenario's reward_fn, i.e. plain sumo-rl diff-waiting-time).
    """
    name = (hparams or {}).get("reward_fn", DEFAULT_TRAIN_REWARD)
    if not name or name == "scenario":
        return {}
    return {"reward_fn": REWARD_FNS[name]}
