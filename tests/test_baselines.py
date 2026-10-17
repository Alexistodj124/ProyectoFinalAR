"""Líneas base: programas de tiempo fijo / actuado y max-pressure en los escenarios toy."""
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from agents.registry import BASELINES, load_policy
from baselines.programs import build_actuated_additional, ensure_actuated, is_green_phase
from env.reforma_env import get_sumo_env, make_parallel_env
from env.scenarios import get_scenario


def _start(policy, name, seed=1, num_seconds=120):
    sc = policy.prepare_scenario(get_scenario(name)) if hasattr(policy, "prepare_scenario") else get_scenario(name)
    env = make_parallel_env(sc, seed, num_seconds=num_seconds, fixed_ts=policy.fixed_ts, program=policy.program)
    obs, _ = env.reset(seed=seed)
    sumo_env = get_sumo_env(env)
    policy.reset(sumo_env)
    return env, sumo_env, obs


def test_registry_loads_all_baselines():
    for algo in BASELINES:
        p = load_policy(algo)
        assert p.name == algo
        assert p.fixed_ts == (algo != "max_pressure")
    assert load_policy("fixed").program == "fixed" and load_policy("actuated").program == "actuated"


def test_green_phase_rule():
    assert is_green_phase("GGrr") and is_green_phase("rGgr")
    assert not is_green_phase("yyrr") and not is_green_phase("rrrr") and not is_green_phase("Gyrr")


def test_fixed_keeps_static_program():
    env, se, _ = _start(load_policy("fixed"), "toy_single")
    conn = se.sumo
    (tls,) = se.traffic_signals
    assert conn.trafficlight.getProgram(tls) == "0"  # toy: programa estático de la red
    phases = set()
    for _ in range(24):
        env.step({a: 0 for a in env.agents})
        phases.add(conn.trafficlight.getPhase(tls))
    assert {0, 2} <= phases  # alterna sus dos verdes (el amarillo de 2 s cae entre muestras de 5 s)
    env.close()


def test_actuated_program_generated_and_active(tmp_path):
    net = get_scenario("toy_single").net_file
    out = build_actuated_additional(net, 10, 60, tmp_path / "act.add.xml")
    logic = ET.parse(out).getroot().find("tlLogic")
    assert logic.get("type") == "actuated" and logic.get("programID") == "actuated"
    phases = logic.findall("phase")
    assert [bool(p.get("minDur")) for p in phases] == [True, False, True, False]  # solo los verdes
    assert all(p.get("minDur") == "10" and p.get("maxDur") == "60" for p in phases if p.get("minDur"))

    sc = get_scenario("toy_grid2x2")
    assert sc.actuated_additional is None
    sc2 = ensure_actuated(sc)
    assert sc2.actuated_additional and ensure_actuated(sc2) is sc2  # idempotente
    assert ensure_actuated(sc).actuated_additional == sc2.actuated_additional  # caché estable

    env, se, _ = _start(load_policy("actuated"), "toy_grid2x2")
    assert {se.sumo.trafficlight.getProgram(t) for t in se.traffic_signals} == {"actuated"}
    durations = []
    last, t0 = None, 0
    for step in range(40):
        env.step({a: 0 for a in env.agents})
        ph = se.sumo.trafficlight.getPhase("1")
        if ph != last:
            durations.append(step - t0)
            last, t0 = ph, step
    assert len(durations) >= 3  # el controlador cambia de fase
    env.close()


def test_max_pressure_actions_valid_and_greedy():
    pol = load_policy("max_pressure")
    env, se, obs = _start(pol, "toy_grid2x2", num_seconds=300)
    for _ in range(20):
        actions = pol.act(obs)
        assert set(actions) == set(obs)
        for ts_id, a in actions.items():
            ts = se.traffic_signals[ts_id]
            p = pol.pressures(ts_id)
            assert len(p) == ts.num_green_phases and isinstance(a, int) and 0 <= a < ts.num_green_phases
            assert p[a] == max(p)  # elige una fase de presión máxima
        obs, *_ = env.step(actions)
    env.close()


def test_max_pressure_movements_follow_green_links():
    pol = load_policy("max_pressure")
    env, se, _ = _start(pol, "toy_single", num_seconds=60)
    (tls,) = se.traffic_signals
    ts = se.traffic_signals[tls]
    links = se.sumo.trafficlight.getControlledLinks(tls)
    for phase, mv in zip(ts.green_phases, pol.movements[tls]):
        expected = sum(phase.state[j] in "Gg" for j, g in enumerate(links) for _ in g)
        assert len(mv) == expected > 0
        assert all(i in ts.lanes for i, _ in mv)
    env.close()


def test_max_pressure_tie_keeps_current_phase():
    pol = load_policy("max_pressure")
    env, se, obs = _start(pol, "toy_single", num_seconds=60)
    (tls,) = se.traffic_signals
    # al inicio no hay autos: todas las presiones son 0 y debe conservar la fase actual
    assert pol.pressures(tls) == [0.0] * se.traffic_signals[tls].num_green_phases
    assert pol.act(obs)[tls] == se.traffic_signals[tls].green_phase
    env.close()
