# E4: entrenamiento

Media ± IC95 entre semillas de entrenamiento. El retorno es la suma de las recompensas del episodio (la recompensa de entrenamiento incluye el backlog de inserción); no es comparable entre algoritmos con escalas de recompensa distintas.

## Entrenamiento

| Método | semillas | retorno final (último 10 % de episodios) | pasos de entorno | tiempo de pared (min) |
|---|---:|---:|---:|---:|
| DQN mejor (E4) | 5 | -61 ± 16 | 144000 | 8.9 |
| PPO | 5 | -111 ± 40 | 144000 | 7.3 |
