#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8642/continuity/}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SMOKE_SCRIPT="${SCRIPT_DIR}/panel_browser_smoke.mjs"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is required to run continuity panel browser smoke." >&2
  exit 1
fi

exec node "${SMOKE_SCRIPT}" "${BASE_URL}"
