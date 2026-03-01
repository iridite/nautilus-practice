#!/bin/bash
# 完全自动化部署脚本 - 从零开始运行 sandbox 策略
# 适用于老家电脑（FnOS Debian + Docker）

set -e

echo "🚀 开始完全自动化部署..."
echo ""

# ============================================================================
# 步骤 1: 创建 .env 文件
# ============================================================================
echo "📝 [1/4] 创建环境配置..."

cat > .env << 'ENVEOF'
# Mihomo 代理订阅链接
CLASH_SUBSCRIPTION_URL=https://rkuoe.no-mad-world.club/link/G1qWf3dIQkoWLjF3?clash=3&extend=1

# 运行环境
NAUTILUS_ENV=sandbox

# 日志级别
LOG_LEVEL=INFO

# 时区
TZ=UTC
ENVEOF

echo "✓ 环境配置已创建"
echo ""

# ============================================================================
# 步骤 2: 创建必需目录
# ============================================================================
echo "📁 [2/4] 创建数据目录..."

mkdir -p data/raw
mkdir -p data/parquet
mkdir -p data/universe
mkdir -p data/instrument
mkdir -p output/backtest/result
mkdir -p output/backtest/report
mkdir -p logs

echo "✓ 目录结构已创建"
echo ""

# ============================================================================
# 步骤 3: 检测 docker-compose 命令
# ============================================================================
echo "🔍 [3/4] 检测 Docker Compose..."

if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
    echo "✓ 使用 docker compose (v2)"
else
    COMPOSE_CMD="docker-compose"
    echo "✓ 使用 docker-compose (v1)"
fi
echo ""

# ============================================================================
# 步骤 4: 构建并启动服务
# ============================================================================
echo "🏗️  [4/4] 构建 Docker 镜像并启动服务..."
echo ""
echo "这将执行以下操作："
echo "  1. 构建 Docker 镜像（首次需要 5-10 分钟）"
echo "  2. 启动 Mihomo 代理服务"
echo "  3. 启动 Nautilus 策略容器"
echo "  4. 自动下载必需的市场数据（约 2-5 分钟）"
echo "  5. 自动生成 Universe 文件"
echo "  6. 运行 Keltner 策略回测"
echo ""
echo "按 Enter 继续，或 Ctrl+C 取消..."
read

# 构建镜像
echo "📦 构建 Docker 镜像..."
$COMPOSE_CMD build

echo ""
echo "🎯 启动服务（后台模式）..."
$COMPOSE_CMD up -d

echo ""
echo "✅ 部署完成！"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 查看实时日志："
echo "  $COMPOSE_CMD logs -f nautilus-keltner"
echo ""
echo "📈 查看服务状态："
echo "  $COMPOSE_CMD ps"
echo ""
echo "🔍 查看回测结果："
echo "  ls -lh output/backtest/result/"
echo ""
echo "🛑 停止服务："
echo "  $COMPOSE_CMD down"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 提示："
echo "  - 首次运行会自动下载数据，需要等待几分钟"
echo "  - 数据下载完成后会自动开始回测"
echo "  - 回测结果保存在 output/backtest/result/ 目录"
echo ""
