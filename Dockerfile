# =====================================================
# 多阶段构建：Node 前端 + Python 后端
# =====================================================

# ============================================
# 阶段 1: 构建 Vue 前端
# ============================================
FROM node:22.12-alpine AS frontend-builder

WORKDIR /app/web

# 复制前端代码
COPY web/package.json web/pnpm-lock.yaml ./

# 安装 pnpm 和依赖
RUN npm install -g pnpm && \
    pnpm install --frozen-lockfile

# 复制源代码
COPY web/src ./src
COPY web/index.html ./
COPY web/tsconfig* ./
COPY web/vite.config.ts ./

# 构建前端
RUN pnpm build

# ============================================
# 阶段 2: Python 运行环境
# ============================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    mysql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ============================================
# 阶段 3: Python 开发环境（可选，用于开发）
# ============================================
FROM runtime AS development

# 安装 uv
RUN pip install uv --no-cache-dir

WORKDIR /app

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装所有依赖（包括开发依赖）
RUN uv sync --extra dev

# 复制源代码
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini .

# 暴露端口
EXPOSE 8000 5173

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["/bin/bash"]

# ============================================
# 阶段 4: Python 生产环境
# ============================================
FROM runtime AS production

# 安装 uv
RUN pip install uv --no-cache-dir

WORKDIR /app

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装生产依赖（不包括开发依赖）
RUN uv sync --no-dev && \
    rm -rf /root/.cache

# 复制源代码
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini .

# 从前端构建阶段复制静态文件
COPY --from=frontend-builder /app/web/dist ./web/dist

# 创建非 root 用户运行应用
RUN mkdir -p /app/uploads && \
    useradd -m -u 1000 prd && \
    chown -R prd:prd /app

USER prd

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 入口点
ENTRYPOINT ["uv", "run"]
CMD ["prd-agent", "api"]

# ============================================
# 元数据
# ============================================
LABEL maintainer="PRD Agent Team"
LABEL description="CrewAI-based requirement workbench"
LABEL version="0.1.0"
