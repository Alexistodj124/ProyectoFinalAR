// Semaforos: barra de color en la linea de alto de cada carril, semaforo fisico (caja con luces
// roja/ambar/verde y flecha de vuelta) en cada aproximacion, tarjeta por cruce con el estado de
// cada eje y el tiempo en la fase, y destello al cambiar de fase.
// STUB: firmas fijas del contrato; el cuerpo lo implementa feat/ui-calles.
import type { Network } from "../types";
import { applyScreen, type Camera } from "./camera";
import type { Palette } from "./theme";

export type Lamp = "G" | "Y" | "R" | "O"; // verde, amarillo, rojo, apagado/desconocido

// Geometria y agrupacion precalculadas (opaca para quien llama).
export interface SignalModel { net: Network; }

export function buildSignalModel(net: Network): SignalModel {
  return { net };
}

// Sigue los cambios de cada semaforo entre mensajes: color de cada grupo/eje y cuando cambio
// (tiempo simulado y performance.now) para el temporizador y el destello.
export class SignalTracker {
  constructor(public model: SignalModel) {}
  // Llamar una vez por mensaje de estado nuevo (t = tiempo simulado del mensaje).
  update(_t: number, _states: Record<string, string> | undefined, _now: number): void {}
  reset(): void {}
}

export interface SignalOpts {
  night: number; // 0 dia .. 1 noche
  accent: string; // color del panel (fijo naranja, RL verde agua) para destellos
  side: "fijo" | "rl";
  now: number; // performance.now() ms
  simT: number; // tiempo simulado actual (s)
}

// Caja clicable de una tarjeta de cruce (px CSS del lienzo).
export interface BadgeHit { id: string; x: number; y: number; w: number; h: number; }

// Barras de color en la linea de alto de cada carril controlado (siempre visibles).
export function drawStopBars(g: CanvasRenderingContext2D, _cam: Camera, dpr: number, _m: SignalModel,
  _states: Record<string, string> | undefined, _pal: Palette): void {
  applyScreen(g, dpr);
}

// Semaforos fisicos en cada aproximacion (con zoom >= LOD.heads).
export function drawHeads(g: CanvasRenderingContext2D, _cam: Camera, dpr: number, _m: SignalModel,
  _states: Record<string, string> | undefined, _pal: Palette, _o: SignalOpts): void {
  applyScreen(g, dpr);
}

// Anillos que se expanden en el cruce cuando cambia de fase.
export function drawFlashes(g: CanvasRenderingContext2D, _cam: Camera, dpr: number, _m: SignalModel,
  _tr: SignalTracker, _o: SignalOpts): void {
  applyScreen(g, dpr);
}

// Tarjetas por cruce (nombre, luz de cada eje, segundos en la fase). Devuelve sus cajas para clic.
export function drawBadges(g: CanvasRenderingContext2D, _cam: Camera, dpr: number, _m: SignalModel,
  _tr: SignalTracker, _pal: Palette, _o: SignalOpts): BadgeHit[] {
  applyScreen(g, dpr);
  return [];
}
