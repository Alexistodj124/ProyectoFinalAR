"""Métricas de evaluación (PLAN §8.1): tripinfo de SUMO + muestreo de colas con TraCI.

Convenciones (iguales para todos los métodos, así la comparación es justa):
- Los promedios por vehículo usan TODOS los vehículos insertados: los que llegaron y los que siguen en
  la red al terminar (SUMO los escribe con `--tripinfo-output.write-unfinished`, con su espera y duración
  acumuladas). Ignorar los atascados haría ver mejor a las políticas que congestionan la red.
- Cola = vehículos detenidos (v < 0.1 m/s) en todos los carriles de entrada de todos los semáforos.
- Aproximación = arista donde el vehículo entra a la red (`departLane` del tripinfo).
- `mean_waiting_time` solo promedia sobre los INSERTADOS, así que un método puede "ganar" dejando autos
  fuera de la red (docs/ajuste_aprendizaje.md §3). Por eso cada fila trae también `loaded`, `inserted`,
  `backlog_pct`, `mean_depart_delay` y `total_delay`, que cuenta a todos los vehículos de la demanda.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

CROSS_NAME_KEY = "reforma"  # una calle es "transversal" si el nombre de su arista no contiene esto


def ci95(values) -> float:
    """Semiancho del IC95 de la media con t de Student: t_{0.975, n-1} * s / sqrt(n). NaN si n < 2."""
    x = np.asarray(values, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return float("nan")
    return float(stats.t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x)))


# ---------------------------------------------------------------------------------------- tripinfo
def parse_tripinfo(path: str) -> pd.DataFrame:
    """Una fila por vehículo: id, depart, approach, waitingTime, duration, departDelay, stops, arrival, finished, co2_mg."""
    rows = []
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag != "tripinfo":
            continue
        em = el.find("emissions")
        arrival = float(el.get("arrival", -1))
        rows.append(
            {
                "id": el.get("id"),
                "depart": float(el.get("depart")),
                "approach": el.get("departLane", "").rsplit("_", 1)[0],
                "waitingTime": float(el.get("waitingTime", 0)),
                "duration": float(el.get("duration", 0)),
                "departDelay": max(0.0, float(el.get("departDelay", 0))),  # SUMO escribe -1 si no aplica
                "stops": float(el.get("waitingCount", 0)),
                "arrival": arrival,
                "finished": arrival >= 0,
                "co2_mg": float(em.get("CO2_abs", 0)) if em is not None else 0.0,
            }
        )
        el.clear()
    return pd.DataFrame(
        rows,
        columns=["id", "depart", "approach", "waitingTime", "duration", "departDelay", "stops", "arrival", "finished",
                 "co2_mg"],
    )


@lru_cache(maxsize=None)
def approach_info(net_file: str) -> dict:
    """{edge: {"name", "axis"}} de las aristas normales. axis = "h"/"v" según su dirección."""
    nodes, edges = {}, {}
    for _, el in ET.iterparse(net_file, events=("end",)):
        if el.tag == "junction":
            nodes[el.get("id")] = (float(el.get("x")), float(el.get("y")))
        elif el.tag == "edge" and el.get("function", "normal") == "normal":
            edges[el.get("id")] = (el.get("from"), el.get("to"), el.get("name", ""))
        if el.tag in ("junction", "edge"):
            el.clear()
    info = {}
    for eid, (a, b, name) in edges.items():
        (x0, y0), (x1, y1) = nodes[a], nodes[b]
        info[eid] = {"name": name, "axis": "h" if abs(x1 - x0) >= abs(y1 - y0) else "v"}
    return info


def cross_approaches(net_file: str, trips: pd.DataFrame) -> set[str]:
    """Aproximaciones que son calles transversales.

    Con la red de Reforma: aristas cuyo `name` no contiene "Reforma". Si ninguna arista de la red tiene
    ese nombre (redes toy), se toma como transversal el eje (horizontal/vertical) con menos flujo total.
    """
    info = approach_info(net_file)
    used = set(trips["approach"].unique()) if len(trips) else set()
    if any(CROSS_NAME_KEY in v["name"].lower() for v in info.values()):
        return {e for e in used if CROSS_NAME_KEY not in info.get(e, {"name": ""})["name"].lower()}
    flow = {"h": 0, "v": 0}
    for e, c in trips["approach"].value_counts().items():
        flow[info.get(e, {"axis": "h"})["axis"]] += int(c)
    if min(flow.values()) == max(flow.values()) == 0 or not all(flow.values()):
        # un solo eje con tráfico: no hay calle transversal que medir
        return set()
    cross_axis = min(flow, key=flow.get)
    return {e for e in used if info.get(e, {}).get("axis") == cross_axis}


# ------------------------------------------------------------------------------ demanda no insertada
@lru_cache(maxsize=16)
def _scheduled_departures(route_file: str, mtime_ns: int) -> dict[str, float]:
    """{id: depart programado} de los <vehicle>/<trip> de un .rou.xml (ignora depart no numérico)."""
    out = {}
    for _, el in ET.iterparse(route_file, events=("end",)):
        if el.tag in ("vehicle", "trip") and el.get("id") is not None:
            try:
                out[el.get("id")] = float(el.get("depart"))
            except (TypeError, ValueError):
                pass
        if el.tag in ("vehicle", "trip", "flow", "route"):
            el.clear()
    return out


def scheduled_departures(route_file: str | None) -> dict[str, float]:
    """Salidas programadas de un archivo de rutas. {} si no hay archivo o solo trae <flow> (toy), porque
    entonces la demanda no se puede enumerar de antemano."""
    if not route_file or not Path(route_file).exists():
        return {}
    return _scheduled_departures(str(route_file), Path(route_file).stat().st_mtime_ns)


def demand_metrics(trips: pd.DataFrame, departs: dict[str, float], num_seconds: float) -> dict:
    """Backlog y demora total (docs/ajuste_aprendizaje.md §1).

    loaded  = vehículos del archivo de rutas con depart < num_seconds (más los insertados, por si el archivo
              no se puede enumerar: entonces loaded = inserted y no hay backlog que medir).
    total_delay = [ sum_insertados (waitingTime + departDelay) + sum_nunca_insertados (num_seconds - depart) ]
                  / loaded.
    Un vehículo que nunca entró se cuenta como si hubiera esperado fuera de la red hasta el final: no se
    puede reducir `total_delay` dejando autos afuera.
    """
    inserted_ids = set(trips["id"]) if len(trips) else set()
    due = {v: d for v, d in departs.items() if d < num_seconds}
    never = {v: d for v, d in due.items() if v not in inserted_ids}
    n_ins = len(trips)
    loaded = len(never) + n_ins
    delay_in = float((trips["waitingTime"] + trips["departDelay"]).sum()) if n_ins else 0.0
    delay_out = float(sum(num_seconds - d for d in never.values()))
    return {
        "loaded": loaded,
        "inserted": n_ins,
        "backlog_pct": 100.0 * len(never) / loaded if loaded else 0.0,
        "mean_depart_delay": float(trips["departDelay"].mean()) if n_ins else 0.0,
        "total_delay": (delay_in + delay_out) / loaded if loaded else float("nan"),
    }


# ------------------------------------------------------------------------------ muestreo durante el episodio
class EpisodeProbe:
    """Mide colas (cada paso del agente) y teletransportes (cada segundo de SUMO) durante un episodio."""

    def __init__(self):
        self.queue_samples: list[int] = []
        self.teleported = 0
        self._lanes: list[str] | None = None

    def attach(self, sumo_env) -> None:
        """Llamar después de env.reset(). Envuelve `_sumo_step` para no perder teletransportes entre pasos."""
        self.sumo_env = sumo_env
        self._lanes = sorted({ln for ts in sumo_env.traffic_signals.values() for ln in ts.lanes})
        original = sumo_env._sumo_step

        def step_and_count():
            original()
            self.teleported += sumo_env.sumo.simulation.getStartingTeleportNumber()

        sumo_env._sumo_step = step_and_count

    def sample(self) -> None:
        lane = self.sumo_env.sumo.lane
        self.queue_samples.append(sum(lane.getLastStepHaltingNumber(ln) for ln in self._lanes))


def episode_metrics(
    trips: pd.DataFrame, probe: EpisodeProbe, net_file: str, num_seconds: float, route_file: str | None = None
) -> dict:
    """Columnas métricas de una fila de evaluate() (sin method/scenario/seed).

    `route_file` es el .rou.xml del episodio; sin él (o con flujos probabilísticos) `loaded` = insertados.
    """
    q = np.asarray(probe.queue_samples, dtype=float)
    arrived = int(trips["finished"].sum()) if len(trips) else 0
    cross = cross_approaches(net_file, trips)
    p95 = {e: float(np.percentile(g["waitingTime"], 95)) for e, g in trips.groupby("approach")}
    cross_wait = trips.loc[trips["approach"].isin(cross), "waitingTime"]
    return {
        "mean_waiting_time": float(trips["waitingTime"].mean()) if len(trips) else float("nan"),
        "mean_travel_time": float(trips["duration"].mean()) if len(trips) else float("nan"),
        "mean_queue": float(q.mean()) if len(q) else float("nan"),
        "max_queue": float(q.max()) if len(q) else float("nan"),
        "throughput_veh_h": arrived / (num_seconds / 3600.0),
        "mean_stops": float(trips["stops"].mean()) if len(trips) else float("nan"),
        "p95_wait_by_approach": json.dumps(p95, sort_keys=True),
        "max_wait_cross_streets": float(cross_wait.max()) if len(cross_wait) else 0.0,
        "co2_kg": float(trips["co2_mg"].sum()) / 1e6,
        "arrived": arrived,
        "teleported": int(probe.teleported),
        **demand_metrics(trips, scheduled_departures(route_file), num_seconds),
    }
