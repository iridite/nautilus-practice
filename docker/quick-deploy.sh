#!/bin/bash
# 一键部署脚本（完全自动化，无交互）
set -e

echo "🚀 开始自动部署..."

# 创建 .env 文件
cat > .env << 'ENVEOF'
CLASH_SUBSCRIPTION_URL=https://rkuoe.no-mad-world.club/link/G1qWf3dIQkoWLjF3?clash=3&extend=1
NAUTILUS_ENV=sandbox
LOG_LEVEL=DEBUG
TZ=UTC
ENVEOF

# 检测 docker-compose 命令
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

# 构建并启动（后台模式）
echo "📦 构建 Docker 镜像..."
$COMPOSE_CMD build

echo "🎯 启动服务（后台模式）..."
$COMPOSE_CMD up -d

echo ""
echo "✅ 部署完成！"
echo ""
echo "查看日志："
echo "  $COMPOSE_CMD logs -f nautilus-keltner"
echo ""
echo "查看状态："
echo "  $COMPOSE_CMD ps"
echo ""
echo "停止服务："
echo "  $COMPOSE_CMD down"
