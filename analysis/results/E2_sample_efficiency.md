# E2: eficiencia de muestras

Primer checkpoint (cada 20 episodios = 14 400 pasos) cuya demora total de validación (semillas 2000 y 2001, escenario `cruce_pico`) es menor o igual a la de la línea base indicada (evaluación final, semillas 1000 a 1009, como referencia). Con 2 episodios de validación es una medida ruidosa; el mejor checkpoint tiene sesgo optimista (es el mínimo de 10 valores).

## Eficiencia de muestras

| Método | semillas que llegan a 1.5 × tiempo fijo (50 s) | pasos hasta 1.5 × tiempo fijo (mediana, k) | semillas que llegan a Tiempo fijo (34 s) | pasos hasta Tiempo fijo (mediana, k) | semillas que llegan a Max-pressure (20 s) | pasos hasta Max-pressure (mediana, k) | mejor checkpoint (media entre semillas, s) | último checkpoint (media entre semillas, s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Q-Learning | 4 de 5 | 101 | 0 de 5 | nunca | 0 de 5 | nunca | 47.2 | 92.5 |
| Dyna-Q n=5 | 4 de 5 | 101 | 0 de 5 | nunca | 0 de 5 | nunca | 51.1 | 99.1 |
| Dyna-Q n=10 | 2 de 5 | 94 | 0 de 5 | nunca | 0 de 5 | nunca | 54.9 | 85.8 |
| Dyna-Q n=50 | 1 de 5 | 101 | 0 de 5 | nunca | 0 de 5 | nunca | 62.4 | 120.9 |
