// Camara del mapa: mundo SUMO (metros, y hacia el norte) -> pantalla (px CSS, y hacia abajo),
// con zoom/desplazamiento del usuario y una rotacion que alinea el eje largo de la red con el
// lado largo del lienzo (el corredor de Reforma va de norte a sur: en un lienzo ancho se dibuja
// horizontal, con el norte a la derecha).
import type { Network } from "../types";

export interface View { k: number; dx: number; dy: number; } // zoom relativo y desplazamiento (px)

export interface Camera {
  w: number; h: number; // tamano del lienzo en px CSS
  s: number; // px por metro
  rot: number; // rotacion del mundo (rad, antihoraria) antes de invertir el eje y
  cos: number; sin: number;
  cx: number; cy: number; // centro de rotacion en el mundo (centro del bbox)
  ox: number; oy: number; // posicion en pantalla del centro de rotacion
}

interface Extents { umin: number; umax: number; vmin: number; vmax: number; }

const PAD = 24;
const axisCache = new WeakMap<Network, { angle: number; elong: number }>();

function points(net: Network): [number, number][] {
  const out: [number, number][] = [];
  for (const l of net.lanes) for (const p of l.shape) out.push(p);
  return out.length ? out : [[net.bbox.minX, net.bbox.minY], [net.bbox.maxX, net.bbox.maxY]];
}

// Eje principal (PCA de los puntos de los carriles), en rad en el marco del mundo, y elongacion
// = largo/ancho de la red medida sobre ese eje.
export function principalAxis(net: Network): { angle: number; elong: number } {
  const hit = axisCache.get(net);
  if (hit) return hit;
  const pts = points(net);
  let mx = 0, my = 0;
  for (const [x, y] of pts) { mx += x; my += y; }
  mx /= pts.length; my /= pts.length;
  let sxx = 0, syy = 0, sxy = 0;
  for (const [x, y] of pts) { sxx += (x - mx) ** 2; syy += (y - my) ** 2; sxy += (x - mx) * (y - my); }
  const angle = 0.5 * Math.atan2(2 * sxy, sxx - syy);
  const c = Math.cos(angle), s = Math.sin(angle);
  let a0 = Infinity, a1 = -Infinity, b0 = Infinity, b1 = -Infinity;
  for (const [x, y] of pts) {
    const a = (x - mx) * c + (y - my) * s, b = -(x - mx) * s + (y - my) * c;
    a0 = Math.min(a0, a); a1 = Math.max(a1, a); b0 = Math.min(b0, b); b1 = Math.max(b1, b);
  }
  const r = { angle, elong: (a1 - a0) / Math.max(1, b1 - b0) };
  axisCache.set(net, r);
  return r;
}

// Rotacion (rad) para un lienzo w x h: el eje largo va al lado largo del lienzo, con el norte a la
// derecha (lienzo ancho) o arriba (lienzo alto). Redes casi cuadradas (elongacion < 1.3) no se rotan.
export function chooseRotation(net: Network, w: number, h: number): number {
  const { angle, elong } = principalAxis(net);
  if (elong < 1.3) return 0;
  let r: number;
  if (w >= h) {
    r = -angle; // eje -> +x
    if (-Math.sin(r) < 0) r += Math.PI; // el norte (0,1) rotado debe apuntar a la derecha
  } else {
    r = Math.PI / 2 - angle; // eje -> +y
    if (Math.cos(r) < 0) r += Math.PI; // el norte debe apuntar hacia arriba
  }
  r = Math.atan2(Math.sin(r), Math.cos(r));
  return Math.abs(r) < (2 * Math.PI) / 180 ? 0 : r;
}

// Elongacion de la red: el App la usa para decidir si apila los dos mapas (corredor largo).
export function elongation(net: Network): number {
  return principalAxis(net).elong;
}

function extents(net: Network, rot: number, cx: number, cy: number): Extents {
  const c = Math.cos(rot), s = Math.sin(rot);
  let umin = Infinity, umax = -Infinity, vmin = Infinity, vmax = -Infinity;
  for (const [x, y] of points(net)) {
    const u = (x - cx) * c - (y - cy) * s, v = (x - cx) * s + (y - cy) * c;
    umin = Math.min(umin, u); umax = Math.max(umax, u); vmin = Math.min(vmin, v); vmax = Math.max(vmax, v);
  }
  return { umin, umax, vmin, vmax };
}

const extCache = new WeakMap<Network, Map<number, Extents>>();
function cachedExtents(net: Network, rot: number, cx: number, cy: number): Extents {
  let m = extCache.get(net);
  if (!m) { m = new Map(); extCache.set(net, m); }
  let e = m.get(rot);
  if (!e) { e = extents(net, rot, cx, cy); m.set(rot, e); }
  return e;
}

// Escala base (k = 1): toda la red cabe en el lienzo con un margen de PAD px.
function baseScale(e: Extents, w: number, h: number): number {
  return Math.min((w - 2 * PAD) / Math.max(1, e.umax - e.umin), (h - 2 * PAD) / Math.max(1, e.vmax - e.vmin));
}

export function makeCamera(net: Network, w: number, h: number, view: View, rot: number): Camera {
  const cx = (net.bbox.minX + net.bbox.maxX) / 2, cy = (net.bbox.minY + net.bbox.maxY) / 2;
  const e = cachedExtents(net, rot, cx, cy);
  const s = baseScale(e, w, h) * view.k;
  const uc = (e.umin + e.umax) / 2, vc = (e.vmin + e.vmax) / 2;
  return {
    w, h, s, rot, cos: Math.cos(rot), sin: Math.sin(rot), cx, cy,
    ox: w / 2 + view.dx - uc * s,
    oy: h / 2 + view.dy + vc * s,
  };
}

export function toScreen(c: Camera, x: number, y: number): [number, number] {
  const dx = x - c.cx, dy = y - c.cy;
  return [c.ox + (dx * c.cos - dy * c.sin) * c.s, c.oy - (dx * c.sin + dy * c.cos) * c.s];
}

export function toWorld(c: Camera, sx: number, sy: number): [number, number] {
  const u = (sx - c.ox) / c.s, v = (c.oy - sy) / c.s;
  return [c.cx + u * c.cos + v * c.sin, c.cy - u * c.sin + v * c.cos];
}

// Transformacion del contexto para dibujar directamente en metros del mundo (lineas y anchos en m).
// OJO: invierte el eje y (determinante negativo): el texto se dibuja siempre en pantalla, nunca aqui.
export function applyWorld(g: CanvasRenderingContext2D, c: Camera, dpr: number): void {
  const a = c.s * c.cos, b = -c.s * c.sin, cc = -c.s * c.sin, d = -c.s * c.cos;
  const e = c.ox - c.s * (c.cos * c.cx - c.sin * c.cy);
  const f = c.oy + c.s * (c.sin * c.cx + c.cos * c.cy);
  g.setTransform(a * dpr, b * dpr, cc * dpr, d * dpr, e * dpr, f * dpr);
}

// Pantalla en px CSS (escala dpr): para texto, iconos y todo lo que tiene tamano fijo en pantalla.
export function applyScreen(g: CanvasRenderingContext2D, dpr: number): void {
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
}

// Angulo SUMO de un vehiculo (grados, 0 = norte, horario) -> rotacion de canvas en pantalla (rad,
// horaria) para un sprite dibujado apuntando hacia arriba (0, -1).
export function screenAngle(c: Camera, sumoDeg: number): number {
  return (sumoDeg * Math.PI) / 180 - c.rot;
}

// Direccion en pantalla (vector unitario) de un vector del mundo.
export function screenDir(c: Camera, wx: number, wy: number): [number, number] {
  const u = wx * c.cos - wy * c.sin, v = wx * c.sin + wy * c.cos;
  const L = Math.hypot(u, v) || 1;
  return [u / L, -v / L];
}

// Vista que centra el punto del mundo (x, y) con zoom k (para "acercar a un cruce").
export function viewFor(net: Network, w: number, h: number, rot: number, x: number, y: number, k: number): View {
  const cam = makeCamera(net, w, h, { k, dx: 0, dy: 0 }, rot);
  const [sx, sy] = toScreen(cam, x, y);
  return { k, dx: w / 2 - sx, dy: h / 2 - sy };
}

// Zoom k para que un tramo de `meters` metros ocupe el lado corto del lienzo.
export function zoomForSpan(net: Network, w: number, h: number, rot: number, meters: number): number {
  const base = makeCamera(net, w, h, { k: 1, dx: 0, dy: 0 }, rot).s;
  return Math.min(w, h) / Math.max(1, meters) / base;
}
