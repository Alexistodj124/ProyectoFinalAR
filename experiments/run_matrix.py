"""Run the experiment matrix E1-E8 (PLAN section 8.2), or any glob of configs x seeds.

    python -m experiments.run_matrix --dry-run                      # what would run
    python -m experiments.run_matrix --exp E3 --seeds 0 1 --jobs 4
    python -m experiments.run_matrix --glob 'experiments/configs/E5/*.yaml' --quick

Phases (each one waits for the previous one):
    1  E1 baselines evaluation        (experiments.evaluate --config)
    2  E2..E6 training (+ final eval) (experiments.train, one process per config x seed)
    3  E7 robustness                  (experiments.robustness, needs the trained runs)
    4  E8 fairness collection         (experiments.robustness --fairness, reads eval CSVs)
Every job is its own process (own libsumo). A job whose run_dir has a DONE marker is skipped,
so an interrupted matrix can simply be launched again. Results go to <runs-dir>/manifest.csv.
"""
from __future__ import annotations

import argparse
import csv
import glob as globmod
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "experiments" / "configs"
DEFAULT_SEEDS = [0, 1, 2, 3, 4]  # = env.scenarios.TRAIN_SEEDS
TRAIN_EXPS = ["E2", "E3", "E4", "E5", "E6"]
ALL_EXPS = ["E1"] + TRAIN_EXPS + ["E7", "E8"]
QUICK = {"num_seconds": 120, "total_episodes": 2, "eval_seeds": 2}
MANIFEST_FIELDS = ["exp", "name", "kind", "seed", "status", "returncode", "wall_s", "run_dir", "config", "finished_at"]


@dataclass
class Job:
    exp: str
    name: str
    kind: str  # eval | train | robustness | fairness
    config: str
    run_dir: Path
    seed: int | None = None
    cmd: list[str] = field(default_factory=list)
    phase: int = 0
    upstream: list[Path] = field(default_factory=list)  # derived jobs (E7/E8): re-run if any upstream is newer

    @property
    def done_path(self) -> Path:
        return self.run_dir / "DONE"

    def is_done(self) -> bool:
        if not self.done_path.exists():
            return False
        if self.upstream:  # derived result is stale if any input finished later
            newest = max((p.stat().st_mtime for p in self.upstream if p.exists()), default=0)
            return self.done_path.stat().st_mtime >= newest
        return True


def _py(*args: str) -> list[str]:
    return [sys.executable, "-m", *args]


def _config_files(exp: str, extra_globs: list[str] | None) -> list[Path]:
    if extra_globs:
        files = sorted({Path(f) for g in extra_globs for f in globmod.glob(g if os.path.isabs(g) else str(REPO_ROOT / g), recursive=True)})
        return [f for f in files if f.suffix in (".yaml", ".yml")]
    return sorted((CONFIG_DIR / exp).glob("*.yaml"))


def _cfg_meta(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text()) or {}
    cfg.setdefault("exp", path.parent.name)
    cfg.setdefault("name", cfg.get("algo", path.stem))
    return cfg


def build_jobs(exps: list[str], seeds: list[int], runs_dir: Path, *, quick: bool = False, do_eval: bool = True,
               globs: list[str] | None = None, no_libsumo: bool = False) -> list[Job]:
    """Pure function (no I/O except reading configs): the list of jobs of the matrix."""
    jobs: list[Job] = []
    flags = ["--no-libsumo"] if no_libsumo else []

    if globs:  # explicit glob: every matching config is a training config
        for f in _config_files("", globs):
            cfg = _cfg_meta(f)
            if cfg.get("algo") is None:
                continue
            jobs += _train_jobs(f, cfg, seeds, runs_dir, quick, do_eval, flags, phase=2)
        return jobs

    for exp in exps:
        if exp == "E1":
            for f in _config_files(exp, None):
                out = runs_dir / "E1" / f.stem
                cmd = _py("experiments.evaluate", "--config", str(f), "--out-dir", str(out))
                if quick:
                    cmd += ["--num-seconds", str(QUICK["num_seconds"]), "--seeds", "1000", "1001"]
                jobs.append(Job("E1", f.stem, "eval", str(f), out, None, cmd, phase=1))
        elif exp in TRAIN_EXPS:
            for f in _config_files(exp, None):
                cfg = _cfg_meta(f)
                if cfg.get("algo") is None:
                    continue
                jobs += _train_jobs(f, cfg, seeds, runs_dir, quick, do_eval, flags, phase=2)
        elif exp == "E7":
            for f in _config_files(exp, None):
                out = runs_dir / "E7"
                cmd = _py("experiments.robustness", "--config", str(f), "--runs-dir", str(runs_dir), "--out", str(out / "robustness.csv"))
                if quick:
                    cmd += ["--num-seconds", str(QUICK["num_seconds"]), "--eval-seeds", str(QUICK["eval_seeds"])]
                jobs.append(Job("E7", f.stem, "robustness", str(f), out, None, cmd, phase=3))
        elif exp == "E8":
            for f in _config_files(exp, None):
                out = runs_dir / "E8"
                cmd = _py("experiments.robustness", "--fairness", "--config", str(f), "--runs-dir", str(runs_dir), "--out", str(out / "fairness.csv"))
                jobs.append(Job("E8", f.stem, "fairness", str(f), out, None, cmd, phase=4))
    return jobs


def _train_jobs(f: Path, cfg: dict, seeds: list[int], runs_dir: Path, quick: bool, do_eval: bool, flags: list[str], phase: int) -> list[Job]:
    out = []
    for s in seeds:
        rd = runs_dir / str(cfg["exp"]) / str(cfg["name"]) / f"seed{s}"
        cmd = _py("experiments.train", "--config", str(f), "--seed", str(s), "--run-dir", str(rd), *flags)
        if do_eval:
            cmd.append("--eval")
        if quick:
            cmd += ["--num-seconds", str(QUICK["num_seconds"]), "--total-episodes", str(QUICK["total_episodes"]),
                    "--eval-seeds", str(QUICK["eval_seeds"])]
        out.append(Job(str(cfg["exp"]), str(cfg["name"]), "train", str(f), rd, s, cmd, phase=phase))
    return out


def attach_upstream(jobs: list[Job]) -> None:
    """E7/E8 must be re-run when any E1-E6 job finished after them."""
    markers = [j.done_path for j in jobs if j.kind in ("train", "eval")]
    for j in jobs:
        if j.kind in ("robustness", "fairness"):
            j.upstream = markers
    # E8 also reads E7's output
    e7 = [j.done_path for j in jobs if j.kind == "robustness"]
    for j in jobs:
        if j.kind == "fairness":
            j.upstream = j.upstream + e7


# ---------------------------------------------------------------- execution
def subprocess_runner(job: Job, env: dict) -> int:
    job.run_dir.mkdir(parents=True, exist_ok=True)
    with (job.run_dir / "stdout.log").open("w") as log:
        return subprocess.run(job.cmd, cwd=REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT).returncode


class Manifest:
    """runs/manifest.csv: one row per job, updated in place (thread-safe)."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.rows: dict[tuple, dict] = {}
        if path.exists():
            for r in csv.DictReader(path.open()):
                self.rows[(r["exp"], r["name"], r["kind"], r["seed"])] = r

    def update(self, job: Job, status: str, returncode: int | str = "", wall_s: float | str = "") -> None:
        row = {"exp": job.exp, "name": job.name, "kind": job.kind, "seed": "" if job.seed is None else job.seed,
               "status": status, "returncode": returncode, "wall_s": wall_s, "run_dir": str(job.run_dir),
               "config": job.config, "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        with self.lock:
            self.rows[(job.exp, job.name, job.kind, str(row["seed"]))] = row
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
                w.writeheader()
                w.writerows(self.rows.values())


def run_jobs(jobs: list[Job], *, n_jobs: int = 1, manifest: Manifest | None = None, force: bool = False,
             runner=subprocess_runner, no_libsumo: bool = False) -> dict[str, int]:
    """Run phase by phase; inside a phase up to n_jobs processes at once. Returns status counts."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    if not no_libsumo:
        env["LIBSUMO_AS_TRACI"] = "1"
    if n_jobs > 1:
        env.setdefault("OMP_NUM_THREADS", "1")  # avoid N torch processes fighting for the same cores
    counts = {"done": 0, "skipped": 0, "failed": 0}

    def work(job: Job) -> None:
        if job.is_done() and not force:
            counts["skipped"] += 1
            if manifest:
                manifest.update(job, "skipped")
            print(f"[skip] {job.exp}/{job.name} seed={job.seed}")
            return
        job.done_path.unlink(missing_ok=True)
        print(f"[run ] {job.exp}/{job.name} seed={job.seed}", flush=True)
        t0 = time.time()
        rc = runner(job, env)
        wall = round(time.time() - t0, 1)
        if rc == 0:
            if not job.done_path.exists():  # eval/robustness CLIs don't write the marker themselves
                job.run_dir.mkdir(parents=True, exist_ok=True)
                job.done_path.write_text(f'{{"finished_at": "{time.strftime("%Y-%m-%d %H:%M:%S")}"}}')
            counts["done"] += 1
        else:
            counts["failed"] += 1
            print(f"[FAIL] {job.exp}/{job.name} seed={job.seed} rc={rc} (see {job.run_dir}/stdout.log)")
        if manifest:
            manifest.update(job, "done" if rc == 0 else "failed", rc, wall)

    for phase in sorted({j.phase for j in jobs}):
        batch = [j for j in jobs if j.phase == phase]
        if n_jobs > 1:
            with ThreadPoolExecutor(max_workers=n_jobs) as ex:
                list(ex.map(work, batch))
        else:
            for j in batch:
                work(j)
    return counts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--exp", nargs="+", default=None, help="E1..E8 (default: all)")
    p.add_argument("--glob", nargs="+", default=None, help="config glob(s) instead of --exp, e.g. 'experiments/configs/E3/*.yaml'")
    p.add_argument("--seeds", type=int, nargs="+", default=DEFAULT_SEEDS)
    p.add_argument("--jobs", type=int, default=1, help="parallel processes (each with its own libsumo)")
    p.add_argument("--runs-dir", default=None, help="default runs/ (runs/_quick with --quick)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--quick", action="store_true", help=f"smoke test: {QUICK}")
    p.add_argument("--force", action="store_true", help="ignore DONE markers")
    p.add_argument("--no-eval", action="store_true", help="skip the final evaluation after training")
    p.add_argument("--no-libsumo", action="store_true")
    a = p.parse_args(argv)

    runs_dir = Path(a.runs_dir) if a.runs_dir else REPO_ROOT / "runs" / ("_quick" if a.quick else "")
    exps = [e.upper() for e in (a.exp or ALL_EXPS)]
    bad = [e for e in exps if e not in ALL_EXPS]
    if bad:
        p.error(f"unknown experiment(s) {bad}; choose from {ALL_EXPS}")
    jobs = build_jobs(exps, a.seeds, runs_dir, quick=a.quick, do_eval=not a.no_eval, globs=a.glob, no_libsumo=a.no_libsumo)
    attach_upstream(jobs)
    if not jobs:
        print("No configs found for", a.glob or exps)
        return 0
    if a.dry_run:
        for j in jobs:
            state = "skip (DONE)" if j.is_done() and not a.force else "run"
            print(f"phase {j.phase}  {state:11s} {j.exp}/{j.name} seed={j.seed}  -> {j.run_dir}")
        print(f"{len(jobs)} jobs, {sum(1 for j in jobs if not j.is_done() or a.force)} would run")
        return 0
    counts = run_jobs(jobs, n_jobs=a.jobs, manifest=Manifest(runs_dir / "manifest.csv"), force=a.force, no_libsumo=a.no_libsumo)
    print(f"finished: {counts}  manifest: {runs_dir / 'manifest.csv'}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
