#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d dashboard/node_modules ]; then
  npm --prefix dashboard ci
fi

node -e "require('playwright')" >/dev/null 2>&1 || npm --prefix dashboard ci
npx --prefix dashboard playwright install --with-deps chromium
if [ ! -f reports/latest/summary.json ]; then
  AI_MODE="${AI_MODE:-mock}" make run-demo-local
fi
DASHBOARD_DATA_SOURCE="${DASHBOARD_DATA_SOURCE:-latest}" npm --prefix dashboard run prepare-public-data
node dashboard/scripts/websiteReadinessCheck.mjs
