# Frontend de la demo en vivo (React + Vite + TypeScript)

Dos mapas sincronizados ("Semáforo fijo" vs "Agente RL"), KPIs grandes (espera promedio, cola, throughput, mejora %), panel de control y gráficas en vivo (últimos 10 min de tiempo simulado). Tema oscuro pensado para proyector. Sin librerías de UI: los mapas y gráficas se dibujan a mano en `<canvas>`.

## Correr en desarrollo
```bash
# 1) backend (otra terminal, desde la raíz del repo): python -m uvicorn web.backend.app:app --port 8000
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

## Contrato con el backend (ver `web/README.md`)
- `GET /api/network`: formato propio del backend, en coordenadas x/y de SUMO (m): `{bbox, lanes[{id, edge, shape, width}], junctions[{id, shape}], tls[{id, name, x, y, links[[índiceEnElEstado, carril, x, y]]}]}`. Los carriles se dibujan como líneas, las intersecciones como polígonos rellenos y cada semáforo como una barra de color en la línea de alto de cada carril que controla (verde si algún enlace del carril está en verde, si no amarillo, si no rojo). `name` (de `tls_names.json`) se escribe junto a cada cruce.
- `GET /api/scenarios` (`{current, scenarios[{name, description, available}]}`) y `GET /api/policies?scenario=` (`{policies[{algo, run, label, compatible, available}]}`): las políticas no compatibles con el escenario elegido no se ofrecen; el selector se refresca al cambiar de escenario.
- `WS /ws`: mensajes `type: "state"` (`t`, `sims`, `improvement_pct`, `incidents`, `scenario`, `profile`, `speed`, `policy`, `demand_veh_h`); el servidor manda y los controles siguen su escenario, política, hora del día y velocidad. `ack` con `ok:false`, `error` y `loading` salen como avisos (toasts) abajo a la derecha; los `ack` exitosos de inject/incident/time_of_day/reset, como confirmaciones breves.
- Los vehículos se interpolan entre los dos últimos mensajes (animación fluida aunque a 1× llegue ~1 mensaje por segundo).
- Si `improvement_pct` no llega, se calcula con la espera promedio.
- El modo mock produce el mismo formato de red y de mensajes.

## Build para que el backend lo sirva
```bash
npm run build        # tsc + vite build -> web/frontend/dist/
```
El backend puede montar `web/frontend/dist` como archivos estáticos en `/`. `dist/` y `node_modules/` no se versionan.
