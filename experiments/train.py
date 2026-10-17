"""Train one config for one or several seeds.

    python -m experiments.train --config experiments/configs/E3/dqn_double.yaml --seed 0
    python -m experiments.train --config X.yaml --seeds 0 1 2 3 4 --eval

LIBSUMO_AS_TRACI must be set BEFORE sumo_rl / traci are imported, so it is done here, at
the top of the module (libsumo runs one simulation per process; use run_matrix --jobs N
to parallelise across processes).
"""
from __future__ import annotations

import os
import sys

if __name__ == "__main__" and "--no-libsumo" not in sys.argv:  # only as a CLI: importing must not change the env
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")

import argparse
import json
import time
from pathlib import Path

from experiments.common import load_config, resolve_run_dir, save_config, set_seed

DONE = "DONE"


def is_done(run_dir: str | Path) -> bool:
    return (Path(run_dir) / DONE).exists()


def write_done(run_dir: str | Path, **info) -> None:
    info.setdefault("finished_at", time.strftime("%Y-%m-%d %H:%M:%S"))
    (Path(run_dir) / DONE).write_text(json.dumps(info, indent=1, default=str))


def evaluate_run(cfg: dict, run_dir: str | Path, n_seeds: int | None = None):
    """Final evaluation of a trained run on cfg["eval"]["scenarios"] (EVAL_SEEDS, never
    used in training). Returns a DataFrame with one row per episode (contract §7)."""
    import pandas as pd

    from agents import registry
    from env.scenarios import EVAL_SEEDS
    from experiments.evaluate import evaluate  # built by feat/baselines-eval

    ev = cfg.get("eval") or {}
    scenarios = ev.get("scenarios") or [cfg["scenario"]]
    n = n_seeds or ev.get("final_seeds") or len(EVAL_SEEDS)
    seeds = EVAL_SEEDS[:n]
    num_seconds = ev.get("num_seconds", cfg.get("num_seconds"))
    policy = registry.load_policy(cfg["algo"], str(run_dir), cfg)
    frames = []
    for sc in scenarios:
        df = evaluate(policy, sc, seeds, num_seconds=num_seconds, incident=ev.get("incident"))
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["method"] = cfg.get("name", cfg["algo"])  # keep ablation variants distinguishable
    out["train_seed"] = cfg.get("seed", 0)
    out["exp"] = cfg.get("exp", "dev")
    return out


def run_one(cfg: dict, *, do_eval: bool = False, eval_seeds: int | None = None, force: bool = False) -> Path:
    """Train (or just evaluate, for baselines) one config with cfg["seed"]; returns run_dir."""
    from agents import registry  # lazy: lets tests monkeypatch registry.ALGOS

    run_dir = resolve_run_dir(cfg)
    if is_done(run_dir) and not force:
        print(f"[train] {run_dir} already DONE, skipping")
        return run_dir
    (run_dir / DONE).unlink(missing_ok=True)
    save_config(cfg, run_dir)
    set_seed(int(cfg.get("seed", 0)))
    t0 = time.time()
    if cfg["algo"] not in registry.BASELINES:
        returned = registry.train(cfg)
        if returned:
            run_dir = Path(returned)
    train_s = time.time() - t0
    if do_eval:
        df = evaluate_run(cfg, run_dir, eval_seeds)
        df.to_csv(run_dir / "eval.csv", index=False)
    write_done(run_dir, algo=cfg["algo"], seed=cfg.get("seed", 0), train_seconds=round(train_s, 1), evaluated=do_eval)
    return run_dir


def build_cfgs(args) -> list[dict]:
    seeds = args.seeds if args.seeds else [args.seed if args.seed is not None else 0]
    cfgs = []
    for s in seeds:
        cfg = load_config(args.config, total_episodes=args.total_episodes, num_seconds=args.num_seconds)
        cfg["seed"] = s
        cfg.pop("run_dir", None)
        if args.run_dir:
            # one seed -> exactly this dir; several seeds -> <dir>/seed<k>
            cfg["run_dir"] = args.run_dir if len(seeds) == 1 else str(Path(args.run_dir) / f"seed{s}")
        cfgs.append(cfg)
    return cfgs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", required=True)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--seeds", type=int, nargs="+", default=None)
    p.add_argument("--total-episodes", type=int, default=None)
    p.add_argument("--num-seconds", type=int, default=None)
    p.add_argument("--run-dir", default=None)
    p.add_argument("--no-libsumo", action="store_true", help="use plain TraCI (needed to open sumo-gui)")
    p.add_argument("--eval", action="store_true", help="evaluate on cfg['eval']['scenarios'] and save eval.csv")
    p.add_argument("--eval-seeds", type=int, default=None, help="how many EVAL_SEEDS to use (default all 10)")
    p.add_argument("--force", action="store_true", help="re-run even if DONE exists")
    args = p.parse_args(argv)
    for cfg in build_cfgs(args):
        run_dir = run_one(cfg, do_eval=args.eval, eval_seeds=args.eval_seeds, force=args.force)
        print(f"[train] {cfg.get('exp')}/{cfg.get('name', cfg['algo'])} seed={cfg['seed']} -> {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
