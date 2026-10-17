// Contrato del backend (docs/ARCHITECTURE.md §8).
export type Vehicle = [id: string, x: number, y: number, angle: number, speed: number];

export interface Metrics {
  mean_wait: number;
  queue: number;
  throughput: number;
  arrived: number;
}

export interface SimState {
  vehicles: Vehicle[];
  tls: Record<string, string>; // id -> cadena de estados ("GGrr...")
  metrics: Metrics;
}

export type SimKey = "fijo" | "rl";

export interface TickMessage {
  t: number;
  sims: Record<SimKey, SimState>;
  improvement_pct?: number | null;
  incidents?: string[]; // opcional: aristas cerradas segun el servidor
}

export type Command =
  | { cmd: "inject"; edge: string; n: number }
  | { cmd: "time_of_day"; profile: "pico" | "mediodia" | "noche" }
  | { cmd: "incident"; edge: string; on: boolean }
  | { cmd: "speed"; value: 0 | 1 | 5 | 20 }
  | { cmd: "reset"; scenario?: string; policy?: { algo: string; run?: string | null } };

// Red ya normalizada para dibujar (coordenadas SUMO, y hacia arriba).
export interface Lane {
  id: string;
  edge: string;
  shape: [number, number][];
  internal: boolean;
}
export interface TlsInfo {
  id: string;
  x: number;
  y: number;
  lanes: string[]; // carriles controlados en el orden de la cadena de estado (si se conoce)
}
export interface Network {
  lanes: Lane[];
  tls: TlsInfo[];
  bbox: { minX: number; minY: number; maxX: number; maxY: number };
}

export interface Option {
  value: string;
  label: string;
}
export interface Backend {
  send(cmd: Command): void;
  close(): void;
}
