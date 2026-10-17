import { useEffect, useState } from "react";
import Controls from "./Controls";
import Kpis from "./Kpis";
import LineChart from "./LineChart";
import NetCanvas, { type Mode, type View } from "./NetCanvas";
import { useBackend } from "./useBackend";

const BANNERS = {
  mock: "MODO DEMO SIN BACKEND: datos simulados por el navegador (no es SUMO).",
  reconnecting: "Conexión perdida con el backend. Reintentando...",
  connecting: "Conectando con el backend...",
  live: "",
} as const;

export default function App() {
  const { status, network, scenarios, policies, msg, history, closed, send } = useBackend();
  const [mode, setMode] = useState<Mode>("ver");
  const [n, setN] = useState(10);
  const [profile, setProfile] = useState<"pico" | "mediodia" | "noche">("pico");
  const [speed, setSpeed] = useState<0 | 1 | 5 | 20>(1);
  const [scenario, setScenario] = useState("");
  const [policy, setPolicy] = useState("");
  const [view, setView] = useState<View>({ k: 1, dx: 0, dy: 0 }); // compartida: los dos mapas se mueven juntos

  useEffect(() => { if (!scenario && scenarios.length) setScenario(scenarios[0].value); }, [scenarios, scenario]);
  useEffect(() => { if (!policy && policies.length) setPolicy(policies[0].value); }, [policies, policy]);

  const onLane = (edge: string) => {
    if (mode === "inyectar") send({ cmd: "inject", edge, n });
    else if (mode === "incidente") send({ cmd: "incident", edge, on: !closed.has(edge) });
  };

  const f = msg?.sims.fijo, r = msg?.sims.rl;
  let improvement: number | null = msg?.improvement_pct ?? null;
  if (improvement === null && f && r && f.metrics.mean_wait > 0.5)
    improvement = ((f.metrics.mean_wait - r.metrics.mean_wait) / f.metrics.mean_wait) * 100;

  return (
    <div className="app">
      {BANNERS[status] && <div className={`banner ${status}`}>{BANNERS[status]}</div>}
      <Kpis fijo={f?.metrics} rl={r?.metrics} improvement={improvement} t={msg?.t ?? 0} />
      <main className="main">
        <div className="maps">
          {network ? (
            <>
              <NetCanvas title="Semáforo fijo" accent="#ff9f43" net={network} sim={f} closed={closed}
                mode={mode} view={view} onView={setView} onLane={onLane} />
              <NetCanvas title="Agente RL" accent="#2ee6a6" net={network} sim={r} closed={closed}
                mode={mode} view={view} onView={setView} onLane={onLane} />
            </>
          ) : (
            <div className="loading">Cargando red...</div>
          )}
        </div>
        <Controls mode={mode} setMode={setMode} n={n} setN={setN} profile={profile} setProfile={setProfile}
          speed={speed} setSpeed={setSpeed} scenarios={scenarios} policies={policies}
          scenario={scenario} setScenario={setScenario} policy={policy} setPolicy={setPolicy}
          closedCount={closed.size} send={send} />
      </main>
      <footer className="charts">
        <LineChart title="Espera promedio" unit="s" field="wait" fijo={history.fijo} rl={history.rl} />
        <LineChart title="Cola" unit="vehículos detenidos" field="queue" fijo={history.fijo} rl={history.rl} />
      </footer>
    </div>
  );
}
