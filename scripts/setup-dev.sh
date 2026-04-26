#!/usr/bin/env bash
set -euo pipefail

echo "[wosb] Setup starting..."

if command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN="python3.12"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "[wosb] Python not found. Install Python 3.12 and retry." >&2
  exit 1
fi

if ! "$PYTHON_BIN" --version | grep -Eq '^Python 3\.12\.'; then
  echo "[wosb] Python 3.12 is required. Found: $("${PYTHON_BIN}" --version 2>&1)" >&2
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  echo "[wosb] Creating virtual environment..."
  "$PYTHON_BIN" -m venv .venv
fi

echo "[wosb] Activating virtual environment..."
source .venv/bin/activate

echo "[wosb] Upgrading pip and installing dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f ".env" ]]; then
  echo "[wosb] WARNING: .env is missing. Copy .env.example to .env and fill Discord values." >&2
fi

echo "[wosb] Starting app at http://127.0.0.1:8000"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
