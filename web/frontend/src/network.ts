import type { Controlled, Junction, Lane, Network, Option, TlsInfo } from "./types";

type Props = Record<string, unknown>;
type Pt = [number, number];

const str = (v: unknown): string | undefined => (typeof v === "string" ? v : undefined);
const num = (v: unknown, d = 0): number => (typeof v === "number" && isFinite(v) ? v : d);
const pts = (v: unknown): Pt[] =>
  Array.isArray(v) ? v.filter((p) => Array.isArray(p) && p.length >= 2).map((p) => [Number(p[0]), Number(p[1])] as Pt) : [];

export function edgeOfLane(laneId: string): string {
  return laneId.replace(/_\d+$/, "");
}

// Formato de GET /api/network (web/backend/geometry.py):
//   {scenario, bbox:[minx,miny,maxx,maxy], lanes:[{id,edge,shape,width}], junctions:[{id,shape}],
//    tls:[{id,name,x,y,links:[[indiceEnElEstado, carril, x, y], ...]}]}
export function parseNetwork(raw: unknown): Network {
  const r = (raw ?? {}) as Props;
  const lanes: Lane[] = [];
  for (const l of (Array.isArray(r.lanes) ? r.lanes : []) as Props[]) {
    const id = str(l.id);
    const shape = pts(l.shape);
    if (!id || shape.length < 2) continue;
    lanes.push({ id, edge: str(l.edge) ?? edgeOfLane(id), shape, width: num(l.width, 3.2) });
  }
  const junctions: Junction[] = [];
  for (const j of (Array.isArray(r.junctions) ? r.junctions : []) as Props[]) {
    const shape = pts(j.shape);
    if (shape.length >= 3) junctions.push({ id: str(j.id) ?? `j${junctions.length}`, shape });
  }
  const tls: TlsInfo[] = [];
  for (const t of (Array.isArray(r.tls) ? r.tls : []) as Props[]) {
    const id = str(t.id);
    if (!id) continue;
    // links[i] = [indice en la cadena de estado, carril, x, y]; se agrupan por carril
    const byLane = new Map<string, Controlled>();
    for (const lk of (Array.isArray(t.links) ? t.links : []) as unknown[][]) {
      const lane = str(lk[1]);
      if (!lane) continue;
      const c = byLane.get(lane) ?? { lane, idx: [], x: num(lk[2]), y: num(lk[3]) };
      c.idx.push(num(lk[0]));
      byLane.set(lane, c);
    }
    tls.push({ id, name: str(t.name) ?? id, x: num(t.x), y: num(t.y), controlled: [...byLane.values()] });
  }
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const bb = Array.isArray(r.bbox) && r.bbox.length === 4 ? (r.bbox as number[]) : null;
  if (bb) {
    [minX, minY, maxX, maxY] = bb;
  } else {
    for (const l of lanes) for (const [x, y] of l.shape) {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x);
      minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    }
  }
  if (!isFinite(minX)) { minX = minY = 0; maxX = maxY = 1; }
  return { scenario: str(r.scenario), lanes, junctions, tls, bbox: { minX, minY, maxX, maxY } };
}

// GET /api/scenarios -> {current, scenarios:[{name, description, available, net_available, ...}]}
export function parseScenarios(raw: unknown): { options: Option[]; current: string | null } {
  const o = (raw ?? {}) as Props;
  const arr = Array.isArray(raw) ? raw : Array.isArray(o.scenarios) ? (o.scenarios as unknown[]) : [];
  const options = arr.map((x): Option => {
    if (typeof x === "string") return { value: x, label: x };
    const p = x as Props;
    const id = str(p.name) ?? str(p.id) ?? str(p.scenario) ?? "?";
    const ok = p.available !== false;
    return { value: id, label: (str(p.description) ?? str(p.label) ?? id) + (ok ? "" : " (no disponible)"), disabled: !ok };
  });
  // Reforma primero (es lo que se presenta), luego el cruce y al final las redes de juguete
  const rank = (v: string) => (v.startsWith("reforma_") ? 0 : v.startsWith("cruce_") ? 1 : 2);
  options.sort((a, b) => rank(a.value) - rank(b.value));
  return { options, current: str(o.current) ?? null };
}

export const policyValue = (algo: string, run: string | null | undefined) => JSON.stringify({ algo, run: run ?? null });

// GET /api/policies?scenario= -> {policies:[{algo, run, label, kind, compatible, available}], current}
// Solo se ofrecen las compatibles con el escenario y las que se pueden importar.
export function parsePolicies(raw: unknown): Option[] {
  const o = (raw ?? {}) as Props;
  const arr = Array.isArray(raw) ? raw : Array.isArray(o.policies) ? (o.policies as unknown[]) : [];
  const out: Option[] = [];
  for (const x of arr) {
    if (typeof x === "string") { out.push({ value: policyValue(x, null), label: x }); continue; }
    const p = x as Props;
    if (p.compatible === false || p.available === false) continue;
    const algo = str(p.algo) ?? str(p.id) ?? "?";
    if (algo === "fixed") continue; // el lado "fijo" ya es el programa de tiempo fijo
    const run = str(p.run) ?? null;
    out.push({ value: policyValue(algo, run), label: str(p.label) ?? (run ? `${algo} (${run})` : algo) });
  }
  return out;
}
