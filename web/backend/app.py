"""FastAPI de la demo en vivo.

    uvicorn web.backend.app:app --port 8000

REST:  GET /api/scenarios | /api/network?scenario= | /api/policies | /api/status | /api/state
WS:    /ws  -> recibe comandos JSON (ver docs/ARCHITECTURE.md seccion 8) y emite el estado ~10 Hz.
La simulacion corre en su propio hilo (SimManager), el bucle de eventos nunca se bloquea.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from env.scenarios import SCENARIOS, get_scenario
from web.backend.geometry import export_network
from web.backend.policies import list_policies
from web.backend.sim_manager import SimManager

log = logging.getLogger("web.app")

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPO_ROOT / "web" / "frontend" / "dist"
ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"]


def _demand_ready(name: str) -> bool:
    sc = get_scenario(name)
    if sc.route_file:
        return Path(sc.route_file).exists()
    try:
        import env.demand  # noqa: F401  (rama feat/env-reforma)

        return True
    except Exception:
        return False


def scenario_info(name: str) -> dict:
    sc = get_scenario(name)
    net_ok = Path(sc.net_file).exists()
    return {
        "name": name,
        "description": sc.description,
        "net_file": os.path.relpath(sc.net_file, REPO_ROOT) if sc.net_file.startswith(str(REPO_ROOT)) else sc.net_file,
        "net_available": net_ok,
        "available": net_ok and _demand_ready(name),
        "profile": sc.profile,
        "num_seconds": sc.num_seconds,
    }


def default_scenario() -> str:
    pref = os.environ.get("WEB_SCENARIO") or "reforma_pico"
    for name in (pref, "toy_grid2x2"):
        if name in SCENARIOS and scenario_info(name)["available"]:
            return name
    return "toy_grid2x2"


class Hub:
    """Reparte el ultimo estado a todos los clientes WS. Si un cliente es lento se saltan cuadros."""

    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.latest: str | None = None
        self._wake: asyncio.Event | None = None
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._task = asyncio.create_task(self._pump())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    def publish(self, msg: str) -> None:
        """Se llama desde el hilo de simulacion."""
        if self.loop is None or self.loop.is_closed():
            return
        self.loop.call_soon_threadsafe(self._set_latest, msg)

    def _set_latest(self, msg: str) -> None:
        self.latest = msg
        self._wake.set()

    async def _pump(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            msg = self.latest
            if not msg or not self.clients:
                continue
            results = await asyncio.gather(*(self._send(ws, msg) for ws in list(self.clients)))
            for ws, ok in zip(list(self.clients), results):
                if not ok:
                    self.clients.discard(ws)

    @staticmethod
    async def _send(ws: WebSocket, msg: str) -> bool:
        try:
            await asyncio.wait_for(ws.send_text(msg), timeout=2.0)
            return True
        except Exception:
            return False


def create_app(initial_scenario: str | None = None, autostart: bool = True) -> FastAPI:
    hub = Hub()
    manager = SimManager(initial_scenario or default_scenario(), publish=hub.publish)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.start()
        if autostart:
            manager.start()
        yield
        await hub.stop()
        if autostart:
            await asyncio.to_thread(manager.stop)

    app = FastAPI(title="Semaforos RL - demo en vivo", lifespan=lifespan)
    app.state.manager, app.state.hub = manager, hub
    app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/scenarios")
    def scenarios():
        return {"current": manager.scenario_name, "scenarios": [scenario_info(n) for n in SCENARIOS]}

    @app.get("/api/network")
    def network(scenario: str | None = None):
        name = scenario or manager.scenario_name
        if name not in SCENARIOS:
            raise HTTPException(404, f"escenario desconocido: {name}")
        net_file = get_scenario(name).net_file
        if not Path(net_file).exists():
            raise HTTPException(404, f"la red de {name} aun no existe ({net_file})")
        return export_network(net_file, name)

    @app.get("/api/policies")
    def policies():
        return {"policies": list_policies(), "current": manager.policy_info}

    @app.get("/api/status")
    def status():
        return {
            "status": manager.status,
            "error": manager.error,
            "scenario": manager.scenario_name,
            "policy": manager.policy_info,
            "speed": manager.speed,
        }

    @app.get("/api/state")
    def state():
        return json.loads(manager.latest)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        origin = ws.headers.get("origin")
        if origin and origin not in ORIGINS:  # los WS no pasan por CORS: se valida a mano
            await ws.close(code=1008)
            return
        await ws.accept()
        hub.clients.add(ws)
        try:
            await ws.send_text(manager.latest)  # estado actual al conectar
            while True:
                raw = await ws.receive_text()
                try:
                    cmd = json.loads(raw)
                    if not isinstance(cmd, dict) or "cmd" not in cmd:
                        raise ValueError('se esperaba {"cmd": ...}')
                except ValueError as exc:
                    await ws.send_text(json.dumps({"type": "ack", "ok": False, "error": str(exc)}))
                    continue
                # no se espera aqui: el ack llega cuando el hilo de simulacion procesa el comando
                asyncio.create_task(_ack(ws, cmd, manager.submit(cmd)))
        except WebSocketDisconnect:
            pass
        finally:
            hub.clients.discard(ws)

    async def _ack(ws: WebSocket, cmd: dict, fut):
        try:
            result = await asyncio.wrap_future(fut)
            msg = {"type": "ack", "cmd": cmd["cmd"], "ok": True, "result": result}
        except Exception as exc:
            msg = {"type": "ack", "cmd": cmd["cmd"], "ok": False, "error": str(exc)}
        try:
            await ws.send_text(json.dumps(msg))
        except Exception:
            pass

    if FRONTEND_DIST.is_dir():  # al final, para no tapar /api ni /ws
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app


app = create_app()
