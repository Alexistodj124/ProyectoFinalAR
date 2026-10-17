"""Loading and aggregation of run outputs (runs/<exp>/<name>/seed<k>/...). Pandas only, no plotting."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = REPO_ROOT / "runs"
FIG_DIR = REPO_ROOT / "docs" / "figures"
RESULTS_DIR = REPO_ROOT / "analysis" / "results"

# metric -> (label, lower_is_better)
METRICS = {
    "total_delay": ("Demora total (s/veh demandado)", True),
    "mean_waiting_time": ("Espera media (s/veh insertado)", True),
    "backlog_pct": ("Backlog de inserción (%)", True),
    "mean_depart_delay": ("Retraso de inserción medio (s)", True),
    "loaded": ("Vehículos de la demanda", False),
    "inserted": ("Vehículos insertados", False),
    "mean_travel_time": ("Tiempo de viaje medio (s)", True),
    "mean_queue": ("Cola media (veh)", True),
    "max_queue": ("Cola máxima (veh)", True),
    "throughput_veh_h": ("Throughput (veh/h)", False),
    "mean_stops": ("Paradas por vehículo", True),
    "max_wait_cross_streets": ("Espera máx. calles transversales (s)", True),
    "co2_kg": ("CO₂ (kg)", True),
}
# Tables: total delay first (the headline: wait alone rewards leaving cars outside the network), then wait and backlog.
# Metrics absent from old CSVs (before total_delay/backlog_pct existed) are skipped, not an error.
TABLE_METRICS = ["total_delay", "mean_waiting_time", "backlog_pct", "mean_travel_time", "throughput_veh_h",
                 "mean_stops", "max_wait_cross_streets"]
BAR_METRICS = ["total_delay", "mean_waiting_time", "backlog_pct"]
BASELINE_METHODS = ["fixed", "actuated", "max_pressure"]


def available(df: pd.DataFrame, metrics) -> list[str]:
    """Metrics of `metrics` that exist in `df` and have at least one value (old CSVs lack the new ones)."""
    return [m for m in metrics if m in df and df[m].notna().any()]


def ci95(x) -> float:
    """Half-width of the 95 % t-interval of the mean (nan if n < 2)."""
    x = np.asarray(pd.Series(x).dropna(), dtype=float)
    if len(x) < 2:
        return float("nan")
    return float(stats.t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x)))


def _tag(path: Path, runs_dir: Path) -> tuple[str, str, int | None]:
    """(exp, name, train_seed) from runs/<exp>/<name>[/seed<k>]/file."""
    parts = path.relative_to(runs_dir).parts[:-1]
    exp = parts[0] if parts else ""
    seed = None
    if parts and (m := re.fullmatch(r"seed(\d+)", parts[-1])):
        seed, parts = int(m.group(1)), parts[:-1]
    return exp, (parts[-1] if len(parts) > 1 else exp), seed


def _is_exp_dir(path: Path, runs_dir: Path) -> bool:
    """Only runs/E<k>/...: skips runs/_quick, runs/_sanity, runs/cache (smoke tests, not results)."""
    parts = path.relative_to(runs_dir).parts
    return bool(parts) and re.fullmatch(r"E\d+", parts[0]) is not None


def load_train_logs(runs_dir: Path | str = RUNS_DIR, exp: str | None = None) -> pd.DataFrame:
    runs_dir = Path(runs_dir)
    frames = []
    for f in sorted(runs_dir.glob(f"{exp or '*'}/*/seed*/train_log.csv")):
        if not _is_exp_dir(f, runs_dir):
            continue
        df = pd.read_csv(f)
        if df.empty:
            continue
        df["exp"], df["name"], df["seed"] = _tag(f, runs_dir)
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_eval(runs_dir: Path | str = RUNS_DIR, exp: str | None = None) -> pd.DataFrame:
    """All eval*.csv of an experiment (baselines in E1, learned runs in E2-E6). Adds exp, train_seed."""
    runs_dir = Path(runs_dir)
    frames = []
    for f in sorted(runs_dir.glob(f"{exp or '*'}/**/eval*.csv")):
        # eval_summary.csv is a summary; eval_<method>_<scenario>.csv duplicates rows of eval.csv when both exist
        if not _is_exp_dir(f, runs_dir):
            continue
        if f.name.endswith("_summary.csv") or (f.name != "eval.csv" and (f.parent / "eval.csv").exists()):
            continue
        df = pd.read_csv(f)
        if df.empty or "scenario" not in df:
            continue
        e, name, seed = _tag(f, runs_dir)
        df["exp"] = df.get("exp", e)
        if "method" not in df:
            df["method"] = name
        if "train_seed" not in df:
            df["train_seed"] = seed if seed is not None else 0
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_csv(runs_dir: Path | str, rel: str) -> pd.DataFrame:
    f = Path(runs_dir) / rel
    return pd.read_csv(f) if f.exists() else pd.DataFrame()


def unit_values(g: pd.DataFrame, m: str) -> tuple[np.ndarray, str]:
    """Replication units of metric `m` for one (method, scenario) group.

    Learned methods (>= 2 training seeds): one value per training seed = mean of its evaluation episodes
    (unit "semilla"). Baselines and single-seed runs: one value per evaluation episode (unit "episodio")."""
    if "train_seed" in g and g["train_seed"].notna().any():
        per_seed = g.groupby("train_seed")[m].mean().dropna()
        if len(per_seed) > 1:
            return per_seed.to_numpy(dtype=float), "semilla"
    return g[m].dropna().to_numpy(dtype=float), "episodio"


def aggregate(df: pd.DataFrame, metrics: list[str], by=("method", "scenario")) -> pd.DataFrame:
    """Long table: by..., metric, mean, ci95, n, unit. The unit of replication is the training seed when
    a method has several (average the 10 eval episodes of each seed first, then CI across seeds);
    otherwise the evaluation episodes (baselines, or a single seed)."""
    by = list(by)
    rows = []
    for key, g in df.groupby(by, sort=False):
        key = key if isinstance(key, tuple) else (key,)
        for m in metrics:
            if m not in g or g[m].isna().all():  # metric absent for this method (old CSV): no row, shown as "-"
                continue
            vals, unit = unit_values(g, m)
            rows.append({**dict(zip(by, key)), "metric": m, "mean": float(np.mean(vals)), "ci95": ci95(vals),
                         "n": len(vals), "unit": unit})
    return pd.DataFrame(rows)


def load_master(runs_dir: Path | str = RUNS_DIR) -> pd.DataFrame:
    """Every final evaluation of the matrix in one frame, without duplicates.

    * learned methods and E1 baselines: `eval.csv` of each run (E2-E6, E8) and of E1/baselines;
    * baselines on scenarios E1 did not evaluate (cruce_mediodia, cruce_pico_x13): their rows of
      E7/robustness.csv (deterministic simulator: on the shared scenarios they equal the E1 rows exactly).
    The E7 learned agents (a single training seed) and the incident rows are NOT here: see `load_csv(.., "E7/robustness.csv")`.
    """
    runs_dir = Path(runs_dir)
    ev = load_eval(runs_dir)
    rob = load_csv(runs_dir, "E7/robustness.csv")
    if not rob.empty and not ev.empty:
        var = rob["variant"] if "variant" in rob else pd.Series("pico", index=rob.index)
        b = rob[rob["method"].isin(BASELINE_METHODS) & (var != "pico_incident")]
        have = set(zip(ev["method"], ev["scenario"]))
        b = b[[(m, s) not in have for m, s in zip(b["method"], b["scenario"])]].copy()
        if not b.empty:
            b["exp"], b["train_seed"] = "E7", np.nan
            ev = pd.concat([ev, b], ignore_index=True)
    return ev


def load_fairness(runs_dir: Path | str = RUNS_DIR) -> pd.DataFrame:
    """E8/fairness.csv sin duplicados: ese CSV reúne todo, y las líneas base aparecen 3 veces (eval.csv de E1, el
    eval_<método>_<escenario>.csv y E7) y los agentes de E7 repiten corridas de E3 a E6. Se descarta lo que viene de
    E7 salvo las líneas base y se deja una fila por (método, escenario, semilla de entrenamiento, semilla de evaluación).
    Solo la hora pico (sin incidente ni perturbación)."""
    df = load_csv(runs_dir, "E8/fairness.csv")
    if df.empty:
        return df
    if "variant" in df:
        df = df[df["variant"] == "pico"]
    if "source" in df:
        from_e7 = df["source"].astype(str).str.startswith("E7/")
        df = df[~from_e7 | df["method"].isin(BASELINE_METHODS)]
    key = [c for c in ("method", "scenario", "train_seed", "seed") if c in df]
    return df.drop_duplicates(subset=key, keep="first").reset_index(drop=True)


def approach_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Expand the p95_wait_by_approach JSON column into long rows (one per episode x approach)."""
    rows = []
    for r in df.itertuples(index=False):
        raw = getattr(r, "p95_wait_by_approach", None)
        if not isinstance(raw, str):
            continue
        for ap, v in json.loads(raw).items():
            rows.append({"method": r.method, "scenario": r.scenario, "approach": ap, "p95_wait": float(v),
                         "train_seed": getattr(r, "train_seed", 0) if hasattr(r, "train_seed") else 0,
                         "variant": getattr(r, "variant", "pico") if hasattr(r, "variant") else "pico"})
    return pd.DataFrame(rows)
