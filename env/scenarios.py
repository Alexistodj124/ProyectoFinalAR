"""Scenario registry: the single source of truth for (network, demand) pairs.

Every training/evaluation/web component refers to scenarios by name, e.g.
``get_scenario("reforma_pico")``. Demand is stochastic per seed: route files are
produced by ``env.demand.routes_for(scenario, seed)`` (see docs/ARCHITECTURE.md).

Toy scenarios use the nets shipped with sumo-rl, so algorithms can be developed
before the Reforma network exists.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import sumo_rl

REPO_ROOT = Path(__file__).resolve().parents[1]
SUMO_RL_NETS = Path(sumo_rl.__file__).resolve().parent / "nets"
NET_DIR = REPO_ROOT / "env" / "net"
ROUTE_DIR = REPO_ROOT / "env" / "routes"

# Demand profiles of PLAN.md section 6.3. scale multiplies the counted flows.
PROFILES = {
    "pico": {"counts": "pico", "scale": 1.0},  # training
    "mediodia": {"counts": "mediodia", "scale": 1.0},  # unseen hour
    "pico_x13": {"counts": "pico", "scale": 1.3},  # stress +30 %
    "noche": {"counts": "pico", "scale": 0.3},  # synthetic night
}

# Seed convention: training, validation and evaluation seeds never overlap.
#   TRAIN_SEEDS: run seeds (the demand of training episode ep of run seed s is
#                experiments.common.episode_seed(s, ep) >= 10_000).
#   VAL_SEEDS:   demand seeds for checkpoint selection (experiments/train.py, E7 seed selection).
#   EVAL_SEEDS:  demand seeds of the final evaluation, never used to choose anything.
TRAIN_SEEDS = [0, 1, 2, 3, 4]
VAL_SEEDS = [2000, 2001, 2002, 2003, 2004]
EVAL_SEEDS = list(range(1000, 1010))


@dataclass(frozen=True)
class Scenario:
    name: str
    net_file: str  # absolute path
    route_file: str | None = None  # static route file; None => generated per seed by env.demand
    profile: str | None = None  # key of PROFILES when demand is generated
    num_seconds: int = 3600
    begin_time: int = 0
    delta_time: int = 5
    yellow_time: int = 3
    min_green: int = 10
    max_green: int = 60
    reward_fn: str = "diff-waiting-time"
    actuated_additional: str | None = None  # additional file with actuated TLS programs (baseline)
    fixed_additional: str | None = None  # additional file with field-measured fixed programs (baseline)
    description: str = ""
    extra: dict = field(default_factory=dict)

    def with_(self, **kw) -> "Scenario":
        return replace(self, **kw)


def _toy(name: str, net: str, rou: str, desc: str, num_seconds: int) -> Scenario:
    return Scenario(
        name=name,
        net_file=str(SUMO_RL_NETS / net),
        route_file=str(SUMO_RL_NETS / rou),
        num_seconds=num_seconds,
        description=desc,
    )


def _reforma(name: str, net: str, profile: str, desc: str) -> Scenario:
    stem = Path(net).stem.replace(".net", "")
    return Scenario(
        name=name,
        net_file=str(NET_DIR / net),
        profile=profile,
        actuated_additional=str(NET_DIR / f"{stem}_actuated.add.xml"),
        fixed_additional=str(NET_DIR / f"{stem}_fixed.add.xml"),
        description=desc,
    )


SCENARIOS: dict[str, Scenario] = {
    # Toy nets for development (exist as soon as sumo-rl is installed).
    "toy_single": _toy(
        "toy_single",
        "single-intersection/single-intersection.net.xml",
        "single-intersection/single-intersection.rou.xml",
        "sumo-rl single intersection (1 TLS)",
        3600,
    ),
    "toy_grid2x2": _toy("toy_grid2x2", "2x2grid/2x2.net.xml", "2x2grid/2x2.rou.xml", "sumo-rl 2x2 grid (4 TLS)", 3600),
}
for _p, _d in [
    ("pico", "hora pico (entrenamiento)"),
    ("mediodia", "mediodía (hora no vista)"),
    ("pico_x13", "hora pico +30 % (estrés)"),
    ("noche", "noche = pico x 0.3"),
]:
    # Full corridor of Av. La Reforma (4–5 TLS): MARL.
    SCENARIOS[f"reforma_{_p}"] = _reforma(f"reforma_{_p}", "reforma.net.xml", _p, f"Corredor Reforma, {_d}")
    # Busiest single intersection cut from the corridor: single-agent algorithms.
    SCENARIOS[f"cruce_{_p}"] = _reforma(f"cruce_{_p}", "cruce.net.xml", _p, f"Cruce más cargado, {_d}")


def get_scenario(name: str | Scenario, **overrides) -> Scenario:
    sc = name if isinstance(name, Scenario) else SCENARIOS[name]
    return sc.with_(**overrides) if overrides else sc


def list_scenarios() -> list[str]:
    return list(SCENARIOS)


@lru_cache(maxsize=None)
def get_topology(net_file: str) -> dict:
    """Order TLS along the corridor's principal axis and link consecutive ones.

    Returns {"order": [tls ids], "neighbors": {tls: [tls,...]}, "xy": {tls: (x, y)}}.
    For a corridor this is exactly the chain of consecutive intersections. For grids
    it gives a chain too (good enough for neighbor-queue features); override in
    env/net/<stem>_topology.json if a scenario needs a different graph.
    """
    import json

    import sumolib

    override = Path(net_file).with_name(Path(net_file).name.replace(".net.xml", "_topology.json"))
    if override.exists():
        return json.loads(override.read_text())
    net = sumolib.net.readNet(net_file, withPrograms=True)
    xy = {}
    for tls in net.getTrafficLights():
        nodes = {c[0].getEdge().getToNode() for c in tls.getConnections()}
        pts = [n.getCoord() for n in nodes] or [(0.0, 0.0)]
        xy[tls.getID()] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    ids = list(xy)
    if len(ids) <= 1:
        return {"order": ids, "neighbors": {i: [] for i in ids}, "xy": xy}
    mx = sum(xy[i][0] for i in ids) / len(ids)
    my = sum(xy[i][1] for i in ids) / len(ids)
    sxx = sum((xy[i][0] - mx) ** 2 for i in ids)
    syy = sum((xy[i][1] - my) ** 2 for i in ids)
    sxy = sum((xy[i][0] - mx) * (xy[i][1] - my) for i in ids)
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)  # principal axis
    ux, uy = math.cos(ang), math.sin(ang)
    order = sorted(ids, key=lambda i: (xy[i][0] - mx) * ux + (xy[i][1] - my) * uy)
    neighbors = {i: [] for i in order}
    for a, b in zip(order, order[1:]):
        neighbors[a].append(b)
        neighbors[b].append(a)
    return {"order": order, "neighbors": neighbors, "xy": xy}


def sumo_home() -> str:
    if "SUMO_HOME" not in os.environ:
        import sumo

        os.environ["SUMO_HOME"] = sumo.SUMO_HOME
    return os.environ["SUMO_HOME"]


sumo_home()
