# E7: generalización

Media ± IC95 sobre los 10 episodios de evaluación (semillas 1000 a 1009). Los agentes aprendidos son UNA sola semilla de entrenamiento elegida por validación (`marl_best` = MAPPO, semilla 3; `comm_best`, semilla 0; PPO, semilla 0; DQN, semilla 1): el IC no incluye la variabilidad entre semillas de entrenamiento. Las líneas base son deterministas por semilla de evaluación. **Negrita** = mejor de la columna.

## Cruce C12: Demora total (s/veh demandado)

| Método | Pico (entrenamiento) | Mediodía (hora no vista) | Pico +30 % (más demanda) | Pico + incidente | × Mediodía (hora no vista) / pico | × Pico +30 % (más demanda) / pico | × Pico + incidente / pico | Δ% vs fijo, Pico (entrenamiento) | Δ% vs fijo, Mediodía (hora no vista) | Δ% vs fijo, Pico +30 % (más demanda) | Δ% vs fijo, Pico + incidente |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Tiempo fijo (10 ep.) | 33.6 ± 6.7 | 16.7 ± 0.3 | 223.4 ± 13.8 | 445.9 ± 15.0 | ×0.50 | ×6.64 | ×13.25 | - | - | - | - |
| Actuado (10 ep.) | 38.0 ± 6.4 | 9.3 ± 0.3 | 200.7 ± 16.0 | **419.5 ± 12.2** | ×0.24 | ×5.28 | ×11.03 | +13.1 % | -44.5 % | -10.2 % | -5.9 % |
| Max-pressure (10 ep.) | 19.8 ± 5.8 | 8.0 ± 0.3 | **99.7 ± 8.0** | 423.2 ± 13.7 | ×0.41 | ×5.05 | ×21.41 | -41.2 % | -51.9 % | -55.4 % | -5.1 % |
| DQN (semilla elegida) (10 ep.) | **19.4 ± 5.6** | 12.3 ± 0.6 | 147.1 ± 18.7 | 462.3 ± 8.6 | ×0.63 | ×7.60 | ×23.88 | -42.5 % | -26.6 % | -34.2 % | +3.7 % |
| PPO (semilla elegida) (10 ep.) | 20.8 ± 7.0 | **7.2 ± 0.2** | 148.4 ± 16.3 | 440.4 ± 10.1 | ×0.34 | ×7.13 | ×21.15 | -38.1 % | -57.1 % | -33.6 % | -1.2 % |

## Cruce C12: Espera media (s/veh insertado)

| Método | Pico (entrenamiento) | Mediodía (hora no vista) | Pico +30 % (más demanda) | Pico + incidente |
|---|---:|---:|---:|---:|
| Tiempo fijo (10 ep.) | 31.3 ± 5.1 | 16.2 ± 0.3 | 50.8 ± 2.7 | 95.6 ± 2.0 |
| Actuado (10 ep.) | 29.0 ± 1.0 | 8.8 ± 0.3 | 51.1 ± 1.4 | 92.3 ± 2.4 |
| Max-pressure (10 ep.) | 16.7 ± 2.0 | 7.5 ± 0.3 | 23.5 ± 0.7 | **81.7 ± 1.9** |
| DQN (semilla elegida) (10 ep.) | 16.6 ± 1.7 | 11.8 ± 0.6 | 22.9 ± 1.1 | 87.9 ± 0.9 |
| PPO (semilla elegida) (10 ep.) | **16.0 ± 1.7** | **6.7 ± 0.2** | **19.5 ± 0.5** | 83.3 ± 1.1 |

## Cruce C12: Backlog de inserción (%)

| Método | Pico (entrenamiento) | Mediodía (hora no vista) | Pico +30 % (más demanda) | Pico + incidente |
|---|---:|---:|---:|---:|
| Tiempo fijo (10 ep.) | 0.3 ± 0.2 | 0.0 ± 0.0 | 11.1 ± 0.7 | 25.0 ± 0.7 |
| Actuado (10 ep.) | 0.8 ± 0.4 | 0.0 ± 0.0 | 9.7 ± 0.8 | **23.7 ± 0.5** |
| Max-pressure (10 ep.) | 0.3 ± 0.3 | 0.0 ± 0.0 | **5.0 ± 0.4** | 24.1 ± 0.8 |
| DQN (semilla elegida) (10 ep.) | **0.2 ± 0.3** | 0.0 ± 0.0 | 8.4 ± 0.9 | 25.1 ± 0.6 |
| PPO (semilla elegida) (10 ep.) | 0.4 ± 0.4 | **0.0 ± 0.0** | 8.8 ± 0.8 | 24.4 ± 0.4 |

## Corredor Reforma: Demora total (s/veh demandado)

| Método | Pico (entrenamiento) | Mediodía (hora no vista) | Pico +30 % (más demanda) | Pico + incidente | × Mediodía (hora no vista) / pico | × Pico +30 % (más demanda) / pico | × Pico + incidente / pico | Δ% vs fijo, Pico (entrenamiento) | Δ% vs fijo, Mediodía (hora no vista) | Δ% vs fijo, Pico +30 % (más demanda) | Δ% vs fijo, Pico + incidente |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Tiempo fijo (10 ep.) | 79.1 ± 8.5 | 30.4 ± 0.3 | 345.7 ± 9.7 | 198.4 ± 9.8 | ×0.38 | ×4.37 | ×2.51 | - | - | - | - |
| Actuado (10 ep.) | 63.4 ± 6.1 | 18.7 ± 0.5 | 320.4 ± 11.9 | 180.5 ± 6.3 | ×0.30 | ×5.05 | ×2.85 | -19.8 % | -38.4 % | -7.3 % | -9.0 % |
| Max-pressure (10 ep.) | 41.7 ± 2.5 | 21.1 ± 0.3 | **252.2 ± 11.5** | **161.8 ± 7.2** | ×0.51 | ×6.05 | ×3.88 | -47.3 % | -30.7 % | -27.0 % | -18.5 % |
| MAPPO (semilla elegida) (10 ep.) | 36.8 ± 3.3 | **17.2 ± 0.4** | 373.3 ± 36.9 | 165.5 ± 8.9 | ×0.47 | ×10.13 | ×4.49 | -53.4 % | -43.5 % | +8.0 % | -16.6 % |
| Comunicación (semilla elegida) (10 ep.) | **36.8 ± 3.4** | 20.7 ± 0.4 | 281.8 ± 13.9 | 175.2 ± 8.7 | ×0.56 | ×7.65 | ×4.76 | -53.4 % | -32.0 % | -18.5 % | -11.7 % |

## Corredor Reforma: Espera media (s/veh insertado)

| Método | Pico (entrenamiento) | Mediodía (hora no vista) | Pico +30 % (más demanda) | Pico + incidente |
|---|---:|---:|---:|---:|
| Tiempo fijo (10 ep.) | 77.1 ± 7.7 | 29.9 ± 0.3 | 123.1 ± 3.5 | 87.5 ± 5.1 |
| Actuado (10 ep.) | 57.9 ± 4.7 | 18.2 ± 0.5 | 79.4 ± 3.8 | 68.7 ± 5.5 |
| Max-pressure (10 ep.) | 40.1 ± 2.0 | 20.5 ± 0.3 | 60.2 ± 5.3 | 61.0 ± 4.5 |
| MAPPO (semilla elegida) (10 ep.) | **34.9 ± 2.3** | **16.6 ± 0.4** | 86.4 ± 12.0 | **42.1 ± 2.4** |
| Comunicación (semilla elegida) (10 ep.) | 35.2 ± 2.7 | 20.1 ± 0.4 | **54.8 ± 3.1** | 44.7 ± 2.1 |

## Corredor Reforma: Backlog de inserción (%)

| Método | Pico (entrenamiento) | Mediodía (hora no vista) | Pico +30 % (más demanda) | Pico + incidente |
|---|---:|---:|---:|---:|
| Tiempo fijo (10 ep.) | 0.2 ± 0.1 | 0.0 ± 0.0 | 15.7 ± 0.6 | 5.4 ± 0.5 |
| Actuado (10 ep.) | 0.4 ± 0.4 | 0.0 ± 0.0 | 15.2 ± 0.9 | 5.3 ± 0.4 |
| Max-pressure (10 ep.) | **0.1 ± 0.1** | 0.0 ± 0.0 | **12.7 ± 0.8** | **4.6 ± 0.4** |
| MAPPO (semilla elegida) (10 ep.) | 0.3 ± 0.3 | **0.0 ± 0.0** | 24.2 ± 2.9 | 5.9 ± 0.6 |
| Comunicación (semilla elegida) (10 ep.) | 0.2 ± 0.1 | 0.0 ± 0.0 | 15.3 ± 0.7 | 6.1 ± 0.4 |
