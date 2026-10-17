"""Evaluación homogénea de cualquier política (líneas base y algoritmos que aprenden).

    python -m experiments.evaluate --algo fixed actuated max_pressure --scenarios toy_grid2x2
    python -m experiments.evaluate --algo dqn --run runs/E3/dqn_double/seed0 --scenarios cruce_pico
    python -m experiments.evaluate --config experiments/configs/E1/baselines.yaml

Una fila por (método, escenario, semilla) con las columnas de docs/ARCHITECTURE.md §7.
"""
from __future__ import annotations

import os
import sys

if __name__ == "__main__" and "--no-libsumo" not in sys.argv:
    # Evaluar es secuencial (una simulación por proceso): libsumo es mucho más rápido que TraCI.
    # Debe fijarse antes de importar sumo_rl.
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")

import argparse
import tempfile
from pathlib import Path

import pandas as pd
import yaml

from env.reforma_env import get_sumo_env, make_parallel_env
from env.scenarios import EVAL_SEEDS, Scenario, get_scenario
from experiments.common import REPO_ROOT
from experiments.metrics import EpisodeProbe, ci95, episode_metrics, parse_tripinfo

COLUMNS = [
    "method", "scenario", "seed", "mean_waiting_time", "mean_travel_time", "mean_queue", "max_queue",
    "throughput_veh_h", "mean_stops", "p95_wait_by_approach", "max_wait_cross_streets", "co2_kg", "arrived",
    "teleported", "loaded", "inserted", "backlog_pct", "mean_depart_delay", "total_delay",
]  # fmt: skip
BASELINES_ALL = ["fixed", "actuated", "max_pressure"]  # E1
METRICS = [c for c in COLUMNS if c not in ("method", "scenario", "seed", "p95_wait_by_approach")]


def run_episode(policy, sc: Scenario, seed: int, num_seconds: int, incident: dict | None, trip_path: str) -> dict:
    """Un episodio de evaluación con la semilla de demanda `seed`; devuelve las columnas de métricas."""
    env = make_parallel_env(
        sc,
        seed,
        num_seconds=num_seconds,
        fixed_ts=policy.fixed_ts,
        program=policy.program,
        tripinfo_path=trip_path,
        emissions=True,
        incident=incident,
    )
    probe = EpisodeProbe()
    try:
        obs, _ = env.reset(seed=seed)
        sumo_env = get_sumo_env(env)
        policy.reset(sumo_env)
        probe.attach(sumo_env)
        route_file = getattr(sumo_env, "_route", None)
        done = False
        while not done:
            # fixed_ts: sumo-rl ignora las acciones, pero el wrapper paralelo exige una por agente.
            actions = {a: 0 for a in env.agents} if policy.fixed_ts else policy.act(obs)
            obs, _, _, truncated, _ = env.step(actions)
            probe.sample()
            done = all(truncated.values()) or not env.agents
    finally:
        env.close()  # SUMO escribe el tripinfo (con los vehículos sin terminar) al cerrar
    # `_route` es el .rou.xml de ESTE episodio (el wrapper de la demanda lo regenera en reset(seed=...)).
    return episode_metrics(parse_tripinfo(trip_path), probe, sc.net_file, num_seconds, route_file)


def evaluate(
    policy,
    scenario: str | Scenario,
    seeds=EVAL_SEEDS,
    *,
    num_seconds: int | None = None,
    incident: dict | None = None,
    out_dir: str | None = None,
    method: str | None = None,
    keep_tripinfo: bool = True,
) -> pd.DataFrame:
    """Evalúa `policy` en `scenario` con cada semilla de `seeds`. Devuelve un DataFrame con COLUMNS.

    Si `out_dir` existe se guarda ahí eval_<método>_<escenario>.csv y, con `keep_tripinfo`, el tripinfo de
    cada episodio (tripinfo/, unos MB por episodio en reforma_*).
    """
    sc = get_scenario(scenario)
    if hasattr(policy, "prepare_scenario"):  # p. ej. el actuado genera su programa si falta
        sc = policy.prepare_scenario(sc)
    method = method or policy.name
    n_sec = num_seconds or sc.num_seconds
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        trip_dir = Path(out_dir) / "tripinfo" if (out_dir and keep_tripinfo) else Path(tmp)
        trip_dir.mkdir(parents=True, exist_ok=True)
        for seed in seeds:
            trip = trip_dir / f"{method}_{sc.name}_{seed}.xml"
            m = run_episode(policy, sc, int(seed), n_sec, incident, str(trip))
            rows.append({"method": method, "scenario": sc.name, "seed": int(seed), **m})
    df = pd.DataFrame(rows, columns=COLUMNS)
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        df.to_csv(Path(out_dir) / f"eval_{method}_{sc.name}.csv", index=False)
    return df


def summarize(df: pd.DataFrame, by=("method", "scenario")) -> pd.DataFrame:
    """Media e IC95 (t de Student) de cada métrica por grupo: columnas <métrica>_mean y <métrica>_ci95."""
    by = list(by)
    out = []
    for key, g in df.groupby(by, sort=False):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(by, key))
        row["n"] = len(g)
        for m in METRICS:
            if m in g:
                row[f"{m}_mean"] = float(g[m].mean())
                row[f"{m}_ci95"] = ci95(g[m].to_numpy())
        out.append(row)
    return pd.DataFrame(out)


def format_summary(
    s: pd.DataFrame,
    metrics=("mean_waiting_time", "total_delay", "backlog_pct", "mean_travel_time", "mean_queue", "throughput_veh_h"),
):
    """Tabla legible 'media ± IC95' para imprimir."""
    t = s[[c for c in s.columns if not c.endswith(("_mean", "_ci95"))]].copy()
    for m in metrics:
        if f"{m}_mean" in s:
            t[m] = [f"{a:.1f} ± {b:.1f}" for a, b in zip(s[f"{m}_mean"], s[f"{m}_ci95"])]
    return t


# --------------------------------------------------------------------------------------------- CLI
def resolve_run(run: str | None) -> str | None:
    """Si `run` trae best/ (el checkpoint elegido con las semillas de validación), se carga de ahí."""
    if run and (Path(run) / "best").is_dir():
        return str(Path(run) / "best")
    return run


def _load(algo: str, run: str | None):
    from agents.registry import BASELINES, load_policy

    name = algo
    if algo not in BASELINES and run:
        cfg_path = Path(run) / "config.yaml"  # el config.yaml está en el run_dir, no en best/
        if cfg_path.exists():
            name = yaml.safe_load(cfg_path.read_text()).get("name", algo)  # p. ej. dqn_double
        load_from = resolve_run(run)
        print(f"[evaluate] {name}: cargando de {load_from}" + (" (best/)" if load_from != run else " (último episodio)"))
        return load_policy(algo, load_from), name
    return load_policy(algo, run), name


def run_methods(
    methods: list[dict], scenarios: list[str], seeds, num_seconds, incident=None, out_dir=None, keep_tripinfo=False
):
    """methods: [{"algo", "run" (opcional), "name" (opcional)}]. Devuelve el DataFrame de todos."""
    dfs = []
    for m in methods:
        policy, default_name = _load(m["algo"], m.get("run"))
        label = m.get("name") or default_name
        for scn in scenarios:
            print(f"[evaluate] {label} @ {scn} ({len(list(seeds))} semillas)", flush=True)
            dfs.append(
                evaluate(
                    policy, scn, seeds, num_seconds=num_seconds, incident=incident, out_dir=out_dir, method=label,
                    keep_tripinfo=keep_tripinfo,
                )
            )
    return pd.concat(dfs, ignore_index=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="YAML con methods x scenarios (experiments/configs/E1/baselines.yaml)")
    ap.add_argument("--algo", nargs="+", help="fixed | actuated | max_pressure | algoritmo que aprende")
    ap.add_argument("--run", help="run_dir del modelo entrenado (algoritmos que aprenden)")
    ap.add_argument("--scenarios", nargs="+")
    ap.add_argument("--seeds", nargs="+", type=int, help="por defecto EVAL_SEEDS (1000..1009)")
    ap.add_argument("--num-seconds", type=int)
    ap.add_argument("--out", help="CSV de salida (el resumen va en <out>_summary.csv)")
    ap.add_argument("--out-dir", help="carpeta de salida: eval.csv (lo usa run_matrix) y eval_<método>_<escenario>.csv")
    ap.add_argument("--keep-tripinfo", action="store_true", help="con --out-dir, guarda también el tripinfo.xml de cada episodio")
    ap.add_argument("--no-libsumo", action="store_true", help="usa TraCI en vez de libsumo")
    a = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(a.config).read_text()) if a.config else {}
    methods = [{"algo": m} if isinstance(m, str) else dict(m) for m in cfg.get("methods", [])]
    if a.algo:
        methods = [{"algo": x, "run": a.run} for x in a.algo]
    scenarios = a.scenarios or cfg.get("scenarios")
    seeds = a.seeds or (cfg["seeds"] if isinstance(cfg.get("seeds"), list) else EVAL_SEEDS)
    num_seconds = a.num_seconds or cfg.get("num_seconds")
    out = a.out or (str(Path(a.out_dir) / "eval.csv") if a.out_dir else None) or cfg.get("out")
    if not methods or not scenarios:
        ap.error("hace falta --algo/--scenarios o --config")

    df = run_methods(
        methods, scenarios, seeds, num_seconds, incident=cfg.get("incident"), out_dir=a.out_dir,
        keep_tripinfo=a.keep_tripinfo,
    )
    summ = summarize(df)
    print(format_summary(summ).to_string(index=False))
    if out:
        out = Path(out) if Path(out).is_absolute() else REPO_ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        summ.to_csv(out.with_name(out.stem + "_summary.csv"), index=False)
        print(f"[evaluate] guardado {out}")


if __name__ == "__main__":
    main()
