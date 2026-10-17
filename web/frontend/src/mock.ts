// Backend falso: red tipo corredor (4 semaforos) + vehiculos + metricas, para
// desarrollar y demostrar la UI sin FastAPI. Imita el contrato de docs/ARCHITECTURE.md §8.
import type { Backend, Command, SimKey, SimState, TickMessage, Vehicle } from "./types";

interface MEdge { id: string; x0: number; y0: number; x1: number; y1: number; len: number; next?: string; to?: string; dir: "EW" | "NS"; }

const XS = [0, 220, 440, 660];
const BX0 = -220, BX1 = 880, CY = 170, OFF = 5;

function buildEdges(): MEdge[] {
  const E: MEdge[] = [];
  const add = (id: string, x0: number, y0: number, x1: number, y1: number, dir: "EW" | "NS", to?: string) =>
    E.push({ id, x0, y0, x1, y1, len: Math.hypot(x1 - x0, y1 - y0), dir, to });
  const nodes = [BX0, ...XS, BX1];
  for (let i = 0; i < nodes.length - 1; i++) {
    add(`EB${i}`, nodes[i], -OFF, nodes[i + 1], -OFF, "EW", i < XS.length ? `J${i}` : undefined);
    add(`WB${i}`, nodes[i + 1], OFF, nodes[i], OFF, "EW", i > 0 ? `J${i - 1}` : undefined);
  }
  XS.forEach((x, i) => {
    add(`SN${i}`, x + OFF, -CY, x + OFF, 0, "NS", `J${i}`);   // sur -> norte (llega)
    add(`SO${i}`, x + OFF, 0, x + OFF, -CY, "NS");              // sale hacia el sur
    add(`NS${i}`, x - OFF, CY, x - OFF, 0, "NS", `J${i}`);
    add(`NO${i}`, x - OFF, 0, x - OFF, CY, "NS");
  });
  for (let i = 0; i < nodes.length - 2; i++) { // encadena rectas
    E.find((e) => e.id === `EB${i}`)!.next = `EB${i + 1}`;
    E.find((e) => e.id === `WB${i + 1}`)!.next = `WB${i}`;
  }
  XS.forEach((_, i) => {
    E.find((e) => e.id === `SN${i}`)!.next = `NO${i}`;
    E.find((e) => e.id === `NS${i}`)!.next = `SO${i}`;
  });
  return E;
}
const EDGES = buildEdges();
const EDGE = new Map(EDGES.map((e) => [e.id, e]));
const ENTRIES = EDGES.filter((e) => e.id === "EB0" || e.id === `WB${XS.length}` || /^(SN|NS)/.test(e.id));
const TLS_LANES = XS.map((_, i) => [`EB${i}`, `WB${i + 1}`, `SN${i}`, `NS${i}`]);

// Red del mock en el mismo formato que GET /api/network del backend real.
export function mockNetwork() {
  const lanes = EDGES.map((e) => ({ id: `${e.id}_0`, edge: e.id, shape: [[e.x0, e.y0], [e.x1, e.y1]], width: 3.2 }));
  const tls = XS.map((x, i) => ({
    id: `J${i}`,
    name: `Cruce ${i + 1}`,
    x,
    y: 0,
    links: TLS_LANES[i].map((id, k) => {
      const e = EDGE.get(id)!;
      return [k, `${id}_0`, e.x1, e.y1];
    }),
  }));
  return { scenario: "mock", bbox: [BX0, -CY, BX1, CY], lanes, junctions: [], tls };
}

// RNG determinista: ambas sims reciben la misma demanda (como en el backend real).
function mulberry32(a: number) {
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface MVeh { id: string; edge: string; s: number; v: number; wait: number; }
const RATES = { pico: 0.22, mediodia: 0.12, noche: 0.04 }; // veh/s por entrada

class MockSim {
  vehs: MVeh[] = [];
  rng = mulberry32(42);
  phase = [0, 0, 0, 0]; // 0: EW verde, 1: NS verde
  phaseT = [0, 0, 0, 0];
  waits: number[] = [];
  arrived = 0;
  n = 0;
  constructor(readonly kind: SimKey) {}

  green(tls: number, e: MEdge) { return (this.phase[tls] === 0) === (e.dir === "EW"); }

  step(dt: number, rate: number, closed: Set<string>, injects: [string, number][]) {
    // demanda (mismo orden de llamadas al rng en ambas sims)
    for (const en of ENTRIES) {
      const r = en.dir === "EW" ? rate : rate * 0.35;
      if (this.rng() < r * dt && !closed.has(en.id)) this.spawn(en.id);
    }
    for (const [edge, k] of injects) for (let i = 0; i < k; i++) this.spawn(edge, -i * 9);
    // semaforos: fijo = ciclo de 30 s; "rl" = elige la fase con mas cola (min verde 8 s)
    for (let i = 0; i < XS.length; i++) {
      this.phaseT[i] += dt;
      if (this.kind === "fijo") {
        if (this.phaseT[i] >= 30) { this.phase[i] ^= 1; this.phaseT[i] = 0; }
      } else if (this.phaseT[i] >= 8) {
        const q = [0, 0];
        for (const v of this.vehs) {
          const e = EDGE.get(v.edge)!;
          if (e.to === `J${i}` && v.v < 1 && e.len - v.s < 60) q[e.dir === "EW" ? 0 : 1]++;
        }
        const want = q[0] >= q[1] ? 0 : 1;
        if (want !== this.phase[i] && q[want] > q[this.phase[i]] + 1) { this.phase[i] = want; this.phaseT[i] = 0; }
      }
    }
    // dinamica: seguimiento de lider + parada ante rojo/cierre
    const byEdge = new Map<string, MVeh[]>();
    for (const v of this.vehs) (byEdge.get(v.edge) ?? byEdge.set(v.edge, []).get(v.edge)!).push(v);
    const done = new Set<string>();
    for (const [eid, list] of byEdge) {
      const e = EDGE.get(eid)!;
      list.sort((a, b) => b.s - a.s);
      let leaderS = Infinity;
      for (const v of list) {
        const stopLine = e.to !== undefined && (closed.has(eid) || !this.green(Number(e.to.slice(1)), e)) ? e.len - 1 : Infinity;
        const limit = Math.min(leaderS - 7, stopLine);
        const gap = limit - v.s;
        const vTarget = gap < 2 ? 0 : Math.min(13.9, Math.sqrt(2 * 3 * Math.max(0, gap - 1)));
        v.v += Math.max(-4.5 * dt, Math.min(2.5 * dt, vTarget - v.v));
        v.s = Math.min(v.s + v.v * dt, limit < v.s ? v.s : limit);
        v.wait += v.v < 0.5 ? dt : 0;
        leaderS = v.s;
        if (v.s >= e.len - 0.01) {
          if (e.next && !closed.has(e.next)) { v.edge = e.next; v.s = 0; }
          else if (!e.next) { done.add(v.id); this.arrived++; this.waits.push(v.wait); }
        }
      }
    }
    if (done.size) this.vehs = this.vehs.filter((v) => !done.has(v.id));
    if (this.waits.length > 400) this.waits.splice(0, this.waits.length - 400);
  }

  spawn(edge: string, s = 0) {
    this.vehs.push({ id: `${this.kind[0]}${this.n++}`, edge, s: Math.max(0, s), v: 8, wait: 0 });
  }

  state(t: number): SimState {
    const vehicles: Vehicle[] = this.vehs.map((v) => {
      const e = EDGE.get(v.edge)!, f = v.s / e.len;
      const ang = ((Math.atan2(e.x1 - e.x0, e.y1 - e.y0) * 180) / Math.PI + 360) % 360;
      return [v.id, e.x0 + (e.x1 - e.x0) * f, e.y0 + (e.y1 - e.y0) * f, ang, v.v];
    });
    const tls: Record<string, string> = {};
    XS.forEach((_, i) => {
      tls[`J${i}`] = TLS_LANES[i].map((id) => (this.green(i, EDGE.get(id)!) ? "G" : "r")).join("");
    });
    const live = this.vehs.map((v) => v.wait);
    const all = [...this.waits, ...live];
    return {
      vehicles,
      tls,
      metrics: {
        mean_wait: all.length ? all.reduce((a, b) => a + b, 0) / all.length : 0,
        queue: this.vehs.filter((v) => v.v < 0.5).length,
        throughput: t > 0 ? (this.arrived / t) * 3600 : 0,
        arrived: this.arrived,
      },
    };
  }
}

export class MockBackend implements Backend {
  private sims: Record<SimKey, MockSim> = { fijo: new MockSim("fijo"), rl: new MockSim("rl") };
  private t = 0;
  private speed = 1;
  private profile: keyof typeof RATES = "pico";
  private closed = new Set<string>();
  private pending: [string, number][] = [];
  private timer: number;

  constructor(private onMsg: (m: TickMessage) => void) {
    this.timer = window.setInterval(() => this.tick(), 100);
  }

  private tick() {
    if (this.speed > 0) {
      // 10 ticks reales/s; el tiempo simulado avanza 0.1*speed s por tick, en pasos <= 0.5 s.
      let left = 0.1 * this.speed;
      let inj = this.pending; this.pending = [];
      while (left > 1e-9) {
        const dt = Math.min(0.5, left);
        for (const s of Object.values(this.sims)) s.step(dt, RATES[this.profile], this.closed, inj);
        inj = []; this.t += dt; left -= dt;
      }
    }
    const f = this.sims.fijo.state(this.t), r = this.sims.rl.state(this.t);
    const a = f.metrics.mean_wait, b = r.metrics.mean_wait;
    this.onMsg({
      t: this.t,
      sims: { fijo: f, rl: r },
      improvement_pct: a > 0.5 ? ((a - b) / a) * 100 : 0,
      incidents: [...this.closed],
      profile: this.profile,
      speed: this.speed,
    });
  }

  send(c: Command) {
    switch (c.cmd) {
      case "inject": if (EDGE.has(c.edge)) this.pending.push([c.edge, c.n]); break;
      case "time_of_day": this.profile = c.profile; break;
      case "incident": c.on ? this.closed.add(c.edge) : this.closed.delete(c.edge); break;
      case "speed": this.speed = c.value; break;
      case "reset":
        this.sims = { fijo: new MockSim("fijo"), rl: new MockSim("rl") };
        this.t = 0; this.closed.clear(); this.pending = []; break;
    }
  }
  close() { window.clearInterval(this.timer); }
}
