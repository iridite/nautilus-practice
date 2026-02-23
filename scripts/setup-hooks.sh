#!/bin/bash

# Setup Git Hooks for nautilus-practice
# This script installs pre-commit and pre-push hooks to enforce branch management rules

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_SOURCE="$SCRIPT_DIR/git-hooks"
HOOKS_TARGET="$PROJECT_ROOT/.git/hooks"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 Setting up Git Hooks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if .git directory exists
if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo "❌ Error: .git directory not found"
    echo "   Please run this script from within the git repository"
    exit 1
fi

# Check if hooks source directory exists
if [ ! -d "$HOOKS_SOURCE" ]; then
    echo "❌ Error: hooks source directory not found: $HOOKS_SOURCE"
    exit 1
fi

# Install pre-commit hook
if [ -f "$HOOKS_SOURCE/pre-commit" ]; then
    echo "📝 Installing pre-commit hook..."
    cp "$HOOKS_SOURCE/pre-commit" "$HOOKS_TARGET/pre-commit"
    chmod +x "$HOOKS_TARGET/pre-commit"
    echo "   ✓ pre-commit hook installed"
else
    echo "⚠️  Warning: pre-commit hook not found in $HOOKS_SOURCE"
fi

# Install pre-push hook
if [ -f "$HOOKS_SOURCE/pre-push" ]; then
    echo "📝 Installing pre-push hook..."
    cp "$HOOKS_SOURCE/pre-push" "$HOOKS_TARGET/pre-push"
    chmod +x "$HOOKS_TARGET/pre-push"
    echo "   ✓ pre-push hook installed"
else
    echo "⚠️  Warning: pre-push hook not found in $HOOKS_SOURCE"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Git hooks setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Installed hooks:"
echo "  • pre-commit: Blocks commits to main branch"
echo "  • pre-push: Blocks pushes to main branch"
echo ""
echo "To bypass hooks (emergency only):"
echo "  git commit --no-verify"
echo "  git push --no-verify"
echo ""
