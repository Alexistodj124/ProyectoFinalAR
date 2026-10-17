# E5: entrenamiento

Media ± IC95 entre semillas de entrenamiento. El retorno es la suma de las recompensas del episodio (la recompensa de entrenamiento incluye el backlog de inserción); no es comparable entre algoritmos con escalas de recompensa distintas.

## Entrenamiento

| Método | semillas | retorno final (último 10 % de episodios) | pasos de entorno | tiempo de pared (min) |
|---|---:|---:|---:|---:|
| IDQN | 5 | -417 ± 619 | 144000 | 32.9 |
| QMIX | 5 | -138 ± 44 | 144000 | 32.4 |
| MAPPO | 5 | -272 ± 109 | 144000 | 25.3 |
