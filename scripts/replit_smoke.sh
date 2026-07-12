#!/usr/bin/env bash
set -Eeuo pipefail

host="${RELIEFQUEUE_REPLIT_SMOKE_HOST:-127.0.0.1}"
port="${RELIEFQUEUE_REPLIT_SMOKE_PORT:-8991}"
base_url="http://$host:$port"
server_log="$(mktemp /tmp/reliefqueue-replit-smoke-server-XXXXXX.log)"
server_pid=""

cleanup() {
  if [[ -n "$server_pid" ]]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  rm -f "$server_log"
}
trap cleanup EXIT INT TERM

on_error() {
  status=$?
  echo "replit-smoke FAIL"
  echo "exit_status=$status"
  echo "failing_line=${BASH_LINENO[0]:-unknown}"
  echo "failing_command=${BASH_COMMAND:-unknown}"
  tail -80 "$server_log" 2>/dev/null || true
  exit "$status"
}
trap on_error ERR

if curl -fsS "$base_url/api/health" >/dev/null 2>&1; then
  echo "replit-smoke FAIL: $base_url is already in use"
  exit 1
fi

PYTHONPATH=src python3 -m reliefqueue.product_api serve --host "$host" --port "$port" >"$server_log" 2>&1 &
server_pid=$!

ready=0
for _ in $(seq 1 40); do
  if curl -fsS "$base_url/api/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  kill -0 "$server_pid" 2>/dev/null
  sleep 0.25
done
[[ "$ready" == "1" ]]

curl -fsS "$base_url/api/health" |
  python3 -c 'import json,sys; assert json.load(sys.stdin) == {"status":"ok"}'
curl -fsS "$base_url/api/product/command/overview" |
  python3 -c 'import json,sys; data=json.load(sys.stdin); assert "summary" in data'

spa_routes=(
  "/"
  "/dashboard?source=latest"
  "/dashboard/assignments"
  "/dashboard/amd-impact"
  "/field/my-cases?worker_id=worker-alpha-boat"
  "/field/cases/RQ-1042"
  "/field/outbox"
  "/local-coordinator?source=latest"
  "/internal/classic-dashboard?source=latest"
)
for route in "${spa_routes[@]}"; do
  curl -fsS "$base_url$route" | grep -qi '<div id="root">'
done

mutation_key="replit-smoke-drill-$$-$(date +%s)"
mutation_payload="$(
  python3 - "$mutation_key" <<'PY'
import json
import sys

print(json.dumps({"idempotency_key": sys.argv[1]}))
PY
)"
mutation_response="$(mktemp /tmp/reliefqueue-replit-smoke-mutation-XXXXXX.json)"
mutation_status="$(
  curl -sS     -o "$mutation_response"     -w '%{http_code}'     -H 'Content-Type: application/json'     --data-binary "$mutation_payload"     "$base_url/api/product/command/drill"
)"
if [[ "$mutation_status" != "200" ]]; then
  echo "replit-smoke FAIL: deterministic mutation returned HTTP $mutation_status"
  cat "$mutation_response" || true
  rm -f "$mutation_response"
  exit 1
fi
python3 - "$mutation_response" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert data.get("status") == "recorded", data
assert (data.get("result") or {}).get("deterministic") is True, data
PY
rm -f "$mutation_response"

[[ "$(curl -sS -o /dev/null -w '%{http_code}' "$base_url/no-such-asset.js")" == "404" ]]
[[ "$(curl -sS -o /dev/null -w '%{http_code}' "$base_url/no-such-route")" == "404" ]]

echo "replit-smoke PASS routes=${#spa_routes[@]} api_reads=1 mutations=1 unknown_404s=2"
