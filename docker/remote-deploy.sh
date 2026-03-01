#!/bin/bash
# 远程部署脚本（在本地机器运行，自动部署到远程机器）
set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  远程部署到老家电脑${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 读取远程机器信息
read -p "远程机器 IP 或域名: " REMOTE_HOST
read -p "远程机器用户名 [默认: root]: " REMOTE_USER
REMOTE_USER=${REMOTE_USER:-root}
read -p "远程部署路径 [默认: ~/nautilus-practice]: " REMOTE_PATH
REMOTE_PATH=${REMOTE_PATH:-~/nautilus-practice}

echo ""
echo -e "${YELLOW}配置信息:${NC}"
echo "  远程主机: $REMOTE_USER@$REMOTE_HOST"
echo "  部署路径: $REMOTE_PATH"
echo ""
read -p "确认部署? [y/N]: " CONFIRM

if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "取消部署"
    exit 0
fi

# 1. 测试 SSH 连接
echo -e "${YELLOW}[1/5] 测试 SSH 连接...${NC}"
if ! ssh -o ConnectTimeout=5 "$REMOTE_USER@$REMOTE_HOST" "echo '连接成功'" &> /dev/null; then
    echo -e "${RED}✗ SSH 连接失败${NC}"
    echo "请检查："
    echo "  1. 远程机器 IP/域名是否正确"
    echo "  2. SSH 服务是否运行"
    echo "  3. 是否配置了 SSH 密钥认证"
    exit 1
fi
echo -e "${GREEN}✓ SSH 连接成功${NC}"

# 2. 检查远程 Docker 环境
echo -e "${YELLOW}[2/5] 检查远程 Docker 环境...${NC}"
if ! ssh "$REMOTE_USER@$REMOTE_HOST" "command -v docker &> /dev/null"; then
    echo -e "${RED}✗ 远程机器未安装 Docker${NC}"
    echo "请先在远程机器安装 Docker"
    exit 1
fi
echo -e "${GREEN}✓ Docker 已安装${NC}"

# 3. 传输代码
echo -e "${YELLOW}[3/5] 传输代码到远程机器...${NC}"
rsync -avz --progress \
    --exclude='.git' \
    --exclude='data/raw' \
    --exclude='data/parquet' \
    --exclude='output' \
    --exclude='logs' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    ./ "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/"

echo -e "${GREEN}✓ 代码传输完成${NC}"

# 4. 远程执行部署
echo -e "${YELLOW}[4/5] 远程执行部署...${NC}"
ssh "$REMOTE_USER@$REMOTE_HOST" << 'ENDSSH'
cd ~/nautilus-practice

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

# 构建并启动
echo "构建 Docker 镜像..."
$COMPOSE_CMD build

echo "启动服务（后台模式）..."
$COMPOSE_CMD up -d

echo ""
echo "✅ 远程部署完成！"
ENDSSH

# 5. 验证部署
echo -e "${YELLOW}[5/5] 验证部署状态...${NC}"
sleep 5
ssh "$REMOTE_USER@$REMOTE_HOST" "cd $REMOTE_PATH && docker-compose ps"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  远程部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "查看远程日志："
echo "  ssh $REMOTE_USER@$REMOTE_HOST 'cd $REMOTE_PATH && docker-compose logs -f nautilus-keltner'"
echo ""
echo "停止远程服务："
echo "  ssh $REMOTE_USER@$REMOTE_HOST 'cd $REMOTE_PATH && docker-compose down'"
