import type { Lane, Network, Option, TlsInfo } from "./types";

// Normaliza el GeoJSON del backend. Es tolerante con los nombres de propiedades
// porque el formato exacto lo define la otra rama (id/lane_id, edge/edge_id, ...).
type Props = Record<string, unknown>;
interface Feature {
  geometry?: { type: string; coordinates: unknown };
  properties?: Props;
}

const str = (v: unknown): string | undefined => (typeof v === "string" ? v : undefined);

export function edgeOfLane(laneId: string): string {
  return laneId.replace(/_\d+$/, "");
}

export function parseNetwork(raw: unknown): Network {
  const feats: Feature[] = Array.isArray((raw as { features?: Feature[] })?.features)
    ? (raw as { features: Feature[] }).features
    : [];
  const lanes: Lane[] = [];
  const tls: TlsInfo[] = [];
  for (const f of feats) {
    const p = f.properties ?? {};
    const g = f.geometry;
    if (!g) continue;
    if (g.type === "LineString" || g.type === "MultiLineString") {
      const lines = (g.type === "LineString" ? [g.coordinates] : g.coordinates) as number[][][];
      for (const line of lines) {
        const id = str(p.id) ?? str(p.lane_id) ?? str(p.lane) ?? `lane${lanes.length}`;
        const edge = str(p.edge) ?? str(p.edge_id) ?? edgeOfLane(id);
        lanes.push({
          id,
          edge,
          shape: line.map((c) => [c[0], c[1]] as [number, number]),
          internal: id.startsWith(":") || p.internal === true,
        });
      }
    } else if (g.type === "Point") {
      const c = g.coordinates as number[];
      const id = str(p.tls) ?? str(p.tls_id) ?? str(p.id);
      if (!id) continue;
      const ls = (p.lanes ?? p.controlled_lanes) as unknown;
      tls.push({
        id,
        x: c[0],
        y: c[1],
        lanes: Array.isArray(ls) ? ls.filter((s): s is string => typeof s === "string") : [],
      });
    }
  }
  // Si hay TLS sin posicion (p. ej. propiedades en un carril), no se puede dibujar marca.
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const l of lanes) for (const [x, y] of l.shape) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  if (!isFinite(minX)) { minX = minY = 0; maxX = maxY = 1; }
  return { lanes, tls, bbox: { minX, minY, maxX, maxY } };
}

// Acepta ["a","b"] o [{id|name|scenario, label|description}].
export function parseScenarios(raw: unknown): Option[] {
  const arr = Array.isArray(raw) ? raw : Array.isArray((raw as { scenarios?: unknown[] })?.scenarios)
    ? (raw as { scenarios: unknown[] }).scenarios : [];
  return arr.map((x) => {
    if (typeof x === "string") return { value: x, label: x };
    const o = x as Props;
    const id = str(o.id) ?? str(o.name) ?? str(o.scenario) ?? "?";
    return { value: id, label: str(o.label) ?? str(o.description) ?? id };
  });
}

// Acepta ["fijo"] o [{algo, run, label}]. value = JSON de la politica.
export function parsePolicies(raw: unknown): Option[] {
  const arr = Array.isArray(raw) ? raw : Array.isArray((raw as { policies?: unknown[] })?.policies)
    ? (raw as { policies: unknown[] }).policies : [];
  return arr.map((x) => {
    if (typeof x === "string") return { value: JSON.stringify({ algo: x }), label: x };
    const o = x as Props;
    const algo = str(o.algo) ?? str(o.name) ?? str(o.id) ?? "?";
    const run = str(o.run) ?? null;
    return { value: JSON.stringify({ algo, run }), label: str(o.label) ?? (run ? `${algo} (${run})` : algo) };
  });
}
