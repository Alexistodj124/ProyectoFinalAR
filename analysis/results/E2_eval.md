# E2: Q-Learning y Dyna-Q (cuánto ayuda planificar): evaluación final

Media ± IC95 (t de Student). Réplica = semilla de entrenamiento (n=5) en los métodos aprendidos y episodio de evaluación (n=10, semillas 1000 a 1009) en las líneas base; se indica en cada fila. **Negrita** = mejor valor de la columna. Demora total = (espera + retraso de inserción de los insertados + tiempo que esperaron afuera los que nunca entraron) / todos los vehículos de la demanda (s por vehículo demandado); espera media = por vehículo insertado; backlog = % de la demanda que no pudo entrar a la red.

## Cruce C12 hora pico (`cruce_pico`)

| Método | Demora total (s/veh demandado) | Espera media (s/veh insertado) | Backlog de inserción (%) | Tiempo de viaje medio (s) | Throughput (veh/h) | Paradas por vehículo | Espera máx. calles transversales (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tiempo fijo (ep.) | 33.64 ± 6.73 | 31.30 ± 5.06 | **0.25 ± 0.18** | 102.43 ± 8.36 | 4737.20 ± 30.00 | 1.35 ± 0.29 | 113.00 ± 12.54 |
| Actuado (ep.) | 38.04 ± 6.40 | 29.04 ± 1.05 | 0.80 ± 0.41 | 98.56 ± 1.69 | 4706.70 ± 35.37 | **1.34 ± 0.11** | **99.90 ± 1.37** |
| Max-pressure (ep.) | **19.77 ± 5.76** | **16.67 ± 1.96** | 0.27 ± 0.28 | **90.88 ± 4.44** | **4741.90 ± 31.26** | 1.49 ± 0.17 | 271.30 ± 42.53 |
| Q-Learning (sem.) | 39.04 ± 10.28 | 19.41 ± 4.63 | 1.48 ± 0.80 | 112.22 ± 6.02 | 4645.06 ± 26.25 | 2.19 ± 0.18 | 158.76 ± 68.41 |
| Dyna-Q n=5 (sem.) | 42.95 ± 14.08 | 26.34 ± 10.81 | 1.30 ± 0.57 | 114.73 ± 14.62 | 4655.78 ± 34.17 | 2.14 ± 0.15 | 268.40 ± 201.61 |
| Dyna-Q n=10 (sem.) | 46.80 ± 10.70 | 20.63 ± 7.85 | 1.77 ± 0.94 | 106.23 ± 4.88 | 4647.22 ± 42.83 | 1.98 ± 0.18 | 186.14 ± 122.02 |
| Dyna-Q n=50 (sem.) | 47.26 ± 10.31 | 22.45 ± 9.33 | 2.14 ± 0.95 | 111.26 ± 12.72 | 4620.60 ± 49.94 | 2.01 ± 0.40 | 299.46 ± 312.13 |

## Cruce C12 mediodía (`cruce_mediodia`)

| Método | Demora total (s/veh demandado) | Espera media (s/veh insertado) | Backlog de inserción (%) | Tiempo de viaje medio (s) | Throughput (veh/h) | Paradas por vehículo | Espera máx. calles transversales (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tiempo fijo (ep.) | 16.70 ± 0.26 | 16.19 ± 0.26 | 0.02 ± 0.02 | 76.30 ± 0.29 | 2986.60 ± 46.05 | 0.60 ± 0.01 | **89.80 ± 6.65** |
| Actuado (ep.) | 9.27 ± 0.29 | 8.76 ± 0.29 | **0.02 ± 0.02** | 67.74 ± 0.34 | 2985.80 ± 45.79 | **0.51 ± 0.01** | 92.40 ± 3.71 |
| Max-pressure (ep.) | **8.03 ± 0.25** | **7.53 ± 0.25** | 0.02 ± 0.02 | **67.08 ± 0.41** | **2987.00 ± 46.86** | 0.59 ± 0.01 | 105.90 ± 16.10 |
| Q-Learning (sem.) | 17.35 ± 4.55 | 16.35 ± 5.06 | 0.07 ± 0.14 | 82.64 ± 9.59 | 2968.36 ± 17.05 | 1.07 ± 0.52 | 184.72 ± 107.48 |
| Dyna-Q n=5 (sem.) | 25.38 ± 16.32 | 24.87 ± 16.32 | 0.02 ± 0.00 | 87.70 ± 20.48 | 2965.46 ± 21.08 | 0.92 ± 0.36 | 295.34 ± 129.50 |
| Dyna-Q n=10 (sem.) | 22.56 ± 12.25 | 20.96 ± 13.33 | 0.13 ± 0.19 | 91.07 ± 9.12 | 2957.32 ± 14.83 | 1.28 ± 0.57 | 233.68 ± 185.31 |
| Dyna-Q n=50 (sem.) | 17.69 ± 6.64 | 16.20 ± 7.11 | 0.12 ± 0.25 | 83.68 ± 10.67 | 2966.04 ± 20.57 | 1.11 ± 0.57 | 198.04 ± 119.63 |
