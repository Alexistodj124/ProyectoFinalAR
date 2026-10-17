"""Lane-closure incidents (experiment E7 and the web demo).

    penv = IncidentWrapper(penv, {"lane": "NB_C14_C12_1", "start": 600, "end": 1500})
    penv = IncidentWrapper(penv, {"edge": "NB_C14_C12", "start": 600, "end": 1500})
    penv = IncidentWrapper(penv, {"edge": "NB_C14_C12", "lanes": [0, 1], "start": 600, "end": 1500})

Between `start` and `end` (simulation seconds) the lane(s) are closed to `passenger`
with traci.lane.setDisallowed, and their original permissions are restored afterwards.
With "edge" and no "lanes", every THROUGH lane but the leftmost one is closed (an accident
that leaves one through lane open). Turn bays stay open, so every route stays valid (closing
the through lanes and leaving only a left-turn bay would leave through traffic with no
connection, and SUMO aborts on "no valid route"). A 1-lane edge is closed completely.
The wrapper is transparent: reset/step/agents/spaces/close and any other attribute go
to the wrapped parallel env.
"""
from __future__ import annotations


def incident_lanes(conn, incident: dict) -> list[str]:
    if "lane" in incident:
        return [incident["lane"]]
    edge = incident["edge"]
    n = conn.edge.getLaneNumber(edge)
    idx = incident.get("lanes")
    if idx is None:
        # through lanes = lanes with a straight ('s') link at the end of the edge
        through = [i for i in range(n) if any(lk[6] == "s" for lk in conn.lane.getLinks(f"{edge}_{i}"))]
        if len(through) >= 2:
            idx = through[:-1]  # keep the leftmost through lane (and any bay) open
        else:
            idx = range(max(1, n - 1))  # no straight movement: keep the leftmost lane open
    return [f"{edge}_{i}" for i in idx]


def close_lanes(conn, lanes: list[str]) -> dict[str, list[str]]:
    """Disallow passenger cars on `lanes`; return the previous disallowed lists."""
    saved = {}
    for ln in lanes:
        saved[ln] = list(conn.lane.getDisallowed(ln))
        conn.lane.setDisallowed(ln, sorted(set(saved[ln]) | {"passenger"}))
    return saved


def open_lanes(conn, saved: dict[str, list[str]]) -> None:
    for ln, dis in saved.items():
        conn.lane.setDisallowed(ln, dis)


class IncidentWrapper:
    def __init__(self, penv, incident: dict):
        self.penv = penv
        self.incident = dict(incident)
        self.start = float(incident.get("start", 0))
        self.end = float(incident.get("end", float("inf")))
        self._saved: dict | None = None
        self.closed_lanes: list[str] = []

    @property
    def _conn(self):
        from env.reforma_env import get_sumo_env

        return get_sumo_env(self.penv).sumo

    @property
    def active(self) -> bool:
        return self._saved is not None

    def _update(self) -> None:
        conn = self._conn
        t = conn.simulation.getTime()
        if self._saved is None and self.start <= t < self.end:
            self.closed_lanes = incident_lanes(conn, self.incident)
            self._saved = close_lanes(conn, self.closed_lanes)
        elif self._saved is not None and t >= self.end:
            open_lanes(conn, self._saved)
            self._saved = None

    def reset(self, seed=None, options=None):
        self._saved = None  # a new simulation starts with the original permissions
        out = self.penv.reset(seed=seed, options=options)
        self._update()
        return out

    def step(self, actions):
        out = self.penv.step(actions)
        if self.penv.agents:  # the simulation is closed once the episode is over
            self._update()
        return out

    def close(self):
        return self.penv.close()

    @property
    def agents(self):
        return self.penv.agents

    @property
    def possible_agents(self):
        return self.penv.possible_agents

    def observation_space(self, agent):
        return self.penv.observation_space(agent)

    def action_space(self, agent):
        return self.penv.action_space(agent)

    def __getattr__(self, name):
        return getattr(self.penv, name)
