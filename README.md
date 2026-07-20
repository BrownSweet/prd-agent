# PRD Agent

基于 CrewAI Flow 的需求工作台，将模糊需求依次推进为结构化需求、逻辑校验、PRD、独立终审和 SDD。提供 Vue Web 管理台与原有 CLI；业务状态由 SQLite/MySQL 和 Python 门禁控制，LLM 输出不能直接改变阶段。

**核心特性：**
- 🤖 CrewAI Flow 编排的多智能体工作流
- 🔐 人工门禁控制确保质量
- 💾 SQLite/MySQL 双数据库持久化任务队列，按连接 URL 自动选择
- 🌐 Vue 3 Web 管理台 + 命令行界面
- 🔌 支持多种 LLM（OpenAI、DeepSeek、Ollama、自定义）
- 📄 自动生成结构化 PRD 和 SDD

---

## 目录

1. [系统架构](#系统架构)
2. [技术栈](#技术栈)
3. [快速开始](#快速开始)
4. [完整安装指南](#完整安装指南)
5. [CrewAI 工作流详解](#crewai-工作流详解)
6. [API 手册](#api-手册)
7. [CLI 使用指南](#cli-使用指南)
8. [Web 管理台](#web-管理台)
9. [开发指南](#开发指南)
10. [测试](#测试)
11. [部署到生产](#部署到生产)
12. [常见问题](#常见问题)

---

## 系统架构

### 工作流阶段

```
初始需求
    ↓
[1] 结构化 (STRUCTURING)
    ↓
[2] 逻辑验证 (LOGIC_VALIDATING) ← 人工门禁
    ↓
[3] 产品类型确认 (PRD_TYPE_CONFIRMING) ← 人工门禁
    ↓
[4] PRD 生成 (PRD_GENERATING)
    ↓
[5] PRD 独立终审 (PRD_REVIEWING)
    ↓
[6] PRD 修订 (PRD_REVISING) ← 人工门禁
    ↓
[7] SDD 确认 (SDD_CONFIRMING) ← 人工门禁
    ↓
[8] SDD 生成 (SDD_GENERATING)
    ↓
[9] 完成 (COMPLETED)
```

### 核心组件

```
┌─────────────────────────────────────────────────┐
│           Vue 3 Web 管理台 (5173)                │
└──────────────────┬──────────────────────────────┘
                   │ HTTP
┌──────────────────▼──────────────────────────────┐
│  FastAPI (8000)                                 │
│  ├─ 项目管理                                     │
│  ├─ 用户认证 (Argon2 + HttpOnly Cookie)        │
│  ├─ LLM 配置管理                                │
│  ├─ 数据库设置向导                              │
│  └─ 结果导出 (PRD/SDD)                          │
└──────────────────┬──────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
┌───────▼──────────┐  ┌──────▼──────────┐
│ SQLite / MySQL   │  │ Async Worker    │
│ ├─ 项目状态      │  │ ├─ CrewAI Flow  │
│ ├─ 任务队列      │  │ ├─ 智能体调度   │
│ ├─ 审查意见      │  │ └─ 结果持久化   │
│ └─ 工作流历史    │  └─────────────────┘
└──────────────────┘
        │
        └─ LLM (OpenAI/DeepSeek/Ollama/Custom)
```

### 数据流

```
用户输入需求
    ↓
[Structuring Agent] → 识别特性、数据、逻辑
    ↓
[Manual Gate] → 结构化就绪检查
    ↓
[PRD Writer Agent] → 生成 PRD 文档
    ↓
[PRD Reviewer Agent] → 独立审查
    ↓
[Solution Architect Agent] → 转换为 SDD
    ↓
导出 PRD/SDD 文档
```

---

## 技术栈

| 层次 | 技术 | 版本 |
|-----|------|------|
| **后端** | Python | 3.12+ |
| | FastAPI | 0.115+ |
| | CrewAI | 1.14.6 |
| | SQLAlchemy | 2.0+ |
| **数据库** | SQLite | Python 内置 pysqlite |
| | MySQL / PyMySQL | 8.0+ / 1.1+ |
| | Alembic | 1.14+ |
| **前端** | Vue | 3.5+ |
| | TypeScript | 5.9+ |
| | Vite | - |
| **认证** | Argon2 | via pwdlib |
| **CLI** | Typer | 0.15+ |
| **服务器** | Uvicorn | 0.34+ |

---

## 快速开始

### 前置条件

- Python 3.12+
- Node.js 22.12+（仅前端开发需要）
- SQLite（Python 内置，无需安装）或 MySQL 8.0+（生产库、测试库各一个）
- LLM API Key（OpenAI、DeepSeek 等）

### 5分钟快速启动

1. **克隆项目并配置环境**

```bash
git clone <repo-url> prd-agent
cd prd-agent

# 复制配置文件
cp .env.example .env
```

2. **编辑 .env 文件**

```bash
# .env
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=sk-xxxxx
DATABASE_URL=sqlite+pysqlite:///./data/prd_agent.db
TEST_DATABASE_URL=sqlite+pysqlite:///./data/prd_agent_test.db
```

如需 MySQL，把两项 URL 替换为：

```dotenv
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/prd_agent?charset=utf8mb4
TEST_DATABASE_URL=mysql+pymysql://user:password@localhost:3306/prd_agent_test?charset=utf8mb4
```

系统根据 URL 前缀自动选择数据库；切换连接不会自动迁移已有数据。

3. **安装依赖并初始化数据库**

```bash
uv sync --extra dev
uv run prd-agent db-upgrade
```

4. **启动三个终端**

```bash
# 终端 1: FastAPI 后端
uv run prd-agent api

# 终端 2: 异步任务工作线程
uv run prd-agent worker

# 终端 3: Vue 前端开发服务器
cd web && pnpm install && pnpm dev
```

5. **打开浏览器**

访问 `http://127.0.0.1:5173`，第一次登录时创建管理员账户。

---

## 完整安装指南

### 第一步：环境准备

#### 1.1 Python 环境

```bash
# 检查 Python 版本
python --version  # 需要 3.12+

# 安装 uv (Python 包管理器，比 pip 快 10 倍)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或者 macOS
brew install uv
```

#### 1.2 MySQL 数据库

```bash
# macOS
brew install mysql

# Ubuntu/Debian
sudo apt-get install mysql-server

# 启动 MySQL 服务
mysql.server start  # macOS
sudo systemctl start mysql  # Linux

# 登录并创建数据库
mysql -u root -p <<EOF
CREATE DATABASE prd_agent
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE prd_agent_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

-- 创建一个专用用户（可选但推荐）
CREATE USER 'prd_user'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON prd_agent.* TO 'prd_user'@'localhost';
GRANT ALL PRIVILEGES ON prd_agent_test.* TO 'prd_user'@'localhost';
FLUSH PRIVILEGES;
EOF
```

#### 1.3 Node.js (仅前端开发)

```bash
# 检查版本
node --version  # 需要 22.12+

# 如果版本过低，使用 nvm 升级
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
nvm install 22
nvm use 22

# 安装 pnpm (快速包管理器)
npm install -g pnpm
```

#### 1.4 LLM API Key

选择以下之一：

- **OpenAI**: https://platform.openai.com/api-keys
- **DeepSeek**: https://platform.deepseek.com/api-keys
- **OpenRouter**: https://openrouter.ai/keys
- **Ollama** (本地): `ollama pull llama2` 后启动 `ollama serve`

### 第二步：项目配置

```bash
# 1. 克隆项目
git clone <repo-url> prd-agent
cd prd-agent

# 2. 复制环境配置
cp .env.example .env

# 3. 编辑 .env 文件
nano .env  # 或用你喜欢的编辑器
```

### 第三步：配置 .env 文件

```dotenv
# === LLM 配置 ===
# 格式: provider/model
# 示例见下面的"LLM 配置详解"

LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=sk-xxxxxxxxxxxxx
LLM_TEMPERATURE=0.2              # 0.0-1.0，越低越确定
LLM_TIMEOUT_SECONDS=120          # API 超时时间
LLM_BASE_URL=                    # 自定义端点（可选）
LLM_PROVIDER=deepseek            # 显式指定 provider（可选）

# === 数据库配置（根据 URL 自动选择 SQLite/MySQL） ===
DATABASE_URL=sqlite+pysqlite:///./data/prd_agent.db
TEST_DATABASE_URL=sqlite+pysqlite:///./data/prd_agent_test.db
# MySQL 8.0+：
# DATABASE_URL=mysql+pymysql://prd_user:password@localhost:3306/prd_agent?charset=utf8mb4
# TEST_DATABASE_URL=mysql+pymysql://prd_user:password@localhost:3306/prd_agent_test?charset=utf8mb4

DATABASE_CONNECT_TIMEOUT_SECONDS=5
DATABASE_READ_TIMEOUT_SECONDS=30

# === API 和工作者配置 ===
API_HOST=127.0.0.1
API_PORT=8000
WORKER_POLL_SECONDS=1            # 任务轮询间隔

# === 工作流配置 ===
MAX_PRD_REVISION_ROUNDS=3         # PRD 最多修订轮数

# === CrewAI 配置 ===
CREWAI_DISABLE_TELEMETRY=true
CREWAI_TRACING_ENABLED=false
```

### 第四步：安装依赖

```bash
# 安装 Python 依赖（包括开发工具）
uv sync --extra dev

# 安装前端依赖
cd web
pnpm install
cd ..
```

### 第五步：初始化数据库

```bash
# 运行数据库迁移
uv run prd-agent db-upgrade

# 应该看到类似输出：
# INFO  [alembic.migration] Running upgrade  -> 001_initial, done
```

### 第六步：启动系统

**开发模式（需要3个终端）：**

```bash
# 终端 1: FastAPI 后端 (localhost:8000)
uv run prd-agent api
# 输出: INFO:     Uvicorn running on http://127.0.0.1:8000

# 终端 2: 异步任务工作线程
uv run prd-agent worker
# 输出: Worker started, polling every 1s

# 终端 3: Vue 开发服务器 (localhost:5173)
cd web
pnpm dev
# 输出: VITE v5.x.x  ready in xxx ms
```

**生产模式（前端预编译）：**

```bash
# 构建前端
cd web
pnpm build
cd ..

# 启动 API（会托管静态文件）
uv run prd-agent api

# 启动工作线程（另一个终端）
uv run prd-agent worker

# 访问 http://127.0.0.1:8000
```

### 第七步：首次登录

1. 打开 http://127.0.0.1:5173 (开发) 或 http://127.0.0.1:8000 (生产)
2. 如果看到登录页面，点击"创建管理员"
3. 设置用户名和密码
4. 如果未配置 LLM，会进入数据库设置向导
5. 填写数据库连接信息并保存
6. 重启 API 和 Worker：按 Ctrl+C 后重新启动

### 忘记管理员密码时重置

系统采用单管理员模式。请在项目根目录执行交互式重置命令：

```bash
uv run prd-agent reset-admin-password
```

根据提示输入并确认新密码（长度为 8 至 128 个字符）。输入内容不会显示，也不会写入 Shell 命令历史。重置成功后，所有已登录会话都会失效，需要使用新密码重新登录。

如果使用 Docker Compose，请执行：

```bash
docker compose exec app prd-agent reset-admin-password
```

该命令要求数据库连接可用且已经创建管理员。如果系统尚未创建管理员，请直接打开登录页完成首次管理员创建，无需执行重置。

---

## CrewAI 工作流详解

### 什么是 CrewAI?

CrewAI 是一个多智能体协作框架，允许 LLM 组织、规划和执行复杂任务。PRD Agent 使用 CrewAI Flow（v1.14.6+）来编排工作流。

### 工作流架构

```python
# src/prd_agent/flow.py - WorkflowEngine 类

class WorkflowEngine:
    """
    状态机 + 持久化工作流引擎
    
    - 状态：ProjectState（包含需求、问题、审查意见）
    - 阶段：Stage（9个不同的工作流阶段）
    - 门禁：WorkflowGate（人工干预点）
    """
    
    def create_project(requirement: str) -> ProjectState
    def submit_user_input(project_id: str, user_input: str) -> ProjectState
    def waive_issue(project_id: str, issue_id: str, reason: str) -> None
    def export_artifact(project_id: str, artifact_type: str) -> str
```

### 智能体定义

#### 1. Product Analyst（产品分析专家）

**角色**：将模糊需求转换为结构化特性列表

```python
role="产品需求分析专家"
goal="将产品需求转化为完整、可追溯且逻辑闭环的结构化规格"
backstory="你擅长识别需求中的事实、假设和缺口。"
```

**输出**：
- 特性列表（名称、描述、数据来源、交互逻辑、影响范围、依赖关系）
- 逻辑问题（阻断问题 vs 重要问题）
- 澄清问题（需要用户确认的项）

#### 2. PRD Writer（PRD 撰写专家）

**角色**：基于确认的结构化需求生成完整 PRD

```python
role="PRD撰写专家"
goal="基于已确认的结构化需求生成可审查、可实施的PRD"
backstory="你熟悉管理后台、C端、API、数据产品、平台和硬件产品。"
```

**输出**：
- 完整 PRD 文档（含功能描述、用户故事、验收标准）
- Markdown 格式，包含目录和交叉引用

#### 3. PRD Reviewer（独立终审专家）

**角色**：独立检查 PRD 的逻辑完整性

```python
role="PRD独立终审专家"
goal="独立发现PRD中的逻辑矛盾、流程断点和场景遗漏"
backstory="你与PRD作者职责隔离，只输出审查结论和问题。"
```

**输出**：
- 审查报告（问题清单、严重程度、建议）
- 不修改原 PRD，只列出问题

#### 4. Solution Architect（SDD 技术规范专家）

**角色**：将 PRD 转换为技术实现规范

```python
role="SDD技术规范专家"
goal="将终审通过的PRD转换为可直接开发的技术契约"
backstory="你重视接口、数据、状态、事务、错误和验收标准的一致性。"
```

**输出**：
- SDD 文档（API 设计、数据模型、状态机、错误处理）

### 工作流配置

#### LLM 配置

CrewAI 使用 `LLM` 类来抽象化不同的 LLM 提供商：

```python
# src/prd_agent/agents.py - AgentFactory

llm_options = {
    "model": "deepseek/deepseek-chat",
    "temperature": 0.2,              # 保持确定性
    "timeout": 120,                   # 长任务允许更长超时
    "api_key": "sk-xxxxx",
    "base_url": "https://...",        # 自定义端点
    "provider": "deepseek",
}
llm = LLM(**llm_options)
```

#### 支持的 LLM 提供商

| Provider | Model Format | 注意事项 |
|----------|--------------|--------|
| OpenAI | openai/gpt-4 | 需要 API Key |
| DeepSeek | deepseek/deepseek-chat | 支持思维链（MCP） |
| OpenRouter | openrouter/deepseek/deepseek-chat | 代理多个模型 |
| Ollama | ollama/llama2 | 本地运行，无需 Key |
| Custom | custom-id | 需要指定 `base_url` |

#### 结构化输出

默认情况下，系统使用 **Pydantic JSON + 本地验证**：

```python
# src/prd_agent/agents.py

supports_native_structured_output = {
    "openai": True,           # 支持 Native JSON Schema
    "deepseek": False,        # 使用 JSON + 本地验证
    "ollama": False,
    "hosted_vllm": False,
}
```

**原因**：某些 LLM 不支持标准 JSON Schema，使用本地验证更稳定。

可以通过 `LLM_NATIVE_STRUCTURED_OUTPUT=true` 强制使用原生结构化输出。

### 任务执行

```python
# src/prd_agent/tasks.py - CrewAITaskExecutor

class TaskExecutor:
    """
    将 Crew AI 任务包装为可中止、可检查进度的执行器
    """
    
    def structure_requirement(requirement: str, questions: list) -> RequirementSpec
    def generate_prd(spec: RequirementSpec) -> str  # Markdown
    def review_prd(prd: str, spec: RequirementSpec) -> ReviewReport
    def generate_sdd(prd: str) -> str  # Markdown
```

### 人工门禁

系统在关键阶段集成人工审核：

```python
# src/prd_agent/gates.py

def assert_structure_ready(state: ProjectState) -> None:
    """结构化就绪检查"""
    # - 所有特性已确认
    # - 所有澄清问题已回答
    # - 无未解决的阻断问题

def assert_logic_ready(state: ProjectState) -> None:
    """逻辑验证检查"""
    # - 特性之间无循环依赖
    # - 所有数据流完整
    # - 所有交互路径可达

def transition(
    state: ProjectState,
    from_stage: Stage,
    to_stage: Stage,
) -> ProjectState:
    """原子性阶段转换"""
    # 验证前置条件
    # 更新状态机
    # 审计日志
```

### 工作流执行流程图

```
create_project(requirement)
    │
    ├─ initialize_project()
    │  └─ save to database
    │
    └─ run_flow(project_id)
       │
       ├─ load project state
       │
       ├─ while not completed:
       │  │
       │  ├─ get current stage
       │  │
       │  ├─ STRUCTURING
       │  │  ├─ call structure_requirement(agent)
       │  │  ├─ save questions/issues
       │  │  └─ wait for user input
       │  │
       │  ├─ LOGIC_VALIDATING
       │  │  ├─ check assert_structure_ready()
       │  │  │  └─ if fail: wait for waive/fix
       │  │  └─ transition to next
       │  │
       │  ├─ PRD_GENERATING
       │  │  ├─ call generate_prd(agent)
       │  │  └─ save artifact
       │  │
       │  ├─ PRD_REVIEWING
       │  │  ├─ call review_prd(agent)
       │  │  └─ save review report
       │  │
       │  └─ ... (继续其他阶段)
       │
       └─ return completed state
```

---

## API 手册

### 基础信息

- **基地址**: `http://localhost:8000`
- **认证**: Cookie-based (`prd_agent_session`)
- **响应格式**: JSON
- **字段命名**: camelCase (与 Python snake_case 自动转换)

### 认证端点

#### 创建管理员 (首次使用)

```http
POST /auth/setup-admin
Content-Type: application/json

{
  "username": "admin",
  "password": "secure_password"
}
```

**响应**:
```json
{
  "adminCreated": true,
  "sessionToken": "..."
}
```

**状态码**: 201 (成功) / 409 (已存在)

#### 登录

```http
POST /auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "password"
}
```

**响应**:
```json
{
  "username": "admin",
  "sessionExpiresAt": "2026-06-27T14:00:00Z"
}
```

Cookie: `Set-Cookie: prd_agent_session=...; HttpOnly; SameSite=Strict`

#### 登出

```http
POST /auth/logout
```

---

### 项目管理

#### 创建项目

```http
POST /projects
Content-Type: application/json
Cookie: prd_agent_session=...

{
  "requirement": "一个用户可以登录并查看个人信息",
  "llmConfigId": "config-123"  // 可选，不填使用默认
}
```

**响应**:
```json
{
  "projectId": "proj-abc123",
  "stage": "STRUCTURING",
  "stageStatus": "running",
  "createdAt": "2026-06-20T10:00:00Z"
}
```

#### 获取项目

```http
GET /projects/{projectId}
Cookie: prd_agent_session=...
```

**响应**:
```json
{
  "projectId": "proj-abc123",
  "stage": "LOGIC_VALIDATING",
  "stageStatus": "waiting_user",
  "createdAt": "2026-06-20T10:00:00Z",
  "updatedAt": "2026-06-20T10:30:00Z",
  "requirementSpec": {
    "features": [
      {
        "featureId": "f-001",
        "name": "用户登录",
        "description": "...",
        "dependencies": ["f-002"]
      }
    ],
    "clarificationQuestions": [
      {
        "itemId": "q-001",
        "question": "登录支持哪些方式?",
        "status": "open"
      }
    ],
    "logicIssues": [
      {
        "issueId": "l-001",
        "description": "特性 f-001 和 f-003 存在循环依赖",
        "severity": "blocking",
        "status": "open"
      }
    ]
  }
}
```

#### 提交用户输入

```http
POST /projects/{projectId}/submit-input
Content-Type: application/json
Cookie: prd_agent_session=...

{
  "input": "下一步"  // 人工门禁通过
}
```

或

```json
{
  "input": "豁免 L-001: 特定产品场景，该依赖可接受"
}
```

或

```json
{
  "input": "我来继续填写问卷：..."
}
```

**响应**: 同上的项目状态

#### 提交答案到澄清问卷

```http
POST /projects/{projectId}/answers
Content-Type: application/json
Cookie: prd_agent_session=...

{
  "answers": [
    {
      "itemId": "q-001",
      "answer": "支持账号密码和社交登录"
    },
    {
      "itemId": "q-002",
      "answer": "..."
    }
  ]
}
```

#### 列出项目

```http
GET /projects?limit=20&offset=0
Cookie: prd_agent_session=...
```

**响应**:
```json
{
  "projects": [
    {
      "projectId": "proj-abc123",
      "stage": "COMPLETED",
      "createdAt": "2026-06-20T10:00:00Z"
    }
  ],
  "total": 42,
  "offset": 0,
  "limit": 20
}
```

---

### 工件导出

#### 导出 PRD

```http
GET /projects/{projectId}/artifacts/prd
Cookie: prd_agent_session=...
Accept: text/markdown
```

**响应**: Markdown 格式的 PRD 文档

#### 导出 SDD

```http
GET /projects/{projectId}/artifacts/sdd
Cookie: prd_agent_session=...
Accept: text/markdown
```

**响应**: Markdown 格式的 SDD 文档

---

### LLM 配置

#### 列出 LLM 配置

```http
GET /llm-configs
Cookie: prd_agent_session=...
```

**响应**:
```json
{
  "configs": [
    {
      "id": "config-default",
      "provider": "deepseek",
      "model": "deepseek-chat",
      "baseUrl": null,
      "temperature": 0.2,
      "apiKeyMasked": "sk-***",
      "isDefault": true
    }
  ]
}
```

#### 创建 LLM 配置

```http
POST /llm-configs
Content-Type: application/json
Cookie: prd_agent_session=...

{
  "provider": "openai",
  "model": "gpt-4",
  "apiKey": "sk-xxxxx",
  "temperature": 0.2,
  "baseUrl": null  // 可选
}
```

#### 更新 LLM 配置

```http
PUT /llm-configs/{configId}
Content-Type: application/json
Cookie: prd_agent_session=...

{
  "temperature": 0.3
}
```

#### 删除 LLM 配置

```http
DELETE /llm-configs/{configId}
Cookie: prd_agent_session=...
```

---

### 数据库设置

#### 获取数据库状态

```http
GET /setup/database
```

**响应**:
```json
{
  "configured": true,
  "connected": true,
  "error": null
}
```

#### 配置数据库

```http
POST /setup/database
Content-Type: application/json

{
  "databaseUrl": "mysql+pymysql://user:pass@localhost:3306/prd_agent?charset=utf8mb4",
  "testDatabaseUrl": "mysql+pymysql://user:pass@localhost:3306/prd_agent_test?charset=utf8mb4"
}
```

API 保存配置后会返回成功，但需要重启以生效。

---

## CLI 使用指南

### 命令概览

```bash
prd-agent --help
```

### 创建新项目

```bash
# 交互式输入
prd-agent new

# 或通过选项
prd-agent new --requirement "需要一个用户登录系统"

# 指定 LLM 配置
prd-agent new --requirement "..." --config deepseek
```

**示例输出**:
```
┌─────────────────────────────────────────┐
│ PRD Agent - 项目状态                     │
├─────────────────────────────────────────┤
│ 项目 ID    │ proj-abc123                 │
│ 阶段       │ LOGIC_VALIDATING            │
│ 状态       │ waiting_user                │
│ 特性       │ 5 项                        │
│ 问题       │ 2 项待解决                  │
└─────────────────────────────────────────┘
```

### 恢复项目

```bash
# 获取正在进行的项目
prd-agent resume proj-abc123

# 系统会显示当前阶段和需要的操作
# 然后进入交互式输入循环
```

### 查看项目状态

```bash
prd-agent status proj-abc123
```

**输出**:
```
阶段: STRUCTURING
状态: running
最后更新: 2 分钟前
```

### 导出工件

```bash
# 导出 PRD
prd-agent export proj-abc123 --artifact prd

# 导出 SDD
prd-agent export proj-abc123 --artifact sdd

# 导出到指定文件
prd-agent export proj-abc123 --artifact prd --output my-prd.md
```

### 数据库操作

```bash
# 升级数据库到最新版本
prd-agent db-upgrade

# 交互式重置管理员密码，并注销所有现有会话
prd-agent reset-admin-password
```

### API 服务器

```bash
# 启动 FastAPI（监听地址和端口由 API_HOST/API_PORT 配置）
prd-agent api
```

### 异步任务工作线程

```bash
# 启动工作线程（轮询任务队列）
prd-agent worker

# 最多处理一个任务后退出
prd-agent worker --once
```

---

### 人工门禁交互

在 `resume` 或交互式环节，系统会提示当前需要的操作：

#### 通过结构化检查

```
需要确认结构化已就绪。请输入：
> 下一步
```

或

```
> next
```

或

```
> 确认
```

#### 豁免逻辑问题

```
找到 3 个逻辑问题（1 个阻断，2 个重要）

L-001: 特性 F-001 和 F-003 循环依赖
  严重程度: BLOCKING
  
L-002: 数据流 D-005 缺少默认值
  严重程度: IMPORTANT

输入豁免命令：
> 豁免 L-001: 该场景中该依赖是可接受的
```

或

```
> waive L-002: Reason in English
```

#### 回答澄清问题

```
请回答以下澄清问题：

Q-001: 登录支持哪些认证方式？
> 支持账密和社交登录

Q-002: 是否需要二次验证？
> 可选配置
```

---

## Web 管理台

### 系统要求

- Node.js 22.12+
- pnpm (推荐) 或 npm

### 开发启动

```bash
cd web
pnpm install
pnpm dev
```

访问 `http://127.0.0.1:5173`

### 生产构建

```bash
cd web
pnpm build

# 输出到 dist/ 目录
# FastAPI 会自动托管 dist 中的文件
```

### 页面概览

#### 登录/设置

- **登录页**: 输入用户名密码
- **首次使用**: 创建管理员账户
- **数据库配置**: 如果未配置，会进入向导

#### 项目列表

- 显示所有项目（最新的在前）
- 支持按阶段筛选
- 可导出 PRD/SDD

#### 项目详情

- **阶段进度**: 可视化工作流进度
- **需求结构**: 特性、问卷、逻辑问题列表
- **交互界面**: 答卷、通过门禁、豁免问题

#### LLM 配置

- 配置默认 LLM
- 支持多个 LLM 配置（创建、编辑、删除）
- 测试 LLM 连接

---

## 开发指南

### 项目结构

```
prd-agent/
├── src/prd_agent/
│   ├── __init__.py
│   ├── agents.py           # CrewAI Agent 定义
│   ├── tasks.py            # CrewAI Task 定义
│   ├── flow.py             # WorkflowEngine（核心状态机）
│   ├── gates.py            # 人工门禁逻辑
│   ├── models.py           # Pydantic 数据模型
│   ├── repositories.py     # SQLAlchemy 数据访问
│   ├── services.py         # 业务逻辑
│   ├── settings.py         # 配置管理
│   ├── api.py              # FastAPI 路由
│   ├── cli.py              # Typer CLI
│   └── worker.py           # 异步工作线程
│
├── alembic/                # 数据库迁移
│   ├── versions/
│   └── env.py
│
├── web/                    # Vue 前端
│   ├── src/
│   │   ├── components/
│   │   ├── views/
│   │   ├── api/
│   │   └── stores/
│   └── package.json
│
├── tests/
│   ├── test_workflow.py
│   ├── test_repositories.py
│   ├── test_services.py
│   ├── conftest.py
│   └── ...
│
├── .env.example            # 环境配置模板
├── pyproject.toml          # Python 项目配置
├── README.md               # 本文档
└── alembic.ini
```

### 核心模块说明

#### models.py - 数据模型

定义所有 Pydantic Schema 和 SQLAlchemy ORM 模型：

```python
# 工作流阶段
class Stage(StrEnum):
    STRUCTURING = "STRUCTURING"
    LOGIC_VALIDATING = "LOGIC_VALIDATING"
    PRD_GENERATING = "PRD_GENERATING"
    # ...

# 项目状态（内存模型）
class ProjectState(BaseModel):
    project_id: str
    stage: Stage
    requirement_spec: RequirementSpec
    # ...

# 特性定义
class RequirementFeature(Schema):
    name: str
    description: str
    data_source: str
    interaction_logic: str
    operation_impact: str
    dependencies: list[str]
```

#### agents.py - 智能体工厂

```python
class AgentFactory:
    def product_analyst(self) -> Agent:
        """需求分析"""
        
    def prd_writer(self) -> Agent:
        """PRD 撰写"""
        
    def prd_reviewer(self) -> Agent:
        """独立审查"""
        
    def solution_architect(self) -> Agent:
        """技术规范"""
```

#### flow.py - 工作流引擎

```python
class WorkflowEngine:
    def create_project(requirement: str) -> ProjectState:
        """创建新项目并开始工作流"""
        
    def submit_user_input(project_id: str, user_input: str):
        """处理用户输入（答卷、门禁通过、豁免等）"""
        
    def waive_issue(project_id: str, issue_id: str, reason: str):
        """豁免逻辑问题"""
```

#### repositories.py - 数据访问层

```python
class SQLAlchemyRepository:
    def create_project(state: ProjectState) -> None:
        """保存项目"""
        
    def get_project(project_id: str) -> ProjectState:
        """读取项目"""
        
    def list_projects(limit: int, offset: int) -> list[ProjectState]:
        """列表"""
        
    def update_project(state: ProjectState) -> None:
        """更新项目"""
```

#### gates.py - 门禁检查

```python
def assert_structure_ready(state: ProjectState) -> None:
    """检查结构化是否就绪
    
    要求：
    - 所有澄清问题已回答
    - 所有特性已确认
    - 无未解决的阻断问题
    """
    
def assert_logic_ready(state: ProjectState) -> None:
    """检查逻辑是否就绪"""
    
def transition(from_stage: Stage, to_stage: Stage) -> None:
    """原子性阶段转换"""
```

### 添加新的智能体

1. **定义 Agent 在 agents.py**

```python
def my_agent(self) -> Agent:
    return self._agent(
        role="我的角色",
        goal="我的目标",
        backstory="我的背景",
        skill_name="my-skill",  # 对应 skills/my-skill.md
    )
```

2. **定义任务在 tasks.py**

```python
def my_task(executor: TaskExecutor, spec: SomeModel) -> str:
    crew = Crew(
        agents=[executor.factory.my_agent()],
        tasks=[Task(
            description="任务描述",
            expected_output="期望输出",
            agent=executor.factory.my_agent(),
        )],
    )
    result = crew.kickoff(inputs={"input": str(spec)})
    return str(result)
```

3. **在 flow.py 中集成**

```python
class WorkflowEngine:
    def my_workflow_step(self, state: ProjectState) -> ProjectState:
        result = self.executor.my_task(state.requirement_spec)
        # 更新状态
        state.some_field = result
        return state
```

### 本地开发技巧

#### 前端自动重加载

```bash
# 前端：pnpm dev 自动启用 HMR
cd web && pnpm dev
```

#### 调试 LLM 调用

设置 `CREWAI_TRACING_ENABLED=true` 查看 CrewAI 的执行跟踪：

```bash
CREWAI_TRACING_ENABLED=true uv run prd-agent api
```

#### 使用本地 Ollama 进行开发

无需 API Key，快速迭代：

```bash
# 1. 启动 Ollama
ollama serve

# 2. 在另一个终端下载模型
ollama pull mistral

# 3. 配置 .env
LLM_MODEL=ollama/mistral
LLM_BASE_URL=http://localhost:11434
```

#### 数据库调试

```bash
# 查看当前迁移版本
alembic current

# 查看迁移历史
alembic history

# 降级到特定版本
alembic downgrade 001_initial

# 查看 SQL
alembic upgrade head --sql
```

### 性能优化

#### 批量处理

如果需要处理大量项目：

```python
# ❌ 避免：逐个加载
for project_id in project_ids:
    state = repository.get_project(project_id)
    # 处理

# ✅ 推荐：批量查询
states = repository.list_projects(limit=1000, offset=0)
```

#### 缓存 LLM 配置

LLM 对象在 `AgentFactory` 初始化时创建，共享使用。避免重复创建。

---

## 测试

### 运行测试

```bash
# 运行全部测试
uv run pytest

# 运行特定文件
uv run pytest tests/test_workflow.py

# 运行特定测试
uv run pytest tests/test_workflow.py::test_create_project

# 显示详细信息
uv run pytest -vv

# 并行运行（加快速度）
uv run pytest -n auto
```

### 测试覆盖率

```bash
# 生成覆盖率报告
uv run pytest --cov=prd_agent --cov-report=html

# 查看报告
open htmlcov/index.html
```

### 前端测试

```bash
cd web

# 运行单元测试
pnpm test

# 运行 E2E 测试
pnpm test:e2e

# 生成覆盖率
pnpm test --coverage
```

### 编写测试

#### 单元测试示例

```python
# tests/test_workflow.py

import pytest
from prd_agent.flow import WorkflowEngine
from prd_agent.repositories import SQLAlchemyRepository
from prd_agent.tasks import CrewAITaskExecutor

@pytest.fixture
def workflow(test_repository):
    executor = CrewAITaskExecutor(AgentFactory(get_settings()))
    return WorkflowEngine(test_repository, executor)

def test_create_project(workflow):
    """测试创建项目"""
    state = workflow.create_project("一个简单的需求")
    
    assert state.project_id is not None
    assert state.stage == Stage.STRUCTURING
    assert state.requirement_spec.source_inputs[0].text == "一个简单的需求"

def test_submit_user_input(workflow):
    """测试用户提交"""
    state = workflow.create_project("需求")
    
    # 完成当前阶段
    state = workflow.submit_user_input(state.project_id, "下一步")
    
    assert state.stage_status == StageStatus.WAITING_USER
```

#### 集成测试

```python
def test_full_workflow(workflow):
    """完整工作流测试"""
    # 创建项目
    state = workflow.create_project("完整需求文本")
    
    # 结构化
    assert state.stage == Stage.STRUCTURING
    
    # 回答问题
    state = workflow.submit_user_input(
        state.project_id,
        "我的答案"
    )
    
    # 通过门禁
    state = workflow.submit_user_input(state.project_id, "下一步")
    
    # ... 继续工作流
```

### 测试数据库

测试使用 `TEST_DATABASE_URL` 指定的数据库：

- **自动清理**：每个测试前后清空所有业务表
- **迁移**：自动运行 `downgrade base` 和 `upgrade head`
- **隔离**：每个测试相互独立

---

## 部署到生产

### Docker 单容器部署（推荐）

部署镜像已经集成以下进程：

- Nginx：监听容器 `8080`，托管 Vue 静态文件并代理 `/api`。
- FastAPI：仅监听容器内部 `127.0.0.1:8000`。
- Worker：处理持久化任务队列。
- Alembic：每次容器启动前自动执行 `upgrade head`。

默认使用 SQLite，数据库和上传文件分别保存在 Docker named volume 中，不需要启动 MySQL：

```bash
bash docker/startup.sh start
```

启动完成后访问：<http://localhost:8080>。

常用命令：

```bash
bash docker/startup.sh status
bash docker/startup.sh logs
bash docker/startup.sh restart
bash docker/startup.sh stop
```

也可以直接使用 Compose：

```bash
docker compose up -d --build --wait
docker compose ps
docker compose logs -f app
```

生产 Compose 默认发布到 `80` 端口：

```bash
docker compose -f docker-compose.prod.yml up -d --build --wait
```

如需修改对外端口，在 `.env` 中设置：

```dotenv
APP_PORT=8088
```

如需连接外部 MySQL，生产库与测试库必须同时配置且使用相同数据库类型：

```dotenv
DOCKER_DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/prd_agent?charset=utf8mb4
DOCKER_TEST_DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/prd_agent_test?charset=utf8mb4
```

切换数据库 URL 不会自动搬迁 SQLite/MySQL 中已有的数据。

### 手动部署参考

### 1. 前置检查

```bash
# 检查依赖
uv sync --extra dev

# 运行测试
.venv/bin/python -m pytest
cd web && pnpm test && pnpm build
```

### 2. 构建前端

```bash
cd web
pnpm install --frozen-lockfile
pnpm build           # 输出到 dist/

# 验证构建
ls -la dist/
```

### 3. 数据库迁移

```bash
# 在生产环境运行迁移
uv run prd-agent db-upgrade

# 验证当前迁移版本
uv run alembic current
```

### 4. 启动服务

**选项 A：分离的进程**

```bash
# 终端 1：API
nohup uv run prd-agent api > api.log 2>&1 &

# 终端 2：Worker
nohup uv run prd-agent worker \
  > worker.log 2>&1 &
```

**选项 B：使用 systemd 服务**

创建 `/etc/systemd/system/prd-agent-api.service`:

```ini
[Unit]
Description=PRD Agent API
After=network.target

[Service]
Type=simple
User=prd
WorkingDirectory=/opt/prd-agent
Environment=API_HOST=127.0.0.1
Environment=API_PORT=8000
ExecStart=/opt/prd-agent/.venv/bin/prd-agent api
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable prd-agent-api
sudo systemctl start prd-agent-api
```

### 5. Nginx 反向代理

```nginx
upstream prd_agent_api {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name prd.example.com;

    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name prd.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # 安全头
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;

    location / {
        proxy_pass http://prd_agent_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持（如果需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 6. 安全配置

#### 环境变量保护

```bash
# ✅ 推荐：使用密钥管理系统
export LLM_API_KEY=$(aws secretsmanager get-secret-value --secret-id prd/llm-key --query SecretString)

# ❌ 避免：硬编码在 .env
# LLM_API_KEY=sk-xxxxx  (不要这样做)
```

#### 数据库加密

```sql
-- 对 api_keys 列加密
ALTER TABLE llm_configs
  MODIFY COLUMN api_key VARBINARY(256);

-- 使用应用层加密
```

#### 审计日志

所有状态转换都记录在 `audit_events` 表中：

```python
class AuditEvent(SQLModel, table=True):
    id: str = Field(primary_key=True)
    project_id: str
    event_type: str        # "project_created", "input_submitted", etc.
    details: str           # JSON string
    created_at: datetime   # 自动戳时间
```

### 7. 监控

#### 日志收集

```bash
# 后端日志
tail -f /var/log/prd-agent/api.log
tail -f /var/log/prd-agent/worker.log

# 使用 ELK Stack 收集
# logstash config:
input {
  file {
    path => "/var/log/prd-agent/*.log"
    start_position => "beginning"
  }
}
```

#### 健康检查

```bash
# 检查 API 是否在线
curl -f http://localhost:8000/api/v1/health || exit 1

# 检查数据库连接
uv run alembic current
```

---

## 常见问题

### 安装和配置

#### Q1: "缺少 DATABASE_URL"

```bash
# 解决方案 1：编辑 .env
DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/prd_agent?charset=utf8mb4

# 解决方案 2：通过 Web 向导
# 访问 http://localhost:5173/setup/database 并填写
```

#### Q2: "连接 MySQL 超时"

```bash
# 检查 MySQL 是否在线
mysql -u root -p -h localhost

# 检查防火墙
sudo ufw allow 3306

# 增加超时时间
DATABASE_CONNECT_TIMEOUT_SECONDS=10
DATABASE_READ_TIMEOUT_SECONDS=60
```

#### Q3: "Module not found: prd_agent"

```bash
# 重新安装
uv sync

# 或在项目目录安装可编辑模式
pip install -e .
```

### LLM 和模型

#### Q4: "LLM API Key 无效"

```bash
# 检查 Key 是否正确
echo $LLM_API_KEY

# 测试连接
curl https://api.deepseek.com/v1/chat/completions \
  -H "Authorization: Bearer $LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}]}'
```

#### Q5: "模型返回无效 JSON"

```bash
# 启用本地验证（避免依赖 provider 的 JSON Schema 支持）
LLM_NATIVE_STRUCTURED_OUTPUT=false

# 或增加超时
LLM_TIMEOUT_SECONDS=180
```

#### Q6: "想用本地 Ollama"

```bash
# 1. 启动 Ollama
ollama serve

# 2. 下载模型
ollama pull mistral

# 3. 配置 .env
LLM_MODEL=ollama/mistral
LLM_BASE_URL=http://localhost:11434
LLM_NATIVE_STRUCTURED_OUTPUT=false
```

### 工作流和任务

#### Q7: "项目卡在某个阶段"

```bash
# 检查 Worker 日志
tail -f worker.log

# 查看项目状态
curl http://localhost:8000/projects/{projectId}

# 检查 MySQL 中的任务队列
mysql> SELECT * FROM workflow_jobs WHERE project_id='xxx';
```

#### Q8: "如何跳过某个阶段"

不能直接跳过，但可以豁免问题：

```bash
# CLI
prd-agent resume proj-123

# 输入豁免命令
> 豁免 L-001: 原因
```

#### Q9: "PRD 生成失败"

```bash
# 检查 LLM 连接
curl -H "Authorization: Bearer $API_KEY" https://api.deepseek.com/...

# 增加超时
LLM_TIMEOUT_SECONDS=300

# 查看详细错误
RUST_LOG=debug uv run prd-agent resume proj-123
```

### 性能和可靠性

#### Q10: "系统响应缓慢"

```bash
# 检查 MySQL 性能
SHOW PROCESSLIST;

# 增加 Worker 性能
WORKER_POLL_SECONDS=0.5

# 增加内存分配
export PYTHONUNBUFFERED=1
```

#### Q11: "Worker 重启后任务丢失"

**不会丢失**。设计特性：

- 任务持久化在 MySQL
- Worker 重启时会把 `running` 状态的任务标记为 `failed`
- 用户可以点击"重试"重新运行

```sql
-- 查看任务状态
SELECT job_id, status FROM workflow_jobs 
  WHERE project_id='xxx'
  ORDER BY created_at DESC;
```

### 开发和测试

#### Q12: "测试数据库权限不足"

测试账户需要以下权限：

```sql
GRANT CREATE, DROP, SELECT, INSERT, UPDATE, DELETE, INDEX 
  ON prd_agent_test.* 
  TO 'test_user'@'localhost';
```

#### Q13: "如何清空所有测试数据"

```bash
# 运行迁移下沉和上升（自动清空）
alembic downgrade base
alembic upgrade head

# 或直接清表
mysql> DROP DATABASE prd_agent_test; CREATE DATABASE prd_agent_test;
```

#### Q14: "前端 Vite 缓存问题"

```bash
# 清空 Vite 缓存
cd web
rm -rf node_modules/.vite
pnpm dev
```

### 部署相关

#### Q15: "生产环境中 API Key 明文保存不安全"

**已知问题**。改进方案：

1. **应用层加密**（推荐短期）
   ```python
   from cryptography.fernet import Fernet
   cipher = Fernet(settings.encryption_key)
   encrypted = cipher.encrypt(api_key.encode())
   ```

2. **外部密钥管理**（推荐长期）
   ```python
   # 使用 AWS Secrets Manager / HashiCorp Vault
   api_key = fetch_from_vault("prd/llm/api-key")
   ```

3. **数据库透明加密**
   ```sql
   -- MySQL InnoDB 原生加密
   SET innodb_encrypt_tables=ON;
   ```

#### Q16: "如何扩展到多个 Worker?"

目前使用单机 MySQL 驱动的任务队列。扩展方案：

```python
# 方案 1：Redis 队列（RQ）
# 方案 2：消息队列（RabbitMQ、Kafka）
# 方案 3：分布式任务系统（Celery）
```

#### Q17: "备份和恢复"

```bash
# 备份数据库
mysqldump -u user -p prd_agent > backup.sql

# 恢复
mysql -u user -p prd_agent < backup.sql

# 备份前端静态文件
tar -czf web-dist.tar.gz web/dist/
```

---

## 贡献指南

### 代码风格

- **Python**: 遵循 PEP 8，使用 `ruff` 格式化
- **前端**: Prettier 格式化，ESLint 检查
- **Commit**: 规范化消息格式 `feat:`, `fix:`, `docs:`, `test:`, `refactor:`

### 提交 PR

1. Fork 项目并创建特性分支
2. 提交包含意义的 commit
3. 编写或更新测试
4. 确保所有测试通过
5. 提交 PR 并等待 review

### 报告 Bug

包含以下信息：

- 系统信息（OS、Python 版本、MySQL 版本）
- 复现步骤
- 错误日志
- 期望行为 vs 实际行为

---

## 许可证

[待补充]

## 联系方式

- **文档**: [GitHub Issues](https://github.com/...)
- **讨论**: [GitHub Discussions](https://github.com/...)

---

**最后更新**: 2026-06-20
