# PRD Agent

基于 CrewAI Flow 的需求工作台，将模糊需求依次推进为结构化需求、逻辑校验、
PRD、独立终审和 SDD。提供 Vue Web 管理台与原有 CLI；业务状态由 MySQL 8.0+
和 Python 门禁控制，LLM 输出不能直接改变阶段。

## 启动

先创建两个独立数据库：

```sql
CREATE DATABASE prd_agent
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE prd_agent_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

配置环境：

```bash
cp .env.example .env
uv sync --extra dev
```

数据库连接可以手动写入 `.env`，也可以先启动 Web 管理台后在
`/setup/database` 安装向导中填写并保存。

手动配置示例：

```dotenv
DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/prd_agent?charset=utf8mb4
TEST_DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/prd_agent_test?charset=utf8mb4
```

生产库和测试库必须不同，测试数据库名称必须以 `_test` 结尾。填写完成后执行迁移：

```bash
uv run prd-agent db-upgrade
```

## Web 管理台

要求 Node.js `>=22.12`。首次安装前端依赖：

```bash
cd web
pnpm install
```

开发模式使用三个终端：

```bash
# 终端 1：FastAPI，只允许监听 localhost
uv run prd-agent api

# 终端 2：异步工作流 Worker
uv run prd-agent worker

# 终端 3：Vite 开发服务器
cd web
pnpm dev
```

浏览器访问 `http://127.0.0.1:5173`。生产模式先执行：

```bash
cd web
pnpm build
cd ..
uv run prd-agent api
uv run prd-agent worker
```

构建后 FastAPI 会直接托管 `web/dist`，访问
`http://127.0.0.1:8000`。排队任务由 MySQL 保存，刷新页面或重启 API 不会丢失；
Worker 重启时会把遗留的 `running` 任务标记为失败，等待用户手动重试。

数据库迁移完成后，首次打开管理台会进入登录页。系统没有默认账号：首次使用时
在该页面创建本机管理员，创建成功后会自动登录。之后需要使用该用户名和密码
进入工作台；登录会话有效期为 7 天。管理员密码使用 Argon2 哈希保存，浏览器
Cookie 使用 `HttpOnly` 和 `SameSite=Strict`，数据库只保存会话令牌的哈希。

如果数据库连接缺失或不可用，API 会进入 setup-only 模式，只开放安装向导接口；
在 Web 中保存数据库配置后，停止当前 API，执行 `uv run prd-agent db-upgrade`，
然后重新启动 `prd-agent api` 和 `prd-agent worker`。
项目默认设置 `CREWAI_TRACING_ENABLED=false` 并抑制 CrewAI tracing 提示，Worker
运行时不会询问是否查看 execution traces；这与 `CREWAI_DISABLE_TELEMETRY=true`
是两项不同配置。

## 自定义 LLM

推荐在 Web 的“LLM 配置”页面管理 provider、模型、Base URL 和 API key。
首次启动时如果设置了以下环境变量，系统会自动创建“环境默认”配置；不设置也可以
先启动管理台，再从页面创建：

```dotenv
# DeepSeek
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=...

# OpenRouter
LLM_MODEL=openrouter/deepseek/deepseek-chat
LLM_API_KEY=...

# Ollama（本地模型通常不需要 API Key）
LLM_MODEL=ollama/llama3.2
LLM_BASE_URL=http://localhost:11434
```

对于其他 OpenAI-compatible 服务，可以显式指定 provider 和地址：

```dotenv
LLM_MODEL=custom-model-id
LLM_PROVIDER=openai
LLM_API_KEY=...
LLM_BASE_URL=https://your-endpoint.example/v1
```

可选参数为 `LLM_TEMPERATURE`（默认 `0.2`）和
`LLM_TIMEOUT_SECONDS`（默认 `120`）。DeepSeek、Ollama 和 hosted vLLM
默认使用“Prompt JSON + 本地 Pydantic 校验”，避免 provider 不支持原生
JSON Schema；可通过 `LLM_NATIVE_STRUCTURED_OUTPUT=true|false` 覆盖。
旧的 `OPENAI_MODEL` 和 `OPENAI_API_KEY` 仍可使用，但只作为向后兼容配置。
按当前本地单用户方案，API key 明文保存在 MySQL，但读取接口只返回掩码。
部署到远程服务器前必须改为加密存储。

## CLI

```bash
uv run prd-agent new
uv run prd-agent resume <project-id>
uv run prd-agent status <project-id>
uv run prd-agent export <project-id> --artifact prd
uv run prd-agent export <project-id> --artifact sdd
uv run prd-agent api
uv run prd-agent worker
```

在结构化、逻辑校验、产品类型确认和 SDD 确认阶段输入 `下一步` 执行人工门禁。
重要逻辑问题可输入 `豁免 L-001: 原因`；阻断问题不能豁免。

## 测试

测试会在 `TEST_DATABASE_URL` 指向的 MySQL 8.0+ 数据库执行
`alembic downgrade base` 和 `alembic upgrade head`，并在数据库用例前后清空
全部业务表。测试账号必须具有建表、删表、索引和数据读写权限。

```bash
uv run pytest
cd web && pnpm test && pnpm build
```
