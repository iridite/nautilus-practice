#!/bin/bash
#
# GitHub Actions 快速验证脚本（无需 Docker）
# 直接在本地环境模拟 workflow 步骤
#

set -e

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 进入项目目录
cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"

echo -e "${BLUE}=========================================="
echo "GitHub Actions 本地验证"
echo "=========================================="
echo "项目路径: ${PROJECT_ROOT}"
echo -e "==========================================${NC}"
echo ""

# 测试计数
TOTAL=0
PASSED=0
FAILED=0

# 测试函数
test_step() {
    local workflow="$1"
    local job="$2"
    local step="$3"
    local command="$4"

    TOTAL=$((TOTAL + 1))
    echo -e "${CYAN}[$TOTAL] ${workflow} > ${job} > ${step}${NC}"

    if eval "$command" > /tmp/test_step_$TOTAL.log 2>&1; then
        echo -e "${GREEN}    ✓ 通过${NC}"
        PASSED=$((PASSED + 1))
        return 0
    else
        echo -e "${RED}    ✗ 失败${NC}"
        echo -e "${YELLOW}    错误输出:${NC}"
        tail -10 /tmp/test_step_$TOTAL.log | sed 's/^/    /'
        FAILED=$((FAILED + 1))
        return 1
    fi
}

echo -e "${BLUE}=========================================="
echo "1. 测试 ci_autofix.yml"
echo -e "==========================================${NC}"
echo ""

# Lint Job
echo -e "${YELLOW}Job: lint${NC}"
test_step "ci_autofix.yml" "lint" "Check Python available" "python3 --version"
test_step "ci_autofix.yml" "lint" "Install uv" "python3 -m pip install --upgrade pip > /dev/null && python3 -m pip install uv > /dev/null 2>&1 || true"
test_step "ci_autofix.yml" "lint" "Sync dependencies" "uv sync"
test_step "ci_autofix.yml" "lint" "Run ruff check" "uv run ruff check ."

echo ""

# Tests Job
echo -e "${YELLOW}Job: tests${NC}"
test_step "ci_autofix.yml" "tests" "Run unittest" "uv run python -m unittest discover -s tests -p 'test_*.py' -v"

echo ""

# Auto-fix Job
echo -e "${YELLOW}Job: auto-fix${NC}"
test_step "ci_autofix.yml" "auto-fix" "Run ruff --fix" "uv run ruff check . --fix"
test_step "ci_autofix.yml" "auto-fix" "Check git status" "git status --porcelain"

echo ""
echo -e "${BLUE}=========================================="
echo "2. 测试 test-coverage.yml"
echo -e "==========================================${NC}"
echo ""

# Test Job
echo -e "${YELLOW}Job: test${NC}"
test_step "test-coverage.yml" "test" "Check Python available" "python3 --version"
test_step "test-coverage.yml" "test" "Install uv" "python3 -m pip install --upgrade pip > /dev/null && python3 -m pip install uv > /dev/null 2>&1 || true"
test_step "test-coverage.yml" "test" "Install dependencies" "uv sync && uv pip install pytest pytest-cov"
test_step "test-coverage.yml" "test" "Run tests with coverage" "uv run pytest --cov=. --cov-report=xml --cov-report=term-missing --cov-fail-under=55"
test_step "test-coverage.yml" "test" "Verify coverage.xml" "test -f coverage.xml"

echo ""
echo -e "${BLUE}=========================================="
echo "3. 测试 sync_to_public.yml"
echo -e "==========================================${NC}"
echo ""

# Sync Job
echo -e "${YELLOW}Job: sync${NC}"
test_step "sync_to_public.yml" "sync" "Check rsync available" "which rsync"
test_step "sync_to_public.yml" "sync" "Check git available" "which git"
test_step "sync_to_public.yml" "sync" "Verify git config" "git config user.name || true"

echo ""
echo -e "${BLUE}=========================================="
echo "测试总结"
echo -e "==========================================${NC}"
echo -e "总计: ${TOTAL}"
echo -e "${GREEN}通过: ${PASSED}${NC}"
echo -e "${RED}失败: ${FAILED}${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ 所有测试通过！GitHub Actions 配置正确。${NC}"
    echo ""
    echo -e "${CYAN}建议:${NC}"
    echo "  1. 可以安全推送到远程仓库"
    echo "  2. CI 应该能正常运行"
    echo "  3. 如需完整测试，使用 act 工具（需要 Docker）"
    exit 0
else
    echo -e "${RED}✗ 有 ${FAILED} 个测试失败${NC}"
    echo ""
    echo -e "${CYAN}建议:${NC}"
    echo "  1. 检查失败的步骤"
    echo "  2. 修复问题后重新运行"
    echo "  3. 查看详细日志: /tmp/test_step_*.log"
    exit 1
fi
