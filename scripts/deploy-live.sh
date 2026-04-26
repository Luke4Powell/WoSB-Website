#!/usr/bin/env bash
set -euo pipefail

echo "[wosb] Live deploy starting..."

if [[ ! -d ".git" ]]; then
  echo "[wosb] Must run from repo root." >&2
  exit 1
fi

bash ./scripts/deploy-update.sh

echo "[wosb] Restarting application service..."
systemctl restart wosb
systemctl status wosb --no-pager

echo "[wosb] Reloading nginx..."
nginx -t
systemctl reload nginx

echo "[wosb] Cloudflared status:"
systemctl status cloudflared --no-pager

echo "[wosb] Done."
