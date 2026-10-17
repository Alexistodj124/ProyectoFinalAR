"""Figures for the report (matplotlib only). PNG + PDF go to docs/figures/.

    python -m analysis.plots --exp E3
    python -m analysis.plots --exp E7 --runs-dir runs --out-dir docs/figures
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.data import (FIG_DIR, METRICS, RUNS_DIR, aggregate, approach_frame, load_csv, load_eval,
                           load_train_logs)

# Okabe-Ito colour-blind safe palette; baselines are always greys.
PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#000000"]
BASELINE_COLORS = {"fixed": "#7f7f7f", "actuated": "#a6a6a6", "max_pressure": "#4d4d4d"}


def apply_style() -> None:
    plt.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
        "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10, "legend.fontsize": 9, "legend.frameon": False,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
        "axes.prop_cycle": plt.cycler(color=PALETTE),
    })


def colors_for(names) -> dict[str, str]:
    out, free = {}, iter(PALETTE * 3)
    for n in sorted(set(names), key=str):
        out[n] = BASELINE_COLORS.get(n) or next(free)
    return out


def legend_below(fig, ax, ncol: int = 4) -> None:
    h, l = ax.get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=min(ncol, len(l)), bbox_to_anchor=(0.5, 0.0))


def save_fig(fig, name: str, out_dir: Path | str = FIG_DIR) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in ("png", "pdf"):
        p = out_dir / f"{name}.{ext}"
        fig.savefig(p)
        paths.append(p)
    plt.close(fig)
    return paths


# ------------------------------------------------------------------ learning curves
def learning_curves(exp: str, runs_dir=RUNS_DIR, out_dir=FIG_DIR, metrics=("return", "mean_waiting_time"),
                    smooth: int = 1, n_grid: int = 100) -> list[Path]:
    """Mean +- std band across seeds. Seeds are interpolated on a common x grid
    (x = env_steps if logged, else episode), cut at the shortest seed."""
    apply_style()
    logs = load_train_logs(runs_dir, exp)
    if logs.empty:
        return []
    metrics = [m for m in metrics if m in logs]
    xcol = "env_steps" if "env_steps" in logs else "episode"
    col = colors_for(logs["name"])
    fig, axes = plt.subplots(1, len(metrics), figsize=(5.2 * len(metrics), 3.6), squeeze=False)
    for ax, m in zip(axes[0], metrics):
        for name, g in logs.groupby("name"):
            runs = [s.sort_values(xcol) for _, s in g.groupby("seed")]
            x_hi = min(r[xcol].max() for r in runs)
            x_lo = max(r[xcol].min() for r in runs)
            if x_hi <= x_lo:
                x_lo = min(r[xcol].min() for r in runs)
            grid = np.linspace(x_lo, x_hi, n_grid)
            ys = np.array([np.interp(grid, r[xcol], r[m].rolling(smooth, min_periods=1).mean()) for r in runs])
            mu, sd = ys.mean(0), ys.std(0) if len(runs) > 1 else np.zeros(n_grid)
            ax.plot(grid, mu, color=col[name], label=f"{name} (n={len(runs)})")
            ax.fill_between(grid, mu - sd, mu + sd, color=col[name], alpha=0.2, linewidth=0)
        ax.set_xlabel("pasos de entorno" if xcol == "env_steps" else "episodio")
        ax.set_ylabel(METRICS.get(m, (m,))[0] if m != "return" else "Retorno por episodio")
        ax.set_title(f"{exp}: {m}")
    axes[0][0].legend()
    return save_fig(fig, f"{exp}_learning_curves", out_dir)


# ------------------------------------------------------------------ bars with CI95
def bar_chart(df: pd.DataFrame, name: str, metrics=("mean_waiting_time", "throughput_veh_h"), out_dir=FIG_DIR,
              title: str = "") -> list[Path]:
    """Grouped bars (x = scenario, one bar per method) with 95 % CI error bars, one panel per metric."""
    apply_style()
    metrics = [m for m in metrics if m in df]
    if df.empty or not metrics:
        return []
    agg = aggregate(df, metrics)
    methods = list(dict.fromkeys(df["method"]))
    scenarios = list(dict.fromkeys(df["scenario"]))
    col = colors_for(methods)
    w = 0.8 / len(methods)
    fig, axes = plt.subplots(1, len(metrics), figsize=(4.6 * len(metrics), 3.8), squeeze=False)
    for ax, m in zip(axes[0], metrics):
        for i, meth in enumerate(methods):
            sub = agg[(agg["metric"] == m) & (agg["method"] == meth)].set_index("scenario").reindex(scenarios)
            ax.bar(np.arange(len(scenarios)) + (i - (len(methods) - 1) / 2) * w, sub["mean"], w * 0.92,
                   yerr=sub["ci95"].fillna(0), capsize=2.5, color=col[meth], label=meth, error_kw={"lw": 1})
        ax.set_xticks(range(len(scenarios)), scenarios, rotation=20, ha="right")
        ax.set_ylabel(METRICS[m][0])
        ax.set_title("↓ menor es mejor" if METRICS[m][1] else "↑ mayor es mejor", fontsize=9)
    legend_below(fig, axes[0][0])
    if title:
        fig.suptitle(title, y=1.04)
    return save_fig(fig, name, out_dir)


def eval_bars(exp: str, runs_dir=RUNS_DIR, out_dir=FIG_DIR, metrics=("mean_waiting_time", "throughput_veh_h")) -> list[Path]:
    df = load_eval(runs_dir, exp)
    return bar_chart(df, f"{exp}_eval_bars", metrics, out_dir, title=f"{exp}: media ± IC95") if not df.empty else []


# ------------------------------------------------------------------ fairness (E8)
def fairness_plot(runs_dir=RUNS_DIR, out_dir=FIG_DIR, name: str = "E8_fairness") -> list[Path]:
    """Per scenario: (left) p95 wait per approach and method, (right) max wait on cross streets."""
    apply_style()
    df = load_csv(runs_dir, "E8/fairness.csv")
    if df.empty:
        return []
    if "variant" in df:
        df = df[df["variant"] == "pico"]
    paths = []
    for sc, d in df.groupby("scenario"):
        ap = approach_frame(d)
        if ap.empty:
            continue
        methods = list(dict.fromkeys(d["method"]))
        approaches = sorted(ap["approach"].unique())
        col = colors_for(methods)
        w = 0.8 / len(methods)
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8), gridspec_kw={"width_ratios": [2.2, 1]})
        agg = aggregate(ap.rename(columns={"approach": "scenario_ap"}), ["p95_wait"], by=("method", "scenario_ap"))
        for i, meth in enumerate(methods):
            sub = agg[agg["method"] == meth].set_index("scenario_ap").reindex(approaches)
            a1.bar(np.arange(len(approaches)) + (i - (len(methods) - 1) / 2) * w, sub["mean"], w * 0.92,
                   yerr=sub["ci95"].fillna(0), capsize=2, color=col[meth], label=meth, error_kw={"lw": 1})
        a1.set_xticks(range(len(approaches)), approaches, rotation=20, ha="right")
        a1.set_ylabel("Espera p95 (s)")
        a1.set_title(f"{sc}: espera p95 por aproximación")
        legend_below(fig, a1)
        mx = aggregate(d, ["max_wait_cross_streets"])
        mx = mx[mx["metric"] == "max_wait_cross_streets"].set_index("method").reindex(methods)
        a2.bar(range(len(methods)), mx["mean"], 0.7, yerr=mx["ci95"].fillna(0), capsize=2, color=[col[m] for m in methods], error_kw={"lw": 1})
        a2.set_xticks(range(len(methods)), methods, rotation=40, ha="right")
        a2.set_title("Espera máx. calles transversales (s)")
        paths += save_fig(fig, f"{name}_{sc}", out_dir)
    return paths


# ------------------------------------------------------------------ robustness (E7)
def robustness_plot(runs_dir=RUNS_DIR, out_dir=FIG_DIR, name: str = "E7_robustness",
                    metric: str = "mean_waiting_time") -> list[Path]:
    """Grouped bars: x = perturbation (variant), bars = methods; one panel per base network."""
    apply_style()
    df = load_csv(runs_dir, "E7/robustness.csv")
    if df.empty or metric not in df:
        return []
    bases = list(dict.fromkeys(df.get("base", pd.Series(["all"] * len(df)))))
    if "base" not in df:
        df["base"] = "all"
    fig, axes = plt.subplots(1, len(bases), figsize=(6.2 * len(bases), 3.8), squeeze=False)
    col = colors_for(df["method"])
    for ax, base in zip(axes[0], bases):
        d = df[df["base"] == base]
        agg = aggregate(d, [metric], by=("method", "variant"))
        variants = list(dict.fromkeys(d["variant"]))
        methods = list(dict.fromkeys(d["method"]))
        w = 0.8 / len(methods)
        for i, meth in enumerate(methods):
            sub = agg[agg["method"] == meth].set_index("variant").reindex(variants)
            ax.bar(np.arange(len(variants)) + (i - (len(methods) - 1) / 2) * w, sub["mean"], w * 0.92,
                   yerr=sub["ci95"].fillna(0), capsize=2, color=col[meth], label=meth, error_kw={"lw": 1})
        ax.set_xticks(range(len(variants)), variants, rotation=15)
        ax.set_ylabel(METRICS[metric][0])
        ax.set_title(f"E7 generalización ({base})")
    legend_below(fig, axes[0][0])
    return save_fig(fig, name, out_dir)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, help="E1..E8")
    ap.add_argument("--runs-dir", default=str(RUNS_DIR))
    ap.add_argument("--out-dir", default=str(FIG_DIR))
    ap.add_argument("--smooth", type=int, default=1, help="rolling-mean window (episodes) for learning curves")
    a = ap.parse_args(argv)
    exp = a.exp.upper()
    if exp == "E7":
        paths = robustness_plot(a.runs_dir, a.out_dir)
    elif exp == "E8":
        paths = fairness_plot(a.runs_dir, a.out_dir)
    else:
        paths = eval_bars(exp, a.runs_dir, a.out_dir) + learning_curves(exp, a.runs_dir, a.out_dir, smooth=a.smooth)
    print("\n".join(map(str, paths)) if paths else f"{exp}: no data in {a.runs_dir}")


if __name__ == "__main__":
    main()
