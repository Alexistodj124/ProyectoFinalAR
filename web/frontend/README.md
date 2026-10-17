# Frontend de la demo en vivo (React + Vite + TypeScript)

Dos mapas sincronizados ("Semáforo fijo" vs "Agente RL"), KPIs grandes (espera promedio, cola, throughput, mejora %), panel de control y gráficas en vivo (últimos 10 min de tiempo simulado). Tema oscuro pensado para proyector. Sin librerías de UI: los mapas y gráficas se dibujan a mano en `<canvas>`.

## Correr en desarrollo
```bash
# 1) backend (otra terminal, desde la raíz del repo): FastAPI en :8000
# 2) frontend
cd web/frontend
npm install
npm run dev          # http://localhost:5173
```
`vite.config.ts` hace proxy de `/api` y `/ws` hacia `http://localhost:8000`.

## Modo mock (sin backend)
- Forzado: abrir `http://localhost:5173/?mock=1`.
- Automático: si el WebSocket no conecta en ~2.5 s, la UI cambia a datos falsos generados en el navegador y muestra un banner amarillo "MODO DEMO SIN BACKEND". Útil para desarrollar la UI y como respaldo visual (los números no vienen de SUMO).

## Uso
- **Modo de clic**: *Ver* (arrastrar = mover, rueda = zoom; ambos mapas comparten la vista), *Inyectar* (clic en una calle de cualquier mapa envía `inject` con el número de carros del slider), *Incidente* (clic cierra o reabre la calle; las cerradas se resaltan en rojo).
- **Hora del día**: pico / mediodía / noche. **Velocidad**: pausa / 1× / 5× / 20×.
- **Escenario** y **Política RL** salen de `/api/scenarios` y `/api/policies`; *Reiniciar* manda `reset`.

## Contrato esperado del backend (docs/ARCHITECTURE.md §8)
- `GET /api/network`: GeoJSON. Carriles = `LineString` con propiedades `id` (carril) y `edge` (si falta, se deduce quitando el sufijo `_N`); coordenadas en el sistema x/y de SUMO. Semáforos = `Point` con `tls` (id) y, opcionalmente, `lanes` (carriles controlados en el orden de la cadena de estado). Sin `lanes`, se dibuja un círculo en la intersección.
- `GET /api/scenarios` y `GET /api/policies`: lista de strings u objetos (`id|name`, `label`; `algo`, `run`).
- `WS /ws`: `{"t", "sims": {"fijo": {vehicles, tls, metrics}, "rl": {...}}, "improvement_pct", "incidents"?}`. `incidents` (opcional) es la lista de aristas cerradas; si no viene, la UI lleva la cuenta local.
- Si `improvement_pct` no llega, se calcula con la espera promedio.

## Build para que el backend lo sirva
```bash
npm run build        # tsc + vite build -> web/frontend/dist/
```
El backend puede montar `web/frontend/dist` como archivos estáticos en `/`. `dist/` y `node_modules/` no se versionan.
