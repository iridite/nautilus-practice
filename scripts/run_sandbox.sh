#!/usr/bin/env bash
# Sandbox 启动脚本
# 用于快速启动 KeltnerRSBreakout 策略的模拟盘测试

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Nautilus Sandbox - KeltnerRSBreakout${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查环境变量文件
if [ ! -f "test.env" ]; then
    echo -e "${RED}错误: test.env 文件不存在${NC}"
    echo "请创建 test.env 文件并配置 OKX 测试网 API 凭证:"
    echo "  OKX_API_KEY=your_key"
    echo "  OKX_API_SECRET=your_secret"
    echo "  OKX_API_PASSPHRASE=your_passphrase"
    exit 1
fi

# 检查 active.yaml 配置
echo -e "${YELLOW}检查配置...${NC}"
ACTIVE_ENV=$(grep "^environment:" config/active.yaml | awk '{print $2}' | tr -d '"')
ACTIVE_STRATEGY=$(grep "^strategy:" config/active.yaml | awk '{print $2}' | tr -d '"')

echo "  环境: $ACTIVE_ENV"
echo "  策略: $ACTIVE_STRATEGY"
echo ""

# 如果不是 sandbox 环境,提示用户
if [ "$ACTIVE_ENV" != "sandbox" ]; then
    echo -e "${YELLOW}警告: 当前环境不是 sandbox (当前: $ACTIVE_ENV)${NC}"
    echo "是否切换到 sandbox 环境? (y/n)"
    read -r response
    if [ "$response" = "y" ]; then
        sed -i 's/^environment:.*/environment: "sandbox"/' config/active.yaml
        echo -e "${GREEN}已切换到 sandbox 环境${NC}"
    else
        echo -e "${RED}取消启动${NC}"
        exit 1
    fi
fi

# 运行预检查
echo -e "${YELLOW}运行预检查...${NC}"
if ! uv run python sandbox/preflight.py --env sandbox; then
    echo -e "${RED}预检查失败,请修复上述问题后重试${NC}"
    exit 1
fi

echo -e "${GREEN}预检查通过!${NC}"
echo ""

# 启动 sandbox
echo -e "${GREEN}启动 Sandbox...${NC}"
echo -e "${YELLOW}提示: 按 Ctrl+C 停止${NC}"
echo ""

uv run python sandbox/engine.py --env sandbox
