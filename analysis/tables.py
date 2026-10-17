"""Tablas en Markdown (y LaTeX opcional), media ± IC95, en analysis/results/.

    python -m analysis.tables --exp E3 [--latex]

Réplica: semilla de entrenamiento (n=5) en los métodos aprendidos; episodio de evaluación (n=10) en las líneas base y en
los agentes de E7 (una sola semilla). Cada fila lo dice entre paréntesis.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from analysis import style
from analysis.data import (METRICS, RESULTS_DIR, RUNS_DIR, TABLE_METRICS, aggregate, approach_frame, available, ci95,
                           load_csv, load_fairness, load_master, load_train_logs, unit_values)
from analysis.specs import exp_frame, scenario_order, spec
from analysis.style import label, scen_label, sort_methods, variant_label

NOTE = ("Media ± IC95 (t de Student). Réplica = semilla de entrenamiento (n=5) en los métodos aprendidos y episodio de "
        "evaluación (n=10, semillas 1000 a 1009) en las líneas base; se indica en cada fila. **Negrita** = mejor valor de la "
        "columna. Demora total = (espera + retraso de inserción de los insertados + tiempo que esperaron afuera los que nunca "
        "entraron) / todos los vehículos de la demanda (s por vehículo demandado); espera media = por vehículo insertado; "
        "backlog = % de la demanda que no pudo entrar a la red.")
UNIT_SHORT = {"semilla": "sem.", "episodio": "ep."}


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
    esc = lambda s: str(s).replace("_", r"\_").replace("±", r"$\pm$").replace("**", "").replace("%", r"\%")
    head = " & ".join([esc(df.index.name or "")] + [esc(c) for c in df.columns]) + r" \\"
    body = "\n".join(" & ".join([esc(i)] + [esc(v) for v in r]) + r" \\" for i, r in df.iterrows())
    return ("\\begin{table}[h]\n\\centering\n\\begin{tabular}{l" + "r" * len(df.columns) + "}\n\\toprule\n"
            f"{head}\n\\midrule\n{body}\n\\bottomrule\n\\end{{tabular}}\n\\caption{{{esc(caption)}}}\n\\end{{table}}\n")


def row_label(m: str, unit: str | None, ctx: str | None = None) -> str:
    return label(m, ctx) + (f" ({UNIT_SHORT.get(unit, unit)})" if unit else "")


def metric_table(agg: pd.DataFrame, rows: str, metrics: list[str], filt: dict | None = None, digits: int = 2,
                 row_name=None) -> pd.DataFrame:
    """Rows = `rows` column of the long aggregate; one column per metric with 'mean ± ci' and the best in bold."""
    a = agg
    for k, v in (filt or {}).items():
        a = a[a[k] == v]
    idx = list(dict.fromkeys(a[rows]))
    units = a.drop_duplicates(rows).set_index(rows)["unit"].to_dict() if "unit" in a else {}
    names = {i: (row_name(i, units.get(i)) if row_name else i) for i in idx}
    out = pd.DataFrame(index=pd.Index([names[i] for i in idx], name="Método" if row_name else rows))
    for m in metrics:
        s = a[a["metric"] == m].set_index(rows)
        if s.empty:
            continue
        lower = METRICS.get(m, ("", True))[1]
        best = (s["mean"].idxmin() if lower else s["mean"].idxmax()) if s["mean"].notna().any() else None
        out[METRICS.get(m, (m,))[0]] = [("**" + fmt(*s.loc[i, ["mean", "ci95"]], digits) + "**") if i == best else
                                        (fmt(*s.loc[i, ["mean", "ci95"]], digits) if i in s.index else "-") for i in idx]
    return out


def _write(name: str, sections: list[tuple[str, pd.DataFrame]], out_dir: Path, latex: bool, title: str,
           note: str = NOTE) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = [f"# {title}", "", note, ""]
    for head, t in sections:
        md += [f"## {head}", "", to_markdown(t), ""]
    paths = [out_dir / f"{name}.md"]
    paths[0].write_text("\n".join(md))
    if latex:
        tex = "\n".join(to_latex(t, f"{title}: {h}") for h, t in sections)
        paths.append(out_dir / f"{name}.tex")
        paths[1].write_text(tex)
    return paths


# ------------------------------------------------------------------ evaluación final por experimento
def eval_tables(exp: str, runs_dir=RUNS_DIR, out_dir=RESULTS_DIR, latex=False) -> list[Path]:
    exp = exp.upper()
    df = exp_frame(load_master(runs_dir), exp)
    if df.empty:
        return []
    metrics = available(df, TABLE_METRICS)
    agg = aggregate(df, metrics)
    order = sort_methods(df["method"])
    secs = []
    for sc in scenario_order(df, exp):
        a = agg[agg["scenario"] == sc].copy()
        a["method"] = pd.Categorical(a["method"], order, ordered=True)
        a = a.sort_values("method").assign(method=lambda x: x["method"].astype(str))
        secs.append((scen_label(sc, flat=True) + f" (`{sc}`)", metric_table(a, "method", metrics, None, row_name=row_name)))
    return _write(f"{exp}_eval", secs, Path(out_dir), latex, f"{spec(exp)['title']}: evaluación final")


def row_name(m, unit):
    return row_label(m, unit)


def training_table(exp: str, runs_dir=RUNS_DIR, out_dir=RESULTS_DIR, latex=False) -> list[Path]:
    """Retorno del último 10 % del entrenamiento, pasos y tiempo de pared por método (entre semillas de entrenamiento)."""
    exp = exp.upper()
    logs = load_train_logs(runs_dir, exp)
    if logs.empty:
        return []
    rows = {}
    for name in sort_methods(logs["name"]):
        g = logs[logs["name"] == name]
        tail = [s.sort_values("episode")["return"].tail(max(1, len(s) // 10)).mean() for _, s in g.groupby("seed")]
        wall = [s["wall_time"].max() / 60 for _, s in g.groupby("seed")] if "wall_time" in g else [np.nan]
        steps = [s["env_steps"].max() for _, s in g.groupby("seed")] if "env_steps" in g else [np.nan]
        rows[label(name)] = {"semillas": len(tail), "retorno final (último 10 % de episodios)": fmt(np.mean(tail), ci95(tail), 0),
                             "pasos de entorno": f"{np.mean(steps):.0f}", "tiempo de pared (min)": f"{np.mean(wall):.1f}"}
    t = pd.DataFrame(rows).T
    t.index.name = "Método"
    note = ("Media ± IC95 entre semillas de entrenamiento. El retorno es la suma de las recompensas del episodio (la recompensa de "
            "entrenamiento incluye el backlog de inserción); no es comparable entre algoritmos con escalas de recompensa distintas.")
    return _write(f"{exp}_training", [("Entrenamiento", t)], Path(out_dir), latex, f"{exp}: entrenamiento", note)


def sample_efficiency_table(exp: str, runs_dir=RUNS_DIR, out_dir=RESULTS_DIR, latex=False) -> list[Path]:
    """Pasos de entorno hasta que la demora total de validación (cada 20 episodios, 2 semillas de validación) baja del nivel
    del tiempo fijo y del de max-pressure en el escenario de entrenamiento. Cuántas semillas lo logran y la mediana de pasos."""
    from analysis.plots import load_selection
    exp = exp.upper()
    s = spec(exp)
    sel = load_selection(runs_dir)
    master = load_master(runs_dir)
    if sel.empty or master.empty or not s["train_scenario"]:
        return []
    sel = sel[(sel["exp"] == exp) | (sel["name"].isin(s["extra_methods"]) & (sel["exp"] != exp))]
    if sel.empty or "env_steps" not in sel:
        return []
    refs = {}
    for b in ("fixed", "max_pressure"):
        d = master[(master["method"] == b) & (master["scenario"] == s["train_scenario"])]
        if not d.empty:
            refs[label(b)] = float(d["total_delay"].mean())
    if "Tiempo fijo" in refs:
        refs["1.5 × tiempo fijo"] = 1.5 * refs["Tiempo fijo"]
    refs = dict(sorted(refs.items(), key=lambda kv: kv[1], reverse=True))
    rows = {}
    for name in sort_methods(sel["name"]):
        g = sel[sel["name"] == name]
        r = {}
        last = g[g["episode"] == g["episode"].max()].set_index("seed")["total_delay"]
        for b, thr in refs.items():
            hits = []
            for sd, gs in g.groupby("seed"):
                gs = gs.sort_values("episode")
                ok = gs[gs["total_delay"] <= thr]
                if len(ok):
                    hits.append(float(ok["env_steps"].iloc[0]))
            n = g["seed"].nunique()
            r[f"semillas que llegan a {b} ({thr:.0f} s)"] = f"{len(hits)} de {n}"
            r[f"pasos hasta {b} (mediana, k)"] = f"{np.median(hits) / 1000:.0f}" if hits else "nunca"
        best = g.groupby("seed")["total_delay"].min()
        r["mejor checkpoint (media entre semillas, s)"] = f"{best.mean():.1f}"
        r["último checkpoint (media entre semillas, s)"] = f"{last.mean():.1f}"
        rows[label(name)] = r
    t = pd.DataFrame(rows).T
    t.index.name = "Método"
    note = ("Primer checkpoint (cada 20 episodios = 14 400 pasos) cuya demora total de validación (semillas 2000 y 2001, escenario "
            f"`{s['train_scenario']}`) es menor o igual a la de la línea base indicada (evaluación final, semillas 1000 a 1009, como "
            "referencia). Con 2 episodios de validación es una medida ruidosa; el mejor checkpoint tiene sesgo optimista "
            "(es el mínimo de 10 valores).")
    return _write(f"{exp}_sample_efficiency", [("Eficiencia de muestras", t)], Path(out_dir), latex,
                  f"{exp}: eficiencia de muestras", note)


# ------------------------------------------------------------------ E7
def robustness_table(runs_dir=RUNS_DIR, out_dir=RESULTS_DIR, latex=False) -> list[Path]:
    df = load_csv(runs_dir, "E7/robustness.csv")
    if df.empty:
        return []
    if "base" not in df:
        df["base"] = "all"
    if "variant" not in df:
        df["variant"] = "pico"
    metrics = available(df, ["total_delay", "mean_waiting_time", "backlog_pct"])
    secs = []
    for base, d in df.groupby("base", sort=False):
        agg = aggregate(d, metrics, by=("method", "variant", "scenario"))
        ms = sort_methods(d["method"])
        variants = list(dict.fromkeys(d["variant"]))
        for metric in metrics:
            a = agg[agg["metric"] == metric]
            t = pd.DataFrame(index=pd.Index([label(m, "E7") + " (10 ep.)" for m in ms], name="Método"))
            for v in variants:
                s_ = a[a["variant"] == v].set_index("method")
                best = s_["mean"].idxmin() if len(s_) else None
                t[variant_label(v, flat=True)] = [("**" if m == best else "") + fmt(*s_.loc[m, ["mean", "ci95"]], 1) +
                                                  ("**" if m == best else "") if m in s_.index else "-" for m in ms]
            ref = a[a["variant"] == "pico"].set_index("method")["mean"]
            if metric == metrics[0] and not ref.empty:
                for v in [v for v in variants if v != "pico"]:
                    s_ = a[a["variant"] == v].set_index("method")["mean"]
                    t[f"× {variant_label(v, flat=True)} / pico"] = [f"×{s_[m] / ref[m]:.2f}" if m in s_.index and m in ref.index and ref[m] else "-" for m in ms]
                if "fixed" in ms:
                    for v in variants:
                        s_ = a[a["variant"] == v].set_index("method")["mean"]
                        if "fixed" in s_.index:
                            t[f"Δ% vs fijo, {variant_label(v, flat=True)}"] = [
                                "-" if m == "fixed" or m not in s_.index else f"{100 * (s_[m] / s_['fixed'] - 1):+.1f} %" for m in ms]
            secs.append((f"{style_base(base)}: {METRICS.get(metric, (metric,))[0]}", t))
    note = ("Media ± IC95 sobre los 10 episodios de evaluación (semillas 1000 a 1009). Los agentes aprendidos son UNA sola semilla "
            "de entrenamiento elegida por validación (`marl_best` = MAPPO, semilla 3; `comm_best`, semilla 0; PPO, semilla 0; DQN, "
            "semilla 1): el IC no incluye la variabilidad entre semillas de entrenamiento. Las líneas base son deterministas por "
            "semilla de evaluación. **Negrita** = mejor de la columna.")
    return _write("E7_robustness", secs, Path(out_dir), latex, "E7: generalización", note)


def style_base(b: str) -> str:
    return {"cruce": "Cruce C12", "reforma": "Corredor Reforma"}.get(b, b)


# ------------------------------------------------------------------ E8
def fairness_table(runs_dir=RUNS_DIR, out_dir=RESULTS_DIR, latex=False) -> list[Path]:
    df = load_fairness(runs_dir)
    if df.empty:
        return []
    secs = []
    for sc, d in df.groupby("scenario", sort=False):
        ap = approach_frame(d)
        if ap.empty:
            continue
        ms = sort_methods(d["method"])
        a = aggregate(ap.rename(columns={"approach": "ap"}), ["p95_wait"], by=("method", "ap"))
        units = a.drop_duplicates("method").set_index("method")["unit"].to_dict()
        t = pd.DataFrame(index=pd.Index([row_label(m, units.get(m)) for m in ms], name="Método"))
        aps = [x for x in sorted(a["ap"].unique(), key=lambda z: (style.is_cross_street(z), z))]
        for apn in aps:
            s_ = a[a["ap"] == apn].set_index("method")
            t[f"p95 {style.approach_label(apn)} (s)"] = [fmt(*s_.loc[m, ["mean", "ci95"]], 0) if m in s_.index else "-" for m in ms]
        extra = aggregate(d, ["max_wait_cross_streets", "total_delay"])
        for met in ("max_wait_cross_streets", "total_delay"):
            s_ = extra[extra["metric"] == met].set_index("method")
            t[METRICS[met][0]] = [fmt(*s_.loc[m, ["mean", "ci95"]], 1 if met == "total_delay" else 0) if m in s_.index else "-" for m in ms]
        secs.append((f"{scen_label(sc, flat=True)} (`{sc}`)", t))
    note = ("Media ± IC95. p95 = percentil 95 de la espera de los vehículos de cada aproximación (s). Espera máx. en transversales = "
            "mayor espera de un vehículo en una calle que no es Reforma. Réplica: semilla de entrenamiento (n=5) o episodio de "
            "evaluación (n=10, líneas base).")
    return _write("E8_fairness", secs, Path(out_dir), latex, "E8: equidad", note) if secs else []


def co2_table(runs_dir=RUNS_DIR, out_dir=RESULTS_DIR, latex=False, scenario: str = "reforma_pico") -> list[Path]:
    df = load_fairness(runs_dir)
    d = df[df["scenario"] == scenario] if not df.empty else df
    if d.empty or "co2_kg" not in d:
        return []
    ms = sort_methods(d["method"])
    agg = aggregate(d, ["co2_kg", "arrived", "mean_stops", "mean_travel_time"], by=("method",))
    ref = agg[(agg["method"] == "fixed") & (agg["metric"] == "co2_kg")]["mean"]
    ref = float(ref.iloc[0]) if len(ref) else np.nan
    t = pd.DataFrame(index=pd.Index([row_label(m, agg[agg["method"] == m]["unit"].iloc[0]) for m in ms], name="Método"))
    g = lambda met, m: agg[(agg["method"] == m) & (agg["metric"] == met)].iloc[0]
    t["CO₂ (kg)"] = [fmt(g("co2_kg", m)["mean"], g("co2_kg", m)["ci95"], 0) for m in ms]
    t["Cambio frente al tiempo fijo"] = ["-" if m == "fixed" else f"{100 * (g('co2_kg', m)['mean'] / ref - 1):+.1f} %" for m in ms]
    t["CO₂ por vehículo que llegó (g)"] = [f"{1000 * g('co2_kg', m)['mean'] / g('arrived', m)['mean']:.0f}" for m in ms]
    t["Paradas por vehículo"] = [fmt(g("mean_stops", m)["mean"], g("mean_stops", m)["ci95"], 2) for m in ms]
    note = ("CO₂ emitido por todos los vehículos de la hora simulada (modelo de emisiones de SUMO, `co2_kg`). Depende del número de "
            "vehículos que circulan y de las paradas y arranques: un método que deja más vehículos afuera emite menos sin servir mejor. "
            "Media ± IC95; réplica = semilla de entrenamiento (n=5) o episodio de evaluación (n=10, líneas base).")
    return _write(f"CO2_{scenario}", [(scen_label(scenario, flat=True), t)], Path(out_dir), latex, "Emisiones de CO₂", note)


def make_tables(exp: str, runs_dir=RUNS_DIR, out_dir=RESULTS_DIR, latex=False) -> list[Path]:
    exp = exp.upper()
    if exp == "E7":
        return robustness_table(runs_dir, out_dir, latex)
    if exp == "E8":
        return fairness_table(runs_dir, out_dir, latex) + co2_table(runs_dir, out_dir, latex)
    return (eval_tables(exp, runs_dir, out_dir, latex) + training_table(exp, runs_dir, out_dir, latex)
            + sample_efficiency_table(exp, runs_dir, out_dir, latex))


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
