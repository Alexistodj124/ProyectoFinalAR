#!/usr/bin/env bash
# Colab setup (Python 3.12, Linux). Usage from a notebook cell:
#   !GITHUB_TOKEN=... bash scripts/colab_setup.sh      (notebooks/colab_train.ipynb does the same in its cells 0.3 and 0.4)
# Idempotent: safe to run again after a runtime restart.
set -euo pipefail

REPO_URL="${REPO_URL:-github.com/Alexistodj124/ProyectoFinalAR.git}"
REPO_DIR="${REPO_DIR:-/content/ProyectoFinalAR}"
BRANCH="${BRANCH:-main}"

if [ ! -d "$REPO_DIR/.git" ]; then
  : "${GITHUB_TOKEN:?export GITHUB_TOKEN (Colab secrets / getpass) to clone the private repo}"
  git clone --branch "$BRANCH" "https://${GITHUB_TOKEN}@${REPO_URL}" "$REPO_DIR"
  git -C "$REPO_DIR" remote set-url origin "https://${REPO_URL}"  # do not keep the token in .git/config
elif [ -n "${GITHUB_TOKEN:-}" ]; then
  # the origin URL has no token, so the pull of the private repo needs it again (HTTP header: not stored anywhere)
  AUTH="$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 | tr -d '\n')"
  git -C "$REPO_DIR" -c "http.extraheader=AUTHORIZATION: basic $AUTH" pull --ff-only || echo "pull skipped (local changes?)"
else
  echo "GITHUB_TOKEN not set: git pull skipped"
fi
cd "$REPO_DIR"

pip install -q -r requirements.txt
export SUMO_HOME="$(python -c 'import sumo; print(sumo.SUMO_HOME)')"
echo "SUMO_HOME=$SUMO_HOME"
python - <<'PY'
import os, sys
os.environ["LIBSUMO_AS_TRACI"] = "1"
import libsumo, torch
print("python", sys.version.split()[0], "| libsumo", libsumo.__version__ if hasattr(libsumo, "__version__") else "ok",
      "| torch", torch.__version__, "| cuda", torch.cuda.is_available(), "| cpus", os.cpu_count())
PY
