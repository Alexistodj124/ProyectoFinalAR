"""E7 (robustness) and E8 (fairness collection).

E7:  python -m experiments.robustness --config experiments/configs/E7/robustness.yaml --out runs/E7/robustness.csv
     Evaluates the learned runs (picked from the config) and the baselines on <base>_pico,
     <base>_mediodia, <base>_pico_x13 and <base>_pico + incident.
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
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
INCIDENT_SUFFIX = "_incident"


# ------------------------------------------------------------------ run selection
def run_score(run_dir: Path) -> tuple[float, str] | None:
    """Lower is better. Prefers the final evaluation (mean waiting time), else the training return."""
    ev = run_dir / "eval.csv"
    if ev.exists():
        df = pd.read_csv(ev)
        if "mean_waiting_time" in df and len(df):
            return float(df["mean_waiting_time"].mean()), "eval.mean_waiting_time"
    tl = run_dir / "train_log.csv"
    if tl.exists():
        df = pd.read_csv(tl)
        if "return" in df and len(df):
            tail = df["return"].tail(max(1, len(df) // 10))
            return -float(tail.mean()), "train.return(last 10%)"
    return None


def select_run(spec: dict, runs_dir: Path) -> Path | None:
    """spec: {run_dir: path} | {from: glob relative to runs_dir, select: best|first}."""
    if spec.get("run_dir"):
        return Path(spec["run_dir"])
    cands = sorted(Path(p) for p in globmod.glob(str(runs_dir / spec["from"])) if (Path(p) / "DONE").exists())
    if not cands:
        return None
    if spec.get("select", "best") == "first":
        return cands[0]
    scored = [(s[0], c) for c in cands if (s := run_score(c)) is not None]
    return min(scored)[1] if scored else cands[0]


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

    # (label, algo, run_dir | None, base)
    methods: list[tuple[str, str, str | None, str]] = []
    for spec in cfg.get("learned", []):
        rd = select_run(spec, runs_dir)
        if rd is None:
            print(f"[E7] no finished run for {spec.get('label', spec['algo'])} ({spec.get('from')}); skipped")
            continue
        print(f"[E7] {spec.get('label', spec['algo'])} -> {rd}")
        methods.append((spec.get("label", spec["algo"]), spec["algo"], str(rd), spec["base"]))
    for bs in cfg.get("baselines", ["fixed", "actuated", "max_pressure"]):
        for base in sorted({m[3] for m in methods} or {cfg.get("default_base", "cruce")}):
            methods.append((bs, bs, None, base))

    frames, incidents = [], {}
    out.parent.mkdir(parents=True, exist_ok=True)
    for label, algo, rd, base in methods:
        policy = registry.load_policy(algo, rd, None)
        for variant in variants:
            scenario, with_incident = parse_variant(variant, base)
            inc = None
            if with_incident:
                inc = incidents.setdefault(base, resolve_incident(cfg.get("incident"), scenario))
            df = evaluate(policy, scenario, seeds, num_seconds=num_seconds, incident=inc)
            df["method"], df["variant"], df["base"], df["run_dir"] = label, variant, base, rd or ""
            df["incident"] = str(inc) if inc else ""
            frames.append(df)
            pd.concat(frames, ignore_index=True).to_csv(out, index=False)  # incremental: survive a crash
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


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
