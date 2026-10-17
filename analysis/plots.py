"""Figuras del informe (solo matplotlib). PNG + PDF van a docs/figures/.

    python -m analysis.plots --exp E3
    python -m analysis.plots --exp E7 --runs-dir runs --out-dir docs/figures

Convenciones: barras = media; barras de error = IC95 (t de Student) sobre las réplicas; los puntos son las réplicas
(semillas de entrenamiento si el método tiene varias, episodios de evaluación en las líneas base). Colores y
nombres en `analysis/style.py`.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter
from matplotlib.lines import Line2D

from analysis import style
from analysis.data import (BAR_METRICS, BASELINE_METHODS, FIG_DIR, METRICS, RUNS_DIR, approach_frame, available, ci95,
                           load_csv, load_fairness, load_master, load_train_logs, unit_values)
from analysis.specs import exp_frame, scenario_order, spec
from analysis.style import (apply_style, color, footnote, label, legend_below, scen_label, sort_methods, variant_label)

SHORT_METRIC = {"total_delay": "Demora total", "mean_waiting_time": "Espera media", "backlog_pct": "Backlog",
                "max_wait_cross_streets": "Espera máx. transversal", "co2_kg": "CO₂", "mean_travel_time": "Tiempo de viaje",
                "throughput_veh_h": "Throughput", "mean_stops": "Paradas"}
NOTE_REPLICAS = ("Barras: media ± IC95. Réplicas: semillas de entrenamiento (n=5) en los métodos aprendidos; "
                 "episodios de evaluación (n=10) en las líneas base. El número sobre cada barra es la media.")


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


def _pct(v, _pos=None) -> str:
    return f"{v:.0f} %"


def _kfmt(v, _pos=None) -> str:
    return f"{v / 1000:g} k"


def _bar(ax, x, mean, ci, w, m, ctx=None, vals=None, text=None, text_size=7.5, rng=None):
    ax.bar(x, mean, w, color=color(m), hatch=style.HATCH.get(m, ""),
           edgecolor="#333333" if m in style.HATCH else "white", linewidth=0.6, label=label(m, ctx),
           yerr=None if pd.isna(ci) else ci, capsize=2.5, error_kw={"lw": 1.1, "ecolor": "#222222"}, zorder=2)
    if vals is not None and len(vals) > 1:
        rng = rng or np.random.default_rng(0)
        ax.scatter(x + rng.uniform(-0.22, 0.22, len(vals)) * w, vals, s=6, color="#111111", alpha=0.5, zorder=3, lw=0)
    if text is not None:
        top = mean + (0 if pd.isna(ci) else ci)
        ax.annotate(text, (x, top), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom",
                    fontsize=text_size, rotation=90, color="#222222", zorder=4)


def bar_panel(ax, df, methods, groups, metric, groupcol="scenario", ctx=None, group_labels=None, annotate=True,
              dots=False, digits=0) -> None:
    """Barras agrupadas: x = `groups`, una barra por método, con IC95 y las réplicas como puntos."""
    n = len(methods)
    w = 0.84 / max(n, 1)
    rng = np.random.default_rng(0)
    for i, m in enumerate(methods):
        for j, g in enumerate(groups):
            sub = df[(df["method"] == m) & (df[groupcol] == g)]
            if sub.empty or metric not in sub or sub[metric].isna().all():
                continue
            vals, _ = unit_values(sub, metric)
            mean, ci = float(np.mean(vals)), ci95(vals)
            x = j + (i - (n - 1) / 2) * w
            _bar(ax, x, mean, ci, w * 0.92, m, ctx, vals if dots else None,
                 f"{mean:.{digits}f}" if annotate else None, rng=rng)
    ax.set_xticks(range(len(groups)), [(group_labels or {}).get(g, g) for g in groups])
    ax.margins(y=0.14)
    ax.set_ylim(bottom=0)
    ax.grid(axis="x", visible=False)


def metric_ylabel(m: str) -> str:
    return METRICS.get(m, (m, True))[0]


def metric_title(m: str) -> str:
    lower = METRICS.get(m, (m, True))[1]
    return f"{SHORT_METRIC.get(m, m)}  ({'↓ menor' if lower else '↑ mayor'} es mejor)"


# ------------------------------------------------------------------ barras de evaluación final
def bar_chart(df: pd.DataFrame, name: str, metrics=BAR_METRICS, out_dir=FIG_DIR, title: str = "", methods=None,
              groups=None, ctx=None, annotate: bool = True) -> list[Path]:
    """Barras agrupadas (x = escenario, una barra por método) con IC95, un panel por métrica.

    Paneles por defecto: demora total (cuenta los vehículos que nunca entraron), espera media por vehículo
    insertado y backlog %. Las métricas que no existen en los datos (CSV viejos) se omiten."""
    apply_style()
    metrics = available(df, metrics)
    if df.empty or not metrics:
        return []
    methods = methods or sort_methods(df["method"])
    groups = groups or list(dict.fromkeys(df["scenario"]))
    pw = float(np.clip(0.42 * len(methods) * len(groups) + 1.6, 5.0, 6.3))
    fig, axes = plt.subplots(1, len(metrics), figsize=(pw * len(metrics), 4.8), squeeze=False)
    for ax, m in zip(axes[0], metrics):
        bar_panel(ax, df, methods, groups, m, "scenario", ctx, {g: scen_label(g) for g in groups}, annotate,
                  digits=1 if m == "backlog_pct" else 0)
        ax.set_ylabel(metric_ylabel(m))
        ax.set_title(metric_title(m))
    legend_below(fig, methods, ctx, note=NOTE_REPLICAS)
    fig.suptitle(title or "", fontsize=13, fontweight="bold")
    return save_fig(fig, name, out_dir)


def eval_bars(exp: str, runs_dir=RUNS_DIR, out_dir=FIG_DIR, metrics=BAR_METRICS) -> list[Path]:
    exp = exp.upper()
    df = exp_frame(load_master(runs_dir), exp)
    if df.empty:
        return []
    methods = sort_methods(df["method"])
    groups = scenario_order(df, exp)
    n_sc = len(groups)
    title = f"{spec(exp)['title']}: evaluación final (semillas 1000 a 1009)"
    apply_style()
    metrics = available(df, metrics)
    if not metrics:
        return []
    pw = float(np.clip(0.42 * len(methods) * n_sc + 1.6, 5.0, 6.3))
    fig, axes = plt.subplots(1, len(metrics), figsize=(pw * len(metrics), 4.8), squeeze=False)
    for ax, m in zip(axes[0], metrics):
        bar_panel(ax, df, methods, groups, m, "scenario", None, {g: scen_label(g) for g in groups},
                  annotate=len(methods) * n_sc <= 40, digits=1 if m == "backlog_pct" else 0)
        ax.set_ylabel(metric_ylabel(m))
        ax.set_title(metric_title(m))
    learned = [m for m in methods if m not in style.BASELINES]
    legend_below(fig, methods, note=NOTE_REPLICAS if learned else
                 "Barras: media ± IC95 sobre los 10 episodios de evaluación (n=10). El número sobre cada barra es la media.")
    fig.suptitle(title, fontsize=13, fontweight="bold")
    return save_fig(fig, f"{exp}_eval_bars", out_dir)


# ------------------------------------------------------------------ curvas de aprendizaje
def _curve_stats(runs: list[pd.DataFrame], xcol: str, ycol: str, smooth: int, grid: np.ndarray):
    ys = np.array([np.interp(grid, r[xcol], r[ycol].rolling(smooth, min_periods=1).mean()) for r in runs])
    mu = ys.mean(0)
    half = np.array([ci95(ys[:, k]) for k in range(ys.shape[1])]) if len(runs) > 1 else np.zeros_like(mu)
    return mu, np.nan_to_num(half)


def _train_logs_for(exp: str, runs_dir) -> pd.DataFrame:
    logs = load_train_logs(runs_dir, None)
    if logs.empty:
        return logs
    s = spec(exp)
    keep = (logs["exp"] == exp.upper()) | (logs["name"].isin(s["extra_methods"]) & (logs["exp"] != exp.upper()))
    return logs[keep]


def load_selection(runs_dir=RUNS_DIR, exp: str | None = None) -> pd.DataFrame:
    """Todos los selection.csv (validación de cada checkpoint en VAL_SEEDS) con exp, name, seed y env_steps."""
    from analysis.data import _is_exp_dir, _tag
    frames = []
    runs_dir = Path(runs_dir)
    for f in sorted(runs_dir.glob(f"{exp or '*'}/*/seed*/selection.csv")):
        if not _is_exp_dir(f, runs_dir):
            continue
        d = pd.read_csv(f)
        if d.empty or "total_delay" not in d:
            continue
        d["exp"], d["name"], d["seed"] = _tag(f, runs_dir)
        tl = f.parent / "train_log.csv"
        if tl.exists():
            t = pd.read_csv(tl)
            if "env_steps" in t:  # episodio del checkpoint -> pasos de entorno (episodios 1-indexados: fila episode-1)
                steps = dict(zip(t["episode"] + 1, t["env_steps"]))
                d["env_steps"] = d["episode"].map(steps)
        frames.append(d)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _baseline_lines(ax, master: pd.DataFrame, scenario: str | None, metric: str = "total_delay") -> list:
    handles = []
    if scenario is None or master.empty:
        return handles
    for b, ls in (("fixed", (0, (4, 2))), ("max_pressure", (0, (1, 1.5)))):
        sub = master[(master["method"] == b) & (master["scenario"] == scenario)]
        if sub.empty or metric not in sub:
            continue
        v = float(sub[metric].mean())
        ax.axhline(v, color=color(b), ls=ls, lw=1.6, zorder=1)
        handles.append(Line2D([0], [0], color=color(b), ls=ls, lw=1.6, label=f"{label(b)} (evaluación)"))
    return handles


def learning_curves(exp: str, runs_dir=RUNS_DIR, out_dir=FIG_DIR, metrics=("return",), smooth: int = 10,
                    n_grid: int = 100, validation: bool = True) -> list[Path]:
    """Curvas de aprendizaje contra pasos de entorno (eficiencia de muestras).

    Paneles: cada columna de `train_log.csv` en `metrics` (por defecto el retorno de entrenamiento, suavizado con una
    media móvil de `smooth` episodios) y, si hay `selection.csv`, la demora total de validación de cada checkpoint
    (VAL_SEEDS, escenario de entrenamiento, escala log). Banda = IC95 entre semillas de entrenamiento. Columnas que
    el log no tiene se omiten."""
    apply_style()
    exp = exp.upper()
    logs = _train_logs_for(exp, runs_dir)
    if logs.empty:
        return []
    cols = available(logs, metrics)
    sel = load_selection(runs_dir, None) if validation else pd.DataFrame()
    if not sel.empty:
        s = spec(exp)
        sel = sel[(sel["exp"] == exp) | (sel["name"].isin(s["extra_methods"]) & (sel["exp"] != exp))]
        sel = sel[sel["name"].isin(set(logs["name"]))]
    if not cols and sel.empty:
        return []
    xcol = "env_steps" if "env_steps" in logs else "episode"
    names = sort_methods(logs["name"])
    master = load_master(runs_dir)
    npan = len(cols) + (0 if sel.empty else 1)
    fig, axes = plt.subplots(1, npan, figsize=(6.0 * npan, 4.4), squeeze=False)
    axes = list(axes[0])
    handles = []
    for ax, m in zip(axes, cols):
        lo_all, hi_all = [], []
        for name in names:
            g = logs[logs["name"] == name]
            runs = [s_.sort_values(xcol) for _, s_ in g.groupby("seed")]
            x_hi = min(r[xcol].max() for r in runs)
            x_lo = max(r[xcol].min() for r in runs)
            if x_hi <= x_lo:
                x_lo = min(r[xcol].min() for r in runs)
            grid = np.linspace(x_lo, x_hi, n_grid)
            for r_ in runs:  # cada semilla, línea fina
                ax.plot(grid, np.interp(grid, r_[xcol], r_[m].rolling(smooth, min_periods=1).mean()), color=color(name),
                        lw=0.7, alpha=0.22, zorder=2)
            mu, _half = _curve_stats(runs, xcol, m, smooth, grid)
            ax.plot(grid, mu, color=color(name), lw=2.2, zorder=3)
        ax.set_xlabel("Pasos de entorno")
        ax.xaxis.set_major_formatter(FuncFormatter(_kfmt))
        if m == "return":  # arranque con retornos 10 a 100 veces peores: escala symlog
            ax.set_yscale("symlog", linthresh=100)
            ax.set_yticks([-10000, -3000, -1000, -300, -100, 0])
            ax.set_ylim(top=30)
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", " ")))
        ax.set_ylabel("Retorno por episodio (escala symlog)" if m == "return" else metric_ylabel(m))
        ax.set_title(f"Retorno de entrenamiento (media móvil de {smooth} ep.)" if m == "return" else m)
    if not sel.empty:
        ax = axes[-1]
        xs = "env_steps" if "env_steps" in sel and sel["env_steps"].notna().any() else "episode"
        for name in names:
            g = sel[sel["name"] == name]
            if g.empty:
                continue
            for _, s_ in g.groupby("seed"):
                s_ = s_.sort_values("episode")
                ax.plot(s_[xs], s_["total_delay"], color=color(name), lw=0.8, alpha=0.28, zorder=2)
            p = g.groupby("episode").agg(x=(xs, "first"), mu=("total_delay", "mean"))
            ax.plot(p["x"], p["mu"], color=color(name), lw=2.2, marker="o", ms=4, zorder=3)
        handles = _baseline_lines(ax, master, spec(exp)["train_scenario"])
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.set_xlabel("Pasos de entorno" if xs == "env_steps" else "Episodio")
        if xs == "env_steps":
            ax.xaxis.set_major_formatter(FuncFormatter(_kfmt))
        ax.set_ylabel("Demora total en validación (s/veh)")
        ax.set_title("Demora total por checkpoint (validación, escala log)")
    hs = style.legend_handles(names)
    n_seeds = int(logs.groupby("name")["seed"].nunique().max())
    style.fig_legend(fig, hs + handles, min(5, len(hs) + len(handles)),
                     f"Línea gruesa: media entre {n_seeds} semillas de entrenamiento (líneas finas: cada semilla; las de validación "
                     "con 2 episodios). Líneas base: evaluación final, solo de referencia.")
    fig.suptitle(f"{spec(exp)['title']}: curvas de aprendizaje", fontsize=13, fontweight="bold")
    return save_fig(fig, f"{exp}_learning_curves", out_dir)


# ------------------------------------------------------------------ resumen: demora total de todos los métodos
def headline_plot(runs_dir=RUNS_DIR, out_dir=FIG_DIR, name: str = "resumen_demora_total",
                  scenarios=("reforma_pico", "cruce_pico")) -> list[Path]:
    """Demora total de todos los métodos en el corredor y en el cruce de pico, ordenados por familia."""
    apply_style()
    master = load_master(runs_dir)
    if master.empty or "total_delay" not in master:
        return []
    scenarios = [s for s in scenarios if (master["scenario"] == s).any()]
    if not scenarios:
        return []
    fig, axes = plt.subplots(1, len(scenarios), figsize=(7.2 * len(scenarios), 6.4), squeeze=False)
    rng = np.random.default_rng(1)
    for ax, sc in zip(axes[0], scenarios):
        d = master[master["scenario"] == sc]
        ms = sort_methods(d["method"])
        for k, m in enumerate(ms):
            vals, unit = unit_values(d[d["method"] == m], "total_delay")
            mean, ci = float(np.mean(vals)), ci95(vals)
            y = k
            ax.barh(y, mean, 0.72, color=color(m), hatch=style.HATCH.get(m, ""),
                    edgecolor="#333333" if m in style.HATCH else "white", xerr=None if pd.isna(ci) else ci,
                    capsize=2.5, error_kw={"lw": 1.1})
            ax.scatter(vals, y + rng.uniform(-0.2, 0.2, len(vals)), s=7, color="#111111", alpha=0.5, zorder=3, lw=0)
            ax.annotate(f"{mean:.0f}", (mean + (0 if pd.isna(ci) else ci), y), xytext=(4, 0), textcoords="offset points",
                        va="center", fontsize=8.5)
        ax.set_yticks(range(len(ms)), [label(m) for m in ms])
        ax.invert_yaxis()
        for b in ("fixed", "max_pressure"):
            if b in ms:
                ax.axvline(float(d[d["method"] == b]["total_delay"].mean()), color=color(b), ls=(0, (3, 2)), lw=1.2, zorder=1)
        ax.set_xlabel(metric_ylabel("total_delay"))
        ax.set_title(f"{scen_label(sc, flat=True)}  (↓ menor es mejor)")
        ax.margins(x=0.12)
        ax.grid(axis="y", visible=False)
        # separadores de familia
        fam = [style.family(m) for m in ms]
        for k in range(1, len(ms)):
            if fam[k] != fam[k - 1]:
                ax.axhline(k - 0.5, color="#999999", lw=0.8)
    fig.suptitle("Demora total de todos los métodos (evaluación final)", fontsize=13, fontweight="bold")
    footnote(fig, "Barras: media ± IC95. Puntos: réplicas (semillas de entrenamiento, n=5, o episodios de evaluación, "
                  "n=10 en las líneas base). Líneas punteadas: tiempo fijo y max-pressure.")
    return save_fig(fig, name, out_dir)


# ------------------------------------------------------------------ equidad (E8)
def _approach_order(aps) -> list[str]:
    cross = sorted([a for a in aps if style.is_cross_street(a)])
    main = sorted([a for a in aps if not style.is_cross_street(a)])
    return main + cross


def fairness_plot(runs_dir=RUNS_DIR, out_dir=FIG_DIR, name: str = "E8_fairness") -> list[Path]:
    """Por escenario: mapa de calor de la espera p95 por aproximación (filas = métodos) y, a la derecha, la espera
    máxima en calles transversales con IC95 (las mismas filas)."""
    apply_style()
    df = load_fairness(runs_dir)
    if df.empty:
        return []
    paths = []
    for sc in dict.fromkeys(df["scenario"]):
        d = df[df["scenario"] == sc]
        ap = approach_frame(d)
        if ap.empty:
            continue
        methods = sort_methods(d["method"])
        approaches = _approach_order(ap["approach"].unique())
        mat = np.full((len(methods), len(approaches)), np.nan)
        for i, m in enumerate(methods):
            for j, a in enumerate(approaches):
                sub = ap[(ap["method"] == m) & (ap["approach"] == a)]
                if len(sub):
                    mat[i, j] = float(np.mean(unit_values(sub.rename(columns={"p95_wait": "v"}), "v")[0]))
        h = 0.42 * len(methods) + 2.4
        fig = plt.figure(figsize=(max(9, 1.15 * len(approaches) + 6.5), h))
        gs = fig.add_gridspec(1, 2, width_ratios=[max(2.0, 0.62 * len(approaches)), 1.5])
        a1, a2 = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
        im = a1.imshow(mat, aspect="auto", cmap="YlOrRd", vmin=0, vmax=np.nanpercentile(mat, 97))
        a1.grid(False)
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                if not np.isnan(mat[i, j]):
                    a1.text(j, i, f"{mat[i, j]:.0f}", ha="center", va="center", fontsize=8.5,
                            color="white" if mat[i, j] > 0.62 * np.nanpercentile(mat, 97) else "#222222")
        a1.set_xticks(range(len(approaches)), [style.approach_label(a) for a in approaches], rotation=35, ha="right")
        a1.set_yticks(range(len(methods)), [label(m) for m in methods])
        a1.tick_params(length=0)
        a1.spines[:].set_visible(False)
        n_main = sum(not style.is_cross_street(a) for a in approaches)
        if 0 < n_main < len(approaches):
            a1.axvline(n_main - 0.5, color="white", lw=3)
            a1.text(n_main / 2 - 0.5, -0.62, "Reforma", ha="center", fontsize=9, color="#555555")
            a1.text(n_main + (len(approaches) - n_main) / 2 - 0.5, -0.62, "Calles transversales", ha="center", fontsize=9,
                    color="#555555")
        fam = [style.family(m) for m in methods]
        for k in range(1, len(methods)):
            if fam[k] != fam[k - 1]:
                a1.axhline(k - 0.5, color="white", lw=3)
        cb = fig.colorbar(im, ax=a1, pad=0.01, fraction=0.04)
        cb.set_label("Espera p95 (s)")
        a1.set_title(f"{scen_label(sc, flat=True)}: espera p95 por aproximación", pad=26)
        for i, m in enumerate(methods):
            sub = d[d["method"] == m]
            if "max_wait_cross_streets" not in sub or sub["max_wait_cross_streets"].isna().all():
                continue
            vals, _ = unit_values(sub, "max_wait_cross_streets")
            mean, ci = float(np.mean(vals)), ci95(vals)
            a2.barh(i, mean, 0.7, color=color(m), hatch=style.HATCH.get(m, ""),
                    edgecolor="#333333" if m in style.HATCH else "white", xerr=None if pd.isna(ci) else ci, capsize=2.5,
                    error_kw={"lw": 1.1})
            a2.scatter(vals, i + np.random.default_rng(i).uniform(-0.18, 0.18, len(vals)), s=6, color="#111111",
                       alpha=0.5, zorder=3, lw=0)
        a2.set_ylim(len(methods) - 0.5, -0.5)
        a2.set_yticks([])
        a2.set_xlabel(metric_ylabel("max_wait_cross_streets"))
        a2.set_title("Espera máx. en transversales")
        a2.grid(axis="y", visible=False)
        a2.margins(x=0.1)
        fig.suptitle("Equidad entre aproximaciones", fontsize=13, fontweight="bold")
        footnote(fig, "Celdas y barras: media entre réplicas (semillas de entrenamiento, n=5, o episodios de evaluación, n=10, "
                      "en las líneas base). Barras de error: IC95.")
        paths += save_fig(fig, f"{name}_{sc}", out_dir)
    return paths


def _place_labels(ax, pts, texts, colors, fontsize=9) -> None:
    """Etiquetas junto a los puntos: prueba varias posiciones y elige la que menos pisa a otras etiquetas y a los
    puntos; las que quedan lejos llevan una línea guía."""
    fig = ax.figure
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    placed: list = []
    cand = [(9, 7, "left", "bottom"), (9, -7, "left", "top"), (-9, 7, "right", "bottom"), (-9, -7, "right", "top"),
            (0, 11, "center", "bottom"), (0, -11, "center", "top"), (11, 0, "left", "center"), (-11, 0, "right", "center"),
            (26, 24, "left", "bottom"), (-26, 24, "right", "bottom"), (26, -24, "left", "top"), (-26, -24, "right", "top"),
            (0, 38, "center", "bottom"), (0, -38, "center", "top"), (44, 0, "left", "center"), (-44, 0, "right", "center")]
    pt_xy = [ax.transData.transform(p) for p in pts]
    axbb = ax.get_window_extent(rend)
    for p, t, c in sorted(zip(pts, texts, colors), key=lambda z: (z[0][1], z[0][0])):
        best, best_cost = None, 1e18
        for k, (dx, dy, ha, va) in enumerate(cand):
            tx = ax.annotate(t, p, xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, fontsize=fontsize)
            bb = tx.get_window_extent(rend)
            cost = sum(bb.overlaps(o) * 100 for o in placed) + k * 1.5
            cost += sum(bb.x0 - 5 < q[0] < bb.x1 + 5 and bb.y0 - 5 < q[1] < bb.y1 + 5 for q in pt_xy) * 40
            cost += 300 * (bb.x0 < axbb.x0 or bb.x1 > axbb.x1 or bb.y0 < axbb.y0 or bb.y1 > axbb.y1)
            tx.remove()
            if cost < best_cost:
                best, best_cost = (dx, dy, ha, va), cost
        dx, dy, ha, va = best
        far = abs(dx) > 14 or abs(dy) > 14
        tx = ax.annotate(t, p, xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, fontsize=fontsize, color=c,
                         fontweight="bold", zorder=6, bbox=dict(fc="white", ec="none", alpha=0.75, pad=0.8),
                         arrowprops=dict(arrowstyle="-", lw=0.7, color="#777777", shrinkA=0, shrinkB=5) if far else None)
        placed.append(tx.get_window_extent(rend))


def tradeoff_plot(runs_dir=RUNS_DIR, out_dir=FIG_DIR, scenario: str = "reforma_pico",
                  name: str | None = None) -> list[Path]:
    """Demora total (eficiencia) contra espera máxima en transversales (equidad), con IC95 en los dos ejes.
    Las flechas unen QMIX con QMIX equitativo y comunicación con comunicación equitativa."""
    apply_style()
    df = load_fairness(runs_dir)
    if df.empty:
        return []
    d = df[df["scenario"] == scenario]
    if d.empty or available(d, ["total_delay", "max_wait_cross_streets"]) != ["total_delay", "max_wait_cross_streets"]:
        return []
    ms = sort_methods(d["method"])
    fig, ax = plt.subplots(figsize=(9.2, 6.4))
    stats = {}
    mk = {"baseline": "s", "single": "o", "marl": "D"}
    for m in ms:
        sub = d[d["method"] == m]
        vx, _ = unit_values(sub, "max_wait_cross_streets")
        vy, _ = unit_values(sub, "total_delay")
        stats[m] = (float(np.mean(vx)), float(np.mean(vy)), ci95(vx), ci95(vy))
        x, y, ex, ey = stats[m]
        ax.errorbar(x, y, xerr=None if pd.isna(ex) else ex, yerr=None if pd.isna(ey) else ey, fmt="none",
                    ecolor=color(m), elinewidth=1.0, capsize=2, alpha=0.4, zorder=2)
        fair = m in style.HATCH
        ax.scatter([x], [y], s=105, marker=mk[style.family(m)], facecolor="white" if fair else color(m),
                   edgecolor=color(m), linewidth=2.2 if fair else 0.8, zorder=3)
    for a, b in (("qmix", "qmix_fair"), ("comm", "comm_fair")):
        if a in stats and b in stats:
            ax.annotate("", xy=stats[b][:2], xytext=stats[a][:2], arrowprops=dict(arrowstyle="->", color=color(a), lw=1.5,
                        ls="--", shrinkA=8, shrinkB=8), zorder=2)
    xs_, ys_ = [v[0] for v in stats.values()], [v[1] for v in stats.values()]
    px, py = 0.14 * (max(xs_) - min(xs_)), 0.14 * (max(ys_) - min(ys_))
    ax.set_xlim(min(xs_) - px, max(xs_) + 1.3 * px)  # zoom a las medias: las barras de error largas se recortan
    ax.set_ylim(min(ys_) - py, max(ys_) + py)
    _place_labels(ax, [stats[m][:2] for m in ms], [label(m) for m in ms],
                  [color(m) if m not in ("fixed", "actuated") else "#555555" for m in ms])
    ax.set_xlabel("Espera máxima en calles transversales (s)")
    ax.set_ylabel("Demora total (s por vehículo demandado)")
    ax.set_title(f"Eficiencia contra equidad: {scen_label(scenario, flat=True)}")
    ax.text(0.015, 0.02, "mejor: abajo y a la izquierda", transform=ax.transAxes, color="#777777", fontsize=10)
    handles = []
    if any(style.family(m) == "baseline" for m in ms):
        handles.append(Line2D([0], [0], marker="s", ls="", color="#888888", label="Líneas base"))
    if any(style.family(m) == "single" for m in ms):
        handles.append(Line2D([0], [0], marker="o", ls="", color="#888888", label="Agente único"))
    if any(style.family(m) == "marl" for m in ms):
        handles.append(Line2D([0], [0], marker="D", ls="", color="#888888", label="Multiagente"))
    if any(m in style.HATCH for m in ms):
        handles.append(Line2D([0], [0], marker="D", mfc="white", mew=2, ls="", color="#888888", label="Variante equitativa (hueca)"))
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=len(handles))
    footnote(fig, "Puntos: media entre réplicas; cruces: IC95 (semillas de entrenamiento, n=5, o episodios de evaluación, n=10, "
                  "en las líneas base). " + ("Flechas: efecto de la penalización de equidad. " if any(m in style.HATCH for m in ms) else "")
             + "Los ejes se acercan a las medias y recortan las barras de error más largas.")
    return save_fig(fig, name or f"E8_tradeoff_{scenario}", out_dir)


# ------------------------------------------------------------------ robustez (E7)
def _boot_ratio(x: np.ndarray, ref: np.ndarray, n_boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Cociente mean(x)/mean(ref) con IC95 bootstrap (percentiles) sobre las semillas de evaluación: (cociente, bajo, alto)."""
    rng = np.random.default_rng(seed)
    x, ref = np.asarray(x, float), np.asarray(ref, float)
    r = x.mean() / ref.mean()
    ix = rng.integers(0, len(x), (n_boot, len(x)))
    ir = rng.integers(0, len(ref), (n_boot, len(ref)))
    b = x[ix].mean(1) / ref[ir].mean(1)
    lo, hi = np.percentile(b, [2.5, 97.5])
    return float(r), float(min(lo, r)), float(max(hi, r))


def _rob_frame(runs_dir) -> pd.DataFrame:
    df = load_csv(runs_dir, "E7/robustness.csv")
    if df.empty:
        return df
    if "base" not in df:
        df["base"] = "all"
    if "variant" not in df:
        df["variant"] = "pico"
    return df


def _rob_metric(df: pd.DataFrame, metric: str) -> str | None:
    """`metric` si existe; si el CSV es viejo (sin total_delay), la espera media."""
    for m in (metric, "mean_waiting_time"):
        if not df.empty and available(df, [m]):
            return m
    return None


BASE_LABEL = {"cruce": "Cruce C12 (1 semáforo)", "reforma": "Corredor Reforma (5 semáforos)", "all": "Todos"}
E7_NOTE = ("Barras: media ± IC95 sobre los 10 episodios de evaluación (semillas 1000 a 1009). Los agentes aprendidos son UNA "
           "sola semilla de entrenamiento elegida por validación: el IC no incluye la variabilidad entre semillas de entrenamiento.")


def robustness_plot(runs_dir=RUNS_DIR, out_dir=FIG_DIR, name: str = "E7_robustness",
                    metric: str = "total_delay") -> list[Path]:
    """Matriz de paneles: fila = red (cruce, corredor), columna = variante de evaluación; barras = métodos con IC95.
    Cada panel tiene su propia escala (el incidente multiplica la demora por 10)."""
    apply_style()
    df = _rob_frame(runs_dir)
    metric = _rob_metric(df, metric)
    if df.empty or metric is None:
        return []
    bases = list(dict.fromkeys(df["base"]))
    variants = list(dict.fromkeys(df["variant"]))
    ms_all = sort_methods(df["method"])
    fig, axes = plt.subplots(len(bases), len(variants), figsize=(3.9 * len(variants), 3.6 * len(bases) + 0.5), squeeze=False)
    for r, base in enumerate(bases):
        for c, v in enumerate(variants):
            ax = axes[r][c]
            d = df[(df["base"] == base) & (df["variant"] == v)]
            ms = [m for m in ms_all if m in set(d["method"])]
            for k, m in enumerate(ms):
                sub = d[d["method"] == m]
                vals, _ = unit_values(sub, metric)
                mean, ci = float(np.mean(vals)), ci95(vals)
                _bar(ax, k, mean, ci, 0.78, m, "E7", None, f"{mean:.0f}" if mean >= 10 else f"{mean:.1f}", 8.5)
            ax.set_xticks([])
            ax.set_xlim(-0.6, max(len(ms) - 0.4, 0.6))
            ax.margins(y=0.22)
            ax.set_ylim(bottom=0)
            ax.grid(axis="x", visible=False)
            if r == 0:
                ax.set_title(variant_label(v, flat=False))
            if c == 0:
                ax.set_ylabel(f"{BASE_LABEL.get(base, base)}\n{metric_ylabel(metric)}")
    legend_below(fig, ms_all, "E7", ncol=4, note=E7_NOTE)
    fig.suptitle("E7: generalización fuera de la hora de entrenamiento (demora total)", fontsize=13, fontweight="bold")
    return save_fig(fig, name, out_dir)


def degradation_plot(runs_dir=RUNS_DIR, out_dir=FIG_DIR, name: str = "E7_degradation",
                     metric: str = "total_delay") -> list[Path]:
    """Izquierda: factor por el que cambia la demora de cada método respecto de su propio desempeño en `pico` (escala
    log, 1 = igual). Derecha: diferencia porcentual respecto del tiempo fijo en la misma variante (¿se mantiene la
    ventaja?). IC95 bootstrap sobre los episodios de evaluación."""
    apply_style()
    df = _rob_frame(runs_dir)
    metric = _rob_metric(df, metric)
    if df.empty or metric is None or "fixed" not in set(df["method"]):
        return []
    bases = list(dict.fromkeys(df["base"]))
    fig, axes = plt.subplots(len(bases), 2, figsize=(12.5, 3.9 * len(bases) + 0.6), squeeze=False)
    ms_all = sort_methods(df["method"])
    for r, base in enumerate(bases):
        d = df[df["base"] == base]
        variants = list(dict.fromkeys(d["variant"]))
        ms = [m for m in ms_all if m in set(d["method"])]

        def arr(m, v):
            return d[(d["method"] == m) & (d["variant"] == v)].sort_values("seed")[metric].to_numpy(float)

        for c, ref_kind in enumerate(("pico", "fixed")):
            ax = axes[r][c]
            vs = [v for v in variants if v != "pico"] if ref_kind == "pico" else variants
            msx = ms if ref_kind == "pico" else [m for m in ms if m != "fixed"]
            n = len(msx)
            w = 0.82 / max(n, 1)
            for i, m in enumerate(msx):
                for j, v in enumerate(vs):
                    x_ = arr(m, v)
                    ref = arr(m, "pico") if ref_kind == "pico" else arr("fixed", v)
                    if not len(x_) or not len(ref):
                        continue
                    ratio, lo, hi = _boot_ratio(x_, ref)
                    xpos = j + (i - (n - 1) / 2) * w
                    kw = dict(color=color(m), hatch=style.HATCH.get(m, ""), edgecolor="#333333" if m in style.HATCH else "white",
                              zorder=2, label=label(m, "E7"))
                    if ref_kind == "pico":  # barras desde 1 (escala log)
                        ax.bar(xpos, ratio - 1, w * 0.92, bottom=1, yerr=[[ratio - lo], [hi - ratio]], capsize=2.5,
                               error_kw={"lw": 1.1}, **kw)
                        ax.annotate(f"×{ratio:.1f}", (xpos, max(ratio, 1)), xytext=(0, 3 + (7 if ratio >= 1 else 0)),
                                    textcoords="offset points", ha="center", va="bottom", fontsize=7.5, rotation=90)
                    else:
                        pt, a, b = 100 * (ratio - 1), 100 * (lo - 1), 100 * (hi - 1)
                        ax.bar(xpos, pt, w * 0.92, yerr=[[pt - a], [b - pt]], capsize=2.5, error_kw={"lw": 1.1}, **kw)
            ax.set_xticks(range(len(vs)), [variant_label(v) for v in vs])
            ax.grid(axis="x", visible=False)
            if ref_kind == "pico":
                ax.axhline(1, color="#222222", lw=0.9)
                ax.set_yscale("log")
                ax.set_yticks([0.3, 0.5, 1, 2, 5, 10, 20])
                ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"×{v:g}"))
                ax.margins(y=0.15)
                if r == 0:
                    ax.set_title("Factor respecto de la hora pico (propia), escala log")
                ax.set_ylabel(BASE_LABEL.get(base, base) + "\nDemora total / demora en pico")
            else:
                ax.axhline(0, color="#222222", lw=0.9)
                ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f} %" if v else "0 %"))
                ax.margins(y=0.12)
                if r == 0:
                    ax.set_title("Diferencia respecto del tiempo fijo (misma variante)")
                ax.set_ylabel("Cambio de la demora total\n(< 0: mejor que el tiempo fijo)")
    legend_below(fig, ms_all, "E7", ncol=4, note=E7_NOTE.replace("Barras: media ± IC95 sobre", "Error: IC95 bootstrap sobre"))
    fig.suptitle("E7: degradación y ventaja relativa (demora total)", fontsize=13, fontweight="bold")
    return save_fig(fig, name, out_dir)


# ------------------------------------------------------------------ efecto de la selección: validación por checkpoint
def selection_plot(runs_dir=RUNS_DIR, out_dir=FIG_DIR, methods=None, name: str = "seleccion_validacion",
                   title: str = "Demora total de validación por checkpoint (una línea por semilla de entrenamiento)",
                   ncol: int = 4) -> list[Path]:
    """Una línea por semilla y método: demora total en las semillas de validación de cada checkpoint (cada 20
    episodios). La estrella marca el checkpoint elegido (`best/`). Muestra cuánto oscila la política entre checkpoints.
    Las líneas de referencia (tiempo fijo, max-pressure) son la evaluación final en el escenario de entrenamiento."""
    apply_style()
    sel = load_selection(runs_dir)
    if sel.empty:
        return []
    names = [m for m in sort_methods(sel["name"]) if methods is None or m in methods]
    if not names:
        return []
    ncol = min(ncol, len(names))
    nrow = int(np.ceil(len(names) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(4.0 * ncol, 3.2 * nrow + 0.9), squeeze=False, sharey=True)
    master = load_master(runs_dir)
    for ax in axes.ravel():
        ax.set_visible(False)
    for ax, m in zip(axes.ravel(), names):
        ax.set_visible(True)
        g = sel[sel["name"] == m]
        xs = "env_steps" if g["env_steps"].notna().any() else "episode"
        for sd, s_ in g.groupby("seed"):
            s_ = s_.sort_values("episode")
            ax.plot(s_[xs], s_["total_delay"], color=color(m), alpha=0.6, lw=1.4, marker="o", ms=3)
            ch = s_[s_["selected"].astype(bool)]
            ax.scatter(ch[xs], ch["total_delay"], marker="*", s=130, color=color(m), edgecolor="black", linewidth=0.8, zorder=4)
        exp = g["exp"].iloc[0]
        scenario = spec(exp)["train_scenario"] or ("reforma_pico" if exp == "E8" else None)
        if scenario:
            for b, ls in (("fixed", (0, (4, 2))), ("max_pressure", (0, (1, 1.5)))):
                sub = master[(master["method"] == b) & (master["scenario"] == scenario)]
                if len(sub):
                    ax.axhline(sub["total_delay"].mean(), color=color(b), ls=ls, lw=1.3, zorder=1)
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_major_formatter(FuncFormatter(_kfmt))
        ax.set_title(label(m), fontsize=11)
    for col in range(ncol):
        shown = [axes[i][col] for i in range(nrow) if axes[i][col].get_visible()]
        shown[-1].set_xlabel("Pasos de entorno")
    for ax in axes[:, 0]:
        ax.set_ylabel("Demora total (s/veh)")
    handles = [Line2D([0], [0], marker="*", ls="", mfc="#999999", mec="black", ms=12, label="checkpoint elegido"),
               Line2D([0], [0], color=color("fixed"), ls=(0, (4, 2)), lw=1.6, label="Tiempo fijo (evaluación)"),
               Line2D([0], [0], color=color("max_pressure"), ls=(0, (1, 1.5)), lw=1.6, label="Max-pressure (evaluación)")]
    style.fig_legend(fig, handles, 3, "Cada punto: demora total sobre 2 episodios de validación (semillas 2000 y 2001); "
                                      "escala vertical logarítmica.")
    fig.suptitle(title, fontsize=13, fontweight="bold")
    return save_fig(fig, name, out_dir)


# ------------------------------------------------------------------ CO2
def co2_plot(runs_dir=RUNS_DIR, out_dir=FIG_DIR, scenario: str = "reforma_pico", name: str | None = None) -> list[Path]:
    apply_style()
    df = load_fairness(runs_dir)
    if df.empty or "co2_kg" not in df:
        return []
    d = df[df["scenario"] == scenario]
    if d.empty:
        return []
    ms = sort_methods(d["method"])
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(ms) + 1.8))
    rng = np.random.default_rng(2)
    fixed = d[d["method"] == "fixed"]["co2_kg"].mean() if "fixed" in set(d["method"]) else None
    for k, m in enumerate(ms):
        vals, _ = unit_values(d[d["method"] == m], "co2_kg")
        mean, ci = float(np.mean(vals)), ci95(vals)
        ax.barh(k, mean, 0.7, color=color(m), hatch=style.HATCH.get(m, ""),
                edgecolor="#333333" if m in style.HATCH else "white", xerr=None if pd.isna(ci) else ci, capsize=2.5,
                error_kw={"lw": 1.1})
        ax.scatter(vals, k + rng.uniform(-0.18, 0.18, len(vals)), s=6, color="#111111", alpha=0.5, zorder=3, lw=0)
        txt = f"{mean:,.0f}".replace(",", " ") + (f"  ({100 * (mean / fixed - 1):+.1f} %)".replace("-", "−") if fixed and m != "fixed" else "")
        ax.annotate(txt, (mean + (0 if pd.isna(ci) else ci), k), xytext=(4, 0), textcoords="offset points", va="center", fontsize=8.5)
    ax.set_yticks(range(len(ms)), [label(m) for m in ms])
    ax.invert_yaxis()
    ax.set_xlim(left=0)
    ax.margins(x=0.22)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("CO₂ emitido en la hora simulada (kg)")
    ax.set_title(f"CO₂ por método: {scen_label(scenario, flat=True)}", fontsize=12)
    footnote(fig, "Barras: media ± IC95; puntos: réplicas (semillas de entrenamiento, n=5; episodios, n=10 en líneas base). "
                  "Entre paréntesis: cambio frente al tiempo fijo.")
    return save_fig(fig, name or f"CO2_{scenario}", out_dir)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, help="E1..E8")
    ap.add_argument("--runs-dir", default=str(RUNS_DIR))
    ap.add_argument("--out-dir", default=str(FIG_DIR))
    ap.add_argument("--smooth", type=int, default=10, help="media móvil (episodios) de las curvas de aprendizaje")
    ap.add_argument("--bar-metrics", nargs="+", default=list(BAR_METRICS), help="columnas de eval para las barras")
    ap.add_argument("--curve-metrics", nargs="+", default=["return"],
                    help="columnas de train_log.csv para las curvas de aprendizaje (cualquiera)")
    ap.add_argument("--robust-metric", default="total_delay", help="columna para la figura de E7")
    a = ap.parse_args(argv)
    exp = a.exp.upper()
    if exp == "E7":
        paths = robustness_plot(a.runs_dir, a.out_dir, metric=a.robust_metric) + degradation_plot(
            a.runs_dir, a.out_dir, metric=a.robust_metric)
    elif exp == "E8":
        paths = fairness_plot(a.runs_dir, a.out_dir) + tradeoff_plot(a.runs_dir, a.out_dir)
    else:
        paths = eval_bars(exp, a.runs_dir, a.out_dir, a.bar_metrics) + learning_curves(
            exp, a.runs_dir, a.out_dir, metrics=a.curve_metrics, smooth=a.smooth)
    print("\n".join(map(str, paths)) if paths else f"{exp}: no data in {a.runs_dir}")


if __name__ == "__main__":
    main()
