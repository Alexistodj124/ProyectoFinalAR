import { useCallback, useEffect, useRef, useState } from "react";
import { MockBackend, mockNetworkGeoJSON } from "./mock";
import { parseNetwork, parsePolicies, parseScenarios } from "./network";
import type { Backend, Command, Network, Option, SimKey, TickMessage } from "./types";

export type Status = "connecting" | "live" | "mock" | "reconnecting";
export interface Point { t: number; wait: number; queue: number; }
export const WINDOW_S = 600; // ventana de las graficas (tiempo simulado)

const MOCK_SCENARIOS: Option[] = [
  { value: "reforma_pico", label: "Reforma - hora pico (demo)" },
  { value: "reforma_mediodia", label: "Reforma - mediodía (demo)" },
];
const MOCK_POLICIES: Option[] = [
  { value: JSON.stringify({ algo: "dqn", run: null }), label: "Agente RL (demo)" },
];

async function getJson(url: string): Promise<unknown> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

// Conecta al WS; si no se puede (o ?mock=1) usa el backend falso con aviso visible.
export function useBackend() {
  const [status, setStatus] = useState<Status>("connecting");
  const [network, setNetwork] = useState<Network | null>(null);
  const [scenarios, setScenarios] = useState<Option[]>([]);
  const [policies, setPolicies] = useState<Option[]>([]);
  const [msg, setMsg] = useState<TickMessage | null>(null);
  const [history, setHistory] = useState<Record<SimKey, Point[]>>({ fijo: [], rl: [] });
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const backend = useRef<Backend | null>(null);
  const hist = useRef<Record<SimKey, Point[]>>({ fijo: [], rl: [] });

  const onMsg = useCallback((m: TickMessage) => {
    // t baja => reinicio de la simulacion: limpiar graficas
    const last = hist.current.fijo[hist.current.fijo.length - 1];
    if (last && m.t < last.t) hist.current = { fijo: [], rl: [] };
    for (const k of ["fijo", "rl"] as SimKey[]) {
      const met = m.sims[k]?.metrics;
      if (!met) continue;
      const arr = hist.current[k];
      arr.push({ t: m.t, wait: met.mean_wait, queue: met.queue });
      while (arr.length && arr[0].t < m.t - WINDOW_S) arr.shift();
    }
    setHistory({ fijo: [...hist.current.fijo], rl: [...hist.current.rl] });
    if (m.incidents) setClosed(new Set(m.incidents));
    setMsg(m);
  }, []);

  useEffect(() => {
    let disposed = false;
    let timer = 0;
    let everOpen = false;
    const forceMock = new URLSearchParams(location.search).get("mock") === "1";

    const startMock = () => {
      if (disposed) return;
      backend.current?.close();
      backend.current = new MockBackend(onMsg);
      setNetwork(parseNetwork(mockNetworkGeoJSON()));
      setScenarios(MOCK_SCENARIOS);
      setPolicies(MOCK_POLICIES);
      setStatus("mock");
    };

    const loadMeta = () => {
      getJson("/api/network").then((j) => !disposed && setNetwork(parseNetwork(j))).catch(() => {});
      getJson("/api/scenarios").then((j) => !disposed && setScenarios(parseScenarios(j))).catch(() => {});
      getJson("/api/policies").then((j) => !disposed && setPolicies(parsePolicies(j))).catch(() => {});
    };

    const connect = () => {
      if (disposed) return;
      const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
      const ws = new WebSocket(url);
      let settled = false;
      // si en 2.5 s no abre, caemos a mock (solo en el primer intento)
      const guard = window.setTimeout(() => { if (!everOpen && !settled) { settled = true; ws.close(); startMock(); } }, 2500);
      ws.onopen = () => {
        if (disposed) return ws.close();
        everOpen = true; settled = true; window.clearTimeout(guard);
        backend.current = { send: (c) => ws.send(JSON.stringify(c)), close: () => ws.close() };
        setStatus("live");
        loadMeta();
      };
      ws.onmessage = (e) => {
        try { onMsg(JSON.parse(e.data) as TickMessage); } catch { /* mensaje invalido: se ignora */ }
      };
      ws.onclose = () => {
        window.clearTimeout(guard);
        if (disposed) return;
        if (!everOpen) { if (!settled) { settled = true; startMock(); } return; }
        setStatus("reconnecting");
        timer = window.setTimeout(connect, 2000);
      };
      ws.onerror = () => ws.close();
    };

    if (forceMock) startMock(); else connect();
    return () => { disposed = true; window.clearTimeout(timer); backend.current?.close(); };
  }, [onMsg]);

  const send = useCallback((c: Command) => {
    if (c.cmd === "incident") {
      setClosed((s) => { const n = new Set(s); c.on ? n.add(c.edge) : n.delete(c.edge); return n; });
    }
    if (c.cmd === "reset") { setClosed(new Set()); hist.current = { fijo: [], rl: [] }; setHistory({ fijo: [], rl: [] }); }
    backend.current?.send(c);
  }, []);

  return { status, network, scenarios, policies, msg, history, closed, send };
}
