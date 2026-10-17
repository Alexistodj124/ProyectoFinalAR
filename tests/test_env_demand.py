"""DemandGenerator.spawn/inject: un vehículo rechazado por SUMO se omite solo y el cursor siempre avanza."""
from __future__ import annotations

import pytest

from env.demand import DemandGenerator


class _Ns:
    """Namespace con métodos registrados (imita conn.route / conn.vehicle / conn.vehicletype)."""

    def __init__(self, **fns):
        self.__dict__.update(fns)


class FakeConn:
    """Conexión TraCI falsa: guarda lo que se agrega y rechaza lo que `reject(vid, rid)` diga."""

    def __init__(self, reject=lambda vid, rid: False, reject_route=lambda rid: False, error=RuntimeError):
        self.vehicles: list[str] = []
        self.routes: dict[str, list[str]] = {}
        self.calls: list[str] = []
        self.error = error

        def route_add(rid, edges):
            if reject_route(rid):
                raise error(f"route {rid} refused")
            self.routes[rid] = edges

        def vehicle_add(vid, rid, **kw):
            self.calls.append(vid)
            if vid in self.vehicles:
                raise error(f"Duplicate vehicle {vid}")
            if reject(vid, rid):
                raise error(f"vehicle {vid} has no valid route")
            self.vehicles.append(vid)

        self.route = _Ns(add=route_add, getIDList=lambda: list(self.routes))
        self.vehicle = _Ns(add=vehicle_add)
        self.vehicletype = _Ns(getIDList=lambda: ["auto"])


@pytest.fixture(scope="module")
def gen_factory():
    return lambda seed=0: DemandGenerator("cruce_pico", profile="pico", seed=seed)


def _expected(gen, lo, hi):
    return [vid for s in range(lo, hi + 1) for vid, _ in gen.arrivals(s)]


def test_spawn_skips_rejected_vehicle_and_never_duplicates(gen_factory):
    gen = gen_factory()
    want = _expected(gen, 0, 59)
    assert len(want) > 20
    bad = set(want[3::5])  # un vehículo de cada cinco falla (p. ej. ruta por una arista cerrada)
    conn = FakeConn(reject=lambda vid, rid: vid in bad)
    added = gen.spawn(conn, 59)
    assert added == len(want) - len(bad)
    assert conn.vehicles == [v for v in want if v not in bad]
    assert len(set(conn.calls)) == len(conn.calls)  # nadie se intentó dos veces
    # volver a llamar con el mismo t no reintenta ningún segundo; con un t mayor solo agrega lo nuevo
    n_calls = len(conn.calls)
    assert gen.spawn(conn, 59) == 0 and len(conn.calls) == n_calls
    more = _expected(gen, 60, 89)
    assert gen.spawn(conn, 89) == len(more) - len({v for v in more if v in bad})
    assert len(set(conn.vehicles)) == len(conn.vehicles)


def test_spawn_route_refused_skips_only_that_route(gen_factory):
    gen = gen_factory()
    bad_rid = "dg_r0"
    conn = FakeConn(reject_route=lambda rid: rid == bad_rid)
    gen.spawn(conn, 120)
    assert bad_rid not in conn.routes and conn.vehicles  # las demás rutas sí entran
    r0 = {vid for s in range(121) for vid, ri in gen.arrivals(s) if ri == 0}
    assert not r0 & set(conn.vehicles)


def test_spawn_cursor_is_per_connection_and_streams_match(gen_factory):
    gen = gen_factory()
    a, b = FakeConn(), FakeConn(reject=lambda vid, rid: vid.startswith("dg1_"))
    gen.spawn(a, 30)
    gen.spawn(b, 30)  # b rechaza algunos, pero su cursor avanza igual
    gen.spawn(a, 60)
    gen.spawn(b, 60)
    assert a.vehicles == _expected(gen, 0, 60)
    assert b.vehicles == [v for v in _expected(gen, 0, 60) if not v.startswith("dg1_")]


def test_spawn_advances_cursor_even_if_connection_dies(gen_factory):
    class FatalTraCIError(Exception):  # mismo nombre que traci.exceptions.FatalTraCIError
        pass

    gen = gen_factory()
    conn = FakeConn(reject=lambda vid, rid: True, error=FatalTraCIError)
    with pytest.raises(FatalTraCIError):  # una conexión caída no es un problema de un vehículo: se propaga
        gen.spawn(conn, 40)
    assert gen._cursor[id(conn)] == 40  # y los segundos ya no se reintentan


def test_inject_skips_failures_and_does_not_reuse_ids(gen_factory):
    gen = gen_factory()
    edge = gen.route_edges[0][0]
    a, b = FakeConn(), FakeConn(reject=lambda vid, rid: vid == "inj1")
    ids = gen.inject([a, b], edge, 4)
    assert ids == ["inj0", "inj2", "inj3"]  # solo los que aceptaron las dos conexiones
    assert a.vehicles == ["inj0", "inj1", "inj2", "inj3"] and b.vehicles == ["inj0", "inj2", "inj3"]
    assert gen.inject([a, b], edge, 2) == ["inj4", "inj5"]  # ids nuevos
    dead = FakeConn(reject_route=lambda rid: True)
    assert gen.inject(dead, edge, 3) == [] and dead.vehicles == []
    assert gen.inject(a, "no_such_edge", 3) == []


def test_spawn_with_closed_edge_in_sumo(gen_factory):
    """Con SUMO real: cerrar una arista de entrada a los autos no tumba spawn(); el resto del flujo entra."""
    import sumolib
    import traci

    from env.scenarios import get_scenario

    sc = get_scenario("cruce_pico")
    gen = gen_factory(seed=1)
    closed = gen.route_edges[0][0]
    traci.start([sumolib.checkBinary("sumo"), "-n", sc.net_file, "--no-step-log", "--no-warnings"], label="dgClosed")
    conn = traci.getConnection("dgClosed")
    try:
        for ln in range(conn.edge.getLaneNumber(closed)):
            conn.lane.setDisallowed(f"{closed}_{ln}", ["passenger"])
        total = 0
        for t in range(1, 91):
            conn.simulationStep()
            total += gen.spawn(conn, t)
        ids = list(conn.vehicle.getIDList()) + list(conn.simulation.getArrivedIDList())
        assert total > 10 and gen._cursor[id(conn)] == 90
        assert len(set(ids)) == len(ids)
        want = _expected(gen, 0, 90)
        assert total < len(want) and set(conn.vehicle.getIDList()) <= set(want)
    finally:
        conn.close()
