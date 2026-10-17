"""Línea base 3: max-pressure (Varaiya, 2013), versión justa para el corredor calibrado.

Para cada semáforo se elige la fase de verde con mayor presión:
    presión(fase) = sum_{carriles de entrada que sirve} ocup(i)  -  sum_{carriles de salida que alimenta} ocup(o)
con CADA carril contado una sola vez y ocup = autos en el carril / capacidad del carril (autos que caben).

Por qué así (comparado en reforma_pico y cruce_pico, 3 semillas, docs/ajuste_aprendizaje.md):
- La versión anterior sumaba por enlace controlado (i -> o). Una fase de Reforma (~8 enlaces) vencía siempre
  a una transversal (~5) con la misma cola por carril: las transversales se morían de hambre y el corredor
  se trababa (9.7 teletransportes por episodio y 10.7 % de backlog en reforma_pico).
- Autos (no solo detenidos) porque los detenidos llegan tarde: un pelotón que se acerca ya es demanda, y con
  solo `halting` la política reaccionó tarde (27 % de backlog).
- Ocupación (no autos crudos) porque los enlaces miden de 86 a 507 m: con autos crudos un enlace corto
  lleno (derrame hacia el cruce) pesa lo mismo que uno largo casi vacío.
- `max_green` (que sumo-rl no impone): tras `max_green` s en verde se pasa a la mejor fase que tenga autos
  esperando, así ninguna aproximación espera más de un ciclo acotado.
sumo-rl respeta min_green y pone el amarillo; aquí solo se decide la próxima fase.
"""
from __future__ import annotations

from agents.base import Policy

MIN_GAP = 2.5  # m, igual que sumo-rl (TrafficSignal.MIN_GAP) para estimar la capacidad de un carril


class MaxPressurePolicy(Policy):
    name = "max_pressure"

    def __init__(self, cfg: dict | None = None):
        pass

    def reset(self, sumo_env):
        super().reset(sumo_env)
        # (carriles de entrada, carriles de salida) sin repetir que abre cada fase de verde ('G'/'g').
        self.lanes: dict[str, list[tuple[list[str], list[str]]]] = {}
        for ts_id, ts in sumo_env.traffic_signals.items():
            links = ts.sumo.trafficlight.getControlledLinks(ts_id)  # un item por índice de señal
            self.lanes[ts_id] = []
            for ph in ts.green_phases:
                mv = [(lk[0], lk[1]) for j, group in enumerate(links) for lk in group if ph.state[j] in "Gg"]
                self.lanes[ts_id].append((list(dict.fromkeys(i for i, _ in mv)), list(dict.fromkeys(o for _, o in mv))))

    def _occupancy(self, lane_id: str) -> float:
        lane = self.sumo_env.sumo.lane
        n = lane.getLastStepVehicleNumber(lane_id)
        return n * (MIN_GAP + lane.getLastStepLength(lane_id)) / lane.getLength(lane_id) if n else 0.0

    def pressures(self, ts_id: str) -> list[float]:
        return [
            sum(map(self._occupancy, ins)) - sum(map(self._occupancy, outs)) for ins, outs in self.lanes[ts_id]
        ]

    def has_demand(self, ts_id: str) -> list[bool]:
        """¿Hay autos en los carriles de entrada de cada fase?"""
        lane = self.sumo_env.sumo.lane
        return [any(lane.getLastStepVehicleNumber(i) for i in ins) for ins, _ in self.lanes[ts_id]]

    def act(self, obs):
        actions = {}
        for ts_id in obs:
            ts = self.sumo_env.traffic_signals[ts_id]
            p, cur = self.pressures(ts_id), ts.green_phase
            # En empate se queda en la fase actual (evita cambios y amarillos innecesarios).
            best = cur if p[cur] >= max(p) else max(range(len(p)), key=p.__getitem__)
            # max_green: el reloj de sumo-rl cuenta desde que empieza el amarillo que precede al verde.
            if ts.time_since_last_phase_change - ts.yellow_time >= ts.max_green:
                demand = self.has_demand(ts_id)
                others = [k for k in range(len(p)) if k != cur and demand[k]]
                if others:
                    best = max(others, key=p.__getitem__)
            actions[ts_id] = best
        return actions


def make_policy(cfg: dict | None = None) -> MaxPressurePolicy:
    return MaxPressurePolicy(cfg)
