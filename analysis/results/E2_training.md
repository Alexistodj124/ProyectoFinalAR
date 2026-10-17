# E2: entrenamiento

Media ± IC95 entre semillas de entrenamiento. El retorno es la suma de las recompensas del episodio (la recompensa de entrenamiento incluye el backlog de inserción); no es comparable entre algoritmos con escalas de recompensa distintas.

## Entrenamiento

| Método | semillas | retorno final (último 10 % de episodios) | pasos de entorno | tiempo de pared (min) |
|---|---:|---:|---:|---:|
| Q-Learning | 5 | -320 ± 163 | 144000 | 6.1 |
| Dyna-Q n=5 | 5 | -456 ± 50 | 144000 | 6.4 |
| Dyna-Q n=10 | 5 | -492 ± 153 | 144000 | 6.4 |
| Dyna-Q n=50 | 5 | -542 ± 91 | 144000 | 7.0 |
