import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import type { Feed, Network, SimKey, TickMessage, Vehicle } from "./types";
import { chooseRotation, makeCamera, toScreen, type Camera, type View } from "./render/camera";
import { buildRoadModel, drawCompass, drawIncidents, drawRoad, drawStreetLabels } from "./render/road";
import { CarRenderer, speedColor, type CarDraw } from "./render/cars";
import { buildSignalModel, drawBadges, drawFlashes, drawHeads, drawStopBars, SignalTracker, type BadgeHit } from "./render/signals";
import { buildSchematicModel, drawSchematic } from "./render/schematic";
import { DAY, palette } from "./render/theme";

export type { View } from "./render/camera";
export type Mode = "ver" | "inyectar" | "incidente";
export type MapStyle = "realista" | "esquematico";

interface Props {
  title: string;
  accent: string;
  simKey: SimKey;
  net: Network;
  feed: MutableRefObject<Feed>;
  closed: Set<string>;
  mode: Mode;
  view: View;
  style: MapStyle;
  night: number; // objetivo: 0 dia, 1 noche (el lienzo se acerca suave)
  onView: (v: View) => void; // el usuario movio la vista (arrastre o rueda)
  onLane: (edge: string) => void;
  onBadge?: (tlsId: string) => void; // clic en la tarjeta (o el nombre) de un semaforo
  onZoomAt?: (x: number, y: number) => void; // doble clic en (x, y) px del lienzo
  onSize?: (w: number, h: number) => void; // tamano del lienzo en px CSS
}

// Para depurar y para scripts/record_demo.py y scripts/ui_snapshot.py.
declare global {
  interface Window {
    __maps?: Record<string, {
      cam: () => Camera | null;
      worldToPage: (x: number, y: number) => [number, number];
      badges: () => BadgeHit[]; // tarjetas clicables de los semaforos, en px de la pagina
    }>;
    __net?: Network; // red actual
    __setView?: (x: number, y: number, k: number) => void; // centra (x, y) del mundo con zoom k (ambos mapas)
    __focus?: (id: string) => boolean; // anima la vista a un semaforo (id) o a toda la red ("all")
    __view?: () => View & { w: number; h: number; focus: string | null; animating: boolean };
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

// Leyenda compacta del encabezado (colores tomados de la paleta de dia y de speedColor).
function Legend({ style }: { style: MapStyle }) {
  if (style === "esquematico") {
    return (
      <span className="pane-legend">
        <span className="lg"><i style={{ background: speedColor(13.9) }} />libre</span>
        <span className="lg"><i style={{ background: speedColor(6.5) }} />lento</span>
        <span className="lg"><i style={{ background: speedColor(0) }} />detenido</span>
      </span>
    );
  }
  return (
    <span className="pane-legend">
      <span className="lg lamps" title="Semáforo: verde, amarillo, rojo">
        <span className="housing"><i style={{ background: DAY.green }} /><i style={{ background: DAY.yellow }} /><i style={{ background: DAY.red }} /></span>semáforo
      </span>
      <span className="lg" title="Luces de freno: el carro frena o está detenido">
        <i className="brake" style={{ background: DAY.brake, color: DAY.brake }} />frenando
      </span>
    </span>
  );
}

export default function NetCanvas(p: Props) {
  const { title, accent, simKey, net, feed, closed, mode, view, style, onView, onLane } = p;
  const ref = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 600, h: 400 });
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const cache = useRef<Interp>({ src: null, map: new Map() });
  const draw = useRef<() => void>(() => {});
  const camRef = useRef<Camera | null>(null);
  const badges = useRef<BadgeHit[]>([]);
  const night = useRef(p.night); // 0..1, se acerca suave al objetivo
  const lastMsg = useRef<TickMessage | null>(null);
  const errs = useRef(new Set<string>());
  const vref = useRef(view); // ultima vista (los eventos seguidos de la rueda no esperan al render)
  vref.current = view;

  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setSize({ w: Math.round(e.contentRect.width), h: Math.round(e.contentRect.height) }));
    ro.observe(wrap.current!);
    return () => ro.disconnect();
  }, []);
  const { onSize } = p;
  useEffect(() => { onSize?.(size.w, size.h); }, [size.w, size.h, onSize]);

  const roadModel = useMemo(() => buildRoadModel(net), [net]);
  const sigModel = useMemo(() => buildSignalModel(net), [net]);
  const schModel = useMemo(() => buildSchematicModel(net), [net]);
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
      badges: () => {
        const r = ref.current!.getBoundingClientRect();
        return badges.current.map((b) => ({ ...b, x: r.left + b.x, y: r.top + b.y }));
      },
    };
    return () => { delete window.__maps?.[simKey]; };
  }, [simKey]);

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
    const target = p.night;
    night.current += (target - night.current) * 0.06;
    if (Math.abs(target - night.current) < 0.01) night.current = target;
    const pal = palette(night.current);
    const closedLanes = new Set(msg?.closed_lanes ?? []);
    const list = interpolated(feed.current, simKey, cache.current);

    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, size.w, size.h);
    if (style === "esquematico") {
      safe("schematic", () => {
        badges.current = drawSchematic(g, cam, dpr, schModel, pal, { states: sim?.tls, cars: list, closedLanes, closedEdges: closed });
      });
    } else {
      const roadOpts = { night: night.current, closedLanes, closedEdges: closed, time: now };
      const sigOpts = { night: night.current, accent, side: simKey, now, simT: msg?.t ?? 0 };
      const carOpts = { night: night.current, colorBySpeed: false };
      safe("road", () => drawRoad(g, cam, dpr, roadModel, pal, roadOpts));
      safe("incidents", () => drawIncidents(g, cam, dpr, roadModel, pal, roadOpts));
      safe("stopbars", () => drawStopBars(g, cam, dpr, sigModel, sim?.tls, pal, night.current));
      if (night.current > 0.02) safe("headlights", () => cars.drawHeadlights(g, cam, dpr, list, pal, carOpts));
      safe("cars", () => cars.draw(g, cam, dpr, list, pal, carOpts));
      safe("heads", () => drawHeads(g, cam, dpr, sigModel, sim?.tls, pal, sigOpts));
      safe("flashes", () => drawFlashes(g, cam, dpr, sigModel, tracker, sigOpts));
      safe("labels", () => drawStreetLabels(g, cam, dpr, roadModel, pal, badges.current)); // tarjetas del cuadro anterior
      safe("badges", () => { badges.current = drawBadges(g, cam, dpr, sigModel, tracker, pal, sigOpts) ?? []; });
    }
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

  const badgeAt = (x: number, y: number): string | null => {
    const b = badges.current.find((b) => x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h);
    return b ? b.id : null;
  };

  const rel = (e: React.PointerEvent | React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top] as const;
  };

  const emit = (v: View) => { vref.current = v; onView(v); };

  return (
    <section className="pane" style={{ ["--accent" as string]: accent }}>
      <h2><span className="dot" /><span className="pane-title">{title}</span><Legend style={style} /></h2>
      <div className={`canvas-wrap mode-${mode}`} ref={wrap}>
        <canvas
          ref={ref}
          style={{ width: size.w, height: size.h }}
          onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, moved: false }; (e.target as Element).setPointerCapture(e.pointerId); }}
          onPointerMove={(e) => {
            const d = drag.current;
            if (!d) { // sin arrastre: mano sobre las tarjetas de los semaforos
              const [x, y] = rel(e);
              ref.current!.style.cursor = badgeAt(x, y) ? "pointer" : "";
              return;
            }
            const mx = e.clientX - d.x, my = e.clientY - d.y;
            if (Math.abs(mx) + Math.abs(my) > 4) d.moved = true;
            if (d.moved) { const v = vref.current; emit({ ...v, dx: v.dx + mx, dy: v.dy + my }); d.x = e.clientX; d.y = e.clientY; }
          }}
          onPointerUp={(e) => {
            const d = drag.current; drag.current = null;
            if (!d || d.moved) return;
            const [x, y] = rel(e);
            const id = badgeAt(x, y);
            if (id) { p.onBadge?.(id); return; }
            if (mode !== "ver") { const edge = edgeAt(x, y); if (edge) onLane(edge); }
          }}
          onPointerCancel={() => { drag.current = null; }}
          onDoubleClick={(e) => {
            const [x, y] = rel(e);
            if (mode === "ver" && !badgeAt(x, y)) p.onZoomAt?.(x, y);
          }}
          onWheel={(e) => {
            const v = vref.current;
            const f = e.deltaY < 0 ? 1.12 : 1 / 1.12;
            const k = Math.max(0.5, Math.min(24, v.k * f));
            const [mx, my] = rel(e); const cx = size.w / 2, cy = size.h / 2, r = k / v.k;
            // zoom centrado en el cursor
            emit({ k, dx: mx - cx - (mx - cx - v.dx) * r, dy: my - cy - (my - cy - v.dy) * r });
          }}
        />
      </div>
    </section>
  );
}
