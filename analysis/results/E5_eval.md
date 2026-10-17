# E5: IDQN, QMIX y MAPPO en el corredor: evaluación final

Media ± IC95 (t de Student). Réplica = semilla de entrenamiento (n=5) en los métodos aprendidos y episodio de evaluación (n=10, semillas 1000 a 1009) en las líneas base; se indica en cada fila. **Negrita** = mejor valor de la columna. Demora total = (espera + retraso de inserción de los insertados + tiempo que esperaron afuera los que nunca entraron) / todos los vehículos de la demanda (s por vehículo demandado); espera media = por vehículo insertado; backlog = % de la demanda que no pudo entrar a la red.

## Corredor hora pico (`reforma_pico`)

| Método | Demora total (s/veh demandado) | Espera media (s/veh insertado) | Backlog de inserción (%) | Tiempo de viaje medio (s) | Throughput (veh/h) | Paradas por vehículo | Espera máx. calles transversales (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tiempo fijo (ep.) | 79.07 ± 8.50 | 77.09 ± 7.71 | 0.18 ± 0.14 | 228.52 ± 11.39 | 6764.20 ± 21.07 | 3.20 ± 0.28 | 523.60 ± 175.67 |
| Actuado (ep.) | 63.44 ± 6.11 | 57.89 ± 4.65 | 0.37 ± 0.36 | **200.33 ± 6.04** | 6831.40 ± 65.12 | **2.69 ± 0.23** | 832.20 ± 375.10 |
| Max-pressure (ep.) | **41.69 ± 2.53** | 40.10 ± 1.98 | **0.12 ± 0.06** | 203.00 ± 4.65 | **6864.40 ± 32.66** | 3.89 ± 0.14 | 419.50 ± 164.13 |
| IDQN (sem.) | 64.12 ± 38.08 | 39.84 ± 6.19 | 1.99 ± 2.49 | 225.60 ± 11.90 | 6671.94 ± 162.27 | 4.27 ± 0.51 | **300.80 ± 74.69** |
| QMIX (sem.) | 55.04 ± 20.52 | 48.30 ± 13.02 | 0.69 ± 1.09 | 242.68 ± 25.16 | 6709.76 ± 141.24 | 4.32 ± 0.31 | 452.66 ± 235.07 |
| MAPPO (sem.) | 46.77 ± 7.33 | **35.74 ± 0.85** | 1.29 ± 0.70 | 231.18 ± 16.82 | 6671.88 ± 93.20 | 4.46 ± 0.28 | 313.64 ± 61.48 |

## Corredor mediodía (`reforma_mediodia`)

| Método | Demora total (s/veh demandado) | Espera media (s/veh insertado) | Backlog de inserción (%) | Tiempo de viaje medio (s) | Throughput (veh/h) | Paradas por vehículo | Espera máx. calles transversales (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tiempo fijo (ep.) | 30.40 ± 0.35 | 29.86 ± 0.34 | **0.04 ± 0.02** | 143.22 ± 0.67 | 4593.30 ± 58.57 | **1.12 ± 0.01** | 160.90 ± 10.48 |
| Actuado (ep.) | **18.73 ± 0.53** | **18.18 ± 0.53** | 0.04 ± 0.02 | **131.94 ± 0.72** | **4598.90 ± 59.06** | 1.24 ± 0.03 | **124.30 ± 9.24** |
| Max-pressure (ep.) | 21.08 ± 0.29 | 20.53 ± 0.29 | 0.04 ± 0.02 | 138.00 ± 0.63 | 4597.60 ± 58.20 | 1.71 ± 0.03 | 158.10 ± 14.63 |
| IDQN (sem.) | 26.87 ± 10.39 | 26.32 ± 10.39 | 0.04 ± 0.00 | 149.02 ± 12.41 | 4576.84 ± 17.12 | 2.19 ± 0.34 | 191.62 ± 118.73 |
| QMIX (sem.) | 40.68 ± 20.27 | 39.34 ± 19.50 | 0.11 ± 0.21 | 169.62 ± 32.02 | 4546.24 ± 47.51 | 2.81 ± 0.95 | 310.88 ± 114.58 |
| MAPPO (sem.) | 19.02 ± 2.25 | 18.47 ± 2.26 | 0.04 ± 0.00 | 139.31 ± 7.09 | 4587.64 ± 11.03 | 2.08 ± 0.43 | 172.06 ± 36.47 |

## Corredor pico +30 % (`reforma_pico_x13`)

| Método | Demora total (s/veh demandado) | Espera media (s/veh insertado) | Backlog de inserción (%) | Tiempo de viaje medio (s) | Throughput (veh/h) | Paradas por vehículo | Espera máx. calles transversales (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tiempo fijo (ep.) | 345.72 ± 9.66 | 123.13 ± 3.54 | 15.71 ± 0.58 | 301.29 ± 4.72 | 7275.50 ± 38.57 | 4.97 ± 0.09 | 666.20 ± 112.99 |
| Actuado (ep.) | 320.37 ± 11.92 | 79.40 ± 3.77 | 15.18 ± 0.88 | **228.88 ± 5.01** | 7542.80 ± 65.62 | **3.16 ± 0.11** | 422.00 ± 77.05 |
| Max-pressure (ep.) | **252.22 ± 11.54** | 60.15 ± 5.31 | **12.69 ± 0.77** | 259.80 ± 6.83 | **7654.50 ± 67.56** | 5.58 ± 0.26 | 1048.70 ± 409.30 |
| IDQN (sem.) | 298.52 ± 38.42 | **54.49 ± 16.22** | 15.91 ± 1.87 | 270.55 ± 31.08 | 7352.68 ± 205.23 | 5.48 ± 0.70 | **407.78 ± 176.68** |
| QMIX (sem.) | 292.57 ± 33.47 | 66.74 ± 20.35 | 15.50 ± 1.99 | 302.50 ± 40.56 | 7286.34 ± 267.09 | 5.82 ± 0.83 | 1019.98 ± 485.68 |
| MAPPO (sem.) | 347.66 ± 28.00 | 63.67 ± 17.96 | 21.50 ± 2.71 | 348.50 ± 36.54 | 6585.60 ± 347.34 | 7.52 ± 1.24 | 694.02 ± 204.49 |
