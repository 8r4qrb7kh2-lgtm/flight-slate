#!/usr/bin/env bash
set -euo pipefail

cd /home/remote/flight-slate

# Match the interactive startup flow exactly.
source .venv/bin/activate
source ./env.flight-slate.sh

# Try to update code, but never fail startup if offline or pull fails.
if [ -d .git ]; then
  if timeout 20s env GIT_TERMINAL_PROMPT=0 git pull --ff-only; then
    echo "[flight-slate] git pull ok"
  else
    echo "[flight-slate] git pull skipped (offline or pull failed)"
  fi
fi

if [ "${EUID}" -eq 0 ]; then
  exec env "PATH=${PATH}" python core_ui_demo.py
else
  exec sudo -E env "PATH=${PATH}" python core_ui_demo.py
fi
