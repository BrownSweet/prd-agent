#!/bin/bash
# =====================================================
# MySQL 自动备份脚本
# =====================================================
# 这个脚本用于在 Docker 容器启动时配置定期备份

BACKUP_DIR="/var/lib/mysql/backups"
DB_NAME="prd_agent"
MYSQL_USER="${MYSQL_USER:-prd_user}"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 创建备份脚本
cat > /usr/local/bin/backup-mysql.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/var/lib/mysql/backups"
DB_NAME="prd_agent"
BACKUP_FILE="$BACKUP_DIR/backup-$(date +%Y%m%d-%H%M%S).sql"

# 执行备份
mysqldump \
  --user=root \
  --password="$MYSQL_ROOT_PASSWORD" \
  --single-transaction \
  --quick \
  --lock-tables=false \
  "$DB_NAME" > "$BACKUP_FILE"

# 压缩
gzip "$BACKUP_FILE"

# 保留最近 7 天的备份
find "$BACKUP_DIR" -name "backup-*.sql.gz" -mtime +7 -delete

echo "Backup completed: ${BACKUP_FILE}.gz"
EOF

chmod +x /usr/local/bin/backup-mysql.sh

# 创建 cron 任务（可选：每天凌晨 2 点执行）
# 注意：Docker 容器中 cron 需要额外配置
echo "0 2 * * * /usr/local/bin/backup-mysql.sh" | crontab -

exit 0
