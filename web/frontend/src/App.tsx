import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Controls, { type Light } from "./Controls";
import Kpis from "./Kpis";
import LineChart from "./LineChart";
import NetCanvas, { type MapStyle, type Mode, type View } from "./NetCanvas";
import Toasts from "./Toasts";
import { policyValue } from "./network";
import {
  chooseRotation, clampView, easeInOutCubic, elongation, fitView, flyMs, lerpView, viewCenter, viewFor, zoomForSpan,
} from "./render/camera";
import type { Network } from "./types";
import { useBackend } from "./useBackend";

const BANNERS = {
  mock: "MODO DEMO SIN BACKEND: datos simulados por el navegador (no es SUMO).",
  reconnecting: "Conexión perdida con el backend. Reintentando...",
  connecting: "Conectando con el backend...",
  live: "",
} as const;

// Parametros de la URL (mandan sobre lo guardado): style=realista|esquematico, night=1|0,
// focus=C12 (semaforo inicial), layout=stacked|side.
const Q = new URLSearchParams(window.location.search);
const LAYOUT_PARAM = Q.get("layout");
const FOCUS_PARAM = Q.get("focus");
const FOCUS_SPAN_M = 140; // metros visibles en el lado corto del lienzo al acercar a un cruce
const SINGLE_SPAN_M = 180; // idem en redes de un solo semaforo (cruce aislado): algo mas de cola a la vista
const STACK_ELONG = 2.2; // redes mas alargadas que esto (el corredor) apilan los mapas en pantallas anchas

const store = {
  get(k: string): string | null { try { return window.localStorage.getItem(k); } catch { return null; } },
  set(k: string, v: string) { try { window.localStorage.setItem(k, v); } catch { /* sin almacenamiento */ } },
};

function initialStyle(): MapStyle {
  const q = Q.get("style");
  if (q === "realista" || q === "esquematico") return q;
  return store.get("demo.style") === "esquematico" ? "esquematico" : "realista";
}

function initialLight(): Light {
  const q = Q.get("night");
  if (q === "1") return "noche";
  if (q === "0") return "dia";
  const s = store.get("demo.light");
  return s === "dia" || s === "noche" ? s : "auto";
}

// true si la ventana mide al menos 1100 px de ancho (mismo corte que el CSS).
function useWide(): boolean {
  const mq = useMemo(() => window.matchMedia("(min-width: 1100px)"), []);
  const [wide, setWide] = useState(mq.matches);
  useEffect(() => {
    const on = () => setWide(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [mq]);
  return wide;
}

interface Size { w: number; h: number; }

export default function App() {
  const { status, network, scenarios, currentScenario, policies, msg, history, closed, send, feed, toasts, dismissToast, loadPolicies } =
    useBackend();
  const [mode, setMode] = useState<Mode>("ver");
  const [n, setN] = useState(10);
  const [profile, setProfile] = useState<"pico" | "mediodia" | "noche">("pico");
  const [speed, setSpeed] = useState<0 | 1 | 5 | 20>(1);
  const [scenario, setScenario] = useState("");
  const [policy, setPolicy] = useState("");
  const [style, setStyleState] = useState<MapStyle>(initialStyle);
  const [light, setLightState] = useState<Light>(initialLight);
  const wide = useWide();

  const setStyle = useCallback((s: MapStyle) => { setStyleState(s); store.set("demo.style", s); }, []);
  const setLight = useCallback((l: Light) => { setLightState(l); store.set("demo.light", l); }, []);

  // El servidor manda: los controles siguen su escenario, politica, hora del dia y velocidad.
  const srv = msg?.scenario ?? currentScenario ?? "";
  useEffect(() => { if (srv) setScenario(srv); }, [srv]);
  useEffect(() => { if (!scenario && scenarios.length) setScenario((scenarios.find((o) => !o.disabled) ?? scenarios[0]).value); }, [scenarios, scenario]);
  useEffect(() => { if (scenario && status === "live") loadPolicies(scenario); }, [scenario, status, loadPolicies]);
  const srvPolicy = msg?.policy ? policyValue(msg.policy.algo, msg.policy.run) : "";
  useEffect(() => { if (srvPolicy) setPolicy(srvPolicy); }, [srvPolicy]);
  // Si la lista cambia (otro escenario) y la politica elegida ya no esta, usar la primera: el <select> la muestra
  // y Reiniciar debe mandar esa, no la anterior (p. ej. MAPPO al pasar a cruce_* daba error de red incompatible).
  useEffect(() => { if (policies.length && !policies.some((o) => o.value === policy)) setPolicy(policies[0].value); }, [policies, policy]);
  const srvProfile = msg?.profile ?? "";
  useEffect(() => { if (srvProfile === "pico" || srvProfile === "mediodia" || srvProfile === "noche") setProfile(srvProfile); }, [srvProfile]);
  const srvSpeed = msg?.speed;
  useEffect(() => { if (srvSpeed === 0 || srvSpeed === 1 || srvSpeed === 5 || srvSpeed === 20) setSpeed(srvSpeed); }, [srvSpeed]);

  // ------------------------------------------------------------ vista compartida y animada
  // focus: "all" (Todo), id de un semaforo, o null si el usuario movio la vista a mano.
  const [view, setViewState] = useState<View>({ k: 1, dx: 0, dy: 0 });
  const [focus, setFocusState] = useState<string | null>("all");
  const [size, setSize] = useState<Size | null>(null);
  const viewRef = useRef(view);
  const focusRef = useRef<string | null>("all");
  const netRef = useRef<Network | null>(null);
  const sizeRef = useRef<Size | null>(null);
  const anim = useRef(0);

  const applyView = useCallback((v: View) => { viewRef.current = v; setViewState(v); }, []);
  const setFocus = useCallback((f: string | null) => { focusRef.current = f; setFocusState(f); }, []);
  const stopAnim = useCallback(() => { if (anim.current) cancelAnimationFrame(anim.current); anim.current = 0; }, []);

  // Vista objetivo de un foco con el tamano actual del lienzo.
  const targetFor = useCallback((id: string): View | null => {
    const net = netRef.current, sz = sizeRef.current;
    if (!net || !sz) return null;
    const rot = chooseRotation(net, sz.w, sz.h);
    if (id === "all") return fitView(net, sz.w, sz.h, rot);
    const t = net.tls.find((t) => t.id === id);
    const span = net.tls.length === 1 ? SINGLE_SPAN_M : FOCUS_SPAN_M;
    return t ? clampView(net, sz.w, sz.h, rot, viewFor(net, sz.w, sz.h, rot, t.x, t.y, zoomForSpan(net, sz.w, sz.h, rot, span))) : null;
  }, []);

  // Anima la vista de los dos mapas hasta `target` (rAF, easeInOutCubic). Arrastre o rueda la cancelan.
  const animateView = useCallback((target: View, ms = 700, anchor?: [number, number]) => {
    stopAnim();
    const net = netRef.current, sz = sizeRef.current;
    if (!net || !sz || ms <= 0) { applyView(target); return; }
    const rot = chooseRotation(net, sz.w, sz.h);
    const from = viewRef.current;
    const dur = anchor ? ms : flyMs(net, sz.w, sz.h, rot, from, target, ms);
    const t0 = performance.now();
    const step = (now: number) => {
      const u = Math.min(1, (now - t0) / dur);
      applyView(u >= 1 ? target : lerpView(net, sz.w, sz.h, rot, from, target, easeInOutCubic(u), anchor));
      anim.current = u >= 1 ? 0 : requestAnimationFrame(step);
    };
    anim.current = requestAnimationFrame(step);
  }, [applyView, stopAnim]);

  const focusOn = useCallback((id: string, ms = 700): boolean => {
    const v = targetFor(id);
    if (!v) return false;
    setFocus(id);
    animateView(v, ms);
    return true;
  }, [targetFor, setFocus, animateView]);

  const onUserView = useCallback((v: View) => { stopAnim(); setFocus(null); applyView(v); }, [stopAnim, setFocus, applyView]);
  const onBadge = useCallback((id: string) => { focusOn(focusRef.current === id ? "all" : id); }, [focusOn]);
  const onZoomAt = useCallback((x: number, y: number) => {
    const sz = sizeRef.current;
    if (!sz) return;
    const from = viewRef.current, k = Math.min(24, from.k * 2), r = k / from.k, cx = sz.w / 2, cy = sz.h / 2;
    setFocus(null);
    animateView({ k, dx: x - cx - (x - cx - from.dx) * r, dy: y - cy - (y - cy - from.dy) * r }, 450, [x, y]);
  }, [setFocus, animateView]);
  const onSize = useCallback((w: number, h: number) => setSize((s) => (s && s.w === w && s.h === h ? s : { w, h })), []);

  // Red nueva: "Todo" (o ?focus= la primera vez); con un solo semaforo (cruce aislado) se acerca a el,
  // porque la red completa deja el cruce diminuto. Mismo foco con otro tamano: se recalcula sin animar;
  // vista libre con otro tamano: conserva el punto del centro y el zoom.
  const appliedNet = useRef<Network | null>(null);
  useLayoutEffect(() => {
    if (!network || !size) return;
    const prevNet = appliedNet.current, prevSize = sizeRef.current;
    netRef.current = network; sizeRef.current = size; appliedNet.current = network;
    if (prevNet !== network) {
      stopAnim();
      const want = !prevNet && FOCUS_PARAM && network.tls.some((t) => t.id === FOCUS_PARAM) ? FOCUS_PARAM
        : network.tls.length === 1 ? network.tls[0].id : "all";
      setFocus(want);
      applyView(targetFor(want) ?? { k: 1, dx: 0, dy: 0 });
      return;
    }
    if (prevSize && prevSize.w === size.w && prevSize.h === size.h) return;
    const f = focusRef.current;
    const v = f ? targetFor(f) : null;
    if (v) { stopAnim(); applyView(v); return; }
    if (prevSize) {
      const c = viewCenter(network, prevSize.w, prevSize.h, chooseRotation(network, prevSize.w, prevSize.h), viewRef.current);
      applyView(viewFor(network, size.w, size.h, chooseRotation(network, size.w, size.h), c[0], c[1], viewRef.current.k));
    }
  }, [network, size, stopAnim, setFocus, applyView, targetFor]);

  useEffect(() => () => stopAnim(), [stopAnim]);

  // Ayudas para scripts (ui_snapshot.py, record_demo.py) y para depurar desde la consola.
  useEffect(() => {
    window.__net = network ?? undefined;
    window.__setView = (x, y, k) => {
      const net = netRef.current, sz = sizeRef.current;
      if (!net || !sz) return;
      stopAnim(); setFocus(null);
      applyView(viewFor(net, sz.w, sz.h, chooseRotation(net, sz.w, sz.h), x, y, k));
    };
    window.__focus = (id) => focusOn(id);
    window.__view = () => ({
      ...viewRef.current, w: sizeRef.current?.w ?? 0, h: sizeRef.current?.h ?? 0,
      focus: focusRef.current, animating: anim.current !== 0,
    });
  }, [network, stopAnim, setFocus, applyView, focusOn]);

  // ------------------------------------------------------------ disposicion y noche
  const elongated = !!network && elongation(network) >= STACK_ELONG;
  const stacked = wide && (LAYOUT_PARAM === "stacked" ? true : LAYOUT_PARAM === "side" ? false : elongated); // telefono: una columna
  const night = light === "noche" ? 1 : light === "dia" ? 0 : profile === "noche" ? 1 : 0;

  const onLane = (edge: string) => {
    if (mode === "inyectar") send({ cmd: "inject", edge, n });
    else if (mode === "incidente") send({ cmd: "incident", edge, on: !closed.has(edge) });
  };

  const f = msg?.sims.fijo, r = msg?.sims.rl;
  const warning = msg?.policy?.warning;
  let improvement: number | null = msg?.improvement_pct ?? null;
  if (improvement === null && f && r && f.metrics.mean_wait > 0.5)
    improvement = ((f.metrics.mean_wait - r.metrics.mean_wait) / f.metrics.mean_wait) * 100;

  const mapProps = {
    net: network!, feed, closed, mode, view, style, night,
    onView: onUserView, onLane, onBadge, onZoomAt,
  };

  return (
    <div className={`app${stacked ? " stacked" : ""}${elongated ? " elongated" : ""}`}>
      {BANNERS[status] && <div className={`banner ${status}`}>{BANNERS[status]}</div>}
      {warning && <div className="banner warn">{warning}</div>}
      <Kpis fijo={f?.metrics} rl={r?.metrics} improvement={improvement} t={msg?.t ?? 0} />
      <main className="main">
        <div className={`maps${stacked ? " stacked" : ""}`}>
          {network ? (
            <>
              <NetCanvas title="Semáforo fijo" accent="#ff9f43" simKey="fijo" onSize={onSize} {...mapProps} />
              <NetCanvas title={`Agente RL${msg?.policy?.label ? ` · ${msg.policy.label}` : ""}`} accent="#2ee6a6" simKey="rl" {...mapProps} />
            </>
          ) : (
            <div className="loading">Cargando red...</div>
          )}
        </div>
        <Controls mode={mode} setMode={setMode} n={n} setN={setN} profile={profile} setProfile={setProfile}
          speed={speed} setSpeed={setSpeed} scenarios={scenarios} policies={policies}
          scenario={scenario} setScenario={setScenario} policy={policy} setPolicy={setPolicy}
          closedCount={closed.size} demand={msg?.demand_veh_h ?? null} send={send}
          net={network} focus={focus} onFocus={focusOn}
          style={style} setStyle={setStyle} light={light} setLight={setLight} />
      </main>
      <footer className="charts">
        <LineChart title="Espera promedio" unit="s" field="wait" fijo={history.fijo} rl={history.rl} />
        <LineChart title="Cola" unit="vehículos detenidos" field="queue" fijo={history.fijo} rl={history.rl} />
      </footer>
      <Toasts toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
