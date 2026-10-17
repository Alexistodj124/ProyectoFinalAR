# E3: ablación de DQN: evaluación final

Media ± IC95 (t de Student). Réplica = semilla de entrenamiento (n=5) en los métodos aprendidos y episodio de evaluación (n=10, semillas 1000 a 1009) en las líneas base; se indica en cada fila. **Negrita** = mejor valor de la columna. Demora total = (espera + retraso de inserción de los insertados + tiempo que esperaron afuera los que nunca entraron) / todos los vehículos de la demanda (s por vehículo demandado); espera media = por vehículo insertado; backlog = % de la demanda que no pudo entrar a la red.

## Cruce C12 hora pico (`cruce_pico`)

| Método | Demora total (s/veh demandado) | Espera media (s/veh insertado) | Backlog de inserción (%) | Tiempo de viaje medio (s) | Throughput (veh/h) | Paradas por vehículo | Espera máx. calles transversales (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tiempo fijo (ep.) | 33.64 ± 6.73 | 31.30 ± 5.06 | 0.25 ± 0.18 | 102.43 ± 8.36 | 4737.20 ± 30.00 | 1.35 ± 0.29 | 113.00 ± 12.54 |
| Actuado (ep.) | 38.04 ± 6.40 | 29.04 ± 1.05 | 0.80 ± 0.41 | 98.56 ± 1.69 | 4706.70 ± 35.37 | **1.34 ± 0.11** | **99.90 ± 1.37** |
| Max-pressure (ep.) | **19.77 ± 5.76** | **16.67 ± 1.96** | 0.27 ± 0.28 | **90.88 ± 4.44** | **4741.90 ± 31.26** | 1.49 ± 0.17 | 271.30 ± 42.53 |
| DQN base (sem.) | 22.66 ± 2.90 | 20.94 ± 4.03 | 0.14 ± 0.15 | 108.98 ± 14.93 | 4723.42 ± 40.10 | 1.85 ± 0.47 | 248.42 ± 60.46 |
| DQN + Double (sem.) | 21.73 ± 0.93 | 19.81 ± 1.86 | **0.12 ± 0.11** | 107.73 ± 13.98 | 4725.68 ± 32.05 | 1.83 ± 0.34 | 256.60 ± 60.15 |
| DQN + Double + Dueling (sem.) | 23.08 ± 1.04 | 20.21 ± 2.38 | 0.20 ± 0.22 | 114.69 ± 10.15 | 4711.78 ± 23.84 | 2.05 ± 0.20 | 252.36 ± 97.40 |
| DQN + Double + Dueling + PER (sem.) | 21.07 ± 1.62 | 18.15 ± 2.52 | 0.25 ± 0.29 | 111.10 ± 7.19 | 4708.98 ± 19.05 | 1.97 ± 0.14 | 221.62 ± 64.59 |

## Cruce C12 mediodía (`cruce_mediodia`)

| Método | Demora total (s/veh demandado) | Espera media (s/veh insertado) | Backlog de inserción (%) | Tiempo de viaje medio (s) | Throughput (veh/h) | Paradas por vehículo | Espera máx. calles transversales (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tiempo fijo (ep.) | 16.70 ± 0.26 | 16.19 ± 0.26 | 0.02 ± 0.02 | 76.30 ± 0.29 | 2986.60 ± 46.05 | 0.60 ± 0.01 | **89.80 ± 6.65** |
| Actuado (ep.) | 9.27 ± 0.29 | 8.76 ± 0.29 | **0.02 ± 0.02** | 67.74 ± 0.34 | 2985.80 ± 45.79 | **0.51 ± 0.01** | 92.40 ± 3.71 |
| Max-pressure (ep.) | **8.03 ± 0.25** | **7.53 ± 0.25** | 0.02 ± 0.02 | **67.08 ± 0.41** | **2987.00 ± 46.86** | 0.59 ± 0.01 | 105.90 ± 16.10 |
| DQN base (sem.) | 19.91 ± 17.31 | 19.40 ± 17.32 | 0.02 ± 0.00 | 83.78 ± 22.22 | 2970.66 ± 19.91 | 0.99 ± 0.37 | 170.50 ± 71.87 |
| DQN + Double (sem.) | 19.66 ± 10.09 | 19.15 ± 10.09 | 0.02 ± 0.00 | 84.62 ± 12.58 | 2970.04 ± 9.85 | 1.13 ± 0.31 | 169.96 ± 108.45 |
| DQN + Double + Dueling (sem.) | 20.26 ± 14.40 | 19.75 ± 14.41 | 0.02 ± 0.00 | 85.07 ± 22.69 | 2970.94 ± 17.42 | 1.05 ± 0.67 | 190.40 ± 112.61 |
| DQN + Double + Dueling + PER (sem.) | 13.71 ± 1.14 | 13.20 ± 1.14 | 0.02 ± 0.00 | 74.36 ± 3.26 | 2979.26 ± 3.98 | 0.75 ± 0.26 | 189.76 ± 82.55 |
