// Estilo esquematico: el dibujo original de la demo (carriles como trazos, cruces rellenos, tramos
// cerrados con rayas rojas, barra de alto con el color del semaforo, carros como rectangulos
// coloreados por velocidad y el nombre de cada semaforo), con la camara nueva (rotacion incluida).
import type { Network } from "../types";
import { applyScreen, applyWorld, screenAngle, toScreen, type Camera } from "./camera";
import { speedColor, type CarDraw } from "./cars";
import type { BadgeHit } from "./signals";
import { FONT, type Palette } from "./theme";

interface SLane { id: string; edge: string; path: Path2D; width: number; }
// Barra de alto en metros: centro (x, y), perpendicular (px, py) y medio ancho del carril.
interface Bar { tls: string; idx: number[]; x: number; y: number; px: number; py: number; half: number; }

export interface SchematicModel {
  net: Network;
  lanes: SLane[];
  junctions: Path2D;
  bars: Bar[];
  hulls: Map<string, [number, number][]>; // puntos que delimitan cada cruce semaforizado (para su nombre)
}

const pathOf = (pts: [number, number][], close = false): Path2D => {
  const p = new Path2D();
  pts.forEach(([x, y], i) => (i ? p.lineTo(x, y) : p.moveTo(x, y)));
  if (close) p.closePath();
  return p;
};

export function buildSchematicModel(net: Network): SchematicModel {
  const byId = new Map(net.lanes.map((l) => [l.id, l]));
  const lanes = net.lanes.map((l) => ({ id: l.id, edge: l.edge, path: pathOf(l.shape), width: l.width }));
  const junctions = new Path2D();
  for (const j of net.junctions) junctions.addPath(pathOf(j.shape, true));
  const bars: Bar[] = [];
  for (const t of net.tls) for (const c of t.controlled) {
    const l = byId.get(c.lane);
    let x = c.x, y = c.y, ux = 0, uy = 1;
    if (l && l.shape.length >= 2) {
      const a = l.shape[l.shape.length - 2], b = l.shape[l.shape.length - 1];
      const L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
      x = b[0]; y = b[1]; ux = (b[0] - a[0]) / L; uy = (b[1] - a[1]) / L;
    }
    bars.push({ tls: t.id, idx: c.idx, x, y, px: -uy, py: ux, half: (l?.width ?? 3.2) / 2 });
  }
  // contorno del cruce: su poligono si viene en la red; si no, las lineas de alto; si no, un cuadro de 10 m
  const hulls = new Map<string, [number, number][]>();
  for (const t of net.tls) {
    const j = net.junctions.find((j) => j.id === t.id);
    const stops = t.controlled.map((c): [number, number] => [c.x, c.y]);
    hulls.set(t.id, j ? j.shape : stops.length ? stops : [[t.x - 5, t.y - 5], [t.x + 5, t.y + 5]]);
  }
  return { net, lanes, junctions, bars, hulls };
}

export interface SchematicOpts {
  states: Record<string, string> | undefined; // cadena de estado de cada semaforo
  cars: CarDraw[];
  closedLanes: Set<string>;
  closedEdges: Set<string>; // respaldo si closedLanes viene vacio (mock)
}

// Color del carril: verde si algun enlace esta en verde, si no amarillo, si no rojo.
function laneLamp(st: string, idx: number[]): 0 | 1 | 2 {
  let y = false;
  for (const i of idx) {
    const c = st[i];
    if (c === "G" || c === "g") return 0;
    if (c === "y" || c === "Y") y = true;
  }
  return y ? 1 : 2;
}

// Colores por velocidad cuantizados (se asigna fillStyle una vez por grupo, no por carro).
const NB = 24;
const SPEED_COLORS = Array.from({ length: NB + 1 }, (_, i) => speedColor((i / NB) * 13.9));
const buckets: CarDraw[][] = Array.from({ length: NB + 1 }, () => []);

// Dibuja todo el mapa esquematico. Devuelve las cajas de los nombres de semaforo (clic = acercar).
export function drawSchematic(g: CanvasRenderingContext2D, cam: Camera, dpr: number, m: SchematicModel,
  pal: Palette, o: SchematicOpts): BadgeHit[] {
  applyScreen(g, dpr);
  g.fillStyle = pal.ground;
  g.fillRect(0, 0, cam.w, cam.h);

  // calzada (en metros): cruces rellenos y cada carril como un trazo un poco mas angosto que el carril
  applyWorld(g, cam, dpr);
  const px = 1 / cam.s; // un px de pantalla en metros
  g.lineCap = "round"; g.lineJoin = "round";
  g.fillStyle = pal.asphalt;
  g.fill(m.junctions);
  g.strokeStyle = pal.asphalt;
  for (const l of m.lanes) { g.lineWidth = Math.max(l.width - 0.5, 3.5 * px); g.stroke(l.path); }

  // tramos cerrados: carril tenido de rojo y raya discontinua encima
  const isClosed = (l: SLane) => (o.closedLanes.size ? o.closedLanes.has(l.id) : o.closedEdges.has(l.edge));
  const closed = m.lanes.filter(isClosed);
  if (closed.length) {
    g.strokeStyle = pal.closed;
    g.globalAlpha = 0.35;
    for (const l of closed) { g.lineWidth = Math.max(l.width - 0.5, 3.5 * px); g.stroke(l.path); }
    g.globalAlpha = 1;
    g.setLineDash([8 * px, 6 * px]);
    for (const l of closed) { g.lineWidth = Math.max(l.width * 0.3, 1.5 * px); g.stroke(l.path); }
    g.setLineDash([]);
  }

  // barras de alto con el color del semaforo (agrupadas por color)
  if (o.states) {
    const paths = [new Path2D(), new Path2D(), new Path2D()];
    for (const b of m.bars) {
      const st = o.states[b.tls];
      if (!st) continue;
      const h = Math.max(b.half + 0.5 * px, 2.5 * px);
      const p = paths[laneLamp(st, b.idx)];
      p.moveTo(b.x - b.px * h, b.y - b.py * h);
      p.lineTo(b.x + b.px * h, b.y + b.py * h);
    }
    g.lineCap = "butt";
    g.lineWidth = Math.max(1.6, 3 * px);
    [pal.green, pal.yellow, pal.red].forEach((c, i) => { g.strokeStyle = c; g.stroke(paths[i]); });
  }
  g.lineCap = "butt"; g.lineJoin = "miter";

  // vehiculos: rectangulos orientados, color por velocidad, en pantalla (tamano minimo visible)
  const vl = Math.max(7, 4.5 * cam.s), vw = Math.max(3.5, 1.9 * cam.s), mg = vl;
  for (const b of buckets) b.length = 0;
  for (const c of o.cars) buckets[Math.round(Math.max(0, Math.min(1, c.speed / 13.9)) * NB)].push(c);
  for (let i = 0; i <= NB; i++) {
    const list = buckets[i];
    if (!list.length) continue;
    g.fillStyle = SPEED_COLORS[i];
    for (const c of list) {
      const [x, y] = toScreen(cam, c.x, c.y);
      if (x < -mg || y < -mg || x > cam.w + mg || y > cam.h + mg) continue;
      const a = screenAngle(cam, c.angle), co = Math.cos(a) * dpr, si = Math.sin(a) * dpr;
      g.setTransform(co, si, -si, co, x * dpr, y * dpr);
      g.fillRect(-vw / 2, -vl / 2, vw, vl);
    }
  }
  for (const b of buckets) b.length = 0;

  // nombres de los semaforos: arriba a la derecha del cruce; si chocan con el anterior, abajo
  applyScreen(g, dpr);
  g.font = `600 12px ${FONT}`;
  g.textAlign = "left";
  g.lineWidth = 3; g.lineJoin = "round";
  g.strokeStyle = pal.labelHalo; g.fillStyle = pal.label;
  const items = m.net.tls.map((t) => {
    let x1 = -Infinity, y0 = Infinity, y1 = -Infinity, x0 = Infinity;
    for (const [wx, wy] of m.hulls.get(t.id) ?? [[t.x, t.y] as [number, number]]) {
      const [sx, sy] = toScreen(cam, wx, wy);
      x0 = Math.min(x0, sx); x1 = Math.max(x1, sx); y0 = Math.min(y0, sy); y1 = Math.max(y1, sy);
    }
    const cx = (x0 + x1) / 2;
    return { t, x: Math.max(x1 - 0.25 * (x1 - x0), cx + 6), y0: y0 - 5, y1: y1 + 5 };
  }).filter((it) => it.x > -200 && it.x < cam.w + 20 && it.y1 > -30 && it.y0 < cam.h + 30).sort((a, b) => a.x - b.x);
  const hits: BadgeHit[] = [];
  let lastUp = -Infinity, lastDown = -Infinity;
  for (const { t, x, y0, y1 } of items) {
    const w = g.measureText(t.name).width;
    const up = x > lastUp + 8 || x <= lastDown + 8;
    if (up) lastUp = x + w; else lastDown = x + w;
    g.textBaseline = up ? "bottom" : "top";
    const y = up ? y0 : y1;
    g.strokeText(t.name, x, y);
    g.fillText(t.name, x, y);
    hits.push({ id: t.id, x: x - 4, y: up ? y - 17 : y - 2, w: w + 8, h: 19 });
  }
  g.lineJoin = "miter";
  return hits;
}
