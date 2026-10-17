// Carros vistos desde arriba: sprites prerenderizados (carroceria, parabrisas, techo, faros),
// color fijo por vehiculo, luces de freno, sombras y faros de noche.
// STUB: firmas fijas del contrato; el cuerpo lo implementa feat/ui-calles.
import { applyScreen, screenAngle, toScreen, type Camera } from "./camera";
import { CAR, type Palette } from "./theme";

export interface CarDraw {
  id: string;
  x: number; y: number; // metros (mundo SUMO), ya interpolados
  angle: number; // grados SUMO (0 = norte, horario)
  speed: number; // m/s
  braking: boolean; // frenando o detenido -> luces de freno encendidas
}

export interface CarOpts {
  night: number; // 0 dia .. 1 noche
  colorBySpeed: boolean; // true: color por velocidad (modo esquematico/leyenda), false: color de carroceria
}

// Color por velocidad: rojo (parado) -> amarillo -> verde (flujo libre, ~14 m/s)
export function speedColor(v: number): string {
  const f = Math.max(0, Math.min(1, v / 13.9));
  return `hsl(${Math.round(f * 125)} 85% 55%)`;
}

export class CarRenderer {
  // Haces de luz de los faros (noche), se llama ANTES de draw() con composicion aditiva.
  drawHeadlights(g: CanvasRenderingContext2D, _cam: Camera, dpr: number, _cars: CarDraw[], _pal: Palette, _o: CarOpts): void {
    applyScreen(g, dpr);
  }

  // Carros (sombra, carroceria, luces). Deja el contexto en applyScreen.
  draw(g: CanvasRenderingContext2D, cam: Camera, dpr: number, cars: CarDraw[], _pal: Palette, o: CarOpts): void {
    applyScreen(g, dpr);
    const L = Math.max(CAR.minLenPx, CAR.length * cam.s), W = Math.max(CAR.minWidPx, CAR.width * cam.s);
    for (const c of cars) {
      const [x, y] = toScreen(cam, c.x, c.y);
      g.save(); g.translate(x, y); g.rotate(screenAngle(cam, c.angle));
      g.fillStyle = o.colorBySpeed ? speedColor(c.speed) : "#cfd5de";
      g.fillRect(-W / 2, -L / 2, W, L);
      g.restore();
    }
  }
}
