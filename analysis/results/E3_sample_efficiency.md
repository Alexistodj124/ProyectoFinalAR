# E3: eficiencia de muestras

Primer checkpoint (cada 20 episodios = 14 400 pasos) cuya demora total de validación (semillas 2000 y 2001, escenario `cruce_pico`) es menor o igual a la de la línea base indicada (evaluación final, semillas 1000 a 1009, como referencia). Con 2 episodios de validación es una medida ruidosa; el mejor checkpoint tiene sesgo optimista (es el mínimo de 10 valores).

## Eficiencia de muestras

| Método | semillas que llegan a 1.5 × tiempo fijo (50 s) | pasos hasta 1.5 × tiempo fijo (mediana, k) | semillas que llegan a Tiempo fijo (34 s) | pasos hasta Tiempo fijo (mediana, k) | semillas que llegan a Max-pressure (20 s) | pasos hasta Max-pressure (mediana, k) | mejor checkpoint (media entre semillas, s) | último checkpoint (media entre semillas, s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DQN base | 5 de 5 | 43 | 5 de 5 | 58 | 0 de 5 | nunca | 27.7 | 40.9 |
| DQN + Double | 5 de 5 | 43 | 5 de 5 | 58 | 0 de 5 | nunca | 28.1 | 38.7 |
| DQN + Double + Dueling | 5 de 5 | 43 | 5 de 5 | 58 | 0 de 5 | nunca | 28.8 | 41.1 |
| DQN + Double + Dueling + PER | 5 de 5 | 43 | 5 de 5 | 58 | 0 de 5 | nunca | 28.3 | 42.4 |
