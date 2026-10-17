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

``diff-waiting-time-pending-fair`` (E8, PLAN §8.2 last paragraph) adds a starvation term:

    M_t = max over approaches (incoming edges) of the longest wait of a vehicle on it
          (its waiting time accumulated on this intersection's lanes, or its pending time)
    r_t = r_t^pending - fair_lambda * (M_t - M_{t-1}) / 100

Same units as the pending reward: while the head of a starved queue keeps waiting, the agent
pays fair_lambda extra "vehicle-equivalents" per second of delay; when it is served, M drops
and the term is refunded, so it telescopes like the rest of the reward. In the sanity runs
QMIX left a cross street unserved for up to 1573 s: a low-volume approach with a few vehicles
contributes little to the summed waiting time, so the plain reward barely sees it, while M_t
grows by delta_time every step only on that approach. fair_lambda (hparam, default 0.5) makes
the longest-waiting vehicle count 1.5 times. Sanity (seed 0, 50 episodes, reforma_pico, EVAL seeds
1000-1002): comm's worst cross-street wait fell from 1269 s to 430 s (lambda 1) / 268 s (lambda
0.5); with QMIX lambda 0.5 was better than lambda 1 and than the plain reward on every metric.
See experiments/configs/README.md (E8).
"""
from __future__ import annotations

import functools

DEFAULT_TRAIN_REWARD = "diff-waiting-time-pending"


def diff_waiting_time_pending(ts) -> float:
    """sumo-rl reward function (receives the sumo_rl TrafficSignal)."""
    lane_wait = sum(ts.get_accumulated_waiting_time_per_lane())
    if not hasattr(ts, "_pending_edges"):  # TrafficSignal objects are rebuilt on every reset
        ts._pending_edges = sorted({lane.rsplit("_", 1)[0] for lane in ts.lanes})
        ts._pending_since = {}
        ts._last_total_wait = 0.0
    now = float(ts.env.sim_step)
    pending, edge_of = set(), {}
    for edge in ts._pending_edges:
        for v in ts.sumo.edge.getPendingVehicles(edge):
            pending.add(v)
            edge_of[v] = edge
    ts._pending_edge_of = edge_of  # used by the fairness variant (max wait per approach)
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


DEFAULT_FAIR_LAMBDA = 0.5


def max_wait_per_approach(ts) -> dict[str, float]:
    """Longest wait [s] of a vehicle on each incoming edge of the intersection.

    Lane part: the per-lane accumulated waiting time that sumo-rl keeps in ts.env.vehicles
    (filled by get_accumulated_waiting_time_per_lane), summed over this intersection's lanes, so
    waits at upstream intersections do not count. Pending part: the time since it was first seen
    pending (needs diff_waiting_time_pending to have run in this step).
    """
    lanes = set(ts.lanes)
    out: dict[str, float] = {}
    vehicles = getattr(ts.env, "vehicles", {})
    for lane in ts.lanes:
        edge = lane.rsplit("_", 1)[0]
        best = out.get(edge, 0.0)
        for v in ts.sumo.lane.getLastStepVehicleIDs(lane):
            w = sum(t for ln, t in vehicles.get(v, {}).items() if ln in lanes)
            best = max(best, float(w))
        out[edge] = best
    now = float(ts.env.sim_step)
    for v, edge in getattr(ts, "_pending_edge_of", {}).items():
        w = now - ts._pending_since.get(v, now)
        out[edge] = max(out.get(edge, 0.0), w)
    return out


def diff_waiting_time_pending_fair(ts, fair_lambda: float = DEFAULT_FAIR_LAMBDA) -> float:
    """diff-waiting-time-pending minus fair_lambda * increase of the max per-approach wait / 100."""
    base = diff_waiting_time_pending(ts)
    m = max(max_wait_per_approach(ts).values(), default=0.0) / 100.0
    last = getattr(ts, "_last_max_wait", 0.0)
    ts._last_max_wait = m
    return base - fair_lambda * (m - last)


REWARD_FNS = {
    "diff-waiting-time-pending": diff_waiting_time_pending,
    "diff-waiting-time-pending-fair": diff_waiting_time_pending_fair,
}


def train_env_kwargs(hparams: dict | None = None) -> dict:
    """Extra make_parallel_env / make_gym_env kwargs for TRAINING envs.

    hparams["reward_fn"]: "diff-waiting-time-pending" (default), "diff-waiting-time-pending-fair"
    (uses hparams["fair_lambda"], default DEFAULT_FAIR_LAMBDA) or "scenario" (keep the scenario's
    reward_fn, i.e. plain sumo-rl diff-waiting-time).
    """
    hparams = hparams or {}
    name = hparams.get("reward_fn", DEFAULT_TRAIN_REWARD)
    if not name or name == "scenario":
        return {}
    fn = REWARD_FNS[name]
    if fn is diff_waiting_time_pending_fair:
        fn = functools.partial(diff_waiting_time_pending_fair, fair_lambda=float(hparams.get("fair_lambda", DEFAULT_FAIR_LAMBDA)))
    return {"reward_fn": fn}
