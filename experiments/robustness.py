"""E7 (robustness) and E8 (fairness collection).

E7:  python -m experiments.robustness --config experiments/configs/E7/robustness.yaml --out runs/E7/robustness.csv
     Evaluates the learned runs (picked from the config) and the baselines on <base>_pico,
     <base>_mediodia, <base>_pico_x13 and <base>_pico + incident. Each learned spec picks its
     training seed(s) WITHOUT looking at EVAL_SEEDS (that would bias E7 optimistically):
       select: best (default) -> the seed whose validation score (selection.csv, VAL_SEEDS) is lowest
       select: all            -> every training seed; robustness_summary.csv reports mean ± IC95
                                 over training seeds (per-seed mean over the EVAL_SEEDS episodes)
       select: first          -> the first seed found
     Every run is loaded from experiments.common.policy_dir(run_dir) (best/ checkpoint if any).
E8:  python -m experiments.robustness --fairness --config experiments/configs/E8/fairness.yaml
     Concatenates the eval CSVs listed in the config into runs/E8/fairness.csv.
"""
from __future__ import annotations

import os
import sys

if __name__ == "__main__" and "--no-libsumo" not in sys.argv:  # only as a CLI: importing must not change the env
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")

import argparse
import glob as globmod
import re
from pathlib import Path

import pandas as pd
import yaml

from experiments.common import policy_dir

REPO_ROOT = Path(__file__).resolve().parents[1]
INCIDENT_SUFFIX = "_incident"


# ------------------------------------------------------------------ run selection
# Validation scores are ranked first by criterion (total_delay before mean_waiting_time: a run
# selected with the backlog-aware metric is preferred over one scored on waiting time alone), then
# by value. The training return is only a last resort for runs without selection.csv.
_CRIT_PRIORITY = {"total_delay": 0, "mean_waiting_time": 1}


def run_score(run_dir: Path) -> tuple[int, float, str] | None:
    """(priority, value, source); lower is better. Uses the validation score of the selected
    checkpoint (run_dir/selection.csv, VAL_SEEDS), else minus the mean training return of the
    last 10 % of episodes. Never looks at eval.csv (EVAL_SEEDS), so E7 stays unbiased."""
    sel = run_dir / "selection.csv"
    if sel.exists():
        df = pd.read_csv(sel)
        if len(df) and "score" in df and "selected" in df:
            row = df[df["selected"].astype(str).str.lower() == "true"]
            row = row.iloc[0] if len(row) else df.loc[df["score"].idxmin()]
            if pd.notna(row.get("score")) and str(row.get("criterion")) in _CRIT_PRIORITY:
                crit = str(row["criterion"])
                return _CRIT_PRIORITY[crit], float(row["score"]), f"val.{crit}"
    tl = run_dir / "train_log.csv"
    if tl.exists():
        df = pd.read_csv(tl)
        if "return" in df and len(df):
            tail = df["return"].tail(max(1, len(df) // 10))
            return len(_CRIT_PRIORITY), -float(tail.mean()), "train.return(last 10%)"
    return None


def select_runs(spec: dict, runs_dir: Path) -> list[Path]:
    """spec: {run_dir: path} | {from: glob relative to runs_dir, select: best|all|first}."""
    if spec.get("run_dir"):
        return [Path(spec["run_dir"])]
    cands = sorted(Path(p) for p in globmod.glob(str(runs_dir / spec["from"])) if (Path(p) / "DONE").exists())
    if not cands:
        return []
    mode = spec.get("select", "best")
    if mode == "all":
        return cands
    if mode == "first":
        return cands[:1]
    if mode != "best":
        raise ValueError(f"select must be best, all or first (got {mode!r})")
    scored = [(s[0], s[1], str(c), c) for c in cands if (s := run_score(c)) is not None]
    return [min(scored)[3]] if scored else cands[:1]


def select_run(spec: dict, runs_dir: Path) -> Path | None:
    """Single-run version of select_runs (select: all returns the first seed)."""
    runs = select_runs(spec, runs_dir)
    return runs[0] if runs else None


def train_seed_of(run_dir: str | Path | None) -> int | None:
    if not run_dir:
        return None
    cfg = Path(run_dir) / "config.yaml"
    if cfg.exists():
        seed = (yaml.safe_load(cfg.read_text()) or {}).get("seed")
        if seed is not None:
            return int(seed)
    m = re.search(r"seed(\d+)", str(run_dir))
    return int(m.group(1)) if m else None


# ------------------------------------------------------------------ incident
def default_incident_edge(net_file: str) -> str:
    """First corridor edge: the first normal edge that joins two signalised nodes (so closing it
    matters), else the longest edge entering the first signalised node."""
    import sumolib

    net = sumolib.net.readNet(net_file)
    tls_nodes = {n.getID() for n in net.getNodes() if n.getType() == "traffic_light"}
    edges = [e for e in net.getEdges() if e.getFunction() == ""]
    between = [e for e in edges if e.getFromNode().getID() in tls_nodes and e.getToNode().getID() in tls_nodes]
    pool = between or [e for e in edges if e.getToNode().getID() in tls_nodes]
    if not pool:
        raise ValueError(f"no suitable incident edge in {net_file}")
    return sorted(pool, key=lambda e: (-e.getLength(), e.getID()))[0].getID()


def resolve_incident(inc: dict | None, scenario: str) -> dict:
    from env.scenarios import get_scenario

    inc = dict(inc or {})
    if not inc.get("edge") and not inc.get("lane"):
        inc["edge"] = default_incident_edge(get_scenario(scenario).net_file)
    inc.setdefault("start", 900)
    inc.setdefault("end", 2100)
    return inc


def parse_variant(variant: str, base: str) -> tuple[str, bool]:
    """'pico_incident' -> ('<base>_pico', True); 'mediodia' -> ('<base>_mediodia', False)."""
    inc = variant.endswith(INCIDENT_SUFFIX)
    profile = variant[: -len(INCIDENT_SUFFIX)] if inc else variant
    return f"{base}_{profile}", inc


# ------------------------------------------------------------------ E7
def run_robustness(cfg: dict, runs_dir: Path, out: Path, *, num_seconds=None, eval_seeds=None) -> pd.DataFrame:
    from agents import registry
    from env.scenarios import EVAL_SEEDS
    from experiments.evaluate import evaluate  # built by feat/baselines-eval

    num_seconds = num_seconds or cfg.get("num_seconds")
    seeds = EVAL_SEEDS[: eval_seeds or cfg.get("eval_seeds") or len(EVAL_SEEDS)]
    variants = cfg.get("variants") or ["pico", "mediodia", "pico_x13", "pico_incident"]

    # (label, algo, run_dir | None, base, selection)
    methods: list[tuple[str, str, str | None, str, str]] = []
    for spec in cfg.get("learned", []):
        label = spec.get("label", spec["algo"])
        rds = select_runs(spec, runs_dir)
        if not rds:
            print(f"[E7] no finished run for {label} ({spec.get('from')}); skipped")
            continue
        mode = "run_dir" if spec.get("run_dir") else spec.get("select", "best")
        for rd in rds:
            print(f"[E7] {label} ({mode}) -> {rd} (loads {policy_dir(rd).name})")
            methods.append((label, spec["algo"], str(rd), spec["base"], mode))
    for bs in cfg.get("baselines", ["fixed", "actuated", "max_pressure"]):
        for base in sorted({m[3] for m in methods} or {cfg.get("default_base", "cruce")}):
            methods.append((bs, bs, None, base, "baseline"))

    frames, incidents = [], {}
    out.parent.mkdir(parents=True, exist_ok=True)
    for label, algo, rd, base, mode in methods:
        policy = registry.load_policy(algo, str(policy_dir(rd)) if rd else None, None)
        for variant in variants:
            scenario, with_incident = parse_variant(variant, base)
            inc = None
            if with_incident:
                inc = incidents.setdefault(base, resolve_incident(cfg.get("incident"), scenario))
            df = evaluate(policy, scenario, seeds, num_seconds=num_seconds, incident=inc)
            df["method"], df["variant"], df["base"], df["run_dir"] = label, variant, base, rd or ""
            df["incident"] = str(inc) if inc else ""
            df["train_seed"] = train_seed_of(rd)
            df["selection"] = mode
            df["policy_dir"] = str(policy_dir(rd)) if rd else ""
            frames.append(df)
            pd.concat(frames, ignore_index=True).to_csv(out, index=False)  # incremental: survive a crash
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    summarize_robustness(df).to_csv(out.with_name(out.stem + "_summary.csv"), index=False)
    return df


SUMMARY_METRICS = ["total_delay", "mean_waiting_time", "mean_travel_time", "throughput_veh_h", "max_wait_cross_streets"]


def summarize_robustness(df: pd.DataFrame) -> pd.DataFrame:
    """Mean ± IC95 per (method, base, variant). When a method has several training seeds
    (select: all) the unit is the training seed: each seed is first averaged over its EVAL_SEEDS
    episodes and the IC95 is over those per-seed means (ci_over=train_seeds). Otherwise the IC95
    is over the evaluation episodes (ci_over=eval_seeds)."""
    from experiments.metrics import ci95

    rows = []
    metrics = [m for m in SUMMARY_METRICS if m in df.columns]
    seed_col = df["train_seed"] if "train_seed" in df else pd.Series([None] * len(df))
    df = df.assign(_ts=seed_col.fillna(-1))
    for (method, base, variant), g in df.groupby(["method", "base", "variant"], sort=False):
        n_ts = g.loc[g["_ts"] >= 0, "_ts"].nunique()
        unit = g.groupby("_ts")[metrics].mean() if n_ts > 1 else g[metrics]
        row = {"method": method, "base": base, "variant": variant, "n_train_seeds": n_ts,
               "n_episodes": len(g), "ci_over": "train_seeds" if n_ts > 1 else "eval_seeds"}
        for m in metrics:
            row[f"{m}_mean"] = float(unit[m].mean())
            row[f"{m}_ci95"] = ci95(unit[m].to_numpy())
        rows.append(row)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ E8
def collect_fairness(cfg: dict, runs_dir: Path, out: Path) -> pd.DataFrame:
    frames = []
    for pat in cfg.get("sources", []):
        for f in sorted(globmod.glob(str(runs_dir / pat))):
            df = pd.read_csv(f)
            if "p95_wait_by_approach" not in df:
                continue
            df["source"] = str(Path(f).relative_to(runs_dir))
            if "variant" not in df:
                df["variant"] = "pico"
            frames.append(df)
    if not frames:
        print("[E8] no eval CSVs found yet")
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    if cfg.get("scenarios"):
        df = df[df["scenario"].isin(cfg["scenarios"])]
    if cfg.get("methods"):
        df = df[df["method"].isin(cfg["methods"])]
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return df


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", required=True)
    p.add_argument("--fairness", action="store_true", help="E8: collect eval CSVs instead of evaluating")
    p.add_argument("--runs-dir", default=str(REPO_ROOT / "runs"))
    p.add_argument("--out", default=None)
    p.add_argument("--num-seconds", type=int, default=None)
    p.add_argument("--eval-seeds", type=int, default=None)
    p.add_argument("--no-libsumo", action="store_true")
    a = p.parse_args(argv)
    cfg = yaml.safe_load(Path(a.config).read_text())
    runs_dir = Path(a.runs_dir)
    if a.fairness:
        out = Path(a.out or runs_dir / "E8" / "fairness.csv")
        df = collect_fairness(cfg, runs_dir, out)
    else:
        out = Path(a.out or runs_dir / "E7" / "robustness.csv")
        df = run_robustness(cfg, runs_dir, out, num_seconds=a.num_seconds, eval_seeds=a.eval_seeds)
    print(f"[{cfg.get('exp')}] {len(df)} rows -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
