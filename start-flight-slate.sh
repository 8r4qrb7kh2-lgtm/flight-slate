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
# Hardware config (tracked).
source ./env.flight-slate.sh
# API keys (untracked, gitignored — see env.flight-slate.local.sh.example).
# Optional so the script doesn't fail if the file is absent.
[ -f ./env.flight-slate.local.sh ] && source ./env.flight-slate.local.sh
sudo -E env "PATH=$PATH" python flight_display.py
