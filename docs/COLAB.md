# Guía de Colab (opcional)

## 1. ¿Hace falta Colab?

No. La matriz completa (E1 a E8, semillas 0 a 4, 200 episodios por corrida) corre en la Mac con `python -m experiments.run_matrix --jobs 8` en unas **4 a 5 h**. Colab sirve para:

- agregar **semillas extra** (por ejemplo 5 a 9);
- entrenar con **más presupuesto** (E5/E6 con 400 episodios, en una carpeta aparte);
- **repetir** corridas si cambia el código o algo falla.

Colab gratis da unas 2 CPU, así que la matriz completa tarda allí unas 12 a 19 h (2 o 3 sesiones): unas 3 a 4 veces más que en la Mac.

| Qué | Dónde |
|---|---|
| Matriz principal E1 a E8 (5 semillas, 200 episodios) | Mac: `run_matrix --jobs 8`, resultados en `runs/` |
| Semillas extra, o repetir corridas sueltas | Colab, celda A de `colab_train.ipynb` |
| E5/E6 con 400 episodios (extensión) | Colab, celda B, resultados en `runs_x400/` |
| Figuras y tablas | Mac (`python -m analysis.make_all`) o `colab_analysis.ipynb` |
| Demo web, informe PDF | Mac (necesitan Node y Chrome) |

## 2. Pasos, en orden

1. **Antes de abrir Colab.** Asegúrate de que la rama que vas a entrenar (`main` por defecto) esté subida a GitHub: el cuaderno clona el repo, no ve cambios locales. Crea un token de GitHub con permiso de lectura sobre `https://github.com/Alexistodj124/ProyectoFinalAR.git`.
2. **Abre el cuaderno.** En Colab: Archivo -> Subir cuaderno -> `notebooks/colab_train.ipynb`. Entorno de ejecución: **CPU** (el tiempo lo domina SUMO y las redes son pequeñas; no se midió ganancia con GPU).
3. **Secreto.** Panel izquierdo -> Secretos -> agrega `GITHUB_TOKEN` con el token y activa "Acceso desde el cuaderno". Si no existe, la celda 0.3 lo pide con `getpass`.
4. **Celdas 0.1 a 0.6** (una sola vez por sesión): runtime, Drive, clonar el repo, dependencias, sincronización y pruebas rápidas. En 0.4 se instala `requirements.txt`, se fija `SUMO_HOME` (de `import sumo`) y `LIBSUMO_AS_TRACI=1`, y se comprueba `pettingzoo==1.24.3`. Si 0.6 falla, no sigas.
5. **Experimentos**, uno por celda: 1 (E1), 2 a 6 (E2 a E6), 7 (E8, variantes `qmix_fair` y `comm_fair`), 8 (E7 y recolección de E8). E7 lee las corridas de E3 a E6. Deja `JOBS = 2`; cada celda sincroniza `runs/` con Drive al terminar.
6. **Celda 9** muestra el estado y el tiempo de pared de cada trabajo: úsala para calibrar los tiempos de abajo.
7. **Celda 10** crea `resultados.zip` (`runs/` y las carpetas `runs_x*/`, sin TensorBoard) y lo descarga. Una copia queda en Drive.

Las celdas A y B son opcionales. A: elegir experimentos, configs o semillas (`--exp`, `--glob`, `--seeds`) y `--dry-run`. B: reentrenar E5/E6 con `EPISODIOS` (400) en `runs_x400/`, con YAML copiados a `/content/cfg_x400/` que solo cambian `total_episodes` (`run_matrix` no tiene `--total-episodes`). Con 400 episodios hay el doble de checkpoints que evaluar (`every_episodes` sigue en 20).

## 3. Tiempos estimados

Salen de los segundos por episodio medidos en la Mac (`docs/ajuste_aprendizaje.md`, sección 2): cruce 1.5 a 2.2 s y corredor 5.5 a 9 s por episodio de 3600 s simulados, 200 episodios, más ~10 % de selección de checkpoint (~35 s por corrida en el cruce y ~110 a 120 s en el corredor) y la evaluación final (~3.5 s por episodio en el cruce, ~8 s en el corredor, 10 semillas por escenario). E1 se midió completo: 352 s en la Mac, un solo proceso.

"Colab" supone que un núcleo es de 1 a 1.5 veces más lento que en la Mac: **es un supuesto, no se midió en Colab**.

| Exp | Corridas | Por corrida, Mac (`--jobs 8`) | Por corrida, Colab | Total Colab (`--jobs 2`) |
|---|---|---|---|---|
| E1 | 1 (12 combinaciones x 10 semillas) | 6 min | 6 a 10 min | 6 a 10 min |
| E2 | 20 | ~9 min | 7 a 10 min | 1.2 a 1.7 h |
| E3 | 20 | ~11 min | 8 a 12 min | 1.4 a 2 h |
| E4 | 10 | ~10 min | 8 a 12 min | 0.7 a 1 h |
| E5 | 15 | ~38 min | 30 a 45 min | 3.6 a 5.5 h |
| E6 | 10 | ~39 min | 30 a 45 min | 2.5 a 3.7 h |
| E8 (`qmix_fair`, `comm_fair`) | 10 | ~38 min | 30 a 45 min | 2.5 a 3.7 h |
| E7 | 1 (un solo proceso) | 15 a 40 min | | 0.3 a 1 h |
| **Todo** | 88 trabajos | **4 a 5 h** en total | | **12 a 19 h** |

- En la Mac, con 8 procesos cada SUMO va 1.25 a 1.3 veces más lento que con 4 o 5. Las corridas largas (E5, E6, E8) quedan al final de la cola, así que al cierre de la fase de entrenamiento algunos núcleos esperan a las últimas.
- **Extensión de 400 episodios** (celda B), también por proporción: E5 y E6 completos con 5 semillas, 11 a 17 h en Colab (~3.5 a 4 h en la Mac con `--jobs 8`); con 3 semillas, 7 a 10 h; solo `idqn` con 5 semillas, 2.4 a 3.6 h. IDQN es el único método de E5 que no llega a la meseta con 200 episodios.
- Para calibrar: Q-Learning con 200 episodios tarda unos 5 min de entrenamiento en la Mac. Si en Colab tarda 7 u 8, el factor es ~1.5.

## 4. Reanudar tras un corte

`run_matrix` marca cada trabajo terminado con un archivo `DONE` y lo salta la próxima vez. La granularidad es la **corrida completa** (config x semilla): una corrida cortada a medias se repite desde cero.

1. Abre el cuaderno, corre 0.2 a 0.5. `sync_down()` (en 0.5) copia de Drive a `runs/` lo que ya había.
2. Relanza la misma celda del experimento. Lo que tiene `DONE` se salta; lo fallido o incompleto se vuelve a correr.

`sync_up()` corre al final de cada celda y cada 5 min desde un hilo de fondo, así que un corte pierde como máximo unos minutos de lo ya terminado. No se suben `tb/` ni `runs/_quick/`.

## 5. Traer los resultados a la Mac y regenerar figuras

```bash
cd <repo>                                   # raíz del repo local
unzip -o ~/Downloads/resultados.zip         # deja runs/ (y runs_x400/ si la hubo)
source scripts/env.sh
python -m analysis.make_all                 # figuras en docs/figures/, tablas en analysis/results/
# extensión de 400 episodios, sin pisar las figuras principales:
python -m analysis.make_all --runs-dir runs_x400 --fig-dir docs/figures_x400 --table-dir analysis/results_x400
```

- Una misma terna experimento/nombre/semilla se **sobrescribe** al descomprimir. Si la Mac ya tiene las semillas 0 a 4, usa en Colab semillas nuevas (5 a 9) o la carpeta `runs_x400/`.
- Si agregaste semillas o reentrenaste algo, E7 y E8 hay que recalcularlos: `rm runs/E7/DONE runs/E8/DONE && python -m experiments.run_matrix --exp E7 E8`. (E7 solo detecta que está desactualizado frente a los trabajos de su misma llamada.)
- Para ver un modelo de Colab en la demo web: `WEB_RUNS_DIR=/ruta/a/runs python -m uvicorn web.backend.app:app --port 8000` (ver `web/README.md`).
- El mismo `make_all` corre en `notebooks/colab_analysis.ipynb` (no necesita SUMO, solo lee los CSV).

## 6. Problemas comunes

- **libsumo: una simulación por proceso.** Con `LIBSUMO_AS_TRACI=1` no se pueden abrir dos entornos en el mismo proceso. Para paralelizar usa `--jobs N` (un proceso por trabajo), no hilos. La demo web y `sumo-gui` necesitan TraCI por socket: no exportes `LIBSUMO_AS_TRACI` o pasa `--no-libsumo`.
- **`SUMO_HOME` no definido.** `python -c "import sumo; print(sumo.SUMO_HOME)"` da la ruta. En el cuaderno la celda 0.4 la guarda en `os.environ`; se pierde si el runtime se reinicia, así que repite 0.3 y 0.4 (los `!python ...` heredan ese entorno).
- **`pettingzoo`.** `requirements.txt` lo fija en 1.24.3 porque `sumo-rl` 1.4.5 falla con la 1.25 o posterior (`agent_selector` pasó a ser un módulo). Si otra celda instala una versión nueva, `pip install pettingzoo==1.24.3`. La celda 0.4 lo verifica.
- **Errores de binarios de numpy** justo después de `pip install`: Entorno de ejecución -> Reiniciar sesión y repite desde 0.3.
- **Drive.** Hay que montarlo en cada sesión nueva. Si `rsync` no existe, la celda 0.5 intenta instalarlo. La cuota gratis es de 15 GB; las corridas de humo sugieren del orden de 100 MB para toda la matriz, pero es una estimación (`du -sh runs`). Si `sync_up()` imprime errores, el zip de la celda 10 es el respaldo.
- **Un trabajo falla.** `runs/manifest.csv` guarda `status=failed` y el código de salida; el detalle está en `runs/<exp>/<nombre>/seed<k>/stdout.log`. Relanzar la celda reintenta solo los que no tienen `DONE`.
- **`Repository not found` o 403 al clonar.** El token no tiene acceso a ese repo, o falta activar "Acceso desde el cuaderno" en el secreto.
- **Interrumpir una celda** (Detener) puede dejar procesos hijos vivos: `!pkill -f experiments.` antes de relanzar.
- Los `.ipynb` se generan con `python scripts/colab_make_notebooks.py`; edita ese script, no el JSON.
