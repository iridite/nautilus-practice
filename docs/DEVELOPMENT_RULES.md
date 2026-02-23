# 开发规则与分支管理

## 🎯 核心原则

**严格禁止直接在 main 分支开发！**

所有新功能、修复、重构都必须：
1. 在独立的 feature 分支开发
2. 通过 Pull Request 合并
3. 经过 CI 检查和代码审查
4. 测试全部通过后才能合并

---

## 📋 分支命名规范

### 必须遵循的格式

```
<type>/<short-description>
```

### 类型（type）

| 类型 | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat/add-rsi-strategy` |
| `fix` | Bug 修复 | `fix/position-sizing-error` |
| `refactor` | 代码重构（不改变功能） | `refactor/simplify-config` |
| `chore` | 配置、依赖更新 | `chore/update-dependencies` |
| `docs` | 文档更新 | `docs/update-readme` |
| `test` | 测试相关 | `test/add-strategy-tests` |

### 命名要求

- ✅ 使用小写字母
- ✅ 使用连字符（`-`）分隔单词
- ✅ 简短但描述清楚（3-5 个单词）
- ❌ 不要使用下划线（`_`）
- ❌ 不要使用中文

### 示例

```bash
# ✅ 好的分支名
feat/momentum-strategy
fix/backtest-data-loading
refactor/remove-unused-components
docs/add-strategy-guide

# ❌ 坏的分支名
feature_new_strategy          # 使用了下划线
fix-bug                       # 太模糊
feat/add-super-awesome-ml-based-strategy-with-ai  # 太长
新功能                        # 使用了中文
```

---

## 🔄 开发工作流

### 1. 创建新分支

```bash
# 确保在 main 分支且是最新的
git checkout main
git pull origin main

# 创建并切换到新分支
git checkout -b feat/your-feature-name
```

### 2. 开发和提交

```bash
# 开发你的功能...

# 提交变更（遵循 Conventional Commits）
git add .
git commit -m "feat(strategy): add RSI momentum strategy"

# 推送到远程
git push origin feat/your-feature-name
```

### 3. 创建 Pull Request

1. 在 GitHub 上创建 PR
2. 填写 PR 模板（自动加载）
3. 等待 CI 检查通过
4. 请求代码审查（如果是团队项目）

### 4. 合并到 main

```bash
# PR 被批准后，在 GitHub 上点击 "Merge"
# 选择 "Squash and merge" 或 "Rebase and merge"

# 合并后，删除远程分支
git push origin --delete feat/your-feature-name

# 本地切换回 main 并更新
git checkout main
git pull origin main

# 删除本地分支
git branch -d feat/your-feature-name
```

---

## ✅ PR 合并前的强制检查

### 自动检查（CI）

以下检查必须全部通过，否则 PR 无法合并：

1. **分支命名检查**
   - 分支名必须符合 `<type>/<description>` 格式

2. **测试检查**
   - 所有单元测试必须通过
   - 测试覆盖率不能低于当前水平（28%）

3. **代码质量检查**
   - Ruff lint 检查通过
   - Ruff format 检查通过

4. **PR 大小检查**
   - 净增加代码 < 500 行（警告）
   - 净增加代码 < 1000 行（强制）
   - 修改文件 < 20 个（警告）

### 手动检查（开发者自查）

在创建 PR 前，请确认：

- [ ] 本地运行所有测试通过
- [ ] 代码已格式化（`uv run ruff format .`）
- [ ] 没有 lint 错误（`uv run ruff check .`）
- [ ] 添加了必要的测试（如果是新功能）
- [ ] 更新了相关文档（如果需要）
- [ ] PR 描述清晰，说明了变更的原因和影响

---

## 🚫 严格禁止的行为

### 1. 直接在 main 分支提交

```bash
# ❌ 绝对禁止
git checkout main
# ... 修改代码 ...
git commit -m "quick fix"
git push origin main
```

**后果**：CI 会拒绝这个 push

### 2. 绕过 PR 流程

```bash
# ❌ 绝对禁止
git checkout main
git merge feat/my-feature --no-ff
git push origin main
```

**后果**：违反开发规范，可能导致未经测试的代码进入 main

### 3. 创建超大 PR

- ❌ 一次性添加 1000+ 行代码
- ❌ 一次性修改 20+ 个文件
- ❌ 混合多个不相关的变更

**后果**：CI 会拒绝，且难以审查

### 4. 提交未测试的代码

```bash
# ❌ 绝对禁止
git commit -m "feat: add new strategy (untested)"
```

**后果**：CI 会失败，PR 无法合并

---

## 📏 PR 大小指南

### 理想的 PR 大小

| 指标 | 理想值 | 最大值 |
|------|--------|--------|
| 净增加代码 | < 200 行 | < 500 行 |
| 修改文件数 | < 5 个 | < 20 个 |
| 提交数 | 1-3 个 | 不限 |
| 审查时间 | < 15 分钟 | < 30 分钟 |

### 如何拆分大 PR

如果你的变更很大，考虑拆分为多个 PR：

**示例：添加新策略**

```
PR 1: feat/add-rsi-indicator (添加 RSI 指标组件)
  ├── strategy/common/indicators/rsi.py
  └── tests/test_rsi.py

PR 2: feat/add-rsi-strategy (使用 RSI 实现策略)
  ├── strategy/rsi_momentum.py
  ├── config/strategies/rsi_momentum.yaml
  └── tests/test_rsi_momentum.py

PR 3: docs/add-rsi-strategy-guide (添加文档)
  └── docs/strategies/rsi_momentum.md
```

**好处**：
- 每个 PR 都很小，容易审查
- 可以独立测试和合并
- 出问题容易回滚

---

## 🔧 本地开发辅助工具

### Pre-commit Hook（推荐）

创建 `.git/hooks/pre-commit`：

```bash
#!/bin/bash

echo "🔍 Running pre-commit checks..."

# 运行 ruff 检查
echo "📝 Checking code style..."
uv run ruff check . || {
    echo "❌ Ruff check failed. Please fix the issues."
    exit 1
}

# 运行 ruff 格式化检查
echo "🎨 Checking code format..."
uv run ruff format --check . || {
    echo "❌ Code is not formatted. Run 'uv run ruff format .' to fix."
    exit 1
}

# 运行测试
echo "🧪 Running tests..."
uv run python -m unittest discover -s tests -p "test_*.py" -v || {
    echo "❌ Tests failed. Please fix the failing tests."
    exit 1
}

echo "✅ All checks passed!"
```

### 快速检查脚本

创建 `scripts/check.sh`：

```bash
#!/bin/bash

set -e

echo "🔍 Running all checks..."

echo "📝 1/3 Linting..."
uv run ruff check .

echo "🎨 2/3 Formatting..."
uv run ruff format --check .

echo "🧪 3/3 Testing..."
uv run python -m unittest discover -s tests -p "test_*.py" -v

echo "✅ All checks passed! Ready to push."
```

使用方法：

```bash
chmod +x scripts/check.sh
./scripts/check.sh
```

---

## 🎓 最佳实践

### 1. 小步快跑

- ✅ 频繁提交小的、完整的变更
- ✅ 每个 PR 只做一件事
- ❌ 不要积累大量变更后一次性提交

### 2. 测试驱动

- ✅ 先写测试，再写实现
- ✅ 确保测试覆盖核心逻辑
- ❌ 不要提交未测试的代码

### 3. 清晰的提交信息

```bash
# ✅ 好的提交信息
feat(strategy): add RSI momentum strategy with 14-period lookback
fix(backtest): correct position sizing calculation for leverage
refactor(config): simplify YAML loading logic

# ❌ 坏的提交信息
update
fix bug
wip
```

### 4. 及时同步 main

```bash
# 定期将 main 的变更合并到你的分支
git checkout feat/your-feature
git fetch origin
git rebase origin/main
```

---

## 🚨 紧急修复流程

如果 main 分支出现严重 bug，需要紧急修复：

```bash
# 1. 创建 hotfix 分支
git checkout main
git pull origin main
git checkout -b fix/critical-bug-description

# 2. 修复 bug
# ... 修改代码 ...

# 3. 测试
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 4. 提交并推送
git commit -m "fix: resolve critical bug in position sizing"
git push origin fix/critical-bug-description

# 5. 创建 PR，标记为 "urgent"
# 6. 快速审查后合并
```

---

## 📊 违规处理

### 第一次违规
- ⚠️ 警告
- 📝 要求重新提交符合规范的 PR

### 第二次违规
- ⚠️⚠️ 严重警告
- 📚 要求重新学习开发规范

### 第三次违规
- 🚫 暂停提交权限
- 👥 需要团队讨论

---

## 📚 相关文档

- [Git Commit 规范](https://www.conventionalcommits.org/)
- [GitHub Flow](https://guides.github.com/introduction/flow/)
- [Code Review 最佳实践](https://google.github.io/eng-practices/review/)

---

## ❓ 常见问题

### Q: 我可以在 main 分支上做小的修改吗？
**A**: 不可以。即使是一行代码的修改，也必须通过 PR 流程。

### Q: 如果 CI 检查失败怎么办？
**A**: 修复问题后重新推送到同一个分支，CI 会自动重新运行。

### Q: 我可以合并自己的 PR 吗？
**A**: 如果是个人项目，可以。但建议等待至少 24 小时，给自己时间重新审视代码。

### Q: PR 被拒绝了怎么办？
**A**: 根据反馈修改代码，重新推送到同一个分支，PR 会自动更新。

---

## 🎯 总结

**记住这三条铁律**：

1. **永远不要直接在 main 分支提交**
2. **所有变更必须通过 PR**
3. **所有 PR 必须通过 CI 检查**

遵循这些规则，你的代码库会更加稳定、可维护，团队协作也会更加顺畅。
