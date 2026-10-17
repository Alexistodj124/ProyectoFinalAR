"""Demanda de la demo: la MISMA para las dos simulaciones, inyectada por TraCI.

SUMO arranca con un archivo de rutas vacio y todos los vehiculos entran por TraCI, llamando
a `SimDemand.spawn(conn, t)` con el mismo `t` en "fijo" y en "rl". Asi la demanda no depende
de la RNG interna de SUMO (que se desincroniza en cuanto los semaforos se comportan distinto).

Dos fuentes de demanda de fondo:
  * `env.demand.DemandGenerator(scenario, profile, seed)` cuando el escenario genera su demanda
    (`scenario.profile`, escenarios reforma_* y cruce_*). Se crea UNA sola instancia por
    construccion (`SharedDemand.gen`): `spawn(conn, t)` lleva un cursor por conexion y las
    llegadas del segundo s solo dependen de (seed, perfil, s), asi que alimenta a las dos sims
    con vehiculos identicos. `set_profile`, `rates` e `inject` tambien son suyos.
  * Respaldo: se leen los vehiculos / flujos del `.rou.xml` del escenario (toy_* o el que
    genera `env.demand.routes_for`) y se expanden a una agenda determinista por semilla.
    La "hora del dia" escala esa agenda (adelgaza o duplica llegadas de forma determinista).
Encima de cualquiera de las dos van las inyecciones manuales (comando `inject`).
"""
from __future__ import annotations

import logging
import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

log = logging.getLogger("web.demand")

# Escala de la agenda estatica segun el perfil (solo se usa en el respaldo sin DemandGenerator).
FALLBACK_SCALE = {"pico": 1.0, "mediodia": 0.7, "pico_x13": 1.3, "noche": 0.3}


def make_generator(scenario, profile: str | None, seed: int):
    """Instancia `env.demand.DemandGenerator(scenario, profile, seed)`; None si no aplica.

    `scenario` es un `Scenario` (o su nombre). Si el escenario no genera demanda (toy_*, que
    traen su .rou.xml) o el modulo no se puede importar, devuelve None y se usa la agenda estatica.
    """
    if not profile:
        return None
    try:
        from env.demand import DemandGenerator
    except Exception as exc:  # ImportError, o un modulo a medio construir
        log.info("DemandGenerator no disponible (%s); se usa el respaldo estatico", exc)
        return None
    return DemandGenerator(scenario, profile, seed=seed)


# --------------------------------------------------------------------------- rutas
class RouteBook:
    """Rutas con sumolib: de un borde a un borde, o de un borde al destino alcanzable mas lejano."""

    def __init__(self, net):
        self.net = net
        self._cache: dict[tuple[str, str], tuple[str, ...] | None] = {}
        self._far: dict[str, tuple[str, ...]] = {}

    def edge(self, edge_id: str):
        """Acepta id de borde o de carril (`borde_0`) y rechaza bordes internos."""
        eid = edge_id
        if not self.net.hasEdge(eid) and "_" in eid:
            eid = eid.rsplit("_", 1)[0]
        if eid.startswith(":") or not self.net.hasEdge(eid):
            raise ValueError(f"borde desconocido: {edge_id}")
        return self.net.getEdge(eid)

    @staticmethod
    def _is_exit(edge) -> bool:
        """Borde por el que los vehiculos salen de la red: sin sucesores (salvo el retorno por el mismo nodo)."""
        return all(s.getToNode() == edge.getFromNode() for s in edge.getOutgoing())

    def path(self, a: str, b: str) -> tuple[str, ...] | None:
        key = (a, b)
        if key not in self._cache:
            edges, _ = self.net.getShortestPath(self.net.getEdge(a), self.net.getEdge(b), vClass="passenger")
            self._cache[key] = tuple(e.getID() for e in edges) if edges else None
        return self._cache[key]

    def farthest_route(self, edge_id: str) -> tuple[str, ...]:
        """Ruta desde `edge_id` hasta el borde de salida (fringe) alcanzable mas lejano."""
        e = self.edge(edge_id)
        if e.getID() in self._far:
            return self._far[e.getID()]
        best: tuple[str, ...] = (e.getID(),)
        best_len = -1.0
        for d in self.net.getEdges(withInternal=False):
            if d.getID() == e.getID() or not d.allows("passenger") or not self._is_exit(d):
                continue
            p = self.path(e.getID(), d.getID())
            if not p:
                continue
            length = sum(self.net.getEdge(x).getLength() for x in p)
            if length > best_len:
                best, best_len = p, length
        self._far[e.getID()] = best
        return best


# --------------------------------------------------------------------------- agenda estatica
@dataclass(frozen=True)
class Arrival:
    t: int
    vid: str
    edges: tuple[str, ...]
    lane: str = "best"
    speed: str = "max"


def _fnum(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load_schedule(route_file: str, book: RouteBook, seed: int, horizon: int) -> list[Arrival]:
    """Expande vehiculos y flujos de un .rou.xml a una agenda determinista (ordenada por t)."""
    rng = random.Random(seed * 7919 + 1)
    root = ET.parse(route_file).getroot()
    named_routes = {r.get("id"): r.get("edges", "").split() for r in root.iter("route") if r.get("id")}

    def edges_of(el) -> tuple[str, ...] | None:
        child = el.find("route")
        if child is not None and child.get("edges"):
            return tuple(child.get("edges").split())
        ref = el.get("route")
        if ref in named_routes:
            return tuple(named_routes[ref])
        if el.get("edges"):
            return tuple(el.get("edges").split())
        if el.get("from") and el.get("to"):
            return book.path(el.get("from"), el.get("to"))
        return None

    out: list[Arrival] = []
    for el in root:
        tag = el.tag
        if tag not in ("vehicle", "trip", "flow"):
            continue
        edges = edges_of(el)
        if not edges:
            continue
        lane, speed = el.get("departLane", "best"), el.get("departSpeed", "max")
        base = el.get("id", tag)
        if tag in ("vehicle", "trip"):
            t = _fnum(el.get("depart"))
            if t is not None and t < horizon:
                out.append(Arrival(int(t), base, edges, lane, speed))
            continue
        b = _fnum(el.get("begin"), 0.0)
        e = min(_fnum(el.get("end"), horizon), horizon)
        times: list[float] = []
        if el.get("probability"):
            p = float(el.get("probability"))
            times = [float(s) for s in range(int(b), int(e)) if rng.random() < p]
        elif el.get("vehsPerHour") or el.get("period"):
            step = 3600.0 / float(el.get("vehsPerHour")) if el.get("vehsPerHour") else float(el.get("period"))
            k = 0
            while b + k * step < e:
                times.append(b + k * step)
                k += 1
        elif el.get("number"):
            n = int(el.get("number"))
            times = [b + (e - b) * i / max(n, 1) for i in range(n)]
        for i, t in enumerate(times):
            out.append(Arrival(int(t), f"{base}.{i}", edges, lane, speed))
    out.sort(key=lambda a: (a.t, a.vid))
    return out


# --------------------------------------------------------------------------- estado compartido
@dataclass
class Injection:
    vid: str
    edges: tuple[str, ...]


@dataclass
class SharedDemand:
    """Todo lo que debe ser identico en las dos simulaciones (se escribe una sola vez)."""

    scenario_name: str
    net_file: str
    seed: int
    profile: str | None
    schedule: list[Arrival] = field(default_factory=list)  # solo respaldo estatico
    use_generator: bool = False
    gen: object | None = None  # env.demand.DemandGenerator compartido por las dos sims
    injections: dict[int, list[Injection]] = field(default_factory=dict)  # respaldo (sin generador)
    gen_injections: dict[int, list[tuple[str, int]]] = field(default_factory=dict)  # t -> [(borde, n)]
    profile_version: int = 0
    scale: float = 1.0
    closed: set = field(default_factory=set)  # bordes cerrados por un incidente
    dropped: int = 0
    _counter: int = 0
    _routes: dict[tuple[str, ...], str] = field(default_factory=dict)
    _u: list[float] = field(default_factory=list)

    def __post_init__(self):
        rng = random.Random(self.seed * 104729 + 7)
        self._u = [rng.random() for _ in range(len(self.schedule))]
        self._by_t: dict[int, list[int]] = {}
        for i, a in enumerate(self.schedule):
            self._by_t.setdefault(a.t, []).append(i)
        if self.gen is not None:
            self.use_generator = True
            self._gen_edges = {e for r in self.gen.route_edges for e in r}
        else:
            self._gen_edges = set()
        if self.profile in FALLBACK_SCALE:
            self.scale = FALLBACK_SCALE[self.profile] if not self.use_generator else 1.0

    def route_id(self, edges: tuple[str, ...]) -> str:
        if edges not in self._routes:
            self._routes[edges] = f"wr{len(self._routes)}"
        return self._routes[edges]

    def inject(self, t_now: int, edges: tuple[str, ...], n: int, per_second: int = 2) -> list[str]:
        """Agenda `n` vehiculos por la ruta `edges`, `per_second` por segundo, desde t_now."""
        self._counter += 1
        ids = []
        for k in range(n):
            vid = f"inj{self._counter}_{k}"
            self.injections.setdefault(t_now + k // per_second, []).append(Injection(vid, edges))
            ids.append(vid)
        return ids

    def set_profile(self, profile: str) -> None:
        """Cambia la hora del dia para las dos sims a la vez (un solo generador)."""
        if self.gen is not None:
            self.gen.set_profile(profile)  # ValueError/KeyError si el perfil no existe
        elif not self.use_generator:
            self.scale = FALLBACK_SCALE.get(profile, 1.0)
        self.profile = profile
        self.profile_version += 1

    def rates(self) -> dict | None:
        """Tasas actuales del generador (veh/h total y por entrada); None sin generador."""
        return self.gen.rates() if self.gen is not None else None

    def can_inject_with_gen(self, edge_id: str) -> bool:
        return self.gen is not None and edge_id in self._gen_edges

    def queue_gen_injection(self, t_now: int, edge_id: str, n: int, per_second: int = 4) -> None:
        """Agenda `n` vehiculos en `edge_id` repartidos en el tiempo (`per_second` por segundo).

        Se materializan en `pre_step`, UNA vez por segundo y para todas las conexiones a la vez,
        con `DemandGenerator.inject` (mismos ids y ruta en las dos sims).
        """
        left, k = n, 0
        while left > 0:
            m = min(per_second, left)
            self.gen_injections.setdefault(t_now + k, []).append((edge_id, m))
            left -= m
            k += 1

    def pre_step(self, t: int, conns: list) -> None:
        """Lo que debe pasar una sola vez por segundo, antes de que las sims hagan spawn/step."""
        for edge_id, n in self.gen_injections.pop(t, ()):
            try:
                ids = self.gen.inject(conns, edge_id, n)
            except Exception as exc:  # p. ej. la ruta cruza un borde cerrado por un incidente: no debe tumbar la demo
                log.warning("inject en %s fallo (%s)", edge_id, exc)
                continue
            if not ids:
                log.warning("inject: %s no esta en ninguna ruta del generador", edge_id)

    def background(self, t: int) -> list[Arrival]:
        """Llegadas de la agenda estatica en el segundo t, ya escaladas (determinista por indice)."""
        out = []
        for i in self._by_t.get(t, ()):
            a = self.schedule[i]
            whole, frac = int(self.scale), self.scale - int(self.scale)
            n = whole + (1 if self._u[i] < frac else 0)
            for k in range(n):
                out.append(a if k == 0 else Arrival(a.t, f"{a.vid}+{k}", a.edges, a.lane, a.speed))
        return out


class SimDemand:
    """Vista por simulacion: llama a spawn() una vez por segundo, antes de simulationStep()."""

    def __init__(self, shared: SharedDemand, first: bool = True):
        self.shared = shared
        self.key_first = first  # solo una de las dos sims cuenta los descartados
        self._registered: set[str] = set()
        self._gen_failed = False

    def _add(self, conn, vid: str, edges: tuple[str, ...], lane="best", speed="max") -> None:
        if self.shared.closed.intersection(edges):  # SUMO no admite rutas por carriles cerrados
            if self.key_first:
                self.shared.dropped += 1
            return
        rid = self.shared.route_id(edges)
        if rid not in self._registered:
            conn.route.add(rid, list(edges))
            self._registered.add(rid)
        try:
            conn.vehicle.add(vid, rid, departLane=lane, departSpeed=speed)
        except Exception as exc:  # ruta bloqueada, id repetido, etc.: no debe tumbar la demo
            log.warning("no se pudo agregar %s: %s", vid, exc)

    def spawn(self, conn, t: int) -> None:
        sh = self.shared
        if sh.gen is not None:
            try:
                sh.gen.spawn(conn, t)
            except Exception as exc:
                # Un vehiculo imposible (p. ej. todos los carriles de su ruta cerrados) no debe
                # tumbar la demo ni repetirse en cada segundo: se salta ese segundo.
                if not self._gen_failed:
                    log.warning("DemandGenerator.spawn fallo en t=%s: %s", t, exc)
                    self._gen_failed = True
                cur = getattr(sh.gen, "_cursor", None)
                if isinstance(cur, dict):
                    cur[id(conn)] = int(t)
        else:
            for a in sh.background(t):
                self._add(conn, a.vid, a.edges, a.lane, a.speed)
        for inj in sh.injections.get(t, ()):
            self._add(conn, inj.vid, inj.edges, "best", "max")
