"""Plots and tables on synthetic CSVs (no SUMO)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from analysis import data, make_all, plots, tables

RNG = np.random.default_rng(0)


def eval_df(method, scenario, train_seeds, base):
    rows = []
    for ts in train_seeds:
        for s in range(1000, 1005):
            rows.append({"method": method, "scenario": scenario, "seed": s, "train_seed": ts,
                         "mean_waiting_time": base + RNG.normal(0, 2), "mean_travel_time": base * 2 + RNG.normal(0, 3),
                         "mean_queue": base / 5, "max_queue": base / 2, "throughput_veh_h": 900 - base + RNG.normal(0, 10),
                         "mean_stops": 1.5, "max_wait_cross_streets": base * 3,
                         "p95_wait_by_approach": json.dumps({"N": base, "S": base + 5, "E": base * 2}),
                         "co2_kg": 1.0, "arrived": 100, "teleported": 0})
    return pd.DataFrame(rows)


@pytest.fixture
def runs(tmp_path):
    r = tmp_path / "runs"
    (r / "E1" / "baselines").mkdir(parents=True)
    base = pd.concat([eval_df(m, sc, [None], b) for m, b in (("fixed", 60), ("max_pressure", 45)) for sc in ("cruce_pico", "cruce_mediodia")])
    base["train_seed"] = 0
    base.to_csv(r / "E1" / "baselines" / "eval.csv", index=False)
    for name, b in (("dqn_plain", 40), ("dqn_double", 35)):
        for seed in range(3):
            d = r / "E3" / name / f"seed{seed}"
            d.mkdir(parents=True)
            n = 20 + seed  # unequal lengths on purpose
            pd.DataFrame({"episode": range(n), "env_steps": np.arange(n) * 100, "return": -np.linspace(100, b, n) + RNG.normal(0, 2, n),
                          "mean_waiting_time": np.linspace(90, b, n), "wall_time": np.arange(n) * 1.5}).to_csv(d / "train_log.csv", index=False)
            e = eval_df(name, "cruce_pico", [seed], b)
            e.to_csv(d / "eval.csv", index=False)
    (r / "E7").mkdir()
    rob = pd.concat([eval_df(m, "cruce_" + v.replace("_incident", ""), [0], b + k * 10).assign(variant=v, base="cruce")
                     for m, b in (("fixed", 60), ("dqn", 40)) for k, v in enumerate(("pico", "mediodia", "pico_incident"))])
    rob.to_csv(r / "E7" / "robustness.csv", index=False)
    (r / "E8").mkdir()
    pd.concat([eval_df(m, "cruce_pico", [0], b).assign(variant="pico") for m, b in (("fixed", 60), ("dqn", 40))]).to_csv(r / "E8" / "fairness.csv", index=False)
    return r


def test_ci95_matches_t_interval():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert data.ci95(x) == pytest.approx(2.776445 * np.std(x, ddof=1) / np.sqrt(5), rel=1e-5)
    assert np.isnan(data.ci95([1.0]))


def test_load_eval_tags_and_aggregate_uses_train_seeds(runs):
    df = data.load_eval(runs, "E3")
    assert set(df["train_seed"]) == {0, 1, 2} and set(df["method"]) == {"dqn_plain", "dqn_double"}
    agg = data.aggregate(df, ["mean_waiting_time"])
    assert set(agg["n"]) == {3}  # replication unit = training seed
    b = data.aggregate(data.load_eval(runs, "E1"), ["mean_waiting_time"])
    assert set(b["n"]) == {5}  # baselines: evaluation episodes


def test_learning_curves_unequal_lengths(runs, tmp_path):
    out = plots.learning_curves("E3", runs, tmp_path / "f")
    assert {p.suffix for p in out} == {".png", ".pdf"} and all(p.stat().st_size > 1000 for p in out)


def test_bars_fairness_robustness(runs, tmp_path):
    f = tmp_path / "f"
    assert len(plots.eval_bars("E1", runs, f)) == 2
    assert len(plots.fairness_plot(runs, f)) == 2
    assert len(plots.robustness_plot(runs, f)) == 2
    assert (f / "E8_fairness_cruce_pico.png").exists()


def test_tables(runs, tmp_path):
    out = tables.make_tables("E1", runs, tmp_path / "t", latex=True)
    md = (tmp_path / "t" / "E1_eval.md").read_text()
    assert "## cruce_pico" in md and "±" in md and "**" in md
    best = [l for l in md.split("## cruce_pico")[1].splitlines() if "max_pressure" in l][0]
    assert "**" in best  # max_pressure has the lowest waiting time
    assert any(p.suffix == ".tex" for p in out)
    assert "Δ%" in "".join(p.read_text() for p in tables.make_tables("E7", runs, tmp_path / "t"))
    assert "p95 N" in "".join(p.read_text() for p in tables.make_tables("E8", runs, tmp_path / "t"))
    tables.make_tables("E3", runs, tmp_path / "t")
    assert "retorno final" in (tmp_path / "t" / "E3_training.md").read_text()


def test_make_all_skips_missing(runs, tmp_path, capsys):
    made = make_all.make_all(runs, tmp_path / "f", tmp_path / "t")
    assert made["E1"] and made["E3"] and made["E7"] and made["E8"]
    assert made["E2"] == [] and made["E6"] == []
    assert "E2] no data" in capsys.readouterr().out


def test_empty_runs_dir(tmp_path):
    assert make_all.make_all(tmp_path / "none", tmp_path / "f", tmp_path / "t") == {e: [] for e in make_all.EXPS}
