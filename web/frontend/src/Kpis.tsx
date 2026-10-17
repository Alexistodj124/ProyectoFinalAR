import type { Metrics } from "./types";

interface Props { fijo?: Metrics; rl?: Metrics; improvement: number | null; t: number; }

const fmt = (v: number | undefined, d = 1) => (v === undefined || !isFinite(v) ? "-" : v.toFixed(d));

function Kpi({ label, unit, a, b, d = 1 }: { label: string; unit: string; a?: number; b?: number; d?: number }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label} <small>{unit}</small></div>
      <div className="kpi-vals">
        <span className="fijo">{fmt(a, d)}</span>
        <span className="vs">vs</span>
        <span className="rl">{fmt(b, d)}</span>
      </div>
    </div>
  );
}

export default function Kpis({ fijo, rl, improvement, t }: Props) {
  const good = (improvement ?? 0) >= 0;
  const mm = Math.floor(t / 60), ss = Math.floor(t % 60);
  return (
    <header className="kpis">
      <div className="title">
        <h1>Semáforos inteligentes · Av. La Reforma</h1>
        <div className="clock">Tiempo simulado {String(mm).padStart(2, "0")}:{String(ss).padStart(2, "0")}
          <span className="key"><i style={{ background: "#ff9f43" }} />Fijo<i style={{ background: "#2ee6a6" }} />RL</span>
        </div>
      </div>
      <Kpi label="Espera promedio" unit="s" a={fijo?.mean_wait} b={rl?.mean_wait} />
      <Kpi label="Cola" unit="veh" a={fijo?.queue} b={rl?.queue} d={0} />
      <Kpi label="Throughput" unit="veh/h" a={fijo?.throughput} b={rl?.throughput} d={0} />
      <div className={`improve ${good ? "good" : "bad"}`}>
        <div className="kpi-label">Mejora</div>
        <div className="improve-val">{improvement === null ? "-" : `${improvement >= 0 ? "" : "−"}${Math.abs(improvement).toFixed(1)} %`}</div>
      </div>
    </header>
  );
}
