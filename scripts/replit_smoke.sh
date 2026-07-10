#!/usr/bin/env bash
# Boots the single-process Replit server on a scratch port and checks the
# health endpoint, the product API facade, SPA fallback routes, and that
# unknown static assets correctly 404.
set -u

host=127.0.0.1
port="${PORT:-8991}"

PYTHONPATH=src python3 -m reliefqueue.product_api serve --host "$host" --port "$port" &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT INT TERM

ok=0
for _ in $(seq 1 30); do
  if curl -sf "http://$host:$port/healthz" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 0.5
done
if [ "$ok" != "1" ]; then
  echo "replit-smoke FAIL: /healthz never became ready"
  exit 1
fi

curl -sf "http://$host:$port/healthz" | grep -q '"status": "ok"' || {
  echo "replit-smoke FAIL: unexpected /healthz body"
  exit 1
}
curl -sf "http://$host:$port/api/product/command/overview" >/dev/null || {
  echo "replit-smoke FAIL: /api/product/command/overview unreachable"
  exit 1
}
curl -sf "http://$host:$port/dashboard" | grep -qi '<div id="root">' || {
  echo "replit-smoke FAIL: /dashboard did not return the SPA shell"
  exit 1
}
curl -sf "http://$host:$port/field/my-cases?worker_id=worker-alpha-boat" | grep -qi '<div id="root">' || {
  echo "replit-smoke FAIL: /field/my-cases did not return the SPA shell"
  exit 1
}
curl -sf "http://$host:$port/local-coordinator" | grep -qi '<div id="root">' || {
  echo "replit-smoke FAIL: /local-coordinator did not return the SPA shell"
  exit 1
}
status=$(curl -s -o /dev/null -w '%{http_code}' "http://$host:$port/no-such-asset.js")
if [ "$status" != "404" ]; then
  echo "replit-smoke FAIL: unknown asset returned $status, expected 404"
  exit 1
fi

echo "replit-smoke PASS"
