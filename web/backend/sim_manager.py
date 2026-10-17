"""SimManager: dos simulaciones SUMO en lock-step ("fijo" vs "rl") con la misma demanda.

Todo el codigo TraCI corre en UN solo hilo (el hilo de simulacion); el resto de la app
(FastAPI) solo manda comandos por una cola y recibe el estado ya serializado.

Paso de 1 s: se reproduce SumoEnvironment.step() de sumo-rl pero segundo a segundo, para
que la animacion sea fluida y la politica siga decidiendo cada `delta_time`:
    _run_steps():  while not time_to_act: _sumo_step(); ts.update()      # sumo-rl
    aqui:          cada segundo -> spawn -> _sumo_step -> ts.update; si algun ts "toca
                   actuar" se calculan observaciones, policy.act(obs) y _apply_actions.
"""
from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
from collections import deque
from concurrent.futures import Future
from pathlib import Path
from queue import Empty, Queue

import sumo_rl.environment.env as sumo_rl_env
import traci.constants as tc

from env.reforma_env import _route_for, get_sumo_env, make_parallel_env
from env.scenarios import EVAL_SEEDS, SCENARIOS, Scenario, get_scenario
from web.backend.demand_driver import RouteBook, SharedDemand, SimDemand, load_schedule, make_generator
from web.backend.geometry import read_net
from web.backend.policies import FixedProgram, load_rl_policy

log = logging.getLogger("web.sim")

TICK = 0.1  # s de pared entre iteraciones del hilo (~10 Hz)
MAX_VEHICLES = 1500  # tope de vehiculos que se envian por simulacion y por tick
MAX_STEPS_PER_TICK = 60  # si el equipo no da abasto, se pierde tiempo simulado en vez de acumular deuda
THROUGHPUT_WINDOW = 300  # s simulados para el throughput "rolling"
VEHICLE_VARS = [tc.VAR_POSITION, tc.VAR_ANGLE, tc.VAR_SPEED, tc.VAR_ACCUMULATED_WAITING_TIME]
SPEEDS = (0, 1, 5, 20)
PROFILE_NAMES = ("pico", "mediodia", "noche", "pico_x13")
BIG_HORIZON = 10**7  # sumo-rl nunca trunca: el manager decide cuando reiniciar

_EMPTY_ROUTE = Path(tempfile.gettempdir()) / "reforma_web_empty.rou.xml"


def _empty_route_file() -> str:
    if not _EMPTY_ROUTE.exists():
        _EMPTY_ROUTE.write_text("<routes/>\n")
    return str(_EMPTY_ROUTE)


class Sim:
    """Una simulacion (SumoEnvironment de sumo-rl) conducida segundo a segundo."""

    def __init__(self, key: str, scenario: Scenario, seed: int, policy, shared: SharedDemand, first: bool = False):
        if sumo_rl_env.LIBSUMO:
            raise RuntimeError("la demo web necesita TraCI por socket: quita LIBSUMO_AS_TRACI del entorno")
        self.key = key
        self.policy = policy
        self.penv = make_parallel_env(
            scenario,
            seed,
            num_seconds=BIG_HORIZON,
            fixed_ts=bool(policy.fixed_ts),
            program=policy.program if policy.fixed_ts else None,
            route_file=_empty_route_file(),  # toda la demanda entra por TraCI (SimDemand)
        )
        try:
            self.se = get_sumo_env(self.penv)
            obs = self.se.reset(seed=seed)  # directo al SumoEnvironment: evita que el wrapper regenere rutas
            self.conn = self.se.sumo
            self.demand = SimDemand(shared, first)
            self.t = int(self.se.sim_step)
            self.controlled = not self.se.fixed_ts
            self._warned = False
            if self.controlled:
                policy.reset(self.se)
                self._act(obs)
        except Exception:
            self.close()
            raise
        # metricas
        self.last_wait: dict[str, float] = {}
        self.finished_n = 0
        self.finished_wait = 0.0
        self.arrived = 0
        self._arr_hist: deque[tuple[int, int]] = deque([(self.t, 0)])
        self._cache_closed: dict[str, list[str]] = {}

    # ---- control -------------------------------------------------------------
    def _act(self, obs: dict) -> None:
        """policy.act(obs) -> set_next_phase en los semaforos que les toca (TD/control de sumo-rl)."""
        ts = self.se.traffic_signals
        try:
            actions = self.policy.act(obs)
        except Exception as exc:  # una politica rota no debe tumbar la demo
            if not self._warned:
                log.exception("policy.act fallo (%s); se mantiene la fase actual", exc)
                self._warned = True
            actions = {a: ts[a].green_phase for a in obs}
        clean = {a: min(max(int(v), 0), ts[a].num_green_phases - 1) for a, v in actions.items() if a in ts}
        self.se._apply_actions(clean)

    def step(self) -> None:
        """Avanza 1 segundo simulado."""
        se, conn = self.se, self.conn
        self.demand.spawn(conn, self.t)
        se._sumo_step()
        self.t += 1
        if self.controlled:
            tss = se.traffic_signals
            for ts in tss.values():
                ts.update()
            if any(ts.next_action_time == self.t for ts in tss.values()):
                self._act(se._compute_observations())
        # contabilidad de vehiculos
        for vid in conn.simulation.getDepartedIDList():
            try:
                conn.vehicle.subscribe(vid, VEHICLE_VARS)
            except Exception:
                pass
        arrived_ids = conn.simulation.getArrivedIDList()
        for vid in arrived_ids:
            self.finished_n += 1
            self.finished_wait += self.last_wait.pop(vid, 0.0)
        self.arrived += len(arrived_ids)
        self._arr_hist.append((self.t, self.arrived))
        while len(self._arr_hist) > 2 and self._arr_hist[1][0] <= self.t - THROUGHPUT_WINDOW:
            self._arr_hist.popleft()

    # ---- comandos ------------------------------------------------------------
    def set_incident(self, edge_id: str, on: bool) -> None:
        """Cierra (setDisallowed passenger) o restaura todos los carriles del borde."""
        n_lanes = self.conn.edge.getLaneNumber(edge_id)
        lanes = [f"{edge_id}_{i}" for i in range(n_lanes)]
        if on:
            for ln in lanes:
                if ln not in self._cache_closed:
                    self._cache_closed[ln] = list(self.conn.lane.getDisallowed(ln))
                self.conn.lane.setDisallowed(ln, sorted(set(self._cache_closed[ln]) | {"passenger"}))
            self._reroute_affected(edge_id)
        else:
            for ln in lanes:
                if ln in self._cache_closed:
                    self.conn.lane.setDisallowed(ln, self._cache_closed.pop(ln))

    def _reroute_affected(self, edge_id: str) -> None:
        """Los vehiculos cuya ruta pendiente pasa por el borde cerrado buscan otro camino (si existe)."""
        v = self.conn.vehicle
        for vid in v.getIDList():
            try:
                route = v.getRoute(vid)
                if edge_id in route[v.getRouteIndex(vid) + 1 :]:
                    v.rerouteTraveltime(vid)
            except Exception:
                continue

    def lane_disallowed(self, edge_id: str) -> dict[str, list[str]]:
        n = self.conn.edge.getLaneNumber(edge_id)
        return {f"{edge_id}_{i}": list(self.conn.lane.getDisallowed(f"{edge_id}_{i}")) for i in range(n)}

    # ---- estado --------------------------------------------------------------
    def snapshot(self) -> dict:
        res = self.conn.vehicle.getAllSubscriptionResults()
        vehicles, queue, sumw = [], 0, 0.0
        last_wait = {}
        for vid, r in res.items():
            (x, y), ang, sp, w = r[tc.VAR_POSITION], r[tc.VAR_ANGLE], r[tc.VAR_SPEED], r[tc.VAR_ACCUMULATED_WAITING_TIME]
            last_wait[vid] = w
            sumw += w
            if sp < 0.1:  # SUMO: "halting" = velocidad < 0.1 m/s
                queue += 1
            if len(vehicles) < MAX_VEHICLES:
                vehicles.append([vid, round(x, 1), round(y, 1), round(ang), round(sp, 1)])
        self.last_wait = last_wait
        n = len(res)
        denom = self.finished_n + n
        t0, a0 = self._arr_hist[0]
        window = max(min(self.t - t0, THROUGHPUT_WINDOW), 60)
        gtl = self.conn.trafficlight
        return {
            "vehicles": vehicles,
            "tls": {tid: gtl.getRedYellowGreenState(tid) for tid in self.se.ts_ids},
            "metrics": {
                "mean_wait": round((self.finished_wait + sumw) / denom, 2) if denom else 0.0,
                "queue": queue,
                "throughput": round((self.arrived - a0) * 3600.0 / window, 1),
                "arrived": self.arrived,
                "n_vehicles": n,
            },
        }

    def close(self) -> None:
        try:
            self.penv.close()
        except Exception:
            log.exception("cerrando %s", self.key)


class SimManager:
    """Hilo de simulacion + cola de comandos + ultimo estado serializado."""

    def __init__(self, scenario: str = "toy_grid2x2", policy: dict | None = None, seed: int = EVAL_SEEDS[0], publish=None):
        self.publish = publish or (lambda msg: None)
        self.scenario_name = scenario
        self.policy_spec = policy
        self.seed = seed
        self.speed = 1.0
        self.sims: dict[str, Sim] = {}
        self.shared: SharedDemand | None = None
        self.policy_info: dict = {}
        self.incidents: set[str] = set()
        self.profile: str | None = None
        self.episode = 0
        self.horizon = 0
        self.status = "starting"  # starting | loading | running | error
        self.error: str | None = None
        self.latest: str = json.dumps({"type": "loading", "scenario": scenario})
        self._cmds: Queue = Queue()
        self._stop = threading.Event()
        self._dirty = True
        self._credit = 0.0
        self._thread = threading.Thread(target=self._run, name="sim-manager", daemon=True)
        self._book: RouteBook | None = None

    # ---- API publica (cualquier hilo) -------------------------------------------
    def start(self) -> "SimManager":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=15)

    def submit(self, cmd: dict) -> Future:
        fut: Future = Future()
        self._cmds.put((cmd, fut))
        return fut

    def call(self, fn, timeout: float = 30.0):
        """Ejecuta fn(manager) en el hilo de simulacion (acceso seguro a TraCI) y devuelve el resultado."""
        fut: Future = Future()
        self._cmds.put(({"cmd": "_call", "fn": fn}, fut))
        return fut.result(timeout)

    def wait_ready(self, timeout: float = 60.0) -> bool:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if self.status in ("running", "error"):
                return self.status == "running"
            time.sleep(0.05)
        return False

    # ---- construccion ---------------------------------------------------------------
    def _build(self, scenario_name: str, policy_spec: dict | None, seed: int, keep_episode: bool = False) -> None:
        if scenario_name not in SCENARIOS:
            raise ValueError(f"escenario desconocido: {scenario_name}")
        sc = get_scenario(scenario_name)
        if not Path(sc.net_file).exists():
            raise ValueError(f"la red de {scenario_name} no existe todavia: {sc.net_file}")
        rl_policy, info = load_rl_policy(policy_spec)
        net = read_net(sc.net_file)
        book = RouteBook(net)
        use_gen = bool(sc.profile) and make_generator(sc.net_file, sc.profile, seed) is not None
        schedule = []
        if not use_gen:
            horizon = sc.num_seconds
            schedule = load_schedule(_route_for(sc, seed), book, seed, horizon)
        shared = SharedDemand(sc.name, sc.net_file, seed, sc.profile, schedule, use_gen)
        if self.profile:  # se conserva la hora del dia elegida al reiniciar
            shared.set_profile(self.profile)
        new = {}
        try:
            new["fijo"] = Sim("fijo", sc, seed, FixedProgram(), shared, first=True)
            new["rl"] = Sim("rl", sc, seed, rl_policy, shared)
        except Exception:
            for s in new.values():
                s.close()
            raise
        old = self.sims
        self.sims, self.shared, self._book = new, shared, book
        for s in old.values():
            s.close()
        self.scenario_name, self.policy_spec, self.seed = sc.name, policy_spec, seed
        self.policy_info = info
        self.horizon = sc.num_seconds
        self.episode = self.episode + 1 if keep_episode else 1
        shared.closed = set(self.incidents)
        for edge in sorted(self.incidents):
            for s in new.values():
                s.set_incident(edge, True)
        self._dirty = True

    # ---- comandos (hilo de simulacion) ---------------------------------------------
    def _handle(self, cmd: dict):
        name = cmd.get("cmd")
        if name == "_call":
            return cmd["fn"](self)
        if name == "speed":
            v = float(cmd.get("value", 1))
            if not 0 <= v <= 60:
                raise ValueError("speed debe estar entre 0 y 60")
            self.speed, self._credit = v, 0.0
            self._dirty = True
            return {"speed": v}
        if name == "reset":
            self.incidents.clear()
            self.profile = None
            self.status = "loading"
            self._broadcast({"type": "loading", "scenario": cmd.get("scenario", self.scenario_name)})
            try:
                self._build(
                    cmd.get("scenario") or self.scenario_name,
                    cmd.get("policy") if "policy" in cmd else self.policy_spec,
                    int(cmd.get("seed", self.seed)),
                )
                self.error = None
            finally:
                self.status = "running" if self.sims else "error"
            return {"scenario": self.scenario_name, "policy": self.policy_info}
        if not self.sims:
            raise ValueError("la simulacion aun no esta lista")
        t = self.sims["fijo"].t
        if name == "inject":
            edges = self._book.farthest_route(str(cmd["edge"]))
            n = max(1, min(int(cmd.get("n", 10)), 200))
            ids = self.shared.inject(t, edges, n)
            return {"vehicles": len(ids), "route": list(edges), "t": t}
        if name == "time_of_day":
            prof = str(cmd.get("profile", ""))
            if prof not in PROFILE_NAMES:
                raise ValueError(f"perfil desconocido: {prof}")
            self.shared.set_profile(prof)
            self.profile = prof
            self._dirty = True
            return {"profile": prof, "scale": self.shared.scale}
        if name == "incident":
            edge = self._book.edge(str(cmd["edge"])).getID()
            on = bool(cmd.get("on", True))
            for s in self.sims.values():
                s.set_incident(edge, on)
            (self.incidents.add if on else self.incidents.discard)(edge)
            self.shared.closed = set(self.incidents)
            self._dirty = True
            return {"edge": edge, "on": on}
        raise ValueError(f"comando desconocido: {name}")

    def _drain(self) -> None:
        while True:
            try:
                cmd, fut = self._cmds.get_nowait()
            except Empty:
                return
            try:
                fut.set_result(self._handle(cmd))
            except Exception as exc:
                log.warning("comando %s fallo: %s", cmd.get("cmd"), exc)
                fut.set_exception(exc)

    # ---- estado ----------------------------------------------------------------------
    def _state(self) -> dict:
        sims = {k: s.snapshot() for k, s in self.sims.items()}
        wf, wr = sims["fijo"]["metrics"]["mean_wait"], sims["rl"]["metrics"]["mean_wait"]
        return {
            "type": "state",
            "t": self.sims["fijo"].t,
            "sims": sims,
            "improvement_pct": round((wf - wr) / wf * 100.0, 1) if wf > 1e-6 else 0.0,
            "speed": self.speed,
            "scenario": self.scenario_name,
            "policy": self.policy_info,
            "profile": self.profile,
            "incidents": sorted(self.incidents),
            "episode": self.episode,
        }

    def _broadcast(self, obj: dict) -> None:
        self.latest = json.dumps(obj, separators=(",", ":"))
        self.publish(self.latest)

    def _publish_state(self) -> None:
        self._broadcast(self._state())
        self._dirty = False

    # ---- bucle principal ---------------------------------------------------------------
    def _run(self) -> None:
        try:
            self.status = "loading"
            self._build(self.scenario_name, self.policy_spec, self.seed)
            self.status = "running"
        except Exception as exc:
            log.exception("no se pudo iniciar la simulacion")
            self.status, self.error = "error", str(exc)
            self._broadcast({"type": "error", "message": str(exc)})
        last_loop = last_pub = time.monotonic()
        while not self._stop.is_set():
            t_loop = time.monotonic()
            dt, last_loop = min(t_loop - last_loop, 0.5), t_loop
            self._drain()
            n_stepped = 0
            try:
                if self.sims and self.speed > 0:
                    self._credit += self.speed * dt
                    n = min(int(self._credit), MAX_STEPS_PER_TICK)
                    self._credit = 0.0 if n >= MAX_STEPS_PER_TICK else self._credit - n
                    n_stepped = n
                    for _ in range(n):
                        for s in self.sims.values():  # lock-step: ambos avanzan el mismo segundo
                            s.step()
                        if self.sims["fijo"].t >= self.horizon:
                            self._build(self.scenario_name, self.policy_spec, self.seed, keep_episode=True)
                    if n:
                        self._publish_state()
                        last_pub = t_loop
                if self.sims and not n_stepped and (self._dirty or (self.speed == 0 and t_loop - last_pub > 1.0)):
                    self._publish_state()
                    last_pub = t_loop
            except Exception as exc:
                log.exception("error en el bucle de simulacion")
                self.status, self.error, self.speed = "error", str(exc), 0.0  # pausa para no repetir el error
                self._broadcast({"type": "error", "message": str(exc)})
            self._stop.wait(max(0.0, TICK - (time.monotonic() - t_loop)))
        for s in self.sims.values():
            s.close()
        self.sims = {}
