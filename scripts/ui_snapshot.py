#!/usr/bin/env python
"""Capturas PNG de la demo web para revisar el dibujo del mapa (Chrome headless + CDP).

Reutiliza el cliente CDP de scripts/record_demo.py. Antes de capturar puede mandar comandos al
backend por WebSocket (reiniciar, hora del dia, incidente...), calentar la simulacion a 20x hasta
un tiempo simulado y ejecutar JavaScript en la pagina (p. ej. hacer zoom). Imprime los errores de
la consola y las excepciones de la pagina, para detectar fallas del render.

    source scripts/env.sh
    python scripts/ui_snapshot.py --out /tmp/a.png                                   # vista por defecto
    python scripts/ui_snapshot.py --out /tmp/b.png --warm 600 --query night=1
    python scripts/ui_snapshot.py --out /tmp/c.png --cmd '{"cmd":"incident","edge":"NB_C12_C10","on":true}'
    python scripts/ui_snapshot.py --out /tmp/d.png --js "window.__maps && 1" --zoom C12:6
    python scripts/ui_snapshot.py --out /tmp/e.png --size 390x844 --dpr 2              # telefono
    python scripts/ui_snapshot.py --url http://localhost:5181 --api http://localhost:8001 --out /tmp/f.png

--zoom TLS:K (o x,y:K) centra el punto con zoom K usando la camara expuesta en window.__maps
(mismo desplazamiento en ambos mapas, como el zoom compartido de la UI).
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import socket
import sys
import time
import urllib.request
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_demo import chrome  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _state(api: str) -> dict:
    with urllib.request.urlopen(f"{api}/api/state", timeout=5) as r:
        return json.loads(r.read().decode())


async def _ws_cmds(api: str, cmds: list[dict]) -> None:
    url = api.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    async with websockets.connect(url, max_size=None) as ws:
        for c in cmds:
            await ws.send(json.dumps(c))
            t0 = time.time()
            while time.time() - t0 < 90:  # espera el ack de este comando (los estados se ignoran)
                m = json.loads(await asyncio.wait_for(ws.recv(), 90))
                if m.get("type") == "ack" and m.get("cmd") == c.get("cmd"):
                    print(f"cmd {c} -> ok={m.get('ok')} {m.get('error') or ''}".rstrip())
                    break
            if c.get("cmd") == "reset":  # el reinicio carga SUMO: esperar a que vuelva a correr
                for _ in range(120):
                    try:
                        if _state(api).get("t") is not None:
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)


async def _warm(api: str, t_goal: float) -> None:
    await _ws_cmds(api, [{"cmd": "speed", "value": 20}])
    t0 = time.time()
    while time.time() - t0 < 600:
        try:
            if _state(api).get("t", 0) >= t_goal:
                break
        except Exception:
            pass
        await asyncio.sleep(0.5)
    await _ws_cmds(api, [{"cmd": "speed", "value": 1}])


ZOOM_JS = r"""
((tid, wx, wy, k) => {
  const m = window.__maps; if (!m) return 'sin window.__maps';
  if (window.__setView) {
    const net = window.__net;
    let x = wx, y = wy;
    if (tid && net) { const t = net.tls.find(t => t.id === tid); if (!t) return 'TLS no encontrado'; x = t.x; y = t.y; }
    window.__setView(x, y, k);
    return 'ok';
  }
  return 'sin window.__setView';
})(%s, %s, %s, %s)
"""


async def run(a) -> int:
    api = (a.api or a.url).rstrip("/")
    cmds = [json.loads(c) for c in a.cmd]
    if cmds:
        await _ws_cmds(api, cmds)
    if a.warm:
        await _warm(api, a.warm)
    w, h = (int(v) for v in a.size.lower().split("x"))
    errors: list[str] = []
    async with chrome(_free_port()) as cdp:
        def on_console(p):
            if p.get("type") in ("error", "assert"):
                errors.append("console: " + " ".join(str(x.get("value", x.get("description", ""))) for x in p.get("args", [])))

        def on_exc(p):
            d = p.get("exceptionDetails", {})
            errors.append("exception: " + (d.get("exception", {}).get("description") or d.get("text", "")))

        cdp.on("Runtime.consoleAPICalled", on_console)
        cdp.on("Runtime.exceptionThrown", on_exc)
        await cdp.send("Page.enable")
        await cdp.send("Runtime.enable")
        await cdp.send("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=a.dpr, mobile=w < 768)
        url = a.url.rstrip("/") + "/" + (("?" + a.query) if a.query else "")
        await cdp.send("Page.navigate", url=url)
        t0 = time.time()
        while time.time() - t0 < 40:  # en vivo: hay lienzo y KPIs con numeros
            try:
                if await cdp.js("!!document.querySelector('canvas') && /\\d/.test(document.querySelector('.kpi-vals')?.textContent || '')"):
                    break
            except RuntimeError:
                pass
            await asyncio.sleep(0.3)
        for z in a.zoom:
            target, k = z.rsplit(":", 1)
            if "," in target:
                x, y = target.split(",")
                expr = ZOOM_JS % ("null", float(x), float(y), float(k))
            else:
                expr = ZOOM_JS % (json.dumps(target), 0, 0, float(k))
            print("zoom", z, "->", await cdp.js(expr))
        for js in a.js:
            print("js", js[:60], "->", await cdp.js(js))
        await asyncio.sleep(a.wait)
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        for i in range(a.shots):
            r = await cdp.send("Page.captureScreenshot", format="png")
            p = out if a.shots == 1 else out.with_name(f"{out.stem}_{i + 1}{out.suffix}")
            p.write_bytes(base64.b64decode(r["data"]))
            print("captura:", p)
            if i + 1 < a.shots:
                await asyncio.sleep(a.every)
    for e in errors[:20]:
        print("ERROR PAGINA:", e[:400])
    return 1 if errors and a.strict else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000", help="pagina (backend o servidor de vite)")
    ap.add_argument("--api", default="", help="backend para comandos/estado (por defecto --url)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--query", default="", help="parametros de la URL, p. ej. night=1&style=esquematico")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--dpr", type=float, default=1.0)
    ap.add_argument("--cmd", action="append", default=[], help="comando JSON por WebSocket antes de capturar (repetible)")
    ap.add_argument("--warm", type=float, default=0, help="corre a 20x hasta este tiempo simulado (s) y vuelve a 1x")
    ap.add_argument("--zoom", action="append", default=[], help="TLS:K o x,y:K (usa window.__setView)")
    ap.add_argument("--js", action="append", default=[], help="JavaScript a evaluar antes de capturar (repetible)")
    ap.add_argument("--wait", type=float, default=2.5, help="segundos de espera antes de capturar")
    ap.add_argument("--shots", type=int, default=1)
    ap.add_argument("--every", type=float, default=1.0)
    ap.add_argument("--strict", action="store_true", help="sale con 1 si la pagina tuvo errores")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
