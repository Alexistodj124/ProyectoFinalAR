# Guion de la presentación

Semáforos inteligentes en Av. La Reforma con RL multiagente · CC3104 · UVG 2026. 19 diapositivas, unos 15–20 minutos (≈1 min por diapositiva; la demo puede tomar 2–3 min). Las notas también están en el campo de notas de `presentacion.pptx`. Lo marcado con `<completar>` o `<dato>` lo llena el equipo; no se inventaron cifras (todas salen de `docs/informe/informe.md` y `analysis/results/`).

## 1. Portada

Buenos días. Somos <completar integrantes>. Presentamos nuestro proyecto final de Aprendizaje por Refuerzo: semáforos inteligentes en la Avenida La Reforma usando aprendizaje por refuerzo multiagente. La idea es sencilla de contar: tomamos un tramo real de Reforma con cinco semáforos consecutivos, lo simulamos en SUMO y comparamos, con el mismo protocolo, los controladores clásicos contra agentes que aprenden a decidir la siguiente fase. Les vamos a contar qué funcionó, qué no, y un hallazgo sobre la recompensa que cambió nuestras conclusiones. Al final hay una demo en vivo con los modelos entrenados.

## 2. El problema

La Avenida La Reforma es uno de los ejes más cargados de la ciudad: un bulevar con arriate central, tres carriles por sentido y calles transversales de una vía. Sus semáforos funcionan con tiempos fijos: reparten el verde según un plan, sin saber cuántos vehículos esperan realmente en cada aproximación. <dato: aquí va una cifra de congestión con fuente verificable; no la inventamos>. Además, los cruces están a distancias muy desiguales, de 123 a 547 metros, así que coordinarlos no es trivial: entre la 15 y la 14 calle caben muy pocos carros y una cola bloquea enseguida al cruce anterior.

## 3. Pregunta de investigación

Nuestra pregunta tiene dos partes. Primero, cuánto reduce el aprendizaje por refuerzo multiagente la espera frente al control actual. Y segundo, si esa mejora se mantiene cuando cambian las condiciones. Para que la respuesta sea honesta comparamos contra tres referencias: el tiempo fijo, un controlador actuado y max-pressure, que es una regla clásica de la literatura y es exigente. Y para la segunda parte evaluamos en una hora que el agente no vio, el mediodía, con 30 % más demanda y con un carril cerrado por un incidente.

## 4. Escenario

Este es el corredor que modelamos: 1.65 kilómetros de Reforma entre la Plaza Obelisco y la 5a calle, con cinco semáforos consecutivos. La red se construyó con las coordenadas, sentidos y carriles de OpenStreetMap, y está georreferenciada. Para los métodos de un solo agente recortamos el cruce de la 12 calle, en azul, que es el más cargado. El tramo en rojo es donde simulamos el incidente. Algo importante desde ya: los conteos vehiculares y el ciclo del semáforo fijo son sintéticos y provisionales. Los generó un script con valores plausibles; no son conteos de campo. Por eso nuestros resultados son una comparación metodológica entre controladores, no una predicción de lo que pasaría en la calle.

## 5. Formulación

Formalmente, cada cruce es un MDP. El estado es la observación de sumo-rl: qué fase está activa, si ya se cumplió el verde mínimo, y la densidad y la cola de cada carril; en la 12 calle son 24 valores. La acción es elegir la siguiente fase verde cada 5 segundos; el amarillo y el verde mínimo los impone el entorno, por seguridad, no el agente. La recompensa es cuánto bajó la espera acumulada, y como veremos en un momento, incluye a los vehículos que esperan para entrar. En el corredor tenemos cinco agentes que solo ven su cruce: eso es un Dec-POMDP. Usamos recompensa de equipo y, en los métodos centralizados, un estado global que solo existe durante el entrenamiento. En ejecución cada semáforo decide solo.

## 6. Métodos

Comparamos una escalera de métodos. A la izquierda, tres líneas base sin aprendizaje: el tiempo fijo, calculado con Webster; el actuado de SUMO, que extiende el verde mientras detecta vehículos; y max-pressure, que en cada intervalo da verde a la fase con mayor diferencia de ocupación entre entrada y salida. En el cruce de la 12 calle probamos un agente: Q-Learning y Dyna-Q tabulares, DQN con sus tres mejoras, y PPO. En el corredor completo, multiagente: aprendices independientes IDQN, QMIX, MAPPO con crítico centralizado y comunicación aprendida al estilo DIAL. En total, 16 configuraciones de RL, todas con la misma fábrica de entornos y el mismo presupuesto.

## 7. Hallazgo clave

Este es el hallazgo que más nos enseñó. En las primeras corridas, todos los agentes parecían aprender y le ganaban al tiempo fijo en espera media. Por ejemplo, un DQN bajaba la espera a 14.9 segundos contra 29.2 del fijo. Pero mirando más de cerca, habían aprendido a cerrar una entrada: casi 5 % de la demanda nunca entraba a la red. La recompensa de sumo-rl solo cuenta la espera sobre los carriles, y cuando un carril se llena la penalización queda acotada; los que no caben esperan afuera gratis. Contando a esos vehículos, la demora total era 97.1 segundos, tres veces la del fijo. La corrección fue doble: entrenar con una recompensa que suma la espera de los pendientes, y medir todo con la demora total por vehículo demandado, que no se puede mejorar dejando autos fuera. El mismo DQN bajó a 0.46 % de backlog y 34.4 segundos.

## 8. Protocolo

Para que la comparación sea justa, todos los métodos de RL siguen el mismo protocolo. Cada configuración se entrena con cinco semillas y el mismo presupuesto: 200 episodios de una hora, que son 144 000 decisiones por agente. Cada 20 episodios guardamos un checkpoint y elegimos el mejor con dos semillas de validación. Ese modelo se evalúa en diez episodios con semillas que nunca se usaron para entrenar ni para elegir. Reportamos media e intervalo de confianza del 95 %, donde la unidad es la semilla de entrenamiento, y comparamos con la prueba t de Welch corregida por Holm. Con cinco semillas el poder es bajo: «sin diferencia detectable» no significa «iguales». Y la métrica principal es la demora total que acabamos de explicar.

## 9. E1 líneas base

El primer experimento responde qué tan bueno es lo actual. En el corredor en hora pico, el tiempo fijo tiene 79.1 segundos de demora total por vehículo, el actuado 63.4 y max-pressure 41.7: casi la mitad que el fijo. En el cruce de la 12 calle pasa lo mismo, 19.8 contra 33.6. Max-pressure también deja el menor backlog. Esto es importante para el resto de la charla: max-pressure es una regla de una línea que no aprende nada, y aun así es la vara más alta. Con 30 % más demanda el corredor se satura en las tres líneas base, con entre 12.7 y 15.7 % de la demanda sin poder entrar.

## 10. E2 a E4 un cruce

En el cruce aislado probamos tres preguntas. E2: ¿ayuda planificar? No. Dyna-Q con 50 pasos de planificación quedó incluso 8 segundos peor que Q-Learning, sin diferencia detectable, y ningún método tabular alcanzó al tiempo fijo; además dejan autos afuera. E3: ¿qué mejora de DQN aporta más? Ninguna se separa del ruido; la versión completa con Double, Dueling y PER tiene la media más baja, 21.1 segundos, y es la que usamos después. E4: DQN contra PPO. Rinden parecido: 21.1 contra 23.8 segundos, sin diferencia detectable entre ellos ni con max-pressure, que tiene 19.8. Los dos bajan claramente la demora frente al fijo y al actuado.

## 11. E5 y E6 corredor multiagente

En el corredor completo, E5 compara qué tan centralizado es el entrenamiento. MAPPO obtiene 46.8 segundos: 41 % menos que el tiempo fijo y 26 % menos que el actuado, ambos significativos tras Holm. El orden de las medias es el esperado, MAPPO, luego QMIX, luego IDQN, y sobre todo MAPPO es mucho más estable entre semillas; pero con cinco semillas esas diferencias no son detectables. Lo central: MAPPO queda 5.1 segundos por encima de max-pressure, sin diferencia detectable. En E6, la comunicación aprendida baja la media de IDQN al nivel de MAPPO, 46.2 segundos, pero no vemos ola verde: los vehículos paran más veces que con cualquier línea base. La ganancia viene de vaciar colas, no de sincronizar cruces.

## 12. E7 robustez

E7 pregunta si el mejor agente generaliza. A mediodía, una hora que no vio, todos los agentes siguen ganándole al tiempo fijo, y MAPPO tiene la menor demora del corredor. Con el carril cerrado, MAPPO y comunicación mejoran al fijo y al actuado, pero no a max-pressure. En el cruce aislado, con dos carriles cerrados en la aproximación sur, DQN y PPO mejoran 16 % al tiempo fijo pero quedan 21 % por detrás de max-pressure. La caída está con 30 % más demanda: MAPPO sube a 373 segundos, 8 % peor que el tiempo fijo y 48 % peor que max-pressure, y deja casi un cuarto de la demanda sin entrar. Con las cinco semillas de E5 el resultado es el mismo. Su demora se multiplica por 10 respecto de la hora pico, contra 6 de max-pressure. Ojo: aquí cada agente es una sola semilla, la mejor en validación, así que la tabla incluso favorece a los agentes. Lo aprendido no se sostiene fuera del rango de demanda del entrenamiento.

## 13. E8 equidad y CO2

E8 pregunta si se sacrifica a las calles transversales. En el cruce aislado, sí: max-pressure, DQN y PPO bajan la demora total favoreciendo a Reforma, y la espera máxima de un vehículo en la 12 calle sube de 113 segundos con el fijo a entre 168 y 271. PPO es el más equitativo de los aprendidos. Es el trade-off clásico entre eficiencia y equidad. En el corredor, en promedio, ese costo no apareció: MAPPO tiene esperas máximas en transversales menores que las líneas base, aunque alguna semilla individual sí abandonó una calle. Probamos una penalización de equidad: ayudó a QMIX pero no fue detectable. Y en CO2, los que menos emiten son el actuado y max-pressure; los agentes paran más veces y quedan entre −8.4 y +2.7 % respecto del fijo.

## 14. Resumen de resultados

Esta figura resume todo. A la izquierda el corredor, a la derecha el cruce; las líneas punteadas son el tiempo fijo y max-pressure. Los mejores métodos aprendidos, MAPPO y comunicación en el corredor y DQN y PPO en el cruce, mejoran claramente al tiempo fijo y al actuado. Pero quedan en la misma banda que max-pressure o un poco por encima. Los métodos tabulares ni siquiera llegan al tiempo fijo. Fíjense también en el ancho de los intervalos: IDQN y QMIX varían mucho entre semillas, y MAPPO es el más estable de los multiagente. Recuerden que la magnitud frente al fijo depende de conteos sintéticos; la comparación contra max-pressure depende menos de ese supuesto, porque todos ven exactamente la misma demanda.

## 15. Demo en vivo

Ahora la demo. Son dos simulaciones de SUMO corriendo en paralelo con la misma demanda y la misma semilla: a la izquierda el semáforo de tiempo fijo y a la derecha MAPPO, el modelo entrenado real. Vamos a: uno, arrancar en hora pico y acelerar para ver cómo se separan las curvas; dos, inyectar carros en la entrada sur y en la 12 calle; tres, cerrar dos carriles entre la 12 y la 10a calle y ver cómo crece la cola. Una aclaración: la tarjeta «Mejora» usa la espera promedio en vivo, que no es la demora total de la evaluación; los números oficiales son los que ya mostramos. Si algo falla, tenemos el video de respaldo de tres minutos y medio.

## 16. Ética y limitaciones

Hay cosas que nuestro modelo no ve y que importan. No hay peatones: un controlador que solo optimiza demora vehicular puede recortar las ventanas para cruzar, así que las fases peatonales deberían ser una restricción dura. No sabe que existen las ambulancias: esa prioridad tiene que ir por encima del agente. Y la recompensa cuenta vehículos, no personas, así que no distingue un bus lleno de un carro. Entre las limitaciones: los datos son sintéticos, cinco semillas dan poco poder estadístico, y en la simulación el agente ve colas exactas por carril, algo que en la calle exigiría detectores en cada carril. Además, optimizar demora total es una decisión de valores: en el cruce ganan quienes van por la avenida y pierden las transversales. Eso debería decidirse con la Municipalidad y la ciudadanía.

## 17. Conclusiones y trabajo futuro

Respondiendo la pregunta, con datos sintéticos: primero, sí hay mejora frente al control actual: MAPPO baja la demora total 41 % en el corredor y DQN 37 % en el cruce. Segundo, ningún método aprendido superó a max-pressure: una regla clásica bien implementada fue la vara que el RL no pasó con este presupuesto. Tercero, los agentes se degradan más que las reglas clásicas cuando la demanda sale del rango de entrenamiento. Y cuarto, un hallazgo metodológico: con la recompensa estándar y la espera media, todos habrían parecido mejores mientras bloqueaban entradas. Como trabajo futuro, lo primero son datos reales; después, peatones, buses y motos, más semillas y entrenamiento con demanda variable, y usar max-pressure como respaldo o punto de partida del agente.

## 18. Uso de IA

Declaramos que usamos IA generativa de forma intensiva. La herramienta principal fue Claude Code, un asistente de programación que trabaja desde la terminal. Con él redactamos el plan y los contratos entre módulos, y varios agentes trabajaron en paralelo, cada uno en su rama: red y demanda, líneas base, métodos, experimentos, demo web y análisis. También generó los borradores del informe y de esta presentación a partir de las tablas de resultados. El asistente puede equivocarse de formas difíciles de notar, por eso el equipo revisó el código y los números y asume la responsabilidad. <completar: qué verificó el equipo a mano y otras herramientas usadas>.

## 19. Preguntas

Gracias. En resumen: el RL multiagente le gana al semáforo fijo y al actuado en nuestra simulación, pero una regla clásica como max-pressure sigue siendo igual o mejor, y los agentes se degradan con más demanda. El código, el informe y los resultados están en el repositorio. Con gusto respondemos sus preguntas.

