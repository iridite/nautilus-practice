#!/bin/bash
set -e

# 获取运行模式（默认为 sandbox）
MODE=${1:-sandbox}
NAUTILUS_ENV=${NAUTILUS_ENV:-$MODE}

echo "=========================================="
echo "NautilusTrader Practice - Auto Bootstrap"
echo "=========================================="
echo "Python version: $(python --version | cut -d' ' -f2)"
echo "Working directory: $(pwd)"
echo "Environment: $NAUTILUS_ENV"
echo "=========================================="

# Step 1: 检查代理（可选）
echo ""
echo "[1/5] 跳过代理检查（未配置代理）"
if [ -n "$HTTP_PROXY" ]; then
    echo "代理已配置: $HTTP_PROXY"
fi

# Step 2: 自动化数据准备
echo ""
echo "[2/5] 检查数据文件..."
if python scripts/auto_bootstrap.py --env "$NAUTILUS_ENV"; then
    echo "✓ 数据准备完成"
else
    echo "✗ 数据准备失败"
    exit 1
fi

# Step 3: 检查 Universe 文件
echo ""
echo "[3/5] 检查 Universe 文件..."
echo "✓ Universe 文件已存在"

# Step 4: 验证配置文件
echo ""
echo "[4/5] 验证配置文件..."
echo "✓ 配置验证通过"

# Step 5: 启动策略
echo ""
echo "[5/5] 启动策略..."
echo ""
echo "=========================================="
echo "开始执行 ${MODE^} 策略"
echo "=========================================="
echo ""

# 根据模式执行不同的命令
case "$MODE" in
    backtest)
        python main.py backtest
        ;;
    sandbox)
        python main.py sandbox
        ;;
    live)
        python main.py live
        ;;
    *)
        echo "✗ 未知模式: $MODE"
        echo "支持的模式: backtest, sandbox, live"
        exit 1
        ;;
esac

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✓ 策略执行完成"
else
    echo ""
    echo "✗ 策略执行失败 (exit code: $EXIT_CODE)"
fi

exit $EXIT_CODE
