#!/usr/bin/env bash
# Sync runs/ with Google Drive. Usage: colab_sync.sh up|down [DRIVE_DIR]
#   up   : local runs/  -> Drive  (call periodically while training)
#   down : Drive        -> local runs/  (restore after a runtime restart; DONE markers make run_matrix resume)
set -euo pipefail
DIR="${2:-/content/drive/MyDrive/ProyectoFinalAR/runs}"
LOCAL="${REPO_DIR:-/content/ProyectoFinalAR}/runs"
mkdir -p "$DIR" "$LOCAL"
case "${1:?up|down}" in
  up)   rsync -a --exclude 'tb/' "$LOCAL"/ "$DIR"/ ;;   # tensorboard events are big and not needed for the report
  down) rsync -a "$DIR"/ "$LOCAL"/ ;;
esac
