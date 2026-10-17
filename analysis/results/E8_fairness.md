# E8: equidad

Media ± IC95. p95 = percentil 95 de la espera de los vehículos de cada aproximación (s). Espera máx. en transversales = mayor espera de un vehículo en una calle que no es Reforma. Réplica: semilla de entrenamiento (n=5) o episodio de evaluación (n=10, líneas base).

## Corredor hora pico (`reforma_pico`)

| Método | p95 Reforma ↑ (entra por C15) (s) | p95 Reforma ↓ (entra por C06) (s) | p95 Transv. 6ª (oeste) (s) | p95 Transv. 10ª (este) (s) | p95 Transv. 12ª (oeste) (s) | p95 Transv. 14ª (oeste) (s) | p95 Transv. 15ª (este) (s) | Espera máx. calles transversales (s) | Demora total (s/veh demandado) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Tiempo fijo (ep.) | 163 ± 32 | 189 ± 22 | 127 ± 11 | 231 ± 47 | 134 ± 17 | 147 ± 22 | 222 ± 60 | 524 ± 176 | 79.1 ± 8.5 |
| Actuado (ep.) | 139 ± 12 | 215 ± 43 | 98 ± 1 | 112 ± 7 | 100 ± 2 | 113 ± 6 | 141 ± 7 | 832 ± 375 | 63.4 ± 6.1 |
| Max-pressure (ep.) | 80 ± 5 | 98 ± 13 | 101 ± 8 | 104 ± 9 | 221 ± 43 | 119 ± 9 | 88 ± 11 | 420 ± 164 | 41.7 ± 2.5 |
| IDQN (sem.) | 89 ± 21 | 96 ± 23 | 91 ± 45 | 90 ± 54 | 152 ± 68 | 119 ± 36 | 137 ± 106 | 301 ± 75 | 64.1 ± 38.1 |
| IDQN + colas de vecinos (sem.) | 101 ± 36 | 121 ± 29 | 95 ± 45 | 81 ± 22 | 240 ± 114 | 163 ± 42 | 105 ± 45 | 443 ± 87 | 51.9 ± 6.8 |
| QMIX (sem.) | 97 ± 35 | 134 ± 118 | 121 ± 22 | 120 ± 61 | 230 ± 93 | 157 ± 83 | 115 ± 82 | 453 ± 235 | 55.0 ± 20.5 |
| MAPPO (sem.) | 95 ± 10 | 104 ± 26 | 72 ± 16 | 38 ± 5 | 125 ± 47 | 96 ± 13 | 112 ± 39 | 314 ± 61 | 46.8 ± 7.3 |
| Comunicación (DIAL) (sem.) | 91 ± 38 | 112 ± 29 | 80 ± 20 | 89 ± 58 | 150 ± 50 | 110 ± 51 | 95 ± 33 | 374 ± 128 | 46.2 ± 14.9 |
| QMIX equitativo (sem.) | 87 ± 18 | 98 ± 23 | 109 ± 72 | 76 ± 26 | 187 ± 51 | 185 ± 87 | 80 ± 22 | 368 ± 103 | 46.5 ± 11.7 |
| Comunicación equitativa (sem.) | 89 ± 19 | 117 ± 25 | 103 ± 78 | 106 ± 54 | 163 ± 44 | 118 ± 77 | 339 ± 641 | 647 ± 580 | 50.6 ± 21.4 |

## Cruce C12 hora pico (`cruce_pico`)

| Método | p95 Reforma ↑ (C14→C12) (s) | p95 Reforma ↓ (C10→C12) (s) | p95 Transv. 12ª (oeste) (s) | Espera máx. calles transversales (s) | Demora total (s/veh demandado) |
|---|---:|---:|---:|---:|---:|
| Tiempo fijo (ep.) | 69 ± 11 | 169 ± 43 | 80 ± 1 | 113 ± 13 | 33.6 ± 6.7 |
| Actuado (ep.) | 52 ± 1 | 279 ± 28 | 91 ± 1 | 100 ± 1 | 38.0 ± 6.4 |
| Max-pressure (ep.) | 23 ± 1 | 86 ± 19 | 179 ± 36 | 271 ± 43 | 19.8 ± 5.8 |
| Q-Learning (sem.) | 29 ± 14 | 144 ± 13 | 98 ± 53 | 159 ± 68 | 39.0 ± 10.3 |
| Dyna-Q n=5 (sem.) | 39 ± 22 | 143 ± 69 | 194 ± 165 | 268 ± 202 | 43.0 ± 14.1 |
| Dyna-Q n=10 (sem.) | 30 ± 13 | 163 ± 74 | 118 ± 92 | 186 ± 122 | 46.8 ± 10.7 |
| Dyna-Q n=50 (sem.) | 41 ± 28 | 127 ± 75 | 216 ± 286 | 299 ± 312 | 47.3 ± 10.3 |
| DQN base (sem.) | 37 ± 15 | 73 ± 21 | 155 ± 41 | 248 ± 60 | 22.7 ± 2.9 |
| DQN + Double (sem.) | 34 ± 8 | 68 ± 8 | 167 ± 37 | 257 ± 60 | 21.7 ± 0.9 |
| DQN + Double + Dueling (sem.) | 31 ± 9 | 81 ± 27 | 158 ± 70 | 252 ± 97 | 23.1 ± 1.0 |
| DQN + Double + Dueling + PER (sem.) | 31 ± 13 | 73 ± 11 | 144 ± 47 | 222 ± 65 | 21.1 ± 1.6 |
| DQN mejor (E4) (sem.) | 31 ± 13 | 73 ± 11 | 144 ± 47 | 222 ± 65 | 21.1 ± 1.6 |
| PPO (sem.) | 22 ± 1 | 93 ± 24 | 98 ± 30 | 168 ± 42 | 23.8 ± 3.6 |
