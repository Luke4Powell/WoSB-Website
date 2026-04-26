#!/usr/bin/env bash
set -euo pipefail

echo "[wosb] Deploy update starting..."

if [[ ! -d ".git" ]]; then
  echo "[wosb] Must run from repo root." >&2
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  echo "[wosb] .venv is missing. Run initial setup first." >&2
  exit 1
fi

source .venv/bin/activate

git fetch origin
git pull --ff-only origin main
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "[wosb] Restart service: sudo systemctl restart wosb"
echo "[wosb] Check status:   sudo systemctl status wosb --no-pager"
