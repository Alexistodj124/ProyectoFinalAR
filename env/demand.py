"""Demand generation for the Reforma scenarios (contract: docs/ARCHITECTURE.md §3).

Model (the same idea as SUMO's jtrrouter, solved exactly instead of by sampling):
* every boundary edge that enters a signalized crossing is a source; its flow is the
  counted volume of that approach (veh/h, = 4 x vehiculos_15min) x profile scale;
* at every crossing a vehicle on approach `a` takes movement m with probability
  count(a, m) / count(a) (turning ratios from the same counts);
* enumerating all paths gives one route per (source, sequence of turns) with rate
  lambda_r = F_source * prod(turn probabilities). Through traffic on Reforma therefore
  crosses several intersections, and the counted volumes of the downstream approaches
  are reproduced in expectation when the counts are consistent (env/synthetic_counts.py).
* departures of route r are a Poisson process of rate lambda_r: N_r ~ Poisson(lambda_r T)
  and times ~ U(0, T) (equivalent to exponential inter-arrival gaps).

For cruce_* the net only contains one crossing, so only its counts are used.

    routes_for("reforma_pico", seed=0) -> ".../env/routes/cache/reforma_pico_s0_x1.0_<hash>.rou.xml"
    python -m env.demand --static          # seed-0 route files in env/routes/ for netedit/sumo-gui
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
import tempfile
import zlib
from functools import lru_cache
from pathlib import Path

import numpy as np

from env.scenarios import PROFILES, ROUTE_DIR, Scenario, get_scenario

COUNTS_DIR = Path(__file__).resolve().parent / "conteos"
CACHE_DIR = ROUTE_DIR / "cache"
GENERATOR_VERSION = "1"
MOVES = {"s": "recto", "l": "izquierda", "L": "izquierda", "r": "derecha", "R": "derecha"}
VTYPE_XML = ('    <vType id="auto" vClass="passenger" accel="2.6" decel="4.5" sigma="0.5" length="4.5" '
             'minGap="2.5" maxSpeed="16.67" speedFactor="normc(1,0.1,0.8,1.2)"/>\n')


# ----------------------------------------------------------------------------- inputs
def read_counts(profile_counts: str) -> dict[tuple[str, str], dict[str, float]]:
    """{(interseccion, aproximacion): {movimiento: veh/h}} from env/conteos/<name>.csv."""
    out: dict = {}
    path = COUNTS_DIR / f"{profile_counts}.csv"
    with path.open() as fh:
        for r in csv.DictReader(line for line in fh if line.strip() and not line.startswith("#")):
            key = (r["interseccion"].strip(), r["aproximacion"].strip())
            out.setdefault(key, {})[r["movimiento"].strip()] = 4.0 * float(r["vehiculos_15min"])
    return out


def _approach(edge) -> str:
    """Where traffic on `edge` comes from, seen from its downstream node (sur/norte/este/oeste)."""
    shape = edge.getShape()
    (x0, y0), (x1, y1) = shape[-2], shape[-1]
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 360  # travel direction, 0 = east
    return ["oeste", "sur", "este", "norte"][int(((ang + 45) % 360) // 90)]


@lru_cache(maxsize=8)
def _read_net(net_file: str):
    import sumolib

    return sumolib.net.readNet(net_file)


def _out_moves(edge) -> list[tuple[object, str]]:
    """[(next_edge, movimiento)] for every outgoing connection of `edge` (no U-turns)."""
    seen = {}
    for nxt, conns in edge.getOutgoing().items():
        d = MOVES.get(conns[0].getDirection())
        if d:
            seen[nxt] = d
    return list(seen.items())


def route_rates(net_file: str, profile_counts: str, scale: float = 1.0) -> list[tuple[tuple[str, ...], float]]:
    """[(edge ids of route, veh/h)] — exact enumeration of the turning-ratio model."""
    net = _read_net(net_file)
    counts = read_counts(profile_counts)
    tls = {n.getID() for n in net.getNodes() if n.getType().startswith("traffic_light")}
    routes: dict[tuple[str, ...], float] = {}

    def walk(edge, path, p, flow, depth=0):
        node = edge.getToNode()
        options = _out_moves(edge)
        if not options or depth > 40:
            routes[tuple(path)] = routes.get(tuple(path), 0.0) + flow * p
            return
        cnt = counts.get((node.getID(), _approach(edge))) if node.getID() in tls else None
        if cnt:
            w = [(e, cnt.get(m, 0.0) / max(1, sum(1 for _, mm in options if mm == m))) for e, m in options]
        else:  # unsignalized / uncounted: go straight if possible, else split evenly
            straight = [(e, 1.0) for e, m in options if m == "recto"]
            w = straight or [(e, 1.0) for e, _ in options]
        tot = sum(x for _, x in w)
        for e, x in w:
            if x > 0 and e.getID() not in path:
                walk(e, path + [e.getID()], p * x / tot, flow, depth + 1)

    for edge in net.getEdges():
        if edge.getIncoming():  # sources: edges nothing flows into (network boundary)
            continue
        node = edge.getToNode()
        cnt = counts.get((node.getID(), _approach(edge)), {})
        flow = sum(cnt.values()) * scale
        if flow > 0:
            walk(edge, [edge.getID()], 1.0, flow)
    return sorted((r, q) for r, q in routes.items() if q > 1e-9)


# ------------------------------------------------------------------------------ files
def _stable_int(*parts) -> int:
    return zlib.crc32("|".join(map(str, parts)).encode())


def _file_sig(path: str | Path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()[:8]


def write_routes(path: Path, routes, seed: int, horizon: float, stream: int = 0) -> int:
    """Poisson departures for every route over [0, horizon); returns #vehicles."""
    rng = np.random.default_rng([seed, stream])
    deps = []
    for ri, (_, vph) in enumerate(routes):
        n = rng.poisson(vph / 3600.0 * horizon)
        deps += [(t, ri) for t in rng.uniform(0.0, horizon, n)]
    deps.sort()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>\n',
             f"<!-- generated by env/demand.py (seed={seed}, {len(deps)} veh, {horizon:.0f} s) -->\n",
             "<routes>\n", VTYPE_XML]
    lines += [f'    <route id="r{ri}" edges="{" ".join(r)}"/>\n' for ri, (r, _) in enumerate(routes)]
    lines += [f'    <vehicle id="v{k}" type="auto" route="r{ri}" depart="{t:.2f}" departLane="best" '
              f'departSpeed="max"/>\n' for k, (t, ri) in enumerate(deps)]
    lines.append("</routes>\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")  # atomic: parallel workers share the cache
    with os.fdopen(fd, "w") as fh:
        fh.writelines(lines)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
    return len(deps)


def routes_for(scenario: str | Scenario, seed: int, scale: float | None = None) -> str:
    """Path of a cached .rou.xml for (scenario, seed, scale). Deterministic per seed."""
    sc = get_scenario(scenario)
    if sc.route_file:
        return sc.route_file
    prof = PROFILES[sc.profile]
    scale = prof["scale"] if scale is None else float(scale)
    counts_file = COUNTS_DIR / f"{prof['counts']}.csv"
    horizon = sc.begin_time + max(sc.num_seconds, 3600)
    sig = hashlib.md5("|".join([GENERATOR_VERSION, _file_sig(sc.net_file), _file_sig(counts_file),
                                str(horizon)]).encode()).hexdigest()[:8]
    out = CACHE_DIR / f"{sc.name}_s{seed}_x{scale:g}_{sig}.rou.xml"
    if not out.exists():
        routes = route_rates(sc.net_file, prof["counts"], scale)
        write_routes(out, routes, seed, horizon, stream=_stable_int(Path(sc.net_file).name, prof["counts"]))
    return str(out)


# --------------------------------------------------------------------- online (web)
class DemandGenerator:
    """Online demand for the web demo: identical vehicles in every simulation.

    Arrivals of second s are drawn from an RNG seeded with (seed, s), so the vehicles
    injected only depend on (seed, profile at second s) — not on how often spawn() is
    called nor on which simulation calls it. One generator can feed both sims A and B.
    """

    def __init__(self, scenario: str | Scenario, profile: str = "pico", seed: int = 0):
        sc = get_scenario(scenario)
        self.scenario, self.seed = sc, seed
        # union of the routes of every count file, so route ids never change with the profile
        by_counts = {c: dict(route_rates(sc.net_file, c, 1.0)) for c in {p["counts"] for p in PROFILES.values()}}
        self.route_edges = sorted(set().union(*by_counts.values()))
        self._by_counts = by_counts
        self._cursor: dict[int, int] = {}
        self._known: dict[int, set] = {}
        self._inject_n = 0
        self.set_profile(profile)

    def set_profile(self, profile: str) -> None:
        p = PROFILES[profile]
        self.profile = profile
        base = self._by_counts[p["counts"]]
        self.lam = np.array([base.get(r, 0.0) * p["scale"] / 3600.0 for r in self.route_edges])  # veh/s

    def rates(self) -> dict:
        """Current hourly rates: total and per entry edge (veh/h)."""
        by_entry: dict[str, float] = {}
        for r, lam in zip(self.route_edges, self.lam):
            by_entry[r[0]] = by_entry.get(r[0], 0.0) + lam * 3600
        return {"profile": self.profile, "scale": PROFILES[self.profile]["scale"],
                "veh_h": float(self.lam.sum() * 3600), "by_entry": by_entry}

    def arrivals(self, s: int) -> list[tuple[str, int]]:
        """[(vehicle id, route index)] departing at integer second s."""
        n = np.random.default_rng([self.seed, int(s)]).poisson(self.lam)
        return [(f"dg{s}_{ri}_{k}", ri) for ri in np.flatnonzero(n) for k in range(n[ri])]

    def _ensure(self, conn, key):
        known = self._known.setdefault(key, set(conn.route.getIDList()))
        if "auto" not in conn.vehicletype.getIDList():
            conn.vehicletype.copy("DEFAULT_VEHTYPE", "auto")
            conn.vehicletype.setImperfection("auto", 0.5)
        return known

    def _add(self, conn, known, vid, ri):
        rid = f"dg_r{ri}"
        if rid not in known:
            conn.route.add(rid, list(self.route_edges[ri]))
            known.add(rid)
        conn.vehicle.add(vid, rid, typeID="auto", depart="now", departLane="best", departSpeed="max")

    def spawn(self, conn, t: float) -> int:
        """Inject every arrival in (last t, t] through TraCI connection `conn`; returns #added."""
        key = id(conn)
        known = self._ensure(conn, key)
        start, end = self._cursor.get(key, -1) + 1, int(math.floor(t))
        added = 0
        for s in range(start, end + 1):
            for vid, ri in self.arrivals(s):
                self._add(conn, known, vid, ri)
                added += 1
        self._cursor[key] = max(self._cursor.get(key, -1), end)
        return added

    def inject(self, conns, edge: str, n: int) -> list[str]:
        """Web 'inject' command: n vehicles on `edge` (most likely route), same ids in every conn."""
        cand = [(lam, ri) for ri, (r, lam) in enumerate(zip(self.route_edges, self.lam)) if edge in r]
        if not cand:
            return []
        ri = max(cand)[1]
        r = self.route_edges[ri]
        ids = [f"inj{self._inject_n + k}" for k in range(n)]
        self._inject_n += n
        for conn in conns if isinstance(conns, (list, tuple)) else [conns]:
            known = self._ensure(conn, id(conn))
            rid = f"dg_inj_{ri}_{edge}"
            if rid not in known:
                conn.route.add(rid, list(r[r.index(edge):]))
                known.add(rid)
            for vid in ids:
                conn.vehicle.add(vid, rid, typeID="auto", depart="now", departLane="best", departSpeed="max")
        return ids


# ------------------------------------------------------------------------- static
def write_static(seed: int = 0) -> list[Path]:
    """Seed-0 route files for manual use (sumo-gui -n env/net/reforma.net.xml -r env/routes/pico.rou.xml)."""
    out = []
    for prof in PROFILES:
        for prefix, stem in (("reforma", ""), ("cruce", "cruce_")):
            sc = get_scenario(f"{prefix}_{prof}")
            routes = route_rates(sc.net_file, PROFILES[prof]["counts"], PROFILES[prof]["scale"])
            p = ROUTE_DIR / f"{stem}{prof}.rou.xml"
            n = write_routes(p, routes, seed, sc.num_seconds, stream=_stable_int(Path(sc.net_file).name, PROFILES[prof]["counts"]))
            print(f"[demand] {p.relative_to(ROUTE_DIR.parent.parent)}: {len(routes)} routes, {n} veh")
            out.append(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Reforma demand generator")
    ap.add_argument("--static", action="store_true", help="write seed-0 route files to env/routes/")
    ap.add_argument("--scenario", default="reforma_pico")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    if a.static:
        write_static(a.seed)
    else:
        print(routes_for(a.scenario, a.seed))


if __name__ == "__main__":
    main()
