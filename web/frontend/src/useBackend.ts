import { useCallback, useEffect, useRef, useState } from "react";
import { MockBackend, mockNetwork } from "./mock";
import { parseNetwork, parsePolicies, parseScenarios, policyValue } from "./network";
import type {
  AckMessage, Backend, Command, Feed, Network, Option, ServerMessage, SimKey, TickMessage, Toast,
} from "./types";

export type Status = "connecting" | "live" | "mock" | "reconnecting";
export interface Point { t: number; wait: number; queue: number; }
export const WINDOW_S = 600; // ventana de las graficas (tiempo simulado)

const MOCK_SCENARIOS: Option[] = [
  { value: "reforma_pico", label: "Reforma - hora pico (demo)" },
  { value: "reforma_mediodia", label: "Reforma - mediodía (demo)" },
];
const MOCK_POLICIES: Option[] = [{ value: policyValue("dqn", null), label: "Agente RL (demo)" }];

async function getJson(url: string): Promise<unknown> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

// Texto corto de un ack exitoso (null = no mostrar nada).
function ackText(a: AckMessage): string | null {
  const r = (a.result ?? {}) as Record<string, unknown>;
  switch (a.cmd) {
    case "inject": return `Inyectando ${r.vehicles ?? ""} carros en ${r.edge ?? "la calle"}`;
    case "incident": return `Incidente ${r.on ? "activado" : "retirado"} en ${r.edge ?? ""}`;
    case "time_of_day": {
      const d = (r.demand ?? null) as { veh_h?: number } | null;
      return `Hora del día: ${r.profile}${d?.veh_h ? ` (≈${Math.round(d.veh_h)} veh/h)` : ""}`;
    }
    case "reset": return `Escenario ${r.scenario ?? ""} listo`;
    default: return null;
  }
}

// Conecta al WS; si no se puede (o ?mock=1) usa el backend falso con aviso visible.
export function useBackend() {
  const [status, setStatus] = useState<Status>("connecting");
  const [network, setNetwork] = useState<Network | null>(null);
  const [scenarios, setScenarios] = useState<Option[]>([]);
  const [currentScenario, setCurrentScenario] = useState<string | null>(null);
  const [policies, setPolicies] = useState<Option[]>([]);
  const [msg, setMsg] = useState<TickMessage | null>(null);
  const [history, setHistory] = useState<Record<SimKey, Point[]>>({ fijo: [], rl: [] });
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [toasts, setToasts] = useState<Toast[]>([]);
  const backend = useRef<Backend | null>(null);
  const hist = useRef<Record<SimKey, Point[]>>({ fijo: [], rl: [] });
  const feed = useRef<Feed>({ prev: null, cur: null, tPrev: 0, tCur: 0 });
  const netScenario = useRef<string | null>(null);
  const live = useRef(false);
  const toastId = useRef(0);

  const toast = useCallback((kind: Toast["kind"], text: string, ms = kind === "error" ? 7000 : 3500) => {
    const id = ++toastId.current;
    setToasts((l) => [...l.filter((t) => t.kind !== "loading" || kind !== "loading"), { id, kind, text }]);
    if (kind !== "loading") window.setTimeout(() => setToasts((l) => l.filter((t) => t.id !== id)), ms);
    return id;
  }, []);
  const dismissToast = useCallback((id: number) => setToasts((l) => l.filter((t) => t.id !== id)), []);

  const onState = useCallback((m: TickMessage) => {
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
    const f = feed.current, now = performance.now();
    feed.current = { prev: f.cur, cur: m, tPrev: f.tCur, tCur: now };
    setToasts((l) => (l.some((t) => t.kind === "loading") ? l.filter((t) => t.kind !== "loading") : l));
    setMsg(m);
  }, []);

  const onMsg = useCallback((m: ServerMessage) => {
    switch (m.type) {
      case "ack":
        if (!m.ok) toast("error", `${m.cmd ?? "comando"}: ${m.error ?? "falló"}`);
        else { const t = ackText(m); if (t) toast("info", t); }
        break;
      case "loading": toast("loading", `Cargando ${m.scenario ?? "escenario"}...`); break;
      case "error": toast("error", `Error del simulador: ${m.message}`); break;
      default: if ("sims" in m && m.sims) onState(m as TickMessage);
    }
  }, [onState, toast]);

  const loadPolicies = useCallback((scenario?: string) => {
    const q = scenario ? `?scenario=${encodeURIComponent(scenario)}` : "";
    getJson(`/api/policies${q}`).then((j) => live.current && setPolicies(parsePolicies(j))).catch(() => {});
  }, []);

  useEffect(() => {
    let disposed = false;
    let timer = 0;
    let everOpen = false;
    const forceMock = new URLSearchParams(location.search).get("mock") === "1";

    const startMock = () => {
      if (disposed) return;
      backend.current?.close();
      live.current = false;
      backend.current = new MockBackend((m) => onMsg(m));
      setNetwork(parseNetwork(mockNetwork()));
      setScenarios(MOCK_SCENARIOS);
      setPolicies(MOCK_POLICIES);
      setStatus("mock");
    };

    const loadMeta = () => {
      getJson("/api/scenarios").then((j) => {
        if (disposed) return;
        const s = parseScenarios(j);
        setScenarios(s.options);
        setCurrentScenario(s.current);
      }).catch(() => {});
      loadPolicies();
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
        live.current = true;
        backend.current = { send: (c) => ws.send(JSON.stringify(c)), close: () => ws.close() };
        setStatus("live");
        loadMeta();
      };
      ws.onmessage = (e) => {
        try { onMsg(JSON.parse(e.data) as ServerMessage); } catch { /* mensaje invalido: se ignora */ }
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
  }, [onMsg, loadPolicies]);

  // La red depende del escenario: se vuelve a pedir cuando el servidor cambia de escenario.
  const serverScenario = msg?.scenario;
  useEffect(() => {
    if (!live.current || status !== "live" || !serverScenario || netScenario.current === serverScenario) return;
    netScenario.current = serverScenario;
    getJson(`/api/network?scenario=${encodeURIComponent(serverScenario)}`)
      .then((j) => setNetwork(parseNetwork(j)))
      .catch((e) => { netScenario.current = null; toast("error", `No se pudo cargar la red: ${e.message}`); });
  }, [serverScenario, status, toast]);

  const send = useCallback((c: Command) => {
    if (c.cmd === "incident") {
      setClosed((s) => { const n = new Set(s); c.on ? n.add(c.edge) : n.delete(c.edge); return n; });
    }
    if (c.cmd === "reset") { setClosed(new Set()); hist.current = { fijo: [], rl: [] }; setHistory({ fijo: [], rl: [] }); }
    backend.current?.send(c);
  }, []);

  return {
    status, network, scenarios, currentScenario, policies, msg, history, closed, send, feed, toasts, dismissToast,
    loadPolicies,
  };
}
