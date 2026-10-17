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
