"""Línea base 3: max-pressure (Varaiya, 2013).

Para cada semáforo se elige la fase de verde con mayor presión:
    presión(fase) = suma sobre los movimientos (carril entrada i -> carril salida o) servidos en verde
                    de [ autos(i) - autos(o) ]
Es la política que estabiliza las colas sin conocer la demanda. sumo-rl se encarga de respetar
min_green y de poner el amarillo; aquí solo se decide la próxima fase.
"""
from __future__ import annotations

import numpy as np

from agents.base import Policy


class MaxPressurePolicy(Policy):
    name = "max_pressure"

    def __init__(self, cfg: dict | None = None):
        pass

    def reset(self, sumo_env):
        super().reset(sumo_env)
        # Movimientos (in_lane, out_lane) que abre cada fase de verde: enlaces con 'G'/'g' en su estado.
        self.movements: dict[str, list[list[tuple[str, str]]]] = {}
        for ts_id, ts in sumo_env.traffic_signals.items():
            links = ts.sumo.trafficlight.getControlledLinks(ts_id)  # un item por índice de señal
            self.movements[ts_id] = [
                [(lk[0], lk[1]) for j, group in enumerate(links) for lk in group if ph.state[j] in "Gg"]
                for ph in ts.green_phases
            ]

    def pressures(self, ts_id: str) -> list[float]:
        lane = self.sumo_env.sumo.lane
        count: dict[str, int] = {}

        def n(l: str) -> int:
            if l not in count:
                count[l] = lane.getLastStepVehicleNumber(l)
            return count[l]

        return [float(sum(n(i) - n(o) for i, o in mv)) for mv in self.movements[ts_id]]

    def act(self, obs):
        actions = {}
        for ts_id in obs:
            p = self.pressures(ts_id)
            cur = self.sumo_env.traffic_signals[ts_id].green_phase
            # En empate se queda en la fase actual (evita cambios y amarillos innecesarios).
            actions[ts_id] = cur if p[cur] >= max(p) else int(np.argmax(p))
        return actions


def make_policy(cfg: dict | None = None) -> MaxPressurePolicy:
    return MaxPressurePolicy(cfg)
