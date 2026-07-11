#!/usr/bin/env bash
set -Eeuo pipefail

HOST="0.0.0.0"
PORT="5000"

echo "RELIEFQUEUE_DEPLOY_START"
echo "cwd=$PWD"
echo "host=$HOST"
echo "port=$PORT"
echo "python=$(python3 --version 2>&1)"
echo "dashboard_dist_present=$([[ -f dashboard/dist/index.html ]] && echo YES || echo NO)"
echo "database_url_present=$([[ -n "${DATABASE_URL:-}" ]] && echo YES || echo NO)"

if [[ ! -f dashboard/dist/index.html ]]; then
  echo "RELIEFQUEUE_DEPLOY_FAIL reason=dashboard_dist_missing"
  exit 1
fi

exec env \
  PYTHONPATH=src \
  python3 -u -m reliefqueue.product_api serve \
    --host "$HOST" \
    --port "$PORT"
