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

if [[ ! -f ".env" ]]; then
  echo "[wosb] .env is missing. Create it from .env.example before deploy." >&2
  exit 1
fi

source .venv/bin/activate

git fetch origin
git pull --ff-only origin main
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "[wosb] Running local-config sanity checks..."

# Check that all keys from .env.example exist in .env (gitignored file drift protection).
missing_keys=()
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  [[ -z "$key" ]] && continue
  if ! grep -Eq "^${key}=" ".env"; then
    missing_keys+=("$key")
  fi
done < ".env.example"

if [[ ${#missing_keys[@]} -gt 0 ]]; then
  echo "[wosb] WARNING: .env is missing keys defined in .env.example:" >&2
  for k in "${missing_keys[@]}"; do
    echo "  - $k" >&2
  done
  echo "[wosb] Add missing keys to .env, then rerun deploy." >&2
  exit 1
fi

# If SITE_BACKGROUND_IMAGE points to a static file, verify file exists.
bg_line="$(grep -E '^SITE_BACKGROUND_IMAGE=' .env || true)"
if [[ -n "$bg_line" ]]; then
  bg_path="${bg_line#SITE_BACKGROUND_IMAGE=}"
  bg_path="${bg_path%\"}"
  bg_path="${bg_path#\"}"
  if [[ -n "$bg_path" ]]; then
    if [[ "$bg_path" != /static/* ]]; then
      echo "[wosb] WARNING: SITE_BACKGROUND_IMAGE must start with /static/ (current: $bg_path)" >&2
      exit 1
    fi
    rel="${bg_path#/}"
    if [[ ! -f "$rel" ]]; then
      echo "[wosb] WARNING: SITE_BACKGROUND_IMAGE file not found: $rel" >&2
      exit 1
    fi
  fi
fi

echo "[wosb] Deploy update completed. Run the live deploy script next:"
echo "[wosb]   bash ./scripts/deploy-live.sh"
