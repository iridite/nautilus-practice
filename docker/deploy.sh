#!/bin/bash
set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Nautilus Keltner 策略 Docker 部署${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 1. 检查 Docker 环境
echo -e "${YELLOW}[1/6] 检查 Docker 环境...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker 未安装${NC}"
    echo "请先安装 Docker: https://docs.docker.com/engine/install/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}✗ Docker Compose 未安装${NC}"
    echo "请先安装 Docker Compose"
    exit 1
fi

DOCKER_VERSION=$(docker --version | grep -oP '\d+\.\d+' | head -1)
echo -e "${GREEN}✓ Docker 版本: $DOCKER_VERSION${NC}"

# 2. 检查硬件资源
echo -e "${YELLOW}[2/6] 检查硬件资源...${NC}"
TOTAL_MEM=$(free -g | awk '/^Mem:/{print $2}')
if [ "$TOTAL_MEM" -lt 8 ]; then
    echo -e "${YELLOW}⚠ 警告: 内存不足 8GB (当前: ${TOTAL_MEM}GB)${NC}"
    echo -e "${YELLOW}  建议调整 docker-compose.yml 中的内存限制${NC}"
fi

CPU_CORES=$(nproc)
if [ "$CPU_CORES" -lt 4 ]; then
    echo -e "${YELLOW}⚠ 警告: CPU 核心数不足 4 (当前: ${CPU_CORES})${NC}"
fi

DISK_FREE=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
if [ "$DISK_FREE" -lt 10 ]; then
    echo -e "${YELLOW}⚠ 警告: 磁盘空间不足 10GB (当前: ${DISK_FREE}GB)${NC}"
fi

echo -e "${GREEN}✓ 硬件检查完成: ${CPU_CORES} CPU, ${TOTAL_MEM}GB RAM, ${DISK_FREE}GB 可用${NC}"

# 3. 配置环境变量
echo -e "${YELLOW}[3/6] 配置环境变量...${NC}"
if [ -f .env ]; then
    echo -e "${GREEN}✓ .env 文件已存在${NC}"
    # 检查是否包含实际的订阅链接
    if grep -q "example.com" .env; then
        echo -e "${RED}✗ .env 文件包含示例链接，需要更新${NC}"
        echo "请编辑 .env 文件，填入实际的 CLASH_SUBSCRIPTION_URL"
        exit 1
    fi
else
    echo -e "${YELLOW}创建 .env 文件...${NC}"
    cat > .env << 'ENVEOF'
# Clash 订阅链接
CLASH_SUBSCRIPTION_URL=https://rkuoe.no-mad-world.club/link/G1qWf3dIQkoWLjF3?clash=3&extend=1

# 运行模式（sandbox 或 live）
NAUTILUS_ENV=sandbox

# 日志级别
LOG_LEVEL=DEBUG

# 时区
TZ=UTC
ENVEOF
    echo -e "${GREEN}✓ .env 文件已创建${NC}"
fi

# 4. 检查数据文件
echo -e "${YELLOW}[4/6] 检查数据文件...${NC}"
if [ ! -d "data/instrument" ] || [ -z "$(ls -A data/instrument 2>/dev/null)" ]; then
    echo -e "${YELLOW}⚠ 警告: data/instrument/ 目录为空${NC}"
    echo -e "${YELLOW}  回测可能会失败，请确保有标的定义文件${NC}"
fi

if [ ! -d "data/raw" ] || [ -z "$(ls -A data/raw 2>/dev/null)" ]; then
    echo -e "${YELLOW}⚠ 警告: data/raw/ 目录为空${NC}"
    echo -e "${YELLOW}  回测可能会失败，请先下载历史数据${NC}"
fi

# 5. 构建 Docker 镜像
echo -e "${YELLOW}[5/6] 构建 Docker 镜像...${NC}"
echo "这可能需要 5-10 分钟，请耐心等待..."

if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

if $COMPOSE_CMD build; then
    echo -e "${GREEN}✓ Docker 镜像构建成功${NC}"
else
    echo -e "${RED}✗ Docker 镜像构建失败${NC}"
    exit 1
fi

# 6. 启动服务
echo -e "${YELLOW}[6/6] 启动服务...${NC}"
echo ""
echo -e "${GREEN}选择启动模式:${NC}"
echo "  1) 前台运行（推荐首次部署，方便观察日志）"
echo "  2) 后台运行（适合长期运行）"
echo ""
read -p "请选择 [1/2]: " MODE

case $MODE in
    1)
        echo -e "${GREEN}启动服务（前台模式）...${NC}"
        echo "按 Ctrl+C 停止服务"
        echo ""
        $COMPOSE_CMD up
        ;;
    2)
        echo -e "${GREEN}启动服务（后台模式）...${NC}"
        $COMPOSE_CMD up -d
        echo ""
        echo -e "${GREEN}✓ 服务已在后台启动${NC}"
        echo ""
        echo "查看日志："
        echo "  $COMPOSE_CMD logs -f nautilus-keltner"
        echo ""
        echo "查看容器状态："
        echo "  $COMPOSE_CMD ps"
        echo ""
        echo "停止服务："
        echo "  $COMPOSE_CMD down"
        ;;
    *)
        echo -e "${RED}无效选择${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
