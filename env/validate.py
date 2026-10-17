"""Validation of the Reforma corridor against a reference travel time (PLAN §6.2).

    python -m env.validate                    # fixed-time, reforma_pico, seed 0, 3600 s
    python -m env.validate --program actuated --seeds 0 1 2

Runs the baseline program, reads the tripinfo output and compares the simulated travel
time of vehicles that drive the WHOLE corridor (Plaza Obelisco <-> 5a calle) with the
"Google Maps" reference below.

REFERENCE_S is a PLACEHOLDER: replace it with the typical travel time Google Maps shows
for the same stretch at the counted hour (e.g. weekday 7:00-8:00), one value per
direction, and note the date of the query here.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# PLACEHOLDER (not measured yet): ~1.65 km at ~18 km/h in the morning peak.
REFERENCE_S = {"NB": 330.0, "SB": 300.0}
REFERENCE_SOURCE = "PLACEHOLDER - reemplazar por Google Maps (dia/hora de la consulta)"
FULL_TRIPS = {"NB": ("NB_S_C15", "NB_C06_N"), "SB": ("SB_N_C06", "SB_C15_S")}


def corridor_times(tripinfo: str | Path) -> dict[str, list[float]]:
    out = {d: [] for d in FULL_TRIPS}
    for t in ET.parse(tripinfo).getroot().iter("tripinfo"):
        if float(t.get("arrival", -1)) < 0:  # unfinished
            continue
        dep, arr = t.get("departLane").rsplit("_", 1)[0], t.get("arrivalLane").rsplit("_", 1)[0]
        for d, (a, b) in FULL_TRIPS.items():
            if dep == a and arr == b:
                out[d].append(float(t.get("duration")))
    return out


def run(scenario="reforma_pico", seed=0, program="fixed", num_seconds=3600, workdir=None) -> dict:
    from env.reforma_env import get_sumo_env, make_parallel_env

    trip = Path(workdir or tempfile.mkdtemp()) / f"validate_{scenario}_{program}_s{seed}_tripinfo.xml"
    penv = make_parallel_env(scenario, seed, num_seconds=num_seconds, fixed_ts=True, program=program,
                             tripinfo_path=str(trip))
    penv.reset(seed=seed)
    se = get_sumo_env(penv)
    t0, teleports, info = time.time(), 0, {}
    while penv.agents:
        _, _, _, trunc, info = penv.step({a: 0 for a in penv.agents})
        teleports += se.sumo.simulation.getStartingTeleportNumber()
        if all(trunc.values()):
            break
    wall = time.time() - t0
    info = next(iter(info.values()), {})
    penv.close()
    tt = corridor_times(trip)
    return {"wall_s": wall, "sim_speed": num_seconds / wall, "tt": tt, "teleports": teleports,
            "mean_wait": info.get("system_mean_waiting_time"), "tripinfo": str(trip)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="reforma_pico")
    ap.add_argument("--program", default="fixed", choices=["fixed", "actuated"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[0])
    ap.add_argument("--num-seconds", type=int, default=3600)
    ap.add_argument("--no-libsumo", action="store_true")
    a = ap.parse_args(argv)
    if not a.no_libsumo and "traci" not in sys.modules:
        os.environ.setdefault("LIBSUMO_AS_TRACI", "1")  # must be set before sumo_rl/traci are imported
    print(f"Referencia: {REFERENCE_SOURCE}")
    print(f"{'seed':>4} {'dir':>3} {'n':>4} {'sim [s]':>8} {'ref [s]':>8} {'error':>7}   sim-s/wall-s  teleports")
    for s in a.seeds:
        r = run(a.scenario, s, a.program, a.num_seconds)
        for d, xs in r["tt"].items():
            m = sum(xs) / len(xs) if xs else float("nan")
            err = (m - REFERENCE_S[d]) / REFERENCE_S[d]
            print(f"{s:>4} {d:>3} {len(xs):>4} {m:>8.1f} {REFERENCE_S[d]:>8.1f} {err:>+7.1%}   "
                  f"{r['sim_speed']:>10.0f}  {r['teleports']:>9}")
    return r


if __name__ == "__main__":
    main()
