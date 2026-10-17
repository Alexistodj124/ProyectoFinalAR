"""Métricas honestas: loaded, inserted, backlog_pct, mean_depart_delay y total_delay (ajuste_aprendizaje.md §1)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from agents.registry import load_policy
from env.validate import loaded_vehicles
from experiments import evaluate as ev
from experiments import metrics as mt

ROUTES = """<routes>
  <vType id="auto"/><route id="r" edges="a b"/>
  <vehicle id="v0" type="auto" route="r" depart="0.00"/>
  <vehicle id="v1" type="auto" route="r" depart="10.00"/>
  <vehicle id="v2" type="auto" route="r" depart="40.00"/>
  <vehicle id="v3" type="auto" route="r" depart="70.00"/>
  <vehicle id="v4" type="auto" route="r" depart="99.50"/>
  <vehicle id="late" type="auto" route="r" depart="100.00"/>
</routes>"""

TRIPINFO = """<tripinfos>
  <tripinfo id="v0" depart="0.0" departLane="e_0" arrival="50.0" duration="50.0" waitingTime="10.0" departDelay="0.0" waitingCount="1"/>
  <tripinfo id="v1" depart="14.0" departLane="e_0" arrival="-1.0" duration="30.0" waitingTime="30.0" departDelay="4.0" waitingCount="2"/>
  <tripinfo id="v2" depart="40.0" departLane="e_0" arrival="90.0" duration="50.0" waitingTime="0.0" departDelay="0.0" waitingCount="0"/>
</tripinfos>"""


@pytest.fixture
def files(tmp_path):
    r, t = tmp_path / "x.rou.xml", tmp_path / "trip.xml"
    r.write_text(ROUTES)
    t.write_text(TRIPINFO)
    return r, t


def test_demand_metrics_by_hand(files):
    r, t = files
    trips = mt.parse_tripinfo(str(t))
    assert trips["departDelay"].tolist() == [0.0, 4.0, 0.0]
    m = mt.demand_metrics(trips, mt.scheduled_departures(str(r)), 100)
    # v3 (depart 70) y v4 (99.5) nunca entraron; "late" (depart 100) no cuenta: no estaba cargado
    assert m["loaded"] == 5 == loaded_vehicles(r, 100) and m["inserted"] == 3
    assert m["backlog_pct"] == pytest.approx(40.0)
    assert m["mean_depart_delay"] == pytest.approx(4.0 / 3)
    inserted_delay = (10 + 0) + (30 + 4) + (0 + 0)
    never_inserted = (100 - 70) + (100 - 99.5)
    assert m["total_delay"] == pytest.approx((inserted_delay + never_inserted) / 5)
    # total_delay >= espera media de los insertados cuando hay backlog: no se puede "ganar" dejando autos afuera
    assert m["total_delay"] > trips["waitingTime"].mean()


def test_demand_metrics_no_backlog_and_unenumerable_demand(files):
    r, t = files
    trips = mt.parse_tripinfo(str(t))
    ok = mt.demand_metrics(trips, {"v0": 0.0, "v1": 10.0, "v2": 40.0}, 100)
    assert ok["backlog_pct"] == 0 and ok["loaded"] == 3
    assert ok["total_delay"] == pytest.approx((10 + 34 + 0) / 3)
    flows = mt.demand_metrics(trips, {}, 100)  # toy con <flow> probabilísticos: no se sabe cuántos faltan
    assert flows["loaded"] == 3 and flows["backlog_pct"] == 0
    empty = mt.demand_metrics(trips.iloc[0:0], {"a": 5.0}, 100)  # nadie entró
    assert empty["inserted"] == 0 and empty["backlog_pct"] == 100 and empty["total_delay"] == pytest.approx(95)
    nothing = mt.demand_metrics(trips.iloc[0:0], {}, 100)
    assert nothing["loaded"] == 0 and np.isnan(nothing["total_delay"])


def test_scheduled_departures_ignores_flows(tmp_path):
    f = tmp_path / "f.rou.xml"
    f.write_text('<routes><route id="r" edges="a"/><flow id="f" route="r" begin="0" end="9" probability="0.5"/></routes>')
    assert mt.scheduled_departures(str(f)) == {} and mt.scheduled_departures(None) == {}


def test_parse_tripinfo_without_depart_delay(tmp_path):
    p = tmp_path / "t.xml"  # tripinfo viejos o de otras herramientas
    p.write_text('<tripinfos><tripinfo id="a" depart="0" departLane="e_0" arrival="5" duration="5" waitingTime="1"/></tripinfos>')
    assert mt.parse_tripinfo(str(p))["departDelay"].tolist() == [0.0]


def test_new_columns_are_in_columns_metrics_and_summary():
    for c in ("loaded", "inserted", "backlog_pct", "mean_depart_delay", "total_delay", "mean_waiting_time", "teleported"):
        assert c in ev.COLUMNS and c in ev.METRICS
    row = dict.fromkeys(ev.COLUMNS, 1.0)
    row.update(method="m", scenario="s", seed=0, p95_wait_by_approach="{}", backlog_pct=2.0, total_delay=30.0)
    s = ev.summarize(pd.DataFrame([row, {**row, "seed": 1, "backlog_pct": 4.0}]))
    assert s["backlog_pct_mean"].iloc[0] == pytest.approx(3.0) and "total_delay_ci95" in s


def test_evaluate_reforma_rows_match_tripinfo_recomputation(tmp_path):
    """cruce_pico (rutas generadas): loaded sale del archivo de rutas del episodio y total_delay del tripinfo."""
    sc_seed = 1000
    df = ev.evaluate(load_policy("max_pressure"), "cruce_pico", seeds=[sc_seed], num_seconds=300, out_dir=str(tmp_path))
    r = df.iloc[0]
    from env.demand import routes_for

    assert r["loaded"] == loaded_vehicles(routes_for("cruce_pico", sc_seed), 300) > 0
    trips = mt.parse_tripinfo(str(tmp_path / "tripinfo" / f"max_pressure_cruce_pico_{sc_seed}.xml"))
    assert r["inserted"] == len(trips) <= r["loaded"]
    assert r["backlog_pct"] == pytest.approx(100 * (r["loaded"] - r["inserted"]) / r["loaded"])
    never = set(mt.scheduled_departures(routes_for("cruce_pico", sc_seed))) - set(trips["id"])
    deps = mt.scheduled_departures(routes_for("cruce_pico", sc_seed))
    out = sum(300 - deps[v] for v in never if deps[v] < 300)
    expected = ((trips["waitingTime"] + trips["departDelay"]).sum() + out) / r["loaded"]
    assert r["total_delay"] == pytest.approx(expected)
    assert r["mean_depart_delay"] == pytest.approx(trips["departDelay"].mean())
    assert r["total_delay"] >= 0 and set(df.columns) == set(ev.COLUMNS)


def test_toy_flows_have_finite_columns():
    df = ev.evaluate(load_policy("fixed"), "toy_single", seeds=[1000], num_seconds=200)
    r = df.iloc[0]
    assert r["loaded"] == r["inserted"] > 0 and r["backlog_pct"] == 0 and np.isfinite(r["total_delay"])


def test_cli_out_dir_keep_tripinfo_and_best(tmp_path, monkeypatch, capsys):
    out = tmp_path / "res"
    ev.main(["--algo", "fixed", "--scenarios", "toy_single", "--seeds", "1000", "--num-seconds", "120", "--out-dir", str(out)])
    assert (out / "eval.csv").exists() and (out / "eval_fixed_toy_single.csv").exists()
    assert not (out / "tripinfo").exists()  # por defecto no se guardan los tripinfo (pesan mucho en reforma)
    out2 = tmp_path / "res2"
    ev.main(["--algo", "fixed", "--scenarios", "toy_single", "--seeds", "1000", "--num-seconds", "120",
             "--out-dir", str(out2), "--keep-tripinfo"])
    assert list((out2 / "tripinfo").glob("*.xml"))
    assert "backlog_pct" in capsys.readouterr().out


def test_run_with_best_dir_loads_from_best(tmp_path, monkeypatch, capsys):
    run = tmp_path / "runs" / "E3" / "dqn_x" / "seed0"
    (run / "best").mkdir(parents=True)
    (run / "config.yaml").write_text("name: dqn_x\nalgo: dqn\n")
    seen = []
    import agents.registry as reg

    monkeypatch.setattr(reg, "load_policy", lambda algo, run_dir=None, cfg=None: seen.append(run_dir) or "policy")
    assert ev.resolve_run(str(run)) == str(run / "best")
    assert ev._load("dqn", str(run)) == ("policy", "dqn_x") and seen == [str(run / "best")]
    assert "best" in capsys.readouterr().out
    (run / "best").rmdir()
    ev._load("dqn", str(run))
    assert seen[-1] == str(run) and ev.resolve_run(None) is None
