"""Línea base 2: semáforo actuado de SUMO (extiende el verde mientras detecta autos)."""
from __future__ import annotations

from agents.base import Policy
from baselines.programs import activate_program, ensure_actuated
from env.scenarios import Scenario


class ActuatedPolicy(Policy):
    name = "actuated"
    fixed_ts = True
    program = "actuated"

    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self.min_green = cfg.get("min_green")
        self.max_green = cfg.get("max_green")

    def prepare_scenario(self, sc: Scenario) -> Scenario:
        """Si el escenario no trae `actuated_additional` (toy), se genera desde la red."""
        return ensure_actuated(sc, self.min_green, self.max_green)

    def reset(self, sumo_env):
        super().reset(sumo_env)
        self.missing = activate_program(sumo_env, self.program)
        if self.missing:
            raise RuntimeError(f"programa 'actuated' ausente en {self.missing}: usa prepare_scenario()")


def make_policy(cfg: dict | None = None) -> ActuatedPolicy:
    return ActuatedPolicy(cfg)
