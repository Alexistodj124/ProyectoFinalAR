"""Qué métodos y escenarios entran en las figuras y tablas de cada experimento (E1 a E6).

`methods` son los métodos entrenados del experimento (más `extra_methods`, que vienen de otro experimento y se usan de
referencia, p. ej. MAPPO en E6); `baselines` se agregan siempre que existan. `train_scenario` es el escenario
en que se entrena y se valida (las líneas base de las curvas de validación salen de ahí).
"""
from __future__ import annotations

import pandas as pd

from analysis.style import BASELINES

CRUCE = ["cruce_pico", "cruce_mediodia"]
REFORMA = ["reforma_pico", "reforma_mediodia", "reforma_pico_x13"]

SPECS = {
    "E1": dict(title="E1: líneas base (sin entrenamiento)", methods=[], baselines=True,
               scenarios=["cruce_pico", "cruce_mediodia", "cruce_pico_x13", "reforma_pico", "reforma_mediodia",
                          "reforma_pico_x13"], train_scenario=None),
    "E2": dict(title="E2: Q-Learning y Dyna-Q (cuánto ayuda planificar)",
               methods=["q_learning", "dyna_q_n5", "dyna_q_n10", "dyna_q_n50"], baselines=True,
               scenarios=CRUCE, train_scenario="cruce_pico"),
    "E3": dict(title="E3: ablación de DQN",
               methods=["dqn_vanilla", "dqn_double", "dqn_double_dueling", "dqn_double_dueling_per"], baselines=True,
               scenarios=CRUCE, train_scenario="cruce_pico"),
    "E4": dict(title="E4: DQN (mejor variante) contra PPO",
               methods=["dqn_best", "ppo"], baselines=True, scenarios=CRUCE, train_scenario="cruce_pico"),
    "E5": dict(title="E5: IDQN, QMIX y MAPPO en el corredor",
               methods=["idqn", "qmix", "mappo"], baselines=True, scenarios=REFORMA, train_scenario="reforma_pico"),
    "E6": dict(title="E6: efecto de la comunicación",
               methods=["idqn", "idqn_neighbor_obs", "comm", "mappo"], extra_methods=["idqn", "mappo"],
               baselines=True, scenarios=REFORMA, train_scenario="reforma_pico"),
    "E8": dict(title="E8: equidad con las calles transversales", methods=[], baselines=False, scenarios=None,
               train_scenario="reforma_pico"),
}


def spec(exp: str) -> dict:
    s = dict(SPECS.get(exp.upper(), {}))
    s.setdefault("methods", [])
    s.setdefault("extra_methods", [])
    s.setdefault("baselines", True)
    s.setdefault("scenarios", None)
    s.setdefault("train_scenario", None)
    s.setdefault("title", exp.upper())
    return s


def exp_frame(master: pd.DataFrame, exp: str) -> pd.DataFrame:
    """Filas de `master` que entran en las figuras/tablas de `exp`: sus corridas, los métodos de referencia de otro
    experimento (`extra_methods`) y las líneas base. Se queda con los escenarios de la especificación."""
    exp = exp.upper()
    if master.empty:
        return master
    s = spec(exp)
    own = master[master["exp"] == exp]
    if own.empty and exp != "E1":  # sin corridas propias no hay experimento (las líneas base solas no lo son)
        return own
    parts = [own]
    if exp == "E1":  # líneas base evaluadas en E1 y, para los escenarios que E1 no cubre, las de E7
        parts.append(master[master["method"].isin(BASELINES) & (master["exp"] == "E7")])
    else:
        if s["extra_methods"]:
            parts.append(master[master["method"].isin(s["extra_methods"]) & (master["exp"] != exp)])
        if s["baselines"]:
            parts.append(master[master["method"].isin(BASELINES) & (master["exp"] != exp)])
    df = pd.concat(parts, ignore_index=True).drop_duplicates(
        subset=[c for c in ("method", "scenario", "train_seed", "seed") if c in master], keep="first")
    if s["scenarios"] and exp in SPECS:
        df = df[df["scenario"].isin(s["scenarios"])]
    return df


def scenario_order(df: pd.DataFrame, exp: str) -> list[str]:
    s = spec(exp)
    present = list(dict.fromkeys(df["scenario"]))
    if s["scenarios"] and exp.upper() in SPECS:
        return [x for x in s["scenarios"] if x in present]
    return present
