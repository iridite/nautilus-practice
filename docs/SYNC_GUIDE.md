# 自动同步到公开仓库

本文档说明如何使用自动同步系统将私有仓库的更新同步到公开展示仓库。

## 工作原理

系统通过 Git post-commit hook 实现全自动同步：

```
私有仓库提交 → Git Hook 触发 → 同步脚本执行 → 删除敏感内容 → 推送到公开仓库
```

## 文件说明

- `.git/hooks/post-commit`: Git 钩子，每次提交后自动触发
- `scripts/sync_to_public.sh`: 同步脚本，处理文件复制和敏感内容删除
- `.sync-config`: 配置文件，定义排除和删除规则

## 自动同步规则

### 排除的文件/目录（不会复制）
- `.env`, `test.env` - 环境变量文件
- `data/`, `output/`, `log/` - 数据和日志目录
- `.venv`, `__pycache__`, `*.pyc` - Python 环境和缓存
- `.idea`, `.vscode` - IDE 配置
- `.ruff_cache`, `.claude`, `tmp/` - 临时文件

### 删除的敏感文件（即使存在也会删除）
- `strategy/keltner_rs_breakout.py` - 核心策略实现
- `config/strategies/keltner_rs_breakout.yaml` - 策略配置
- `tests/test_keltner_rs_breakout.py` - 策略测试
- `docs/reviews/dk_alpha_trend_audit.md` - 策略审计文档

## 使用方法

### 自动同步（推荐）

正常提交代码即可，系统会自动同步：

```bash
git add .
git commit -m "feat: 添加新功能"
git push
```

同步会在后台异步执行，不会阻塞你的提交操作。

### 手动同步

如果需要手动触发同步：

```bash
./scripts/sync_to_public.sh
```

### 查看同步日志

```bash
tail -f /tmp/nautilus-sync.log
```

## 配置修改

编辑 `.sync-config` 文件来修改同步规则：

```bash
# 添加新的排除模式
EXCLUDE_PATTERNS+=(
    "new_sensitive_dir/"
)

# 添加新的敏感文件
SENSITIVE_FILES+=(
    "path/to/sensitive_file.py"
)
```

修改后立即生效，无需重启。

## 禁用自动同步

如果需要临时禁用自动同步：

```bash
# 方法 1: 删除 Git Hook
rm .git/hooks/post-commit

# 方法 2: 修改配置文件
# 编辑 .sync-config，设置 SYNC_ENABLED=false
```

## 故障排查

### 同步失败

1. 检查日志：`cat /tmp/nautilus-sync.log`
2. 确认公开仓库路径正确
3. 确认有推送权限

### Hook 未触发

1. 确认 Hook 文件存在：`ls -la .git/hooks/post-commit`
2. 确认 Hook 可执行：`chmod +x .git/hooks/post-commit`
3. 确认在 main 分支：`git branch`

### 敏感文件未删除

1. 检查 `.sync-config` 中的 `SENSITIVE_FILES` 配置
2. 确认文件路径相对于仓库根目录
3. 手动运行同步脚本测试

## 安全建议

1. **定期检查公开仓库**：确认没有敏感信息泄露
2. **更新排除规则**：添加新的敏感文件到配置中
3. **审查提交内容**：提交前确认不包含敏感信息
4. **备份私有仓库**：保持私有仓库的完整备份

## 维护

### 添加新的敏感文件

编辑 `scripts/sync_to_public.sh`，在 `SENSITIVE_FILES` 数组中添加：

```bash
SENSITIVE_FILES=(
    # ... 现有文件 ...
    "path/to/new_sensitive_file.py"
)
```

### 修改公开仓库路径

编辑 `scripts/sync_to_public.sh`，修改 `PUBLIC_REPO` 变量：

```bash
PUBLIC_REPO="/new/path/to/public/repo"
```

## 注意事项

- 同步是单向的：私有 → 公开
- 同步会删除公开仓库中的额外文件（使用 `--delete`）
- 提交信息会保留，但会添加同步标记
- 敏感文件删除后无法恢复，请确保配置正确
