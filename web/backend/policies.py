"""Politicas que puede usar la demo: lista de lo disponible y carga con respaldos seguros."""
from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path

import yaml

from agents.base import Policy
from agents.registry import ALGOS, BASELINES, load_policy
from env.scenarios import SCENARIOS, Scenario, get_scenario

log = logging.getLogger("web.policies")

REPO_ROOT = Path(__file__).resolve().parents[2]
# Los modelos se buscan en runs/ (se puede apuntar a otra carpeta con WEB_RUNS_DIR, p. ej. el runs/ de otro worktree).
RUNS_DIR = Path(os.environ.get("WEB_RUNS_DIR") or REPO_ROOT / "runs").resolve()
MULTIAGENT = {"idqn", "qmix", "mappo", "comm"}  # reforma_*; el resto de los algoritmos entrenados es de 1 agente (cruce_*)
MODEL_PATTERNS = ("model.pt", "model.zip", "qtable.npz", "*.pt", "*.zip", "*.npz")
LABELS = {"fixed": "Tiempo fijo", "actuated": "Actuado", "max_pressure": "Max-pressure"}
DEFAULT_RL = {"algo": "max_pressure", "run": None}


class FixedProgram(Policy):
    """El lado "fijo" de la demo: SUMO ejecuta el programa de tiempo fijo del escenario."""

    name = "fixed"
    fixed_ts = True
    program = "fixed"


class CyclicPolicy(Policy):
    """Respaldo sencillo si max-pressure aun no existe: rota las fases verdes en orden."""

    name = "cyclic"

    def __init__(self, hold_decisions: int = 3):
        self.hold = hold_decisions
        self._count: dict[str, int] = {}

    def reset(self, sumo_env):
        super().reset(sumo_env)
        self._count = {}

    def act(self, obs):
        ts = self.sumo_env.traffic_signals
        out = {}
        for a in obs:
            self._count[a] = self._count.get(a, 0) + 1
            cur = ts[a].green_phase
            out[a] = (cur + 1) % ts[a].num_green_phases if self._count[a] % self.hold == 0 else cur
        return out


def _module_available(algo: str) -> bool:
    try:
        return importlib.util.find_spec(ALGOS[algo]) is not None
    except (ImportError, ValueError, KeyError):
        return False


def _find_model(run: Path) -> Path | None:
    for pat in MODEL_PATTERNS:
        hits = sorted(run.glob(pat))
        if hits:
            return hits[0]
    return None


def _read_cfg(run: Path) -> dict:
    f = run / "config.yaml"
    if not f.exists():
        return {}
    try:
        return yaml.safe_load(f.read_text()) or {}
    except Exception:
        return {}


def is_compatible(algo: str, run_scenario: str | None, target: str | Scenario | None) -> bool:
    """Una politica entrenada solo sirve en la red donde se entreno (mismas dimensiones de observacion):
    MARL en reforma_*, 1 agente en cruce_*."""
    if target is None or algo in BASELINES:
        return True
    tgt = get_scenario(target) if not isinstance(target, Scenario) else target
    if run_scenario in SCENARIOS:
        return get_scenario(run_scenario).net_file == tgt.net_file
    return (algo in MULTIAGENT) == tgt.name.startswith("reforma")


def list_policies(scenario: str | None = None) -> list[dict]:
    """Baselines + toda corrida `runs/**/seed<k>/` con modelo guardado.

    Cada elemento lleva `compatible` (True si sirve para `scenario`; sin escenario, siempre True).
    """
    out = [
        {
            "id": a,
            "algo": a,
            "run": None,
            "label": LABELS[a],
            "kind": "baseline",
            "scenario": None,
            "multiagent": False,
            "compatible": True,
            "available": _module_available(a),
        }
        for a in ("max_pressure", "actuated", "fixed")
    ]
    if RUNS_DIR.is_dir():
        for run in sorted(RUNS_DIR.rglob("seed*")):
            if not run.is_dir() or not (run / "config.yaml").exists():
                continue
            cfg = _read_cfg(run)
            algo = cfg.get("algo")
            model = _find_model(run)
            if algo not in ALGOS or algo in BASELINES or model is None:
                continue
            rel = run.relative_to(RUNS_DIR).as_posix()
            exp = run.parent.parent.name
            out.append(
                {
                    "id": rel,
                    "algo": algo,
                    "run": rel,
                    "label": f"{cfg.get('name', algo)} · {cfg.get('exp', exp)} (seed {cfg.get('seed', run.name[4:])})",
                    "kind": "trained",
                    "scenario": cfg.get("scenario"),
                    "multiagent": algo in MULTIAGENT,
                    "compatible": is_compatible(algo, cfg.get("scenario"), scenario),
                    "available": _module_available(algo),
                    "model": model.name,
                }
            )
    return out


def resolve_run(run: str) -> Path:
    """Convierte `run` (relativo a runs/, al repo o absoluto) en un directorio DENTRO de runs/.

    Se restringe a runs/ porque los checkpoints de PyTorch son pickles: no se debe poder
    cargar cualquier archivo del disco desde un mensaje del WebSocket.
    """
    for base in (RUNS_DIR, REPO_ROOT, Path("/")):
        cand = (base / run).resolve() if base != Path("/") else Path(run).resolve()
        if cand.is_dir() and cand.is_relative_to(RUNS_DIR.resolve()):
            return cand
    raise ValueError(f"corrida no encontrada dentro de runs/: {run}")


def load_rl_policy(spec: dict | None, scenario: str | Scenario | None = None) -> tuple[Policy, dict]:
    """Devuelve (politica, info). Sin modelo o con un baseline que aun no existe, usa respaldos.

    `spec` = {"algo": ..., "run": ...}. Un `spec` explicito invalido lanza ValueError (el comando
    `reset` lo informa al cliente); el defecto nunca falla.
    """
    spec = dict(spec or DEFAULT_RL)
    algo = spec.get("algo") or "max_pressure"
    run = spec.get("run")
    if algo not in ALGOS:
        raise ValueError(f"algoritmo desconocido: {algo}")
    explicit = bool(spec.get("algo")) and not (algo == "max_pressure" and not run)
    try:
        if algo in BASELINES:
            pol = load_policy(algo, None, None)
        else:
            if not run:
                raise ValueError(f"{algo} necesita una corrida entrenada (campo 'run')")
            run_dir = resolve_run(run)
            run_sc = _read_cfg(run_dir).get("scenario")
            if not is_compatible(algo, run_sc, scenario):
                tgt = scenario.name if isinstance(scenario, Scenario) else scenario
                raise ValueError(f"{run} se entreno en {run_sc} y no sirve para {tgt} (otra red u otro tipo de agente)")
            from experiments.common import policy_dir

            pol = load_policy(algo, str(policy_dir(run_dir)))  # best/ (validación) si existe
        info = {"algo": algo, "run": run, "label": LABELS.get(algo, algo), "warning": None}
        if run:
            info["label"] = f"{algo} ({run})"
        return pol, info
    except (ImportError, ModuleNotFoundError) as exc:
        if explicit and algo not in BASELINES:
            raise ValueError(f"no se pudo cargar {algo}: {exc}") from exc
        log.warning("%s no importable (%s); respaldo ciclico", algo, exc)
        return CyclicPolicy(), {
            "algo": "cyclic",
            "run": None,
            "label": "Ciclico (respaldo)",
            "warning": f"{algo} no esta disponible todavia; se usa una politica ciclica",
        }
