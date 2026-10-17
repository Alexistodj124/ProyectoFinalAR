import { useEffect, useMemo, useRef, useState } from "react";
import type { Network, SimState } from "./types";

export interface View { k: number; dx: number; dy: number; } // zoom relativo y desplazamiento (px)
export type Mode = "ver" | "inyectar" | "incidente";

interface Props {
  title: string;
  accent: string;
  net: Network;
  sim: SimState | undefined;
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
function tlsColor(c: string): string {
  return c === "G" || c === "g" ? "#22e07a" : c === "y" || c === "Y" ? "#ffd23f" : "#ff4d4d";
}

export default function NetCanvas({ title, accent, net, sim, closed, mode, view, onView, onLane }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 600, h: 400 });
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);

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

  useEffect(() => {
    const cv = ref.current!;
    const dpr = window.devicePixelRatio || 1;
    cv.width = size.w * dpr; cv.height = size.h * dpr;
    const g = cv.getContext("2d")!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, size.w, size.h);
    g.lineCap = "round"; g.lineJoin = "round";
    const { X, Y, s } = tf;
    const lw = Math.max(3.5, 3.6 * s);

    const path = (pts: [number, number][]) => {
      g.beginPath();
      pts.forEach(([x, y], i) => (i ? g.lineTo(X(x), Y(y)) : g.moveTo(X(x), Y(y))));
    };
    for (const l of net.lanes) {
      const isClosed = closed.has(l.edge);
      path(l.shape);
      g.strokeStyle = isClosed ? "#7a2230" : "#2a3140";
      g.lineWidth = l.internal ? lw * 0.8 : lw;
      g.stroke();
    }
    // incidentes: borde resaltado + franjas
    for (const l of net.lanes) if (closed.has(l.edge) && !l.internal) {
      path(l.shape); g.strokeStyle = "#ff4d4d"; g.lineWidth = Math.max(1.5, lw * 0.25);
      g.setLineDash([8, 6]); g.stroke(); g.setLineDash([]);
    }

    // semaforos: marca al final de cada carril controlado (o circulo en la interseccion)
    for (const t of net.tls) {
      const st = sim?.tls[t.id];
      if (!st) continue;
      if (t.lanes.length) {
        t.lanes.forEach((id, i) => {
          const l = laneById.get(id);
          const c = st[i];
          if (!l || !c) return;
          const [x1, y1] = l.shape[l.shape.length - 1];
          const [x0, y0] = l.shape[l.shape.length - 2] ?? l.shape[0];
          const L = Math.hypot(x1 - x0, y1 - y0) || 1;
          const nx = (x1 - x0) / L, ny = (y1 - y0) / L;
          const bx = X(x1 - nx * 2), by = Y(y1 - ny * 2);
          const px = -(Y(y1) - Y(y0)) / L / s, py = (X(x1) - X(x0)) / L / s; // perpendicular en pantalla
          g.strokeStyle = tlsColor(c); g.lineWidth = Math.max(3, lw * 0.9);
          g.lineCap = "butt";
          g.beginPath(); g.moveTo(bx - px * lw * 0.5, by - py * lw * 0.5); g.lineTo(bx + px * lw * 0.5, by + py * lw * 0.5); g.stroke();
          g.lineCap = "round";
        });
      } else {
        const greens = [...st].filter((c) => c === "G" || c === "g").length;
        const yellows = [...st].filter((c) => c === "y" || c === "Y").length;
        g.fillStyle = tlsColor(greens ? "G" : yellows ? "y" : "r");
        g.beginPath(); g.arc(X(t.x), Y(t.y), Math.max(5, 7 * s), 0, Math.PI * 2); g.fill();
      }
    }

    // vehiculos: rectangulos orientados (angulo SUMO: 0 = norte, horario)
    const vl = Math.max(7, 4.5 * s), vw = Math.max(3.5, 1.9 * s);
    for (const [, x, y, ang, v] of sim?.vehicles ?? []) {
      g.save();
      g.translate(X(x), Y(y));
      g.rotate((ang * Math.PI) / 180);
      g.fillStyle = speedColor(v);
      g.fillRect(-vw / 2, -vl / 2, vw, vl);
      g.restore();
    }
  }, [net, sim, closed, tf, size, laneById]);

  const edgeAt = (ex: number, ey: number): string | null => {
    let best: string | null = null, bd = Math.max(10, 4 * tf.s);
    for (const l of net.lanes) {
      if (l.internal) continue;
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
