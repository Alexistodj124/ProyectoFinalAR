// Contrato del backend (web/README.md y docs/ARCHITECTURE.md §8).
export type Vehicle = [id: string, x: number, y: number, angle: number, speed: number];

export interface Metrics {
  mean_wait: number;
  queue: number;
  throughput: number;
  arrived: number;
  n_vehicles?: number;
}

export interface SimState {
  vehicles: Vehicle[];
  tls: Record<string, string>; // id -> cadena de estados ("GGrr..."), un caracter por enlace
  metrics: Metrics;
}

export type SimKey = "fijo" | "rl";

export interface PolicyInfo {
  algo: string;
  run?: string | null;
  label?: string;
  warning?: string | null;
}

// Mensaje `type: "state"` (el mock no manda `type`).
export interface TickMessage {
  type?: "state";
  t: number;
  sims: Record<SimKey, SimState>;
  improvement_pct?: number | null;
  incidents?: string[]; // bordes cerrados segun el servidor
  scenario?: string;
  profile?: string | null;
  speed?: number;
  episode?: number;
  demand_veh_h?: number | null;
  policy?: PolicyInfo;
}

// Otros mensajes del servidor (sin `sims`).
export interface AckMessage {
  type: "ack";
  cmd?: string;
  ok: boolean;
  result?: Record<string, unknown>;
  error?: string;
}
export interface LoadingMessage { type: "loading"; scenario?: string; }
export interface ErrorMessage { type: "error"; message: string; }
export type ServerMessage = TickMessage | AckMessage | LoadingMessage | ErrorMessage;

export type Command =
  | { cmd: "inject"; edge: string; n: number }
  | { cmd: "time_of_day"; profile: "pico" | "mediodia" | "noche" }
  | { cmd: "incident"; edge: string; on: boolean }
  | { cmd: "speed"; value: 0 | 1 | 5 | 20 }
  | { cmd: "reset"; scenario?: string; policy?: { algo: string; run?: string | null } };

// Red ya normalizada para dibujar (coordenadas SUMO en metros, y hacia el norte).
export interface Lane {
  id: string;
  edge: string;
  shape: [number, number][];
  width: number;
}
export interface Junction {
  id: string;
  shape: [number, number][];
}
// Un carril controlado por un semaforo: `idx` son las posiciones de la cadena de estado
// (un carril puede tener varios enlaces: recto, izquierda...) y (x, y) su linea de alto.
export interface Controlled {
  lane: string;
  idx: number[];
  x: number;
  y: number;
}
export interface TlsInfo {
  id: string;
  name: string;
  x: number;
  y: number;
  controlled: Controlled[];
}
export interface Network {
  scenario?: string;
  lanes: Lane[];
  junctions: Junction[];
  tls: TlsInfo[];
  bbox: { minX: number; minY: number; maxX: number; maxY: number };
}

export interface Option {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface Toast {
  id: number;
  kind: "info" | "error" | "loading";
  text: string;
}

export interface Backend {
  send(cmd: Command): void;
  close(): void;
}

// Los dos ultimos mensajes de estado y el instante (ms, performance.now) en que llegaron:
// el lienzo interpola las posiciones entre ellos (con ~1 mensaje de retraso).
export interface Feed {
  prev: TickMessage | null;
  cur: TickMessage | null;
  tPrev: number;
  tCur: number;
}
