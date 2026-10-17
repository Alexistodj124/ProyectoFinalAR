# E4: DQN (mejor variante) contra PPO: evaluación final

Media ± IC95 (t de Student). Réplica = semilla de entrenamiento (n=5) en los métodos aprendidos y episodio de evaluación (n=10, semillas 1000 a 1009) en las líneas base; se indica en cada fila. **Negrita** = mejor valor de la columna. Demora total = (espera + retraso de inserción de los insertados + tiempo que esperaron afuera los que nunca entraron) / todos los vehículos de la demanda (s por vehículo demandado); espera media = por vehículo insertado; backlog = % de la demanda que no pudo entrar a la red.

## Cruce C12 hora pico (`cruce_pico`)

| Método | Demora total (s/veh demandado) | Espera media (s/veh insertado) | Backlog de inserción (%) | Tiempo de viaje medio (s) | Throughput (veh/h) | Paradas por vehículo | Espera máx. calles transversales (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tiempo fijo (ep.) | 33.64 ± 6.73 | 31.30 ± 5.06 | 0.25 ± 0.18 | 102.43 ± 8.36 | 4737.20 ± 30.00 | 1.35 ± 0.29 | 113.00 ± 12.54 |
| Actuado (ep.) | 38.04 ± 6.40 | 29.04 ± 1.05 | 0.80 ± 0.41 | 98.56 ± 1.69 | 4706.70 ± 35.37 | **1.34 ± 0.11** | **99.90 ± 1.37** |
| Max-pressure (ep.) | **19.77 ± 5.76** | 16.67 ± 1.96 | 0.27 ± 0.28 | **90.88 ± 4.44** | **4741.90 ± 31.26** | 1.49 ± 0.17 | 271.30 ± 42.53 |
| DQN mejor (E4) (sem.) | 21.07 ± 1.62 | 18.15 ± 2.52 | **0.25 ± 0.29** | 111.10 ± 7.19 | 4708.98 ± 19.05 | 1.97 ± 0.14 | 221.62 ± 64.59 |
| PPO (sem.) | 23.83 ± 3.58 | **15.79 ± 0.51** | 0.70 ± 0.32 | 114.58 ± 10.27 | 4675.28 ± 26.18 | 2.16 ± 0.15 | 167.80 ± 41.70 |

## Cruce C12 mediodía (`cruce_mediodia`)

| Método | Demora total (s/veh demandado) | Espera media (s/veh insertado) | Backlog de inserción (%) | Tiempo de viaje medio (s) | Throughput (veh/h) | Paradas por vehículo | Espera máx. calles transversales (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tiempo fijo (ep.) | 16.70 ± 0.26 | 16.19 ± 0.26 | 0.02 ± 0.02 | 76.30 ± 0.29 | 2986.60 ± 46.05 | 0.60 ± 0.01 | 89.80 ± 6.65 |
| Actuado (ep.) | 9.27 ± 0.29 | 8.76 ± 0.29 | **0.02 ± 0.02** | 67.74 ± 0.34 | 2985.80 ± 45.79 | **0.51 ± 0.01** | 92.40 ± 3.71 |
| Max-pressure (ep.) | 8.03 ± 0.25 | 7.53 ± 0.25 | 0.02 ± 0.02 | **67.08 ± 0.41** | **2987.00 ± 46.86** | 0.59 ± 0.01 | 105.90 ± 16.10 |
| DQN mejor (E4) (sem.) | 13.71 ± 1.14 | 13.20 ± 1.14 | 0.02 ± 0.00 | 74.36 ± 3.26 | 2979.26 ± 3.98 | 0.75 ± 0.26 | 189.76 ± 82.55 |
| PPO (sem.) | **7.47 ± 2.10** | **6.96 ± 2.10** | 0.02 ± 0.00 | 67.99 ± 3.70 | 2983.88 ± 3.46 | 0.76 ± 0.19 | **71.54 ± 29.07** |
