#!/usr/bin/env python
"""Graba clips de la demo web (fijo vs. RL) para el video de respaldo.

Abre Google Chrome headless, lo controla con el Chrome DevTools Protocol (paquete `websockets`
del venv) y graba la pagina real con `Page.startScreencast`. Durante cada clip maneja la UI
de verdad: clics del mouse (Input.dispatchMouseEvent) en los botones, en el deslizador y en
los carriles del mapa (modos Inyectar / Incidente), la rueda del mouse para hacer zoom y los
botones de Vista / tarjetas de los semaforos para acercarse a un cruce. Las posiciones en el
mapa salen de la propia pagina (window.__maps[...].worldToPage y window.__view), asi que no
dependen de replicar la camara. Un puntero dibujado encima de la pagina muestra donde se hace
cada clic (headless no pinta el cursor del sistema). Cada clip se convierte a MP4 H.264 a 30 fps
constantes con ffmpeg.

Uso (el backend debe estar corriendo, ver web/README.md):

    source scripts/env.sh
    WEB_RUNS_DIR=/ruta/a/runs python -m uvicorn web.backend.app:app --port 8000   # otra terminal
    python scripts/record_demo.py --list
    python scripts/record_demo.py --out ../video/clips                 # todos los clips
    python scripts/record_demo.py --out ../video/clips --clips a_mappo,d_incidente
    python scripts/record_demo.py --screenshot /tmp/demo.png           # solo una captura

Los cuadros (JPEG) se guardan en <out>/<clip>_frames/ con su marca de tiempo y se borran
tras codificar (salvo --keep-frames). No escribe nada dentro del repo.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import websockets

CHROME = os.environ.get("CHROME_BIN", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
FFMPEG = os.environ.get("FFMPEG_BIN", shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg")
W, H = 1920, 1080

# Politicas usadas en el video (la mejor semilla de cada metodo segun selection.csv de best/).
POL = {
    "mappo": {"algo": "mappo", "run": "E5/mappo/seed3"},
    "comm": {"algo": "comm", "run": "E6/comm/seed0"},
    "qmix": {"algo": "qmix", "run": "E5/qmix/seed3"},
    "max_pressure": {"algo": "max_pressure", "run": None},
    "dqn": {"algo": "dqn", "run": "E4/dqn_best/seed1"},
    "ppo": {"algo": "ppo", "run": "E4/ppo/seed0"},
}

# Puntero y "onda" de clic dibujados sobre la pagina (solo para la grabacion).
OVERLAY_JS = r"""
(() => {
  if (window.__rec) return true;
  const st = document.createElement('style');
  st.textContent = `
    #rec-cursor{position:fixed;left:0;top:0;width:30px;height:30px;z-index:99999;pointer-events:none;
      transition:transform .55s cubic-bezier(.22,.8,.3,1);transform:translate(960px,600px);filter:drop-shadow(0 2px 4px #000a)}
    .rec-ripple{position:fixed;z-index:99998;pointer-events:none;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;
      border:3px solid #2ee6a6;animation:recr .7s ease-out forwards}
    @keyframes recr{from{transform:scale(.4);opacity:1}to{transform:scale(4);opacity:0}}`;
  document.head.appendChild(st);
  const c = document.createElement('div');
  c.id = 'rec-cursor';
  c.innerHTML = '<svg width="30" height="30" viewBox="0 0 24 24"><path d="M3 2l7.5 19 2.6-7.4L20.5 11z" fill="#fff" stroke="#0b0e14" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  document.body.appendChild(c);
  window.__rec = {
    move(x, y) { c.style.transform = `translate(${x - 3}px, ${y - 2}px)`; },
    ripple(x, y) { const r = document.createElement('div'); r.className = 'rec-ripple';
      r.style.left = x + 'px'; r.style.top = y + 'px'; document.body.appendChild(r); setTimeout(() => r.remove(), 800); },
    hide() { c.style.opacity = 0; }, show() { c.style.opacity = 1; },
  };
  return true;
})()
"""


# --------------------------------------------------------------------------- CDP
class CDP:
    """Cliente minimo del Chrome DevTools Protocol sobre websockets."""

    def __init__(self, ws):
        self.ws = ws
        self.n = 0
        self.pending: dict[int, asyncio.Future] = {}
        self.handlers: dict[str, list] = {}
        self.reader = asyncio.create_task(self._read())

    async def _read(self):
        async for raw in self.ws:
            m = json.loads(raw)
            if "id" in m:
                fut = self.pending.pop(m["id"], None)
                if fut and not fut.done():
                    if "error" in m:
                        fut.set_exception(RuntimeError(f"CDP: {m['error']}"))
                    else:
                        fut.set_result(m.get("result", {}))
            else:
                for h in self.handlers.get(m.get("method"), []):
                    res = h(m.get("params", {}))
                    if asyncio.iscoroutine(res):
                        asyncio.create_task(res)

    async def send(self, method: str, **params):
        self.n += 1
        fut = asyncio.get_running_loop().create_future()
        self.pending[self.n] = fut
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        return await asyncio.wait_for(fut, 60)

    def on(self, method: str, fn):
        self.handlers.setdefault(method, []).append(fn)

    async def js(self, expr: str):
        r = await self.send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            raise RuntimeError(f"JS: {r['exceptionDetails'].get('text')} {r['exceptionDetails'].get('exception', {}).get('description', '')}")
        return r.get("result", {}).get("value")


def _http_json(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


@contextlib.asynccontextmanager
async def chrome(port: int = 9333, headless: bool = True):
    profile = tempfile.mkdtemp(prefix="rec-chrome-")
    args = [
        CHROME, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
        f"--window-size={W},{H}", "--force-device-scale-factor=1", "--hide-scrollbars",
        "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--mute-audio",
        "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows", "--remote-allow-origins=*", "about:blank",
    ]
    if headless:
        args.insert(1, "--headless=new")
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                targets = _http_json(f"http://127.0.0.1:{port}/json/list")
                pages = [t for t in targets if t.get("type") == "page"]
                if pages:
                    break
            except OSError:
                pass
            await asyncio.sleep(0.2)
        else:
            raise RuntimeError("Chrome no abrio el puerto de depuracion")
        async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None) as ws:
            cdp = CDP(ws)
            yield cdp
            cdp.reader.cancel()
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


# --------------------------------------------------------------------------- grabacion
@dataclass
class Recorder:
    cdp: CDP
    out_dir: Path
    keep_frames: bool = False
    quality: int = 88
    min_interval: float = 1 / 40  # cuadros mas seguidos que esto se descartan (la salida es 30 fps)
    frames: list = field(default_factory=list)
    _dir: Path | None = None
    _on: bool = False
    _t_end: float = 0.0

    def __post_init__(self):
        self.cdp.on("Page.screencastFrame", self._frame)

    async def _frame(self, p):
        await self.cdp.send("Page.screencastFrameAck", sessionId=p["sessionId"])
        if not self._on:
            return
        ts = p["metadata"].get("timestamp") or time.time()
        if self.frames and ts - self.frames[-1][1] < self.min_interval:
            return
        f = self._dir / f"f{len(self.frames):06d}.jpg"
        f.write_bytes(base64.b64decode(p["data"]))
        self.frames.append((f.name, ts))

    async def start(self, name: str):
        self._dir = self.out_dir / f"{name}_frames"
        shutil.rmtree(self._dir, ignore_errors=True)
        self._dir.mkdir(parents=True)
        self.frames = []
        self._on = True
        await self.cdp.send("Page.startScreencast", format="jpeg", quality=self.quality,
                            maxWidth=W, maxHeight=H, everyNthFrame=1)

    async def stop(self, name: str) -> Path:
        self._t_end = time.time()
        await self.cdp.send("Page.stopScreencast")
        self._on = False
        return await asyncio.to_thread(self._encode, name)

    def _encode(self, name: str) -> Path:
        if len(self.frames) < 2:
            raise RuntimeError(f"{name}: solo {len(self.frames)} cuadros")
        lines = []
        for (f, t), (_, t2) in zip(self.frames, self.frames[1:]):
            lines += [f"file '{f}'", f"duration {max(t2 - t, 0.001):.4f}"]
        last, tl = self.frames[-1]
        lines += [f"file '{last}'", f"duration {max(self._t_end - tl, 1 / 30):.4f}", f"file '{last}'"]
        (self._dir / "list.txt").write_text("\n".join(lines) + "\n")
        (self._dir / "timestamps.json").write_text(json.dumps(self.frames))
        out = self.out_dir / f"{name}.mp4"
        cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "list.txt",
               "-vf", f"fps=30,scale={W}:{H}:flags=lanczos,format=yuv420p", "-r", "30",
               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-movflags", "+faststart", str(out.resolve())]
        subprocess.run(cmd, cwd=self._dir, check=True)
        span = self._t_end - self.frames[0][1]
        print(f"   -> {out.name}: {len(self.frames)} cuadros, {span:.1f} s, {len(self.frames) / span:.1f} fps de captura", flush=True)
        if not self.keep_frames:
            shutil.rmtree(self._dir, ignore_errors=True)
        return out


# --------------------------------------------------------------------------- manejo de la UI
class Demo:
    def __init__(self, cdp: CDP, url: str):
        self.cdp, self.url = cdp, url.rstrip("/")
        self.net = None
        self.cursor = (W / 2, H * 0.55)
        self.events: list[tuple[float, str]] = []  # (hora real, que paso): se pasa a segundos del clip en clips_log.json
        self._label: str | None = None

    def ev(self, desc: str):
        self.events.append((time.time(), desc))

    # -- carga
    async def open(self):
        await self.cdp.send("Page.enable")
        await self.cdp.send("Runtime.enable")
        await self.cdp.send("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
        await self.cdp.send("Page.navigate", url=self.url)
        await self.wait_live()
        await self.cdp.js(OVERLAY_JS)
        await self.wait_view()

    async def wait_live(self, timeout: float = 40):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                ok = await self.cdp.js(
                    "!!document.querySelector('canvas') && !document.querySelector('.banner.mock')"
                    " && !document.querySelector('.banner.connecting') && !document.querySelector('.banner.reconnecting')"
                    " && /\\d/.test(document.querySelector('.kpi-vals .fijo')?.textContent || '')")
                if ok:
                    return
            except RuntimeError:
                pass
            await asyncio.sleep(0.3)
        raise RuntimeError("la pagina no llego a modo en vivo (backend apagado o en modo demo)")

    async def state(self) -> dict:
        return _http_json(f"{self.url}/api/state")

    async def sim_t(self) -> int:
        return int((await self.state()).get("t", 0))

    async def wait_sim(self, t: float, timeout: float = 400):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if await self.sim_t() >= t:
                return
            await asyncio.sleep(0.25)
        raise TimeoutError(f"t simulado {t} no llego")

    # -- puntero
    async def move(self, x: float, y: float, pause: float = 0.65):
        await self.cdp.js(f"window.__rec && window.__rec.move({x:.1f},{y:.1f})")
        await self.cdp.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        self.cursor = (x, y)
        await asyncio.sleep(pause)

    async def click_xy(self, x: float, y: float, pause: float = 0.65, label: str | None = None):
        await self.move(x, y, pause)
        self.ev(f"clic {label or self._label or f'({x:.0f},{y:.0f})'}")
        self._label = None
        await self.cdp.js(f"window.__rec && window.__rec.ripple({x:.1f},{y:.1f})")
        for t in ("mousePressed", "mouseReleased"):
            await self.cdp.send("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", buttons=1 if t == "mousePressed" else 0, clickCount=1)
        await asyncio.sleep(0.25)

    async def rect(self, js_el: str) -> tuple[float, float, float, float]:
        r = await self.cdp.js(f"(() => {{ const e = {js_el}; if (!e) return null; const b = e.getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; }})()")
        if not r:
            raise RuntimeError(f"no se encontro el elemento: {js_el}")
        return tuple(r)

    async def click_el(self, js_el: str, pause: float = 0.65):
        x, y, w, h = await self.rect(js_el)
        await self.click_xy(x + w / 2, y + h / 2, pause)

    @staticmethod
    def seg_button(group: str, text: str) -> str:
        """Boton `text` del grupo de controles cuya etiqueta empieza con `group`."""
        return (f"[...document.querySelectorAll('.controls .group')].find(g => (g.querySelector('label')?.textContent || '')"
                f".toLowerCase().startsWith({json.dumps(group.lower())}))?.querySelector('.seg') && "
                f"[...[...document.querySelectorAll('.controls .group')].find(g => (g.querySelector('label')?.textContent || '')"
                f".toLowerCase().startsWith({json.dumps(group.lower())})).querySelectorAll('.seg button')]"
                f".find(b => b.textContent.trim() === {json.dumps(text)})")

    async def seg(self, group: str, text: str, pause: float = 0.65):
        self._label = f"{group} > {text}"
        await self.click_el(self.seg_button(group, text), pause)

    async def speed(self, label: str, pause: float = 0.5):  # "Pausa" | "1×" | "5×" | "20×"
        await self.seg("Velocidad", label, pause)

    async def mode(self, label: str, pause: float = 0.5):  # "Ver" | "Inyectar" | "Incidente"
        await self.seg("Modo", label, pause)

    async def set_select(self, index: int, value: str, pause: float = 0.65):
        """Selecciona `value` en el <select> numero `index` del panel (0 = escenario, 1 = politica).
        El menu nativo no se puede abrir en headless: se mueve el puntero y se fija el valor como lo haria React."""
        el = f"document.querySelectorAll('.controls select')[{index}]"
        x, y, w, h = await self.rect(el)
        await self.click_xy(x + w / 2, y + h / 2, pause, label=f"select {'escenario' if index == 0 else 'politica'} = {value}")
        for _ in range(40):
            ok = await self.cdp.js(f"[...{el}.options].some(o => o.value === {json.dumps(value)})")
            if ok:
                break
            await asyncio.sleep(0.25)
        else:
            raise RuntimeError(f"opcion no disponible en el select {index}: {value}")
        await self.cdp.js(
            f"(() => {{ const s = {el}; const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;"
            f" set.call(s, {json.dumps(value)}); s.dispatchEvent(new Event('change', {{bubbles: true}})); }})()")
        await asyncio.sleep(0.4)

    async def set_cars(self, n: int):
        """Mueve el deslizador de 'Carros' (modo Inyectar) a `n`."""
        el = "document.querySelector('.controls .slider input[type=range]')"
        x, y, w, h = await self.rect(el)
        frac = (n - 1) / 39
        await self.move(x + 8 + frac * (w - 16), y + h / 2, 0.5)
        self.ev(f"deslizador Carros = {n}")
        await self.cdp.js(
            f"(() => {{ const s = {el}; const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
            f" set.call(s, '{n}'); s.dispatchEvent(new Event('input', {{bubbles: true}})); }})()")
        await asyncio.sleep(0.4)

    async def reset_ui(self, scenario: str, policy: dict, warm_to: float = 0):
        """Escenario + politica en los selects y clic en Reiniciar (lo mismo que haria una persona)."""
        cur = (await self.state()).get("scenario")
        if cur != scenario:
            await self.set_select(0, scenario)
        await self.set_select(1, json.dumps({"algo": policy["algo"], "run": policy["run"]}, separators=(",", ":")))
        self._label = "Reiniciar"
        await self.click_el("document.querySelector('.controls .reset')")
        await self.wait_reset(scenario, policy)
        self.ev(f"reset listo ({scenario}, {policy['algo']}): t simulado ~0")
        if cur != scenario:
            self.net = None
            await asyncio.sleep(1.0)  # la pagina pide la red nueva (vista "Todo"; en un cruce aislado, el cruce)
            await self.wait_view()
        if warm_to:
            await self.speed("20×")
            await self.wait_sim(warm_to)

    async def wait_reset(self, scenario: str, policy: dict, timeout: float = 60):
        t0 = time.time()
        await asyncio.sleep(0.5)
        while time.time() - t0 < timeout:
            s = await self.state()
            p = s.get("policy") or {}
            if s.get("scenario") == scenario and p.get("algo") == policy["algo"] and p.get("run") == policy["run"] and s.get("t", 999) < 120:
                return s
            await asyncio.sleep(0.3)
        raise RuntimeError(f"el reset a {scenario} / {policy} no termino")

    # -- mapa
    async def network(self) -> dict:
        if self.net is None:
            sc = (await self.state()).get("scenario")
            self.net = _http_json(f"{self.url}/api/network?scenario={sc}")
        return self.net

    async def canvas_rect(self, which: int = 1):
        return await self.rect(f"document.querySelectorAll('.pane canvas')[{which}]")

    async def view(self) -> dict:
        """Vista compartida real de la pagina: {k, dx, dy, w, h, focus, animating} (window.__view)."""
        v = await self.cdp.js("window.__view ? window.__view() : null")
        if not v:
            raise RuntimeError("la pagina no expone window.__view (frontend viejo?)")
        return v

    async def wait_view(self, timeout: float = 4.0):
        """Espera a que termine la animacion de la vista (Vista, tarjeta, doble clic)."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                v = await self.cdp.js("window.__view ? window.__view() : null")
                if v and not v.get("animating"):
                    return v
            except RuntimeError:
                pass
            await asyncio.sleep(0.1)
        return None

    async def world_to_screen(self, x: float, y: float, which: int = 1) -> tuple[float, float]:
        """Punto del mundo SUMO -> pixel de la pagina, con la camara real del lienzo (0 = fijo, 1 = RL)."""
        key = "fijo" if which == 0 else "rl"
        r = await self.cdp.js(f"window.__maps && window.__maps.{key} ? window.__maps.{key}.worldToPage({x}, {y}) : null")
        if not r:
            raise RuntimeError("la pagina no expone window.__maps")
        return float(r[0]), float(r[1])

    async def lane_point(self, edge: str, frac: float = 0.5) -> tuple[float, float]:
        """Punto (mundo) a una fraccion de la longitud del carril central del borde."""
        net = await self.network()
        lanes = sorted((l for l in net["lanes"] if l["edge"] == edge), key=lambda l: l["id"])
        if not lanes:
            raise ValueError(f"borde no encontrado: {edge}")
        shape = lanes[len(lanes) // 2]["shape"]
        segs = [math.dist(a, b) for a, b in zip(shape, shape[1:])]
        goal, acc = frac * sum(segs), 0.0
        for (a, b), d in zip(zip(shape, shape[1:]), segs):
            if acc + d >= goal:
                u = (goal - acc) / max(d, 1e-9)
                return a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
            acc += d
        return tuple(shape[-1])

    async def click_lane(self, edge: str, frac: float = 0.5, which: int = 1):
        x, y = await self.lane_point(edge, frac)
        sx, sy = await self.world_to_screen(x, y, which)
        await self.click_xy(sx, sy, label=f"carril {edge}")

    async def zoom_at(self, wx: float, wy: float, steps: int, which: int = 1, delay: float = 0.07):
        """Rueda del mouse sobre el punto del mundo (wx, wy): cada paso multiplica el zoom por 1.12 (max 24)."""
        await self.wait_view()
        sx, sy = await self.world_to_screen(wx, wy, which)
        await self.move(sx, sy, 0.6)
        self.ev(f"rueda {steps:+d} pasos en ({wx}, {wy})")
        for _ in range(abs(steps)):
            await self.cdp.send("Input.dispatchMouseEvent", type="mouseWheel", x=sx, y=sy, deltaX=0, deltaY=-100 if steps > 0 else 100)
            await asyncio.sleep(delay)
        self.ev(f"zoom listo (k = {(await self.view())['k']:.2f})")
        await asyncio.sleep(0.3)

    async def pan(self, dx: float, dy: float, which: int = 1, steps: int = 20):
        """Arrastra el mapa (dx, dy) pixeles con el boton izquierdo, en modo Ver."""
        cx, cy, cw, ch = await self.canvas_rect(which)
        x0, y0 = cx + cw / 2, cy + ch / 2
        await self.move(x0, y0, 0.5)
        await self.cdp.send("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0, button="left", buttons=1, clickCount=1)
        for i in range(1, steps + 1):
            x, y = x0 + dx * i / steps, y0 + dy * i / steps
            await self.cdp.js(f"window.__rec.move({x:.1f},{y:.1f})")
            await self.cdp.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="left", buttons=1)
            await asyncio.sleep(0.03)
        await self.cdp.send("Input.dispatchMouseEvent", type="mouseReleased", x=x0 + dx, y=y0 + dy, button="left", buttons=0, clickCount=1)
        self.cursor = (x0 + dx, y0 + dy)
        await asyncio.sleep(0.4)

    async def focus(self, tls: str = "all", pause: float = 0.65):
        """Clic en el boton de Vista de ese semaforo ("C12"...) o en "Todo" ("all"); espera la animacion."""
        self._label = f"Vista > {tls}"
        await self.click_el(f"document.querySelector('.controls [data-focus={json.dumps(tls)}]')", pause)
        await asyncio.sleep(0.1)
        await self.wait_view()
        self.ev(f"vista lista ({tls})")

    async def click_badge(self, tls: str, which: int = 1, pause: float = 0.65):
        """Clic en la tarjeta (o el nombre, en esquematico) del semaforo `tls` dentro del mapa."""
        key = "fijo" if which == 0 else "rl"
        b = await self.cdp.js(f"(window.__maps?.{key}?.badges?.() || []).find(b => b.id === {json.dumps(tls)}) || null")
        if not b:
            raise RuntimeError(f"no hay tarjeta visible para {tls}")
        await self.click_xy(b["x"] + b["w"] / 2, b["y"] + b["h"] / 2, pause, label=f"tarjeta {tls} (mapa {key})")
        await asyncio.sleep(0.1)
        await self.wait_view()
        self.ev(f"vista lista ({tls})")

    async def zoom_reset(self):
        """Vuelve a la vista completa con el boton "Todo" de Vista (animado; la simulacion sigue)."""
        await self.focus("all", 0.4)

    async def hold(self, seconds: float):
        await asyncio.sleep(seconds)


# --------------------------------------------------------------------------- clips
# Cada clip prepara la escena SIN grabar y luego graba con `async with rec(...)`.
# Las posiciones de clic usan la geometria real de /api/network.
CLIPS: dict[str, tuple[str, callable]] = {}


def clip(name: str, desc: str):
    def deco(fn):
        CLIPS[name] = (desc, fn)
        return fn
    return deco


@clip("a_mappo", "Reforma hora pico: tiempo fijo vs MAPPO (Reiniciar en la UI, 5x y 20x)")
async def clip_a(d: Demo, rec):
    await d.reset_ui("reforma_pico", POL["max_pressure"], warm_to=30)
    await d.speed("5×")
    async with rec("a_mappo"):
        await d.hold(1.5)
        await d.reset_ui("reforma_pico", POL["mappo"])
        await d.speed("5×")
        await d.hold(14)
        await d.speed("20×")
        await d.move(1772, 880, 0.4)  # puntero fuera del mapa y de las tarjetas (abajo del panel)
        await d.hold(34)


@clip("b_inyectar", "Inyectar 40 carros en la entrada sur (NB_S_C15) y, con Vista 12, en la 12 calle (C12_W_in)")
async def clip_b(d: Demo, rec):
    await d.reset_ui("reforma_pico", POL["mappo"], warm_to=240)
    await d.speed("5×")
    async with rec("b_inyectar"):
        await d.hold(1.0)
        await d.zoom_at(100, 60, 9)  # rueda sobre la entrada sur: entrada, 15 y 14 calle de cerca
        await d.mode("Inyectar")
        await d.set_cars(40)
        await d.click_lane("NB_S_C15", 0.45)
        await d.hold(8)
        await d.focus("C12")  # boton "12" de Vista: los dos mapas viajan a la 12 calle
        await d.hold(0.8)
        await d.click_lane("C12_W_in", 0.8)  # 12 calle (entrada oeste), cerca del cruce para que se vea
        await d.hold(20)
        await d.mode("Ver")
        await d.hold(2)
    await d.zoom_reset()


@clip("c_hora", "Hora del dia: pico -> mediodia -> noche (y regreso a pico)")
async def clip_c(d: Demo, rec):
    await d.reset_ui("reforma_pico", POL["mappo"], warm_to=300)
    await d.speed("20×")
    async with rec("c_hora"):
        await d.hold(2)
        await d.seg("Hora", "Mediodía")
        await d.hold(14)
        await d.seg("Hora", "Noche")
        await d.hold(14)
        await d.seg("Hora", "Pico")
        await d.hold(8)


@clip("d_incidente", "Incidente en Reforma norte entre 12 y 10a calle (zoom al tramo), activar y retirar")
async def clip_d(d: Demo, rec):
    await d.reset_ui("reforma_pico", POL["mappo"], warm_to=240)
    await d.speed("5×")
    async with rec("d_incidente"):
        await d.hold(1.0)
        await d.zoom_at(225, 720, 12)  # tramo 12-10a con zoom ~4: a partir de 2.4 px/m se dibujan barrera y conos
        await d.hold(1.0)
        await d.mode("Incidente")
        await d.click_lane("NB_C12_C10", 0.55)
        await d.hold(3)
        await d.speed("20×")
        await d.hold(22)
        await d.speed("5×")
        await d.click_lane("NB_C12_C10", 0.55)
        await d.hold(3)
        await d.speed("20×")
        await d.hold(12)
        await d.mode("Ver")
        await d.hold(1)
    await d.zoom_reset()


@clip("e_comm", "Reforma hora pico: tiempo fijo vs agentes con comunicacion (comm)")
async def clip_e(d: Demo, rec):
    await d.speed("5×")
    async with rec("e_comm"):
        await d.hold(1.0)
        await d.reset_ui("reforma_pico", POL["comm"])
        await d.speed("20×")
        await d.hold(36)


@clip("f_maxpressure", "Reforma hora pico: tiempo fijo vs max-pressure (linea base fuerte)")
async def clip_f(d: Demo, rec):
    await d.speed("5×")
    async with rec("f_maxpressure"):
        await d.hold(1.0)
        await d.reset_ui("reforma_pico", POL["max_pressure"])
        await d.speed("20×")
        await d.hold(36)


@clip("g_cruce", "Cruce aislado Reforma y 12 calle: tiempo fijo vs DQN y luego vs PPO")
async def clip_g(d: Demo, rec):
    await d.speed("5×")
    async with rec("g_cruce"):
        await d.hold(1.0)
        await d.reset_ui("cruce_pico", POL["dqn"])
        await d.speed("20×")
        await d.hold(24)
        await d.reset_ui("cruce_pico", POL["ppo"])
        await d.speed("20×")
        await d.hold(22)


@clip("h_velocidad", "Control de velocidad: pausa, 1x con zoom a un cruce, 5x y 20x")
async def clip_h(d: Demo, rec):
    await d.reset_ui("reforma_pico", POL["mappo"], warm_to=200)
    await d.speed("5×")
    async with rec("h_velocidad"):
        await d.hold(1.0)
        await d.speed("Pausa")
        await d.hold(2.0)
        await d.focus("C12")  # boton "12" de Vista (animado) y luego la rueda para ver semaforos y carros de cerca
        await d.hold(0.8)
        await d.zoom_at(207, 653, 5)
        await d.hold(1.0)
        await d.speed("1×")
        await d.hold(9)
        await d.speed("5×")
        await d.hold(6)
        await d.speed("20×")
        await d.hold(7)
    await d.zoom_reset()


@clip("i_qmix", "Reforma hora pico: tiempo fijo vs QMIX")
async def clip_i(d: Demo, rec):
    await d.speed("5×")
    async with rec("i_qmix"):
        await d.hold(1.0)
        await d.reset_ui("reforma_pico", POL["qmix"])
        await d.speed("20×")
        await d.hold(30)


@clip("j_mapa", "Mapa: boton de Vista a la 12 calle, clic en la tarjeta de la 10a, noche y estilo esquematico")
async def clip_j(d: Demo, rec):
    await d.reset_ui("reforma_pico", POL["mappo"], warm_to=240)
    await d.speed("1×")
    async with rec("j_mapa"):
        await d.hold(1.5)
        await d.focus("C12")  # boton "12" de Vista: los dos mapas se acercan juntos
        await d.move(1772, 880, 0.4)  # puntero fuera del mapa: se ven las luces, el contador y el destello
        await d.hold(8)
        try:
            await d.click_badge("C10")  # tarjeta del semaforo de la 10a calle dentro del mapa RL
        except RuntimeError:
            await d.focus("C10")
        await d.hold(5)
        await d.seg("Iluminación", "Noche")  # a 1x: faros, alumbrado y semaforos de noche
        await d.hold(7)
        await d.seg("Estilo", "Esquemático")
        await d.hold(5)
        await d.seg("Estilo", "Realista")
        await d.hold(0.6)
        await d.seg("Iluminación", "Día")
        await d.hold(0.6)
        await d.focus("all")
        await d.hold(3)


ORDER = ["a_mappo", "b_inyectar", "c_hora", "d_incidente", "e_comm", "f_maxpressure", "i_qmix", "h_velocidad", "g_cruce", "j_mapa"]


async def run(args):
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    async with chrome(args.port, headless=not args.headed) as cdp:
        demo = Demo(cdp, args.url)
        await demo.open()
        if args.screenshot:
            await asyncio.sleep(2)
            r = await cdp.send("Page.captureScreenshot", format="png")
            Path(args.screenshot).write_bytes(base64.b64decode(r["data"]))
            print("captura:", args.screenshot)
            return
        rec_ = Recorder(cdp, out, keep_frames=args.keep_frames)
        last_events: dict[str, dict] = {}

        @contextlib.asynccontextmanager
        async def rec(name):
            print(f"[grabando] {name}", flush=True)
            await rec_.start(name)
            demo.events = []
            try:
                yield
            finally:
                await rec_.stop(name)
                t0 = rec_.frames[0][1]
                last_events[name] = {"duration_s": round(rec_._t_end - t0, 2),
                                     "events": [[round(t - t0, 2), e] for t, e in demo.events if t >= t0 - 1]}

        names = args.clips.split(",") if args.clips else ORDER
        for n in names:
            if n not in CLIPS:
                raise SystemExit(f"clip desconocido: {n} (usa --list)")
        log_file = out / "clips_log.json"
        try:  # se conserva lo de corridas anteriores (un registro por clip)
            log = [e for e in json.loads(log_file.read_text()) if e.get("clip") not in names]
        except (OSError, ValueError):
            log = []
        for n in names:
            t0 = time.time()
            st0 = await demo.state()
            await CLIPS[n][1](demo, rec)
            st1 = await demo.state()
            m = {k: st1["sims"][k]["metrics"] for k in ("fijo", "rl")}
            log.append({"clip": n, "desc": CLIPS[n][0], "seconds": round(time.time() - t0, 1),
                        "end_t": st1.get("t"), "policy": st1.get("policy"), "improvement_pct": st1.get("improvement_pct"),
                        "metrics_end": m, "start_t": st0.get("t"), **last_events.get(n, {})})
            print(f"   fin {n}: t={st1.get('t')} mejora={st1.get('improvement_pct')} pol={st1['policy']['label']}", flush=True)
            log_file.write_text(json.dumps(sorted(log, key=lambda e: ORDER.index(e["clip"])), indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--out", default="../video/clips", help="carpeta de salida (fuera del repo)")
    ap.add_argument("--clips", default="", help="lista separada por comas (por defecto, todos en orden)")
    ap.add_argument("--list", action="store_true", help="lista los clips y sale")
    ap.add_argument("--screenshot", default="", help="solo guarda una captura PNG de la pagina")
    ap.add_argument("--keep-frames", action="store_true", help="no borra los JPEG tras codificar")
    ap.add_argument("--headed", action="store_true", help="Chrome con ventana (para depurar)")
    ap.add_argument("--port", type=int, default=9333, help="puerto de depuracion remota de Chrome")
    args = ap.parse_args()
    if args.list:
        for n in ORDER:
            print(f"{n:15s} {CLIPS[n][0]}")
        return
    asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
