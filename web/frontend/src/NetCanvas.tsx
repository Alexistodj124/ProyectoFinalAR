import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import type { Feed, Network, SimKey, TickMessage, Vehicle } from "./types";

export interface View { k: number; dx: number; dy: number; } // zoom relativo y desplazamiento (px)
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

const PAD = 24;

// Color por velocidad: rojo (parado) -> amarillo -> verde (flujo libre, ~14 m/s)
function speedColor(v: number): string {
  const f = Math.max(0, Math.min(1, v / 13.9));
  return `hsl(${Math.round(f * 125)} 85% 55%)`;
}
const GREEN = "#22e07a", YELLOW = "#ffd23f", RED = "#ff4d4d";

// Estado de un carril controlado: verde si algun enlace esta en verde, si no amarillo, si no rojo.
function laneSignal(st: string, idx: number[]): string {
  let y = false;
  for (const i of idx) {
    const c = st[i];
    if (c === "G" || c === "g") return GREEN;
    if (c === "y" || c === "Y") y = true;
  }
  return y ? YELLOW : RED;
}

function lerpAngle(a: number, b: number, f: number): number {
  const d = ((b - a + 540) % 360) - 180;
  return a + d * f;
}

// Posicion de cada vehiculo interpolada entre los dos ultimos mensajes (se dibuja con ~1 mensaje de retraso).
function interpolated(feed: Feed, key: SimKey, cache: { src: TickMessage | null; map: Map<string, Vehicle> }): Vehicle[] {
  const cur = feed.cur?.sims[key]?.vehicles ?? [];
  const prevMsg = feed.prev;
  if (!prevMsg || !feed.cur || feed.cur.t <= prevMsg.t || feed.cur.t - prevMsg.t > 30) return cur;
  if (cache.src !== prevMsg) {
    cache.src = prevMsg;
    cache.map = new Map((prevMsg.sims[key]?.vehicles ?? []).map((v) => [v[0], v]));
  }
  const span = Math.max(1, feed.tCur - feed.tPrev);
  const f = Math.max(0, Math.min(1, (performance.now() - feed.tCur) / span));
  if (f >= 1) return cur;
  return cur.map((v) => {
    const p = cache.map.get(v[0]);
    if (!p || Math.hypot(v[1] - p[1], v[2] - p[2]) > 60) return v;
    return [v[0], p[1] + (v[1] - p[1]) * f, p[2] + (v[2] - p[2]) * f, lerpAngle(p[3], v[3], f), v[4]] as Vehicle;
  });
}

export default function NetCanvas({ title, accent, simKey, net, feed, closed, mode, view, onView, onLane }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 600, h: 400 });
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const cache = useRef<{ src: TickMessage | null; map: Map<string, Vehicle> }>({ src: null, map: new Map() });
  const draw = useRef<() => void>(() => {});

  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(wrap.current!);
    return () => ro.disconnect();
  }, []);

  // transformacion mundo -> pantalla: ajusta al bbox, eje y invertido, mas zoom/pan del usuario
  const tf = useMemo(() => {
    const { minX, minY, maxX, maxY } = net.bbox;
    const base = Math.min((size.w - 2 * PAD) / Math.max(1, maxX - minX), (size.h - 2 * PAD) / Math.max(1, maxY - minY));
    const s = base * view.k;
    const ox = (size.w - (maxX - minX) * s) / 2 + view.dx - minX * s;
    const oy = (size.h + (maxY - minY) * s) / 2 + view.dy + minY * s;
    return { s, X: (x: number) => ox + x * s, Y: (y: number) => oy - y * s };
  }, [net, size, view]);

  const laneById = useMemo(() => new Map(net.lanes.map((l) => [l.id, l])), [net]);

  // Se redefine en cada render (usa la red, el zoom y los cierres actuales); el bucle rAF la llama ~60 veces/s.
  draw.current = () => {
    const cv = ref.current;
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(size.w * dpr) || cv.height !== Math.round(size.h * dpr)) {
      cv.width = Math.round(size.w * dpr); cv.height = Math.round(size.h * dpr);
    }
    const g = cv.getContext("2d")!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, size.w, size.h);
    g.lineCap = "round"; g.lineJoin = "round";
    const { X, Y, s } = tf;
    const sim = feed.current.cur?.sims[simKey];

    const path = (pts: [number, number][]) => {
      g.beginPath();
      pts.forEach(([x, y], i) => (i ? g.lineTo(X(x), Y(y)) : g.moveTo(X(x), Y(y))));
    };
    // interior de las intersecciones (el backend no manda carriles internos)
    g.fillStyle = "#2a3140";
    for (const j of net.junctions) { path(j.shape); g.closePath(); g.fill(); }
    for (const l of net.lanes) {
      path(l.shape);
      g.strokeStyle = closed.has(l.edge) ? "#7a2230" : "#2a3140";
      g.lineWidth = Math.max(3.5, l.width * s);
      g.stroke();
    }
    // incidentes: borde resaltado con franjas
    for (const l of net.lanes) if (closed.has(l.edge)) {
      path(l.shape); g.strokeStyle = RED; g.lineWidth = Math.max(1.5, l.width * s * 0.3);
      g.setLineDash([8, 6]); g.stroke(); g.setLineDash([]);
    }

    // semaforos: barra en la linea de alto de cada carril controlado, con el color de su(s) enlace(s)
    for (const t of net.tls) {
      const st = sim?.tls[t.id];
      if (!st) continue;
      for (const c of t.controlled) {
        const l = laneById.get(c.lane);
        const [x1, y1] = l ? l.shape[l.shape.length - 1] : [c.x, c.y];
        const [x0, y0] = l ? l.shape[l.shape.length - 2] : [c.x, c.y - 1];
        const dx = X(x1) - X(x0), dy = Y(y1) - Y(y0), L = Math.hypot(dx, dy) || 1;
        const half = Math.max(2.5, ((l?.width ?? 3.2) * s) / 2 + 0.5);
        const px = -dy / L, py = dx / L; // perpendicular al carril, en pantalla
        const bx = X(x1), by = Y(y1);
        g.strokeStyle = laneSignal(st, c.idx);
        g.lineWidth = Math.max(3, 1.4 * s * 3);
        g.lineCap = "butt";
        g.beginPath(); g.moveTo(bx - px * half, by - py * half); g.lineTo(bx + px * half, by + py * half); g.stroke();
        g.lineCap = "round";
      }
    }

    // vehiculos: rectangulos orientados (angulo SUMO: 0 = norte, horario)
    const vl = Math.max(7, 4.5 * s), vw = Math.max(3.5, 1.9 * s);
    for (const [, x, y, ang, v] of interpolated(feed.current, simKey, cache.current)) {
      g.save();
      g.translate(X(x), Y(y));
      g.rotate((ang * Math.PI) / 180);
      g.fillStyle = speedColor(v);
      g.fillRect(-vw / 2, -vl / 2, vw, vl);
      g.restore();
    }

    // etiquetas de los semaforos
    g.font = "600 12px system-ui, sans-serif"; g.textAlign = "left"; g.textBaseline = "middle";
    g.lineWidth = 3; g.strokeStyle = "#0e121b"; g.fillStyle = "#c9d2e3";
    for (const t of net.tls) {
      const lx = X(t.x) + Math.max(14, 7 * s), ly = Y(t.y);
      g.strokeText(t.name, lx, ly); g.fillText(t.name, lx, ly);
    }
  };

  useEffect(() => {
    let raf = 0;
    const loop = () => { draw.current(); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const edgeAt = (ex: number, ey: number): string | null => {
    let best: string | null = null, bd = Math.max(10, 4 * tf.s);
    for (const l of net.lanes) {
      for (let i = 1; i < l.shape.length; i++) {
        const ax = tf.X(l.shape[i - 1][0]), ay = tf.Y(l.shape[i - 1][1]);
        const bx = tf.X(l.shape[i][0]), by = tf.Y(l.shape[i][1]);
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
            const k = Math.max(0.5, Math.min(12, view.k * f));
            const [mx, my] = rel(e); const cx = size.w / 2, cy = size.h / 2, r = k / view.k;
            // zoom centrado en el cursor
            onView({ k, dx: mx - cx - (mx - cx - view.dx) * r, dy: my - cy - (my - cy - view.dy) * r });
          }}
        />
        <div className="legend"><i className="g" />libre<i className="y" />lento<i className="r" />detenido</div>
      </div>
    </section>
  );
}
