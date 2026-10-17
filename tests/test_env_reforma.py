"""Reforma scenarios: networks, demand, baseline programs, incidents and the gym view."""
import json
from pathlib import Path

import pytest

from env.scenarios import NET_DIR, SCENARIOS, get_scenario, get_topology

REFORMA = [s for s in SCENARIOS if s.startswith("reforma_")]
CRUCE = [s for s in SCENARIOS if s.startswith("cruce_")]


def _run(penv, actions=None):
    """Step until truncation; return the last info dict of the first agent."""
    info = {}
    while penv.agents:
        act = actions or {a: penv.action_space(a).sample() for a in penv.agents}
        obs, rew, term, trunc, info = penv.step(act)
        for a in obs:
            assert penv.observation_space(a).contains(obs[a]), a
        if all(trunc.values()):
            break
    return next(iter(info.values()), {})


@pytest.mark.parametrize("name", ["reforma_pico", "cruce_pico"])
def test_scenario_runs_300s_random(name):
    from env.reforma_env import get_sumo_env, make_parallel_env

    penv = make_parallel_env(name, seed=0, num_seconds=300)
    obs, _ = penv.reset(seed=0)
    n = len(penv.possible_agents)
    assert (4 <= n <= 5) if name.startswith("reforma") else n == 1
    se = get_sumo_env(penv)
    for a in penv.possible_agents:
        ts = se.traffic_signals[a]
        assert 2 <= ts.num_green_phases <= 4
        # sumo-rl layout: one-hot phase + min_green flag + density + queue per incoming lane
        assert penv.observation_space(a).shape == (ts.num_green_phases + 1 + 2 * len(ts.lanes),)
        assert penv.action_space(a).n == ts.num_green_phases
    _run(penv)
    assert se.sim_step == 300
    assert se.sumo.vehicle.getIDCount() > 0
    penv.close()


@pytest.mark.slow
@pytest.mark.parametrize("name", [s for s in REFORMA + CRUCE if s not in ("reforma_pico", "cruce_pico")])
def test_other_profiles_run_300s(name):
    from env.reforma_env import make_parallel_env

    penv = make_parallel_env(name, seed=1, num_seconds=300)
    penv.reset(seed=1)
    _run(penv)
    penv.close()


def test_network_files_and_topology():
    names = json.loads((NET_DIR / "tls_names.json").read_text())
    topo = get_topology(get_scenario("reforma_pico").net_file)
    assert topo["order"] == ["C15", "C14", "C12", "C10", "C06"]  # south -> north
    assert set(names) == set(topo["order"])
    assert get_topology(get_scenario("cruce_pico").net_file)["order"] == ["C12"]
    for stem in ("reforma", "cruce"):
        for kind in ("fixed", "actuated"):
            assert (NET_DIR / f"{stem}_{kind}.add.xml").exists()


def test_heterogeneous_agents():
    from env.reforma_env import make_parallel_env

    penv = make_parallel_env("reforma_pico", seed=0, num_seconds=60)
    dims = {penv.observation_space(a).shape[0] for a in penv.possible_agents}
    acts = {penv.action_space(a).n for a in penv.possible_agents}
    assert len(dims) > 1 and len(acts) > 1  # different lanes and phases per crossing
    penv.close()


def test_demand_deterministic_per_seed():
    from env.demand import route_rates, routes_for

    a, a2, b = routes_for("reforma_pico", 0), routes_for("reforma_pico", 0), routes_for("reforma_pico", 1)
    assert a == a2 and Path(a).read_text() == Path(a2).read_text()
    assert Path(a).read_text() != Path(b).read_text()
    x13 = routes_for("reforma_pico_x13", 0)
    n = lambda p: Path(p).read_text().count("<vehicle ")  # noqa: E731
    assert 1.15 < n(x13) / n(a) < 1.45
    # total inserted flow = sum of the counted entry approaches; through traffic crosses all 5 TLS
    rr = route_rates(get_scenario("reforma_pico").net_file, "pico")
    assert any(r[0] == "NB_S_C15" and r[-1] == "NB_C06_N" for r, _ in rr)
    cruce = route_rates(get_scenario("cruce_pico").net_file, "pico")
    assert all(len(r) == 2 for r, _ in cruce)


def test_demand_generator_identical_streams():
    from env.demand import DemandGenerator

    g1, g2 = DemandGenerator("cruce_pico", seed=3), DemandGenerator("cruce_pico", seed=3)
    assert [g1.arrivals(s) for s in range(200)] == [g2.arrivals(s) for s in range(200)]
    assert g1.rates()["veh_h"] > 0
    g1.set_profile("noche")
    assert g1.rates()["veh_h"] < g2.rates()["veh_h"]


def test_demand_generator_spawn_traci():
    import traci
    import sumolib

    from env.demand import DemandGenerator

    sc = get_scenario("cruce_pico")
    gen = DemandGenerator(sc, seed=0)
    ids = []
    for label in ("dgA", "dgB"):
        traci.start([sumolib.checkBinary("sumo"), "-n", sc.net_file, "--no-step-log", "--no-warnings"], label=label)
        conn = traci.getConnection(label)
        for t in range(1, 61):
            conn.simulationStep()
            gen.spawn(conn, t)
        ids.append(sorted(conn.vehicle.getIDList()) + sorted(conn.simulation.getArrivedIDList()))
        conn.close()
    assert ids[0] == ids[1] and len(ids[0]) > 10


@pytest.mark.parametrize("program", ["fixed", "actuated"])
def test_baseline_program_active(program):
    from env.reforma_env import get_sumo_env, make_parallel_env

    penv = make_parallel_env("reforma_pico", seed=0, num_seconds=60, fixed_ts=True, program=program)
    penv.reset(seed=0)
    conn = get_sumo_env(penv).sumo
    assert {conn.trafficlight.getProgram(t) for t in penv.possible_agents} == {program}
    _run(penv, {a: 0 for a in penv.possible_agents})
    penv.close()


def test_incident_closes_and_reopens_lane():
    from env.reforma_env import get_sumo_env, make_parallel_env

    lane = "NB_C14_C12_1"
    penv = make_parallel_env("reforma_pico", seed=0, num_seconds=120,
                             incident={"lane": lane, "start": 30, "end": 80})
    penv.reset(seed=0)
    conn = get_sumo_env(penv).sumo
    seen = {}
    while penv.agents:
        _, _, _, trunc, _ = penv.step({a: 0 for a in penv.agents})
        if all(trunc.values()):
            break
        seen[conn.simulation.getTime()] = "passenger" in conn.lane.getDisallowed(lane)
    assert not seen[20] and seen[40] and seen[75] and not seen[85]
    penv.close()


def test_gym_env_cruce():
    from env.reforma_env import make_gym_env

    genv = make_gym_env("cruce_pico", seed=0, num_seconds=60)
    o, _ = genv.reset(seed=0)
    assert genv.observation_space.contains(o)
    o, r, te, tr, _ = genv.step(genv.action_space.sample())
    assert isinstance(r, float) and genv.observation_space.contains(o)
    genv.close()


def test_counts_consistent_and_calibrated():
    """Counts (env/conteos) are consistent along the corridor and keep the calibrated ratios."""
    from env.build_network import CORRIDOR
    from env.demand import read_counts, route_rates

    for prof in ("pico", "mediodia"):
        c = read_counts(prof)
        ids = [x["id"] for x in CORRIDOR]
        for k, (a, b) in enumerate(zip(ids, ids[1:])):  # NB: what reaches b = what left a towards b
            cross = next(v for (i, ap), v in c.items() if i == a and ap in ("este", "oeste"))
            to_nb = cross["izquierda" if CORRIDOR[k]["cross_dir"] == "EB" else "derecha"]
            assert abs(c[(a, "sur")]["recto"] + to_nb - sum(c[(b, "sur")].values())) <= 8  # 15-min rounding
    tot = {p: sum(q for _, q in route_rates(get_scenario("reforma_pico").net_file, p)) for p in ("pico", "mediodia")}
    assert 6500 < tot["pico"] < 8500  # calibrated peak (env/conteos/README.md)
    assert 0.6 <= tot["mediodia"] / tot["pico"] <= 0.7
    # cruce_* uses exactly the C12 counts of the corridor
    c12 = read_counts("pico")
    cruce = route_rates(get_scenario("cruce_pico").net_file, "pico")
    assert abs(sum(q for _, q in cruce) - sum(sum(v.values()) for (i, _), v in c12.items() if i == "C12")) < 1e-6


def test_routes_carry_calibrated_vtype():
    from env.demand import VTYPE, routes_for

    txt = Path(routes_for("cruce_pico", 0)).read_text()
    assert f'tau="{VTYPE["tau"]}"' in txt and f'sigma="{VTYPE["sigma"]}"' in txt
