import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import type { Feed, Network, SimKey, TickMessage, Vehicle } from "./types";
import { chooseRotation, makeCamera, toScreen, viewFor, type Camera, type View } from "./render/camera";
import { buildRoadModel, drawCompass, drawIncidents, drawRoad, drawStreetLabels } from "./render/road";
import { CarRenderer, type CarDraw } from "./render/cars";
import { buildSignalModel, drawBadges, drawFlashes, drawHeads, drawStopBars, SignalTracker, type BadgeHit } from "./render/signals";
import { palette } from "./render/theme";

export type { View } from "./render/camera";
export type Mode = "ver" | "inyectar" | "incidente";

interface Props {
  title: string;
  accent: string;
  simKey: SimKey;
  net: Network;
  feed: MutableRefObject<Feed>;
  closed: Set<string>;
  mode: Mode;
  view: View;
  onView: (v: View) => void;
  onLane: (edge: string) => void;
}

// Para depurar y para scripts/record_demo.py: camara y conversion mundo -> pagina de cada lienzo.
declare global {
  interface Window {
    __maps?: Record<string, { cam: () => Camera | null; worldToPage: (x: number, y: number) => [number, number] }>;
    __net?: Network; // red actual
    __setView?: (x: number, y: number, k: number) => void; // centra (x, y) del mundo con zoom k (ambos mapas)
  }
}

function lerpAngle(a: number, b: number, f: number): number {
  const d = ((b - a + 540) % 360) - 180;
  return a + d * f;
}

interface Interp { src: TickMessage | null; map: Map<string, Vehicle>; }

// Posicion de cada vehiculo interpolada entre los dos ultimos mensajes (se dibuja con ~1 mensaje de retraso).
// braking: detenido o perdio velocidad desde el mensaje anterior.
function interpolated(feed: Feed, key: SimKey, cache: Interp): CarDraw[] {
  const cur = feed.cur?.sims[key]?.vehicles ?? [];
  const prevMsg = feed.prev;
  const plain = (v: Vehicle, p?: Vehicle): CarDraw =>
    ({ id: v[0], x: v[1], y: v[2], angle: v[3], speed: v[4], braking: v[4] < 0.5 || (!!p && p[4] - v[4] > 0.6) });
  if (!prevMsg || !feed.cur || feed.cur.t <= prevMsg.t || feed.cur.t - prevMsg.t > 30) return cur.map((v) => plain(v));
  if (cache.src !== prevMsg) {
    cache.src = prevMsg;
    cache.map = new Map((prevMsg.sims[key]?.vehicles ?? []).map((v) => [v[0], v]));
  }
  const span = Math.max(1, feed.tCur - feed.tPrev);
  const f = Math.max(0, Math.min(1, (performance.now() - feed.tCur) / span));
  return cur.map((v) => {
    const p = cache.map.get(v[0]);
    if (!p || f >= 1 || Math.hypot(v[1] - p[1], v[2] - p[2]) > 60) return plain(v, p);
    return {
      id: v[0], x: p[1] + (v[1] - p[1]) * f, y: p[2] + (v[2] - p[2]) * f, angle: lerpAngle(p[3], v[3], f),
      speed: v[4], braking: v[4] < 0.5 || p[4] - v[4] > 0.6,
    };
  });
}

// Modo noche: automatico con el perfil "noche"; ?night=1 / ?night=0 en la URL lo fuerza.
const NIGHT_PARAM = new URLSearchParams(window.location.search).get("night");

export default function NetCanvas({ title, accent, simKey, net, feed, closed, mode, view, onView, onLane }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 600, h: 400 });
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const cache = useRef<Interp>({ src: null, map: new Map() });
  const draw = useRef<() => void>(() => {});
  const camRef = useRef<Camera | null>(null);
  const badges = useRef<BadgeHit[]>([]);
  const night = useRef(0); // 0..1, se acerca suave al objetivo
  const lastMsg = useRef<TickMessage | null>(null);
  const errs = useRef(new Set<string>());

  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(wrap.current!);
    return () => ro.disconnect();
  }, []);

  const roadModel = useMemo(() => buildRoadModel(net), [net]);
  const sigModel = useMemo(() => buildSignalModel(net), [net]);
  const tracker = useMemo(() => new SignalTracker(sigModel), [sigModel]);
  const cars = useMemo(() => new CarRenderer(), []);
  const rot = useMemo(() => chooseRotation(net, size.w, size.h), [net, size]);
  const cam = useMemo(() => makeCamera(net, size.w, size.h, view, rot), [net, size, view, rot]);

  useEffect(() => {
    window.__maps = window.__maps ?? {};
    window.__maps[simKey] = {
      cam: () => camRef.current,
      worldToPage: (x, y) => {
        const r = ref.current!.getBoundingClientRect();
        const [sx, sy] = toScreen(camRef.current!, x, y);
        return [r.left + sx, r.top + sy];
      },
    };
    return () => { delete window.__maps?.[simKey]; };
  }, [simKey]);

  useEffect(() => {
    if (simKey !== "fijo") return; // la vista es compartida: basta con un lienzo
    window.__net = net;
    window.__setView = (x, y, k) => onView(viewFor(net, size.w, size.h, rot, x, y, k));
  });

  // Cada paso se aisla: si un modulo falla, el resto del mapa se sigue dibujando (el error se loguea una vez).
  const safe = (name: string, fn: () => void) => {
    try { fn(); } catch (e) {
      if (!errs.current.has(name)) { errs.current.add(name); console.error(`[render] ${name}:`, e); }
    }
  };

  // Se redefine en cada render (usa la red, el zoom y los cierres actuales); el bucle rAF la llama ~60 veces/s.
  draw.current = () => {
    const cv = ref.current;
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(size.w * dpr) || cv.height !== Math.round(size.h * dpr)) {
      cv.width = Math.round(size.w * dpr); cv.height = Math.round(size.h * dpr);
    }
    const g = cv.getContext("2d")!;
    camRef.current = cam;
    const now = performance.now();
    const msg = feed.current.cur;
    const sim = msg?.sims[simKey];
    if (msg && msg !== lastMsg.current) {
      lastMsg.current = msg;
      safe("tracker", () => tracker.update(msg.t, sim?.tls, now));
    }
    const target = NIGHT_PARAM === "1" ? 1 : NIGHT_PARAM === "0" ? 0 : msg?.profile === "noche" ? 1 : 0;
    night.current += (target - night.current) * 0.06;
    if (Math.abs(target - night.current) < 0.01) night.current = target;
    const pal = palette(night.current);
    const closedLanes = new Set(msg?.closed_lanes ?? []);
    const roadOpts = { night: night.current, closedLanes, closedEdges: closed, time: now };
    const sigOpts = { night: night.current, accent, side: simKey, now, simT: msg?.t ?? 0 };
    const carOpts = { night: night.current, colorBySpeed: false };

    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, size.w, size.h);
    safe("road", () => drawRoad(g, cam, dpr, roadModel, pal, roadOpts));
    safe("incidents", () => drawIncidents(g, cam, dpr, roadModel, pal, roadOpts));
    safe("stopbars", () => drawStopBars(g, cam, dpr, sigModel, sim?.tls, pal));
    const list = interpolated(feed.current, simKey, cache.current);
    if (night.current > 0.02) safe("headlights", () => cars.drawHeadlights(g, cam, dpr, list, pal, carOpts));
    safe("cars", () => cars.draw(g, cam, dpr, list, pal, carOpts));
    safe("heads", () => drawHeads(g, cam, dpr, sigModel, sim?.tls, pal, sigOpts));
    safe("flashes", () => drawFlashes(g, cam, dpr, sigModel, tracker, sigOpts));
    safe("labels", () => drawStreetLabels(g, cam, dpr, roadModel, pal));
    safe("badges", () => { badges.current = drawBadges(g, cam, dpr, sigModel, tracker, pal, sigOpts); });
    safe("compass", () => drawCompass(g, cam, dpr, pal, size.w - 30, 30));
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
  };

  useEffect(() => {
    let raf = 0;
    const loop = () => { draw.current(); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const edgeAt = (ex: number, ey: number): string | null => {
    let best: string | null = null, bd = Math.max(10, 4 * cam.s);
    for (const l of net.lanes) {
      for (let i = 1; i < l.shape.length; i++) {
        const [ax, ay] = toScreen(cam, l.shape[i - 1][0], l.shape[i - 1][1]);
        const [bx, by] = toScreen(cam, l.shape[i][0], l.shape[i][1]);
        const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy || 1;
        const u = Math.max(0, Math.min(1, ((ex - ax) * dx + (ey - ay) * dy) / L2));
        const d = Math.hypot(ex - (ax + u * dx), ey - (ay + u * dy));
        if (d < bd) { bd = d; best = l.edge; }
      }
    }
    return best;
  };

  const rel = (e: React.PointerEvent | React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top] as const;
  };

  return (
    <section className="pane" style={{ ["--accent" as string]: accent }}>
      <h2><span className="dot" />{title}</h2>
      <div className={`canvas-wrap mode-${mode}`} ref={wrap}>
        <canvas
          ref={ref}
          style={{ width: size.w, height: size.h }}
          onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, moved: false }; (e.target as Element).setPointerCapture(e.pointerId); }}
          onPointerMove={(e) => {
            const d = drag.current; if (!d) return;
            const mx = e.clientX - d.x, my = e.clientY - d.y;
            if (Math.abs(mx) + Math.abs(my) > 4) d.moved = true;
            if (d.moved) { onView({ ...view, dx: view.dx + mx, dy: view.dy + my }); d.x = e.clientX; d.y = e.clientY; }
          }}
          onPointerUp={(e) => {
            const d = drag.current; drag.current = null;
            if (d && !d.moved && mode !== "ver") {
              const [x, y] = rel(e); const edge = edgeAt(x, y);
              if (edge) onLane(edge);
            }
          }}
          onWheel={(e) => {
            const f = e.deltaY < 0 ? 1.12 : 1 / 1.12;
            const k = Math.max(0.5, Math.min(24, view.k * f));
            const [mx, my] = rel(e); const cx = size.w / 2, cy = size.h / 2, r = k / view.k;
            // zoom centrado en el cursor
            onView({ k, dx: mx - cx - (mx - cx - view.dx) * r, dy: my - cy - (my - cy - view.dy) * r });
          }}
        />
        <div className="legend"><i className="r" />luces de freno = frenando o detenido</div>
      </div>
    </section>
  );
}
