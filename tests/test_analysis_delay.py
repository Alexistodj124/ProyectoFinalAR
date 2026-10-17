"""analysis: total_delay y backlog_pct como métricas de primera clase (y CSV viejos sin ellas)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis import data, make_all, plots, tables
from tests.test_analysis import eval_df

RNG = np.random.default_rng(1)


def with_delay(df, wait_to_delay=1.0, backlog=0.0):
    df = df.copy()
    df["loaded"] = 1000
    df["inserted"] = (1000 * (1 - backlog / 100)).astype(int) if hasattr(backlog, "astype") else int(1000 * (1 - backlog / 100))
    df["backlog_pct"] = backlog
    df["mean_depart_delay"] = 1.0
    df["total_delay"] = df["mean_waiting_time"] * wait_to_delay + backlog * 20
    return df


@pytest.fixture
def runs(tmp_path):
    r = tmp_path / "runs"
    (r / "E1" / "baselines").mkdir(parents=True)
    new = pd.concat([with_delay(eval_df("fixed", "cruce_pico", [0], 60), 1.1, 0.2),
                     with_delay(eval_df("hungry", "cruce_pico", [0], 20), 1.0, 8.0)])  # espera baja, mucho backlog
    old = eval_df("old_method", "cruce_pico", [0], 40)  # CSV viejo: sin las columnas nuevas
    new.to_csv(r / "E1" / "baselines" / "eval.csv", index=False)
    (r / "E1" / "legacy").mkdir()
    old.to_csv(r / "E1" / "legacy" / "eval.csv", index=False)
    for seed in range(2):
        d = r / "E3" / "dqn" / f"seed{seed}"
        d.mkdir(parents=True)
        n = 15
        pd.DataFrame({"episode": range(n), "env_steps": np.arange(n) * 100, "return": -np.linspace(100, 40, n),
                      "mean_waiting_time": np.linspace(90, 40, n), "total_delay": np.linspace(150, 45, n),
                      "wall_time": np.arange(n) * 1.5}).to_csv(d / "train_log.csv", index=False)
    return r


def test_tables_put_total_delay_and_backlog_first(runs, tmp_path):
    tables.make_tables("E1", runs, tmp_path / "t")
    md = (tmp_path / "t" / "E1_eval.md").read_text()
    header = [l for l in md.splitlines() if l.startswith("| Método")][0]
    cols = [c.strip() for c in header.strip("|").split("|")]
    assert cols[1:4] == [data.METRICS[m][0] for m in ("total_delay", "mean_waiting_time", "backlog_pct")]
    assert data.METRICS["max_wait_cross_streets"][0] in cols and data.METRICS["mean_stops"][0] in cols
    # "hungry" gana en espera pero pierde en demora total: la negrita va a métricas distintas
    row = lambda name: [l for l in md.splitlines() if l.startswith(f"| {name} ")][0]
    assert "**" in row("hungry").split("|")[3] and "**" not in row("hungry").split("|")[2]
    # el método viejo no tiene las columnas nuevas: "-" y sin excepción
    assert row("old_method").split("|")[2].strip() == "-"


def test_all_missing_metric_does_not_crash(runs, tmp_path):
    only_old = data.load_eval(runs, "E1").query("method == 'old_method'")
    agg = data.aggregate(only_old, ["mean_waiting_time", "total_delay"])  # total_delay no existe
    assert set(agg["metric"]) == {"mean_waiting_time"}
    df = data.load_eval(runs, "E1")
    agg = data.aggregate(df, ["mean_waiting_time", "total_delay"])
    t = tables.metric_table(agg, "method", ["mean_waiting_time", "total_delay"], {"scenario": "cruce_pico"})
    assert t.loc["old_method", data.METRICS["total_delay"][0]] == "-"
    assert plots.bar_chart(only_old.drop(columns=["mean_waiting_time"]), "x", out_dir=tmp_path) == []


def test_bar_charts_default_to_total_delay_wait_backlog(runs, tmp_path):
    df = data.load_eval(runs, "E1")
    assert data.available(df, data.BAR_METRICS) == ["total_delay", "mean_waiting_time", "backlog_pct"]
    out = plots.eval_bars("E1", runs, tmp_path / "f")
    assert {p.suffix for p in out} == {".png", ".pdf"} and all(p.stat().st_size > 1000 for p in out)
    assert plots.eval_bars("E1", runs, tmp_path / "g", metrics=("total_delay",))


def test_learning_curve_option_for_any_column(runs, tmp_path):
    out = plots.learning_curves("E3", runs, tmp_path / "f", metrics=("total_delay", "no_such_column"))
    assert out and all(p.stat().st_size > 1000 for p in out)
    assert plots.learning_curves("E3", runs, tmp_path / "f", metrics=("no_such_column",)) == []
    plots.main(["--exp", "E3", "--runs-dir", str(runs), "--out-dir", str(tmp_path / "h"),
                "--curve-metrics", "total_delay", "return", "--bar-metrics", "total_delay"])
    assert (tmp_path / "h" / "E3_learning_curves.png").exists()


def test_load_eval_ignores_summary_and_per_method_copies(tmp_path):
    d = tmp_path / "E1" / "baselines"
    d.mkdir(parents=True)
    df = with_delay(eval_df("fixed", "cruce_pico", [0], 60))
    df.to_csv(d / "eval.csv", index=False)
    df.to_csv(d / "eval_fixed_cruce_pico.csv", index=False)  # lo que escribe evaluate(out_dir=...)
    df.head(1).to_csv(d / "eval_summary.csv", index=False)
    assert len(data.load_eval(tmp_path, "E1")) == len(df)
    (d / "eval.csv").unlink()  # sin eval.csv, los eval_<método>_<escenario>.csv sí cuentan
    assert len(data.load_eval(tmp_path, "E1")) == len(df)


def test_make_all_with_new_columns(runs, tmp_path):
    made = make_all.make_all(runs, tmp_path / "f", tmp_path / "t")
    assert made["E1"] and made["E3"]
