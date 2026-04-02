#!/usr/bin/env bash
set -euo pipefail

cd /home/remote/flight-slate

# Auto-export variables from env file.
set -a
. ./env.flight-slate.sh
set +a

# Try to update code, but never fail startup if offline or pull fails.
if [ -d .git ]; then
  if timeout 20s env GIT_TERMINAL_PROMPT=0 git pull --ff-only; then
    echo "[flight-slate] git pull ok"
  else
    echo "[flight-slate] git pull skipped (offline or pull failed)"
  fi
fi

exec /home/remote/flight-slate/.venv/bin/python /home/remote/flight-slate/core_ui_demo.py
