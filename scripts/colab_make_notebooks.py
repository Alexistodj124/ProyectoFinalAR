"""Regenerates notebooks/colab_train.ipynb and notebooks/colab_analysis.ipynb (plain json, no nbformat needed).

    python scripts/colab_make_notebooks.py
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


def notebook(cells: list[dict], gpu: bool) -> dict:
    return {"cells": cells, "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"colab": {"provenance": [], "gpuType": "T4" if gpu else None},
                         "accelerator": "GPU" if gpu else "None",
                         "kernelspec": {"display_name": "Python 3", "name": "python3"},
                         "language_info": {"name": "python"}}}


EXP_CELL = '''
SEEDS = "0 1 2 3 4" #@param {{type:"string"}}
JOBS = 2 #@param {{type:"integer"}}
QUICK = False #@param {{type:"boolean"}}
# Los experimentos terminados (marca DONE) se saltan solos: puedes volver a correr la celda.
flags = "--quick" if QUICK else ""
!python -m experiments.run_matrix --exp {exp} --seeds {{SEEDS}} --jobs {{JOBS}} {{flags}}
sync_up()
'''


def train_notebook() -> dict:
    c = [
        md("""
# Entrenamiento en Colab: semáforos inteligentes en Av. La Reforma

Este cuaderno corre la matriz de experimentos E1 a E7 (PLAN §8.2) en Google Colab. Cada celda de experimento es independiente y se puede relanzar: `run_matrix` salta las corridas que ya tienen su marca `DONE`.

**Orden recomendado:** 0 (entorno) -> 1 (E1) -> 2 (E2) -> ... -> 7 (E7) -> 8 (empaquetar). E7 y E8 leen los resultados de E1 a E6.

**Tiempos aproximados (estimaciones: calibrar con `QUICK` y las primeras corridas reales).** Dependen de la velocidad de SUMO (1 hora simulada ~ 20 a 60 s de reloj con libsumo) y del número de CPUs (Colab gratis: 2). Una GPU ayuda poco: la simulación es el cuello de botella, no la red neuronal.
"""),
        md("## 0. Entorno\n### 0.1 GPU o CPU\nPuedes usar un runtime solo de CPU. Si hay GPU, el código la usa sola (`torch.cuda.is_available()`)."),
        code("""
import os, subprocess, sys
print(sys.version)
print(subprocess.run("nvidia-smi -L || echo 'sin GPU (CPU)'", shell=True, capture_output=True, text=True).stdout)
print("CPUs:", os.cpu_count())
"""),
        md("### 0.2 Google Drive (opcional pero recomendado)\nLas sesiones de Colab mueren. Montamos Drive para guardar `runs/` cada cierto tiempo y poder reanudar. Pon `USE_DRIVE = False` para trabajar solo en local."),
        code("""
USE_DRIVE = True #@param {type:"boolean"}
DRIVE_DIR = "/content/drive/MyDrive/ProyectoFinalAR/runs" #@param {type:"string"}
if USE_DRIVE:
    from google.colab import drive
    drive.mount("/content/drive")
""", form=True),
        md(f"""
### 0.3 Clonar el repositorio privado
Repo: `{REPO_URL}`. Necesitas un token de GitHub con permiso de lectura:
- Opción A (recomendada): en Colab, panel de la izquierda -> llave (Secretos) -> agrega `GITHUB_TOKEN` y activa "Acceso desde el cuaderno".
- Opción B: se pide con `getpass` (no se imprime).

El token no se guarda en `.git/config`. `BRANCH` es la rama a entrenar (normalmente `main` una vez integradas las ramas).
"""),
        code(f"""
import getpass, os
BRANCH = "main" #@param {{type:"string"}}
try:
    from google.colab import userdata
    os.environ["GITHUB_TOKEN"] = userdata.get("GITHUB_TOKEN")
except Exception:
    os.environ["GITHUB_TOKEN"] = getpass.getpass("GITHUB_TOKEN: ")
os.environ["BRANCH"] = BRANCH
REPO_DIR = "/content/ProyectoFinalAR"
os.environ["REPO_DIR"] = REPO_DIR
if not os.path.isdir(REPO_DIR + "/.git"):
    !git clone --branch {{BRANCH}} https://$GITHUB_TOKEN@{REPO_URL.removeprefix('https://')} {{REPO_DIR}}
    !git -C {{REPO_DIR}} remote set-url origin {REPO_URL}
else:
    !git -C {{REPO_DIR}} pull --ff-only
%cd {{REPO_DIR}}
""", form=True),
        md("### 0.4 Dependencias y variables de SUMO\nInstala `requirements.txt` (SUMO viene por pip: `eclipse-sumo`, `libsumo`), fija `SUMO_HOME` y `LIBSUMO_AS_TRACI=1` (una simulación por proceso, mucho más rápido). Tarda 2 a 4 minutos la primera vez. Equivale a `scripts/colab_setup.sh`."),
        code("""
!pip install -q -r requirements.txt
import sumo
os.environ["SUMO_HOME"] = sumo.SUMO_HOME
os.environ["LIBSUMO_AS_TRACI"] = "1"
os.environ["PYTHONPATH"] = REPO_DIR + ":" + os.environ.get("PYTHONPATH", "")
import torch
print("SUMO_HOME =", sumo.SUMO_HOME, "| torch", torch.__version__, "| cuda", torch.cuda.is_available())
"""),
        md("### 0.5 Prueba rápida (1 a 2 min)\nSi esto falla, no sigas: revisa el entorno. `--dry-run` lista lo que correría la matriz sin ejecutar nada."),
        code("""
!python -m pytest -q tests/test_smoke.py
!python -m experiments.run_matrix --dry-run
"""),
        md("### 0.6 Sincronización con Drive\n`sync_up()` copia `runs/` a Drive (sin los eventos de TensorBoard). Se llama al final de cada experimento y además cada 5 minutos en un hilo de fondo. `sync_down()` restaura todo después de reiniciar el runtime."),
        code("""
import threading, time
RUNS = REPO_DIR + "/runs"
def sync_up():
    if USE_DRIVE:
        !rsync -a --exclude 'tb/' {RUNS}/ {DRIVE_DIR}/
def sync_down():
    if USE_DRIVE and os.path.isdir(DRIVE_DIR):
        !mkdir -p {RUNS} && rsync -a {DRIVE_DIR}/ {RUNS}/
def _loop():
    while True:
        time.sleep(300)
        try: sync_up()
        except Exception as e: print("sync error", e)
sync_down()  # reanuda: lo que ya estaba en Drive se marca como hecho
if USE_DRIVE and not any(t.name == "drive-sync" for t in threading.enumerate()):
    threading.Thread(target=_loop, daemon=True, name="drive-sync").start()
"""),
        md("""
## 1. E1: líneas base (evaluación, sin entrenar)
Tiempo fijo, actuado y max-pressure en todos los escenarios, 10 semillas de evaluación. **~10 a 30 min** (3 métodos x escenarios x 10 episodios de 1 h simulada). Salida: `runs/E1/baselines/eval.csv`.
"""),
        code(EXP_CELL.format(exp="E1"), form=True),
        md("## 2. E2: Q-Learning vs Dyna-Q (cruce)\n¿Cuánto ayuda planificar? Métodos tabulares, baratos. **~0.5 a 1.5 h** con 5 semillas y 2 procesos. Mira el presupuesto en `experiments/configs/README.md`."),
        code(EXP_CELL.format(exp="E2"), form=True),
        md("## 3. E3: ablación de DQN (cruce)\nDQN base, Double, Dueling, PER y combinaciones. **~3 a 8 h** (varias variantes x 5 semillas). Si el tiempo apremia, baja `SEEDS` a `0 1 2` y repite luego con las demás."),
        code(EXP_CELL.format(exp="E3"), form=True),
        md("## 4. E4: DQN vs PPO (cruce)\n¿Value-based o policy-based? **~1 a 3 h** (reutiliza el DQN de E3 como comparación)."),
        code(EXP_CELL.format(exp="E4"), form=True),
        md("## 5. E5: IDQN vs QMIX vs MAPPO (corredor)\nEl corredor completo con 4 a 5 semáforos: cada episodio es más lento y MAPPO/QMIX más pesados. **~4 a 10 h**. Es el experimento más caro: conviene lanzarlo primero con `QUICK` para medir la velocidad."),
        code(EXP_CELL.format(exp="E5"), form=True),
        md("## 6. E6: con y sin comunicación (corredor)\nIDQN con observación de vecinos y mensajes aprendidos (`comm`) frente a la versión sin comunicación. **~3 a 6 h**."),
        code(EXP_CELL.format(exp="E6"), form=True),
        md("""
## 7. E7: robustez y E8: equidad
E7 toma el mejor agente de cada familia (la mejor semilla por espera media en su `eval.csv`) y lo evalúa junto a las 3 líneas base en mediodía, pico +30 % y pico con incidente. **~30 a 90 min**. E8 solo reúne los CSV de evaluación (segundos). Antes de E7, si ya existe la red de Reforma, revisa `experiments/configs/E7/robustness.yaml` (campo `incident.edge`; con `null` se elige la primera arista del corredor).
"""),
        code(EXP_CELL.format(exp="E7").replace("--exp E7", "--exp E7 E8"), form=True),
        md("## 8. Empaquetar resultados\nCrea `resultados.zip` con `runs/` (sin TensorBoard) y lo descarga. También deja una copia en Drive si está montado."),
        code("""
sync_up()
!cd {REPO_DIR} && zip -qr resultados.zip runs -x 'runs/*/tb/*' 'runs/*/*/*/tb/*' '*.log' && ls -lh resultados.zip
from google.colab import files
files.download(REPO_DIR + "/resultados.zip")
"""),
        md("Opcional: TensorBoard sobre las corridas.\n"),
        code("""
%load_ext tensorboard
%tensorboard --logdir {REPO_DIR}/runs
"""),
    ]
    return notebook(c, gpu=True)


def analysis_notebook() -> dict:
    c = [
        md("""
# Análisis de resultados

Carga las corridas (de Drive o de `resultados.zip`), y corre `analysis.make_all`, que genera todas las figuras (`docs/figures/`) y tablas (`analysis/results/`) de los experimentos que ya tienen datos. Los que faltan se saltan.
"""),
        code(f"""
import getpass, os
try:
    from google.colab import userdata
    os.environ["GITHUB_TOKEN"] = userdata.get("GITHUB_TOKEN")
except Exception:
    os.environ["GITHUB_TOKEN"] = getpass.getpass("GITHUB_TOKEN: ")
REPO_DIR = "/content/ProyectoFinalAR"
BRANCH = "main"
if not os.path.isdir(REPO_DIR + "/.git"):
    !git clone --branch {{BRANCH}} https://$GITHUB_TOKEN@{REPO_URL.removeprefix('https://')} {{REPO_DIR}}
    !git -C {{REPO_DIR}} remote set-url origin {REPO_URL}
%cd {{REPO_DIR}}
!pip install -q numpy pandas scipy matplotlib pyyaml
os.environ["PYTHONPATH"] = REPO_DIR
"""),
        md("## Cargar las corridas\nElige la fuente: **Drive** (la misma carpeta que usó el cuaderno de entrenamiento) o **zip** (sube `resultados.zip` con el panel de archivos o `files.upload()`)."),
        code("""
SOURCE = "drive" #@param ["drive", "zip"]
DRIVE_DIR = "/content/drive/MyDrive/ProyectoFinalAR/runs" #@param {type:"string"}
ZIP_PATH = "/content/resultados.zip" #@param {type:"string"}
if SOURCE == "drive":
    from google.colab import drive
    drive.mount("/content/drive")
    !mkdir -p runs && rsync -a --exclude 'tb/' {DRIVE_DIR}/ runs/
else:
    if not os.path.exists(ZIP_PATH):
        from google.colab import files
        up = files.upload(); ZIP_PATH = "/content/" + next(iter(up))
    !unzip -oq {ZIP_PATH} -d .
!find runs -maxdepth 3 -name DONE | sort | head -50
""", form=True),
        md("## Generar figuras y tablas"),
        code("""
from analysis.make_all import make_all
made = make_all()
"""),
        md("## Ver las figuras"),
        code("""
import glob
from IPython.display import Image, display
for p in sorted(glob.glob("docs/figures/*.png")):
    print(p); display(Image(p))
"""),
        md("## Ver las tablas (Markdown)"),
        code("""
from IPython.display import Markdown, display
for p in sorted(glob.glob("analysis/results/*.md")):
    display(Markdown(open(p).read()))
"""),
        md("## Descargar figuras y tablas"),
        code("""
!zip -qr analisis.zip docs/figures analysis/results
from google.colab import files
files.download("analisis.zip")
"""),
    ]
    return notebook(c, gpu=False)


def main() -> None:
    NB_DIR.mkdir(exist_ok=True)
    for name, nb in (("colab_train.ipynb", train_notebook()), ("colab_analysis.ipynb", analysis_notebook())):
        (NB_DIR / name).write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n")
        print("wrote", NB_DIR / name)


if __name__ == "__main__":
    main()
