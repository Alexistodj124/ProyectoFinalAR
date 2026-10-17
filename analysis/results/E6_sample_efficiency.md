# E6: eficiencia de muestras

Primer checkpoint (cada 20 episodios = 14 400 pasos) cuya demora total de validación (semillas 2000 y 2001, escenario `reforma_pico`) es menor o igual a la de la línea base indicada (evaluación final, semillas 1000 a 1009, como referencia). Con 2 episodios de validación es una medida ruidosa; el mejor checkpoint tiene sesgo optimista (es el mínimo de 10 valores).

## Eficiencia de muestras

| Método | semillas que llegan a 1.5 × tiempo fijo (119 s) | pasos hasta 1.5 × tiempo fijo (mediana, k) | semillas que llegan a Tiempo fijo (79 s) | pasos hasta Tiempo fijo (mediana, k) | semillas que llegan a Max-pressure (42 s) | pasos hasta Max-pressure (mediana, k) | mejor checkpoint (media entre semillas, s) | último checkpoint (media entre semillas, s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| IDQN | 5 de 5 | 58 | 4 de 5 | 101 | 0 de 5 | nunca | 69.2 | 75.6 |
| IDQN + colas de vecinos | 5 de 5 | 58 | 5 de 5 | 58 | 0 de 5 | nunca | 53.5 | 72.8 |
| MAPPO | 5 de 5 | 43 | 5 de 5 | 72 | 1 de 5 | 130 | 58.2 | 63.0 |
| Comunicación (DIAL) | 5 de 5 | 58 | 5 de 5 | 72 | 0 de 5 | nunca | 50.6 | 52.9 |
