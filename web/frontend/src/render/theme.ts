// Paletas (dia/noche), umbrales de nivel de detalle y medidas compartidas por road/cars/signals.
// Todo el mapa usa estos tokens: no definir colores sueltos en los modulos de dibujo.

export interface Palette {
  ground: string; // fondo (manzanas)
  sidewalk: string; // banqueta / bordillo bajo el asfalto
  asphalt: string;
  junction: string; // asfalto del interior del cruce
  marking: string; // lineas blancas (separadores, borde, alto, cebra, flechas)
  median: string; // arriate central
  tree: string; // copas de arboles en el arriate
  label: string; // nombres de calles
  labelHalo: string;
  closed: string; // tramo cerrado (rayado)
  cone: string; coneStripe: string;
  housing: string; // caja del semaforo
  lampOff: string;
  green: string; yellow: string; red: string;
  brake: string; // luces de freno
  headlight: string; // haz de los faros (noche)
  streetlight: string; // charco de luz del alumbrado (noche)
  badgeBg: string; badgeBorder: string; badgeText: string; badgeMuted: string;
  curb: string; // bordillo (borde de la calzada y del arriate)
  markingYellow: string; // linea amarilla junto al arriate / centro de calles de doble sentido
  treeHi: string; // brillo de las copas de los arboles
  building: string; buildingEdge: string; // huellas de edificios junto a las calles
}

export const DAY: Palette = {
  ground: "#111815",
  sidewalk: "#454b54",
  asphalt: "#30343c",
  junction: "#2c3038",
  marking: "#e8ecf2",
  median: "#1e3a29",
  tree: "#2e5e3e",
  label: "#c9d2e3",
  labelHalo: "#0b0e14",
  closed: "#ff4d4d",
  cone: "#ff7a1a", coneStripe: "#f4f4f4",
  housing: "#15181e",
  lampOff: "#2a2f38",
  green: "#22e07a", yellow: "#ffd23f", red: "#ff4d4d",
  brake: "#ff2a2a",
  headlight: "#fff3c4",
  streetlight: "#ffcf7a",
  badgeBg: "rgba(14,18,27,0.86)", badgeBorder: "#2a3346", badgeText: "#e8ecf3", badgeMuted: "#8b95a7",
  curb: "#5d646f",
  markingYellow: "#e3b341",
  treeHi: "#4f8f60",
  building: "#19201d", buildingEdge: "#252e2a",
};

export const NIGHT: Palette = {
  ground: "#06090c",
  sidewalk: "#262a31",
  asphalt: "#1a1d23",
  junction: "#181b21",
  marking: "#8f96a3",
  median: "#0f1f16",
  tree: "#173222",
  label: "#aab4c6",
  labelHalo: "#020305",
  closed: "#ff4d4d",
  cone: "#ff7a1a", coneStripe: "#d8d8d8",
  housing: "#0b0d11",
  lampOff: "#1b1f26",
  green: "#2bff8e", yellow: "#ffd84a", red: "#ff5252",
  brake: "#ff1f1f",
  headlight: "#fff3c4",
  streetlight: "#ffc861",
  badgeBg: "rgba(6,9,14,0.88)", badgeBorder: "#232b3b", badgeText: "#e8ecf3", badgeMuted: "#7d879a",
  curb: "#353a44",
  markingYellow: "#8c7743",
  treeHi: "#25503a",
  building: "#0b0f12", buildingEdge: "#141a1f",
};

function parse(c: string): [number, number, number, number] {
  if (c.startsWith("#")) {
    const h = c.length === 4 ? c.slice(1).split("").map((x) => x + x).join("") : c.slice(1);
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 1];
  }
  const m = c.match(/rgba?\(([^)]+)\)/);
  if (!m) return [0, 0, 0, 1];
  const p = m[1].split(",").map((x) => parseFloat(x));
  return [p[0], p[1], p[2], p[3] ?? 1];
}

function lerpColor(a: string, b: string, t: number): string {
  if (t <= 0) return a;
  if (t >= 1) return b;
  const A = parse(a), B = parse(b);
  const v = A.map((x, i) => x + (B[i] - x) * t);
  return `rgba(${Math.round(v[0])},${Math.round(v[1])},${Math.round(v[2])},${v[3].toFixed(3)})`;
}

// Paleta intermedia para la transicion dia -> noche (night en [0, 1]). Cacheada por paso de 1/32.
const mixCache = new Map<number, Palette>();
export function palette(night: number): Palette {
  const q = Math.round(Math.max(0, Math.min(1, night)) * 32);
  let p = mixCache.get(q);
  if (!p) {
    const t = q / 32;
    p = Object.fromEntries(
      (Object.keys(DAY) as (keyof Palette)[]).map((k) => [k, lerpColor(DAY[k], NIGHT[k], t)]),
    ) as unknown as Palette;
    mixCache.set(q, p);
  }
  return p;
}

// Colores de carroceria con su frecuencia aproximada en la calle (blanco, gris y negro dominan).
export const CAR_COLORS: { body: string; weight: number }[] = [
  { body: "#f2f3f5", weight: 22 }, // blanco
  { body: "#b9bec6", weight: 16 }, // plata
  { body: "#6b717b", weight: 13 }, // gris
  { body: "#1d2026", weight: 14 }, // negro
  { body: "#c0262d", weight: 9 }, // rojo
  { body: "#1f4fa3", weight: 8 }, // azul
  { body: "#16305e", weight: 5 }, // azul oscuro
  { body: "#2f6b45", weight: 3 }, // verde
  { body: "#c9b48a", weight: 4 }, // beige
  { body: "#e8b923", weight: 3 }, // amarillo
  { body: "#d9682b", weight: 3 }, // naranja
];

// Medidas reales (m) y minimos en pantalla (px) para que se vean al alejar el zoom.
export const CAR = { length: 4.6, width: 1.85, minLenPx: 6, minWidPx: 3 };
export const SIDEWALK_M = 1.6; // ancho de banqueta a cada lado de la calzada
// Distancia de la linea de alto al final del carril: SUMO detiene el frente del carro ~1 m antes del
// final, asi que la linea va justo ahi y la cebra queda dentro del cruce (en la boca).
export const STOP_BACK_M = 0.8;
export const CROSSWALK_M = 3.5; // largo del paso de cebra (sentido del transito)

// Niveles de detalle: px por metro (Camera.s) a partir de los cuales se dibuja cada cosa.
export const LOD = {
  markings: 1.4, // separadores de carril, lineas de borde, alto, cebras
  arrows: 3.0, // flechas pintadas en los carriles
  heads: 2.0, // semaforos fisicos en cada aproximacion
  carSprite: 1.3, // carros con detalle (debajo: capsula de color)
  shadows: 2.5, // sombras de carros
  trees: 1.0, // arboles del arriate
};

export const FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif";
