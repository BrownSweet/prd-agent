# syntax=docker/dockerfile:1

FROM node:22.12-alpine AS frontend-builder

WORKDIR /build/web
RUN npm install -g pnpm@9.15.9
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build


FROM python:3.12-slim AS backend-builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim AS production

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    API_HOST=127.0.0.1 \
    API_PORT=8000 \
    PROJECT_ROOT=/app \
    DATABASE_URL=sqlite+pysqlite:////app/data/prd_agent.db \
    TEST_DATABASE_URL=sqlite+pysqlite:////app/data/prd_agent_test.db \
    UPLOAD_DIR=/app/uploads \
    CREWAI_DISABLE_TELEMETRY=true \
    CREWAI_TRACING_ENABLED=false

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl nginx \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 prd \
    && mkdir -p /app/data /app/uploads /tmp/nginx \
    && chown -R prd:prd /app /tmp/nginx

COPY --from=backend-builder --chown=prd:prd /app/.venv /app/.venv
COPY --chown=prd:prd alembic/ /app/alembic/
COPY --chown=prd:prd alembic.ini /app/alembic.ini
COPY --from=frontend-builder --chown=prd:prd /build/web/dist /app/web/dist
COPY docker/nginx.deploy.conf /etc/nginx/nginx.conf
COPY docker/entrypoint.sh /usr/local/bin/prd-agent-entrypoint

RUN chmod +x /usr/local/bin/prd-agent-entrypoint

USER prd

EXPOSE 8080
VOLUME ["/app/data", "/app/uploads"]

HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=5 \
    CMD curl --fail --silent http://127.0.0.1:8080/health >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/prd-agent-entrypoint"]
