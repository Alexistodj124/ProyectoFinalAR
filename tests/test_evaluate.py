"""Evaluación y métricas: ci95, summarize, tripinfo, equidad y evaluate() end-to-end en escenarios toy."""
import json

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from agents.registry import load_policy
from env.scenarios import get_scenario
from experiments import evaluate as ev
from experiments.metrics import ci95, cross_approaches, parse_tripinfo

TRIPINFO = """<?xml version="1.0"?>
<tripinfos>
  <tripinfo id="a" depart="0.0" departLane="-h11_0" arrival="50.0" duration="50.0" waitingTime="10.0" waitingCount="1">
    <emissions CO2_abs="2000000.0"/>
  </tripinfo>
  <tripinfo id="b" depart="5.0" departLane="-h11_1" arrival="-1.00" duration="30.0" waitingTime="30.0" waitingCount="2">
    <emissions CO2_abs="1000000.0"/>
  </tripinfo>
  <tripinfo id="c" depart="9.0" departLane="-v11_0" arrival="60.0" duration="51.0" waitingTime="2.0" waitingCount="0"/>
</tripinfos>"""


def test_ci95_matches_student_t():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    expected = stats.t.ppf(0.975, 4) * np.std(x, ddof=1) / np.sqrt(5)
    assert ci95(x) == pytest.approx(expected) and ci95(x) == pytest.approx(1.9632, abs=1e-3)
    assert ci95([3, 3, 3]) == 0.0
    assert np.isnan(ci95([1.0]))


def test_summarize_synthetic():
    rows = []
    for method, base in [("a", 10.0), ("b", 20.0)]:
        for s, d in enumerate([-1.0, 0.0, 1.0]):
            r = dict.fromkeys(ev.COLUMNS, 1.0)
            r.update(method=method, scenario="s", seed=s, mean_waiting_time=base + d, p95_wait_by_approach="{}")
            rows.append(r)
    s = ev.summarize(pd.DataFrame(rows))
    assert list(s["method"]) == ["a", "b"] and list(s["n"]) == [3, 3]
    assert s["mean_waiting_time_mean"].tolist() == pytest.approx([10.0, 20.0])
    assert s["mean_waiting_time_ci95"].tolist() == pytest.approx([ci95([9, 10, 11])] * 2)
    assert s["arrived_ci95"].tolist() == [0.0, 0.0]
    assert "p95_wait_by_approach_mean" not in s
    by_scn = ev.summarize(pd.DataFrame(rows), by=["scenario"])
    assert len(by_scn) == 1 and by_scn["n"].iloc[0] == 6


def test_parse_tripinfo_and_cross_streets(tmp_path):
    p = tmp_path / "trip.xml"
    p.write_text(TRIPINFO)
    t = parse_tripinfo(str(p))
    assert list(t["approach"]) == ["-h11", "-h11", "-v11"]
    assert list(t["finished"]) == [True, False, True]
    assert t["co2_mg"].sum() == 3e6 and t["stops"].tolist() == [1, 2, 0]
    # toy: sin nombres, la transversal es el eje con menos flujo (vertical: 1 contra 2 vehículos)
    assert cross_approaches(get_scenario("toy_grid2x2").net_file, t) == {"-v11"}


def test_cross_streets_by_name(tmp_path):
    net = tmp_path / "x.net.xml"
    net.write_text(
        '<net><junction id="a" x="0" y="0"/><junction id="b" x="100" y="0"/><junction id="c" x="0" y="100"/>'
        '<edge id="main" from="a" to="b" name="Avenida La Reforma"/>'
        '<edge id="side" from="c" to="a" name="Calle 7"/><edge id="noname" from="c" to="b"/></net>'
    )
    trips = pd.DataFrame({"approach": ["main", "main", "main", "side", "noname"]})
    assert cross_approaches(str(net), trips) == {"side", "noname"}


@pytest.mark.parametrize("algo", ["fixed", "max_pressure"])
def test_evaluate_toy_single_columns(algo, tmp_path):
    pol = load_policy(algo)
    df = ev.evaluate(pol, "toy_single", seeds=[1000, 1001], num_seconds=300, out_dir=str(tmp_path))
    assert list(df.columns) == ev.COLUMNS and len(df) == 2
    assert (df["method"] == algo).all() and (df["scenario"] == "toy_single").all()
    num = df.drop(columns=["method", "scenario", "p95_wait_by_approach"])
    assert np.isfinite(num.to_numpy(dtype=float)).all()
    assert (df["arrived"] > 0).all() and (df["throughput_veh_h"] > 0).all() and (df["co2_kg"] > 0).all()
    assert (df["max_queue"] >= df["mean_queue"]).all() and (df["mean_waiting_time"] >= 0).all()
    p95 = json.loads(df["p95_wait_by_approach"].iloc[0])
    assert len(p95) >= 2 and all(v >= 0 for v in p95.values())
    assert (tmp_path / f"eval_{algo}_toy_single.csv").exists() and (tmp_path / "tripinfo").is_dir()


def test_evaluate_grid_three_baselines_and_determinism():
    dfs = [ev.evaluate(load_policy(a), "toy_grid2x2", seeds=[1000], num_seconds=300) for a in ev.BASELINES_ALL]
    df = pd.concat(dfs)
    assert list(df["method"]) == ["fixed", "actuated", "max_pressure"]
    assert np.isfinite(df[ev.METRICS].to_numpy(dtype=float)).all()
    again = ev.evaluate(load_policy("fixed"), "toy_grid2x2", seeds=[1000], num_seconds=300)
    pd.testing.assert_frame_equal(df.iloc[[0]].reset_index(drop=True), again)  # misma semilla, mismo resultado


def test_cli_config(tmp_path, capsys):
    cfg = tmp_path / "e.yaml"
    out = tmp_path / "res" / "eval.csv"
    cfg.write_text(
        f"methods: [fixed, max_pressure]\nscenarios: [toy_single]\nseeds: [1000, 1001]\nnum_seconds: 200\nout: {out}\n"
    )
    ev.main(["--config", str(cfg)])
    df = pd.read_csv(out)
    assert set(df["method"]) == {"fixed", "max_pressure"} and len(df) == 4
    assert (out.parent / "eval_summary.csv").exists()
    assert "mean_waiting_time" in capsys.readouterr().out
