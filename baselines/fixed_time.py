"""Línea base 1: tiempo fijo. SUMO corre el programa estático (el ciclo medido en campo)."""
from __future__ import annotations

from agents.base import Policy
from baselines.programs import activate_program
from env.scenarios import Scenario


class FixedTimePolicy(Policy):
    name = "fixed"
    fixed_ts = True  # sumo-rl ignora las acciones y deja correr el programa de SUMO
    program = "fixed"

    def __init__(self, cfg: dict | None = None):
        self.program = (cfg or {}).get("program", "fixed")

    def prepare_scenario(self, sc: Scenario) -> Scenario:
        # Reforma: fixed_additional lo trae la rama del entorno. Toy: se usa el programa de la red.
        return sc

    def reset(self, sumo_env):
        super().reset(sumo_env)
        # Si existe el programa "fixed" (archivo adicional) se fuerza; si no, queda el de la red.
        self.missing = activate_program(sumo_env, self.program)


def make_policy(cfg: dict | None = None) -> FixedTimePolicy:
    return FixedTimePolicy(cfg)
