#!/bin/bash
# 自动同步私有仓库到公开仓库
# 用途：去除敏感内容后同步到公开展示仓库

set -e

# 默认配置
PRIVATE_REPO="/home/yixian/Projects/nautilus-practice"
CONFIG_FILE="$PRIVATE_REPO/.sync-config"

# 加载配置文件
if [ ! -f "$CONFIG_FILE" ]; then
    echo "错误: 配置文件不存在: $CONFIG_FILE"
    exit 1
fi

source "$CONFIG_FILE"

# 使用配置文件中的值
PUBLIC_REPO="${PUBLIC_REPO_PATH}"
LOG_FILE="${LOG_FILE:-/tmp/nautilus-sync.log}"

# 检查是否启用同步
if [ "$SYNC_ENABLED" != "true" ]; then
    echo "同步已禁用 (SYNC_ENABLED=$SYNC_ENABLED)"
    exit 0
fi

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

# 排除敏感文件
for file in "${SENSITIVE_FILES[@]}"; do
    RSYNC_EXCLUDE="$RSYNC_EXCLUDE --exclude=$file"
done

# 同步文件到公开仓库
log "正在同步文件..."
rsync -av --delete $RSYNC_EXCLUDE "$PRIVATE_REPO/" "$PUBLIC_REPO/" >> "$LOG_FILE" 2>&1 || error_exit "rsync 失败"

# 进入公开仓库
cd "$PUBLIC_REPO" || error_exit "无法进入公开仓库"

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

# 推送到远程（带自动 rebase 处理）
log "正在推送到远程仓库..."
if ! git push origin main >> "$LOG_FILE" 2>&1; then
    log "推送失败，尝试 pull --rebase 后重新推送..."

    # 先 fetch 远程更新
    git fetch origin >> "$LOG_FILE" 2>&1 || error_exit "fetch 失败"

    # 尝试 rebase
    if git rebase origin/main >> "$LOG_FILE" 2>&1; then
        log "rebase 成功，重新推送..."
        git push origin main >> "$LOG_FILE" 2>&1 || error_exit "rebase 后推送仍然失败"
    else
        # rebase 失败（可能有冲突），使用 force-with-lease
        log "rebase 失败，使用 force-with-lease 强制推送..."
        git rebase --abort >> "$LOG_FILE" 2>&1
        git push --force-with-lease origin main >> "$LOG_FILE" 2>&1 || error_exit "强制推送失败"
    fi
fi

log "========== 同步完成 =========="
