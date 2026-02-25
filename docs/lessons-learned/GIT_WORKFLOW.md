# Git 工作流与 CI 策略

本文档记录 AI Agent 在 Git 和 CI 环境中的工作规范。

## 一般原则

1. **不自主创建或合并 PR**: AI agent 不得自行创建或合并 PR
2. **推送控制**: 仅在明确授权后才能推送到远程
3. **测试优先**: 推送前运行完整测试套件
4. **变更透明**: 提供简洁的补丁摘要（文件、动机、测试结果）

## ⚠️ 关键教训（从实际错误中学到）

**问题**: AI Agent 两次直接在 main 分支提交代码，违反分支管理规则

**根本原因**:
- pre-push hook **只能阻止推送操作**，**无法阻止本地提交**
- AI Agent 在开始工作时没有先创建分支
- 依赖 hook 提醒而非主动遵守规则

**正确流程（必须严格遵守）**:
1. **开始任何工作前**，先检查当前分支：`git branch --show-current`
2. **如果在 main 分支**，立即创建新分支：`git checkout -b <type>/<description>`
3. **完成工作后**，推送分支并创建 PR
4. **绝不直接在 main 分支提交**，即使是小改动

**补救流程**（如果已经在 main 提交）:
```bash
# 1. 创建新分支指向错误的 commit
git branch <type>/<description> <commit-hash>

# 2. 重置 main 到上一个正确的 commit
git reset --hard <previous-commit>

# 3. 切换到新分支继续工作
git checkout <type>/<description>

# 4. 推送新分支
git push -u origin <type>/<description>
```

## 分支命名规范

- `feat/`: 新功能
- `fix/`: Bug 修复
- `refactor/`: 代码重构
- `docs/`: 文档更新
- `test/`: 测试相关
- `chore/`: 构建、工具、依赖更新

## Commit Message 规范

遵循 Conventional Commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**类型**:
- `feat`: 新功能
- `fix`: Bug 修复
- `refactor`: 重构
- `docs`: 文档
- `test`: 测试
- `chore`: 构建/工具

**示例**:
```
feat(strategy): add filter statistics and zero-trade diagnostics

- Add filter_stats tracking for 8 filters
- Implement _log_filter_statistics() with auto-warning
- Use ERROR level for 100% blocked warnings
- Add detailed debug logs for each filter

Resolves: #123
```

## CI/CD 集成

### GitHub Actions 工作流

1. **PR 检查** (`.github/workflows/pr-checks.yml`)
   - 运行测试套件
   - 代码质量检查
   - 覆盖率报告

2. **自动同步** (`.github/workflows/sync-main-to-dev.yml`)
   - main → dev 自动同步
   - 避免分支分歧

### Pre-commit Hooks

- **pre-push**: 阻止直接推送到 main/dev
- **pre-commit**: 代码格式化、linting

## 最佳实践

1. **小步提交**: 每个 commit 只做一件事
2. **描述性消息**: 清晰说明"为什么"而非"是什么"
3. **测试先行**: 提交前确保测试通过
4. **及时推送**: 完成功能后及时推送，避免冲突
5. **定期同步**: 从 main 拉取最新变更

## 常见错误与解决

### 错误 1: 忘记创建分支

**症状**: 在 main 分支直接提交

**解决**: 使用上述补救流程

### 错误 2: Commit 消息不规范

**症状**: 消息模糊，如 "fix bug" 或 "update code"

**解决**: 使用 Conventional Commits 格式，描述具体变更

### 错误 3: 大量文件一次提交

**症状**: 单个 commit 包含多个不相关的变更

**解决**: 使用 `git add -p` 分批提交

### 错误 4: 推送前未测试

**症状**: CI 失败，需要额外的修复 commit

**解决**: 本地运行 `pytest` 确保测试通过

## 相关资源

- [Conventional Commits](https://www.conventionalcommits.org/)
- [Git Best Practices](https://git-scm.com/book/en/v2)
- [GitHub Flow](https://guides.github.com/introduction/flow/)
