"""Setup smoke test: SUMO + sumo-rl run on a toy scenario."""
import sumo_rl

from env.scenarios import get_scenario, get_topology


def test_toy_single_runs_a_few_steps():
    sc = get_scenario("toy_single")
    env = sumo_rl.parallel_env(
        net_file=sc.net_file,
        route_file=sc.route_file,
        num_seconds=60,
        delta_time=sc.delta_time,
        yellow_time=sc.yellow_time,
        min_green=sc.min_green,
        sumo_warnings=False,
    )
    obs, _ = env.reset(seed=0)
    assert len(obs) == 1
    for _ in range(5):
        obs, rew, term, trunc, info = env.step({a: 0 for a in env.agents})
    env.close()


def test_topology_chain():
    topo = get_topology(get_scenario("toy_grid2x2").net_file)
    assert len(topo["order"]) == 4
    assert all(len(v) in (1, 2) for v in topo["neighbors"].values())


def test_factory_toy_gym_and_tripinfo(tmp_path):
    from env.reforma_env import get_sumo_env, make_gym_env, make_parallel_env

    trip = tmp_path / "dir with spaces" / "trip.xml"
    penv = make_parallel_env("toy_grid2x2", seed=3, num_seconds=120, tripinfo_path=str(trip))
    obs, _ = penv.reset(seed=3)
    assert len(obs) == 4
    se = get_sumo_env(penv)
    assert set(se.traffic_signals) == set(obs)
    done = False
    while not done:
        obs, rew, term, trunc, _ = penv.step({a: 0 for a in penv.agents})
        done = all(trunc.values()) or not penv.agents
    penv.close()
    assert trip.exists()

    genv = make_gym_env("toy_single", seed=1, num_seconds=60)
    o, _ = genv.reset(seed=1)
    assert genv.observation_space.contains(o)
    o, r, te, tr, _ = genv.step(genv.action_space.sample())
    assert isinstance(r, float)
    genv.close()
