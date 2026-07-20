#!/usr/bin/env bash

set -Eeuo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command_name="${1:-start}"

cd "$project_dir"

if ! docker info >/dev/null 2>&1; then
    echo "错误：Docker daemon 未启动或当前用户无权访问。" >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "错误：需要 Docker Compose v2（docker compose）。" >&2
    exit 1
fi

case "$command_name" in
    start|up)
        docker compose up --detach --build --wait --wait-timeout 300
        echo "部署完成：http://localhost:${APP_PORT:-8080}"
        ;;
    stop|down)
        docker compose down
        ;;
    restart)
        docker compose down
        docker compose up --detach --build --wait --wait-timeout 300
        ;;
    status|ps)
        docker compose ps
        ;;
    logs)
        docker compose logs --follow app
        ;;
    *)
        echo "用法：bash docker/startup.sh [start|stop|restart|status|logs]" >&2
        exit 1
        ;;
esac
