#!/bin/bash
# =====================================================
# PRD Agent Docker 快速启动脚本
# =====================================================
# 用法: bash docker/startup.sh [dev|prod]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

MODE="${1:-dev}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印函数
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查前置条件
check_prerequisites() {
    print_info "检查前置条件..."

    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose 未安装，请先安装 Docker Compose"
        exit 1
    fi

    print_info "Docker 版本: $(docker --version)"
    print_info "Docker Compose 版本: $(docker-compose --version)"
}

# 环境配置
setup_env() {
    print_info "配置环境变量..."

    if [ ! -f "$PROJECT_DIR/.env" ]; then
        if [ ! -f "$PROJECT_DIR/.env.docker" ]; then
            print_error ".env 和 .env.docker 都不存在"
            exit 1
        fi

        print_warn "未找到 .env 文件，正在从 .env.docker 复制..."
        cp "$PROJECT_DIR/.env.docker" "$PROJECT_DIR/.env"

        print_warn "请编辑 .env 文件并填写 LLM API Key"
        print_warn "然后重新运行此脚本"

        if command -v nano &> /dev/null; then
            read -p "是否现在编辑 .env 文件? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                nano "$PROJECT_DIR/.env"
            fi
        fi
    fi

    # 验证必要的环境变量
    if ! grep -q "LLM_API_KEY" "$PROJECT_DIR/.env" || grep "LLM_API_KEY=$" "$PROJECT_DIR/.env"; then
        print_error "LLM_API_KEY 未设置"
        exit 1
    fi
}

# 启动开发环境
startup_dev() {
    print_info "启动开发环境..."

    cd "$PROJECT_DIR"

    print_info "启动所有服务..."
    docker-compose up -d

    print_info "等待服务就绪（约 30 秒）..."
    sleep 5

    # 检查服务状态
    print_info "检查服务状态..."
    docker-compose ps

    print_info ""
    print_info "============================================"
    print_info "✅ 开发环境已启动"
    print_info "============================================"
    print_info ""
    print_info "服务访问地址："
    print_info "  前端:   http://localhost:5173"
    print_info "  API:    http://localhost:8000"
    print_info "  MySQL:  http://localhost:8080 (Adminer)"
    print_info ""
    print_info "查看日志："
    print_info "  docker-compose logs -f api"
    print_info "  docker-compose logs -f worker"
    print_info ""
    print_info "停止服务："
    print_info "  docker-compose down"
    print_info ""
}

# 启动生产环境
startup_prod() {
    print_info "启动生产环境..."

    cd "$PROJECT_DIR"

    # 检查 SSL 证书（可选）
    if [ -f "$PROJECT_DIR/docker/certs/cert.pem" ] && [ -f "$PROJECT_DIR/docker/certs/key.pem" ]; then
        print_info "检测到 SSL 证书，启用 HTTPS"
    else
        print_warn "未检测到 SSL 证书，使用 HTTP"
        print_warn "生产环境强烈建议配置 SSL"
    fi

    print_info "启动所有服务（生产配置）..."
    docker-compose -f docker-compose.prod.yml up -d

    print_info "等待服务就绪（约 60 秒）..."
    for i in {1..12}; do
        if docker-compose -f docker-compose.prod.yml exec -T api curl -s http://localhost:8000/health > /dev/null 2>&1; then
            break
        fi
        echo "等待中... ($i/12)"
        sleep 5
    done

    # 检查服务状态
    print_info "检查服务状态..."
    docker-compose -f docker-compose.prod.yml ps

    print_info ""
    print_info "============================================"
    print_info "✅ 生产环境已启动"
    print_info "============================================"
    print_info ""
    print_info "服务访问地址："
    print_info "  Web:    http://localhost (或配置的域名)"
    print_info "  API:    http://localhost/api (通过 Nginx 代理)"
    print_info ""
    print_info "查看日志："
    print_info "  docker-compose -f docker-compose.prod.yml logs -f api"
    print_info ""
    print_info "停止服务："
    print_info "  docker-compose -f docker-compose.prod.yml down"
    print_info ""
}

# 清理资源
cleanup() {
    print_warn "停止并清理所有容器和卷..."

    if [ "$MODE" = "prod" ]; then
        docker-compose -f docker-compose.prod.yml down -v
    else
        docker-compose down -v
    fi

    print_info "清理完成"
}

# 显示帮助信息
show_help() {
    cat << EOF
用法: $0 [命令]

命令:
  dev              启动开发环境 (默认)
  prod             启动生产环境
  stop             停止所有服务
  clean            停止并删除所有容器和卷
  help             显示此帮助信息

示例:
  $0                  # 启动开发环境
  $0 dev              # 同上
  $0 prod             # 启动生产环境
  $0 clean            # 清理所有资源

EOF
}

# 主程序
main() {
    case "$MODE" in
        dev|development)
            check_prerequisites
            setup_env
            startup_dev
            ;;
        prod|production)
            check_prerequisites
            setup_env
            startup_prod
            ;;
        stop)
            print_info "停止所有服务..."
            cd "$PROJECT_DIR"
            docker-compose down
            print_info "已停止"
            ;;
        clean)
            read -p "确定要删除所有容器和卷吗? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                cleanup
            else
                print_info "已取消"
            fi
            ;;
        help|-h|--help)
            show_help
            ;;
        *)
            print_error "未知命令: $MODE"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 运行主程序
main
