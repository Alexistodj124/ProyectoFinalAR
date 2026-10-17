"""Markdown (and optional LaTeX) result tables, mean ± CI95, saved to analysis/results/.

    python -m analysis.tables --exp E3 [--latex]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.data import (METRICS, RESULTS_DIR, RUNS_DIR, TABLE_METRICS, aggregate, approach_frame, ci95, load_csv,
                           load_eval, load_train_logs)

NOTE = ("Media ± IC95 (t de Student). Réplica = semilla de entrenamiento si el método tiene varias; "
        "si no, episodios de evaluación. **Negrita** = mejor valor de la columna.")


def fmt(mean: float, ci: float, digits: int = 2) -> str:
    if pd.isna(mean):
        return "-"
    return f"{mean:.{digits}f}" + ("" if pd.isna(ci) else f" ± {ci:.{digits}f}")


def to_markdown(df: pd.DataFrame) -> str:
    cols = [df.index.name or ""] + [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] + ["---:"] * (len(cols) - 1)) + "|"]
    for idx, row in df.iterrows():
        lines.append("| " + " | ".join([str(idx)] + [str(v) for v in row]) + " |")
    return "\n".join(lines)


def to_latex(df: pd.DataFrame, caption: str = "") -> str:
    esc = lambda s: str(s).replace("_", r"\_").replace("±", r"$\pm$").replace("**", "")
    head = " & ".join([esc(df.index.name or "")] + [esc(c) for c in df.columns]) + r" \\"
    body = "\n".join(" & ".join([esc(i)] + [esc(v) for v in r]) + r" \\" for i, r in df.iterrows())
    return ("\\begin{table}[h]\n\\centering\n\\begin{tabular}{l" + "r" * len(df.columns) + "}\n\\toprule\n"
            f"{head}\n\\midrule\n{body}\n\\bottomrule\n\\end{{tabular}}\n\\caption{{{esc(caption)}}}\n\\end{{table}}\n")


def metric_table(agg: pd.DataFrame, rows: str, metrics: list[str], filt: dict | None = None, digits: int = 2) -> pd.DataFrame:
    """Rows = `rows` column of the long aggregate; one column per metric with 'mean ± ci' and the best in bold."""
    a = agg
    for k, v in (filt or {}).items():
        a = a[a[k] == v]
    out = pd.DataFrame(index=pd.Index(list(dict.fromkeys(a[rows])), name=rows))
    for m in metrics:
        s = a[a["metric"] == m].set_index(rows)
        if s.empty:
            continue
        lower = METRICS.get(m, ("", True))[1]
        best = s["mean"].idxmin() if lower else s["mean"].idxmax()
        out[METRICS.get(m, (m,))[0]] = [("**" + fmt(*s.loc[i, ["mean", "ci95"]], digits) + "**") if i == best else
                                         (fmt(*s.loc[i, ["mean", "ci95"]], digits) if i in s.index else "-") for i in out.index]
    return out


def _write(name: str, sections: list[tuple[str, pd.DataFrame]], out_dir: Path, latex: bool, title: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = [f"# {title}", "", NOTE, ""]
    for head, t in sections:
        md += [f"## {head}", "", to_markdown(t), ""]
    paths = [out_dir / f"{name}.md"]
    paths[0].write_text("\n".join(md))
    if latex:
        tex = "\n".join(to_latex(t, f"{title}: {h}") for h, t in sections)
        paths.append(out_dir / f"{name}.tex")
        paths[1].write_text(tex)
    return paths


def eval_tables(exp: str, runs_dir=RUNS_DIR, out_dir=RESULTS_DIR, latex=False) -> list[Path]:
    df = load_eval(runs_dir, exp)
    if df.empty:
        return []
    metrics = [m for m in TABLE_METRICS if m in df]
    agg = aggregate(df, metrics)
    secs = [(sc, metric_table(agg, "method", metrics, {"scenario": sc})) for sc in dict.fromkeys(df["scenario"])]
    return _write(f"{exp}_eval", secs, Path(out_dir), latex, f"{exp}: evaluación final")


def training_table(exp: str, runs_dir=RUNS_DIR, out_dir=RESULTS_DIR, latex=False) -> list[Path]:
    """Last-10 % return and wall time per method, across training seeds."""
    logs = load_train_logs(runs_dir, exp)
    if logs.empty:
        return []
    rows = {}
    for name, g in logs.groupby("name"):
        tail = [s.sort_values("episode")["return"].tail(max(1, len(s) // 10)).mean() for _, s in g.groupby("seed")]
        wall = [s["wall_time"].max() / 60 for _, s in g.groupby("seed")] if "wall_time" in g else [np.nan]
        steps = [s["env_steps"].max() for _, s in g.groupby("seed")] if "env_steps" in g else [np.nan]
        rows[name] = {"semillas": len(tail), "retorno final (último 10 %)": fmt(np.mean(tail), ci95(tail)),
                      "pasos de entorno": f"{np.mean(steps):.0f}", "tiempo (min)": f"{np.mean(wall):.1f}"}
    t = pd.DataFrame(rows).T
    t.index.name = "método"
    return _write(f"{exp}_training", [("Entrenamiento", t)], Path(out_dir), latex, f"{exp}: entrenamiento")


def robustness_table(runs_dir=RUNS_DIR, out_dir=RESULTS_DIR, latex=False) -> list[Path]:
    df = load_csv(runs_dir, "E7/robustness.csv")
    if df.empty:
        return []
    agg = aggregate(df, ["mean_waiting_time"], by=("method", "variant", "base"))
    secs = []
    for base, a in agg.groupby("base"):
        t = pd.DataFrame(index=pd.Index(list(dict.fromkeys(a["method"])), name="método"))
        for v in dict.fromkeys(a["variant"]):
            s = a[a["variant"] == v].set_index("method")
            t[v] = [fmt(*s.loc[i, ["mean", "ci95"]]) if i in s.index else "-" for i in t.index]
        ref = a[a["variant"] == "pico"].set_index("method")["mean"]
        if not ref.empty:  # degradation vs the training hour
            for v in [v for v in dict.fromkeys(a["variant"]) if v != "pico"]:
                s = a[a["variant"] == v].set_index("method")["mean"]
                t[f"Δ% {v}"] = [f"{100 * (s[i] / ref[i] - 1):+.0f} %" if i in s.index and i in ref.index and ref[i] else "-" for i in t.index]
        secs.append((f"{base}: espera media (s)", t))
    return _write("E7_robustness", secs, Path(out_dir), latex, "E7: generalización")


def fairness_table(runs_dir=RUNS_DIR, out_dir=RESULTS_DIR, latex=False) -> list[Path]:
    df = load_csv(runs_dir, "E8/fairness.csv")
    if df.empty:
        return []
    if "variant" in df:
        df = df[df["variant"] == "pico"]
    secs = []
    for sc, d in df.groupby("scenario"):
        ap = approach_frame(d)
        if ap.empty:
            continue
        a = aggregate(ap.rename(columns={"approach": "ap"}), ["p95_wait"], by=("method", "ap"))
        t = pd.DataFrame(index=pd.Index(list(dict.fromkeys(a["method"])), name="método"))
        for apn in sorted(a["ap"].unique()):
            s = a[a["ap"] == apn].set_index("method")
            t[f"p95 {apn}"] = [fmt(*s.loc[i, ["mean", "ci95"]]) if i in s.index else "-" for i in t.index]
        mx = aggregate(d, ["max_wait_cross_streets"])
        mx = mx[mx["metric"] == "max_wait_cross_streets"].set_index("method")
        t["espera máx. transversales"] = [fmt(*mx.loc[i, ["mean", "ci95"]]) if i in mx.index else "-" for i in t.index]
        secs.append((sc, t))
    return _write("E8_fairness", secs, Path(out_dir), latex, "E8: equidad") if secs else []


def make_tables(exp: str, runs_dir=RUNS_DIR, out_dir=RESULTS_DIR, latex=False) -> list[Path]:
    exp = exp.upper()
    if exp == "E7":
        return robustness_table(runs_dir, out_dir, latex)
    if exp == "E8":
        return fairness_table(runs_dir, out_dir, latex)
    return eval_tables(exp, runs_dir, out_dir, latex) + training_table(exp, runs_dir, out_dir, latex)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True)
    ap.add_argument("--runs-dir", default=str(RUNS_DIR))
    ap.add_argument("--out-dir", default=str(RESULTS_DIR))
    ap.add_argument("--latex", action="store_true")
    a = ap.parse_args(argv)
    paths = make_tables(a.exp, a.runs_dir, a.out_dir, a.latex)
    print("\n".join(map(str, paths)) if paths else f"{a.exp}: no data in {a.runs_dir}")


if __name__ == "__main__":
    main()
