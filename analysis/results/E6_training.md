# E6: entrenamiento

Media ± IC95 entre semillas de entrenamiento. El retorno es la suma de las recompensas del episodio (la recompensa de entrenamiento incluye el backlog de inserción); no es comparable entre algoritmos con escalas de recompensa distintas.

## Entrenamiento

| Método | semillas | retorno final (último 10 % de episodios) | pasos de entorno | tiempo de pared (min) |
|---|---:|---:|---:|---:|
| IDQN + colas de vecinos | 5 | -218 ± 59 | 144000 | 31.8 |
| Comunicación (DIAL) | 5 | -221 ± 174 | 144000 | 27.2 |
