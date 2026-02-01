#!/bin/bash
# 自动同步私有仓库到公开仓库
# 用途：去除敏感内容后同步到公开展示仓库

set -e

# 配置
PRIVATE_REPO="/home/yixian/Projects/nautilus-practice"
PUBLIC_REPO="/home/yixian/Projects/Nautilus-Ops-Integrated"
LOG_FILE="/tmp/nautilus-sync.log"

# 需要排除的文件和目录
EXCLUDE_PATTERNS=(
    ".git"
    ".env"
    "test.env"
    "data/"
    "output/"
    "log/"
    ".venv"
    "__pycache__"
    "*.pyc"
    ".idea"
    ".vscode"
    ".DS_Store"
    ".aider*"
    ".langgraph_api"
    ".ruff_cache"
    ".claude"
    "tmp/"
)

# 需要删除的敏感文件（即使在源仓库存在）
SENSITIVE_FILES=(
    "strategy/keltner_rs_breakout.py"
    "config/strategies/keltner_rs_breakout.yaml"
    "tests/test_keltner_rs_breakout.py"
    "docs/reviews/dk_alpha_trend_audit.md"
)

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 错误处理
error_exit() {
    log "错误: $1"
    exit 1
}

# 开始同步
log "========== 开始同步到公开仓库 =========="

# 检查仓库是否存在
[ -d "$PRIVATE_REPO" ] || error_exit "私有仓库不存在: $PRIVATE_REPO"
[ -d "$PUBLIC_REPO" ] || error_exit "公开仓库不存在: $PUBLIC_REPO"

# 进入私有仓库
cd "$PRIVATE_REPO" || error_exit "无法进入私有仓库"

# 获取最新提交信息
COMMIT_MSG=$(git log -1 --pretty=%B)
COMMIT_HASH=$(git rev-parse --short HEAD)

log "同步提交: $COMMIT_HASH - $COMMIT_MSG"

# 构建 rsync 排除参数
RSYNC_EXCLUDE=""
for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    RSYNC_EXCLUDE="$RSYNC_EXCLUDE --exclude=$pattern"
done

# 同步文件到公开仓库
log "正在同步文件..."
rsync -av --delete $RSYNC_EXCLUDE "$PRIVATE_REPO/" "$PUBLIC_REPO/" >> "$LOG_FILE" 2>&1 || error_exit "rsync 失败"

# 进入公开仓库
cd "$PUBLIC_REPO" || error_exit "无法进入公开仓库"

# 删除敏感文件
log "正在删除敏感文件..."
for file in "${SENSITIVE_FILES[@]}"; do
    if [ -f "$file" ]; then
        rm -f "$file"
        log "已删除: $file"
    fi
done

# 检查是否有变更
if [ -z "$(git status --porcelain)" ]; then
    log "没有变更需要提交"
    log "========== 同步完成 =========="
    exit 0
fi

# 提交变更
log "正在提交变更..."
git add -A
git commit -m "sync: $COMMIT_MSG

Synced from private repo: $COMMIT_HASH
Auto-generated commit - sensitive content removed" >> "$LOG_FILE" 2>&1 || error_exit "提交失败"

# 推送到远程
log "正在推送到远程仓库..."
git push origin main >> "$LOG_FILE" 2>&1 || error_exit "推送失败"

log "========== 同步完成 =========="
