#!/usr/bin/env bash
set -euo pipefail

echo "[wosb] Starting production runtime..."

if [[ ! -d ".venv" ]]; then
  echo "[wosb] .venv is missing. Run: bash ./scripts/setup-dev.sh" >&2
  exit 1
fi

if [[ ! -f ".env" ]]; then
  echo "[wosb] .env is missing. Copy .env.example to .env and fill values." >&2
  exit 1
fi

source .venv/bin/activate

# Production mode: no --reload. Bind to localhost so a reverse proxy can front it.
exec uvicorn app.main:app --host 127.0.0.1 --port 8000
