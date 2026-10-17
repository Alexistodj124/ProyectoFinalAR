"""Periodic checkpoints of every learner and validation-based model selection (experiments/train.py).

The per-algorithm tests run tiny trainings on the toy nets (regular TraCI, so they share the pytest
process); the selection tests use a dummy algorithm and a fake evaluate (no SUMO).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest
import yaml

from agents import registry
from env.scenarios import EVAL_SEEDS, TRAIN_SEEDS, VAL_SEEDS
from experiments import train
from experiments.common import (
    TrainLogger,
    checkpoint_every,
    episode_seed,
    is_checkpoint_episode,
    list_checkpoints,
    policy_dir,
    resolve_run_dir,
    save_config,
    snapshot_checkpoint,
)


# ---------------------------------------------------------------- helpers (no SUMO)
def test_seed_sets_are_disjoint():
    train_eps = {episode_seed(s, ep) for s in TRAIN_SEEDS for ep in range(1000)}
    assert len(VAL_SEEDS) == 5
    assert not set(VAL_SEEDS) & set(EVAL_SEEDS)
    assert not set(VAL_SEEDS) & set(TRAIN_SEEDS)
    assert not set(VAL_SEEDS) & train_eps and min(train_eps) >= 10_000


def test_checkpoint_schedule():
    assert checkpoint_every({}) == 20 and checkpoint_every({"eval": {"every_episodes": 5}}) == 5
    cfg = {"eval": {"every_episodes": 20}}
    due = [n for n in range(1, 51) if is_checkpoint_episode(cfg, n, 50)]
    assert due == [20, 40, 50]  # every N and always at the end
    assert not is_checkpoint_episode(cfg, 0, 50)


def test_snapshot_list_and_policy_dir(tmp_path):
    (tmp_path / "config.yaml").write_text("algo: x\n")
    for ep in (10, 2):
        (tmp_path / "model.pt").write_text(f"ep{ep}")
        d = snapshot_checkpoint(tmp_path, ep, ["model.pt", "missing.bin"])
        assert (d / "config.yaml").exists() and not (d / "missing.bin").exists()
    assert [p.name for p in list_checkpoints(tmp_path)] == ["ep0002", "ep0010"]  # numeric order
    assert (tmp_path / "checkpoints" / "ep0002" / "model.pt").read_text() == "ep2"
    assert policy_dir(tmp_path) == tmp_path
    (tmp_path / "best").mkdir()
    assert policy_dir(tmp_path) == tmp_path / "best"
    assert list_checkpoints(tmp_path / "nothing") == []


# ---------------------------------------------------------------- every learner (SUMO, toy nets)
SINGLE = {"scenario": "toy_single"}
GRID = {"scenario": "toy_grid2x2"}
MARL_HP = {"learning_starts": 10, "batch_size": 8, "device": "cpu", "hidden": [16]}
CASES = {
    "qlearning": (SINGLE, {}),
    "dyna_q": (SINGLE, {"n_planning": 3}),
    "dqn": (SINGLE, {"learning_starts": 10, "batch_size": 8, "target_update": 10, "buffer_size": 200, "device": "cpu"}),
    "ppo": (SINGLE, {"n_steps": 20, "batch_size": 10, "n_epochs": 1}),
    "idqn": (GRID, MARL_HP),
    "qmix": (GRID, MARL_HP),
    "mappo": (GRID, {**MARL_HP, "n_steps": 10, "critic_hidden": [16]}),
    "comm": (GRID, {**MARL_HP, "msg_dim": 2, "msg_hidden": 8}),
}
FILES = {"qlearning": ["qtable.npz"], "dyna_q": ["qtable.npz", "model.pkl", "qtable_vi.npz"], "ppo": ["model.zip", "vecnormalize.pkl"]}


def _rollout_same_actions(algo: str, dirs: list[Path], scenario: str, seconds: int = 40) -> None:
    """Load a policy from each dir and check that they act identically along one episode."""
    from env.reforma_env import get_sumo_env, make_parallel_env

    pols = [registry.load_policy(algo, str(d)) for d in dirs]
    env = make_parallel_env(scenario, 1000, num_seconds=seconds)
    try:
        obs, _ = env.reset(seed=1000)
        se = get_sumo_env(env)
        for p in pols:
            p.reset(se)
        while env.agents:
            acts = [p.act(obs) for p in pols]
            assert all(a == acts[0] for a in acts), acts
            assert set(acts[0]) == set(obs)
            obs, *_ = env.step(acts[0])
    finally:
        env.close()


@pytest.mark.slow
@pytest.mark.parametrize("algo", list(CASES))
def test_learner_writes_loadable_checkpoints(algo, tmp_path):
    base, hp = CASES[algo]
    cfg = dict(exp="t", algo=algo, name=f"{algo}_ck", seed=0, total_episodes=3, num_seconds=100,
               run_dir=str(tmp_path / "run"), eval={"every_episodes": 2}, hparams=dict(hp), **base)
    run_dir = Path(registry.train(cfg))
    ckpts = list_checkpoints(run_dir)
    assert [c.name for c in ckpts] == ["ep0002", "ep0003"]  # every 2 episodes + the last one
    for c in ckpts:
        assert (c / "config.yaml").exists()
        for f in FILES.get(algo, ["model.pt"]):
            assert (c / f).exists(), (c, f)
    # the last checkpoint is the final model kept in run_dir; ep0002 loads too
    _rollout_same_actions(algo, [run_dir, ckpts[-1]], base["scenario"])
    pol = registry.load_policy(algo, str(ckpts[0]))
    assert hasattr(pol, "act")


# ---------------------------------------------------------------- selection (no SUMO)
dummy = types.ModuleType("tests_dummy_ckpt_algo")
dummy.SCORES = {}  # checkpoint name -> validation total_delay


def _dummy_train(cfg):
    run_dir = resolve_run_dir(cfg)
    save_config(cfg, run_dir)
    log = TrainLogger(run_dir, tensorboard=False)
    total = cfg["total_episodes"]
    for ep in range(total):
        log.log_episode(episode=ep, env_steps=ep + 1, **{"return": -float(ep)}, mean_waiting_time=1.0)
        if is_checkpoint_episode(cfg, ep + 1, total):
            (Path(run_dir) / "model.pt").write_text(f"ep{ep + 1:04d}")
            snapshot_checkpoint(run_dir, ep + 1, ["model.pt"])
    return str(run_dir)


def _dummy_load(run_dir):
    return types.SimpleNamespace(name="dummy", tag=(Path(run_dir) / "model.pt").read_text(), dir=str(run_dir))


dummy.train = _dummy_train
dummy.load_policy = _dummy_load


@pytest.fixture
def fake(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "tests_dummy_ckpt_algo", dummy)
    monkeypatch.setitem(registry.ALGOS, "dummyck", "tests_dummy_ckpt_algo")
    fake_eval = types.ModuleType("experiments.evaluate")
    state = {"with_total_delay": True}

    def evaluate(policy, scenario, seeds=(1000,), *, num_seconds=None, incident=None, out_dir=None):
        calls.append((policy.tag, scenario, tuple(seeds), num_seconds))
        score = dummy.SCORES.get(policy.tag, 100.0)
        df = pd.DataFrame({"method": "dummy", "scenario": scenario, "seed": list(seeds),
                           "mean_waiting_time": 1000.0 - score, "throughput_veh_h": 1.0})
        if state["with_total_delay"]:
            df["total_delay"] = score
        return df

    fake_eval.evaluate = evaluate
    monkeypatch.setitem(sys.modules, "experiments.evaluate", fake_eval)
    return types.SimpleNamespace(calls=calls, state=state)


def _cfg_file(tmp_path, **kw) -> Path:
    cfg = {"exp": "E3", "algo": "dummyck", "name": "d", "scenario": "toy_single", "total_episodes": 10,
           "num_seconds": 600, "eval": {"scenarios": ["toy_single", "toy_grid2x2"], "every_episodes": 3, "val_seeds": 2}}
    cfg.update(kw)
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def test_selection_picks_argmin_writes_best_and_evaluates_it(tmp_path, fake):
    dummy.SCORES = {"ep0003": 50.0, "ep0006": 20.0, "ep0009": 35.0, "ep0010": 60.0}
    rd = tmp_path / "run"
    assert train.main(["--config", str(_cfg_file(tmp_path)), "--seed", "0", "--run-dir", str(rd), "--eval", "--eval-seeds", "2"]) == 0
    val_calls = [c for c in fake.calls if c[2] == tuple(VAL_SEEDS[:2])]
    assert [c[0] for c in val_calls] == ["ep0003", "ep0006", "ep0009", "ep0010"]
    assert all(c[1] == "toy_single" and c[3] == 600 for c in val_calls)  # training scenario, full num_seconds
    sel = pd.read_csv(rd / "selection.csv")
    assert list(sel["checkpoint"]) == ["ep0003", "ep0006", "ep0009", "ep0010"]
    assert set(sel["criterion"]) == {"total_delay"} and list(sel["score"]) == [50.0, 20.0, 35.0, 60.0]
    assert sel.loc[sel["selected"], "checkpoint"].tolist() == ["ep0006"]
    assert (rd / "best" / "model.pt").read_text() == "ep0006" and (rd / "best" / "config.yaml").exists()
    assert (rd / "model.pt").read_text() == "ep0010"  # run_dir keeps the last model
    assert policy_dir(rd) == rd / "best"
    eval_calls = [c for c in fake.calls if c[2] == tuple(EVAL_SEEDS[:2])]
    assert {c[0] for c in eval_calls} == {"ep0006"} and {c[1] for c in eval_calls} == {"toy_single", "toy_grid2x2"}
    done = yaml.safe_load((rd / "DONE").read_text())
    assert done["best_checkpoint"] == "ep0006" and done["policy_dir"] == "best" and done["n_checkpoints"] == 4


def test_selection_falls_back_to_mean_waiting_time(tmp_path, fake):
    fake.state["with_total_delay"] = False
    dummy.SCORES = {"ep0003": 50.0, "ep0006": 20.0, "ep0009": 35.0, "ep0010": 60.0}  # mwt = 1000 - score
    rd = tmp_path / "run"
    train.main(["--config", str(_cfg_file(tmp_path)), "--seed", "0", "--run-dir", str(rd)])
    sel = pd.read_csv(rd / "selection.csv")
    assert set(sel["criterion"]) == {"mean_waiting_time"}
    assert sel.loc[sel["selected"], "checkpoint"].tolist() == ["ep0010"]


def test_no_select_and_single_checkpoint(tmp_path, fake):
    rd = tmp_path / "a"
    train.main(["--config", str(_cfg_file(tmp_path)), "--seed", "0", "--run-dir", str(rd), "--no-select", "--eval"])
    assert not (rd / "best").exists() and not (rd / "selection.csv").exists()
    assert {c[0] for c in fake.calls} == {"ep0010"}  # final eval on run_dir (= last model)
    fake.calls.clear()
    rd = tmp_path / "b"  # one checkpoint only: copied without evaluating anything
    train.main(["--config", str(_cfg_file(tmp_path, total_episodes=2)), "--seed", "0", "--run-dir", str(rd)])
    assert fake.calls == [] and (rd / "best" / "model.pt").read_text() == "ep0002"


def test_select_only_and_force_clears_old_selection(tmp_path, fake):
    dummy.SCORES = {"ep0003": 5.0}
    rd = tmp_path / "run"
    cfg = str(_cfg_file(tmp_path))
    train.main(["--config", cfg, "--seed", "0", "--run-dir", str(rd), "--no-select"])
    assert not (rd / "best").exists()
    train.main(["--config", cfg, "--seed", "0", "--run-dir", str(rd), "--select-only"])
    assert (rd / "best" / "model.pt").read_text() == "ep0003"
    # retraining with fewer episodes must not keep stale checkpoints/best from the previous run
    train.main(["--config", str(_cfg_file(tmp_path, total_episodes=2)), "--seed", "0", "--run-dir", str(rd), "--force", "--no-select"])
    assert [c.name for c in list_checkpoints(rd)] == ["ep0002"] and not (rd / "best").exists()
