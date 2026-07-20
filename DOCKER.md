# Docker 部署

当前 Docker 镜像采用单容器部署：Nginx 提供 Vue 前端并代理 `/api`，FastAPI 与 Worker 在容器内部运行。容器启动时会自动执行 Alembic 数据库迁移。

## 快速启动

```bash
cp .env.example .env
# 编辑 .env，填写需要的 LLM 配置
bash docker/startup.sh start
```

访问：<http://localhost:8080>

## 常用命令

```bash
bash docker/startup.sh status
bash docker/startup.sh logs
bash docker/startup.sh restart
bash docker/startup.sh stop
```

等价的 Compose 命令：

```bash
docker compose up -d --build --wait
docker compose ps
docker compose logs -f app
docker compose down
```

生产配置默认使用宿主机 `80` 端口：

```bash
docker compose -f docker-compose.prod.yml up -d --build --wait
```

## 数据持久化

默认使用 SQLite：

```text
DATABASE_URL=sqlite+pysqlite:////app/data/prd_agent.db
```

数据保存在两个 named volume：

- `prd_data`：SQLite 数据库。
- `prd_uploads`：项目上传附件。

`docker compose down` 不会删除数据卷。只有显式执行 `docker compose down -v` 才会删除数据，请谨慎使用。

## 使用外部 MySQL

在 `.env` 中配置容器可访问的 MySQL 地址：

```dotenv
DOCKER_DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/prd_agent?charset=utf8mb4
DOCKER_TEST_DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/prd_agent_test?charset=utf8mb4
```

生产库和测试库必须是不同数据库，并且必须同时使用 SQLite 或同时使用 MySQL。修改 URL 只会切换连接，不会自动迁移已有数据。

## 修改端口

开发 Compose 默认使用 `8080`，生产 Compose 默认使用 `80`。可以通过 `.env` 覆盖：

```dotenv
APP_PORT=8088
```

## 健康检查

```bash
curl -f http://localhost:8080/health
```

成功响应说明 Nginx 和 FastAPI 代理链路都可用。容器中任一核心进程退出，入口脚本会停止其余进程并触发 Docker 重启策略。

## 管理员密码重置

```bash
docker compose exec app prd-agent reset-admin-password
```

## 镜像结构

- Node 构建阶段：安装前端依赖并生成 `web/dist`。
- Python 构建阶段：根据 `uv.lock` 安装生产依赖。
- 运行阶段：非 root 用户运行 Nginx、FastAPI 和 Worker。
- `/app/data` 与 `/app/uploads` 使用持久化卷。
