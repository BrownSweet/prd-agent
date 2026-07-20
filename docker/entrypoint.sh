#!/usr/bin/env bash

set -Eeuo pipefail

api_pid=""
worker_pid=""
nginx_pid=""

shutdown() {
    trap - EXIT INT TERM
    for pid in "$nginx_pid" "$worker_pid" "$api_pid"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
}

trap shutdown EXIT INT TERM

mkdir -p /app/data /app/uploads /tmp/nginx/{client_body,proxy,fastcgi,uwsgi,scgi}

echo "[startup] upgrading database"
prd-agent db-upgrade

echo "[startup] starting FastAPI on 127.0.0.1:8000"
prd-agent api &
api_pid=$!

api_ready=false
for _ in {1..60}; do
    if ! kill -0 "$api_pid" 2>/dev/null; then
        echo "[startup] FastAPI exited before becoming ready" >&2
        exit 1
    fi
    if curl --fail --silent http://127.0.0.1:8000/api/v1/health >/dev/null; then
        api_ready=true
        break
    fi
    sleep 0.5
done

if [[ "$api_ready" != "true" ]]; then
    echo "[startup] FastAPI did not become ready within 30 seconds" >&2
    exit 1
fi

echo "[startup] starting workflow worker"
prd-agent worker &
worker_pid=$!

echo "[startup] starting Nginx on 0.0.0.0:8080"
nginx -g "daemon off;" &
nginx_pid=$!

wait -n "$api_pid" "$worker_pid" "$nginx_pid"
status=$?
echo "[startup] a managed process exited with status $status" >&2
exit "$status"
