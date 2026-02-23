#!/bin/bash

set -e

echo "🔍 Running all pre-push checks..."
echo ""

# 检查是否在 main 分支
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" = "main" ]; then
    echo "❌ ERROR: You are on the main branch!"
    echo "Please create a feature branch:"
    echo "  git checkout -b feat/your-feature-name"
    exit 1
fi

# 检查分支命名
if [[ ! "$CURRENT_BRANCH" =~ ^(feat|fix|refactor|chore|docs|test)/.+ ]]; then
    echo "❌ ERROR: Invalid branch name: $CURRENT_BRANCH"
    echo "Branch name must follow pattern: feat/*, fix/*, refactor/*, chore/*, docs/*, test/*"
    echo ""
    echo "Examples:"
    echo "  feat/add-rsi-strategy"
    echo "  fix/position-sizing-bug"
    echo "  refactor/simplify-config"
    exit 1
fi

echo "✅ Branch name is valid: $CURRENT_BRANCH"
echo ""

# 1. Linting
echo "📝 [1/3] Running ruff check..."
if ! uv run ruff check .; then
    echo ""
    echo "❌ Ruff check failed. Please fix the issues above."
    echo "Tip: Run 'uv run ruff check --fix .' to auto-fix some issues"
    exit 1
fi
echo "✅ Linting passed"
echo ""

# 2. Formatting
echo "🎨 [2/3] Checking code format..."
if ! uv run ruff format --check .; then
    echo ""
    echo "❌ Code is not formatted properly."
    echo "Run 'uv run ruff format .' to fix formatting"
    exit 1
fi
echo "✅ Formatting passed"
echo ""

# 3. Testing
echo "🧪 [3/3] Running tests..."
if ! uv run python -m unittest discover -s tests -p "test_*.py" -v; then
    echo ""
    echo "❌ Tests failed. Please fix the failing tests."
    exit 1
fi
echo "✅ All tests passed"
echo ""

# 检查 PR 大小（如果有未提交的变更）
if ! git diff --quiet HEAD; then
    echo "⚠️  You have uncommitted changes. Please commit them first."
    echo ""
fi

# 统计变更
CHANGED_FILES=$(git diff --name-only origin/main...HEAD 2>/dev/null | wc -l || echo "0")
if [ "$CHANGED_FILES" -gt 0 ]; then
    ADDED_LINES=$(git diff --numstat origin/main...HEAD 2>/dev/null | awk '{sum+=$1} END {print sum}' || echo "0")
    DELETED_LINES=$(git diff --numstat origin/main...HEAD 2>/dev/null | awk '{sum+=$2} END {print sum}' || echo "0")
    NET_LINES=$((ADDED_LINES - DELETED_LINES))

    echo "📊 Change Statistics:"
    echo "  - Changed files: $CHANGED_FILES"
    echo "  - Added lines: $ADDED_LINES"
    echo "  - Deleted lines: $DELETED_LINES"
    echo "  - Net change: $NET_LINES lines"
    echo ""

    if [ $NET_LINES -gt 500 ]; then
        echo "⚠️  WARNING: Large PR detected ($NET_LINES lines net)"
        echo "Consider breaking it into smaller PRs for easier review"
        echo ""
    fi

    if [ $NET_LINES -gt 1000 ]; then
        echo "❌ ERROR: PR is too large ($NET_LINES lines net)"
        echo "Please break it into smaller, focused PRs"
        exit 1
    fi

    if [ $CHANGED_FILES -gt 20 ]; then
        echo "⚠️  WARNING: Many files changed ($CHANGED_FILES files)"
        echo "Consider breaking it into smaller PRs"
        echo ""
    fi
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ All checks passed! Ready to push."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo "  1. git push origin $CURRENT_BRANCH"
echo "  2. Create a Pull Request on GitHub"
echo "  3. Wait for CI checks to pass"
echo "  4. Merge after approval"
