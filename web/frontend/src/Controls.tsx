import type { Mode } from "./NetCanvas";
import type { Command, Option } from "./types";

interface Props {
  mode: Mode; setMode: (m: Mode) => void;
  n: number; setN: (n: number) => void;
  profile: string; setProfile: (p: "pico" | "mediodia" | "noche") => void;
  speed: number; setSpeed: (v: 0 | 1 | 5 | 20) => void;
  scenarios: Option[]; policies: Option[];
  scenario: string; setScenario: (s: string) => void;
  policy: string; setPolicy: (s: string) => void;
  closedCount: number;
  send: (c: Command) => void;
}

function Seg<T extends string | number>({ items, value, onPick }: { items: [T, string][]; value: T; onPick: (v: T) => void }) {
  return (
    <div className="seg">
      {items.map(([v, l]) => (
        <button key={String(v)} className={v === value ? "on" : ""} onClick={() => onPick(v)}>{l}</button>
      ))}
    </div>
  );
}

export default function Controls(p: Props) {
  return (
    <aside className="controls">
      <div className="group">
        <label>Modo de clic en el mapa</label>
        <Seg<Mode> value={p.mode} onPick={p.setMode}
          items={[["ver", "Ver"], ["inyectar", "Inyectar"], ["incidente", "Incidente"]]} />
        {p.mode === "inyectar" && (
          <div className="slider">
            <span>Carros: <b>{p.n}</b></span>
            <input type="range" min={1} max={40} value={p.n} onChange={(e) => p.setN(+e.target.value)} />
          </div>
        )}
        <div className="hint">
          {p.mode === "ver" && "Arrastra para mover, rueda para zoom."}
          {p.mode === "inyectar" && "Haz clic en una calle de cualquier mapa."}
          {p.mode === "incidente" && `Clic en una calle para cerrar/abrir. Cerradas: ${p.closedCount}`}
        </div>
      </div>
      <div className="group">
        <label>Hora del día</label>
        <Seg value={p.profile} onPick={(v) => { p.setProfile(v as "pico"); p.send({ cmd: "time_of_day", profile: v as "pico" }); }}
          items={[["pico", "Pico"], ["mediodia", "Mediodía"], ["noche", "Noche"]]} />
      </div>
      <div className="group">
        <label>Velocidad</label>
        <Seg<number> value={p.speed} onPick={(v) => { p.setSpeed(v as 0); p.send({ cmd: "speed", value: v as 0 }); }}
          items={[[0, "Pausa"], [1, "1×"], [5, "5×"], [20, "20×"]]} />
      </div>
      <div className="group">
        <label>Escenario</label>
        <select value={p.scenario} onChange={(e) => p.setScenario(e.target.value)}>
          {p.scenarios.length === 0 && <option value="">(sin datos)</option>}
          {p.scenarios.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <label>Política RL</label>
        <select value={p.policy} onChange={(e) => p.setPolicy(e.target.value)}>
          {p.policies.length === 0 && <option value="">(sin datos)</option>}
          {p.policies.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <button className="reset" onClick={() => p.send({
          cmd: "reset",
          scenario: p.scenario || undefined,
          policy: p.policy ? JSON.parse(p.policy) : undefined,
        })}>Reiniciar</button>
      </div>
    </aside>
  );
}
