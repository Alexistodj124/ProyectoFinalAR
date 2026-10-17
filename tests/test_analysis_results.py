"""analysis: carga sin duplicados, estadística, selección y las figuras/tablas nuevas, con CSV sintéticos (sin SUMO)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps

from analysis import data, make_all, plots, specs, stats, style, tables
from tests.test_analysis import eval_df
from tests.test_analysis_delay import with_delay

RNG = np.random.default_rng(3)


def full(df, base, backlog=0.0):
    df = with_delay(df, 1.0, backlog)
    df["total_delay"] = base * 1.1 + RNG.normal(0, 1, len(df))
    df["max_wait_cross_streets"] = base * 5 + RNG.normal(0, 10, len(df))
    return df


def learned(r, exp, name, scenarios, base, n_seeds=5, n_ep=20):
    for seed in range(n_seeds):
        d = r / exp / name / f"seed{seed}"
        d.mkdir(parents=True)
        eps = np.arange(n_ep)
        pd.DataFrame({"episode": eps, "env_steps": (eps + 1) * 720, "return": -np.linspace(5000, 100, n_ep),
                      "mean_waiting_time": np.linspace(90, base, n_ep), "wall_time": eps * 1.0}).to_csv(d / "train_log.csv", index=False)
        pd.DataFrame({"checkpoint": [f"ep{e:04d}" for e in (10, 20)], "episode": [10, 20], "criterion": "total_delay",
                      "total_delay": [base * 3 + seed, base * 1.2 + seed], "selected": [False, True]}).to_csv(d / "selection.csv", index=False)
        e = pd.concat([full(eval_df(name, sc, [seed], base), base) for sc in scenarios])
        e["exp"] = exp
        e.to_csv(d / "eval.csv", index=False)


@pytest.fixture
def runs(tmp_path):
    r = tmp_path / "runs"
    (r / "E1" / "baselines").mkdir(parents=True)
    scs = ["cruce_pico", "reforma_pico"]
    base = pd.concat([full(eval_df(m, sc, [None], b), b) for m, b in (("fixed", 60), ("actuated", 50), ("max_pressure", 40)) for sc in scs])
    base["train_seed"] = 0
    base["exp"] = "E1"
    base.to_csv(r / "E1" / "baselines" / "eval.csv", index=False)
    base.to_csv(r / "E1" / "baselines" / "eval_fixed_copy.csv", index=False)  # copia por método: no debe contar doble
    learned(r, "E4", "dqn_best", ["cruce_pico"], 30)
    learned(r, "E4", "ppo", ["cruce_pico"], 35)
    learned(r, "E5", "mappo", ["reforma_pico"], 35)
    learned(r, "E5", "idqn", ["reforma_pico"], 45)
    learned(r, "E6", "comm", ["reforma_pico"], 36)
    learned(r, "E8", "qmix_fair", ["reforma_pico"], 38)
    (r / "_quick" / "E5" / "mappo" / "seed0").mkdir(parents=True)  # corrida de humo: se ignora
    eval_df("mappo", "reforma_pico", [0], 1).to_csv(r / "_quick" / "E5" / "mappo" / "seed0" / "eval.csv", index=False)
    (r / "E7").mkdir()
    rows = []
    for fam, sc, ms in (("cruce", "cruce", [("fixed", 60), ("max_pressure", 40), ("dqn_best", 30)]),
                        ("reforma", "reforma", [("fixed", 60), ("max_pressure", 40), ("marl_best", 35)])):
        for k, v in enumerate(("pico", "mediodia", "pico_x13", "pico_incident")):
            scn = f"{sc}_{v.replace('_incident', '')}"
            for m, b in ms:
                d = full(eval_df(m, scn, [3], b * (1 + k)), b * (1 + k)).assign(variant=v, base=fam,
                                                                              selection="baseline" if b in (60, 40) else "best")
                d["train_seed"] = np.nan if m in ("fixed", "max_pressure") else 3
                rows.append(d)
    pd.concat(rows).to_csv(r / "E7" / "robustness.csv", index=False)
    (r / "E8").mkdir(exist_ok=True)
    fair = pd.concat([base.assign(source="E1/baselines/eval.csv"), base.assign(source="E1/baselines/eval_fixed_copy.csv"),
                      base.assign(source="E7/robustness.csv")])
    lr = [pd.read_csv(f).assign(source=str(f.relative_to(r))) for f in sorted(r.glob("E[4568]/*/seed*/eval.csv"))]
    lr.append(pd.read_csv(r / "E7" / "robustness.csv").query("method == 'marl_best'").assign(source="E7/robustness.csv"))
    pd.concat([fair] + lr).assign(variant="pico").to_csv(r / "E8" / "fairness.csv", index=False)
    return r


def test_load_master_has_no_duplicates_and_skips_quick(runs):
    m = data.load_master(runs)
    assert len(m[(m["method"] == "fixed") & (m["scenario"] == "cruce_pico")]) == 5  # eval_fixed_copy.csv no cuenta doble
    assert "_quick" not in set(m["exp"]) and (m[m["method"] == "mappo"]["scenario"] == "reforma_pico").all()
    assert len(m[m["method"] == "mappo"]) == 5 * 5  # solo las 5 semillas de E5 (la de _quick queda fuera)
    # las líneas base de E7 entran solo en escenarios que E1 no cubre (mediodía y +30 %), nunca el incidente
    b7 = m[m["exp"] == "E7"]
    assert set(b7["scenario"]) == {"cruce_mediodia", "cruce_pico_x13", "reforma_mediodia", "reforma_pico_x13"}
    assert set(b7["method"]) == set(data.BASELINE_METHODS) - {"actuated"}


def test_unit_values_seed_vs_episode(runs):
    m = data.load_master(runs)
    v, unit = data.unit_values(m[(m["method"] == "mappo") & (m["scenario"] == "reforma_pico")], "total_delay")
    assert unit == "semilla" and len(v) == 5
    v, unit = data.unit_values(m[(m["method"] == "fixed") & (m["scenario"] == "reforma_pico")], "total_delay")
    assert unit == "episodio" and len(v) == 5


def test_load_fairness_dedups_baselines_and_drops_e7_learned(runs):
    f = data.load_fairness(runs)
    assert len(f[(f["method"] == "fixed") & (f["scenario"] == "reforma_pico")]) == 5
    assert "marl_best" not in set(f["method"])  # repite una corrida de E5
    assert set(f["method"]) >= {"fixed", "mappo", "idqn", "comm", "qmix_fair", "dqn_best", "ppo"}


def test_exp_frame_adds_references_and_requires_own_runs(runs):
    m = data.load_master(runs)
    e6 = specs.exp_frame(m, "E6")
    assert {"comm", "mappo", "idqn", "fixed"} <= set(e6["method"])  # MAPPO e IDQN vienen de E5 como referencia
    assert specs.exp_frame(m, "E2").empty  # E2 no tiene corridas: las líneas base solas no son un experimento
    assert set(specs.exp_frame(m, "E1")["scenario"]) >= {"cruce_pico", "cruce_mediodia", "reforma_pico_x13"}


def test_welch_matches_scipy_and_holm():
    a, b = RNG.normal(10, 2, 5), RNG.normal(14, 3, 10)
    r = stats.welch(a, b)
    ref = sps.ttest_ind(a, b, equal_var=False)
    assert r["p"] == pytest.approx(ref.pvalue, rel=1e-6)
    assert r["diff_lo"] < r["diff"] < r["diff_hi"]
    adj = stats.holm([0.01, 0.04, 0.03, np.nan])
    assert adj[0] == pytest.approx(0.03) and adj[2] == pytest.approx(0.06) and adj[1] == pytest.approx(0.06) and np.isnan(adj[3])


def test_stats_table(runs, tmp_path):
    out = stats.make_stats(runs, tmp_path / "t")
    md = (tmp_path / "t" / "comparaciones_estadisticas.md").read_text()
    assert "MAPPO contra tiempo fijo" in md and "p (Holm)" in md and "favorece a" in md
    assert "E7: agente aprendido" in md and "reforma_pico [pico_incident]" in md
    f = pd.read_csv(tmp_path / "t" / "comparaciones_estadisticas.csv")
    assert (f["p_holm"] >= f["p"] - 1e-12).all()
    row = f[(f["A"] == "mappo") & (f["B"] == "fixed") & (f["metrica"] == "total_delay") & (f["origen"] == "matriz")].iloc[0]
    assert row["unidad_A"] == "semilla" and row["unidad_B"] == "episodio" and row["n_a"] == 5 and row["n_b"] == 5


def test_style_families_and_labels():
    assert style.family("fixed") == "baseline" and style.family("ppo") == "single" and style.family("qmix_fair") == "marl"
    assert style.color("fixed") != style.color("max_pressure")
    assert style.label("dqn_best", "E7") != style.label("dqn_best")
    assert style.color("never_heard_of_it") == style.color("never_heard_of_it")  # determinista
    assert style.sort_methods(["qmix", "fixed", "zzz", "mappo"]) == ["fixed", "qmix", "mappo", "zzz"]
    assert style.approach_label("C06_W_in").startswith("Transv.") and "Reforma" in style.approach_label("NB_S_C15")
    assert style.is_cross_street("C12_W_in") and not style.is_cross_street("NB_C14_C12")


def test_selection_loader_and_sample_efficiency(runs, tmp_path):
    sel = plots.load_selection(runs)
    assert {"env_steps", "exp", "name", "seed"} <= set(sel.columns)
    assert set(sel[sel["episode"] == 10]["env_steps"]) == {10 * 720}  # checkpoint tras 10 episodios = 10 x 720 pasos
    out = tables.sample_efficiency_table("E5", runs, tmp_path / "t")
    md = out[0].read_text()
    assert "MAPPO" in md and "IDQN" in md and "de 5" in md


def test_new_figures(runs, tmp_path):
    f = tmp_path / "f"
    for fn in (plots.headline_plot, plots.fairness_plot, plots.tradeoff_plot, plots.robustness_plot,
               plots.degradation_plot, plots.selection_plot, plots.co2_plot):
        out = fn(runs, f)
        assert out and {p.suffix for p in out} == {".png", ".pdf"} and all(p.stat().st_size > 1000 for p in out), fn.__name__
    assert plots.learning_curves("E5", runs, f)  # retorno + validación (selection.csv)
    assert plots.eval_bars("E6", runs, f) and (f / "E6_eval_bars.png").exists()
    assert (f / "E8_tradeoff_reforma_pico.png").exists() and (f / "E7_degradation.png").exists()


def test_boot_ratio_ci_contains_point():
    x, ref = RNG.normal(60, 5, 10), RNG.normal(30, 3, 10)
    r, lo, hi = plots._boot_ratio(x, ref)
    assert lo <= r <= hi and r == pytest.approx(x.mean() / ref.mean())


def test_make_all_full(runs, tmp_path):
    made = make_all.make_all(runs, tmp_path / "f", tmp_path / "t", latex=True)
    assert made["E1"] and made["E4"] and made["E5"] and made["E6"] and made["E7"] and made["E8"] and made["extra"]
    assert made["E2"] == [] and made["E3"] == []
    t = tmp_path / "t"
    assert (t / "E5_eval.md").exists() and (t / "CO2_reforma_pico.md").exists() and (t / "E7_robustness.md").exists()
    e5 = (t / "E5_eval.md").read_text()
    assert "MAPPO (sem.)" in e5 and "Tiempo fijo (ep.)" in e5  # la tabla dice cuál es la réplica
    e7 = (t / "E7_robustness.md").read_text()
    assert "pico_incident" in e7 or "incidente" in e7
