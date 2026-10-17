// Semaforos: barra de color en la linea de alto de cada carril, semaforo fisico (caja con luces
// roja/ambar/verde y flecha de vuelta) en cada aproximacion, tarjeta por cruce con el estado de
// cada eje y el tiempo en la fase, y destello al cambiar de fase.
import type { Network } from "../types";
import { edgeOfLane } from "../network";
import { applyScreen, principalAxis, screenDir, toScreen, type Camera } from "./camera";
import { CAR, DAY, FONT, LOD, NIGHT, STOP_BACK_M, palette, type Palette } from "./theme";

export type Lamp = "G" | "Y" | "R" | "O"; // verde, amarillo, rojo, apagado/desconocido

type Pt = [number, number];

// Carril controlado de una aproximacion: punto de la linea de alto (mundo) y sus enlaces.
export interface ApproachLane {
  id: string;
  index: number; // indice SUMO (0 = carril de la derecha)
  x: number; y: number; // linea de alto (fin del carril menos STOP_BACK_M)
  ex: number; ey: number; // fin del carril (borde del cruce)
  w: number;
  idx: number[];
  dirs: string[];
}

// Aproximacion = borde que entra al cruce, con sus carriles controlados.
export interface Approach {
  edge: string;
  name: string;
  axis: 0 | 1; // 0 = eje del corredor, 1 = transversal
  lanes: ApproachLane[]; // ordenados por indice
  ux: number; uy: number; // sentido de marcha (unitario, mundo)
  nx: number; ny: number; // normal hacia la derecha del sentido de marcha
  cx: number; cy: number; // centro de la linea de alto (entre bordes interior y exterior)
  ox: number; oy: number; // borde exterior (derecho) de la calzada en la linea de alto
  width: number; // ancho total de los carriles controlados
  straight: number[]; // enlaces rectos (o todos si no hay rectos)
  left: number[]; // enlaces de vuelta izquierda (y U)
}

export interface SignalAxis {
  label: string;
  idx: number[];
  aps: number[]; // indices (en SignalTls.approaches) de las aproximaciones de este eje
}

export interface SignalTls {
  id: string;
  name: string;
  short: string; // "Reforma y 12 calle" -> "12 calle"
  x: number; y: number;
  axes: SignalAxis[]; // [corredor, transversal] (solo los que tienen enlaces)
  approaches: Approach[];
  junction: Pt[]; // poligono del cruce (o las lineas de alto si no hay)
}

// Geometria y agrupacion precalculadas (opaca para quien llama).
export interface SignalModel {
  net: Network;
  tls: SignalTls[];
  // Lo que las tarjetas no deben tapar, en el mundo. Tramos [x0, y0, x1, y1, peso por metro]: colas
  // (carriles que llegan a un semaforo, cerca del alto) y el resto de carriles con poco peso.
  // Puntos [x, y, peso]: semaforos fisicos y lineas de alto.
  obsSegs: Float32Array;
  obsPts: Float32Array;
}

const STOP_BAR_M = 0.6; // grosor de la barra de color en el mundo

function laneIndex(id: string): number {
  const m = id.match(/_(\d+)$/);
  return m ? parseInt(m[1], 10) : 0;
}

function shortStreet(name: string): string {
  return name.replace(/^(avenida|av\.?|calzada|bulevar|boulevard|blvd\.?)\s+((la|el|los|las)\s+)?/i, "").trim();
}

function shortTls(name: string): string {
  const m = name.match(/\s+y\s+(.+)$/i);
  return (m ? m[1] : name).trim();
}

// Punto a `d` metros antes del final de la polilinea y direccion del ultimo tramo util.
function endFrame(shape: Pt[], d: number): { x: number; y: number; ux: number; uy: number } | null {
  if (shape.length < 2) return null;
  let total = 0;
  for (let i = 1; i < shape.length; i++) total += Math.hypot(shape[i][0] - shape[i - 1][0], shape[i][1] - shape[i - 1][1]);
  let rem = Math.min(d, total * 0.5);
  let px = shape[shape.length - 1][0], py = shape[shape.length - 1][1], ux = 0, uy = 0;
  for (let i = shape.length - 1; i > 0; i--) {
    const [x1, y1] = shape[i], [x0, y0] = shape[i - 1];
    const L = Math.hypot(x1 - x0, y1 - y0);
    if (L < 1e-6) continue;
    if (!ux && !uy && (L > 0.5 || i === 1)) { ux = (x1 - x0) / L; uy = (y1 - y0) / L; }
    if (rem <= L) { px = x1 - ((x1 - x0) * rem) / L; py = y1 - ((y1 - y0) * rem) / L; rem = 0; break; }
    rem -= L;
  }
  if (!ux && !uy) return null;
  return { x: px, y: py, ux, uy };
}

export function buildSignalModel(net: Network): SignalModel {
  const laneById = new Map(net.lanes.map((l) => [l.id, l]));
  const edgeName = new Map(net.edges.map((e) => [e.id, e.name]));
  const { angle } = principalAxis(net);
  const ca = Math.cos(angle), sa = Math.sin(angle);
  const tls: SignalTls[] = [];
  const approachLanes = new Set<string>();

  for (const t of net.tls) {
    const byEdge = new Map<string, ApproachLane[]>();
    const dirOf = new Map<string, Pt>();
    for (const c of t.controlled ?? []) {
      if (!c || !Array.isArray(c.idx)) continue;
      const lane = laneById.get(c.lane);
      const w = lane?.width ?? 3.2;
      let f = lane ? endFrame(lane.shape, STOP_BACK_M) : null;
      let ex = c.x, ey = c.y;
      if (lane && f) { const e = lane.shape[lane.shape.length - 1]; ex = e[0]; ey = e[1]; }
      if (!f) { // sin geometria: direccion hacia el centro del cruce
        const dx = t.x - c.x, dy = t.y - c.y, L = Math.hypot(dx, dy) || 1;
        f = { x: c.x - (dx / L) * STOP_BACK_M, y: c.y - (dy / L) * STOP_BACK_M, ux: dx / L, uy: dy / L };
      }
      const edge = lane?.edge ?? edgeOfLane(c.lane);
      approachLanes.add(c.lane);
      const arr = byEdge.get(edge) ?? [];
      arr.push({
        id: c.lane, index: laneIndex(c.lane), x: f.x, y: f.y, ex, ey, w,
        idx: c.idx.slice(), dirs: c.idx.map((_, i) => (c.dirs?.[i] || "s")),
      });
      byEdge.set(edge, arr);
      const d = dirOf.get(edge) ?? [0, 0];
      dirOf.set(edge, [d[0] + f.ux, d[1] + f.uy]);
    }

    const approaches: Approach[] = [];
    for (const [edge, lanes] of byEdge) {
      lanes.sort((a, b) => a.index - b.index);
      const d = dirOf.get(edge)!;
      const L = Math.hypot(d[0], d[1]) || 1;
      const ux = d[0] / L, uy = d[1] / L, nx = uy, ny = -ux;
      // bordes exterior (derecha) e interior a lo largo de la normal
      let lo = Infinity, hi = -Infinity, mx = 0, my = 0;
      for (const l of lanes) { mx += l.x; my += l.y; }
      mx /= lanes.length; my /= lanes.length;
      for (const l of lanes) {
        const o = (l.x - mx) * nx + (l.y - my) * ny;
        lo = Math.min(lo, o - l.w / 2); hi = Math.max(hi, o + l.w / 2);
      }
      const mid = (lo + hi) / 2;
      const straight: number[] = [], left: number[] = [], all: number[] = [];
      for (const l of lanes) l.idx.forEach((k, i) => {
        all.push(k);
        const dd = l.dirs[i];
        if (dd === "s") straight.push(k);
        else if (dd === "l" || dd === "L" || dd === "t") left.push(k);
      });
      const axis: 0 | 1 = Math.abs(ux * ca + uy * sa) >= Math.SQRT1_2 ? 0 : 1;
      approaches.push({
        edge, name: edgeName.get(edge) ?? "", axis, lanes, ux, uy, nx, ny,
        cx: mx + nx * mid, cy: my + ny * mid, ox: mx + nx * hi, oy: my + ny * hi, width: hi - lo,
        straight: straight.length ? straight : all, left,
      });
    }

    const axes: SignalAxis[] = [];
    for (const a of [0, 1] as const) {
      const aps = approaches.filter((p) => p.axis === a);
      if (!aps.length) continue;
      const counts = new Map<string, number>();
      for (const p of aps) {
        const n = p.name && p.name !== p.edge ? shortStreet(p.name) : "";
        if (n) counts.set(n, (counts.get(n) ?? 0) + p.lanes.length);
      }
      let label = "";
      let best = 0;
      for (const [n, c] of counts) if (c > best) { best = c; label = n; }
      axes.push({
        label: label || (a === 0 ? "Eje A" : "Eje B"), idx: aps.flatMap((p) => p.straight),
        aps: aps.map((p) => approaches.indexOf(p)),
      });
    }

    const jn = net.junctions?.find((j) => j.id === t.id);
    const junction: Pt[] = jn && jn.shape.length >= 3
      ? jn.shape
      : approaches.flatMap((p) => p.lanes.map((l): Pt => [l.ex, l.ey]));
    if (!junction.length) junction.push([t.x, t.y]);
    tls.push({ id: t.id, name: t.name, short: shortTls(t.name || t.id), x: t.x, y: t.y, axes, approaches, junction });
  }

  // Lo que las tarjetas evitan: tramos de <= 10 m de cada carril, con mas peso en las colas (carriles
  // que llegan a un semaforo, cerca del alto), y puntos en los semaforos fisicos y las lineas de alto.
  const segs: number[] = [];
  const SEG = 10;
  for (const l of net.lanes) {
    const near = approachLanes.has(l.id);
    let acc = 0;
    for (let i = l.shape.length - 1; i > 0; i--) {
      const [x1, y1] = l.shape[i], [x0, y0] = l.shape[i - 1];
      const L = Math.hypot(x1 - x0, y1 - y0);
      if (L < 1e-6) continue;
      const n = Math.ceil(L / SEG);
      for (let k = 0; k < n; k++) {
        const a = k / n, b = (k + 1) / n, dist = acc + (a + b) * L / 2;
        const w = near ? (dist < 70 ? 0.75 : dist < 140 ? 0.375 : 0.15) : 0.0625;
        segs.push(x1 - (x1 - x0) * a, y1 - (y1 - y0) * a, x1 - (x1 - x0) * b, y1 - (y1 - y0) * b, w);
      }
      acc += L;
    }
  }
  const pts: number[] = [];
  for (const t of tls) {
    for (const a of t.approaches) {
      pts.push(a.cx, a.cy, 4);
      pts.push(a.ox + a.ux * 1.3 + a.nx * 1.5, a.oy + a.uy * 1.3 + a.ny * 1.5, 5); // poste y caja
    }
  }
  return { net, tls, obsSegs: new Float32Array(segs), obsPts: new Float32Array(pts) };
}

// ---------------------------------------------------------------- estados

function charLamp(c: string | undefined): Lamp {
  switch (c) {
    case "G": case "g": return "G";
    case "y": case "Y": case "u": return "Y";
    case "r": case "R": case "s": return "R";
    default: return "O";
  }
}

// Luz de un grupo de enlaces: verde si alguno esta en verde, si no amarillo, si no rojo.
export function lampOf(state: string | undefined, idx: number[]): Lamp {
  if (!state) return "O";
  let y = false, r = false;
  for (const i of idx) {
    const l = charLamp(state[i]);
    if (l === "G") return "G";
    if (l === "Y") y = true;
    else if (l === "R") r = true;
  }
  return y ? "Y" : r ? "R" : "O";
}

// Luz principal (recto) y flecha de vuelta izquierda de una aproximacion. La flecha se enciende con
// vuelta protegida (G) o con vuelta en verde mientras el recto no lo esta.
export function approachLamps(state: string | undefined, a: Approach): { ball: Lamp; arrow: Lamp | null } {
  const ball = lampOf(state, a.straight);
  if (!a.left.length) return { ball, arrow: null };
  const l = lampOf(state, a.left);
  const prot = !!state && a.left.some((k) => state[k] === "G");
  const arrow: Lamp = prot || (l === "G" && ball !== "G") ? "G" : l === "Y" && ball !== "Y" ? "Y" : "O";
  return { ball, arrow };
}

// Luz de cada eje del cruce.
export function axisLamps(t: SignalTls, state: string | undefined): Lamp[] {
  return t.axes.map((a) => lampOf(state, a.idx));
}

function lampColor(l: Lamp, pal: Palette): string {
  return l === "G" ? pal.green : l === "Y" ? pal.yellow : l === "R" ? pal.red : pal.lampOff;
}

interface Track {
  lamps: Lamp[]; // por eje: verde si alguna aproximacion del eje esta en verde (fila activa)
  app: Lamp[]; // por aproximacion (luz del recto), en el orden de SignalTls.approaches
  phaseStart: number; // tiempo simulado del ultimo cambio de alguna aproximacion
  changedAtNow: number; // performance.now() de ese cambio (-inf si no hubo)
  flash: Lamp; // luz nueva que provoco el ultimo cambio (verde si alguna aproximacion paso a verde)
  exact: boolean; // false: se empezo a observar a media fase (no se muestra el temporizador)
}

interface CardLayout {
  id: string; x: number; y: number; w: number; h: number; ax: number; ay: number;
  compact: boolean;
  leader: boolean; // linea guia al cruce (no, si el cruce llena la vista y la tarjeta va en una esquina)
}

// Sigue los cambios de cada semaforo entre mensajes: color de cada aproximacion y eje y cuando
// cambio (tiempo simulado y performance.now) para el temporizador y el destello. Una fase con
// adelanto/retraso (un sentido de Reforma en verde y el otro en rojo) tambien cuenta como cambio.
export class SignalTracker {
  tracks = new Map<string, Track>();
  lastT: number | null = null;
  // caches de dibujo por lienzo (dependen de la camara)
  layoutCam: Camera | null = null;
  layoutCompact = false;
  layout: CardLayout[] = [];
  prevCand = new Map<string, number>();
  obsCam: Camera | null = null;
  obsSegXY: Float32Array = new Float32Array(0);
  obsPtXY: Float32Array = new Float32Array(0);

  constructor(public model: SignalModel) {}

  // Llamar una vez por mensaje de estado nuevo (t = tiempo simulado del mensaje).
  update(t: number, states: Record<string, string> | undefined, now: number): void {
    if (!states) return;
    if (this.lastT !== null && t < this.lastT - 0.5) this.tracks.clear(); // reinicio o vuelta del episodio
    this.lastT = t;
    for (const tl of this.model.tls) {
      const st = states[tl.id];
      const lamps = axisLamps(tl, st);
      const app = tl.approaches.map((a) => lampOf(st, a.straight));
      const tr = this.tracks.get(tl.id);
      if (!tr) {
        this.tracks.set(tl.id, { lamps, app, phaseStart: t, changedAtNow: -Infinity, flash: "O", exact: t <= 1.5 });
        continue;
      }
      let changed = false;
      let flash: Lamp = "O";
      for (let i = 0; i < app.length; i++) {
        if (app[i] === tr.app[i]) continue;
        changed = true;
        if (app[i] === "G") flash = "G";
        else if (app[i] === "Y" && flash !== "G") flash = "Y";
        else if (flash === "O") flash = app[i];
      }
      tr.lamps = lamps;
      if (changed) {
        tr.app = app; tr.phaseStart = t; tr.changedAtNow = now; tr.flash = flash; tr.exact = true;
      }
    }
  }

  reset(): void {
    this.tracks.clear();
    this.lastT = null;
    this.layoutCam = null;
    this.prevCand.clear();
  }

  get(id: string): Track | undefined { return this.tracks.get(id); }
}

export interface SignalOpts {
  night: number; // 0 dia .. 1 noche
  accent: string; // color del panel (fijo naranja, RL verde agua) para destellos
  side: "fijo" | "rl";
  now: number; // performance.now() ms
  simT: number; // tiempo simulado actual (s)
}

// Caja clicable de una tarjeta de cruce (px CSS del lienzo).
export interface BadgeHit { id: string; x: number; y: number; w: number; h: number; }

// ---------------------------------------------------------------- sprites

// Brillo radial de un color (blanco -> transparente, tenido con source-in). Uno por color.
const glowCache = new Map<string, HTMLCanvasElement>();
function glowSprite(color: string): HTMLCanvasElement {
  let c = glowCache.get(color);
  if (c) return c;
  c = document.createElement("canvas");
  c.width = c.height = 64;
  const x = c.getContext("2d")!;
  const gr = x.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, "rgba(255,255,255,1)");
  gr.addColorStop(0.18, "rgba(255,255,255,0.75)");
  gr.addColorStop(0.45, "rgba(255,255,255,0.22)");
  gr.addColorStop(1, "rgba(255,255,255,0)");
  x.fillStyle = gr;
  x.fillRect(0, 0, 64, 64);
  x.globalCompositeOperation = "source-in";
  x.fillStyle = color;
  x.fillRect(0, 0, 64, 64);
  if (glowCache.size > 256) glowCache.clear();
  glowCache.set(color, c);
  return c;
}

// Grado de noche (0..1) de una paleta de palette(night): se recupera del color de las marcas, que
// cambia mucho entre DAY y NIGHT (drawStopBars no recibe opciones).
const nightCache = new WeakMap<Palette, number>();
function rgb(c: string): number[] {
  if (c.startsWith("#")) return [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
  const m = c.match(/rgba?\(([^)]+)\)/);
  return m ? m[1].split(",").map((x) => parseFloat(x)) : [0, 0, 0];
}
function nightOf(pal: Palette): number {
  let v = nightCache.get(pal);
  if (v === undefined) {
    const a = rgb(DAY.marking), b = rgb(NIGHT.marking), c = rgb(pal.marking);
    const d = a[0] + a[1] + a[2] - b[0] - b[1] - b[2];
    v = d ? Math.max(0, Math.min(1, (a[0] + a[1] + a[2] - c[0] - c[1] - c[2]) / d)) : 0;
    nightCache.set(pal, v);
  }
  return v;
}

function smooth(a: number, b: number, v: number): number {
  const t = Math.max(0, Math.min(1, (v - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

// Contexto en pantalla girado: eje x local = (dx, dy) en pantalla, eje y local = su derecha.
function setFrame(g: CanvasRenderingContext2D, dpr: number, x: number, y: number, dx: number, dy: number): void {
  g.setTransform(dpr * dx, dpr * dy, -dpr * dy, dpr * dx, dpr * x, dpr * y);
}

function resetCtx(g: CanvasRenderingContext2D, dpr: number): void {
  applyScreen(g, dpr);
  g.globalAlpha = 1;
  g.globalCompositeOperation = "source-over";
  g.shadowBlur = 0;
  g.shadowColor = "transparent";
  g.setLineDash([]);
}

// ---------------------------------------------------------------- barras de alto

// Barras de color en la linea de alto de cada carril controlado (siempre visibles).
export function drawStopBars(g: CanvasRenderingContext2D, cam: Camera, dpr: number, m: SignalModel,
  states: Record<string, string> | undefined, pal: Palette, night = nightOf(pal)): void {
  resetCtx(g, dpr);
  if (!states || !m.tls.length) return;
  const s = cam.s;
  const far = 1 - smooth(LOD.markings * 0.8, LOD.markings, s); // 1 = vista lejana (sin lineas pintadas)
  const thick = Math.max(STOP_BAR_M * s, 3 + 1.8 * far);
  const minLen = 12 + 6 * far; // px: largo minimo de la barra de una aproximacion
  // Lejos las barras se corren hacia el cruce para que la cola no las tape (los carros tienen un
  // tamano minimo en pantalla y se detienen junto al borde del cruce).
  const half = Math.max(CAR.minLenPx, CAR.length * s) / 2;
  const shift = far * (STOP_BACK_M * s + Math.max(0, half - 1.0 * s) + thick / 2 + 1);
  const margin = 40;
  // brillo: de noche siempre; de dia solo lejos, para distinguir las luces de los carros con freno
  const glowA = Math.max(night > 0.02 ? 0.55 * night : 0, 0.36 * far);
  const bars: { x: number; y: number; dx: number; dy: number; segs: { o: number; len: number; c: string }[]; len: number }[] = [];

  for (const t of m.tls) {
    const st = states[t.id];
    for (const a of t.approaches) {
      const [cx0, cy0] = toScreen(cam, a.cx, a.cy);
      if (cx0 < -margin || cy0 < -margin || cx0 > cam.w + margin || cy0 > cam.h + margin) continue;
      const [dx, dy] = screenDir(cam, a.ux, a.uy);
      const full = a.width * s;
      const k = Math.max(1, minLen / Math.max(1e-6, full));
      const segs = a.lanes.map((l) => {
        const o = ((l.x - a.cx) * a.nx + (l.y - a.cy) * a.ny) * s * k;
        const gap = k > 1.6 ? Math.min(1.2, (l.w * s * k) * 0.12) : 0.14 * l.w * s;
        return { o, len: Math.max(1, l.w * s * k - gap), c: lampColor(lampOf(st, l.idx), pal) };
      });
      bars.push({ x: cx0 + dx * shift, y: cy0 + dy * shift, dx, dy, segs, len: full * k });
    }
  }

  // contorno oscuro (contraste sobre asfalto y carros) solo de lejos
  if (far > 0) {
    g.fillStyle = pal.labelHalo;
    g.globalAlpha = 0.85 * far;
    const o = 1.6;
    for (const b of bars) {
      setFrame(g, dpr, b.x, b.y, b.dx, b.dy);
      g.beginPath();
      g.roundRect(-thick / 2 - o, -b.len / 2 - o, thick + 2 * o, b.len + 2 * o, 2.5);
      g.fill();
    }
    g.globalAlpha = 1;
  }
  for (const b of bars) {
    setFrame(g, dpr, b.x, b.y, b.dx, b.dy);
    for (const sg of b.segs) {
      g.fillStyle = sg.c;
      g.fillRect(-thick / 2, sg.o - sg.len / 2, thick, sg.len);
    }
  }
  if (glowA > 0) {
    g.globalCompositeOperation = "lighter";
    g.globalAlpha = glowA;
    for (const b of bars) {
      setFrame(g, dpr, b.x, b.y, b.dx, b.dy);
      for (const sg of b.segs) {
        if (sg.c === pal.lampOff) continue;
        const gw = thick * (5 + 2 * far) + 6, gl = sg.len + thick * 3 + 6;
        g.drawImage(glowSprite(sg.c), -gw / 2, sg.o - gl / 2, gw, gl);
      }
    }
  }
  resetCtx(g, dpr);
}

// ---------------------------------------------------------------- semaforos fisicos

// Semaforos fisicos en cada aproximacion (con zoom >= LOD.heads).
export function drawHeads(g: CanvasRenderingContext2D, cam: Camera, dpr: number, m: SignalModel,
  states: Record<string, string> | undefined, pal: Palette, o: SignalOpts): void {
  resetCtx(g, dpr);
  const s = cam.s;
  const fade = smooth(LOD.heads * 0.85, LOD.heads * 1.1, s);
  if (fade <= 0 || !m.tls.length) return;
  const night = o.night;
  const R = Math.max(3.6, 2.2 + 0.36 * s); // radio de cada luz (px)
  const pitch = R * 2.5;
  const poleR = Math.max(2.2, 0.8 + 0.16 * s);
  const margin = 80;

  interface Head { x: number; y: number; dx: number; dy: number; L: number; W: number; lamps: { u: number; c: string; on: boolean; arrow: boolean }[]; px: number; arm: number; }
  const heads: Head[] = [];
  for (const t of m.tls) {
    const st = states?.[t.id];
    for (const a of t.approaches) {
      const [ox, oy] = toScreen(cam, a.ox, a.oy);
      if (ox < -margin || oy < -margin || ox > cam.w + margin || oy > cam.h + margin) continue;
      const [dx, dy] = screenDir(cam, a.ux, a.uy);
      const { ball, arrow } = approachLamps(st, a);
      const n = arrow ? 4 : 3;
      const L = Math.max(n * pitch + R * 0.6, n === 4 ? 31 : 24);
      const W = Math.max(R * 2.7, 9);
      const gap = Math.max(0.3 * s, 2);
      // poste en la banqueta un poco despues del alto (el brazo no tapa la barra) y la caja colgada
      // hacia atras, junto al bordillo
      const off = gap + W / 2;
      const pole = Math.max(1.3 * s, 5);
      const along = pole - (L / 2 + poleR + 1);
      const hx = ox + -dy * off + dx * along, hy = oy + dx * off + dy * along;
      const lamps: Head["lamps"] = [];
      const order: Lamp[] = ["R", "Y", "G"];
      const step = (L - R * 0.6) / n;
      order.forEach((lm, i) => {
        lamps.push({ u: L / 2 - R * 0.3 - step * (i + 0.5), c: lampColor(lm, pal), on: ball === lm, arrow: false });
      });
      if (arrow) lamps.push({ u: L / 2 - R * 0.3 - step * 3.5, c: lampColor(arrow === "O" ? "G" : arrow, pal), on: arrow !== "O", arrow: true });
      heads.push({ x: hx, y: hy, dx, dy, L, W, lamps, px: L / 2 + poleR + 1, arm: a.width * s * 0.62 + off });
    }
  }
  if (!heads.length) return;

  // brazo (mastil) del poste sobre los carriles: linea oscura con borde claro tenue
  g.lineCap = "round";
  const armW = Math.max(0.2 * s, 1.4);
  for (const pass of [0, 1]) {
    g.strokeStyle = pass ? pal.housing : pal.marking;
    g.lineWidth = pass ? armW : armW + 1.6;
    g.globalAlpha = fade * (pass ? 0.95 : 0.22);
    for (const h of heads) {
      setFrame(g, dpr, h.x, h.y, h.dx, h.dy);
      g.beginPath();
      g.moveTo(h.px, 0);
      g.lineTo(h.px, -h.arm);
      g.stroke();
    }
  }
  g.globalAlpha = fade;
  // sombra (de dia) + caja + borde claro
  for (const h of heads) {
    setFrame(g, dpr, h.x, h.y, h.dx, h.dy);
    const r = Math.min(h.W / 2, Math.max(2, h.W * 0.35));
    if (night < 0.9) {
      g.globalAlpha = fade * 0.4 * (1 - night);
      g.fillStyle = pal.labelHalo;
      g.beginPath();
      g.roundRect(-h.L / 2 + 1.2, -h.W / 2 + 1.6, h.L, h.W, r);
      g.fill();
      g.globalAlpha = fade;
    }
    g.fillStyle = pal.housing;
    g.beginPath();
    g.roundRect(-h.L / 2, -h.W / 2, h.L, h.W, r);
    g.fill();
    g.globalAlpha = fade * 0.45;
    g.strokeStyle = pal.marking;
    g.lineWidth = 1;
    g.stroke();
    g.globalAlpha = fade;
    // poste
    g.fillStyle = pal.housing;
    g.beginPath();
    g.arc(h.px, 0, poleR, 0, Math.PI * 2);
    g.fill();
    g.globalAlpha = fade * 0.45;
    g.stroke();
    g.globalAlpha = fade;
    // luces
    for (const l of h.lamps) {
      const rr = l.arrow ? R * 0.9 : R;
      g.fillStyle = l.on && !l.arrow ? l.c : pal.lampOff;
      g.beginPath();
      g.arc(l.u, 0, rr, 0, Math.PI * 2);
      g.fill();
      if (l.arrow) {
        g.strokeStyle = l.on ? l.c : pal.badgeMuted;
        g.globalAlpha = fade * (l.on ? 1 : 0.35);
        g.lineWidth = Math.max(1.1, rr * 0.3);
        g.lineCap = "round";
        g.lineJoin = "round";
        // flecha hacia la izquierda del sentido de marcha (y local negativo)
        g.beginPath();
        g.moveTo(l.u, rr * 0.55);
        g.lineTo(l.u, -rr * 0.5);
        g.moveTo(l.u - rr * 0.42, -rr * 0.1);
        g.lineTo(l.u, -rr * 0.55);
        g.lineTo(l.u + rr * 0.42, -rr * 0.1);
        g.stroke();
        g.globalAlpha = fade;
      }
    }
  }
  // brillo de las luces encendidas
  g.globalCompositeOperation = "lighter";
  g.globalAlpha = fade * (0.6 + 0.4 * night);
  for (const h of heads) {
    setFrame(g, dpr, h.x, h.y, h.dx, h.dy);
    for (const l of h.lamps) {
      if (!l.on) continue;
      const G = R * (2.6 + 1.8 * night);
      g.drawImage(glowSprite(l.c), l.u - G, -G, G * 2, G * 2);
    }
  }
  resetCtx(g, dpr);
}

// ---------------------------------------------------------------- destellos

// Anillos que se expanden en el cruce cuando cambia de fase.
export function drawFlashes(g: CanvasRenderingContext2D, cam: Camera, dpr: number, m: SignalModel,
  tr: SignalTracker, o: SignalOpts): void {
  resetCtx(g, dpr);
  const pal = palette(o.night);
  const DUR = 900;
  for (const t of m.tls) {
    const k = tr.get(t.id);
    if (!k) continue;
    const f = (o.now - k.changedAtNow) / DUR;
    if (!(f >= 0 && f < 1)) continue;
    const [x, y] = toScreen(cam, t.x, t.y);
    if (x < -80 || y < -80 || x > cam.w + 80 || y > cam.h + 80) continue;
    const e = 1 - (1 - f) ** 3;
    const a = (1 - f) ** 1.5;
    const col = k.flash === "G" ? pal.green : k.flash === "Y" ? pal.yellow : o.accent;
    // relleno tenue al inicio
    if (f < 0.35) {
      g.globalAlpha = 0.18 * (1 - f / 0.35);
      g.fillStyle = col;
      g.beginPath();
      g.arc(x, y, 10 + 20 * e, 0, Math.PI * 2);
      g.fill();
    }
    g.strokeStyle = col;
    g.globalAlpha = a;
    g.lineWidth = 1 + 3 * (1 - f);
    g.beginPath();
    g.arc(x, y, 12 + 48 * e, 0, Math.PI * 2);
    g.stroke();
    // segundo anillo con el color del panel, un poco despues
    const f2 = f - 0.18;
    if (f2 > 0) {
      const e2 = 1 - (1 - f2 / 0.82) ** 3;
      g.strokeStyle = o.accent;
      g.globalAlpha = 0.6 * (1 - f2 / 0.82) ** 1.5;
      g.lineWidth = 1.5;
      g.beginPath();
      g.arc(x, y, 12 + 34 * e2, 0, Math.PI * 2);
      g.stroke();
    }
  }
  resetCtx(g, dpr);
}

// ---------------------------------------------------------------- tarjetas

interface Rect { x: number; y: number; w: number; h: number; }

function overlap(a: Rect, b: Rect): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  return w > 0 && h > 0 ? w * h : 0;
}

// Obstaculos del modelo en pantalla (cacheados por camara).
function screenObstacles(m: SignalModel, cam: Camera, tr: SignalTracker): { segs: Float32Array; pts: Float32Array } {
  if (tr.obsCam !== cam || tr.obsSegXY.length !== m.obsSegs.length || tr.obsPtXY.length !== m.obsPts.length) {
    const S = m.obsSegs, P = m.obsPts;
    const segs = tr.obsSegXY.length === S.length ? tr.obsSegXY : new Float32Array(S.length);
    for (let i = 0; i < S.length; i += 5) {
      const [x0, y0] = toScreen(cam, S[i], S[i + 1]);
      const [x1, y1] = toScreen(cam, S[i + 2], S[i + 3]);
      segs[i] = x0; segs[i + 1] = y0; segs[i + 2] = x1; segs[i + 3] = y1; segs[i + 4] = S[i + 4];
    }
    const pts = tr.obsPtXY.length === P.length ? tr.obsPtXY : new Float32Array(P.length);
    for (let i = 0; i < P.length; i += 3) {
      const [x, y] = toScreen(cam, P[i], P[i + 1]);
      pts[i] = x; pts[i + 1] = y; pts[i + 2] = P[i + 2];
    }
    tr.obsCam = cam; tr.obsSegXY = segs; tr.obsPtXY = pts;
  }
  return { segs: tr.obsSegXY, pts: tr.obsPtXY };
}

// Largo (px) del tramo (x0, y0)-(x1, y1) dentro del rectangulo [rx0, rx1] x [ry0, ry1] (Liang-Barsky).
function clipLen(x0: number, y0: number, x1: number, y1: number, rx0: number, ry0: number, rx1: number, ry1: number): number {
  if ((x0 < rx0 && x1 < rx0) || (x0 > rx1 && x1 > rx1) || (y0 < ry0 && y1 < ry0) || (y0 > ry1 && y1 > ry1)) return 0;
  const dx = x1 - x0, dy = y1 - y0;
  let t0 = 0, t1 = 1;
  const ps = [-dx, dx, -dy, dy], qs = [x0 - rx0, rx1 - x0, y0 - ry0, ry1 - y0];
  for (let i = 0; i < 4; i++) {
    const p = ps[i], q = qs[i];
    if (p === 0) { if (q < 0) return 0; continue; }
    const r = q / p;
    if (p < 0) { if (r > t1) return 0; if (r > t0) t0 = r; } else { if (r < t0) return 0; if (r < t1) t1 = r; }
  }
  return (t1 - t0) * Math.hypot(dx, dy);
}

interface Metrics { compact: boolean; w: number; h: number; }

const ARW = 11; // px por flecha en las pastillas compactas

function measure(g: CanvasRenderingContext2D, m: SignalModel, compact: boolean): Metrics {
  g.font = `600 11px ${FONT}`;
  const timerW = g.measureText("188 s").width;
  if (compact) {
    g.font = `700 12px ${FONT}`;
    let nw = 0, gw = 0;
    for (const t of m.tls) {
      nw = Math.max(nw, g.measureText(t.short).width);
      gw = Math.max(gw, t.axes.reduce((s, a) => s + a.aps.length * ARW + 6, 0) + 4 * Math.max(0, t.axes.length - 1));
    }
    return { compact, w: Math.ceil(9 + nw + 8 + gw + 6 + timerW + 9), h: 22 };
  }
  g.font = `700 12px ${FONT}`;
  let tw = 0;
  for (const t of m.tls) tw = Math.max(tw, g.measureText(t.short).width);
  g.font = `500 11px ${FONT}`;
  let lw = 0;
  for (const t of m.tls) for (const a of t.axes) lw = Math.max(lw, g.measureText(a.label).width);
  const rows = Math.max(1, ...m.tls.map((t) => t.axes.length));
  const w = Math.ceil(Math.max(tw + 16, 9 + 28 + 7 + lw + 10 + timerW + 9, 128));
  return { compact, w, h: 22 + rows * 15 + 3 };
}

const measureCache = new WeakMap<SignalModel, Map<boolean, Metrics>>();
function metrics(g: CanvasRenderingContext2D, m: SignalModel, compact: boolean): Metrics {
  let mc = measureCache.get(m);
  if (!mc) { mc = new Map(); measureCache.set(m, mc); }
  let mt = mc.get(compact);
  if (!mt) { mt = measure(g, m, compact); mc.set(compact, mt); }
  return mt;
}

// Posicion de cada tarjeta: junto a su cruce donde tape menos colas, semaforos y otras tarjetas.
// Cada candidata se mete primero en el lienzo y se evalua donde de verdad quedaria. Si el cruce llena
// la vista (mucho zoom) la tarjeta pasa a pastilla y se va a la esquina mas despejada, sin linea guia.
function layoutCards(g: CanvasRenderingContext2D, cam: Camera, m: SignalModel, tr: SignalTracker, compact: boolean): CardLayout[] {
  if (tr.layoutCam === cam && tr.layoutCompact === compact) return tr.layout;
  const full = metrics(g, m, compact), small = metrics(g, m, true);
  const { segs, pts } = screenObstacles(m, cam, tr);
  const pad = 6;
  const placed: CardLayout[] = [];
  const blocked: Rect[] = [{ x: cam.w - 62, y: 0, w: 62, h: 62 }]; // brujula
  const vis = m.tls
    .map((t) => {
      const [ax, ay] = toScreen(cam, t.x, t.y);
      let l = Infinity, r = -Infinity, tp = Infinity, b = -Infinity;
      for (const [x, y] of t.junction) {
        const [sx, sy] = toScreen(cam, x, y);
        l = Math.min(l, sx); r = Math.max(r, sx); tp = Math.min(tp, sy); b = Math.max(b, sy);
      }
      return { t, ax, ay, l: Math.min(l, ax - 4) - 3, r: Math.max(r, ax + 4) + 3, tp: Math.min(tp, ay - 4) - 3, b: Math.max(b, ay + 4) + 3 };
    })
    .filter((v) => v.ax > -10 && v.ay > -10 && v.ax < cam.w + 10 && v.ay < cam.h + 10)
    .sort((p, q) => p.ax - q.ax);
  const e = Math.max(2, 1.6 * cam.s);
  for (const v of vis) {
    const huge = v.r - v.l > cam.w * 0.5 || v.b - v.tp > cam.h * 0.9;
    const cc = compact || huge;
    const { w, h } = cc ? small : full;
    const G = cc ? 7 : 10;
    const cands: (Rect & { pen: number })[] = [];
    for (let r = 0; r < 3; r++) {
      const yA = v.tp - G - h - r * (h + 8);
      const yB = v.b + G + r * (h + 8);
      cands.push({ x: v.l - G - w, y: yA, w, h, pen: r * 1.5 });
      cands.push({ x: v.r + G, y: yA, w, h, pen: r * 1.5 + 0.3 });
      cands.push({ x: v.ax - w / 2, y: yA, w, h, pen: r * 1.5 + 1 });
      cands.push({ x: v.l - G - w, y: yB, w, h, pen: 14 + r * 1.5 });
      cands.push({ x: v.r + G, y: yB, w, h, pen: 14 + r * 1.5 + 0.3 });
    }
    // esquinas del lienzo
    for (const [fx, fy] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
      cands.push({ x: fx ? cam.w - pad - w : pad, y: fy ? cam.h - pad - h : pad, w, h, pen: huge ? fy * 0.5 : 6 });
    }
    const jr: Rect = { x: v.l, y: v.tp, w: v.r - v.l, h: v.b - v.tp };
    const prev = tr.prevCand.get(v.t.id);
    let best = 0, bestScore = Infinity, bx = pad, by = pad;
    cands.forEach((c, i) => {
      const x = Math.max(pad, Math.min(cam.w - pad - w, c.x));
      const y = Math.max(pad, Math.min(cam.h - pad - h, c.y));
      const cr: Rect = { x, y, w, h };
      let sc = c.pen + (prev === i ? -2.5 : 0) + Math.hypot(x - c.x, y - c.y) * 0.03;
      for (const p of placed) sc += (overlap(cr, p) / (w * h)) * 200;
      for (const p of blocked) sc += (overlap(cr, p) / (w * h)) * 40;
      sc += (overlap(cr, jr) / (w * h)) * (huge ? 4 : 30);
      const x0 = x - e, x1 = x + w + e, y0 = y - e, y1 = y + h + e;
      let ob = 0;
      for (let k = 0; k < segs.length; k += 5) ob += clipLen(segs[k], segs[k + 1], segs[k + 2], segs[k + 3], x0, y0, x1, y1) * segs[k + 4];
      sc += ob / cam.s;
      for (let k = 0; k < pts.length; k += 3) {
        const px = pts[k], py = pts[k + 1];
        if (px > x0 && px < x1 && py > y0 && py < y1) sc += pts[k + 2];
      }
      const nx = Math.max(x, Math.min(v.ax, x + w)), ny = Math.max(y, Math.min(v.ay, y + h));
      sc += Math.hypot(nx - v.ax, ny - v.ay) * (huge ? 0.004 : 0.03);
      if (sc < bestScore) { bestScore = sc; best = i; bx = x; by = y; }
    });
    tr.prevCand.set(v.t.id, best);
    let x = bx;
    const y = by;
    // si quedo encima de otra tarjeta, correrla a un lado
    for (const p of placed) {
      if (!overlap({ x, y, w, h }, p)) continue;
      const right = p.x + p.w + 6, left = p.x - 6 - w;
      x = right + w <= cam.w - pad && (Math.abs(right - x) <= Math.abs(left - x) || left < pad) ? right : Math.max(pad, left);
    }
    placed.push({ id: v.t.id, x, y, w, h, ax: v.ax, ay: v.ay, compact: cc, leader: !huge });
  }
  tr.layoutCam = cam;
  tr.layoutCompact = compact;
  tr.layout = placed;
  return placed;
}

// Flecha rellena de largo L centrada en (cx, cy) que apunta hacia (dx, dy) (unitario, pantalla).
function arrowGlyph(g: CanvasRenderingContext2D, cx: number, cy: number, dx: number, dy: number, L: number): void {
  const px = -dy, py = dx;
  const hd = L * 0.58, hw = L * 0.46, sw = L * 0.15;
  const tx = cx + (dx * L) / 2, ty = cy + (dy * L) / 2;
  const bx = cx - (dx * L) / 2, by = cy - (dy * L) / 2;
  const nx = tx - dx * hd, ny = ty - dy * hd;
  g.beginPath();
  g.moveTo(tx, ty);
  g.lineTo(nx + px * hw, ny + py * hw);
  g.lineTo(nx + px * sw, ny + py * sw);
  g.lineTo(bx + px * sw, by + py * sw);
  g.lineTo(bx - px * sw, by - py * sw);
  g.lineTo(nx - px * sw, ny - py * sw);
  g.lineTo(nx - px * hw, ny - py * hw);
  g.closePath();
  g.fill();
}

// Luz de cada aproximacion de un eje, con su sentido de marcha en pantalla (izquierda/arriba primero).
interface RowItem { l: Lamp; dx: number; dy: number; }
function rowItems(cam: Camera, t: SignalTls, axis: SignalAxis, k: Track | undefined): RowItem[] {
  return axis.aps
    .map((j) => {
      const ap = t.approaches[j];
      const [dx, dy] = screenDir(cam, ap.ux, ap.uy);
      return { l: k?.app[j] ?? "O", dx, dy };
    })
    .sort((p, q) => p.dx * 2 + p.dy - (q.dx * 2 + q.dy));
}

// Flechas de color dentro de una caja (x, y = borde izquierdo y centro vertical), una por aproximacion.
function arrowBox(g: CanvasRenderingContext2D, x: number, y: number, bw: number, bh: number, items: RowItem[],
  L: number, pal: Palette, glow: number): void {
  g.fillStyle = pal.housing;
  g.beginPath();
  g.roundRect(x, y - bh / 2, bw, bh, bh / 2);
  g.fill();
  const step = bw / items.length;
  items.forEach((it, j) => {
    g.fillStyle = lampColor(it.l, pal);
    arrowGlyph(g, x + step * (j + 0.5), y, it.dx, it.dy, L);
  });
  if (glow > 0) {
    g.globalCompositeOperation = "lighter";
    g.globalAlpha = glow * 0.8;
    items.forEach((it, j) => {
      if (it.l === "O") return;
      const gx = x + step * (j + 0.5);
      g.drawImage(glowSprite(lampColor(it.l, pal)), gx - 9, y - 9, 18, 18);
    });
    g.globalCompositeOperation = "source-over";
    g.globalAlpha = 1;
  }
}

function miniSignal(g: CanvasRenderingContext2D, x: number, y: number, lamp: Lamp, pal: Palette, glow: number): void {
  // caja horizontal de 28x11 con tres luces (rojo, ambar, verde)
  g.fillStyle = pal.housing;
  g.beginPath();
  g.roundRect(x, y - 5.5, 28, 11, 5.5);
  g.fill();
  const order: Lamp[] = ["R", "Y", "G"];
  order.forEach((l, i) => {
    g.fillStyle = l === lamp ? lampColor(l, pal) : pal.lampOff;
    g.beginPath();
    g.arc(x + 5.5 + i * 8.5, y, 3.3, 0, Math.PI * 2);
    g.fill();
  });
  const i = order.indexOf(lamp);
  if (i >= 0 && glow > 0) {
    g.globalCompositeOperation = "lighter";
    g.globalAlpha = glow;
    g.drawImage(glowSprite(lampColor(lamp, pal)), x + 5.5 + i * 8.5 - 10, y - 10, 20, 20);
    g.globalCompositeOperation = "source-over";
    g.globalAlpha = 1;
  }
}

// Tarjetas por cruce (nombre, luz de cada eje, segundos en la fase). Devuelve sus cajas para clic.
// Si los sentidos de un eje no coinciden (fase con adelanto/retraso: Reforma en verde hacia un lado y
// en rojo hacia el otro), la fila muestra una flecha de color por sentido en vez de un solo semaforo.
// Las pastillas compactas muestran siempre las flechas (dicen el eje y el sentido sin texto).
export function drawBadges(g: CanvasRenderingContext2D, cam: Camera, dpr: number, m: SignalModel,
  tr: SignalTracker, pal: Palette, o: SignalOpts): BadgeHit[] {
  resetCtx(g, dpr);
  if (!m.tls.length) return [];
  const compact = cam.w < 600 || cam.h < 260 || cam.s < 0.3;
  const cards = layoutCards(g, cam, m, tr, compact);
  const hits: BadgeHit[] = [];
  const byId = new Map(m.tls.map((t) => [t.id, t]));
  const PULSE = 1400;
  g.textBaseline = "middle";
  g.font = `600 11px ${FONT}`;
  const timerW = g.measureText("188 s").width;

  // lineas guia primero (debajo de todas las tarjetas)
  g.strokeStyle = pal.badgeMuted;
  g.lineWidth = 1;
  for (const c of cards) {
    if (!c.leader) continue;
    const nx = Math.max(c.x, Math.min(c.ax, c.x + c.w)), ny = Math.max(c.y, Math.min(c.ay, c.y + c.h));
    if (Math.hypot(nx - c.ax, ny - c.ay) < 4) continue;
    g.globalAlpha = 0.7;
    g.beginPath();
    g.moveTo(nx, ny);
    g.lineTo(c.ax, c.ay);
    g.stroke();
    g.globalAlpha = 1;
    g.fillStyle = pal.badgeText;
    g.beginPath();
    g.arc(c.ax, c.ay, 2.6, 0, Math.PI * 2);
    g.fill();
    g.strokeStyle = pal.labelHalo;
    g.lineWidth = 1.2;
    g.stroke();
    g.strokeStyle = pal.badgeMuted;
    g.lineWidth = 1;
  }

  for (const c of cards) {
    const t = byId.get(c.id)!;
    const k = tr.get(c.id);
    const lamps = k?.lamps ?? t.axes.map((): Lamp => "O");
    const pf = k ? (o.now - k.changedAtNow) / PULSE : 1;
    const pulse = pf >= 0 && pf < 1 ? (1 - pf) ** 2 : 0;
    const active = lamps.indexOf("G") >= 0 ? lamps.indexOf("G") : lamps.indexOf("Y");
    const secs = k ? Math.max(0, Math.floor(o.simT - k.phaseStart)) : 0;
    // a media fase (recien cargada la pagina) no se sabe cuanto lleva: guion en vez de segundos
    const timer = k?.exact ? `${secs} s` : "—";
    const r = c.compact ? c.h / 2 : 8;

    // fondo con sombra suave (solo 5 tarjetas)
    // (capa opaca con la sombra debajo: el fondo translucido no deja ver la sombra de color)
    g.save();
    g.shadowColor = pal.labelHalo;
    g.shadowBlur = 10;
    g.shadowOffsetY = 2;
    g.fillStyle = pal.labelHalo;
    g.beginPath();
    g.roundRect(c.x, c.y, c.w, c.h, r);
    g.fill();
    if (pulse > 0) {
      g.shadowColor = o.accent;
      g.shadowBlur = 18 * pulse;
      g.shadowOffsetY = 0;
      g.globalAlpha = pulse;
      g.fill();
    }
    g.restore();
    g.fillStyle = pal.badgeBg;
    g.fill();
    g.strokeStyle = pal.badgeBorder;
    g.lineWidth = 1;
    g.beginPath();
    g.roundRect(c.x + 0.5, c.y + 0.5, c.w - 1, c.h - 1, r);
    g.stroke();
    if (pulse > 0) {
      g.strokeStyle = o.accent;
      g.globalAlpha = pulse;
      g.lineWidth = 1.5;
      g.stroke();
      g.globalAlpha = 1;
    }
    const glow = 0.35 + 0.4 * o.night;
    const tColor = active >= 0 ? lampColor(lamps[active], pal) : pal.badgeMuted;

    if (c.compact) {
      const cy = c.y + c.h / 2;
      g.font = `700 12px ${FONT}`;
      g.fillStyle = pal.badgeText;
      g.textAlign = "left";
      g.fillText(t.short, c.x + 9, cy + 0.5);
      let x = c.x + c.w - 9;
      g.font = `600 11px ${FONT}`;
      g.textAlign = "right";
      g.fillStyle = k?.exact ? tColor : pal.badgeMuted;
      if (active >= 0) g.fillText(timer, x, cy + 0.5);
      x -= timerW + 6;
      for (let i = t.axes.length - 1; i >= 0; i--) {
        const items = rowItems(cam, t, t.axes[i], k);
        const bw = items.length * ARW + 6;
        x -= bw;
        arrowBox(g, x, cy, bw, 15, items, 9.5, pal, glow);
        x -= 4;
      }
    } else {
      g.font = `700 12px ${FONT}`;
      g.fillStyle = pal.badgeText;
      g.textAlign = "left";
      g.fillText(t.short, c.x + 9, c.y + 12.5);
      t.axes.forEach((a, i) => {
        const cy = c.y + 29 + i * 15;
        const l = lamps[i] ?? "O";
        const items = rowItems(cam, t, a, k);
        if (items.length > 1 && items.some((it) => it.l !== items[0].l)) arrowBox(g, c.x + 9, cy, 28, 11, items, 8.5, pal, glow);
        else miniSignal(g, c.x + 9, cy, l, pal, glow);
        g.font = `500 11px ${FONT}`;
        g.textAlign = "left";
        g.fillStyle = l === "G" || l === "Y" ? pal.badgeText : pal.badgeMuted;
        g.fillText(a.label, c.x + 9 + 28 + 7, cy + 0.5);
        if (i === active) {
          g.font = `600 11px ${FONT}`;
          g.textAlign = "right";
          g.fillStyle = k?.exact ? tColor : pal.badgeMuted;
          g.fillText(timer, c.x + c.w - 9, cy + 0.5);
        }
      });
    }
    hits.push({ id: c.id, x: c.x, y: c.y, w: c.w, h: c.h });
  }
  g.textAlign = "left";
  g.textBaseline = "alphabetic";
  resetCtx(g, dpr);
  return hits;
}
