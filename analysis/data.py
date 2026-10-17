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
    "mean_waiting_time": ("Espera media por vehículo (s)", True),
    "mean_travel_time": ("Tiempo de viaje medio (s)", True),
    "mean_queue": ("Cola media (veh)", True),
    "max_queue": ("Cola máxima (veh)", True),
    "throughput_veh_h": ("Throughput (veh/h)", False),
    "mean_stops": ("Paradas por vehículo", True),
    "max_wait_cross_streets": ("Espera máx. calles transversales (s)", True),
    "co2_kg": ("CO₂ (kg)", True),
}
TABLE_METRICS = ["mean_waiting_time", "mean_travel_time", "mean_queue", "throughput_veh_h", "mean_stops"]


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


def load_train_logs(runs_dir: Path | str = RUNS_DIR, exp: str | None = None) -> pd.DataFrame:
    runs_dir = Path(runs_dir)
    frames = []
    for f in sorted(runs_dir.glob(f"{exp or '*'}/*/seed*/train_log.csv")):
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


def aggregate(df: pd.DataFrame, metrics: list[str], by=("method", "scenario")) -> pd.DataFrame:
    """Long table: by..., metric, mean, ci95, n. The unit of replication is the training seed when
    a method has several (average the 10 eval episodes of each seed first, then CI across seeds);
    otherwise the evaluation episodes (baselines, or a single seed)."""
    by = list(by)
    rows = []
    d = df.assign(train_seed=df["train_seed"] if "train_seed" in df else 0)
    for key, g in d.groupby(by, sort=False):
        key = key if isinstance(key, tuple) else (key,)
        for m in metrics:
            if m not in g:
                continue
            per_seed = g.groupby("train_seed")[m].mean()
            vals = per_seed if len(per_seed) > 1 else g[m]
            rows.append({**dict(zip(by, key)), "metric": m, "mean": float(vals.mean()), "ci95": ci95(vals), "n": len(vals.dropna())})
    return pd.DataFrame(rows)


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
