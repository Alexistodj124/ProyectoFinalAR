// Calles realistas: banquetas, asfalto, interior de cruces, arriate central, marcas viales
// (separadores, bordes, lineas de alto, cebras, flechas), alumbrado de noche, incidentes y nombres.
// STUB: firmas fijas del contrato; el cuerpo lo implementa feat/ui-calles (ver docs del render).
import type { Network } from "../types";
import { applyScreen, type Camera } from "./camera";
import type { Palette } from "./theme";

// Geometria precalculada en metros del mundo (opaca para quien llama).
export interface RoadModel { net: Network; }

export function buildRoadModel(net: Network): RoadModel {
  return { net };
}

export interface RoadOpts {
  night: number; // 0 dia .. 1 noche
  closedLanes: Set<string>; // carriles cerrados (state.closed_lanes)
  closedEdges: Set<string>; // bordes con incidente (state.incidents); respaldo si closedLanes esta vacio
  time: number; // performance.now() en ms (animaciones sutiles)
}

// Fondo + calzadas + cruces + arriate + marcas (segun LOD) + alumbrado. Deja el contexto en applyScreen.
export function drawRoad(g: CanvasRenderingContext2D, cam: Camera, dpr: number, _m: RoadModel, pal: Palette, _o: RoadOpts): void {
  applyScreen(g, dpr);
  g.fillStyle = pal.ground;
  g.fillRect(0, 0, cam.w, cam.h);
}

// Carriles cerrados: rayado, conos y barrera al inicio del tramo. Deja el contexto en applyScreen.
export function drawIncidents(g: CanvasRenderingContext2D, _cam: Camera, dpr: number, _m: RoadModel, _pal: Palette, _o: RoadOpts): void {
  applyScreen(g, dpr);
}

// Nombres de calles en pantalla (texto derecho, sin choques). Deja el contexto en applyScreen.
export function drawStreetLabels(g: CanvasRenderingContext2D, _cam: Camera, dpr: number, _m: RoadModel, _pal: Palette): void {
  applyScreen(g, dpr);
}

// Rosa de los vientos (flecha N) centrada en (x, y) de pantalla, girada con la camara.
export function drawCompass(g: CanvasRenderingContext2D, _cam: Camera, dpr: number, _pal: Palette, _x: number, _y: number): void {
  applyScreen(g, dpr);
}
