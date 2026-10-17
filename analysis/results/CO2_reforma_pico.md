# Emisiones de CO₂

CO₂ emitido por todos los vehículos de la hora simulada (modelo de emisiones de SUMO, `co2_kg`). Depende del número de vehículos que circulan y de las paradas y arranques: un método que deja más vehículos afuera emite menos sin servir mejor. Media ± IC95; réplica = semilla de entrenamiento (n=5) o episodio de evaluación (n=10, líneas base).

## Corredor hora pico

| Método | CO₂ (kg) | Cambio frente al tiempo fijo | CO₂ por vehículo que llegó (g) | Paradas por vehículo |
|---|---:|---:|---:|---:|
| Tiempo fijo (ep.) | 2828 ± 142 | - | 418 | 3.20 ± 0.28 |
| Actuado (ep.) | 2507 ± 69 | -11.3 % | 367 | 2.69 ± 0.23 |
| Max-pressure (ep.) | 2557 ± 67 | -9.6 % | 372 | 3.89 ± 0.14 |
| IDQN (sem.) | 2703 ± 101 | -4.4 % | 405 | 4.27 ± 0.51 |
| IDQN + colas de vecinos (sem.) | 2685 ± 216 | -5.1 % | 397 | 4.02 ± 0.82 |
| QMIX (sem.) | 2905 ± 232 | +2.7 % | 433 | 4.32 ± 0.31 |
| MAPPO (sem.) | 2767 ± 132 | -2.2 % | 415 | 4.46 ± 0.28 |
| Comunicación (DIAL) (sem.) | 2590 ± 148 | -8.4 % | 382 | 4.08 ± 0.74 |
| QMIX equitativo (sem.) | 2806 ± 75 | -0.8 % | 414 | 4.15 ± 0.25 |
| Comunicación equitativa (sem.) | 2607 ± 149 | -7.8 % | 384 | 3.92 ± 0.38 |
