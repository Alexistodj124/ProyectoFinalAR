"""Regenerates notebooks/colab_train.ipynb and notebooks/colab_analysis.ipynb (plain json, no nbformat needed).

    python scripts/colab_make_notebooks.py

Edit THIS file, not the .ipynb (they are generated). Guide for the human: docs/COLAB.md.
"""
from __future__ import annotations

import json
from pathlib import Path

NB_DIR = Path(__file__).resolve().parents[1] / "notebooks"
REPO_URL = "https://github.com/Alexistodj124/ProyectoFinalAR.git"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text: str, form: bool = False) -> dict:
    meta = {"cellView": "form"} if form else {}
    return {"cell_type": "code", "metadata": meta, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


def notebook(cells: list[dict]) -> dict:
    # nbformat 4.4: no cell ids. CPU runtime on purpose: the simulation (SUMO, one process per job) is the
    # bottleneck and the networks are small MLPs; a GPU was not measured to help.
    return {"cells": cells, "nbformat": 4, "nbformat_minor": 4,
            "metadata": {"colab": {"provenance": []},
                         "kernelspec": {"display_name": "Python 3", "name": "python3"},
                         "language_info": {"name": "python"}}}


# Clone/pull of the private repo with the GitHub token from the Colab secret GITHUB_TOKEN.
# The token goes in an HTTP header, so it is not stored in .git/config nor in FETCH_HEAD, and it is
# masked in the output.
CLONE_CELL = '''
import base64, getpass, os, subprocess
BRANCH = "main" #@param {type:"string"}
REPO_URL = "__REPO_URL__"
REPO_DIR = "/content/ProyectoFinalAR"
try:
    from google.colab import userdata
    TOKEN = userdata.get("GITHUB_TOKEN")
except Exception:
    TOKEN = getpass.getpass("GITHUB_TOKEN: ")
AUTH = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()

def git(*args):
    r = subprocess.run(["git", "-c", f"http.extraheader=AUTHORIZATION: basic {AUTH}", *args], capture_output=True, text=True)
    print((r.stdout + r.stderr).replace(AUTH, "***").replace(TOKEN, "***").strip())
    r.check_returncode()

if not os.path.isdir(REPO_DIR + "/.git"):
    git("clone", "--branch", BRANCH, REPO_URL, REPO_DIR)
else:
    git("-C", REPO_DIR, "pull", "--ff-only", "origin", BRANCH)
os.chdir(REPO_DIR)
git("log", "-1", "--oneline")
'''.replace("__REPO_URL__", REPO_URL)


# ------------------------------------------------------------------ training notebook
TRAIN_CELL = '''
SEEDS = "0 1 2 3 4" #@param {type:"string"}
JOBS = 2 #@param {type:"integer"}
QUICK = False #@param {type:"boolean"}
# QUICK = prueba de humo (120 s simulados, 2 episodios); sus resultados van a runs/_quick y no se sincronizan.
# Lo que ya tiene marca DONE se salta solo: puedes volver a lanzar la celda tras un corte.
flags = "--quick" if QUICK else ""
!python -m experiments.run_matrix --exp __EXP__ --seeds {SEEDS} --jobs {JOBS} {flags}
sync_up()
'''


def train_cell(exp: str) -> dict:
    return code(TRAIN_CELL.replace("__EXP__", exp), form=True)


def train_notebook() -> dict:
    c = [
        md("""
# Entrenamiento en Colab: semáforos inteligentes en Av. La Reforma

Colab es **opcional**: la matriz completa (E1 a E8, semillas 0 a 4, 200 episodios) corre en la Mac en unas 4 a 5 h con `--jobs 8`. Este cuaderno sirve para semillas extra, presupuestos más largos (celda opcional B) o para repetir corridas. La guía paso a paso está en `docs/COLAB.md`.

Qué hace `experiments.run_matrix` (cada fase espera a la anterior; cada trabajo es un proceso con su propio libsumo):
1. **E1**: evalúa las líneas base (fijo, actuado, max-pressure) con las 10 `EVAL_SEEDS`.
2. **E2 a E6 y las variantes con equidad de E8 (`qmix_fair`, `comm_fair`)**: entrenan 200 episodios. Al terminar cada corrida se evalúan sus checkpoints (uno cada 20 episodios) con las `VAL_SEEDS`, el mejor se copia a `best/` y la evaluación final (`eval.csv`) carga `best/` y usa las `EVAL_SEEDS`.
3. **E7**: robustez (mediodía, pico +30 %, incidente) de los mejores agentes y las líneas base.
4. **E8**: reúne los `eval.csv` en `runs/E8/fairness.csv`.

Una corrida con marca `DONE` se salta, así que cualquier celda se puede relanzar tras un corte. Una corrida interrumpida a medias se reinicia desde cero (no hay reanudación por episodio).

**Orden:** 0 (entorno) -> 1 (E1) -> 2 a 6 (E2 a E6) -> 7 (E8, variantes con equidad) -> 8 (E7 y recolección de E8) -> 9 (estado) -> 10 (empaquetar). Las celdas A y B son opcionales. E7 y E8 leen lo que dejaron E1 a E6.

**Tiempos estimados en Colab gratis** (2 CPU, `--jobs 2`, 5 semillas). Salen de los segundos por episodio de `docs/ajuste_aprendizaje.md` (cruce 1.5 a 2.2 s, corredor 5.5 a 9 s por episodio de 3600 s simulados), más ~10 % de selección de checkpoint y la evaluación final (3.5 s por episodio en el cruce, 8 s en el corredor). Se midieron en la Mac; el rango supone que un núcleo de Colab es de 1 a 1.5 veces más lento. **No se midió en Colab**: calibra con la primera corrida (Q-Learning, 200 episodios, tarda unos 5 min en la Mac).

| Celda | Corridas | Por corrida | Total con `--jobs 2` |
|---|---|---|---|
| 1. E1 (un solo proceso) | 1 | | 6 a 10 min |
| 2. E2 (Q-Learning, Dyna-Q n5/n10/n50) | 20 | 7 a 10 min | 1.2 a 1.7 h |
| 3. E3 (4 variantes de DQN) | 20 | 8 a 12 min | 1.4 a 2 h |
| 4. E4 (DQN, PPO) | 10 | 8 a 12 min | 0.7 a 1 h |
| 5. E5 (IDQN, QMIX, MAPPO) | 15 | 30 a 45 min | 3.6 a 5.5 h |
| 6. E6 (IDQN con vecinos, comm) | 10 | 30 a 45 min | 2.5 a 3.7 h |
| 7. E8 (`qmix_fair`, `comm_fair`; la recolección tarda segundos) | 10 | 30 a 45 min | 2.5 a 3.7 h |
| 8. E7 (un solo proceso) | 1 | | 0.3 a 1 h |
| **Todo** | 88 trabajos | | **unas 12 a 19 h: 2 o 3 sesiones** |

Las sesiones gratis se cortan por inactividad y por tiempo máximo, así que conviene lanzar de a un experimento, dejar la pestaña abierta y confiar en la sincronización con Drive (0.5). Corre primero E5 o E6 con 1 semilla si quieres medir antes de comprometer horas.
"""),
        md("## 0. Entorno\n### 0.1 Runtime\nUsa un runtime de **CPU**: el tiempo lo domina SUMO (un proceso por trabajo) y las redes son MLP pequeñas; no se midió ganancia con GPU. Colab gratis da 2 CPU, así que `JOBS = 2`; si tu runtime tiene más, sube `JOBS`."),
        code("""
import os, sys
print(sys.version)
print("CPUs:", os.cpu_count(), "-> JOBS recomendado:", min(os.cpu_count() or 1, 8))
"""),
        md("### 0.2 Google Drive (opcional pero recomendado)\nLas sesiones de Colab mueren. Montamos Drive para guardar `runs/` cada cierto tiempo y poder reanudar. Pon `USE_DRIVE = False` para trabajar solo en local (se pierde todo al cerrar el runtime, salvo que descargues el zip de la celda 10)."),
        code("""
USE_DRIVE = True #@param {type:"boolean"}
DRIVE_DIR = "/content/drive/MyDrive/ProyectoFinalAR/runs" #@param {type:"string"}
if USE_DRIVE:
    from google.colab import drive
    drive.mount("/content/drive")
""", form=True),
        md(f"""
### 0.3 Clonar el repositorio privado
Repo: `{REPO_URL}`. Necesitas un token de GitHub con permiso de lectura sobre ese repo:
- Opción A (recomendada): en Colab, panel de la izquierda -> llave (Secretos) -> agrega `GITHUB_TOKEN` y activa "Acceso desde el cuaderno".
- Opción B: si no hay secreto, se pide con `getpass` (no se imprime).

El token viaja en un encabezado HTTP: no queda en `.git/config` y se enmascara en la salida. `BRANCH` es la rama a entrenar (normalmente `main`). Si el clon ya existe, hace `git pull --ff-only`.
"""),
        code(CLONE_CELL, form=True),
        md("### 0.4 Dependencias y variables de SUMO\nInstala `requirements.txt` (SUMO viene por pip: `eclipse-sumo`, `libsumo`, `traci`, `sumolib`; `pettingzoo` queda fijo en 1.24.3 porque `sumo-rl` 1.4.5 se rompe con la 1.25 o posterior). Fija `SUMO_HOME` a partir de `import sumo` y `LIBSUMO_AS_TRACI=1` (una simulación por proceso, mucho más rápido; `run_matrix` también lo pone). Tarda 2 a 4 minutos la primera vez. Equivale a `scripts/colab_setup.sh`. Si después de instalar aparece un error de binarios de numpy, reinicia el runtime (Entorno de ejecución -> Reiniciar sesión) y repite desde 0.3."),
        code("""
!pip install -q -r requirements.txt
import importlib.metadata as im, sumo
os.environ["SUMO_HOME"] = sumo.SUMO_HOME
os.environ["LIBSUMO_AS_TRACI"] = "1"
os.environ["PYTHONPATH"] = REPO_DIR + os.pathsep + os.environ.get("PYTHONPATH", "")
assert im.version("pettingzoo") == "1.24.3", "pettingzoo debe ser 1.24.3 (requirements.txt)"
print("SUMO_HOME =", sumo.SUMO_HOME, "| pettingzoo", im.version("pettingzoo"), "| torch", im.version("torch"))
"""),
        md("### 0.5 Sincronización con Drive\n`sync_up()` copia `runs/` a Drive (sin los eventos de TensorBoard ni `runs/_quick`). Se llama al final de cada experimento y, además, cada 5 minutos desde un hilo de fondo. `sync_down()` restaura lo que ya estaba en Drive: se llama al arrancar, así que **tras un corte basta volver a correr 0.2 a 0.5 y relanzar la celda del experimento**; las corridas con `DONE` se saltan. `EXTRA_SYNC` registra otras carpetas (la celda B agrega la suya)."),
        code("""
import shutil, subprocess, threading, time
RUNS = REPO_DIR + "/runs"
DRIVE_ROOT = os.path.dirname(DRIVE_DIR.rstrip("/"))
EXTRA_SYNC = {}  # carpeta local -> carpeta en Drive (las celdas opcionales la llenan)
if USE_DRIVE and shutil.which("rsync") is None:
    subprocess.run(["apt-get", "install", "-y", "-qq", "rsync"], check=False)

def _rsync(src, dst):
    os.makedirs(dst, exist_ok=True)
    r = subprocess.run(["rsync", "-a", "--exclude", "tb/", "--exclude", "_quick/", src.rstrip("/") + "/", dst.rstrip("/") + "/"],
                       capture_output=True, text=True)
    if r.returncode not in (0, 24):  # 24 = un archivo desapareció durante la copia (corrida en curso)
        print("rsync:", r.stderr.strip()[:300])

def _pairs():
    return {RUNS: DRIVE_DIR, **EXTRA_SYNC}

def sync_up():
    if USE_DRIVE:
        for local, remote in _pairs().items():
            if os.path.isdir(local):
                _rsync(local, remote)

def sync_down():
    if USE_DRIVE:
        for local, remote in _pairs().items():
            if os.path.isdir(remote):
                _rsync(remote, local)

def _loop():
    while True:
        time.sleep(300)
        try:
            sync_up()
        except Exception as e:
            print("sync error:", e)

sync_down()  # reanuda: lo que ya estaba en Drive cuenta como hecho
if USE_DRIVE and not any(t.name == "drive-sync" for t in threading.enumerate()):
    threading.Thread(target=_loop, daemon=True, name="drive-sync").start()
print("runs/ restaurado" if os.path.isdir(RUNS) else "runs/ vacío (primera vez)")
"""),
        md("### 0.6 Pruebas rápidas (2 a 4 min)\nSi algo falla aquí, no sigas: revisa el entorno. La primera línea corre las pruebas de humo de SUMO y sumo-rl, la segunda lista los 88 trabajos de la matriz completa (marca `skip (DONE)` los ya hechos) y la tercera entrena y evalúa E3 de punta a punta en versión mínima (`--quick`: 120 s simulados, 2 episodios, resultados en `runs/_quick`)."),
        code("""
!python -m pytest -q tests/test_smoke.py
!python -m experiments.run_matrix --dry-run | tail -n 3
!python -m experiments.run_matrix --quick --exp E3 --seeds 0 --jobs 2
"""),
        md("""
## 1. E1: líneas base (evaluación, sin entrenar)
Tiempo fijo, actuado y max-pressure en `reforma_pico`, `reforma_mediodia`, `reforma_pico_x13` y `cruce_pico`, con las 10 `EVAL_SEEDS`. Es **un solo proceso** (120 episodios); en la Mac tardó unos 6 min. Salida: `runs/E1/baselines/eval.csv`.
"""),
        code("""
QUICK = False #@param {type:"boolean"}
flags = "--quick" if QUICK else ""
!python -m experiments.run_matrix --exp E1 {flags}
sync_up()
""", form=True),
        md("## 2. E2: Q-Learning y Dyna-Q (cruce)\n¿Cuánto ayuda planificar? 4 configs (`q_learning`, `dyna_q_n5`, `dyna_q_n10`, `dyna_q_n50`) x 5 semillas, 200 episodios en `cruce_pico` (evaluación también en `cruce_mediodia`). **1.2 a 1.7 h** en Colab."),
        train_cell("E2"),
        md("## 3. E3: ablación de DQN (cruce)\n`dqn_vanilla`, `dqn_double`, `dqn_double_dueling` y `dqn_double_dueling_per` x 5 semillas, 200 episodios. **1.4 a 2 h**. Si el tiempo apremia, baja `SEEDS` a `0 1 2` y completa después con `3 4`."),
        train_cell("E3"),
        md("## 4. E4: DQN vs PPO (cruce)\n¿Value-based o policy-based? `dqn_best` y `ppo` x 5 semillas, mismo presupuesto de pasos de entorno. **0.7 a 1 h**."),
        train_cell("E4"),
        md("## 5. E5: IDQN vs QMIX vs MAPPO (corredor)\nEl corredor `reforma_pico` con 5 semáforos: cada episodio es unas 4 veces más lento que en el cruce. 15 corridas, **3.6 a 5.5 h**. Es el bloque más caro: parte con `SEEDS = 0` para medir el tiempo real y completa después."),
        train_cell("E5"),
        md("## 6. E6: con y sin comunicación (corredor)\n`idqn_neighbor_obs` (IDQN con las colas de los vecinos) y `comm` (mensajes aprendidos), mismo presupuesto que E5. 10 corridas, **2.5 a 3.7 h**."),
        train_cell("E6"),
        md("## 7. E8: variantes con equidad (corredor)\n`qmix_fair` y `comm_fair` usan la recompensa `diff-waiting-time-pending-fair` (penaliza la espera máxima por aproximación, `fair_lambda = 0.5`) con el mismo presupuesto e hiperparámetros que `qmix` (E5) y `comm` (E6). 10 corridas, **2.5 a 3.7 h**. Al final `run_matrix` también ejecuta la recolección de E8 (fase 4); se repite en la celda 8 cuando ya existe E7."),
        train_cell("E8"),
        md("""
## 8. E7: robustez y recolección de E8
De cada familia (`dqn` de E3, `ppo` de E4, `mappo` de E5, `comm` de E6) E7 toma la corrida con mejor puntaje de **validación** (`selection.csv`; no mira `EVAL_SEEDS`) y la evalúa, junto a las 3 líneas base, en mediodía, pico +30 % y pico con un incidente en `NB_C12_C10` (900 a 2100 s). Es **un solo proceso** (0.3 a 1 h). Después se recalcula `runs/E8/fairness.csv` con los `eval.csv` de todo.

E7 y E8 solo se repiten solos si cambió algo de esta misma llamada. Si volviste a entrenar E3 a E6 después de haber corrido E7, marca `RECALCULAR` (borra sus marcas `DONE`).
"""),
        code("""
JOBS = 2 #@param {type:"integer"}
RECALCULAR = False #@param {type:"boolean"}
if RECALCULAR:
    !rm -f runs/E7/DONE runs/E8/DONE
!python -m experiments.run_matrix --exp E7 E8 --jobs {JOBS}
sync_up()
""", form=True),
        md("""
## A. (Opcional) Solo algunos experimentos, configs o semillas
Sirve para repartir el trabajo en varias sesiones o para semillas extra (por ejemplo `5 6 7 8 9`, que no chocan con las semillas de demanda de las 0 a 4). Escribe los experimentos en `EXPERIMENTOS` (`E2 E3`), o bien uno o más globs de YAML en `CONFIGS` (`experiments/configs/E5/mappo*.yaml`), que tienen prioridad. Con `CONFIGS` solo se entrenan configs con `algo`: E1, E7 y la recolección de E8 se lanzan con `EXPERIMENTOS`. `DRY_RUN` solo lista lo que correría.

Si mezclas estas corridas con las que ya tienes en la Mac, que no repitan la misma terna experimento/nombre/semilla (se pisarían al descomprimir). Después de agregar semillas, E7 y E8 hay que recalcularlos (celda 8 con `RECALCULAR`).
"""),
        code("""
EXPERIMENTOS = "E5" #@param {type:"string"}
CONFIGS = "" #@param {type:"string"}
SEMILLAS = "0 1 2" #@param {type:"string"}
JOBS = 2 #@param {type:"integer"}
DRY_RUN = False #@param {type:"boolean"}
FORCE = False #@param {type:"boolean"}
import shlex
args = ["python", "-m", "experiments.run_matrix", "--seeds", *SEMILLAS.split(), "--jobs", str(JOBS)]
args += ["--glob", *CONFIGS.split()] if CONFIGS.strip() else ["--exp", *EXPERIMENTOS.split()]
args += (["--dry-run"] if DRY_RUN else []) + (["--force"] if FORCE else [])
cmd = " ".join(shlex.quote(a) for a in args)
print(cmd)
get_ipython().system(cmd)
if not DRY_RUN:
    sync_up()
""", form=True),
        md("""
## B. (Opcional) E5 y E6 con más presupuesto
IDQN es el único método de E5 que no llega a la meseta con 200 episodios (`docs/ajuste_aprendizaje.md`, sección 6). Esta celda reentrena E5/E6 con `EPISODIOS` (400 por defecto) en una carpeta **aparte** (`runs_x400/`), con copias de los YAML en `/content/cfg_x400/` que solo cambian `total_episodes`. El epsilon y las demás programaciones se escalan con `total_episodes`; `every_episodes` sigue en 20, así que hay el doble de checkpoints que evaluar.

`run_matrix` no tiene `--total-episodes`, por eso se usan YAML modificados y `--glob` con `--runs-dir`. Los resultados **no se mezclan** con la matriz principal: E7, E8 y las tablas del informe siguen usando `runs/` (200 episodios). Compárala aparte con `python -m analysis.make_all --runs-dir runs_x400 --fig-dir docs/figures_x400 --table-dir analysis/results_x400` (o el cuaderno de análisis).

Costo estimado, proporcional al de la matriz de 200 episodios (no medido): E5 y E6 completos con 5 semillas son unas 11 a 17 h en Colab gratis; con 3 semillas, 7 a 10 h. Solo `idqn` con 5 semillas, 2.4 a 3.6 h. Usa `SOLO_NOMBRES` para elegir configs por su `name` (`idqn idqn_neighbor_obs qmix mappo comm`).
"""),
        code("""
EPISODIOS = 400 #@param {type:"integer"}
EXPERIMENTOS_GRANDE = "E5 E6" #@param {type:"string"}
SOLO_NOMBRES = "idqn" #@param {type:"string"}
SEMILLAS = "0 1 2 3 4" #@param {type:"string"}
JOBS = 2 #@param {type:"integer"}
import glob as _glob, shlex, yaml
CFG_DIR = f"/content/cfg_x{EPISODIOS}"
RUNS_X = f"{REPO_DIR}/runs_x{EPISODIOS}"
names = set(SOLO_NOMBRES.split())
paths = []
for exp in EXPERIMENTOS_GRANDE.split():
    for f in sorted(_glob.glob(f"{REPO_DIR}/experiments/configs/{exp}/*.yaml")):
        cfg = yaml.safe_load(open(f))
        if "algo" not in cfg or (names and cfg.get("name", cfg["algo"]) not in names):
            continue
        cfg["total_episodes"] = EPISODIOS
        out = f"{CFG_DIR}/{exp}/{os.path.basename(f)}"
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as fh:
            yaml.safe_dump(cfg, fh, sort_keys=False, allow_unicode=True)
        paths.append(out)
print(len(paths), "configs con total_episodes =", EPISODIOS)
EXTRA_SYNC[RUNS_X] = f"{DRIVE_ROOT}/runs_x{EPISODIOS}"
sync_down()
args = ["python", "-m", "experiments.run_matrix", "--glob", *paths, "--runs-dir", RUNS_X,
        "--seeds", *SEMILLAS.split(), "--jobs", str(JOBS)]
cmd = " ".join(shlex.quote(a) for a in args)
print(cmd)
if paths:
    get_ipython().system(cmd)
    sync_up()
""", form=True),
        md("## 9. Estado y tiempos\nResumen de `runs/manifest.csv` (trabajos hechos, saltados y fallidos, con su tiempo de pared) y el último episodio de las corridas en curso. Úsalo para calibrar las estimaciones de arriba. Si algo falló, el detalle está en `runs/<exp>/<nombre>/seed<k>/stdout.log`."),
        code("""
import glob, pandas as pd
m = RUNS + "/manifest.csv"
if os.path.exists(m):
    df = pd.read_csv(m)
    print(df.groupby(["exp", "status"]).size().unstack(fill_value=0))
    ok = df[df["status"] == "done"]
    print("\\nTiempo de pared por trabajo hecho (min):")
    print((ok.groupby("exp")["wall_s"].agg(["count", "mean", "max"]) / [1, 60, 60]).round(1))
    bad = df[df["status"] == "failed"]
    print("\\nFallidos:", bad[["exp", "name", "seed", "returncode"]].to_string(index=False) if len(bad) else "ninguno")
for d in sorted(glob.glob(RUNS + "/E*/*/seed*")):
    f = d + "/train_log.csv"
    if not os.path.exists(d + "/DONE") and os.path.exists(f):
        r = pd.read_csv(f).iloc[-1]
        print("en curso:", d.replace(RUNS + "/", ""), "| episodio", int(r["episode"]), "| %.0f s" % r["wall_time"])
"""),
        md("## 10. Empaquetar resultados\nCrea `resultados.zip` con `runs/` y las carpetas `runs_x*/` de la celda B (sin TensorBoard ni `_quick`) y lo descarga. Descomprímelo en la raíz del repo local (`unzip -o resultados.zip`) y corre `python -m analysis.make_all`. También deja una copia en Drive si está montado."),
        code("""
import glob, zipfile
sync_up()
zip_path = REPO_DIR + "/resultados.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for top in [RUNS] + sorted(glob.glob(REPO_DIR + "/runs_x*")):
        for root, dirs, files in os.walk(top):
            dirs[:] = [d for d in dirs if d not in ("tb", "_quick")]
            for name in files:
                p = os.path.join(root, name)
                z.write(p, os.path.relpath(p, REPO_DIR))
print(f"{zip_path}: {os.path.getsize(zip_path) / 1e6:.1f} MB")
from google.colab import files
files.download(zip_path)
"""),
        md("Opcional: TensorBoard sobre las corridas (los eventos están en `runs/**/tb/`, que no se sincronizan a Drive).\n"),
        code("""
%load_ext tensorboard
%tensorboard --logdir {RUNS}
"""),
    ]
    return notebook(c)


# ------------------------------------------------------------------ analysis notebook
def analysis_notebook() -> dict:
    c = [
        md("""
# Análisis de resultados

Carga las corridas (de Drive o de `resultados.zip`) y corre `python -m analysis.make_all`, que genera las figuras (`docs/figures/`) y las tablas (`analysis/results/`) de los experimentos que ya tienen datos; los que faltan se saltan. No necesita SUMO: solo lee los CSV de `runs/`. En la Mac se hace igual: descomprime el zip en la raíz del repo y corre `python -m analysis.make_all`.

La demora total (`total_delay`) y el backlog van junto a la espera media en todas las tablas y figuras.
"""),
        code(CLONE_CELL, form=True),
        code("""
!pip install -q numpy pandas scipy matplotlib pyyaml
os.environ["PYTHONPATH"] = REPO_DIR + os.pathsep + os.environ.get("PYTHONPATH", "")
"""),
        md("## Cargar las corridas\nElige la fuente: **drive** (la misma carpeta que usó el cuaderno de entrenamiento) o **zip** (sube `resultados.zip` con el panel de archivos o `files.upload()`). `RUNS_NAME` es la carpeta dentro del repo: `runs` para la matriz principal o `runs_x400` para la extensión de la celda B; en ese caso las figuras y tablas van a carpetas con ese sufijo, para no pisar las principales."),
        code("""
SOURCE = "drive" #@param ["drive", "zip"]
RUNS_NAME = "runs" #@param {type:"string"}
DRIVE_ROOT = "/content/drive/MyDrive/ProyectoFinalAR" #@param {type:"string"}
ZIP_PATH = "/content/resultados.zip" #@param {type:"string"}
FIG_DIR = "docs/figures" if RUNS_NAME == "runs" else f"docs/figures_{RUNS_NAME}"
TABLE_DIR = "analysis/results" if RUNS_NAME == "runs" else f"analysis/results_{RUNS_NAME}"
if SOURCE == "drive":
    from google.colab import drive
    drive.mount("/content/drive")
    !mkdir -p {RUNS_NAME} && rsync -a --exclude 'tb/' {DRIVE_ROOT}/{RUNS_NAME}/ {RUNS_NAME}/
else:
    if not os.path.exists(ZIP_PATH):
        from google.colab import files
        up = files.upload(); ZIP_PATH = "/content/" + next(iter(up))
    !unzip -oq {ZIP_PATH} -d .
""", form=True),
        md("## Qué hay\nCorridas terminadas por experimento (marca `DONE`) y trabajos fallidos del manifiesto."),
        code("""
import glob, pandas as pd
done = sorted(glob.glob(f"{RUNS_NAME}/E*/**/DONE", recursive=True))
print(pd.Series([p.split("/")[1] for p in done]).value_counts().sort_index().to_string() if done else "sin corridas")
m = f"{RUNS_NAME}/manifest.csv"
if os.path.exists(m):
    df = pd.read_csv(m)
    print("fallidos:", df[df["status"] == "failed"][["exp", "name", "seed"]].values.tolist() or "ninguno")
"""),
        md("## Generar figuras y tablas"),
        code("""
!python -m analysis.make_all --runs-dir {RUNS_NAME} --fig-dir {FIG_DIR} --table-dir {TABLE_DIR}
"""),
        md("## Ver las figuras"),
        code("""
from IPython.display import Image, display
for p in sorted(glob.glob(f"{FIG_DIR}/*.png")):
    print(p); display(Image(p))
"""),
        md("## Ver las tablas (Markdown)"),
        code("""
from IPython.display import Markdown, display
for p in sorted(glob.glob(f"{TABLE_DIR}/*.md")):
    display(Markdown(open(p).read()))
"""),
        md("## Descargar figuras y tablas\nCopia el contenido a `docs/figures/` y `analysis/results/` del repo local."),
        code("""
!zip -qr analisis.zip {FIG_DIR} {TABLE_DIR}
from google.colab import files
files.download("analisis.zip")
"""),
    ]
    return notebook(c)


def main() -> None:
    NB_DIR.mkdir(exist_ok=True)
    for name, nb in (("colab_train.ipynb", train_notebook()), ("colab_analysis.ipynb", analysis_notebook())):
        (NB_DIR / name).write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n")
        print("wrote", NB_DIR / name)


if __name__ == "__main__":
    main()
