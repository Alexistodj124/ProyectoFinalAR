# Comparaciones estadísticas de los pares clave

Prueba t de Welch (dos colas) sobre las réplicas: semilla de entrenamiento (media de sus 10 episodios de evaluación, n=5) en los métodos aprendidos y episodio de evaluación (n=10, semillas 1000 a 1009) en las líneas base. A − B < 0 favorece a A (menor demora o menor espera). `p (Holm)` corrige por el número de comparaciones de TODA la tabla de este archivo (no por escenario). Con n=5 el poder es bajo: «sin diferencia detectable» no prueba que sean iguales. «IC95 se solapan» compara los intervalos de cada media. Las comparaciones entre pares de métodos aprendidos usan n=5 contra n=5.

## reforma_pico: Demora total (s/veh demandado)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| MAPPO contra tiempo fijo | 46.8 | 79.1 | -32.3 [-42.2, -22.4] | -40.9 % | 5 / 10 | <0.001 | <0.001 | no | favorece a MAPPO (p Holm < 0.05) |
| MAPPO contra actuado | 46.8 | 63.4 | -16.7 [-25.0, -8.4] | -26.3 % | 5 / 10 | <0.001 | 0.043 | no | favorece a MAPPO (p Holm < 0.05) |
| MAPPO contra max-pressure | 46.8 | 41.7 | +5.1 [-2.1, +12.3] | +12.2 % | 5 / 10 | 0.131 | 1.000 | sí | sin diferencia detectable |
| comunicación contra MAPPO | 46.2 | 46.8 | -0.5 [-15.3, +14.2] | -1.1 % | 5 / 5 | 0.933 | 1.000 | sí | sin diferencia detectable |
| comunicación contra IDQN | 46.2 | 64.1 | -17.9 [-55.3, +19.6] | -27.9 % | 5 / 5 | 0.277 | 1.000 | sí | sin diferencia detectable |
| colas de vecinos contra IDQN | 51.9 | 64.1 | -12.2 [-50.0, +25.6] | -19.1 % | 5 / 5 | 0.427 | 1.000 | sí | sin diferencia detectable |
| QMIX contra MAPPO | 55.0 | 46.8 | +8.3 [-11.9, +28.4] | +17.7 % | 5 / 5 | 0.340 | 1.000 | sí | sin diferencia detectable |
| IDQN contra MAPPO | 64.1 | 46.8 | +17.3 [-20.4, +55.1] | +37.1 % | 5 / 5 | 0.278 | 1.000 | sí | sin diferencia detectable |
| QMIX contra max-pressure | 55.0 | 41.7 | +13.3 [-7.1, +33.7] | +32.0 % | 5 / 10 | 0.146 | 1.000 | sí | sin diferencia detectable |
| comunicación contra max-pressure | 46.2 | 41.7 | +4.6 [-10.2, +19.3] | +10.9 % | 5 / 10 | 0.449 | 1.000 | sí | sin diferencia detectable |
| QMIX equitativo contra QMIX | 46.5 | 55.0 | -8.5 [-29.1, +12.0] | -15.5 % | 5 / 5 | 0.352 | 1.000 | sí | sin diferencia detectable |
| comunicación equitativa contra comunicación | 50.6 | 46.2 | +4.4 [-17.8, +26.5] | +9.4 % | 5 / 5 | 0.657 | 1.000 | sí | sin diferencia detectable |

## reforma_pico: Espera máx. calles transversales (s)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| MAPPO contra tiempo fijo | 313.6 | 523.6 | -210.0 [-389.0, -30.9] | -40.1 % | 5 / 10 | 0.026 | 0.902 | sí | favorece a MAPPO, solo sin corregir (p < 0.05) |
| MAPPO contra actuado | 313.6 | 832.2 | -518.6 [-895.0, -142.1] | -62.3 % | 5 / 10 | 0.012 | 0.452 | no | favorece a MAPPO, solo sin corregir (p < 0.05) |
| MAPPO contra max-pressure | 313.6 | 419.5 | -105.9 [-273.7, +62.0] | -25.2 % | 5 / 10 | 0.192 | 1.000 | sí | sin diferencia detectable |
| comunicación contra MAPPO | 374.1 | 313.6 | +60.5 [-66.2, +187.2] | +19.3 % | 5 / 5 | 0.284 | 1.000 | sí | sin diferencia detectable |
| comunicación contra IDQN | 374.1 | 300.8 | +73.3 [-55.3, +202.0] | +24.4 % | 5 / 5 | 0.216 | 1.000 | sí | sin diferencia detectable |
| colas de vecinos contra IDQN | 442.6 | 300.8 | +141.8 [+46.3, +237.3] | +47.1 % | 5 / 5 | 0.009 | 0.357 | sí | favorece a IDQN, solo sin corregir (p < 0.05) |
| QMIX contra MAPPO | 452.7 | 313.6 | +139.0 [-92.9, +370.9] | +44.3 % | 5 / 5 | 0.179 | 1.000 | sí | sin diferencia detectable |
| IDQN contra MAPPO | 300.8 | 313.6 | -12.8 [-93.7, +68.0] | -4.1 % | 5 / 5 | 0.722 | 1.000 | sí | sin diferencia detectable |
| QMIX contra max-pressure | 452.7 | 419.5 | +33.2 [-216.3, +282.6] | +7.9 % | 5 / 10 | 0.772 | 1.000 | sí | sin diferencia detectable |
| comunicación contra max-pressure | 374.1 | 419.5 | -45.4 [-231.2, +140.5] | -10.8 % | 5 / 10 | 0.607 | 1.000 | sí | sin diferencia detectable |
| QMIX equitativo contra QMIX | 367.8 | 452.7 | -84.8 [-316.3, +146.6] | -18.7 % | 5 / 5 | 0.397 | 1.000 | sí | sin diferencia detectable |
| comunicación equitativa contra comunicación | 647.0 | 374.1 | +272.9 [-301.0, +846.7] | +72.9 % | 5 / 5 | 0.266 | 1.000 | sí | sin diferencia detectable |

## cruce_pico: Demora total (s/veh demandado)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| DQN contra tiempo fijo | 21.1 | 33.6 | -12.6 [-19.4, -5.8] | -37.4 % | 5 / 10 | 0.002 | 0.090 | no | favorece a DQN mejor (E4), solo sin corregir (p < 0.05) |
| DQN contra actuado | 21.1 | 38.0 | -17.0 [-23.4, -10.5] | -44.6 % | 5 / 10 | <0.001 | 0.008 | no | favorece a DQN mejor (E4) (p Holm < 0.05) |
| DQN contra max-pressure | 21.1 | 19.8 | +1.3 [-4.5, +7.1] | +6.6 % | 5 / 10 | 0.629 | 1.000 | sí | sin diferencia detectable |
| PPO contra tiempo fijo | 23.8 | 33.6 | -9.8 [-16.9, -2.7] | -29.2 % | 5 / 10 | 0.011 | 0.408 | sí | favorece a PPO, solo sin corregir (p < 0.05) |
| PPO contra max-pressure | 23.8 | 19.8 | +4.1 [-2.1, +10.3] | +20.5 % | 5 / 10 | 0.179 | 1.000 | sí | sin diferencia detectable |
| PPO contra DQN | 23.8 | 21.1 | +2.8 [-0.8, +6.3] | +13.1 % | 5 / 5 | 0.103 | 1.000 | sí | sin diferencia detectable |
| DQN completo contra DQN base | 21.1 | 22.7 | -1.6 [-4.5, +1.3] | -7.0 % | 5 / 5 | 0.230 | 1.000 | sí | sin diferencia detectable |
| Dyna-Q n=50 contra Q-Learning | 47.3 | 39.0 | +8.2 [-3.9, +20.3] | +21.1 % | 5 / 5 | 0.156 | 1.000 | sí | sin diferencia detectable |
| Q-Learning contra tiempo fijo | 39.0 | 33.6 | +5.4 [-5.3, +16.1] | +16.1 % | 5 / 10 | 0.285 | 1.000 | sí | sin diferencia detectable |
| DQN contra Dyna-Q n=50 | 21.1 | 47.3 | -26.2 [-36.4, -15.9] | -55.4 % | 5 / 5 | 0.002 | 0.080 | no | favorece a DQN mejor (E4), solo sin corregir (p < 0.05) |

## cruce_pico: Espera máx. calles transversales (s)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| DQN contra tiempo fijo | 221.6 | 113.0 | +108.6 [+44.8, +172.4] | +96.1 % | 5 / 10 | 0.008 | 0.324 | no | favorece a Tiempo fijo, solo sin corregir (p < 0.05) |
| DQN contra actuado | 221.6 | 99.9 | +121.7 [+57.1, +186.3] | +121.8 % | 5 / 10 | 0.006 | 0.261 | no | favorece a Actuado, solo sin corregir (p < 0.05) |
| DQN contra max-pressure | 221.6 | 271.3 | -49.7 [-117.1, +17.8] | -18.3 % | 5 / 10 | 0.130 | 1.000 | sí | sin diferencia detectable |
| PPO contra tiempo fijo | 167.8 | 113.0 | +54.8 [+13.9, +95.7] | +48.5 % | 5 / 10 | 0.018 | 0.651 | no | favorece a Tiempo fijo, solo sin corregir (p < 0.05) |
| PPO contra max-pressure | 167.8 | 271.3 | -103.5 [-155.6, -51.4] | -38.1 % | 5 / 10 | <0.001 | 0.042 | no | favorece a PPO (p Holm < 0.05) |
| PPO contra DQN | 167.8 | 221.6 | -53.8 [-119.6, +12.0] | -24.3 % | 5 / 5 | 0.094 | 1.000 | sí | sin diferencia detectable |
| DQN completo contra DQN base | 221.6 | 248.4 | -26.8 [-100.3, +46.7] | -10.8 % | 5 / 5 | 0.425 | 1.000 | sí | sin diferencia detectable |
| Dyna-Q n=50 contra Q-Learning | 299.5 | 158.8 | +140.7 [-168.1, +449.5] | +88.6 % | 5 / 5 | 0.283 | 1.000 | sí | sin diferencia detectable |
| Q-Learning contra tiempo fijo | 158.8 | 113.0 | +45.8 [-21.9, +113.4] | +40.5 % | 5 / 10 | 0.138 | 1.000 | sí | sin diferencia detectable |
| DQN contra Dyna-Q n=50 | 221.6 | 299.5 | -77.8 [-386.9, +231.2] | -26.0 % | 5 / 5 | 0.532 | 1.000 | sí | sin diferencia detectable |

## reforma_pico_x13: Demora total (s/veh demandado)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| MAPPO contra max-pressure con +30 % de demanda | 347.7 | 252.2 | +95.4 [+67.9, +123.0] | +37.8 % | 5 / 10 | <0.001 | 0.006 | no | favorece a Max-pressure (p Holm < 0.05) |
| MAPPO contra tiempo fijo con +30 % de demanda | 347.7 | 345.7 | +1.9 [-25.5, +29.4] | +0.6 % | 5 / 10 | 0.866 | 1.000 | sí | sin diferencia detectable |

## reforma_pico_x13: Espera máx. calles transversales (s)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| MAPPO contra max-pressure con +30 % de demanda | 694.0 | 1048.7 | -354.7 [-782.3, +72.9] | -33.8 % | 5 / 10 | 0.096 | 1.000 | sí | sin diferencia detectable |
| MAPPO contra tiempo fijo con +30 % de demanda | 694.0 | 666.2 | +27.8 [-178.3, +234.0] | +4.2 % | 5 / 10 | 0.763 | 1.000 | sí | sin diferencia detectable |


# E7: agente aprendido contra líneas base fuera de la hora de entrenamiento

Réplicas = 10 episodios de evaluación de UNA sola semilla de entrenamiento elegida por validación (la varianza entre semillas de entrenamiento no está incluida: las diferencias significativas aquí valen para esa semilla). Holm por las comparaciones de esta tabla.

## cruce_pico [pico]: Demora total (s/veh demandado)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| DQN (semilla elegida) contra tiempo fijo, pico | 19.4 | 33.6 | -14.3 [-22.5, -6.1] | -42.5 % | 10 / 10 | 0.002 | 0.023 | - | favorece a DQN (semilla elegida) (p Holm < 0.05) |
| DQN (semilla elegida) contra max-pressure, pico | 19.4 | 19.8 | -0.4 [-7.9, +7.1] | -2.1 % | 10 / 10 | 0.910 | 1.000 | - | sin diferencia detectable |
| PPO (semilla elegida) contra tiempo fijo, pico | 20.8 | 33.6 | -12.8 [-21.9, -3.8] | -38.1 % | 10 / 10 | 0.008 | 0.095 | - | favorece a PPO (semilla elegida), solo sin corregir (p < 0.05) |
| PPO (semilla elegida) contra max-pressure, pico | 20.8 | 19.8 | +1.1 [-7.4, +9.5] | +5.3 % | 10 / 10 | 0.796 | 1.000 | - | sin diferencia detectable |

## cruce_mediodia [mediodia]: Demora total (s/veh demandado)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| DQN (semilla elegida) contra tiempo fijo, mediodia | 12.3 | 16.7 | -4.4 [-5.0, -3.8] | -26.6 % | 10 / 10 | <0.001 | <0.001 | - | favorece a DQN (semilla elegida) (p Holm < 0.05) |
| DQN (semilla elegida) contra max-pressure, mediodia | 12.3 | 8.0 | +4.2 [+3.6, +4.8] | +52.6 % | 10 / 10 | <0.001 | <0.001 | - | favorece a Max-pressure (p Holm < 0.05) |
| PPO (semilla elegida) contra tiempo fijo, mediodia | 7.2 | 16.7 | -9.5 [-9.9, -9.2] | -57.1 % | 10 / 10 | <0.001 | <0.001 | - | favorece a PPO (semilla elegida) (p Holm < 0.05) |
| PPO (semilla elegida) contra max-pressure, mediodia | 7.2 | 8.0 | -0.9 [-1.2, -0.5] | -10.9 % | 10 / 10 | <0.001 | <0.001 | - | favorece a PPO (semilla elegida) (p Holm < 0.05) |

## cruce_pico_x13 [pico_x13]: Demora total (s/veh demandado)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| DQN (semilla elegida) contra tiempo fijo, pico_x13 | 147.1 | 223.4 | -76.3 [-98.0, -54.6] | -34.2 % | 10 / 10 | <0.001 | <0.001 | - | favorece a DQN (semilla elegida) (p Holm < 0.05) |
| DQN (semilla elegida) contra max-pressure, pico_x13 | 147.1 | 99.7 | +47.4 [+27.8, +66.9] | +47.5 % | 10 / 10 | <0.001 | 0.003 | - | favorece a Max-pressure (p Holm < 0.05) |
| PPO (semilla elegida) contra tiempo fijo, pico_x13 | 148.4 | 223.4 | -75.0 [-94.8, -55.1] | -33.6 % | 10 / 10 | <0.001 | <0.001 | - | favorece a PPO (semilla elegida) (p Holm < 0.05) |
| PPO (semilla elegida) contra max-pressure, pico_x13 | 148.4 | 99.7 | +48.7 [+31.3, +66.0] | +48.8 % | 10 / 10 | <0.001 | <0.001 | - | favorece a Max-pressure (p Holm < 0.05) |

## cruce_pico [pico_incident]: Demora total (s/veh demandado)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| DQN (semilla elegida) contra tiempo fijo, pico_incident | 462.3 | 445.9 | +16.4 [+0.0, +32.8] | +3.7 % | 10 / 10 | 0.049 | 0.346 | - | favorece a Tiempo fijo, solo sin corregir (p < 0.05) |
| DQN (semilla elegida) contra max-pressure, pico_incident | 462.3 | 423.2 | +39.1 [+23.9, +54.3] | +9.2 % | 10 / 10 | <0.001 | 0.001 | - | favorece a Max-pressure (p Holm < 0.05) |
| PPO (semilla elegida) contra tiempo fijo, pico_incident | 440.4 | 445.9 | -5.4 [-22.4, +11.6] | -1.2 % | 10 / 10 | 0.507 | 1.000 | - | sin diferencia detectable |
| PPO (semilla elegida) contra max-pressure, pico_incident | 440.4 | 423.2 | +17.2 [+1.3, +33.1] | +4.1 % | 10 / 10 | 0.035 | 0.284 | - | favorece a Max-pressure, solo sin corregir (p < 0.05) |

## reforma_pico [pico]: Demora total (s/veh demandado)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| MAPPO (semilla elegida) contra tiempo fijo, pico | 36.8 | 79.1 | -42.2 [-51.0, -33.4] | -53.4 % | 10 / 10 | <0.001 | <0.001 | - | favorece a MAPPO (semilla elegida) (p Holm < 0.05) |
| MAPPO (semilla elegida) contra max-pressure, pico | 36.8 | 41.7 | -4.9 [-8.7, -1.0] | -11.7 % | 10 / 10 | 0.017 | 0.167 | - | favorece a MAPPO (semilla elegida), solo sin corregir (p < 0.05) |
| Comunicación (semilla elegida) contra tiempo fijo, pico | 36.8 | 79.1 | -42.3 [-51.1, -33.4] | -53.4 % | 10 / 10 | <0.001 | <0.001 | - | favorece a Comunicación (semilla elegida) (p Holm < 0.05) |
| Comunicación (semilla elegida) contra max-pressure, pico | 36.8 | 41.7 | -4.9 [-8.8, -0.9] | -11.7 % | 10 / 10 | 0.018 | 0.167 | - | favorece a Comunicación (semilla elegida), solo sin corregir (p < 0.05) |

## reforma_mediodia [mediodia]: Demora total (s/veh demandado)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| MAPPO (semilla elegida) contra tiempo fijo, mediodia | 17.2 | 30.4 | -13.2 [-13.7, -12.7] | -43.5 % | 10 / 10 | <0.001 | <0.001 | - | favorece a MAPPO (semilla elegida) (p Holm < 0.05) |
| MAPPO (semilla elegida) contra max-pressure, mediodia | 17.2 | 21.1 | -3.9 [-4.4, -3.4] | -18.5 % | 10 / 10 | <0.001 | <0.001 | - | favorece a MAPPO (semilla elegida) (p Holm < 0.05) |
| Comunicación (semilla elegida) contra tiempo fijo, mediodia | 20.7 | 30.4 | -9.7 [-10.2, -9.2] | -32.0 % | 10 / 10 | <0.001 | <0.001 | - | favorece a Comunicación (semilla elegida) (p Holm < 0.05) |
| Comunicación (semilla elegida) contra max-pressure, mediodia | 20.7 | 21.1 | -0.4 [-0.9, +0.1] | -1.9 % | 10 / 10 | 0.108 | 0.650 | - | sin diferencia detectable |

## reforma_pico_x13 [pico_x13]: Demora total (s/veh demandado)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| MAPPO (semilla elegida) contra tiempo fijo, pico_x13 | 373.3 | 345.7 | +27.5 [-9.9, +65.0] | +8.0 % | 10 / 10 | 0.133 | 0.665 | - | sin diferencia detectable |
| MAPPO (semilla elegida) contra max-pressure, pico_x13 | 373.3 | 252.2 | +121.1 [+83.3, +158.8] | +48.0 % | 10 / 10 | <0.001 | <0.001 | - | favorece a Max-pressure (p Holm < 0.05) |
| Comunicación (semilla elegida) contra tiempo fijo, pico_x13 | 281.8 | 345.7 | -63.9 [-79.7, -48.1] | -18.5 % | 10 / 10 | <0.001 | <0.001 | - | favorece a Comunicación (semilla elegida) (p Holm < 0.05) |
| Comunicación (semilla elegida) contra max-pressure, pico_x13 | 281.8 | 252.2 | +29.6 [+12.8, +46.4] | +11.7 % | 10 / 10 | 0.002 | 0.023 | - | favorece a Max-pressure (p Holm < 0.05) |

## reforma_pico [pico_incident]: Demora total (s/veh demandado)

| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| MAPPO (semilla elegida) contra tiempo fijo, pico_incident | 165.5 | 198.4 | -33.0 [-45.2, -20.7] | -16.6 % | 10 / 10 | <0.001 | <0.001 | - | favorece a MAPPO (semilla elegida) (p Holm < 0.05) |
| MAPPO (semilla elegida) contra max-pressure, pico_incident | 165.5 | 161.8 | +3.7 [-6.9, +14.3] | +2.3 % | 10 / 10 | 0.471 | 1.000 | - | sin diferencia detectable |
| Comunicación (semilla elegida) contra tiempo fijo, pico_incident | 175.2 | 198.4 | -23.3 [-35.4, -11.1] | -11.7 % | 10 / 10 | <0.001 | 0.012 | - | favorece a Comunicación (semilla elegida) (p Holm < 0.05) |
| Comunicación (semilla elegida) contra max-pressure, pico_incident | 175.2 | 161.8 | +13.4 [+2.9, +23.9] | +8.3 % | 10 / 10 | 0.015 | 0.167 | - | favorece a Max-pressure, solo sin corregir (p < 0.05) |

