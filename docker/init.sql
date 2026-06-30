-- =====================================================
-- PRD Agent MySQL 初始化脚本
-- =====================================================
-- 这个脚本在 MySQL 容器启动时自动执行

-- 创建测试数据库
CREATE DATABASE IF NOT EXISTS prd_agent_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

-- 为测试用户授权
GRANT ALL PRIVILEGES ON prd_agent_test.* TO 'prd_user'@'%';

-- 刷新权限
FLUSH PRIVILEGES;

-- =====================================================
-- 可选：创建额外的用户（生产环境推荐）
-- =====================================================
-- CREATE USER 'prd_readonly'@'%' IDENTIFIED BY 'readonly_password';
-- GRANT SELECT ON prd_agent.* TO 'prd_readonly'@'%';

-- CREATE USER 'backup'@'%' IDENTIFIED BY 'backup_password';
-- GRANT SELECT, LOCK TABLES ON prd_agent.* TO 'backup'@'%';

-- FLUSH PRIVILEGES;
