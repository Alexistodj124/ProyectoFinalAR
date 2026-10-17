"""Train one config for one or several seeds.

    python -m experiments.train --config experiments/configs/E3/dqn_double.yaml --seed 0
    python -m experiments.train --config X.yaml --seeds 0 1 2 3 4 --eval
    python -m experiments.train --config X.yaml --seed 0 --select-only   # (re)select a DONE run

Model selection (after training, skip with --no-select): every learner leaves self-contained
checkpoints in run_dir/checkpoints/ep{N:04d}/ (every cfg["eval"]["every_episodes"] episodes and
at the end). Each one is evaluated on the TRAINING scenario with the first
cfg["eval"]["val_seeds"] (default 2) VAL_SEEDS (2000..2004, disjoint from TRAIN/EVAL seeds and
from training episode seeds), full num_seconds; the lowest total_delay (mean_waiting_time if
evaluate.py does not report it) is copied to run_dir/best/ and every score goes to
run_dir/selection.csv. The final evaluation (eval.csv, EVAL_SEEDS) then loads
experiments.common.policy_dir(run_dir) = best/ if it exists, else run_dir (last model).
Cost: n_checkpoints x val_seeds evaluation episodes. Measured (4 processes in parallel, 2 seeds):
~3.2 s per checkpoint on cruce_pico and ~11 s on reforma_pico, so with 200 episodes, every 20
(10 checkpoints) it is ~35 s (cruce) or ~110-120 s (reforma) per run, about 10 % of the training
time. A run with a single checkpoint (e.g. --quick) is copied to best/ without evaluating.

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

from experiments.common import BEST, CHECKPOINTS, list_checkpoints, load_config, policy_dir, resolve_run_dir, save_config, set_seed

DONE = "DONE"
SELECTION = "selection.csv"
DEFAULT_VAL_SEEDS = 2


def is_done(run_dir: str | Path) -> bool:
    return (Path(run_dir) / DONE).exists()


def write_done(run_dir: str | Path, **info) -> None:
    info.setdefault("finished_at", time.strftime("%Y-%m-%d %H:%M:%S"))
    (Path(run_dir) / DONE).write_text(json.dumps(info, indent=1, default=str))


def selection_criterion(df) -> str:
    """Column used to rank checkpoints: total_delay (counts the insertion backlog, see
    docs/ajuste_aprendizaje.md) when evaluate.py reports it, else mean_waiting_time."""
    if "total_delay" in df.columns and df["total_delay"].notna().all():
        return "total_delay"
    return "mean_waiting_time"


def select_checkpoint(cfg: dict, run_dir: str | Path, n_val: int | None = None):
    """Evaluate every checkpoint of run_dir on VAL_SEEDS, copy the best one to run_dir/best/ and
    write run_dir/selection.csv. Returns the selection DataFrame (None if there are no checkpoints)."""
    import shutil

    import pandas as pd

    from agents import registry
    from env.scenarios import VAL_SEEDS
    from experiments.evaluate import evaluate

    run_dir = Path(run_dir)
    ckpts = list_checkpoints(run_dir)
    if not ckpts:
        return None
    ev = cfg.get("eval") or {}
    n = int(n_val or ev.get("val_seeds") or DEFAULT_VAL_SEEDS)
    seeds = VAL_SEEDS[:n]
    rows, frames = [], []
    if len(ckpts) == 1:  # nothing to choose: no evaluation needed
        rows.append({"checkpoint": ckpts[0].name, "episode": int(ckpts[0].name[2:]), "criterion": "", "score": float("nan")})
    else:
        for c in ckpts:
            t0 = time.time()
            policy = registry.load_policy(cfg["algo"], str(c), cfg)
            df = evaluate(policy, cfg["scenario"], seeds, num_seconds=cfg.get("num_seconds"))
            df = df.assign(checkpoint=c.name)
            frames.append(df)
            row = {"checkpoint": c.name, "episode": int(c.name[2:]), "eval_seconds": round(time.time() - t0, 1)}
            for col in ("total_delay", "mean_waiting_time", "max_wait_cross_streets", "throughput_veh_h", "teleported"):
                if col in df.columns:
                    row[col] = float(df[col].mean())
            rows.append(row)
            print(f"[select] {run_dir.name} {c.name}: " + ", ".join(f"{k}={v:.2f}" for k, v in row.items() if isinstance(v, float)), flush=True)
        crit = selection_criterion(pd.concat(frames, ignore_index=True))
        for r in rows:
            r["criterion"], r["score"] = crit, r[crit]
    sel = pd.DataFrame(rows)
    sel["val_seeds"] = " ".join(str(s) for s in seeds)
    best_i = 0 if len(sel) == 1 else int(sel["score"].to_numpy().argmin())
    sel["selected"] = [i == best_i for i in range(len(sel))]
    best = run_dir / BEST
    if best.exists():
        shutil.rmtree(best)
    shutil.copytree(ckpts[best_i], best)
    sel.to_csv(run_dir / SELECTION, index=False)
    if frames:
        pd.concat(frames, ignore_index=True).to_csv(run_dir / "selection_episodes.csv", index=False)
    print(f"[select] {run_dir} -> best = {ckpts[best_i].name}", flush=True)
    return sel


def clear_selection(run_dir: str | Path) -> None:
    """Remove the outputs of a previous training of this run_dir (checkpoints, best/, selection)."""
    import shutil

    run_dir = Path(run_dir)
    for d in (CHECKPOINTS, BEST):
        if (run_dir / d).exists():
            shutil.rmtree(run_dir / d)
    for f in (SELECTION, "selection_episodes.csv"):
        (run_dir / f).unlink(missing_ok=True)


def evaluate_run(cfg: dict, run_dir: str | Path, n_seeds: int | None = None):
    """Final evaluation of a trained run on cfg["eval"]["scenarios"] (EVAL_SEEDS, never
    used in training nor in model selection). Loads policy_dir(run_dir): the checkpoint chosen
    on VAL_SEEDS (best/) if there is one, else the final model. Returns a DataFrame with one row
    per episode (contract §7)."""
    import pandas as pd

    from agents import registry
    from env.scenarios import EVAL_SEEDS
    from experiments.evaluate import evaluate  # built by feat/baselines-eval

    ev = cfg.get("eval") or {}
    scenarios = ev.get("scenarios") or [cfg["scenario"]]
    n = n_seeds or ev.get("final_seeds") or len(EVAL_SEEDS)
    seeds = EVAL_SEEDS[:n]
    num_seconds = ev.get("num_seconds", cfg.get("num_seconds"))
    policy = registry.load_policy(cfg["algo"], str(policy_dir(run_dir)), cfg)
    frames = []
    for sc in scenarios:
        df = evaluate(policy, sc, seeds, num_seconds=num_seconds, incident=ev.get("incident"))
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["method"] = cfg.get("name", cfg["algo"])  # keep ablation variants distinguishable
    out["train_seed"] = cfg.get("seed", 0)
    out["exp"] = cfg.get("exp", "dev")
    return out


def run_one(cfg: dict, *, do_eval: bool = False, eval_seeds: int | None = None, force: bool = False,
            select: bool = True, val_seeds: int | None = None) -> Path:
    """Train (or just evaluate, for baselines) one config with cfg["seed"], select the best
    checkpoint on VAL_SEEDS (unless select=False) and optionally evaluate; returns run_dir."""
    from agents import registry  # lazy: lets tests monkeypatch registry.ALGOS

    run_dir = resolve_run_dir(cfg)
    if is_done(run_dir) and not force:
        print(f"[train] {run_dir} already DONE, skipping")
        return run_dir
    (run_dir / DONE).unlink(missing_ok=True)
    clear_selection(run_dir)
    save_config(cfg, run_dir)
    set_seed(int(cfg.get("seed", 0)))
    t0 = time.time()
    learner = cfg["algo"] not in registry.BASELINES
    if learner:
        returned = registry.train(cfg)
        if returned:
            run_dir = Path(returned)
    train_s = time.time() - t0
    info = {}
    if learner and select:
        t1 = time.time()
        sel = select_checkpoint(cfg, run_dir, val_seeds)
        if sel is not None:
            info = {"select_seconds": round(time.time() - t1, 1), "best_checkpoint": str(sel.loc[sel["selected"], "checkpoint"].iloc[0]),
                    "n_checkpoints": len(sel)}
    if do_eval:
        df = evaluate_run(cfg, run_dir, eval_seeds)
        df.to_csv(run_dir / "eval.csv", index=False)
    write_done(run_dir, algo=cfg["algo"], seed=cfg.get("seed", 0), train_seconds=round(train_s, 1), evaluated=do_eval,
               policy_dir=policy_dir(run_dir).name, **info)
    return run_dir


def select_only(cfg: dict, *, val_seeds: int | None = None, do_eval: bool = False, eval_seeds: int | None = None) -> Path:
    """(Re)run the model selection (and optionally the final evaluation) of an already trained run."""
    run_dir = resolve_run_dir(cfg)
    saved = run_dir / "config.yaml"
    if saved.exists():  # the resolved config of the training (same algo, scenario, hparams)
        cfg = {**load_config(saved), "run_dir": str(run_dir)}
    sel = select_checkpoint(cfg, run_dir, val_seeds)
    if sel is None:
        print(f"[select] {run_dir}: no checkpoints/ (trained before periodic checkpoints?)")
    if do_eval:
        evaluate_run(cfg, run_dir, eval_seeds).to_csv(run_dir / "eval.csv", index=False)
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
    p.add_argument("--no-select", action="store_true", help="skip the checkpoint selection on VAL_SEEDS (evaluate the last model)")
    p.add_argument("--val-seeds", type=int, default=None, help="how many VAL_SEEDS for the selection (default cfg eval.val_seeds or 2)")
    p.add_argument("--select-only", action="store_true", help="do not train: (re)select the checkpoints of an existing run")
    args = p.parse_args(argv)
    for cfg in build_cfgs(args):
        if args.select_only:
            run_dir = select_only(cfg, val_seeds=args.val_seeds, do_eval=args.eval, eval_seeds=args.eval_seeds)
            print(f"[select] {cfg.get('exp')}/{cfg.get('name', cfg['algo'])} seed={cfg['seed']} -> {policy_dir(run_dir)}")
            continue
        run_dir = run_one(cfg, do_eval=args.eval, eval_seeds=args.eval_seeds, force=args.force,
                          select=not args.no_select, val_seeds=args.val_seeds)
        print(f"[train] {cfg.get('exp')}/{cfg.get('name', cfg['algo'])} seed={cfg['seed']} -> {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
