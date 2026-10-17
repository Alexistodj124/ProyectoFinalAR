import { useMemo } from "react";
import type { MapStyle, Mode } from "./NetCanvas";
import { chooseRotation } from "./render/camera";
import type { Command, Network, Option, TlsInfo } from "./types";

export type Light = "auto" | "dia" | "noche";

interface Props {
  mode: Mode; setMode: (m: Mode) => void;
  n: number; setN: (n: number) => void;
  profile: string; setProfile: (p: "pico" | "mediodia" | "noche") => void;
  speed: number; setSpeed: (v: 0 | 1 | 5 | 20) => void;
  scenarios: Option[]; policies: Option[];
  scenario: string; setScenario: (s: string) => void;
  policy: string; setPolicy: (s: string) => void;
  closedCount: number;
  demand: number | null;
  send: (c: Command) => void;
  net: Network | null; focus: string | null; onFocus: (id: string) => void;
  style: MapStyle; setStyle: (s: MapStyle) => void;
  light: Light; setLight: (l: Light) => void;
}

function Seg<T extends string | number>({ items, value, onPick, className = "" }:
  { items: [T, string][]; value: T | null; onPick: (v: T) => void; className?: string }) {
  return (
    <div className={`seg ${className}`}>
      {items.map(([v, l]) => (
        <button key={String(v)} className={v === value ? "on" : ""} onClick={() => onPick(v)}>{l}</button>
      ))}
    </div>
  );
}

// Etiqueta corta de un semaforo: "Reforma y 10a calle" -> "10a", "Cruce 2" -> "2".
function shortName(t: TlsInfo): string {
  const s = t.name.replace(/^(av(enida|\.)?\s+)?(la\s+)?reforma\s+y\s+/i, "").replace(/\s+calle$/i, "").replace(/^cruce\s+/i, "").trim();
  return s && s.length <= 5 ? s : t.id;
}

export default function Controls(p: Props) {
  // Botones de Vista en el orden en que se ven los cruces en un mapa ancho (de izquierda a derecha).
  const order = useMemo(() => {
    const net = p.net;
    if (!net?.tls.length) return [];
    const rot = chooseRotation(net, 2, 1), c = Math.cos(rot), s = Math.sin(rot);
    return [...net.tls].sort((a, b) => (a.x - b.x) * c - (a.y - b.y) * s);
  }, [p.net]);

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
          {p.mode === "ver" && "Arrastra para mover; rueda o doble clic para zoom. Clic en un cruce para acercarte."}
          {p.mode === "inyectar" && "Haz clic en una calle de cualquier mapa."}
          {p.mode === "incidente" && `Clic en una calle para cerrar/abrir. Cerradas: ${p.closedCount}`}
        </div>
      </div>
      {order.length > 0 && (
        <div className="group">
          <label>Vista</label>
          <div className="seg vista">
            <button className={p.focus === "all" ? "on" : ""} data-focus="all" onClick={() => p.onFocus("all")}>Todo</button>
            {order.map((t) => (
              <button key={t.id} className={p.focus === t.id ? "on" : ""} data-focus={t.id} title={t.name}
                onClick={() => p.onFocus(t.id)}>{shortName(t)}</button>
            ))}
          </div>
        </div>
      )}
      <div className="group">
        <label>Hora del día</label>
        <Seg value={p.profile} onPick={(v) => { p.setProfile(v as "pico"); p.send({ cmd: "time_of_day", profile: v as "pico" }); }}
          items={[["pico", "Pico"], ["mediodia", "Mediodía"], ["noche", "Noche"]]} />
        {p.demand !== null && <div className="hint">Demanda ≈ {p.demand.toLocaleString("es")} veh/h</div>}
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
          {p.scenarios.map((o) => <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>)}
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
      <div className="group">
        <label>Estilo</label>
        <Seg<MapStyle> value={p.style} onPick={p.setStyle} items={[["realista", "Realista"], ["esquematico", "Esquemático"]]} />
      </div>
      <div className="group">
        <label>Iluminación</label>
        <Seg<Light> value={p.light} onPick={p.setLight} items={[["auto", "Auto"], ["dia", "Día"], ["noche", "Noche"]]} />
      </div>
    </aside>
  );
}
