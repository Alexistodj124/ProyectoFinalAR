"""Pruebas del backend de la demo web sobre toy_grid2x2 (4 TLS).

Se levanta un uvicorn real en un hilo (puerto libre) y se usan `requests` + `websockets`:
el TestClient de Starlette pide httpx, que no esta en el entorno compartido.
"""
import os

os.environ.pop("LIBSUMO_AS_TRACI", None)  # la demo necesita TraCI por socket (2 simulaciones)

import json
import socket
import threading
import time

import pytest
import requests
import uvicorn
from websockets.sync.client import connect

import sumo_rl.environment.env as sumo_rl_env
from env.scenarios import get_scenario
from web.backend.app import create_app
from web.backend.demand_driver import Arrival, FALLBACK_SCALE, SharedDemand
from web.backend.geometry import export_network
from web.backend.policies import CyclicPolicy, list_policies, load_rl_policy, resolve_run

needs_traci = pytest.mark.skipif(sumo_rl_env.LIBSUMO, reason="otro modulo importo sumo_rl con LIBSUMO_AS_TRACI")
GRID = "toy_grid2x2"


# ------------------------------------------------------------------ pruebas sin SUMO
def test_geometry_toy_nets():
    for name, n_tls in (("toy_single", 1), ("toy_grid2x2", 4)):
        net = export_network(get_scenario(name).net_file, name)
        assert len(net["tls"]) == n_tls and net["lanes"] and net["edges"] and net["junctions"]
        x0, y0, x1, y1 = net["bbox"]
        assert x1 > x0 and y1 > y0
        lane = net["lanes"][0]
        assert {"id", "edge", "name", "shape", "width", "allow_passenger"} <= set(lane)
        assert len(lane["shape"]) >= 2 and len(lane["shape"][0]) == 2
        assert all(len(t["links"]) > 0 for t in net["tls"])
        assert not net["projected"]  # redes toy sin proyeccion: no hay lon/lat
        assert export_network(get_scenario(name).net_file, name) is net  # cacheado


def test_policies_listing_and_fallback():
    ids = {p["id"] for p in list_policies()}
    assert {"max_pressure", "actuated", "fixed"} <= ids
    pol, info = load_rl_policy(None)  # defecto: max_pressure, o ciclica si aun no existe
    assert hasattr(pol, "act") and info["label"]
    assert isinstance(CyclicPolicy(), type(CyclicPolicy()))
    with pytest.raises(ValueError):
        resolve_run("/etc")  # solo se cargan modelos dentro de runs/
    with pytest.raises(ValueError):
        load_rl_policy({"algo": "no_existe"})


def test_demand_schedule_is_deterministic_and_scalable():
    sched = [Arrival(t, f"v{t}_{k}", ("a", "b")) for t in range(300) for k in range(3)]

    def count(profile):
        sh = SharedDemand("x", "net", 1, "pico", sched, False)
        sh.set_profile(profile)
        return sum(len(sh.background(t)) for t in range(300))

    assert count("pico") == 900 and count("pico") == count("pico")
    assert count("noche") < 450 < count("pico_x13") - 100
    assert abs(count("noche") / 900 - FALLBACK_SCALE["noche"]) < 0.08


# ------------------------------------------------------------------ pruebas con las dos simulaciones
class Client:
    """Sesion HTTP contra el servidor de prueba."""

    def __init__(self, app, port):
        self.app, self.port = app, port
        self.base = f"http://127.0.0.1:{port}"

    def get(self, path, **kw):
        return requests.get(self.base + path, timeout=30, **kw)


@pytest.fixture(scope="module")
def client():
    if sumo_rl_env.LIBSUMO:
        pytest.skip("LIBSUMO_AS_TRACI activo en este proceso")
    app = create_app(GRID)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    t0 = time.time()
    while not server.started and time.time() - t0 < 30:
        time.sleep(0.05)
    assert server.started
    assert app.state.manager.wait_ready(60), app.state.manager.error
    yield Client(app, port)
    server.should_exit = True
    thread.join(timeout=20)


class WS:
    def __init__(self, sock):
        self.sock = sock

    def recv(self):
        return json.loads(self.sock.recv(timeout=30))

    def send_raw(self, text):
        self.sock.send(text)


def recv_state(ws, pred=lambda s: True, limit=400):
    """Lee mensajes hasta un estado que cumpla pred (ignora acks y otros mensajes)."""
    for _ in range(limit):
        msg = ws.recv()
        if msg.get("type") == "state" and pred(msg):
            return msg
    raise AssertionError("no llego el estado esperado")


def send(ws, **cmd):
    """Manda un comando y espera su ack (los estados que lleguen en medio se descartan)."""
    ws.send_raw(json.dumps(cmd))
    for _ in range(400):
        msg = ws.recv()
        if msg.get("type") == "ack":
            return msg
    raise AssertionError("no llego el ack")


@pytest.fixture()
def ws(client):
    with connect(f"ws://127.0.0.1:{client.port}/ws") as sock:
        yield WS(sock)


def test_network_scenarios_policies(client):
    net = client.get("/api/network", params={"scenario": GRID}).json()
    assert len(net["tls"]) == 4 and len(net["lanes"]) > 0
    assert client.get("/api/network").json()["scenario"] == GRID  # por defecto, el actual
    assert client.get("/api/network", params={"scenario": "nope"}).status_code == 404
    sc = {s["name"]: s for s in client.get("/api/scenarios").json()["scenarios"]}
    assert sc[GRID]["available"] and sc["toy_single"]["available"]
    assert isinstance(sc["reforma_pico"]["net_available"], bool)
    pols = client.get("/api/policies").json()["policies"]
    assert any(p["kind"] == "baseline" for p in pols)
    assert client.get("/api/status").json()["status"] == "running"


def test_ws_delivers_both_sims(ws):
    assert send(ws, cmd="speed", value=20)["ok"]
    a = recv_state(ws)
    b = recv_state(ws, lambda s: s["t"] > a["t"] + 5, limit=100)
    assert b["t"] > a["t"]
    assert set(b["sims"]) == {"fijo", "rl"}
    for sim in b["sims"].values():
        assert set(sim["tls"]) == {"1", "2", "5", "6"} or len(sim["tls"]) == 4
        assert {"mean_wait", "queue", "throughput", "arrived"} <= set(sim["metrics"])
        v = sim["vehicles"][0]
        assert len(v) == 5 and isinstance(v[0], str)
    assert "improvement_pct" in b


def test_inject_same_vehicles_in_both_sims(ws):
    send(ws, cmd="speed", value=20)
    ack = send(ws, cmd="inject", edge="-h11", n=4)
    assert ack["ok"], ack
    t0 = ack["result"]["t"]
    seen = {"fijo": set(), "rl": set()}

    def collect(s):
        for k in seen:
            seen[k] |= {v[0] for v in s["sims"][k]["vehicles"] if v[0].startswith("inj")}
        return s["t"] > t0 + 12

    recv_state(ws, collect, limit=300)
    assert len(seen["fijo"]) == 4
    assert seen["fijo"] == seen["rl"]


def test_incident_toggles_lane_permissions(client, ws):
    mgr = client.app.state.manager
    edge = "-h12"

    def perms(m):
        return {k: s.lane_disallowed(edge) for k, s in m.sims.items()}

    assert all(not d for lanes in mgr.call(perms).values() for d in lanes.values())
    assert send(ws, cmd="incident", edge=edge, on=True)["ok"]
    closed = mgr.call(perms)
    for sim in ("fijo", "rl"):
        assert closed[sim] and all("passenger" in d for d in closed[sim].values())
    s = recv_state(ws, lambda s: edge in s["incidents"], limit=100)
    assert s["incidents"] == [edge]
    assert send(ws, cmd="incident", edge=edge, on=False)["ok"]
    assert all(not d for lanes in mgr.call(perms).values() for d in lanes.values())
    assert not send(ws, cmd="incident", edge="no_existe", on=True)["ok"]


def test_time_of_day_and_bad_commands(ws):
    ack = send(ws, cmd="time_of_day", profile="noche")
    assert ack["ok"] and ack["result"]["profile"] == "noche"
    assert not send(ws, cmd="time_of_day", profile="madrugada")["ok"]
    assert not send(ws, cmd="speed", value=1000)["ok"]
    assert not send(ws, cmd="baila")["ok"]
    ws.send_raw("no es json")
    assert ws.recv()["ok"] is False
    assert send(ws, cmd="time_of_day", profile="pico")["ok"]


def test_speed_zero_pauses(client, ws):
    mgr = client.app.state.manager
    send(ws, cmd="speed", value=20)
    recv_state(ws, lambda s: s["t"] > 5, limit=100)
    assert send(ws, cmd="speed", value=0)["ok"]
    t_a = mgr.call(lambda m: m.sims["fijo"].t)
    time.sleep(0.8)
    assert mgr.call(lambda m: m.sims["fijo"].t) == t_a
    states = [recv_state(ws) for _ in range(2)]  # latidos mientras esta en pausa
    assert states[-1]["t"] == t_a and states[-1]["speed"] == 0
    assert send(ws, cmd="speed", value=20)["ok"]
    assert recv_state(ws, lambda s: s["t"] > t_a + 3, limit=100)["t"] > t_a


def test_reset_switches_scenario_and_reports_errors(ws):
    assert not send(ws, cmd="reset", scenario="no_existe")["ok"]
    ack = send(ws, cmd="reset", scenario="toy_single", policy={"algo": "max_pressure"})
    assert ack["ok"], ack
    send(ws, cmd="speed", value=20)
    s = recv_state(ws, lambda s: s["scenario"] == "toy_single" and s["t"] > 3, limit=300)
    assert len(s["sims"]["rl"]["tls"]) == 1


# ------------------------------------------------------------------ con un DemandGenerator simulado (contrato seccion 3)
@needs_traci
def test_manager_uses_demand_generator_when_available(monkeypatch):
    """Si env.demand existe y el escenario genera su demanda, spawn() se llama igual en las dos sims."""
    import sys
    import types

    from env.scenarios import SCENARIOS
    from web.backend.sim_manager import SimManager

    calls = {"profiles": []}

    class FakeGenerator:
        def __init__(self, net_file, profile, seed=0):
            self.profile, self.seed = profile, seed

        def set_profile(self, profile):
            calls["profiles"].append(profile)
            self.profile = profile

        def spawn(self, conn, t):
            if t % 4 == 0:
                conn.route.add(f"g{t}", ["-h11", "-h12", "-h13"])
                conn.vehicle.add(f"gen{t}", f"g{t}", departLane="best", departSpeed="max")

    fake = types.ModuleType("env.demand")
    fake.DemandGenerator = FakeGenerator
    monkeypatch.setitem(sys.modules, "env.demand", fake)
    monkeypatch.setitem(SCENARIOS, "toy_gen", get_scenario(GRID).with_(name="toy_gen", profile="pico"))

    mgr = SimManager("toy_gen").start()
    try:
        assert mgr.wait_ready(60), mgr.error
        assert mgr.shared.use_generator and not mgr.shared.schedule
        mgr.submit({"cmd": "speed", "value": 20}).result(5)
        mgr.submit({"cmd": "time_of_day", "profile": "noche"}).result(5)
        deadline = time.time() + 20
        while mgr.sims["fijo"].t < 30 and time.time() < deadline:
            time.sleep(0.1)
        state = json.loads(mgr.latest)
        ids = {k: {v[0] for v in state["sims"][k]["vehicles"] if v[0].startswith("gen")} for k in ("fijo", "rl")}
        arrived = {k: state["sims"][k]["metrics"]["arrived"] for k in ("fijo", "rl")}
        assert ids["fijo"] or arrived["fijo"]  # el generador alimento la sim
        assert ids["fijo"] == ids["rl"] or abs(len(ids["fijo"]) - len(ids["rl"])) <= 2
        assert calls["profiles"].count("noche") == 2  # set_profile se aplico a cada sim
    finally:
        mgr.stop()


@needs_traci
def test_same_control_same_demand_gives_identical_sims():
    """Premisa de la demo: con el mismo control, las dos sims son identicas (demanda inyectada igual)."""
    from env.reforma_env import _route_for
    from web.backend.demand_driver import RouteBook, load_schedule
    from web.backend.geometry import read_net
    from web.backend.policies import FixedProgram
    from web.backend.sim_manager import Sim

    sc = get_scenario(GRID)
    book = RouteBook(read_net(sc.net_file))
    shared = SharedDemand(sc.name, sc.net_file, 7, None, load_schedule(_route_for(sc, 7), book, 7, 3600), False)
    a, b = Sim("a", sc, 7, FixedProgram(), shared, first=True), Sim("b", sc, 7, FixedProgram(), shared)
    try:
        shared.inject(50, book.farthest_route("-h11"), 6)
        for _ in range(200):
            a.step()
            b.step()
        assert a.snapshot()["metrics"] == b.snapshot()["metrics"]
        assert a.snapshot()["metrics"]["arrived"] > 0
    finally:
        a.close()
        b.close()
