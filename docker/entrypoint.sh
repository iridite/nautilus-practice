#!/bin/bash
set -e

echo "=========================================="
echo "Nautilus Practice Backtest Runner"
echo "=========================================="

# Environment variable to control proxy dependency
REQUIRE_PROXY=${REQUIRE_PROXY:-true}

# Step 1: Validate proxy configuration
echo ""
echo "[1/5] Validating proxy configuration..."
if [ "$REQUIRE_PROXY" = "true" ]; then
    if [ -z "$HTTP_PROXY" ]; then
        echo "✗ Error: HTTP_PROXY environment variable is not set"
        echo "  Please check docker-compose.yml environment variable configuration"
        exit 1
    fi
    echo "Proxy configuration: $HTTP_PROXY"
    echo "✓ Proxy configuration validated"
else
    echo "✓ Skipping proxy validation (REQUIRE_PROXY=false)"
fi

# Step 2: Generate Mihomo configuration
echo ""
echo "[2/5] Generating Mihomo configuration..."
if [ -f "/app/docker/mihomo-config.yaml.template" ]; then
    envsubst < /app/docker/mihomo-config.yaml.template > /tmp/mihomo-config.yaml
    echo "✓ Mihomo configuration generated"
else
    echo "✓ Skipping Mihomo config generation (template not found)"
fi

# Step 3: Wait for Mihomo proxy to be ready
echo ""
echo "[3/5] Checking proxy availability..."

if [ "$REQUIRE_PROXY" = "true" ]; then
    echo "Waiting for Mihomo proxy to be ready..."
    MAX_ATTEMPTS=60
    ATTEMPT=0
    PROXY_URL="http://mihomo:7890"
    TEST_URL="https://api.binance.com/api/v3/ping"

    while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -s --proxy "$PROXY_URL" --max-time 5 "$TEST_URL" > /dev/null 2>&1; then
        echo "✓ Mihomo proxy is ready"
        break
    fi

    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
        echo "✗ Error: Mihomo proxy failed to become ready after 5 minutes"
        echo "  Please check if Mihomo container is running and healthy"
        exit 1
    fi

    if [ $((ATTEMPT % 12)) -eq 0 ]; then
        echo "  Still waiting... (${ATTEMPT}/${MAX_ATTEMPTS})"
    fi
    sleep 5
    done
else
    echo "✓ Skipping proxy check (REQUIRE_PROXY=false)"
fi

# Step 4: Validate configuration files
echo ""
echo "[4/5] Validating configuration files..."
if timeout 30 python -c "from core.config_adapter import get_adapter; get_adapter()" 2>&1; then
    echo "✓ Configuration validation passed"
else
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 124 ]; then
        echo "✗ Error: Configuration validation timed out (30 seconds)"
    else
        echo "✗ Error: Configuration validation failed"
    fi
    echo "  Please check your YAML configuration files in config/"
    exit 1
fi

# Step 5: Execute backtest
echo ""
echo "[5/5] Running backtest (high-level engine)..."
echo "------------------------------------------"
if python main.py backtest --type high; then
    BACKTEST_EXIT_CODE=0
    echo "------------------------------------------"
    echo "✓ Backtest completed successfully"
else
    BACKTEST_EXIT_CODE=$?
    echo "------------------------------------------"
    echo "✗ Backtest failed with exit code: $BACKTEST_EXIT_CODE"
fi

# Step 4: Output result summary
echo ""
echo "[4/4] Backtest result summary:"
echo "------------------------------------------"
RESULT_DIR="output/backtest/result"
if [ -d "$RESULT_DIR" ]; then
    echo "Latest backtest results:"
    ls -lht "$RESULT_DIR"/*.json 2>/dev/null | head -3 | while read -r line; do
        echo "  $line"
    done

    LATEST_FILE=$(ls -t "$RESULT_DIR"/*.json 2>/dev/null | head -1)
    if [ -n "$LATEST_FILE" ]; then
        FILE_SIZE=$(du -h "$LATEST_FILE" | cut -f1)
        echo ""
        echo "Latest result: $LATEST_FILE"
        echo "File size: $FILE_SIZE"
    fi
else
    echo "  No results directory found at $RESULT_DIR"
fi

echo "=========================================="
echo "Backtest run completed"
echo "=========================================="

exit $BACKTEST_EXIT_CODE
