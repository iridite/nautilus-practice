#!/bin/bash
# 完全自动化的 entrypoint - 从零开始运行 sandbox 策略
set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}NautilusTrader Practice - Auto Bootstrap${NC}"
echo -e "${BLUE}==========================================${NC}"
echo "Python version: $(python --version)"
echo "Working directory: $(pwd)"
echo "Environment: ${NAUTILUS_ENV:-sandbox}"
echo -e "${BLUE}==========================================${NC}"
echo ""

# ============================================================================
# 步骤 1: 等待代理就绪（如果使用 Mihomo）
# ============================================================================
if [ -n "$HTTP_PROXY" ]; then
    echo -e "${YELLOW}[1/5] 等待 Mihomo 代理就绪...${NC}"

    MAX_WAIT=60
    WAIT_COUNT=0
    PROXY_HOST=$(echo $HTTP_PROXY | sed 's|http://||' | cut -d: -f1)
    PROXY_PORT=$(echo $HTTP_PROXY | sed 's|http://||' | cut -d: -f2)

    while ! nc -z "$PROXY_HOST" "$PROXY_PORT" 2>/dev/null; do
        if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
            echo -e "${RED}错误: 代理未就绪，超时退出${NC}"
            exit 1
        fi
        echo "代理未就绪，等待 5 秒... ($WAIT_COUNT/$MAX_WAIT)"
        sleep 5
        WAIT_COUNT=$((WAIT_COUNT + 5))
    done

    echo -e "${GREEN}✓ Mihomo 代理已就绪${NC}"
    echo "  HTTP Proxy: $HTTP_PROXY"
    echo "  HTTPS Proxy: $HTTPS_PROXY"
    echo ""
else
    echo -e "${YELLOW}[1/5] 跳过代理检查（未配置代理）${NC}"
    echo ""
fi

# ============================================================================
# 步骤 2: 检查并下载必需数据
# ============================================================================
echo -e "${YELLOW}[2/5] 检查数据文件...${NC}"

# 从策略配置读取需要的交易对
STRATEGY_CONFIG="config/strategies/keltner_rs_breakout.yaml"
UNIVERSE_TOP_N=$(grep "universe_top_n:" "$STRATEGY_CONFIG" | awk '{print $2}')
TIMEFRAME=$(grep "timeframe:" "$STRATEGY_CONFIG" | awk '{print $2}')

echo "策略配置:"
echo "  - Universe Top N: ${UNIVERSE_TOP_N:-15}"
echo "  - Timeframe: ${TIMEFRAME:-1d}"
echo ""

# 检查是否需要下载数据
DATA_DIR="data/raw"
REQUIRED_SYMBOLS=("BTCUSDT" "ETHUSDT" "SOLUSDT" "BNBUSDT" "ADAUSDT")

MISSING_DATA=false
MISSING_SYMBOLS=()
for symbol in "${REQUIRED_SYMBOLS[@]}"; do
    if [ ! -d "$DATA_DIR/$symbol" ] || [ -z "$(ls -A $DATA_DIR/$symbol 2>/dev/null)" ]; then
        echo "  ✗ 缺失数据: $symbol"
        MISSING_DATA=true
        MISSING_SYMBOLS+=("$symbol")
    else
        echo "  ✓ 数据存在: $symbol"
    fi
done
echo ""

if [ "$MISSING_DATA" = true ]; then
    echo -e "${YELLOW}开始并行下载缺失的数据...${NC}"

    # 计算日期范围（最近 2 年）
    END_DATE=$(date +%Y-%m-%d)
    START_DATE=$(date -d "2 years ago" +%Y-%m-%d)

    echo "日期范围: $START_DATE 到 $END_DATE"
    echo "并发数: 3 个交易对"
    echo ""

    # 使用并行下载脚本（5x 性能提升）
    python scripts/download_parallel.py \
        --symbols "${MISSING_SYMBOLS[@]}" \
        --start-date "$START_DATE" \
        --end-date "$END_DATE" \
        --max-workers 3 \
        || echo "警告: 部分数据下载失败"

    echo -e "${GREEN}✓ 数据下载完成${NC}"
    echo ""
else
    echo -e "${GREEN}✓ 所有必需数据已存在（增量更新已跳过）${NC}"
    echo ""
fi

# ============================================================================
# 步骤 3: 生成 Universe（如果需要）
# ============================================================================
echo -e "${YELLOW}[3/5] 检查 Universe 文件...${NC}"

UNIVERSE_FILE="data/universe/universe_${UNIVERSE_TOP_N:-15}_W-MON.json"

if [ ! -f "$UNIVERSE_FILE" ]; then
    echo "  ✗ Universe 文件不存在: $UNIVERSE_FILE"
    echo ""
    echo -e "${YELLOW}生成 Universe...${NC}"

    python scripts/generate_universe.py \
        --top-n "${UNIVERSE_TOP_N:-15}" \
        --freq "W-MON" \
        --output "$UNIVERSE_FILE" \
        || echo "警告: Universe 生成失败，将使用默认配置"

    echo -e "${GREEN}✓ Universe 生成完成${NC}"
    echo ""
else
    echo -e "${GREEN}✓ Universe 文件已存在${NC}"
    echo "  文件: $UNIVERSE_FILE"
    echo ""
fi

# ============================================================================
# 步骤 4: 验证配置文件
# ============================================================================
echo -e "${YELLOW}[4/5] 验证配置文件...${NC}"

REQUIRED_CONFIGS=(
    "config/environments/sandbox.yaml"
    "config/strategies/keltner_rs_breakout.yaml"
)

CONFIG_OK=true
for config in "${REQUIRED_CONFIGS[@]}"; do
    if [ ! -f "$config" ]; then
        echo -e "${RED}  ✗ 配置文件缺失: $config${NC}"
        CONFIG_OK=false
    else
        echo "  ✓ 配置文件存在: $config"
    fi
done
echo ""

if [ "$CONFIG_OK" = false ]; then
    echo -e "${RED}错误: 配置文件缺失，无法继续${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 配置验证通过${NC}"
echo ""

# ============================================================================
# 步骤 5: 运行策略
# ============================================================================
echo -e "${YELLOW}[5/5] 启动策略...${NC}"
echo ""
echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}开始执行 Sandbox 策略${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""

# 运行主程序（传递所有参数）
exec python main.py "$@"
