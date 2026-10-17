# Source this file:  source scripts/env.sh
# Activates the venv (default: ../.venv, shared by all worktrees) and exports SUMO_HOME.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
VENV="${VENV:-$REPO_ROOT/../.venv}"
if [ -f "$VENV/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
fi
export SUMO_HOME="$(python -c 'import sumo; print(sumo.SUMO_HOME)')"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
# Training runs: export LIBSUMO_AS_TRACI=1 (much faster, one simulation per process).
# The web demo must NOT set it, because it runs two simulations at once.
