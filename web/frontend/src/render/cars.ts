// Carros vistos desde arriba: sprites prerenderizados (carroceria, parabrisas, techo, faros),
// color fijo por vehiculo, luces de freno, sombras y faros de noche.
//
// Todo se dibuja desde un atlas construido una sola vez (perezoso, compartido por los dos lienzos):
// 6 estilos x 11 colores x 5 niveles (mip) + luces de noche, capsulas, sombra, brillos y haces.
// Por carro: un setTransform (rotacion + posicion) y uno o dos drawImage; nada de save/restore,
// shadowBlur ni gradientes por cuadro. La posicion SUMO es la defensa delantera: el sprite se
// ancla ahi (frente en y = 0, cola hacia +y), asi los carros paran justo en la linea de alto.
import { applyScreen, type Camera } from "./camera";
import { CAR, CAR_COLORS, DAY, LOD, type Palette } from "./theme";

export interface CarDraw {
  id: string;
  x: number; y: number; // metros (mundo SUMO), ya interpolados
  angle: number; // grados SUMO (0 = norte, horario)
  speed: number; // m/s
  braking: boolean; // frenando o detenido -> luces de freno encendidas
}

export interface CarOpts {
  night: number; // 0 dia .. 1 noche
  colorBySpeed: boolean; // true: color por velocidad (modo esquematico/leyenda), false: color de carroceria
}

// Color por velocidad: rojo (parado) -> amarillo -> verde (flujo libre, ~14 m/s)
export function speedColor(v: number): string {
  const f = Math.max(0, Math.min(1, v / 13.9));
  return `hsl(${Math.round(f * 125)} 85% 55%)`;
}

// ---------------------------------------------------------------- colores derivados de theme.ts
const DARK = DAY.labelHalo; // sombras y oscurecidos
const LIGHT = CAR_COLORS[0].body; // brillos
const GLASS = DAY.housing; // vidrio polarizado
const SKY = DAY.label; // reflejo del cielo en el vidrio

function rgbOf(c: string): [number, number, number] {
  const h = c.length === 4 ? c.slice(1).split("").map((x) => x + x).join("") : c.slice(1, 7);
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function mix(a: string, b: string, t: number): string {
  const A = rgbOf(a), B = rgbOf(b);
  return `rgb(${A.map((x, i) => Math.round(x + (B[i] - x) * t)).join(",")})`;
}
function rgba(c: string, a: number): string {
  return `rgba(${rgbOf(c).join(",")},${a})`;
}
// t < 0 oscurece, t > 0 aclara
function shade(c: string, t: number): string {
  return t < 0 ? mix(c, DARK, -t) : mix(c, LIGHT, t);
}
function luma(c: string): number {
  const [r, g, b] = rgbOf(c);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// ---------------------------------------------------------------- estilos de carroceria
// Medidas en m desde la defensa delantera: g0 base del parabrisas, r0..r1 techo, g1 fin del medallon.
interface Style {
  L: number; W: number; weight: number;
  fr: number; rr: number; // radio de las esquinas delanteras / traseras
  g0: number; r0: number; r1: number; g1: number;
  pillars: number; // postes entre ventanas laterales
  rails?: boolean; // barras de techo (SUV)
  ribs?: boolean; // nervaduras del techo (microbus)
  sunroof?: boolean;
  bed?: number; // inicio de la palangana (pickup)
}

// Todos <= 5 m: SUMO reserva 5 m por carro (largo por defecto del vType).
const STYLES: Style[] = [
  { L: 4.55, W: 1.78, weight: 22, fr: 0.44, rr: 0.36, g0: 1.3, r0: 1.95, r1: 3.12, g1: 3.7, pillars: 1 }, // sedan
  { L: 4.85, W: 1.84, weight: 10, fr: 0.4, rr: 0.34, g0: 1.42, r0: 2.08, r1: 3.36, g1: 3.96, pillars: 1, sunroof: true }, // sedan grande
  { L: 4.2, W: 1.75, weight: 20, fr: 0.5, rr: 0.4, g0: 1.08, r0: 1.72, r1: 3.36, g1: 3.88, pillars: 1 }, // hatchback
  { L: 4.7, W: 1.88, weight: 24, fr: 0.36, rr: 0.3, g0: 1.12, r0: 1.7, r1: 4.08, g1: 4.44, pillars: 2, rails: true }, // SUV
  { L: 4.95, W: 1.86, weight: 14, fr: 0.34, rr: 0.14, g0: 1.3, r0: 1.88, r1: 2.82, g1: 3.0, pillars: 1, bed: 3.1 }, // pickup doble cabina
  { L: 4.85, W: 1.9, weight: 6, fr: 0.3, rr: 0.18, g0: 0.52, r0: 1.16, r1: 4.6, g1: 4.74, pillars: 3, ribs: true }, // microbus
];
const NS = STYLES.length, NC = CAR_COLORS.length;

// Faro y calavera del lado derecho (x > 0); el izquierdo es el espejo. Rectangulos rotados (m, rad).
interface Lamp { cx: number; cy: number; w: number; h: number; rot: number; }
const headLamp = (st: Style): Lamp => ({ cx: st.W / 2 - 0.3, cy: 0.13 + st.fr * 0.1, w: 0.42, h: 0.12, rot: 0.17 });
const tailLamp = (st: Style): Lamp => ({ cx: st.W / 2 - 0.27, cy: st.L - 0.1 - st.rr * 0.1, w: 0.38, h: 0.1, rot: -0.12 });

// ---------------------------------------------------------------- asignacion estable por id
function fnv1a(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  return h >>> 0;
}
function cumulative(w: number[]): number[] {
  let acc = 0;
  return w.map((x) => (acc += x));
}
const COLOR_CUM = cumulative(CAR_COLORS.map((c) => c.weight));
const STYLE_CUM = cumulative(STYLES.map((s) => s.weight));
function pick(cum: number[], r: number): number {
  for (let i = 0; i < cum.length; i++) if (r < cum[i]) return i;
  return cum.length - 1;
}

// Tipo de carro (estilo * NC + color), igual en los dos lienzos para el mismo id.
const kinds = new Map<string, number>();
function kindOf(id: string): number {
  let k = kinds.get(id);
  if (k === undefined) {
    if (kinds.size > 40000) kinds.clear();
    const h = fnv1a(id);
    const h2 = Math.imul(h ^ (h >>> 16), 0x45d9f3b) >>> 0; // segunda mezcla, independiente del color
    k = pick(STYLE_CUM, (h2 >>> 7) % STYLE_CUM[NS - 1]) * NC + pick(COLOR_CUM, h % COLOR_CUM[NC - 1]);
    kinds.set(id, k);
  }
  return k;
}

// ---------------------------------------------------------------- dibujo de los sprites (en metros)
function bodyPath(st: Style): Path2D {
  const { L, fr, rr } = st, hw = st.W / 2;
  const p = new Path2D();
  p.moveTo(-(hw - fr), 0.02);
  p.quadraticCurveTo(0, -0.05, hw - fr, 0.02);
  // costados: un poco mas angostos en las esquinas que a media carroceria
  const hf = hw - 0.05, hr = hw - 0.025;
  p.bezierCurveTo(hw - fr * 0.2, 0.03, hf, fr * 0.3, hf, fr);
  p.bezierCurveTo(hw + 0.01, L * 0.32, hw + 0.012, L * 0.62, hr, L - rr);
  p.bezierCurveTo(hr, L - rr * 0.3, hr - rr * 0.2, L - 0.01, hw - rr, L - 0.01);
  p.quadraticCurveTo(0, L + 0.02, -(hw - rr), L - 0.01);
  p.bezierCurveTo(-(hr - rr * 0.2), L - 0.01, -hr, L - rr * 0.3, -hr, L - rr);
  p.bezierCurveTo(-hw - 0.012, L * 0.62, -hw - 0.01, L * 0.32, -hf, fr);
  p.bezierCurveTo(-hf, fr * 0.3, -(hw - fr * 0.2), 0.03, -(hw - fr), 0.02);
  p.closePath();
  return p;
}

// Vidrios (parabrisas, ventanas laterales y medallon) como una sola pieza; el techo va encima.
function glassPath(st: Style): Path2D {
  const hw = st.W / 2, a = hw - 0.17, b = hw - 0.09, c = hw - 0.19;
  const { g0, r0, r1, g1 } = st;
  const p = new Path2D();
  p.moveTo(-a, g0 + 0.07);
  p.quadraticCurveTo(0, g0 - 0.09, a, g0 + 0.07);
  p.lineTo(b, r0 + 0.08);
  p.lineTo(b, r1 - 0.04);
  p.lineTo(c, g1 - 0.06);
  p.quadraticCurveTo(0, g1 + 0.06, -c, g1 - 0.06);
  p.lineTo(-b, r1 - 0.04);
  p.lineTo(-b, r0 + 0.08);
  p.closePath();
  return p;
}

function lampPath(g: CanvasRenderingContext2D, l: Lamp, side: number): void {
  const c = Math.cos(l.rot * side), s = Math.sin(l.rot * side);
  const pts: [number, number][] = [[-l.w / 2, -l.h / 2], [l.w / 2, -l.h / 2], [l.w / 2, l.h / 2], [-l.w / 2, l.h / 2]];
  g.beginPath();
  pts.forEach(([x, y], i) => {
    const X = side * l.cx + x * c - y * s, Y = l.cy + x * s + y * c;
    if (i) g.lineTo(X, Y); else g.moveTo(X, Y);
  });
  g.closePath();
}

function line(g: CanvasRenderingContext2D, x0: number, y0: number, x1: number, y1: number): void {
  g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
}

function softSpot(g: CanvasRenderingContext2D, x: number, y: number, rx: number, ry: number, color: string, a: number): void {
  const gr = g.createRadialGradient(x, y, 0, x, y, rx);
  gr.addColorStop(0, rgba(color, a));
  gr.addColorStop(1, rgba(color, 0));
  g.save();
  g.translate(x, y); g.scale(1, ry / rx); g.translate(-x, -y);
  g.fillStyle = gr;
  g.beginPath(); g.arc(x, y, rx, 0, Math.PI * 2); g.fill();
  g.restore();
}

function paintCar(g: CanvasRenderingContext2D, st: Style, body: string, p: number): void {
  const { L, W, g0, r0, r1, g1 } = st, hw = W / 2, px = 1 / p;
  const dark = luma(body) < 90;
  const rim = dark ? mix(body, LIGHT, 0.32) : mix(body, DARK, 0.5);
  const path = bodyPath(st);
  g.lineCap = "round";

  // espejos (la carroceria tapa su base)
  g.fillStyle = shade(body, -0.28);
  for (const s of [-1, 1]) {
    g.beginPath(); g.ellipse(s * (hw + 0.05), g0 + 0.14, 0.12, 0.065, s * 0.35, 0, Math.PI * 2); g.fill();
  }

  // carroceria: mas clara al centro, mas oscura en los costados
  const gx = g.createLinearGradient(-hw, 0, hw, 0);
  gx.addColorStop(0, shade(body, -0.42));
  gx.addColorStop(0.1, shade(body, -0.14));
  gx.addColorStop(0.32, body);
  gx.addColorStop(0.5, shade(body, dark ? 0.12 : 0.08));
  gx.addColorStop(0.68, body);
  gx.addColorStop(0.9, shade(body, -0.14));
  gx.addColorStop(1, shade(body, -0.42));
  g.fillStyle = gx;
  g.fill(path);

  g.save();
  g.clip(path);
  // defensas un poco mas oscuras
  const gy = g.createLinearGradient(0, 0, 0, L);
  gy.addColorStop(0, rgba(DARK, 0.3));
  gy.addColorStop(0.07, rgba(DARK, 0));
  gy.addColorStop(0.93, rgba(DARK, 0));
  gy.addColorStop(1, rgba(DARK, 0.32));
  g.fillStyle = gy;
  g.fillRect(-hw - 0.1, -0.1, W + 0.2, L + 0.2);
  // brillo del capo y de la cajuela
  softSpot(g, 0, g0 * 0.45, hw * 0.75, g0 * 0.4, LIGHT, dark ? 0.16 : 0.12);
  if (!st.bed && L - g1 > 0.35) softSpot(g, 0, (g1 + L) / 2, hw * 0.6, (L - g1) * 0.35, LIGHT, dark ? 0.12 : 0.08);
  // pliegues del capo
  if (p >= 20 && g0 > 0.9) {
    g.strokeStyle = rgba(DARK, 0.16); g.lineWidth = 0.025;
    for (const s of [-1, 1]) line(g, s * 0.3, 0.22, s * 0.4, g0 - 0.08);
  }

  // vidrios con reflejo del cielo
  const glass = glassPath(st);
  const span = Math.max(0.01, g1 - g0);
  const gg = g.createLinearGradient(0, g0, 0, g1);
  gg.addColorStop(0, mix(GLASS, SKY, 0.32));
  gg.addColorStop(Math.min(0.99, (r0 - g0) / span), GLASS);
  gg.addColorStop(Math.max(0.01, Math.min(1, (r1 - g0) / span)), GLASS);
  gg.addColorStop(1, mix(GLASS, SKY, 0.2));
  g.fillStyle = gg;
  g.fill(glass);
  g.save();
  g.clip(glass);
  g.fillStyle = rgba(LIGHT, 0.1);
  g.beginPath();
  g.moveTo(-hw * 0.55, g0 - 0.1); g.lineTo(-hw * 0.15, g0 - 0.1); g.lineTo(hw * 0.25, r0 + 0.1); g.lineTo(-hw * 0.15, r0 + 0.1);
  g.closePath(); g.fill();
  g.restore();

  // techo
  const rw = hw - 0.27;
  const gr = g.createLinearGradient(-rw, 0, rw, 0);
  gr.addColorStop(0, shade(body, -0.16));
  gr.addColorStop(0.5, shade(body, dark ? 0.14 : 0.07));
  gr.addColorStop(1, shade(body, -0.16));
  g.fillStyle = gr;
  g.beginPath(); g.roundRect(-rw, r0, 2 * rw, r1 - r0, Math.min(0.22, (r1 - r0) / 3)); g.fill();
  if (p >= 10) { g.strokeStyle = rgba(DARK, 0.28); g.lineWidth = Math.max(0.02, 0.5 * px); g.stroke(); }
  softSpot(g, -rw * 0.2, r0 + (r1 - r0) * 0.35, rw * 0.7, (r1 - r0) * 0.3, LIGHT, dark ? 0.12 : 0.08);

  // postes A, B y C en color de carroceria
  g.strokeStyle = shade(body, -0.08); g.lineWidth = Math.max(0.07, 0.6 * px);
  const a = hw - 0.17, b = hw - 0.09, c = hw - 0.19;
  for (const s of [-1, 1]) {
    line(g, s * a, g0 + 0.07, s * rw, r0 + 0.05);
    line(g, s * rw, r1 - 0.03, s * c, g1 - 0.06);
    for (let k = 1; k <= st.pillars; k++) {
      const y = r0 + ((r1 - r0) * k) / (st.pillars + 1);
      line(g, s * rw, y, s * b, y);
    }
  }

  if (st.sunroof) {
    g.fillStyle = mix(GLASS, SKY, 0.14);
    g.beginPath(); g.roundRect(-rw * 0.6, r0 + 0.16, rw * 1.2, (r1 - r0) * 0.38, 0.06); g.fill();
    g.strokeStyle = shade(body, -0.35); g.lineWidth = Math.max(0.025, 0.4 * px); g.stroke();
  }
  if (st.rails) {
    g.strokeStyle = mix(body, DARK, 0.62); g.lineWidth = Math.max(0.055, 0.5 * px);
    for (const s of [-1, 1]) line(g, s * (rw - 0.07), r0 + 0.12, s * (rw - 0.07), r1 - 0.12);
  }
  if (st.ribs) {
    g.strokeStyle = shade(body, -0.12); g.lineWidth = Math.max(0.035, 0.4 * px);
    for (let k = 1; k <= 4; k++) { const y = r0 + 0.5 + ((r1 - r0 - 0.7) * k) / 5; line(g, -rw + 0.12, y, rw - 0.12, y); }
  }
  if (st.bed) {
    const bx = hw - 0.1, y0 = st.bed, y1 = L - 0.13;
    g.fillStyle = shade(body, -0.6);
    g.beginPath(); g.roundRect(-bx, y0, 2 * bx, y1 - y0, 0.05); g.fill();
    const gb = g.createLinearGradient(0, y0, 0, y0 + 0.45);
    gb.addColorStop(0, rgba(DARK, 0.5));
    gb.addColorStop(1, rgba(DARK, 0));
    g.fillStyle = gb; g.fillRect(-bx, y0, 2 * bx, 0.45);
    g.strokeStyle = shade(body, -0.45); g.lineWidth = Math.max(0.04, 0.4 * px);
    for (const x of [-0.45, 0, 0.45]) line(g, x, y0 + 0.12, x, y1 - 0.06);
  }

  // parrilla
  g.fillStyle = shade(body, -0.55);
  g.beginPath(); g.roundRect(-0.36, 0.035, 0.72, 0.06, 0.02); g.fill();

  // faros (palidos, apagados) y calaveras (rojo oscuro)
  const hl = headLamp(st), tl = tailLamp(st);
  for (const s of [-1, 1]) {
    lampPath(g, hl, s);
    g.fillStyle = mix(DAY.headlight, LIGHT, 0.45); g.fill();
    if (p >= 10) { g.strokeStyle = rgba(DARK, 0.5); g.lineWidth = Math.max(0.025, 0.5 * px); g.stroke(); }
    lampPath(g, tl, s);
    g.fillStyle = mix(DAY.brake, DARK, 0.5); g.fill();
  }
  g.restore();

  // contorno sutil: los negros se leen sobre el asfalto y los blancos no son rectangulos planos
  g.strokeStyle = rim; g.lineWidth = Math.max(0.05, 0.85 * px);
  g.stroke(path);
}

// Noche: carroceria un poco mas oscura (menos luz ambiente) y faros/calaveras encendidos.
// Se dibuja encima de la carroceria con alpha = night (un solo drawImage extra por carro).
function paintLights(g: CanvasRenderingContext2D, st: Style): void {
  const hl = headLamp(st), tl = tailLamp(st);
  g.fillStyle = rgba(DARK, 0.3);
  g.fill(bodyPath(st));
  for (const s of [-1, 1]) {
    softSpot(g, s * hl.cx, hl.cy, 0.5, 0.32, DAY.headlight, 0.55);
    lampPath(g, hl, s); g.fillStyle = DAY.headlight; g.fill();
    softSpot(g, s * tl.cx, tl.cy, 0.42, 0.26, DAY.brake, 0.45);
    lampPath(g, tl, s); g.fillStyle = mix(DAY.brake, DARK, 0.18); g.fill();
  }
}

// Capsula de color (zoom lejano), proporciones nominales CAR.
function paintCapsule(g: CanvasRenderingContext2D, body: string): void {
  const w = CAR.width, l = CAR.length;
  g.beginPath(); g.roundRect(-w / 2, 0, w, l, w * 0.42);
  g.fillStyle = body; g.fill();
  g.strokeStyle = luma(body) < 90 ? mix(body, LIGHT, 0.35) : mix(body, DARK, 0.4);
  g.lineWidth = 0.32; g.stroke();
}

// Sombra suave (shadowBlur solo aqui, al construir el atlas): la forma se dibuja fuera y su sombra cae dentro.
function paintShadow(g: CanvasRenderingContext2D, p: number): void {
  const w = CAR.width, l = CAR.length, off = 4000;
  g.shadowColor = DARK; g.shadowBlur = 0.3 * p * 2; g.shadowOffsetX = off;
  g.fillStyle = DARK;
  g.beginPath(); g.roundRect(-w / 2 - off / p, 0.05, w, l - 0.1, 0.45); g.fill();
}

function paintGlow(g: CanvasRenderingContext2D, color: string, a: number): void {
  const gr = g.createRadialGradient(0, 0, 0, 0, 0, 1);
  gr.addColorStop(0, rgba(color, a));
  gr.addColorStop(0.25, rgba(color, a * 0.55));
  gr.addColorStop(0.6, rgba(color, a * 0.15));
  gr.addColorStop(1, rgba(color, 0));
  g.fillStyle = gr; g.fillRect(-1, -1, 2, 2);
}

// Haz de los dos faros: ~14 m, ~35 grados, caida radial; bordes suaves sumando cunas de distinta apertura.
const CONE_LEN = 14;
function paintCone(g: CanvasRenderingContext2D): void {
  g.globalCompositeOperation = "lighter";
  const K = 6;
  for (const lx of [-0.6, 0.6]) {
    const gr = g.createRadialGradient(lx, 0, 0, lx, 0, CONE_LEN);
    gr.addColorStop(0, rgba(DAY.headlight, 0.9));
    gr.addColorStop(0.1, rgba(DAY.headlight, 0.62));
    gr.addColorStop(0.4, rgba(DAY.headlight, 0.26));
    gr.addColorStop(0.75, rgba(DAY.headlight, 0.07));
    gr.addColorStop(1, rgba(DAY.headlight, 0));
    g.fillStyle = gr;
    g.globalAlpha = 1 / K;
    for (let k = 0; k < K; k++) {
      const t = Math.tan(((10 + (14 * k) / (K - 1)) * Math.PI) / 180) * CONE_LEN;
      g.beginPath();
      g.moveTo(lx - 0.15, 0.05); g.lineTo(lx + 0.15, 0.05);
      g.lineTo(lx + 0.15 + t, -CONE_LEN); g.lineTo(lx - 0.15 - t, -CONE_LEN);
      g.closePath(); g.fill();
    }
  }
  g.globalAlpha = 1;
  g.globalCompositeOperation = "source-over";
}

// ---------------------------------------------------------------- atlas
interface Sprite {
  sx: number; sy: number; sw: number; sh: number; // rectangulo en el atlas (px)
  ex: number; ey: number; ew: number; eh: number; // extension local en m (origen = frente al centro)
}
interface Item { sp: Sprite; p: number; paint: (g: CanvasRenderingContext2D) => void; }
interface Atlas {
  img: CanvasImageSource;
  body: Sprite[]; // ((nivel * NS) + estilo) * NC + color
  lights: Sprite[]; // nivel * NS + estilo
  capsule: Sprite[]; // color
  shadow: Sprite; glow: Sprite; dot: Sprite; cone: Sprite;
}

const LEVELS = [48, 24, 12, 6, 3]; // px por metro de cada nivel, de mayor a menor
const PAD_X = 0.26, PAD_Y = 0.14; // margen del sprite (espejos, contorno, halo de las luces)
const GAP = 3; // separacion entre sprites del atlas (evita que el filtrado mezcle vecinos)
const ATLAS_W = 2048;

let atlas: Atlas | null = null;

function buildAtlas(): Atlas {
  const items: Item[] = [];
  // sprite centrado en x; y local de ey a ey + eh (m)
  const add = (p: number, ey: number, ew: number, eh: number, paint: (g: CanvasRenderingContext2D) => void): Sprite => {
    const sw = Math.ceil(ew * p), sh = Math.ceil(eh * p);
    const sp: Sprite = { sx: 0, sy: 0, sw, sh, ex: -sw / p / 2, ey, ew: sw / p, eh: sh / p };
    items.push({ sp, p, paint });
    return sp;
  };
  const body: Sprite[] = [], lights: Sprite[] = [];
  for (const p of LEVELS) {
    for (const st of STYLES) {
      const ew = st.W + 2 * PAD_X, eh = st.L + 2 * PAD_Y;
      for (const c of CAR_COLORS) body.push(add(p, -PAD_Y, ew, eh, (g) => paintCar(g, st, c.body, p)));
      lights.push(add(p, -PAD_Y, ew, eh, (g) => paintLights(g, st)));
    }
  }
  const capsule = CAR_COLORS.map((c) => add(6, -0.2, CAR.width + 0.4, CAR.length + 0.4, (g) => paintCapsule(g, c.body)));
  const shadow = add(16, -0.7, CAR.width + 1.4, CAR.length + 1.4, (g) => paintShadow(g, 16));
  const glow = add(16, -1, 2, 2, (g) => paintGlow(g, DAY.brake, 1));
  const dot = add(16, -1, 2, 2, (g) => paintGlow(g, DAY.headlight, 1));
  const cone = add(10, -CONE_LEN - 0.4, 14.6, CONE_LEN + 0.6, paintCone);

  // empaquetado por estantes
  const order = [...items].sort((a, b) => b.sp.sh - a.sp.sh);
  let x = GAP, y = GAP, rowH = 0;
  for (const it of order) {
    if (x + it.sp.sw + GAP > ATLAS_W) { x = GAP; y += rowH + GAP; rowH = 0; }
    it.sp.sx = x; it.sp.sy = y;
    x += it.sp.sw + GAP; rowH = Math.max(rowH, it.sp.sh);
  }
  const cv = document.createElement("canvas");
  cv.width = ATLAS_W; cv.height = y + rowH + GAP;
  const g = cv.getContext("2d")!;
  for (const it of items) {
    const sp = it.sp;
    g.save();
    g.beginPath(); g.rect(sp.sx, sp.sy, sp.sw, sp.sh); g.clip();
    g.setTransform(it.p, 0, 0, it.p, sp.sx - sp.ex * it.p, sp.sy - sp.ey * it.p);
    it.paint(g);
    g.restore();
  }
  const a: Atlas = { img: cv, body, lights, capsule, shadow, glow, dot, cone };
  // ImageBitmap: textura inmutable, la forma mas rapida de dibujar desde el atlas
  if (typeof createImageBitmap === "function") createImageBitmap(cv).then((b) => { a.img = b; }).catch(() => {});
  return a;
}

function getAtlas(): Atlas {
  return (atlas ??= buildAtlas());
}

// Colores por velocidad cuantizados (evita crear cadenas por carro y por cuadro)
const SPEED_STEPS = 32;
const SPEED_COLORS = Array.from({ length: SPEED_STEPS }, (_, i) => speedColor((i / (SPEED_STEPS - 1)) * 13.9));

// ---------------------------------------------------------------- render
export class CarRenderer {
  // Datos por carro visible (px de dispositivo), compartidos entre drawHeadlights y draw del mismo cuadro.
  private cap = 0;
  private X = new Float32Array(0); private Y = new Float32Array(0);
  private C = new Float32Array(0); private S = new Float32Array(0); // cos/sin del angulo * dpr
  private V = new Float32Array(0);
  private K = new Uint16Array(0); private B = new Uint8Array(0);
  private n = 0;
  private pList: CarDraw[] | null = null; private pCam: Camera | null = null; private pDpr = 0;
  // Tablas por estilo (px CSS), recalculadas por cuadro
  private kx = new Float32Array(NS); private ky = new Float32Array(NS);
  private Lpx = new Float32Array(NS); private Wpx = new Float32Array(NS);
  private q = new Float32Array(NS * 2); // escala de los sprites nominales (sombra, capsula)
  private d = new Float32Array(NS * 4); private tl = new Float32Array(NS * 4); // destino del sprite y calavera
  private pT = 0;

  private prepare(cam: Camera, dpr: number, cars: CarDraw[]): number {
    const now = performance.now();
    if (cars === this.pList && cam === this.pCam && dpr === this.pDpr && now - this.pT < 8) return this.n;
    this.pList = cars; this.pCam = cam; this.pDpr = dpr; this.pT = now;
    if (cars.length > this.cap) {
      const c = (this.cap = Math.max(256, cars.length * 1.5) | 0);
      this.X = new Float32Array(c); this.Y = new Float32Array(c); this.C = new Float32Array(c);
      this.S = new Float32Array(c); this.V = new Float32Array(c); this.K = new Uint16Array(c); this.B = new Uint8Array(c);
    }
    const s = cam.s, m = Math.max(CAR.minLenPx, 5 * s) + (CONE_LEN + 1) * s + 8; // margen de recorte (px CSS)
    const xmax = cam.w + m, ymax = cam.h + m;
    const a = cam.cos * s, b = cam.sin * s, D = Math.PI / 180;
    let n = 0;
    for (let i = 0; i < cars.length; i++) {
      const c = cars[i];
      const dx = c.x - cam.cx, dy = c.y - cam.cy;
      const x = cam.ox + dx * a - dy * b, y = cam.oy - (dx * b + dy * a);
      if (!(x > -m && x < xmax && y > -m && y < ymax)) continue; // tambien descarta NaN
      const t = c.angle * D - cam.rot;
      this.X[n] = x * dpr; this.Y[n] = y * dpr;
      this.C[n] = Math.cos(t) * dpr; this.S[n] = Math.sin(t) * dpr;
      this.V[n] = c.speed; this.K[n] = kindOf(c.id); this.B[n] = c.braking ? 1 : 0;
      n++;
    }
    return (this.n = n);
  }

  // Largo/ancho en pantalla por estilo y escala (px CSS por m) a lo largo y a lo ancho.
  private sizes(s: number): number {
    let kmax = 0;
    for (let i = 0; i < NS; i++) {
      const st = STYLES[i];
      const L = Math.max(CAR.minLenPx, st.L * s), W = Math.max(CAR.minWidPx, st.W * s);
      this.Lpx[i] = L; this.Wpx[i] = W; this.kx[i] = W / st.W; this.ky[i] = L / st.L;
      this.q[i * 2] = W / CAR.width; this.q[i * 2 + 1] = L / CAR.length;
      kmax = Math.max(kmax, this.kx[i], this.ky[i]);
    }
    return kmax;
  }

  // Haces de luz de los faros (noche), se llama ANTES de draw() con composicion aditiva.
  drawHeadlights(g: CanvasRenderingContext2D, cam: Camera, dpr: number, cars: CarDraw[], _pal: Palette, o: CarOpts): void {
    if (o.colorBySpeed || o.night <= 0.01) { applyScreen(g, dpr); return; }
    const n = this.prepare(cam, dpr, cars);
    const A = getAtlas(), img = A.img;
    const { X, Y, C, S } = this;
    g.globalCompositeOperation = "lighter";
    if (cam.s < 0.9) {
      // lejos: solo un punto calido al frente de cada carro
      const d = A.dot, r = Math.max(1.6, 1.4 * cam.s) * dpr, ahead = 0.8;
      g.setTransform(1, 0, 0, 1, 0, 0);
      g.globalAlpha = 0.8 * o.night;
      for (let i = 0; i < n; i++) {
        const fx = X[i] + S[i] * ahead, fy = Y[i] - C[i] * ahead;
        g.drawImage(img, d.sx, d.sy, d.sw, d.sh, fx + d.ex * r, fy + d.ey * r, d.ew * r, d.eh * r);
      }
    } else {
      const c = A.cone, s = cam.s;
      const dx = c.ex * s, dy = c.ey * s, dw = c.ew * s, dh = c.eh * s;
      g.globalAlpha = 0.42 * o.night;
      for (let i = 0; i < n; i++) {
        g.setTransform(C[i], S[i], -S[i], C[i], X[i], Y[i]);
        g.drawImage(img, c.sx, c.sy, c.sw, c.sh, dx, dy, dw, dh);
      }
    }
    g.globalAlpha = 1;
    g.globalCompositeOperation = "source-over";
    applyScreen(g, dpr);
  }

  // Carros (sombra, carroceria, luces). Deja el contexto en applyScreen.
  draw(g: CanvasRenderingContext2D, cam: Camera, dpr: number, cars: CarDraw[], pal: Palette, o: CarOpts): void {
    const n = this.prepare(cam, dpr, cars);
    const { X, Y, C, S, K, B } = this;
    const s = cam.s;

    if (o.colorBySpeed) {
      const L = Math.max(CAR.minLenPx, CAR.length * s), W = Math.max(CAR.minWidPx, CAR.width * s);
      for (let i = 0; i < n; i++) {
        g.setTransform(C[i], S[i], -S[i], C[i], X[i], Y[i]);
        g.fillStyle = SPEED_COLORS[Math.min(SPEED_STEPS - 1, Math.max(0, Math.round((this.V[i] / 13.9) * (SPEED_STEPS - 1))))];
        g.fillRect(-W / 2, 0, W, L);
      }
      applyScreen(g, dpr);
      return;
    }

    const A = getAtlas(), img = A.img;
    const { kx, ky, Lpx, Wpx } = this;
    const kmax = this.sizes(s) * dpr;
    const sprite = s >= LOD.carSprite;
    const night = o.night;

    // sombras (pasada aparte, debajo de todos los carros), corridas hacia abajo a la derecha
    if (sprite && s >= LOD.shadows) {
      const sh = A.shadow, ox = 0.22 * s * dpr, oy = 0.34 * s * dpr;
      const q = this.q;
      g.globalAlpha = 0.5 - 0.22 * night;
      for (let i = 0; i < n; i++) {
        const st = (K[i] / NC) | 0;
        g.setTransform(C[i], S[i], -S[i], C[i], X[i] + ox, Y[i] + oy);
        const qx = q[st * 2], qy = q[st * 2 + 1];
        g.drawImage(img, sh.sx, sh.sy, sh.sw, sh.sh, sh.ex * qx, sh.ey * qy, sh.ew * qx, sh.eh * qy);
      }
      g.globalAlpha = 1;
    }

    g.fillStyle = pal.brake;
    if (sprite) {
      // nivel mas pequeno con al menos los px por metro de la pantalla
      let lv = 0;
      while (lv + 1 < LEVELS.length && LEVELS[lv + 1] >= kmax) lv++;
      const base = lv * NS * NC, lbase = lv * NS;
      // rectangulos destino por estilo (mismas extensiones para todos los colores del nivel)
      const { d, tl } = this;
      for (let k = 0; k < NS; k++) {
        const sp = A.body[base + k * NC];
        d[k * 4] = sp.ex * kx[k]; d[k * 4 + 1] = sp.ey * ky[k]; d[k * 4 + 2] = sp.ew * kx[k]; d[k * 4 + 3] = sp.eh * ky[k];
        const t = tailLamp(STYLES[k]);
        tl[k * 4] = (t.cx - t.w / 2) * kx[k]; tl[k * 4 + 1] = (t.cy - t.h / 2) * ky[k];
        tl[k * 4 + 2] = t.w * kx[k]; tl[k * 4 + 3] = t.h * ky[k];
      }
      const lit = night > 0.02;
      for (let i = 0; i < n; i++) {
        const kind = K[i], st = (kind / NC) | 0, j = st * 4;
        const sp = A.body[base + kind];
        g.setTransform(C[i], S[i], -S[i], C[i], X[i], Y[i]);
        g.drawImage(img, sp.sx, sp.sy, sp.sw, sp.sh, d[j], d[j + 1], d[j + 2], d[j + 3]);
        if (lit) {
          const lp = A.lights[lbase + st];
          g.globalAlpha = night;
          g.drawImage(img, lp.sx, lp.sy, lp.sw, lp.sh, d[j], d[j + 1], d[j + 2], d[j + 3]);
          g.globalAlpha = 1;
        }
        if (B[i]) {
          g.fillRect(tl[j], tl[j + 1], tl[j + 2], tl[j + 3]);
          g.fillRect(-tl[j] - tl[j + 2], tl[j + 1], tl[j + 2], tl[j + 3]);
        }
      }
      // brillo de frenos (y calaveras de noche) con composicion aditiva; redondo, no necesita rotacion
      const gl = A.glow;
      g.globalCompositeOperation = "lighter";
      g.setTransform(1, 0, 0, 1, 0, 0);
      const aBrake = 0.5 + 0.4 * night, aTail = 0.3 * night;
      for (let i = 0; i < n; i++) {
        if (!B[i] && !lit) continue;
        const st = (K[i] / NC) | 0;
        const rear = Lpx[st] + 0.05 * ky[st];
        const r = Math.max(2.5, Wpx[st] * (B[i] ? 0.66 : 0.5)) * dpr;
        const rx = X[i] - S[i] * rear, ry = Y[i] + C[i] * rear;
        g.globalAlpha = B[i] ? aBrake : aTail;
        g.drawImage(img, gl.sx, gl.sy, gl.sw, gl.sh, rx + gl.ex * r, ry + gl.ey * r, gl.ew * r, gl.eh * r);
      }
      g.globalAlpha = 1;
      g.globalCompositeOperation = "source-over";
    } else {
      // lejos: capsula de color; frenando, el cuarto trasero en rojo (de noche, calaveras tenues siempre)
      const { d, q } = this, cp = A.capsule[0];
      for (let k = 0; k < NS; k++) {
        const qx = q[k * 2], qy = q[k * 2 + 1];
        d[k * 4] = cp.ex * qx; d[k * 4 + 1] = cp.ey * qy; d[k * 4 + 2] = cp.ew * qx; d[k * 4 + 3] = cp.eh * qy;
      }
      const tail = night > 0.02;
      for (let i = 0; i < n; i++) {
        const kind = K[i], st = (kind / NC) | 0, j = st * 4;
        const sp = A.capsule[kind % NC];
        g.setTransform(C[i], S[i], -S[i], C[i], X[i], Y[i]);
        g.drawImage(img, sp.sx, sp.sy, sp.sw, sp.sh, d[j], d[j + 1], d[j + 2], d[j + 3]);
        if (B[i] || tail) {
          if (!B[i]) g.globalAlpha = 0.4 * night;
          g.fillRect(-Wpx[st] / 2, Lpx[st] * 0.75, Wpx[st], Lpx[st] * 0.25);
          g.globalAlpha = 1;
        }
      }
    }
    applyScreen(g, dpr);
  }
}
