#!/bin/bash
# 快速部署检查脚本
# 用法: ./scripts/check_deployment.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "Docker 部署检查"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ISSUES=0

# 1. 检查关键文件
echo "1. 检查关键文件..."
REQUIRED_FILES=(
    "Dockerfile"
    "docker-compose.prod.yml"
    "docker/entrypoint-auto.sh"
    "config/active.yaml"
    "config/environments/sandbox.yaml"
    "config/strategies/keltner_rs_breakout.yaml"
    ".env"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "  ${GREEN}✓${NC} $file"
    else
        echo -e "  ${RED}✗${NC} $file"
        ISSUES=$((ISSUES + 1))
    fi
done
echo ""

# 2. 检查环境变量
echo "2. 检查环境变量..."
if [ -f ".env" ]; then
    REQUIRED_VARS=("OKX_API_KEY" "OKX_API_SECRET" "OKX_API_PASSPHRASE")
    for var in "${REQUIRED_VARS[@]}"; do
        if grep -q "^${var}=" .env; then
            echo -e "  ${GREEN}✓${NC} $var"
        else
            echo -e "  ${RED}✗${NC} $var"
            ISSUES=$((ISSUES + 1))
        fi
    done
else
    echo -e "  ${RED}✗${NC} .env 文件不存在"
    ISSUES=$((ISSUES + 1))
fi
echo ""

# 3. 检查数据目录
echo "3. 检查数据目录..."
REQUIRED_DIRS=("data/instrument" "data/top" "data/universe" "data/raw")
for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo -e "  ${GREEN}✓${NC} $dir"
    else
        echo -e "  ${YELLOW}⚠${NC} $dir (将在容器启动时创建)"
    fi
done
echo ""

# 4. 检查 active.yaml 配置
echo "4. 检查 active.yaml 配置..."
if grep -q "environment: sandbox" config/active.yaml; then
    echo -e "  ${GREEN}✓${NC} environment: sandbox"
else
    echo -e "  ${RED}✗${NC} environment 未设置为 sandbox"
    ISSUES=$((ISSUES + 1))
fi
echo ""

# 5. 检查 Universe 配置一致性
echo "5. 检查 Universe 配置..."
STRATEGY_TOP_N=$(grep "universe_top_n:" config/strategies/keltner_rs_breakout.yaml | awk '{print $2}')
SANDBOX_FILE=$(grep "file:" config/environments/sandbox.yaml | grep universe | awk -F'"' '{print $2}')
EXPECTED_FILE="data/universe/universe_${STRATEGY_TOP_N}_W-MON.json"

if [ "$SANDBOX_FILE" = "$EXPECTED_FILE" ]; then
    echo -e "  ${GREEN}✓${NC} Universe 路径一致: $EXPECTED_FILE"
else
    echo -e "  ${YELLOW}⚠${NC} Universe 路径可能不一致"
    echo "     策略配置: universe_${STRATEGY_TOP_N}_W-MON.json"
    echo "     sandbox:   $SANDBOX_FILE"
fi
echo ""

# 6. 运行 preflight 检查
echo "6. 运行 preflight 检查..."
if command -v uv &> /dev/null; then
    if uv run python -c "
import sys
sys.path.insert(0, '.')
from sandbox.preflight import run_preflight
from core.loader import load_config
from pathlib import Path

try:
    env_config, strategy_config, _ = load_config('sandbox')
    base_dir = Path('.')
    problems = run_preflight(base_dir, env_config.sandbox, strategy_config, warn_on_missing_instruments=True)

    if problems:
        for p in problems:
            print(f'  ✗ {p}')
        sys.exit(1)
    else:
        print('  ✓ Preflight 检查通过')
        sys.exit(0)
except Exception as e:
    print(f'  ✗ Preflight 检查失败: {e}')
    sys.exit(1)
" 2>&1; then
        echo ""
    else
        ISSUES=$((ISSUES + 1))
        echo ""
    fi
else
    echo -e "  ${YELLOW}⚠${NC} uv 未安装，跳过 preflight 检查"
    echo ""
fi

# 7. 总结
echo "=========================================="
if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✅ 所有检查通过! 可以安全部署${NC}"
    echo ""
    echo "建议的部署步骤:"
    echo "  1. docker build -t iridite/nautilus-keltner:latest ."
    echo "  2. docker push iridite/nautilus-keltner:latest"
    echo "  3. docker compose -f docker-compose.prod.yml up -d"
    exit 0
else
    echo -e "${RED}❌ 发现 $ISSUES 个问题，请修复后再部署${NC}"
    echo ""
    echo "详细信息请查看: docs/DEPLOYMENT_CHECKLIST.md"
    exit 1
fi
