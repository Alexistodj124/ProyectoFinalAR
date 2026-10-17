#!/usr/bin/env bash
# Creates the Python environment and installs SUMO + RL dependencies.
#   bash scripts/setup_env.sh            # venv in ../.venv (shared by git worktrees)
#   VENV=.venv bash scripts/setup_env.sh # venv inside the repo
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${VENV:-$REPO_ROOT/../.venv}"
if command -v uv >/dev/null 2>&1; then
  [ -d "$VENV" ] || uv venv -p 3.11 "$VENV"
  VIRTUAL_ENV="$VENV" uv pip install -r "$REPO_ROOT/requirements.txt"
else
  [ -d "$VENV" ] || python3 -m venv "$VENV"
  "$VENV/bin/pip" install -r "$REPO_ROOT/requirements.txt"
fi
"$VENV/bin/python" -c "import sumo, sumo_rl; print('SUMO_HOME =', sumo.SUMO_HOME)"
