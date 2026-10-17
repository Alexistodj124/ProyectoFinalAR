"""Validation of the Reforma corridor against a reference travel time (PLAN §6.2).

    python -m env.validate                                  # fixed-time, reforma_pico, seeds 1000-1002, 3600 s
    python -m env.validate --program actuated --seeds 0 1 2
    python -m env.validate --scenario reforma_pico_x13      # stress profile (no reference check)

Runs the baseline program, reads the tripinfo output and compares the simulated travel
time of vehicles that drive the WHOLE corridor (Plaza Obelisco <-> 5a calle) with the
"Google Maps" reference below. It also checks that the demand is realistic and not
gridlocked (the calibration criteria of env/conteos/README.md):

* travel time within +-15 % of REFERENCE_S in both directions (only for reforma_pico);
* teleports < 1 % of the inserted vehicles;
* insertion backlog (vehicles of the route file that SUMO could not insert by the end,
  because their entry edge was full) < 2 % of the loaded vehicles;
* queues that build and clear: reported as the ratio between the halted vehicles of the
  last 10 min and those around mid-hour (a permanent spillback keeps growing; the
  calibrated peak gives ~1.2-1.3, i.e. near-capacity queues that stay inside the links).

REFERENCE_S is a PLACEHOLDER: replace it with the typical travel time Google Maps shows
for the same stretch at the counted hour (e.g. weekday 7:00-8:00), one value per
direction, and note the date of the query here.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# PLACEHOLDER (not measured yet): ~1.65 km at ~18 km/h in the morning peak.
REFERENCE_S = {"NB": 330.0, "SB": 300.0}
REFERENCE_SOURCE = "PLACEHOLDER - reemplazar por Google Maps (dia/hora de la consulta)"
FULL_TRIPS = {"NB": ("NB_S_C15", "NB_C06_N"), "SB": ("SB_N_C06", "SB_C15_S")}
TOLERANCE = {"tt": 0.15, "teleports": 0.01, "backlog": 0.02}
DEFAULT_SEEDS = [1000, 1001, 1002]  # first EVAL_SEEDS, the ones of the README tables


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


def trip_stats(tripinfo: str | Path) -> dict:
    """Inserted vehicles (SUMO only writes a tripinfo for inserted ones) and mean waiting time."""
    waits = [float(t.get("waitingTime", 0)) for t in ET.parse(tripinfo).getroot().iter("tripinfo")]
    return {"inserted": len(waits), "mean_wait": sum(waits) / len(waits) if waits else float("nan")}


def loaded_vehicles(route_file: str | Path, num_seconds: float) -> int:
    """Vehicles of the route file that should have departed within [0, num_seconds)."""
    deps = re.findall(r'<vehicle [^>]*depart="([0-9.]+)"', Path(route_file).read_text())
    return sum(float(d) < num_seconds for d in deps)


def run(scenario="reforma_pico", seed=0, program="fixed", num_seconds=3600, workdir=None) -> dict:
    from env.reforma_env import get_sumo_env, make_parallel_env

    trip = Path(workdir or tempfile.mkdtemp()) / f"validate_{scenario}_{program}_s{seed}_tripinfo.xml"
    penv = make_parallel_env(scenario, seed, num_seconds=num_seconds, fixed_ts=True, program=program,
                             tripinfo_path=str(trip))
    penv.reset(seed=seed)
    se = get_sumo_env(penv)
    route_file = se._route
    t0, teleports, info, halting = time.time(), 0, {}, {}
    while penv.agents:
        _, _, _, trunc, info = penv.step({a: 0 for a in penv.agents})
        conn = se.sumo
        teleports += conn.simulation.getStartingTeleportNumber()
        now = int(conn.simulation.getTime())
        if now % 60 == 0:
            halting[now] = sum(conn.vehicle.getSpeed(v) < 0.1 for v in conn.vehicle.getIDList())
        if all(trunc.values()):
            break
    wall = time.time() - t0
    info = next(iter(info.values()), {})
    penv.close()
    tt = corridor_times(trip)
    ts = trip_stats(trip)
    loaded = loaded_vehicles(route_file, num_seconds)
    mid = [h for t, h in halting.items() if num_seconds / 2 - 300 <= t < num_seconds / 2 + 300]
    end = [h for t, h in halting.items() if t >= num_seconds - 600]
    return {"wall_s": wall, "sim_speed": num_seconds / wall, "tt": tt, "teleports": teleports,
            "inserted": ts["inserted"], "loaded": loaded, "backlog": max(0, loaded - ts["inserted"]),
            "mean_wait": ts["mean_wait"], "system_mean_waiting_time": info.get("system_mean_waiting_time"),
            "halting_mid": sum(mid) / max(1, len(mid)), "halting_end": sum(end) / max(1, len(end)),
            "tripinfo": str(trip)}


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="reforma_pico")
    ap.add_argument("--program", default="fixed", choices=["fixed", "actuated"])
    ap.add_argument("--seeds", type=int, nargs="+", default=DEFAULT_SEEDS)
    ap.add_argument("--num-seconds", type=int, default=3600)
    ap.add_argument("--no-libsumo", action="store_true")
    a = ap.parse_args(argv)
    if not a.no_libsumo and "traci" not in sys.modules:
        os.environ.setdefault("LIBSUMO_AS_TRACI", "1")  # must be set before sumo_rl/traci are imported
    # the reference is matched by the "measured" fixed-time plan; other programs are only reported
    check_tt = a.scenario == "reforma_pico" and a.program == "fixed" and a.num_seconds >= 3600
    print(f"{a.scenario} / {a.program} / {a.num_seconds} s. Referencia: {REFERENCE_SOURCE}")
    print(f"{'seed':>5} {'NB [s]':>7} {'SB [s]':>7} {'n NB/SB':>9} {'espera':>7} {'insert.':>8} "
          f"{'backlog':>8} {'telep.':>7} {'cola mitad/fin':>15}")
    rows = []
    for s in a.seeds:
        r = run(a.scenario, s, a.program, a.num_seconds)
        rows.append(r)
        nb, sb = _mean(r["tt"]["NB"]), _mean(r["tt"]["SB"])
        print(f"{s:>5} {nb:>7.1f} {sb:>7.1f} {len(r['tt']['NB']):>4}/{len(r['tt']['SB']):<4} {r['mean_wait']:>7.1f} "
              f"{r['inserted']:>8} {r['backlog'] / max(1, r['loaded']):>8.2%} {r['teleports']:>7} "
              f"{r['halting_mid']:>7.0f}/{r['halting_end']:<7.0f}")
    tt = {d: _mean([_mean(r["tt"][d]) for r in rows if r["tt"][d]]) for d in FULL_TRIPS}
    backlog = sum(r["backlog"] for r in rows) / max(1, sum(r["loaded"] for r in rows))
    tele = sum(r["teleports"] for r in rows) / max(1, sum(r["inserted"] for r in rows))
    ok = backlog < TOLERANCE["backlog"] and tele < TOLERANCE["teleports"]
    grow = _mean([r["halting_end"] / max(1.0, r["halting_mid"]) for r in rows])
    print(f"media: NB {tt['NB']:.1f} s, SB {tt['SB']:.1f} s, espera {_mean([r['mean_wait'] for r in rows]):.1f} s, "
          f"backlog {backlog:.2%} (<2 %), teletransportes {tele:.2%} (<1 %), cola fin/mitad {grow:.2f}")
    if check_tt:
        for d in FULL_TRIPS:
            err = (tt[d] - REFERENCE_S[d]) / REFERENCE_S[d]
            ok &= abs(err) <= TOLERANCE["tt"]
            print(f"  {d}: {tt[d]:.1f} s vs referencia {REFERENCE_S[d]:.0f} s ({err:+.1%}, tolerancia +-15 %)")
    print("CALIBRACION OK" if ok else "FUERA DE CRITERIO (ver env/conteos/README.md)")
    return rows


if __name__ == "__main__":
    main()
