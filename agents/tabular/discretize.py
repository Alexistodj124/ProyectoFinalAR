"""State discretization for tabular agents (one intersection).

sumo-rl observation layout per TLS:
    [one-hot green phase (n_green)] + [min_green flag (1)] + [density per lane] + [queue per lane]
The tabular state is  (green phase index, min_green flag, queue level of approach 1, ..., approach A)
with queue level in {0: baja, 1: media, 2: alta}. An *approach* is an incoming edge (lane id
without its trailing "_k"), so the state space is n_green x 2 x 3^A for any intersection
(4 phases, 4 approaches -> 4 x 2 x 81 = 648 states). Q-tables are dicts, so only visited
states take memory.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

LEVELS = ("baja", "media", "alta")
DEFAULT_THRESHOLDS = (0.15, 0.45)  # queue fraction: < 0.15 baja, < 0.45 media, else alta


def lane_groups_by_edge(lanes: list[str]) -> list[list[int]]:
    """Indices of `lanes` grouped by incoming edge, in first-appearance order."""
    groups: dict[str, list[int]] = {}
    for i, lane in enumerate(lanes):
        edge = lane.rsplit("_", 1)[0]
        groups.setdefault(edge, []).append(i)
    return list(groups.values())


@dataclass
class Discretizer:
    n_green: int
    groups: list[list[int]]  # lane indices per approach
    thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS
    agg: str = "mean"  # how lanes of one approach are combined: "mean" | "max"

    @classmethod
    def from_ts(cls, ts, thresholds=DEFAULT_THRESHOLDS, agg: str = "mean") -> "Discretizer":
        """Build from a sumo_rl TrafficSignal (uses .lanes and .num_green_phases)."""
        return cls(int(ts.num_green_phases), lane_groups_by_edge(list(ts.lanes)), tuple(thresholds), agg)

    @property
    def n_lanes(self) -> int:
        return sum(len(g) for g in self.groups)

    @property
    def n_approaches(self) -> int:
        return len(self.groups)

    @property
    def n_levels(self) -> int:
        return len(self.thresholds) + 1

    @property
    def n_states_total(self) -> int:
        return self.n_green * 2 * self.n_levels**self.n_approaches

    def level(self, q: float) -> int:
        return int(np.searchsorted(self.thresholds, q, side="right"))

    def encode(self, obs: np.ndarray) -> tuple[int, ...]:
        """obs vector -> hashable state tuple (phase, min_green flag, level per approach)."""
        obs = np.asarray(obs)
        phase = int(np.argmax(obs[: self.n_green]))
        flag = int(obs[self.n_green] > 0.5)
        q0 = self.n_green + 1 + self.n_lanes  # queues start after densities
        reduce = np.max if self.agg == "max" else np.mean
        levels = tuple(self.level(float(reduce(obs[[q0 + j for j in g]]))) for g in self.groups)
        return (phase, flag, *levels)
