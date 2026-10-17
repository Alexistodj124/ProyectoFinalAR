"""Tests of experiments/train.py, run_matrix.py and robustness.py (no SUMO needed except one fast incident-edge test)."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest
import yaml

from agents import registry
from experiments import robustness, run_matrix, train
from experiments.common import TrainLogger, resolve_run_dir

# ---------------------------------------------------------------- dummy algorithm
dummy = types.ModuleType("tests_dummy_algo")
dummy.CALLS = []


def _dummy_train(cfg):
    run_dir = resolve_run_dir(cfg)
    log = TrainLogger(run_dir, tensorboard=False)
    for ep in range(cfg["total_episodes"]):
        log.log_episode(episode=ep, env_steps=(ep + 1) * 10, **{"return": -100 + ep + cfg["seed"], "mean_waiting_time": 50 - ep})
    dummy.CALLS.append((cfg["seed"], cfg["num_seconds"]))
    (Path(run_dir) / "model.pt").write_text("x")
    return str(run_dir)


dummy.train = _dummy_train
dummy.load_policy = lambda run_dir: ("policy", run_dir)


@pytest.fixture
def fake_algo(monkeypatch):
    dummy.CALLS.clear()
    monkeypatch.setitem(sys.modules, "tests_dummy_algo", dummy)
    monkeypatch.setitem(registry.ALGOS, "dummy", "tests_dummy_algo")

    fake_eval = types.ModuleType("experiments.evaluate")

    def evaluate(policy, scenario, seeds=(1000,), *, num_seconds=None, incident=None, out_dir=None):
        return pd.DataFrame({"method": "dummy", "scenario": scenario, "seed": list(seeds),
                             "mean_waiting_time": 10.0, "throughput_veh_h": 100.0})

    fake_eval.evaluate = evaluate
    monkeypatch.setitem(sys.modules, "experiments.evaluate", fake_eval)
    return dummy


def write_cfg(path: Path, **kw) -> Path:
    cfg = {"exp": "E3", "algo": "dummy", "name": "dummy_a", "scenario": "toy_single", "total_episodes": 4,
           "num_seconds": 600, "eval": {"scenarios": ["toy_single", "toy_grid2x2"]}}
    cfg.update(kw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg))
    return path


# ---------------------------------------------------------------- train.py
def test_train_end_to_end_multi_seed_with_eval(tmp_path, fake_algo):
    cfg = write_cfg(tmp_path / "c.yaml")
    rc = train.main(["--config", str(cfg), "--seeds", "0", "1", "--run-dir", str(tmp_path / "out"),
                     "--total-episodes", "3", "--num-seconds", "120", "--eval", "--eval-seeds", "2"])
    assert rc == 0
    assert fake_algo.CALLS == [(0, 120), (1, 120)]  # overrides applied, one train() per seed
    for s in (0, 1):
        d = tmp_path / "out" / f"seed{s}"
        assert (d / "DONE").exists() and (d / "config.yaml").exists()
        assert len(pd.read_csv(d / "train_log.csv")) == 3
        ev = pd.read_csv(d / "eval.csv")
        assert set(ev["scenario"]) == {"toy_single", "toy_grid2x2"} and len(ev) == 4
        assert set(ev["method"]) == {"dummy_a"} and set(ev["train_seed"]) == {s}


def test_train_skips_done_and_force_reruns(tmp_path, fake_algo):
    cfg = write_cfg(tmp_path / "c.yaml")
    args = ["--config", str(cfg), "--seed", "0", "--run-dir", str(tmp_path / "r")]
    train.main(args)
    train.main(args)
    assert len(fake_algo.CALLS) == 1
    train.main(args + ["--force"])
    assert len(fake_algo.CALLS) == 2


def test_import_does_not_set_libsumo_env_but_cli_does():
    import os
    import subprocess

    env = {k: v for k, v in os.environ.items() if k != "LIBSUMO_AS_TRACI"}
    code = "import os, experiments.train; print(os.environ.get('LIBSUMO_AS_TRACI'))"
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True).stdout
    assert out.strip() == "None"  # importing must not leak the variable into other code
    src = Path(train.__file__).read_text().split("import argparse")[0]
    assert 'os.environ.setdefault("LIBSUMO_AS_TRACI", "1")' in src  # set before any sumo import when run as CLI


# ---------------------------------------------------------------- run_matrix
@pytest.fixture
def cfg_tree(tmp_path, monkeypatch):
    root = tmp_path / "configs"
    write_cfg(root / "E1" / "baselines.yaml", algo=None)
    write_cfg(root / "E3" / "a.yaml", name="a")
    write_cfg(root / "E3" / "b.yaml", name="b")
    write_cfg(root / "E5" / "m.yaml", exp="E5", name="m")
    write_cfg(root / "E7" / "robustness.yaml", exp="E7")
    write_cfg(root / "E8" / "fairness.yaml", exp="E8")
    monkeypatch.setattr(run_matrix, "CONFIG_DIR", root)
    return root


def test_build_jobs_matrix(cfg_tree, tmp_path):
    jobs = run_matrix.build_jobs(["E1", "E3", "E5", "E7", "E8"], [0, 1], tmp_path / "runs")
    kinds = [(j.exp, j.kind) for j in jobs]
    assert kinds.count(("E3", "train")) == 4 and kinds.count(("E5", "train")) == 2
    assert [j.phase for j in jobs if j.kind == "eval"] == [1]
    assert {j.phase for j in jobs if j.kind == "train"} == {2}
    assert [j.phase for j in jobs if j.kind == "robustness"] == [3] and [j.phase for j in jobs if j.kind == "fairness"] == [4]
    t = next(j for j in jobs if j.name == "b" and j.seed == 1)
    assert t.run_dir == tmp_path / "runs" / "E3" / "b" / "seed1"
    assert "--eval" in t.cmd and "--run-dir" in t.cmd


def test_quick_and_glob(cfg_tree, tmp_path):
    jobs = run_matrix.build_jobs([], [0], tmp_path, quick=True, globs=[str(cfg_tree / "E3" / "*.yaml")])
    assert len(jobs) == 2
    assert "--num-seconds" in jobs[0].cmd and jobs[0].cmd[jobs[0].cmd.index("--total-episodes") + 1] == "2"


def test_dry_run_prints_and_runs_nothing(cfg_tree, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(run_matrix, "subprocess_runner", lambda *a: pytest.fail("must not run"))
    (tmp_path / "runs" / "E3" / "a" / "seed0").mkdir(parents=True)
    (tmp_path / "runs" / "E3" / "a" / "seed0" / "DONE").write_text("{}")
    rc = run_matrix.main(["--exp", "E3", "--seeds", "0", "--dry-run", "--runs-dir", str(tmp_path / "runs")])
    out = capsys.readouterr().out
    assert rc == 0 and "skip (DONE)" in out and "E3/b seed=0" in out and "1 would run" in out
    assert not (tmp_path / "runs" / "manifest.csv").exists()


@pytest.mark.parametrize("n_jobs", [1, 3])
def test_run_skips_done_writes_manifest_and_survives_failures(cfg_tree, tmp_path, n_jobs):
    runs = tmp_path / "runs"
    jobs = run_matrix.build_jobs(["E3"], [0, 1], runs)
    run_matrix.attach_upstream(jobs)
    ran = []

    def runner(job, env):
        ran.append((job.name, job.seed))
        return 1 if (job.name, job.seed) == ("b", 1) else 0

    man = run_matrix.Manifest(runs / "manifest.csv")
    c1 = run_matrix.run_jobs(jobs, n_jobs=n_jobs, manifest=man, runner=runner)
    assert c1 == {"done": 3, "skipped": 0, "failed": 1}
    c2 = run_matrix.run_jobs(jobs, n_jobs=n_jobs, manifest=man, runner=runner)  # resume: only the failed one runs
    assert c2 == {"done": 0, "skipped": 3, "failed": 1}
    rows = pd.read_csv(runs / "manifest.csv")
    assert len(rows) == 4 and sorted(rows["status"]) == ["failed", "skipped", "skipped", "skipped"]
    c3 = run_matrix.run_jobs(jobs, n_jobs=1, manifest=man, force=True, runner=lambda j, e: 0)
    assert c3["done"] == 4


def test_derived_jobs_rerun_when_upstream_newer(cfg_tree, tmp_path):
    import os
    runs = tmp_path / "runs"
    jobs = run_matrix.build_jobs(["E3", "E7"], [0], runs)
    run_matrix.attach_upstream(jobs)
    rob = next(j for j in jobs if j.kind == "robustness")
    tr = next(j for j in jobs if j.kind == "train")
    for j, t in ((tr, 1000), (rob, 2000)):
        j.run_dir.mkdir(parents=True)
        j.done_path.write_text("{}")
        os.utime(j.done_path, (t, t))
    assert rob.is_done()
    os.utime(tr.done_path, (3000, 3000))  # a training run finished after E7 was computed
    assert not rob.is_done()


# ---------------------------------------------------------------- robustness
def test_variant_parsing():
    assert robustness.parse_variant("pico_incident", "reforma") == ("reforma_pico", True)
    assert robustness.parse_variant("pico_x13", "cruce") == ("cruce_pico_x13", False)


def test_select_best_run(tmp_path):
    for s, w in ((0, 30.0), (1, 12.0), (2, 20.0)):
        d = tmp_path / "E3" / "dqn" / f"seed{s}"
        d.mkdir(parents=True)
        (d / "DONE").write_text("{}")
        pd.DataFrame({"mean_waiting_time": [w, w]}).to_csv(d / "eval.csv", index=False)
    assert robustness.select_run({"from": "E3/dqn/seed*", "select": "best"}, tmp_path).name == "seed1"
    assert robustness.select_run({"from": "E9/*"}, tmp_path) is None
    assert robustness.select_run({"run_dir": "x/y"}, tmp_path) == Path("x/y")


def test_run_robustness_with_fakes(tmp_path, fake_algo, monkeypatch):
    seen = []
    mod = sys.modules["experiments.evaluate"]
    orig = mod.evaluate

    def ev(policy, scenario, seeds, **kw):
        seen.append((scenario, kw.get("incident")))
        return orig(policy, scenario, seeds, **kw)

    mod.evaluate = ev
    monkeypatch.setattr(registry, "load_policy", lambda algo, run_dir=None, cfg=None: (algo, run_dir))
    d = tmp_path / "E3" / "x" / "seed0"
    d.mkdir(parents=True)
    (d / "DONE").write_text("{}")
    cfg = {"variants": ["pico", "mediodia", "pico_incident"], "baselines": ["fixed"], "eval_seeds": 2,
           "incident": {"edge": "e1", "start": 10, "end": 20},
           "learned": [{"label": "dummy_best", "algo": "dummy", "base": "cruce", "from": "E3/x/seed*"}]}
    df = robustness.run_robustness(cfg, tmp_path, tmp_path / "E7" / "robustness.csv")
    assert set(df["method"]) == {"dummy_best", "fixed"}
    assert set(df["variant"]) == {"pico", "mediodia", "pico_incident"}
    assert ("cruce_mediodia", None) in seen
    assert ("cruce_pico", {"edge": "e1", "start": 10, "end": 20}) in seen
    assert (tmp_path / "E7" / "robustness.csv").exists()


def test_collect_fairness(tmp_path):
    d = tmp_path / "E1" / "baselines"
    d.mkdir(parents=True)
    row = {"method": "fixed", "scenario": "cruce_pico", "seed": 1000, "p95_wait_by_approach": '{"N": 40, "E": 90}', "max_wait_cross_streets": 120}
    pd.DataFrame([row, {**row, "scenario": "toy_single"}]).to_csv(d / "eval.csv", index=False)
    cfg = {"sources": ["E1/*/eval*.csv", "E9/*.csv"], "scenarios": ["cruce_pico"]}
    df = robustness.collect_fairness(cfg, tmp_path, tmp_path / "E8" / "fairness.csv")
    assert len(df) == 1 and (tmp_path / "E8" / "fairness.csv").exists()


def test_default_incident_edge_on_grid():
    from env.scenarios import get_scenario

    edge = robustness.default_incident_edge(get_scenario("toy_grid2x2").net_file)
    inc = robustness.resolve_incident(None, "toy_grid2x2")
    assert edge and inc["edge"] == edge and inc["start"] < inc["end"]
