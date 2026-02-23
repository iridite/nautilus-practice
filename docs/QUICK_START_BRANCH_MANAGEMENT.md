# 🚀 快速开始：严格分支管理

## 📖 概述

本项目已启用**严格的分支管理规则**，所有代码变更必须通过 Pull Request 流程。

---

## ⚡ 快速工作流

### 1️⃣ 创建新功能

```bash
# 确保在最新的 main 分支
git checkout main
git pull origin main

# 创建 feature 分支（注意命名规范！）
git checkout -b feat/your-feature-name
```

### 2️⃣ 开发和测试

```bash
# 开发你的功能...

# 运行本地检查（推荐在提交前运行）
./scripts/check.sh

# 提交变更
git add .
git commit -m "feat: add your feature description"
```

### 3️⃣ 推送和创建 PR

```bash
# 推送到远程
git push origin feat/your-feature-name

# 在 GitHub 上创建 Pull Request
# 等待 CI 检查通过
# 合并后删除分支
```

---

## 🎯 分支命名规范

**必须**使用以下格式：`<type>/<description>`

| 类型 | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat/add-rsi-strategy` |
| `fix` | Bug 修复 | `fix/position-sizing-bug` |
| `refactor` | 重构 | `refactor/simplify-config` |
| `chore` | 配置/工具 | `chore/update-deps` |
| `docs` | 文档 | `docs/update-readme` |
| `test` | 测试 | `test/add-unit-tests` |

---

## ✅ 本地检查脚本

在推送前运行：

```bash
./scripts/check.sh
```

这会检查：
- ✅ 分支命名是否正确
- ✅ 代码风格（ruff check）
- ✅ 代码格式（ruff format）
- ✅ 所有测试是否通过
- ✅ PR 大小是否合理

---

## 🚫 严格禁止

### ❌ 直接在 main 分支提交

```bash
# 这会被 pre-push hook 阻止
git checkout main
git commit -m "quick fix"
git push origin main  # ❌ 被拒绝
```

### ❌ 错误的分支命名

```bash
# 这些都是错误的
git checkout -b new-feature        # ❌ 缺少类型前缀
git checkout -b feature_new_thing  # ❌ 使用了下划线
git checkout -b 新功能              # ❌ 使用了中文
```

### ❌ 超大 PR

- 净增加代码 > 1000 行 → CI 拒绝
- 修改文件 > 20 个 → 警告

---

## 🔧 故障排除

### Pre-push hook 不工作？

```bash
chmod +x .git/hooks/pre-push
```

### 检查脚本不工作？

```bash
chmod +x scripts/check.sh
```

### CI 检查失败？

```bash
# 本地运行相同的检查
./scripts/check.sh

# 修复问题后重新推送
git push origin feat/your-feature
```

---

## 📚 详细文档

- [开发规则详解](./DEVELOPMENT_RULES.md)
- [分支保护设置](./BRANCH_PROTECTION_SETUP.md)
- [PR 模板](../.github/PULL_REQUEST_TEMPLATE.md)

---

## 🎓 示例工作流

```bash
# 1. 开始新功能
git checkout main
git pull origin main
git checkout -b feat/momentum-strategy

# 2. 开发
# ... 编写代码 ...

# 3. 本地检查
./scripts/check.sh

# 4. 提交
git add .
git commit -m "feat(strategy): add momentum strategy with RSI filter"

# 5. 推送
git push origin feat/momentum-strategy

# 6. 在 GitHub 创建 PR
# 7. 等待 CI 通过
# 8. 合并

# 9. 清理
git checkout main
git pull origin main
git branch -d feat/momentum-strategy
```

---

## ⚠️ 重要提醒

1. **永远不要直接在 main 分支提交**
2. **所有变更必须通过 PR**
3. **所有 PR 必须通过 CI 检查**
4. **保持 PR 小而专注**（< 500 行）

遵循这些规则，你的代码库会更加稳定和可维护！
