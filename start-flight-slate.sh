#!/usr/bin/env bash

cd /home/remote/flight-slate

# Try to update code, but never fail startup if offline or pull fails.
if [ -d .git ]; then
  if timeout 20s env GIT_TERMINAL_PROMPT=0 git pull --ff-only; then
    echo "[flight-slate] git pull ok"
  else
    echo "[flight-slate] git pull skipped (offline or pull failed)"
  fi
fi

source .venv/bin/activate
./env.flight-slate.sh
sudo -E env "PATH=$PATH" python core_ui_demo.py
