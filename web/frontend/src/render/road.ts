// Calles realistas: banquetas, asfalto, interior de cruces, arriate central con arboles, marcas viales
// (separadores, bordes, lineas de alto, cebras, flechas), alumbrado de noche, incidentes y nombres.
// Toda la geometria se precalcula en metros del mundo (Path2D) en buildRoadModel; el dibujo por cuadro
// solo rellena/traza esos caminos y unos pocos sprites en pantalla.
import type { Lane, Network } from "../types";
import { applyScreen, applyWorld, screenDir, toScreen, type Camera } from "./camera";
import { CROSSWALK_M, FONT, LOD, SIDEWALK_M, STOP_BACK_M, type Palette } from "./theme";

type Pt = [number, number];

const MEDIAN_HALF = 0.42; // medio ancho del arriate cuando la red no deja hueco entre sentidos (Reforma)
const NOSE_M = 1.2; // el arriate termina en punta redonda a esta distancia de la boca del cruce
const TREE_STEP = 9; // m entre arboles del arriate
const LAMP_STEP = 27; // m entre postes del arriate (cada 3 arboles, entre dos de ellos)
const DASH = [3, 6]; // guion / espacio de los separadores (m)
const SOLID_M = 20; // separador continuo antes de la linea de alto
const CW_GAP = 0.6; // espacio entre la boca del cruce y la cebra (m)
const STRIPE = 0.5; // ancho de cada franja de la cebra (y del espacio entre franjas)
const LINE_M = 0.15; // ancho de lineas de borde y separadores
const STOP_W = 0.4; // ancho de la linea de alto
const EDGE_INSET = 0.3; // distancia de la linea de borde al bordillo
const ARROW_LEN = 5; // largo de las flechas pintadas
const ARROW_GAP = 5; // de la punta de la flecha a la linea de alto
const MIN_PX = 0.8; // ninguna linea mas delgada que esto en pantalla

// ---------------------------------------------------------------- geometria basica (metros)

const dist = (a: Pt, b: Pt) => Math.hypot(b[0] - a[0], b[1] - a[1]);

function dedupe(p: Pt[]): Pt[] {
  const out: Pt[] = [];
  for (const q of p) {
    const l = out[out.length - 1];
    if (!l || dist(l, q) > 1e-3) out.push([q[0], q[1]]);
  }
  return out;
}

function polyLen(p: Pt[]): number {
  let L = 0;
  for (let i = 1; i < p.length; i++) L += dist(p[i - 1], p[i]);
  return L;
}

function area(p: Pt[]): number {
  let a = 0;
  for (let i = 0; i < p.length; i++) {
    const [x0, y0] = p[i], [x1, y1] = p[(i + 1) % p.length];
    a += x0 * y1 - x1 * y0;
  }
  return a / 2;
}

const ccw = (p: Pt[]): Pt[] => (area(p) < 0 ? p.slice().reverse() : p);

// Desplaza la polilinea d metros a la izquierda del sentido de avance (d < 0: derecha), con uniones
// en inglete limitadas (normal promedio de los dos segmentos).
function offset(p: Pt[], d: number): Pt[] {
  const n = p.length;
  if (n < 2) return p.slice();
  const nx: number[] = [], ny: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    const dx = p[i + 1][0] - p[i][0], dy = p[i + 1][1] - p[i][1];
    const L = Math.hypot(dx, dy) || 1;
    nx.push(-dy / L); ny.push(dx / L);
  }
  const out: Pt[] = [];
  for (let i = 0; i < n; i++) {
    let mx: number, my: number;
    if (i === 0) { mx = nx[0]; my = ny[0]; }
    else if (i === n - 1) { mx = nx[n - 2]; my = ny[n - 2]; }
    else {
      mx = nx[i - 1] + nx[i]; my = ny[i - 1] + ny[i];
      const L = Math.hypot(mx, my);
      if (L < 1e-6) { mx = nx[i]; my = ny[i]; }
      else {
        mx /= L; my /= L;
        const c = Math.max(0.35, mx * nx[i] + my * ny[i]);
        mx /= c; my /= c;
      }
    }
    out.push([p[i][0] + mx * d, p[i][1] + my * d]);
  }
  return out;
}

// Punto y direccion unitaria a s metros del inicio (s se recorta al largo de la polilinea).
function at(p: Pt[], s: number): [number, number, number, number] {
  let acc = 0;
  for (let i = 1; i < p.length; i++) {
    const dx = p[i][0] - p[i - 1][0], dy = p[i][1] - p[i - 1][1], L = Math.hypot(dx, dy);
    if (L < 1e-9) continue;
    if (acc + L >= s || i === p.length - 1) {
      const t = Math.max(0, Math.min(1, (s - acc) / L));
      return [p[i - 1][0] + dx * t, p[i - 1][1] + dy * t, dx / L, dy / L];
    }
    acc += L;
  }
  return [p[0]?.[0] ?? 0, p[0]?.[1] ?? 0, 1, 0];
}

// Tramo de la polilinea entre s0 y s1 (metros desde el inicio).
function slice(p: Pt[], s0: number, s1: number): Pt[] {
  if (s1 - s0 < 1e-3) return [];
  const a = at(p, s0), out: Pt[] = [[a[0], a[1]]];
  let acc = 0;
  for (let i = 1; i < p.length; i++) {
    acc += dist(p[i - 1], p[i]);
    if (acc > s0 + 1e-3 && acc < s1 - 1e-3) out.push(p[i]);
  }
  const b = at(p, s1);
  out.push([b[0], b[1]]);
  return out;
}

// Promedio punto a punto (solo si tienen los mismos vertices).
function avg(a: Pt[], b: Pt[]): Pt[] | null {
  if (a.length !== b.length) return null;
  return a.map((p, i) => [(p[0] + b[i][0]) / 2, (p[1] + b[i][1]) / 2] as Pt);
}

function distToPoly(q: Pt, p: Pt[]): number {
  let best = Infinity;
  for (let i = 1; i < p.length; i++) {
    const [ax, ay] = p[i - 1], [bx, by] = p[i];
    const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((q[0] - ax) * dx + (q[1] - ay) * dy) / L2));
    best = Math.min(best, Math.hypot(q[0] - ax - dx * t, q[1] - ay - dy * t));
  }
  return best;
}

function inside(q: Pt, p: Pt[]): boolean {
  let c = false;
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
    const [xi, yi] = p[i], [xj, yj] = p[j];
    if ((yi > q[1]) !== (yj > q[1]) && q[0] < ((xj - xi) * (q[1] - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}

function addPoly(path: Path2D, p: Pt[]): void {
  if (p.length < 3) return;
  path.moveTo(p[0][0], p[0][1]);
  for (let i = 1; i < p.length; i++) path.lineTo(p[i][0], p[i][1]);
  path.closePath();
}

function addLine(path: Path2D, p: Pt[]): void {
  if (p.length < 2) return;
  path.moveTo(p[0][0], p[0][1]);
  for (let i = 1; i < p.length; i++) path.lineTo(p[i][0], p[i][1]);
}

// Cuadrilatero en el marco local (u hacia adelante, v a la izquierda) con origen o y direccion d.
function frame(o: Pt, d: Pt) {
  return (u: number, v: number): Pt => [o[0] + d[0] * u - d[1] * v, o[1] + d[1] * u + d[0] * v];
}

const laneIndex = (id: string) => { const m = /_(\d+)$/.exec(id); return m ? +m[1] : 0; };
const hash = (i: number) => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

// ---------------------------------------------------------------- modelo

interface EdgeGeo {
  id: string; name: string; from: string; to: string;
  lanes: Lane[]; shapes: Pt[][]; // ordenados por indice SUMO (0 = derecha)
  right: Pt[]; left: Pt[]; center: Pt[]; // bordes exteriores y eje
  width: number; len: number;
  kind: "oneway" | "divided" | "twoway"; // divided: el lado izquierdo es arriate
  inset: number; // m que el arriate le quita al carril interior (arriate sintetico)
  approach: boolean; // sus carriles tienen semaforo al final
}

interface Median { center: Pt[]; half: number; }
interface Lamp { x: number; y: number; r: number; k: number; }
interface Tree { x: number; y: number; r: number; }
interface LabelAnchor { text: string; path: Pt[]; len: number; kind: "avenue" | "street"; jEnd: -1 | 0 | 1; }

// Geometria precalculada en metros del mundo (opaca para quien llama).
export interface RoadModel {
  net: Network;
  edges: EdgeGeo[];
  laneOf: Map<string, { e: EdgeGeo; i: number }>;
  lanePoly: Map<string, Pt[]>;
  sidewalks: Path2D; // bordes exteriores (se trazan con 2 x SIDEWALK_M)
  rims: Path2D; // contorno de los cruces (esquinas redondeadas de banqueta)
  curbs: Path2D; // bordillo: bordes exteriores + esquinas de los cruces
  asphalt: Path2D; // calzadas + cruces (una sola pasada: sin costuras)
  junctions: Path2D;
  medianFill: Path2D;
  medianLines: Path2D; // eje del arriate (linea verde de lejos)
  medians: Median[];
  edgeWhite: Path2D; edgeYellow: Path2D;
  sepSolid: Path2D; sepDashed: Path2D;
  stops: Path2D;
  zebra: Path2D; zebraBands: Path2D;
  arrowShafts: Path2D; arrowHeads: Path2D;
  trees: Tree[];
  lamps: Lamp[];
  labels: LabelAnchor[];
  juncs: { id: string; poly: Pt[]; cx: number; cy: number; r: number }[];
  buildings: Path2D; buildingsAlt: Path2D; roofs: Path2D; // huellas de edificios (dos tonos) y pretiles
  incCache: Map<string, IncidentGeo>;
  icons: Pt[]; // iconos de incidente del ultimo cuadro (los nombres los esquivan)
}

export function buildRoadModel(net: Network): RoadModel {
  const m: RoadModel = {
    net, edges: [], laneOf: new Map(), lanePoly: new Map(),
    sidewalks: new Path2D(), rims: new Path2D(), curbs: new Path2D(), asphalt: new Path2D(), junctions: new Path2D(),
    medianFill: new Path2D(), medianLines: new Path2D(), medians: [],
    edgeWhite: new Path2D(), edgeYellow: new Path2D(), sepSolid: new Path2D(), sepDashed: new Path2D(),
    stops: new Path2D(), zebra: new Path2D(), zebraBands: new Path2D(), arrowShafts: new Path2D(), arrowHeads: new Path2D(),
    trees: [], lamps: [], labels: [], juncs: [], incCache: new Map(), icons: [],
    buildings: new Path2D(), buildingsAlt: new Path2D(), roofs: new Path2D(),
  };
  try { build(net, m); } catch (e) { console.error("[road] buildRoadModel:", e); }
  try { addBuildings(m); } catch (e) { console.error("[road] edificios:", e); }
  return m;
}

// Cuadrilateros convexos que se tocan (ejes separadores) con un margen en metros.
function quadsOverlap(a: Pt[], b: Pt[], margin: number): boolean {
  for (const P of [a, b]) for (let i = 0; i < P.length; i++) {
    const [x0, y0] = P[i], [x1, y1] = P[(i + 1) % P.length];
    const L = Math.hypot(x1 - x0, y1 - y0) || 1, nx = (y0 - y1) / L, ny = (x1 - x0) / L;
    let a0 = Infinity, a1 = -Infinity, b0 = Infinity, b1 = -Infinity;
    for (const q of a) { const d = q[0] * nx + q[1] * ny; a0 = Math.min(a0, d); a1 = Math.max(a1, d); }
    for (const q of b) { const d = q[0] * nx + q[1] * ny; b0 = Math.min(b0, d); b1 = Math.max(b1, d); }
    if (a1 + margin < b0 || b1 + margin < a0) return false;
  }
  return true;
}

// Huellas de edificios procedurales (deterministas) en dos filas detras de cada banqueta: textura de
// ciudad discreta alrededor del corredor. Se descartan las que tocan calles, cruces u otros edificios.
function addBuildings(m: RoadModel): void {
  if (!m.juncs.length) return; // redes sin cruces (mock): sin edificios
  const clearance = SIDEWALK_M + 1.4;
  const clear = (q: Pt) => {
    for (const e of m.edges) if (distToPoly(q, e.center) < e.width / 2 + clearance) return false;
    for (const j of m.juncs) if (inside(q, j.poly) || distToPoly(q, [...j.poly, j.poly[0]]) < clearance) return false;
    return true;
  };
  const placed: { q: Pt[]; x0: number; y0: number; x1: number; y1: number }[] = [];
  let seed = 7;
  const rnd = () => hash(seed++);
  for (const e of m.edges) {
    const sides: (1 | -1)[] = e.kind === "oneway" ? [-1, 1] : [-1];
    for (const side of sides) {
      const line = side < 0 ? e.right : e.left, L = polyLen(line);
      for (let row = 0; row < 2; row++) {
        let s = 1 + rnd() * 5;
        while (s < L - 6) {
          const w = 9 + rnd() * 17, gap = 2 + rnd() * 4.5;
          const back = SIDEWALK_M + (row === 0 ? 1.8 + rnd() * 3 : 31 + rnd() * 5);
          const depth = row === 0 ? 12 + rnd() * 15 : 10 + rnd() * 14;
          const [x, y, dx, dy] = at(line, Math.min(L, s + w / 2));
          const f = frame([x, y], [dx, dy]);
          const q = [f(-w / 2, side * back), f(w / 2, side * back), f(w / 2, side * (back + depth)), f(-w / 2, side * (back + depth))];
          s += w + gap;
          let ok = true;
          for (let a = 0; a <= 3 && ok; a++) for (let b = 0; b <= 3 && ok; b++) {
            const u = a / 3, v = b / 3;
            const p0: Pt = [q[0][0] + (q[1][0] - q[0][0]) * u, q[0][1] + (q[1][1] - q[0][1]) * u];
            const p1: Pt = [q[3][0] + (q[2][0] - q[3][0]) * u, q[3][1] + (q[2][1] - q[3][1]) * u];
            ok = clear([p0[0] + (p1[0] - p0[0]) * v, p0[1] + (p1[1] - p0[1]) * v]);
          }
          if (!ok) continue;
          const xs = q.map((p) => p[0]), ys = q.map((p) => p[1]);
          const bb = { q, x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
          if (placed.some((p) => p.x0 < bb.x1 + 2 && bb.x0 < p.x1 + 2 && p.y0 < bb.y1 + 2 && bb.y0 < p.y1 + 2 && quadsOverlap(p.q, q, 1.5))) continue;
          placed.push(bb);
          addPoly(rnd() < 0.35 ? m.buildingsAlt : m.buildings, q);
          const c = q.reduce((acc, p) => [acc[0] + p[0] / 4, acc[1] + p[1] / 4] as Pt, [0, 0] as Pt);
          addPoly(m.roofs, q.map((p) => { const d = Math.hypot(p[0] - c[0], p[1] - c[1]) || 1, k = Math.max(0, d - 1.4) / d; return [c[0] + (p[0] - c[0]) * k, c[1] + (p[1] - c[1]) * k] as Pt; }));
        }
      }
    }
  }
}

function build(net: Network, m: RoadModel): void {
  const info = new Map((net.edges ?? []).map((e) => [e.id, e]));
  const dirsOf = new Map<string, string[]>();
  for (const t of net.tls ?? []) for (const c of t.controlled ?? []) dirsOf.set(c.lane, c.dirs ?? []);

  // carriles por borde, ordenados por indice
  const byEdge = new Map<string, Lane[]>();
  for (const l of net.lanes ?? []) {
    if (!l.shape || l.shape.length < 2) continue;
    const arr = byEdge.get(l.edge) ?? [];
    arr.push(l);
    byEdge.set(l.edge, arr);
  }
  for (const [id, ls] of byEdge) {
    ls.sort((a, b) => laneIndex(a.id) - laneIndex(b.id));
    const shapes = ls.map((l) => dedupe(l.shape));
    if (shapes.some((s) => s.length < 2)) continue;
    const w0 = ls[0].width || 3.2, wN = ls[ls.length - 1].width || 3.2;
    const W = ls.reduce((a, l) => a + (l.width || 3.2), 0);
    const center = offset(shapes[0], W / 2 - w0 / 2);
    const inf = info.get(id);
    const e: EdgeGeo = {
      id, name: inf?.name ?? "", from: inf?.from ?? "", to: inf?.to ?? "", lanes: ls, shapes,
      right: offset(shapes[0], -w0 / 2), left: offset(shapes[shapes.length - 1], wN / 2), center,
      width: W, len: polyLen(center), kind: "oneway", inset: 0, approach: ls.some((l) => dirsOf.has(l.id)),
    };
    m.edges.push(e);
    ls.forEach((l, i) => {
      m.laneOf.set(l.id, { e, i });
      const w = l.width || 3.2;
      m.lanePoly.set(l.id, [...offset(shapes[i], w / 2), ...offset(shapes[i], -w / 2).reverse()]);
    });
  }

  // cruces (los degenerados de los extremos se ignoran)
  for (const j of net.junctions ?? []) {
    const p = dedupe(j.shape ?? []);
    if (p.length < 3 || Math.abs(area(p)) < 1) continue;
    const poly = ccw(p);
    let cx = 0, cy = 0;
    for (const q of poly) { cx += q[0]; cy += q[1]; }
    cx /= poly.length; cy /= poly.length;
    const r = Math.max(...poly.map((q) => Math.hypot(q[0] - cx, q[1] - cy)));
    m.juncs.push({ id: j.id, poly, cx, cy, r });
  }
  const jById = new Map(m.juncs.map((j) => [j.id, j]));

  // pares de sentidos opuestos: arriate (con hueco o sintetico) o doble linea amarilla
  const byKey = new Map<string, EdgeGeo>();
  for (const e of m.edges) if (e.from && e.to) byKey.set(`${e.from}>${e.to}`, e);
  const partner = new Map<EdgeGeo, EdgeGeo>();
  for (const a of m.edges) {
    if (!a.from || !a.to) continue;
    const b = byKey.get(`${a.to}>${a.from}`);
    if (!b || b === a || a.id > b.id) continue;
    const mid = at(a.left, polyLen(a.left) / 2);
    const gap = distToPoly([mid[0], mid[1]], b.left);
    if (gap > 15) continue;
    partner.set(a, b); partner.set(b, a);
    const avenue = Math.min(a.lanes.length, b.lanes.length) >= 3 || /avenida|av\.|bulevar|boulevard|calzada|reforma/i.test(a.name);
    const center = avg(a.left, b.left.slice().reverse()) ?? offset(a.left, gap / 2);
    if (gap < 0.5 && !avenue) {
      a.kind = b.kind = "twoway";
      addLine(m.edgeYellow, offset(center, 0.12));
      addLine(m.edgeYellow, offset(center, -0.12));
      if (a.name) m.labels.push({ text: abbreviate(a.name), path: center, len: polyLen(center), kind: "avenue", jEnd: -1 });
      continue;
    }
    a.kind = b.kind = "divided";
    let half: number;
    if (gap >= 0.5) {
      half = gap / 2;
      const poly = [...a.left, ...b.left];
      addPoly(m.medianFill, ccw(poly));
    } else {
      half = MEDIAN_HALF;
      a.inset = b.inset = Math.max(0, half - gap / 2);
      addMedianNose(m.medianFill, center, half, jById.has(a.from) ? NOSE_M : 0, jById.has(a.to) ? NOSE_M : 0);
    }
    m.medians.push({ center, half });
    addLine(m.medianLines, center);
    const L = polyLen(center);
    const t0 = jById.has(a.from) ? NOSE_M + 4 : 3, t1 = L - (jById.has(a.to) ? NOSE_M + 4 : 3);
    if (t1 > t0) {
      const n = Math.floor((t1 - t0) / TREE_STEP) + 1, s0 = t0 + (t1 - t0 - (n - 1) * TREE_STEP) / 2;
      const rr = gap >= 0.5 ? Math.max(0.9, Math.min(3, half * 0.9)) : 1.0;
      for (let k = 0; k < n; k++) {
        const [x, y] = at(center, s0 + k * TREE_STEP);
        m.trees.push({ x, y, r: rr * (0.82 + 0.36 * hash(m.trees.length)) });
        if (k % Math.round(LAMP_STEP / TREE_STEP) === 1 && k < n - 1) {
          const [lx, ly] = at(center, s0 + (k + 0.5) * TREE_STEP);
          m.lamps.push({ x: lx, y: ly, r: 12, k: 1.3 });
        }
      }
    }
    if (a.name) m.labels.push({ text: abbreviate(a.name), path: center, len: L, kind: "avenue", jEnd: -1 });
  }

  // calzada, banquetas, bordillos y lineas de borde por borde
  for (const e of m.edges) {
    addPoly(m.asphalt, ccw([...e.left, ...e.right.slice().reverse()]));
    addLine(m.sidewalks, e.right);
    addLine(m.curbs, e.right);
    const stopS = e.approach ? e.len - STOP_BACK_M + STOP_W / 2 : e.len;
    addLine(m.edgeWhite, slice(offset(e.right, EDGE_INSET), 0, stopS));
    if (e.kind === "oneway") {
      addLine(m.sidewalks, e.left);
      addLine(m.curbs, e.left);
      addLine(m.edgeWhite, slice(offset(e.left, -EDGE_INSET), 0, stopS));
    } else if (e.kind === "divided") {
      addLine(m.edgeYellow, slice(offset(e.left, -(e.inset + (e.inset > 0 ? 0.12 : EDGE_INSET))), 0, stopS)); // pegada al bordillo
    }
    // separadores: discontinuos, continuos en los ultimos SOLID_M antes del alto
    for (let i = 0; i < e.lanes.length - 1; i++) {
      const mid = avg(e.shapes[i], e.shapes[i + 1]) ?? offset(e.shapes[i], (e.lanes[i].width || 3.2) / 2);
      const L = polyLen(mid);
      if (e.approach) {
        const end = L - STOP_BACK_M - STOP_W / 2, cut = Math.max(0, end - SOLID_M);
        addLine(m.sepDashed, slice(mid, 0, cut));
        addLine(m.sepSolid, slice(mid, cut, end));
      } else addLine(m.sepDashed, mid);
    }
    // linea de alto y flecha en cada carril con semaforo
    e.lanes.forEach((l, i) => {
      const dirs = dirsOf.get(l.id);
      if (!dirs) return;
      const sh = e.shapes[i], L = polyLen(sh), w = l.width || 3.2;
      const [x, y, dx, dy] = at(sh, L - STOP_BACK_M);
      const f = frame([x, y], [dx, dy]);
      const inner = i === e.lanes.length - 1 ? e.inset : 0;
      addLine(m.stops, [f(0, -w / 2), f(0, w / 2 - inner)]);
      const tip = L - STOP_BACK_M - ARROW_GAP;
      if (tip - ARROW_LEN > 4) {
        const [ax, ay, adx, ady] = at(sh, tip - ARROW_LEN);
        addArrow(m, frame([ax, ay], [adx, ady]), dirs);
      }
    });
    // alumbrado de las calles transversales (lado derecho)
    if (e.kind === "oneway" && e.len > 40 && (jById.has(e.to) || jById.has(e.from))) {
      const side = offset(e.right, -SIDEWALK_M * 0.55);
      for (let s = 16; s < e.len - 12; s += 32) {
        const [x, y] = at(side, jById.has(e.to) ? e.len - s : s);
        m.lamps.push({ x, y, r: 10, k: 0.85 });
      }
    }
    // nombres de las calles transversales
    if (e.kind === "oneway" && e.name && e.name !== e.id) {
      m.labels.push({ text: abbreviate(e.name), path: e.center, len: e.len, kind: "street", jEnd: jById.has(e.to) ? 1 : jById.has(e.from) ? 0 : -1 });
    }
  }

  // cruces: asfalto, banqueta redondeada, bordillo de las esquinas y postes en cada esquina
  const ends: Pt[] = [];
  for (const e of m.edges) ends.push(e.right[0], e.left[0], e.right[e.right.length - 1], e.left[e.left.length - 1]);
  for (const j of m.juncs) {
    addPoly(m.asphalt, j.poly);
    addPoly(m.junctions, j.poly);
    addPoly(m.rims, j.poly);
    const near = ends.filter((q) => Math.hypot(q[0] - j.cx, q[1] - j.cy) < j.r + 2);
    const mouth = j.poly.map((q) => near.some((e) => dist(e, q) < 0.6));
    const n = j.poly.length;
    const isCurb = (i: number) => !(mouth[i] && mouth[(i + 1) % n]);
    const start = [...Array(n).keys()].find((i) => !isCurb((i + n - 1) % n) && isCurb(i));
    if (start === undefined) {
      if (mouth.every((x) => !x)) addPoly(m.curbs, j.poly);
      continue;
    }
    let run: Pt[] = [];
    const flush = () => {
      if (run.length >= 2) {
        addLine(m.curbs, run);
        const L = polyLen(run), [x, y] = at(run, L / 2);
        const dx = x - j.cx, dy = y - j.cy, D = Math.hypot(dx, dy) || 1;
        if (L > 2) m.lamps.push({ x: x + (dx / D) * SIDEWALK_M * 0.6, y: y + (dy / D) * SIDEWALK_M * 0.6, r: 14, k: 1.2 });
      }
      run = [];
    };
    for (let k = 0; k < n; k++) {
      const i = (start + k) % n;
      if (isCurb(i)) {
        if (!run.length) run.push(j.poly[i]);
        run.push(j.poly[(i + 1) % n]);
      } else flush();
    }
    flush();
  }

  // cebras en cada boca de los cruces semaforizados (un par de sentidos opuestos = una sola cebra)
  for (const t of net.tls ?? []) {
    const j = jById.get(t.id) ?? m.juncs.find((q) => inside([t.x, t.y], q.poly));
    if (!j) continue;
    const done = new Set<EdgeGeo>();
    for (const e of m.edges) {
      if (done.has(e) || (e.to !== j.id && e.from !== j.id)) continue;
      done.add(e);
      const mouth = (q: EdgeGeo) => {
        const endSide = q.to === j.id;
        const R = endSide ? q.right[q.right.length - 1] : q.right[0];
        const Lf = endSide ? q.left[q.left.length - 1] : q.left[0];
        const [, , dx, dy] = at(q.center, endSide ? q.len : 0);
        return { R, Lf, d: (endSide ? [dx, dy] : [-dx, -dy]) as Pt };
      };
      const a = mouth(e);
      let R = a.R, Lf = a.Lf;
      const p = partner.get(e);
      if (p && (p.to === j.id || p.from === j.id)) { done.add(p); Lf = mouth(p).R; }
      addCrosswalk(m, R, Lf, a.d);
    }
  }
}

// Arriate sintetico: banda de 2*half alrededor del eje, con punta redonda donde llega a un cruce.
function addMedianNose(path: Path2D, c: Pt[], half: number, trim0: number, trim1: number): void {
  const L = polyLen(c);
  const core = slice(c, trim0 > 0 ? trim0 + half : 0, L - (trim1 > 0 ? trim1 + half : 0));
  if (core.length < 2) return;
  const lft = offset(core, half), rgt = offset(core, -half);
  path.moveTo(lft[0][0], lft[0][1]);
  for (const q of lft) path.lineTo(q[0], q[1]);
  const [ex, ey, edx, edy] = at(core, polyLen(core));
  const ae = Math.atan2(edy, edx);
  if (trim1 > 0) path.arc(ex, ey, half, ae + Math.PI / 2, ae - Math.PI / 2, true);
  for (let i = rgt.length - 1; i >= 0; i--) path.lineTo(rgt[i][0], rgt[i][1]);
  const [sx, sy, sdx, sdy] = at(core, 0);
  const as = Math.atan2(sdy, sdx);
  if (trim0 > 0) path.arc(sx, sy, half, as - Math.PI / 2, as - (3 * Math.PI) / 2, true);
  path.closePath();
}

// Franjas de cebra paralelas al transito entre las esquinas R y Lf de la boca, hacia adentro del cruce (d).
function addCrosswalk(m: RoadModel, R: Pt, Lf: Pt, d: Pt): void {
  const W = dist(R, Lf);
  if (W < 2) return;
  const lat: Pt = [(Lf[0] - R[0]) / W, (Lf[1] - R[1]) / W];
  const P = (t: number, u: number): Pt => [R[0] + lat[0] * t + d[0] * u, R[1] + lat[1] * t + d[1] * u];
  const n = Math.floor((W - 0.6 + STRIPE) / (2 * STRIPE));
  if (n < 1) return;
  const total = n * 2 * STRIPE - STRIPE, t0 = (W - total) / 2;
  const u0 = CW_GAP, u1 = CW_GAP + CROSSWALK_M;
  for (let k = 0; k < n; k++) {
    const t = t0 + k * 2 * STRIPE;
    addPoly(m.zebra, [P(t, u0), P(t + STRIPE, u0), P(t + STRIPE, u1), P(t, u1)]);
  }
  addPoly(m.zebraBands, [P(t0, u0), P(t0 + total, u0), P(t0 + total, u1), P(t0, u1)]);
}

// Flecha pintada (recto / izquierda / derecha y combinaciones) en el marco local del carril.
function addArrow(m: RoadModel, f: (u: number, v: number) => Pt, dirs: string[]): void {
  const S = dirs.some((x) => x === "s"), Lt = dirs.some((x) => "lLt".includes(x)), Rt = dirs.some((x) => "rR".includes(x));
  if (!S && !Lt && !Rt) return;
  const head = (bx: number, by: number, dx: number, dy: number, len: number, hw: number) => {
    const ux = bx + dx * len, uy = by + dy * len;
    addPoly(m.arrowHeads, [f(ux, uy), f(bx - dy * hw, by + dx * hw), f(bx + dy * hw, by - dx * hw)]);
  };
  const shaftEnd = S ? ARROW_LEN - 1.55 : 2.3;
  addLine(m.arrowShafts, [f(0, 0), f(shaftEnd, 0)]);
  if (S) head(shaftEnd - 0.05, 0, 1, 0, 1.6, 0.6);
  // rama de vuelta: sale en curva y termina con la punta casi de lado
  const branch = (side: 1 | -1) => {
    const b0 = S ? 1.3 : shaftEnd;
    const bx = b0 + 1.15, by = side * 0.55;
    addLine(m.arrowShafts, [f(b0, 0), f(b0 + 0.5, side * 0.08), f(b0 + 0.9, side * 0.28), f(bx, by)]);
    const dx = 0.42, dy = side * 0.907;
    head(bx - dx * 0.05, by - dy * 0.05, dx, dy, 1.0, 0.5);
  };
  if (Lt) branch(1);
  if (Rt) branch(-1);
}

function abbreviate(name: string): string {
  return name.replace(/^Avenida\s+/i, "Av. ").replace(/^Calzada\s+/i, "Calz. ").replace(/^Boulevard\s+|^Bulevar\s+/i, "Blvd. ");
}

// ---------------------------------------------------------------- sprites (cacheados por color)

const sprites = new Map<string, HTMLCanvasElement>();

function makeCanvas(n: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement("canvas");
  c.width = c.height = n;
  return [c, c.getContext("2d")!];
}

// Copa de arbol vista desde arriba: sombra, lobulos irregulares y brillo arriba a la izquierda.
function treeSprite(pal: Palette): HTMLCanvasElement {
  const key = `tree|${pal.tree}|${pal.treeHi}|${pal.labelHalo}`;
  let c = sprites.get(key);
  if (c) return c;
  const N = 96, R = N * 0.4, cx = N / 2, cy = N / 2;
  const [cv, g] = makeCanvas(N);
  const lobes: [number, number, number][] = [[0, 0, 0.62]];
  for (let k = 0; k < 7; k++) {
    const a = (k / 7) * Math.PI * 2 + 0.3;
    lobes.push([Math.cos(a) * 0.42, Math.sin(a) * 0.42, 0.42 + 0.08 * Math.sin(k * 2.3)]);
  }
  const blob = (dx: number, dy: number, scale: number) => {
    g.beginPath();
    for (const [x, y, r] of lobes) { g.moveTo(cx + dx + x * R * scale + r * R * scale, cy + dy + y * R * scale); g.arc(cx + dx + x * R * scale, cy + dy + y * R * scale, r * R * scale, 0, Math.PI * 2); }
    g.fill();
  };
  g.fillStyle = pal.labelHalo; g.globalAlpha = 0.45;
  blob(R * 0.12, R * 0.16, 1);
  g.globalAlpha = 1; g.fillStyle = pal.tree;
  blob(0, 0, 1);
  g.globalCompositeOperation = "source-atop";
  const hi = g.createRadialGradient(cx - R * 0.35, cy - R * 0.4, 0, cx - R * 0.2, cy - R * 0.25, R * 1.05);
  hi.addColorStop(0, pal.treeHi);
  hi.addColorStop(1, pal.tree);
  g.fillStyle = hi;
  g.fillRect(0, 0, N, N);
  g.globalAlpha = 0.35; g.fillStyle = pal.labelHalo;
  g.lineWidth = R * 0.08; g.strokeStyle = pal.labelHalo;
  for (const [x, y, r] of lobes.slice(1)) { g.beginPath(); g.arc(cx + x * R, cy + y * R, r * R, 0.2, 1.6); g.stroke(); }
  sprites.set(key, cv);
  c = cv;
  return c;
}

// Charco de luz del alumbrado (perfil suave), coloreado con pal.streetlight.
function glowSprite(color: string): HTMLCanvasElement {
  const key = `glow|${color}`;
  let c = sprites.get(key);
  if (c) return c;
  const N = 128;
  const [cv, g] = makeCanvas(N);
  const gr = g.createRadialGradient(N / 2, N / 2, 0, N / 2, N / 2, N / 2);
  gr.addColorStop(0, "rgba(255,255,255,1)");
  gr.addColorStop(0.22, "rgba(255,255,255,0.62)");
  gr.addColorStop(0.55, "rgba(255,255,255,0.2)");
  gr.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = gr;
  g.fillRect(0, 0, N, N);
  g.globalCompositeOperation = "source-in";
  g.fillStyle = color;
  g.fillRect(0, 0, N, N);
  sprites.set(key, cv);
  c = cv;
  return c;
}

// ---------------------------------------------------------------- dibujo

export interface RoadOpts {
  night: number; // 0 dia .. 1 noche
  closedLanes: Set<string>; // carriles cerrados (state.closed_lanes)
  closedEdges: Set<string>; // bordes con incidente (state.incidents); respaldo si closedLanes esta vacio
  time: number; // performance.now() en ms (animaciones sutiles)
}

function reset(g: CanvasRenderingContext2D, dpr: number): void {
  g.globalAlpha = 1;
  g.globalCompositeOperation = "source-over";
  g.setLineDash([]);
  g.shadowBlur = 0;
  applyScreen(g, dpr);
}

const onScreen = (cam: Camera, x: number, y: number, pad: number) => x > -pad && y > -pad && x < cam.w + pad && y < cam.h + pad;

// Fondo + calzadas + cruces + arriate + marcas (segun LOD) + alumbrado. Deja el contexto en applyScreen.
export function drawRoad(g: CanvasRenderingContext2D, cam: Camera, dpr: number, m: RoadModel, pal: Palette, o: RoadOpts): void {
  applyScreen(g, dpr);
  g.fillStyle = pal.ground;
  g.fillRect(0, 0, cam.w, cam.h);
  if (!m.edges.length) return;
  const px = 1 / cam.s;
  applyWorld(g, cam, dpr);
  g.lineJoin = "round";
  g.lineCap = "butt";

  // edificios: sombra corrida (sol fijo en el mundo), dos tonos y pretil de la azotea con zoom
  if (cam.s >= 2) {
    g.globalAlpha = Math.min(1, (cam.s - 2) / 1.5) * 0.5;
    g.fillStyle = pal.labelHalo;
    g.translate(1.2, -1.2);
    g.fill(m.buildings);
    g.fill(m.buildingsAlt);
    applyWorld(g, cam, dpr);
    g.globalAlpha = 1;
  }
  const bA = 0.55 + 0.45 * Math.max(0, Math.min(1, (cam.s - 1) / 1.5)); // discretos de lejos
  g.globalAlpha = bA;
  g.fillStyle = pal.building;
  g.fill(m.buildings);
  g.fill(m.buildingsAlt);
  g.globalAlpha = 0.4 * bA;
  g.fillStyle = pal.buildingEdge;
  g.fill(m.buildingsAlt);
  g.globalAlpha = 1;
  if (cam.s >= 1.6) {
    g.globalAlpha = Math.min(1, (cam.s - 1.6) / 1);
    g.strokeStyle = pal.buildingEdge;
    g.lineWidth = Math.max(0.3, MIN_PX * px);
    g.stroke(m.buildings);
    g.stroke(m.buildingsAlt);
    if (cam.s >= 4) g.stroke(m.roofs);
    g.globalAlpha = 1;
  }

  // banquetas: trazo ancho centrado en el borde exterior; el asfalto tapa la mitad interior
  g.strokeStyle = pal.sidewalk;
  g.lineWidth = Math.max(2 * SIDEWALK_M, 2.4 * px);
  g.stroke(m.sidewalks);
  g.stroke(m.rims);

  // calzada (una sola pasada para que no haya costuras) e interior de los cruces
  g.fillStyle = pal.asphalt;
  g.fill(m.asphalt);
  g.fillStyle = pal.junction;
  g.fill(m.junctions);
  g.strokeStyle = pal.curb;
  g.lineWidth = Math.max(0.25, 0.9 * px);
  g.stroke(m.curbs);

  // arriate: de lejos es una linea verde; de cerca, bordillo + relleno verde
  const far = Math.max(0, Math.min(1, (2.2 - cam.s) / 0.8));
  if (far < 1) {
    g.globalAlpha = 1 - far;
    g.fillStyle = pal.median;
    g.fill(m.medianFill);
    g.strokeStyle = pal.curb;
    g.lineWidth = Math.max(0.22, MIN_PX * px);
    g.stroke(m.medianFill);
  }
  if (far > 0) {
    g.globalAlpha = far;
    g.strokeStyle = pal.tree;
    g.lineWidth = Math.max(2 * MEDIAN_HALF, 1.6 * px);
    g.stroke(m.medianLines);
  }
  g.globalAlpha = 1;

  // marcas viales (aparecen suave a partir de LOD.markings)
  const ma = Math.max(0, Math.min(1, (cam.s - LOD.markings) / 0.6));
  if (ma > 0) {
    const lw = Math.max(LINE_M, MIN_PX * px);
    g.globalAlpha = ma;
    g.lineWidth = lw;
    g.strokeStyle = pal.marking;
    g.stroke(m.edgeWhite);
    g.stroke(m.sepSolid);
    g.setLineDash(DASH);
    g.stroke(m.sepDashed);
    g.setLineDash([]);
    g.strokeStyle = pal.markingYellow;
    g.stroke(m.edgeYellow);
    g.strokeStyle = pal.marking;
    g.lineWidth = Math.max(STOP_W, 1.2 * px);
    g.stroke(m.stops);
    g.fillStyle = pal.marking;
    const zb = Math.max(0, Math.min(1, (cam.s - 2.0) / 0.6));
    if (zb < 1) { g.globalAlpha = ma * 0.35 * (1 - zb); g.fill(m.zebraBands); }
    if (zb > 0) { g.globalAlpha = ma * 0.9 * zb; g.fill(m.zebra); }
    const aa = Math.max(0, Math.min(1, (cam.s - LOD.arrows) / 0.8));
    if (aa > 0) {
      g.globalAlpha = ma * aa * 0.85;
      g.lineWidth = Math.max(0.32, MIN_PX * px);
      g.lineJoin = "round";
      g.stroke(m.arrowShafts);
      g.fill(m.arrowHeads);
    }
    g.globalAlpha = 1;
  }

  // arboles del arriate (en pantalla: el brillo siempre arriba a la izquierda)
  applyScreen(g, dpr);
  if (cam.s >= LOD.trees && m.trees.length) {
    const spr = treeSprite(pal);
    g.globalAlpha = Math.min(1, (cam.s - LOD.trees) / 0.5);
    for (const t of m.trees) {
      const [sx, sy] = toScreen(cam, t.x, t.y);
      const r = (t.r * cam.s) / 0.8; // el sprite deja margen para la sombra
      if (!onScreen(cam, sx, sy, r)) continue;
      g.drawImage(spr, sx - r, sy - r, 2 * r, 2 * r);
    }
    g.globalAlpha = 1;
  }

  // postes de alumbrado de dia (cabeza del poste vista desde arriba)
  if (cam.s >= 2.5 && o.night < 0.98 && m.lamps.length) {
    const r = Math.max(1.4, 0.3 * cam.s);
    g.globalAlpha = Math.min(1, (cam.s - 2.5) / 1) * (1 - o.night);
    g.beginPath();
    for (const l of m.lamps) {
      const [sx, sy] = toScreen(cam, l.x, l.y);
      if (!onScreen(cam, sx, sy, 4)) continue;
      g.moveTo(sx + r, sy);
      g.arc(sx, sy, r, 0, Math.PI * 2);
    }
    g.fillStyle = pal.lampOff;
    g.fill();
    g.lineWidth = 1;
    g.strokeStyle = pal.curb;
    g.stroke();
    g.globalAlpha = 1;
  }

  // alumbrado de noche: charcos de luz calida y el foco de cada poste
  if (o.night > 0.02 && m.lamps.length) {
    const spr = glowSprite(pal.streetlight);
    g.globalCompositeOperation = "lighter";
    for (const l of m.lamps) {
      const [sx, sy] = toScreen(cam, l.x, l.y);
      const r = Math.max(6, l.r * cam.s);
      if (!onScreen(cam, sx, sy, r)) continue;
      g.globalAlpha = Math.min(1, 0.22 * o.night * l.k);
      g.drawImage(spr, sx - r, sy - r, 2 * r, 2 * r);
    }
    if (cam.s >= 1.2) {
      g.fillStyle = pal.streetlight;
      g.globalAlpha = 0.9 * o.night;
      const r = Math.max(1.1, 0.28 * cam.s);
      g.beginPath();
      for (const l of m.lamps) {
        const [sx, sy] = toScreen(cam, l.x, l.y);
        if (!onScreen(cam, sx, sy, 4)) continue;
        g.moveTo(sx + r, sy);
        g.arc(sx, sy, r, 0, Math.PI * 2);
      }
      g.fill();
    }
  }
  reset(g, dpr);
}

// ---------------------------------------------------------------- incidentes

interface IncidentGeo {
  e: EdgeGeo;
  strip: Path2D; // carriles cerrados (para recortar y contornear)
  hatch: Path2D; hatch2: Path2D; // franjas diagonales rojas / blancas
  v0: number; v1: number; // limites laterales del tramo cerrado medidos desde el borde derecho
  mid: Pt;
}

function incidentGeo(m: RoadModel, e: EdgeGeo, idx: number[]): IncidentGeo {
  const key = `${e.id}|${idx.join(",")}`;
  const hit = m.incCache.get(key);
  if (hit) return hit;
  // un poligono por grupo de carriles cerrados contiguos (el contorno no marca la linea entre ellos)
  const strip = new Path2D();
  for (let a = 0; a < idx.length;) {
    let b = a;
    while (b + 1 < idx.length && idx[b + 1] === idx[b] + 1) b++;
    const i0 = idx[a], i1 = idx[b];
    addPoly(strip, ccw([...offset(e.shapes[i0], -(e.lanes[i0].width || 3.2) / 2), ...offset(e.shapes[i1], (e.lanes[i1].width || 3.2) / 2).reverse()]));
    a = b + 1;
  }
  let v0 = Infinity, v1 = -Infinity, acc = 0;
  e.lanes.forEach((l, i) => {
    const w = l.width || 3.2;
    if (idx.includes(i)) { v0 = Math.min(v0, acc); v1 = Math.max(v1, acc + w); }
    acc += w;
  });
  // franjas a 45 grados sobre el borde, cada 2.4 m (alternando rojo / blanco)
  const base = offset(e.center, -e.width / 2);
  const span = v1 - v0, hatch = new Path2D(), hatch2 = new Path2D();
  let k = 0;
  for (let s = -span; s < e.len + span; s += 1.2, k++) {
    const [x0, y0, dx, dy] = at(base, Math.max(0, Math.min(e.len, s)));
    const f0 = frame([x0, y0], [dx, dy]);
    const a = f0(s - Math.max(0, Math.min(e.len, s)), v0 - 0.5), b = f0(s - Math.max(0, Math.min(e.len, s)) + span + 1, v1 + 0.5);
    addLine(k % 2 ? hatch2 : hatch, [a, b]);
  }
  const [mx, my] = at(e.center, e.len / 2);
  const g: IncidentGeo = { e, strip, hatch, hatch2, v0, v1, mid: [mx, my] };
  m.incCache.set(key, g);
  return g;
}

// Carriles cerrados: rayado, conos y barrera al inicio del tramo. Deja el contexto en applyScreen.
export function drawIncidents(g: CanvasRenderingContext2D, cam: Camera, dpr: number, m: RoadModel, pal: Palette, o: RoadOpts): void {
  applyScreen(g, dpr);
  const byEdge = new Map<EdgeGeo, number[]>();
  if (o.closedLanes.size) {
    for (const id of o.closedLanes) {
      const r = m.laneOf.get(id);
      if (!r) continue;
      const arr = byEdge.get(r.e) ?? [];
      if (!arr.includes(r.i)) arr.push(r.i);
      byEdge.set(r.e, arr);
    }
  } else {
    for (const id of o.closedEdges) {
      const e = m.edges.find((q) => q.id === id);
      if (!e) continue;
      const idx = e.lanes.length > 1 ? e.lanes.map((_, i) => i).slice(0, -1) : [0];
      byEdge.set(e, idx);
    }
  }
  m.icons = [];
  if (!byEdge.size) return;
  const px = 1 / cam.s;
  const far = cam.s < 1.4;
  const blink = 0.5 + 0.5 * Math.sin((o.time / 1000) * Math.PI * 2 * 1.1);
  const items = [...byEdge].map(([e, idx]) => incidentGeo(m, e, idx.sort((a, b) => a - b)));

  applyWorld(g, cam, dpr);
  for (const it of items) {
    g.save();
    g.clip(it.strip);
    g.globalAlpha = 0.2;
    g.fillStyle = pal.closed;
    g.fill(it.strip);
    g.lineCap = "butt";
    g.lineWidth = Math.max(0.55, MIN_PX * px);
    g.globalAlpha = far ? 0.35 : 0.55;
    g.strokeStyle = pal.closed;
    g.stroke(it.hatch);
    g.globalAlpha = far ? 0.15 : 0.3;
    g.strokeStyle = pal.coneStripe;
    g.stroke(it.hatch2);
    g.restore();
    g.strokeStyle = pal.closed;
    g.lineJoin = "round";
    if (far) {
      g.globalAlpha = 0.95;
      g.lineWidth = 2.5 * px;
      g.setLineDash([7 * px, 4 * px]);
    } else {
      g.globalAlpha = 0.8;
      g.lineWidth = Math.max(0.2, MIN_PX * px);
    }
    g.stroke(it.strip);
    g.setLineDash([]);
    g.globalAlpha = 1;
  }

  if (cam.s >= 2.4) { // de cerca: barrera y conos (mas lejos serian una linea de puntos)
    for (const it of items) drawBarrierAndCones(g, cam, dpr, it, pal, blink);
  }

  applyScreen(g, dpr);
  // de lejos: triangulo de advertencia en el centro del tramo
  const tri = Math.max(0, Math.min(1, (2.2 - cam.s) / 0.8));
  if (tri > 0) {
    for (const it of items) {
      m.icons.push(it.mid);
      const [sx, sy] = toScreen(cam, it.mid[0], it.mid[1]);
      if (!onScreen(cam, sx, sy, 20)) continue;
      warningIcon(g, sx, sy - 2, pal, tri, blink);
    }
  }
  reset(g, dpr);
}

function drawBarrierAndCones(g: CanvasRenderingContext2D, cam: Camera, dpr: number, it: IncidentGeo, pal: Palette, blink: number): void {
  const e = it.e, base = offset(e.center, -e.width / 2);
  const sB = Math.min(3.2, e.len * 0.2);
  const [bx, by, bdx, bdy] = at(base, sB);
  const f = frame([bx, by], [bdx, bdy]);
  // barrera: barra a rayas naranja / blanco de lado a lado de los carriles cerrados
  applyWorld(g, cam, dpr);
  const T = 0.55, seg = 0.75;
  g.fillStyle = pal.housing;
  g.globalAlpha = 0.85;
  g.beginPath();
  const q = [f(-T / 2 - 0.08, it.v0 + 0.15), f(T / 2 + 0.08, it.v0 + 0.15), f(T / 2 + 0.08, it.v1 - 0.15), f(-T / 2 - 0.08, it.v1 - 0.15)];
  g.moveTo(q[0][0], q[0][1]); for (const p of q.slice(1)) g.lineTo(p[0], p[1]); g.closePath();
  g.fill();
  g.globalAlpha = 1;
  let k = 0;
  for (let v = it.v0 + 0.25; v < it.v1 - 0.25; v += seg, k++) {
    const v2 = Math.min(it.v1 - 0.25, v + seg);
    g.fillStyle = k % 2 ? pal.coneStripe : pal.cone;
    g.beginPath();
    const r = [f(-T / 2, v), f(T / 2, v), f(T / 2, v2), f(-T / 2, v2)];
    g.moveTo(r[0][0], r[0][1]); for (const p of r.slice(1)) g.lineTo(p[0], p[1]); g.closePath();
    g.fill();
  }

  // conos en pantalla (tamano minimo legible): linea entre carriles cerrados y abiertos + junto a la barrera
  applyScreen(g, dpr);
  const cones: Pt[] = [];
  const vLine = it.v1 < e.width - 0.1 ? it.v1 - 0.45 : it.v0 + 0.45;
  for (let s = sB + 4; s < e.len - 6; s += s < 35 ? 5 : 15) {
    const [x, y, dx, dy] = at(base, s);
    cones.push(frame([x, y], [dx, dy])(0, vLine));
  }
  for (let v = it.v0 + 0.8; v < it.v1 - 0.5; v += 1.6) cones.push(f(-1.2, v));
  const r = Math.max(2.6, 0.4 * cam.s);
  for (const [x, y] of cones) {
    const [sx, sy] = toScreen(cam, x, y);
    if (!onScreen(cam, sx, sy, r + 2)) continue;
    g.fillStyle = pal.labelHalo;
    g.globalAlpha = 0.35;
    g.beginPath(); g.arc(sx + r * 0.25, sy + r * 0.3, r * 1.05, 0, Math.PI * 2); g.fill();
    g.globalAlpha = 1;
    g.fillStyle = pal.cone;
    g.beginPath(); g.arc(sx, sy, r, 0, Math.PI * 2); g.fill();
    if (r >= 3) {
      g.strokeStyle = pal.coneStripe;
      g.lineWidth = Math.max(0.8, r * 0.22);
      g.beginPath(); g.arc(sx, sy, r * 0.55, 0, Math.PI * 2); g.stroke();
      g.fillStyle = pal.cone;
      g.beginPath(); g.arc(sx, sy, r * 0.22, 0, Math.PI * 2); g.fill();
    }
  }

  // luces ambar intermitentes en los extremos de la barrera
  const glow = glowSprite(pal.yellow);
  for (const v of [it.v0 + 0.35, it.v1 - 0.35]) {
    const [sx, sy] = toScreen(cam, ...f(0, v));
    if (!onScreen(cam, sx, sy, 30)) continue;
    const gr = Math.max(7, 2.2 * cam.s);
    g.globalCompositeOperation = "lighter";
    g.globalAlpha = 0.25 + 0.6 * blink;
    g.drawImage(glow, sx - gr, sy - gr, 2 * gr, 2 * gr);
    g.globalCompositeOperation = "source-over";
    g.globalAlpha = 0.45 + 0.55 * blink;
    g.fillStyle = pal.yellow;
    g.beginPath(); g.arc(sx, sy, Math.max(1.6, 0.22 * cam.s), 0, Math.PI * 2); g.fill();
  }
  g.globalAlpha = 1;
}

function warningIcon(g: CanvasRenderingContext2D, x: number, y: number, pal: Palette, a: number, blink: number): void {
  const s = 11;
  g.globalAlpha = a;
  g.lineJoin = "round";
  g.beginPath();
  g.moveTo(x, y - s);
  g.lineTo(x + s * 1.1, y + s * 0.8);
  g.lineTo(x - s * 1.1, y + s * 0.8);
  g.closePath();
  g.lineWidth = 4;
  g.strokeStyle = pal.labelHalo;
  g.stroke();
  g.fillStyle = pal.closed;
  g.fill();
  g.lineWidth = 1.2;
  g.strokeStyle = pal.coneStripe;
  g.globalAlpha = a * (0.55 + 0.45 * blink);
  g.stroke();
  g.globalAlpha = a;
  g.fillStyle = pal.coneStripe;
  g.font = `800 11px ${FONT}`;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText("!", x, y + s * 0.18);
}

// ---------------------------------------------------------------- nombres de calles

const widths = new Map<string, number>();
interface Box { x0: number; y0: number; x1: number; y1: number; }
const hits = (a: Box, b: Box) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

// Caja en pantalla (px CSS) que los nombres deben esquivar, p. ej. las tarjetas de los cruces.
export interface ScreenBox { x: number; y: number; w: number; h: number; }

// Zonas que los nombres no deben tapar: cada cruce, las tarjetas (las del cuadro anterior si NetCanvas
// las pasa; si no, una estimacion encima del corredor), los iconos de incidente y la brujula.
function reserved(cam: Camera, m: RoadModel, avoid?: ScreenBox[]): Box[] {
  const out: Box[] = [{ x0: cam.w - 56, y0: 0, x1: cam.w, y1: 56 }];
  for (const t of m.net.tls ?? []) {
    const j = m.juncs.find((q) => q.id === t.id);
    const [sx, sy] = toScreen(cam, j?.cx ?? t.x, j?.cy ?? t.y);
    const r = Math.max(18, (j?.r ?? 12) * cam.s + 6);
    out.push({ x0: sx - r, y0: sy - r, x1: sx + r, y1: sy + r });
    if (!avoid) out.push({ x0: sx - 88, y0: sy - r - 66, x1: sx + 88, y1: sy - r + 6 });
  }
  for (const b of avoid ?? []) out.push({ x0: b.x - 4, y0: b.y - 4, x1: b.x + b.w + 4, y1: b.y + b.h + 4 });
  for (const [x, y] of m.icons) {
    const [sx, sy] = toScreen(cam, x, y);
    out.push({ x0: sx - 16, y0: sy - 16, x1: sx + 16, y1: sy + 14 });
  }
  return out;
}

// Nombres de calles en pantalla (texto derecho, sin choques). Deja el contexto en applyScreen.
// `avoid` (opcional): cajas de las tarjetas de los cruces (BadgeHit[] del cuadro anterior).
export function drawStreetLabels(g: CanvasRenderingContext2D, cam: Camera, dpr: number, m: RoadModel, pal: Palette, avoid?: ScreenBox[]): void {
  applyScreen(g, dpr);
  if (!m.labels.length) return;
  const size = Math.round(Math.max(11, Math.min(14, 11.5 + 1.3 * Math.log2(Math.max(0.5, cam.s)))));
  g.font = `600 ${size}px ${FONT}`;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.lineJoin = "round";
  const taken = reserved(cam, m, avoid);
  for (const lb of m.labels) {
    const wk = `${size}|${lb.text}`;
    let tw = widths.get(wk);
    if (tw === undefined) { tw = g.measureText(lb.text).width; widths.set(wk, tw); }
    const cands: number[] = [];
    if (lb.kind === "avenue") {
      if (lb.len * cam.s < tw + 40) continue; // tramo muy corto en pantalla
      for (const f of [0.5, 0.33, 0.67, 0.2, 0.8]) cands.push(f * lb.len);
    } else {
      // primero a distancias fijas en pantalla desde el cruce, luego a fracciones del tramo
      const minD = Math.max(22, (tw / 2 + 30) / cam.s);
      const ds = [tw / 2 + 46, tw / 2 + 96, tw / 2 + 150].map((p) => p / cam.s).concat([0.45, 0.65, 0.85].map((f) => f * lb.len));
      for (const d0 of ds) {
        const d = Math.max(minD, d0);
        if (d > lb.len - tw / 2 / cam.s) continue;
        cands.push(lb.jEnd === 1 ? lb.len - d : lb.jEnd === 0 ? d : lb.len / 2);
      }
    }
    for (const s of cands) {
      if (lb.kind === "avenue" && Math.min(s, lb.len - s) * cam.s < tw / 2 + 14) continue;
      const [x, y, dx, dy] = at(lb.path, s);
      const [sx, sy] = toScreen(cam, x, y);
      if (sx < 30 || sy < 14 || sx > cam.w - 30 || sy > cam.h - 14) continue;
      let [ux, uy] = screenDir(cam, dx, dy);
      if (ux < -1e-3 || (Math.abs(ux) <= 1e-3 && uy > 0)) { ux = -ux; uy = -uy; }
      const hw = tw / 2 + 5, hh = size / 2 + 3;
      const ex = Math.abs(ux) * hw + Math.abs(uy) * hh, ey = Math.abs(uy) * hw + Math.abs(ux) * hh;
      const box = { x0: sx - ex, y0: sy - ey, x1: sx + ex, y1: sy + ey };
      if (box.x0 < 8 || box.y0 < 8 || box.x1 > cam.w - 8 || box.y1 > cam.h - 8) continue; // entero en el lienzo
      if (taken.some((b) => hits(b, box))) continue;
      taken.push(box);
      g.setTransform(dpr * ux, dpr * uy, -dpr * uy, dpr * ux, dpr * sx, dpr * sy);
      g.lineWidth = 3.5;
      g.strokeStyle = pal.labelHalo;
      g.globalAlpha = 0.85;
      g.strokeText(lb.text, 0, 0.5);
      g.globalAlpha = 1;
      g.fillStyle = pal.label;
      g.fillText(lb.text, 0, 0.5);
      applyScreen(g, dpr);
      break;
    }
  }
  reset(g, dpr);
}

// Rosa de los vientos (flecha N) centrada en (x, y) de pantalla, girada con la camara.
export function drawCompass(g: CanvasRenderingContext2D, cam: Camera, dpr: number, pal: Palette, x: number, y: number): void {
  applyScreen(g, dpr);
  const r = 15;
  g.beginPath();
  g.arc(x, y, r, 0, Math.PI * 2);
  g.fillStyle = pal.badgeBg;
  g.fill();
  g.lineWidth = 1;
  g.strokeStyle = pal.badgeBorder;
  g.stroke();
  const [nx, ny] = screenDir(cam, 0, 1);
  // marco con "arriba" = norte
  g.setTransform(dpr * -ny, dpr * nx, dpr * -nx, dpr * -ny, dpr * x, dpr * y);
  g.beginPath();
  g.moveTo(0, -r + 2);
  g.lineTo(4.2, -r + 8.5);
  g.lineTo(-4.2, -r + 8.5);
  g.closePath();
  g.fillStyle = pal.red;
  g.fill();
  g.beginPath();
  g.moveTo(0, r - 2.5);
  g.lineTo(2.6, r - 6.5);
  g.lineTo(-2.6, r - 6.5);
  g.closePath();
  g.fillStyle = pal.badgeMuted;
  g.fill();
  applyScreen(g, dpr);
  g.font = `700 10px ${FONT}`;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillStyle = pal.badgeText;
  g.fillText("N", x, y + 0.5);
  reset(g, dpr);
}
