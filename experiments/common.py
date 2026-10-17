"""Shared training utilities: configs, run directories, seeding and logging."""
from __future__ import annotations

import csv
import random
import time
from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_config(path: str | Path, **overrides) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg


def resolve_run_dir(cfg: dict) -> Path:
    if cfg.get("run_dir"):
        d = Path(cfg["run_dir"])
    else:
        d = REPO_ROOT / "runs" / cfg.get("exp", "dev") / cfg.get("name", cfg["algo"]) / f"seed{cfg.get('seed', 0)}"
    d.mkdir(parents=True, exist_ok=True)
    cfg["run_dir"] = str(d)
    return d


def save_config(cfg: dict, run_dir: str | Path) -> None:
    Path(run_dir, "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch

        torch.manual_seed(seed)
    except ImportError:
        pass


def episode_seed(seed: int, episode: int) -> int:
    """Demand seed for training episode `episode` of run seed `seed`. Always >= 10_000,
    so it never collides with env.scenarios.EVAL_SEEDS (1000..1009)."""
    return 10_000 + seed * 100_000 + episode


class TrainLogger:
    """Appends one row per episode to <run_dir>/train_log.csv and mirrors scalars to TensorBoard."""

    def __init__(self, run_dir: str | Path, tensorboard: bool = True):
        self.run_dir = Path(run_dir)
        self.path = self.run_dir / "train_log.csv"
        self._fields: list[str] | None = None
        self._t0 = time.time()
        self.tb = None
        if tensorboard:
            try:
                from torch.utils.tensorboard import SummaryWriter

                self.tb = SummaryWriter(str(self.run_dir / "tb"))
            except Exception:
                self.tb = None

    def log_episode(self, **row) -> None:
        row.setdefault("wall_time", round(time.time() - self._t0, 2))
        if self._fields is None:
            self._fields = list(row)
            with self.path.open("w", newline="") as f:
                csv.DictWriter(f, fieldnames=self._fields).writeheader()
        with self.path.open("a", newline="") as f:
            csv.DictWriter(f, fieldnames=self._fields, extrasaction="ignore").writerow(row)
        if self.tb is not None:
            step = int(row.get("env_steps", row.get("episode", 0)))
            for k, v in row.items():
                if isinstance(v, (int, float)) and k not in ("episode", "env_steps"):
                    self.tb.add_scalar(f"train/{k}", v, step)

    def close(self) -> None:
        if self.tb is not None:
            self.tb.close()


# ------------------------------------------------------------------ checkpoints
CHECKPOINTS = "checkpoints"  # run_dir/checkpoints/ep{N:04d}/ : self-contained, loadable with load_policy
BEST = "best"  # run_dir/best/ : copy of the checkpoint chosen on VAL_SEEDS (experiments/train.py)
DEFAULT_CHECKPOINT_EVERY = 20


def checkpoint_every(cfg: dict) -> int:
    """Episodes between checkpoints: cfg["eval"]["every_episodes"] (default 20)."""
    n = (cfg.get("eval") or {}).get("every_episodes") or DEFAULT_CHECKPOINT_EVERY
    return max(1, int(n))


def is_checkpoint_episode(cfg: dict, episodes_done: int, total_episodes: int) -> bool:
    """True after `episodes_done` finished episodes if a checkpoint is due (every N and at the end)."""
    return episodes_done > 0 and (episodes_done % checkpoint_every(cfg) == 0 or episodes_done == total_episodes)


def checkpoint_dir(run_dir: str | Path, episodes_done: int) -> Path:
    return Path(run_dir) / CHECKPOINTS / f"ep{int(episodes_done):04d}"


def snapshot_checkpoint(run_dir: str | Path, episodes_done: int, files: list[str]) -> Path:
    """Copy `files` (names relative to run_dir, just written by the learner) and config.yaml into
    run_dir/checkpoints/ep{N:04d}/, so that load_policy(<that dir>) works like load_policy(run_dir)."""
    import shutil

    run_dir = Path(run_dir)
    dst = checkpoint_dir(run_dir, episodes_done)
    dst.mkdir(parents=True, exist_ok=True)
    for name in [*files, "config.yaml"]:
        src = run_dir / name
        if src.exists():
            shutil.copy2(src, dst / name)
    return dst


def list_checkpoints(run_dir: str | Path) -> list[Path]:
    """Checkpoint dirs of a run, sorted by episode."""
    root = Path(run_dir) / CHECKPOINTS
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir() and p.name.startswith("ep")), key=lambda p: int(p.name[2:]))


def policy_dir(run_dir: str | Path) -> Path:
    """Directory to load a trained run from: run_dir/best (validation-selected checkpoint) if it
    exists, else run_dir itself (final model)."""
    best = Path(run_dir) / BEST
    return best if best.is_dir() else Path(run_dir)
