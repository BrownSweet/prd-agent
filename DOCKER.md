# Docker 部署指南

本指南涵盖如何使用 Docker 和 Docker Compose 部署 PRD Agent。

## 目录

1. [快速开始](#快速开始)
2. [架构概览](#架构概览)
3. [开发环境](#开发环境)
4. [生产部署](#生产部署)
5. [常见操作](#常见操作)
6. [故障排查](#故障排查)

---

## 快速开始

### 前置条件

- Docker 20.10+
- Docker Compose 2.0+

检查版本：

```bash
docker --version
docker-compose --version
```

### 一键启动（开发）

```bash
# 1. 配置环境变量
cp .env.docker .env
# 编辑 .env，填写 LLM API Key

# 2. 启动所有服务
docker-compose up -d

# 3. 等待初始化（约 30 秒）
docker-compose logs -f api

# 4. 打开浏览器
# http://localhost:5173   (前端开发服务器)
# http://localhost:8000   (API)
# http://localhost:8080   (Adminer - MySQL 可视化)
```

### 查看日志

```bash
# 所有服务日志
docker-compose logs -f

# 特定服务日志
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f mysql
```

### 停止服务

```bash
# 暂停（保留数据）
docker-compose stop

# 停止并删除容器（保留卷数据）
docker-compose down

# 完全删除（包括数据库）
docker-compose down -v
```

---

## 架构概览

### 开发环境（docker-compose.yml）

```
┌─────────────────────────────────────────────────┐
│ Docker Compose 开发环境                         │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────┐  ┌──────────────┐           │
│  │ Frontend     │  │ Adminer      │           │
│  │ :5173        │  │ :8080        │           │
│  └──────┬───────┘  └──────┬───────┘           │
│         │                 │                    │
│         │  HTTP          │                    │
│         └─────────┬───────┘                   │
│                   │                           │
│         ┌─────────▼──────────┐               │
│         │  API :8000         │               │
│         │  (FastAPI)         │               │
│         └─────────┬──────────┘               │
│                   │                           │
│         ┌─────────▼──────────┐               │
│         │  Worker            │               │
│         │  (Async Tasks)     │               │
│         └─────────┬──────────┘               │
│                   │                           │
│         ┌─────────▼──────────┐               │
│         │  MySQL :3306       │               │
│         │  (prd_agent db)    │               │
│         └────────────────────┘               │
│                                              │
└─────────────────────────────────────────────────┘
```

### 生产环境（docker-compose.prod.yml）

```
┌────────────────────────────────────────────────┐
│ Docker Compose 生产环境                        │
├────────────────────────────────────────────────┤
│                                                │
│        ┌────────────────────────┐             │
│        │  Nginx :80/:443        │             │
│        │  (反向代理 + SSL)      │             │
│        └────────────┬───────────┘             │
│                     │                         │
│  ┌──────────────────┴──────────────────┐     │
│  │                                     │     │
│  ▼                                     ▼     │
│  ┌──────────────┐            ┌──────────────┐│
│  │ API          │            │ Worker       ││
│  │ (Production) │            │ (async)      ││
│  └──────┬───────┘            └──────┬───────┘│
│         │                           │        │
│         │         ┌─────────────────┘        │
│         │         │                         │
│         ▼         ▼                         │
│  ┌─────────────────────────┐               │
│  │ MySQL :3306             │               │
│  │ (持久化 + 备份)         │               │
│  └─────────────────────────┘               │
│                                            │
└────────────────────────────────────────────┘
```

---

## 开发环境

### 启动开发环境

```bash
docker-compose up -d

# 或者实时查看日志
docker-compose up
```

### 服务访问地址

| 服务 | URL | 说明 |
|-----|-----|------|
| 前端 | http://localhost:5173 | Vue 开发服务器（热重加载） |
| API | http://localhost:8000 | FastAPI（自动重加载） |
| MySQL | localhost:3306 | 数据库 |
| Adminer | http://localhost:8080 | MySQL 可视化工具 |

### 代码修改和热重加载

**Python 后端** - 源代码自动重加载：

```bash
# api 和 worker 的 src 目录已挂载
docker-compose exec api /bin/bash
# 在容器内修改代码后会自动重新加载
```

**Vue 前端** - Vite 热模块重加载：

```bash
# 编辑 web/src 中的文件
# 保存后浏览器自动刷新
```

### 进入容器 Shell

```bash
# API 容器
docker-compose exec api sh

# Worker 容器
docker-compose exec worker sh

# MySQL 容器
docker-compose exec mysql mysql -u prd_user -p prd_agent

# 前端容器
docker-compose exec frontend sh
```

### 查看容器状态

```bash
# 列出所有容器
docker-compose ps

# 查看容器资源使用
docker stats

# 查看容器网络
docker network ls
docker network inspect prd-agent_prd-network
```

### 重启特定服务

```bash
# 重启 API
docker-compose restart api

# 重启 Worker
docker-compose restart worker

# 重启 MySQL（会丢失内存缓存，但保留数据）
docker-compose restart mysql
```

### 查看容器日志

```bash
# 最后 100 行
docker-compose logs --tail=100 api

# 实时跟踪
docker-compose logs -f worker

# 查看特定时间段
docker-compose logs --since=5m api

# 保存到文件
docker-compose logs api > logs.txt
```

---

## 生产部署

### 前置条件

- 服务器（Linux 推荐）
- Docker 和 Docker Compose
- 域名和 SSL 证书（可选）
- LLM API Key

### 第一步：准备服务器

```bash
# 1. 更新系统
sudo apt update && sudo apt upgrade -y

# 2. 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 3. 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 4. 验证安装
docker --version
docker-compose --version
```

### 第二步：部署项目

```bash
# 1. 克隆项目
git clone <repo-url> prd-agent
cd prd-agent

# 2. 配置环境
cp .env.docker .env

# 3. 编辑 .env，填写生产环境变量
nano .env

# 示例配置：
# LLM_MODEL=deepseek/deepseek-chat
# LLM_API_KEY=sk-xxxxxxxxxxxxx
# MYSQL_ROOT_PASSWORD=secure_password
# MYSQL_USER=prd_user
# MYSQL_PASSWORD=secure_password
```

### 第三步：启动生产环境

```bash
# 使用生产配置文件
docker-compose -f docker-compose.prod.yml up -d

# 等待服务就绪（约 60 秒）
docker-compose -f docker-compose.prod.yml logs -f api

# 检查所有服务是否健康
docker-compose -f docker-compose.prod.yml ps
```

### 第四步：配置 SSL（可选）

#### 使用 Let's Encrypt

```bash
# 1. 安装 Certbot
sudo apt install certbot python3-certbot-nginx -y

# 2. 获取证书
sudo certbot certonly --standalone \
  -d prd.example.com \
  --agree-tos \
  -m admin@example.com

# 3. 证书位置
# /etc/letsencrypt/live/prd.example.com/

# 4. 复制证书到项目目录
sudo cp /etc/letsencrypt/live/prd.example.com/fullchain.pem docker/certs/cert.pem
sudo cp /etc/letsencrypt/live/prd.example.com/privkey.pem docker/certs/key.pem
sudo chown $USER:$USER docker/certs/*

# 5. 编辑 docker/default.conf，启用 SSL
nano docker/default.conf
# 取消注释 ssl_certificate 和 ssl_certificate_key 行
# 注释掉 listen 80

# 6. 重启 Nginx
docker-compose -f docker-compose.prod.yml restart nginx
```

### 第五步：配置监控和日志

#### 查看实时日志

```bash
# 所有服务
docker-compose -f docker-compose.prod.yml logs -f

# 特定服务
docker-compose -f docker-compose.prod.yml logs -f api --tail=50

# 导出日志
docker-compose -f docker-compose.prod.yml logs api > api.log
```

#### 日志旋转

Docker 已配置日志旋转，最大 10MB，保留 3 个文件。编辑 docker-compose.prod.yml 修改：

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "100m"    # 改为 100MB
    max-file: "10"      # 保留 10 个文件
```

### 第六步：数据库备份

#### 手动备份

```bash
# 备份数据库
docker-compose -f docker-compose.prod.yml exec mysql \
  mysqldump -u prd_user -p prd_agent > backup.sql

# 压缩备份
gzip backup.sql

# 上传到安全位置
scp backup.sql.gz backup-server:/backups/
```

#### 自动备份（使用脚本）

```bash
# 创建备份脚本
cat > /home/prd/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/prd/backups"
mkdir -p $BACKUP_DIR
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

cd /home/prd/prd-agent

docker-compose -f docker-compose.prod.yml exec -T mysql \
  mysqldump -u prd_user -p$(grep MYSQL_PASSWORD .env | cut -d= -f2) \
  prd_agent | gzip > $BACKUP_DIR/backup-$TIMESTAMP.sql.gz

# 删除 7 天前的备份
find $BACKUP_DIR -name "backup-*.sql.gz" -mtime +7 -delete
EOF

chmod +x /home/prd/backup.sh

# 添加 crontab 定时任务（每天凌晨 2 点）
crontab -e
# 添加行：0 2 * * * /home/prd/backup.sh
```

### 第七步：自动重启和监控

#### Systemd 服务（可选）

```bash
# 创建 systemd 服务文件
sudo tee /etc/systemd/system/prd-agent.service << 'EOF'
[Unit]
Description=PRD Agent Docker Compose
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/home/prd/prd-agent
ExecStart=/usr/bin/docker-compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker-compose -f docker-compose.prod.yml down
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# 启用和启动
sudo systemctl daemon-reload
sudo systemctl enable prd-agent
sudo systemctl start prd-agent

# 查看状态
sudo systemctl status prd-agent
```

---

## 常见操作

### 扩展 API 实例

使用 docker-compose scale 命令（仅在生产环境有多个 API 实例时）：

```bash
# 扩展到 3 个 API 实例
docker-compose -f docker-compose.prod.yml up -d --scale api=3

# 注意：需要负载均衡器（如 Nginx）来分发流量
```

### 升级应用

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 重新构建镜像
docker-compose -f docker-compose.prod.yml build --no-cache

# 3. 重新启动服务
docker-compose -f docker-compose.prod.yml up -d

# 4. 验证
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs api
```

### 数据库迁移

```bash
# 自动执行（在启动时）
docker-compose -f docker-compose.prod.yml up -d

# 或手动执行
docker-compose -f docker-compose.prod.yml exec api \
  uv run prd-agent db-upgrade
```

### 清理 Docker 资源

```bash
# 删除未使用的镜像
docker image prune -a

# 删除未使用的卷
docker volume prune

# 删除未使用的网络
docker network prune

# 完全清理（谨慎！）
docker system prune -a --volumes
```

### 实时监控

```bash
# Docker 资源使用
docker stats

# 容器进程
docker ps

# 容器网络
docker network inspect prd-agent_prd-network

# 容器存储
docker inspect <container_id> | grep -A 10 "Mounts"
```

---

## 故障排查

### 服务无法启动

```bash
# 1. 检查日志
docker-compose logs <service_name>

# 2. 检查端口是否被占用
lsof -i :8000
lsof -i :3306
lsof -i :5173

# 3. 检查环境变量
docker-compose config | grep -A 20 "environment:"

# 4. 重新构建镜像
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 数据库连接失败

```bash
# 1. 检查 MySQL 容器状态
docker-compose ps mysql

# 2. 检查 MySQL 日志
docker-compose logs mysql

# 3. 手动连接测试
docker-compose exec mysql mysql -u prd_user -p prd_agent

# 4. 检查网络连接
docker-compose exec api ping mysql

# 5. 重启数据库
docker-compose restart mysql
```

### LLM API 连接问题

```bash
# 1. 检查 API Key
docker-compose exec api env | grep LLM

# 2. 测试连接（示例 DeepSeek）
docker-compose exec api curl -H "Authorization: Bearer $LLM_API_KEY" \
  https://api.deepseek.com/v1/models

# 3. 查看错误日志
docker-compose logs -f api | grep -i error

# 4. 增加超时时间
# 编辑 .env：
# LLM_TIMEOUT_SECONDS=300
docker-compose restart api
```

### 内存或磁盘不足

```bash
# 1. 检查磁盘使用
docker system df

# 2. 清理未使用的资源
docker image prune -a
docker volume prune
docker system prune

# 3. 增加 Docker 资源限制
# 编辑 docker-compose.yml，在服务下添加：
# resources:
#   limits:
#     cpus: '2'
#     memory: 4G
#   reservations:
#     cpus: '1'
#     memory: 2G

# 4. 检查 MySQL 数据大小
docker-compose exec mysql du -sh /var/lib/mysql
```

### 容器频繁崩溃

```bash
# 1. 查看重启历史
docker-compose logs api | tail -100

# 2. 检查健康检查配置
docker inspect <container_id> | grep -A 15 "HealthCheck"

# 3. 禁用健康检查（临时调试）
docker-compose down
# 编辑 docker-compose.yml，注释掉 healthcheck 部分
docker-compose up -d

# 4. 查看容器退出码
docker-compose ps
# 退出码说明：
# 0 = 正常退出
# 1 = 应用程序错误
# 125 = Docker 运行时错误
# 137 = OOM killed
```

### 前端无法连接到 API

```bash
# 1. 检查 API 是否在线
curl http://localhost:8000/health

# 2. 检查网络连接
docker-compose exec frontend ping api

# 3. 查看前端日志
docker-compose logs frontend

# 4. 检查 CORS 配置
# API 应该允许来自 localhost:5173 的请求

# 5. 清除浏览器缓存
# 打开 DevTools -> 清空缓存 -> 刷新
```

---

## 性能优化

### 数据库优化

```bash
# 1. 启用查询日志
docker-compose exec mysql mysql -u prd_user -p prd_agent
mysql> SET GLOBAL slow_query_log='ON';
mysql> SET GLOBAL long_query_time=2;

# 2. 查看慢查询
docker-compose exec mysql tail -f /var/log/mysql/slow.log

# 3. 优化索引
# 定期运行 ANALYZE TABLE
docker-compose exec mysql mysql -u prd_user -p prd_agent
mysql> ANALYZE TABLE <table_name>;
```

### API 性能

```bash
# 编辑 docker-compose.yml，增加资源：
services:
  api:
    # ...
    resources:
      limits:
        cpus: '2'
        memory: 2G
```

### MySQL 性能

```bash
# 编辑 docker-compose.yml，MySQL 命令行优化：
mysql:
  command: >
    --character-set-server=utf8mb4
    --max_connections=500
    --innodb_buffer_pool_size=1G
    --innodb_log_file_size=256M
```

---

## 相关资源

- [Docker 官方文档](https://docs.docker.com/)
- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Nginx 反向代理](https://nginx.org/en/docs/)
- [MySQL Docker 镜像](https://hub.docker.com/_/mysql)

---

**最后更新**: 2026-06-20
