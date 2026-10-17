# E3: entrenamiento

Media ± IC95 entre semillas de entrenamiento. El retorno es la suma de las recompensas del episodio (la recompensa de entrenamiento incluye el backlog de inserción); no es comparable entre algoritmos con escalas de recompensa distintas.

## Entrenamiento

| Método | semillas | retorno final (último 10 % de episodios) | pasos de entorno | tiempo de pared (min) |
|---|---:|---:|---:|---:|
| DQN base | 5 | -54 ± 8 | 144000 | 7.6 |
| DQN + Double | 5 | -67 ± 25 | 144000 | 7.6 |
| DQN + Double + Dueling | 5 | -58 ± 18 | 144000 | 8.0 |
| DQN + Double + Dueling + PER | 5 | -61 ± 16 | 144000 | 8.9 |
