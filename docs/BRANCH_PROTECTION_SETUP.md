# Branch Protection Rules Setup Guide

## 🔒 GitHub Branch Protection Rules

由于这是私有仓库，你需要在 GitHub 上手动配置分支保护规则。

### 配置步骤

1. **进入仓库设置**
   - 访问：https://github.com/iridite/nautilus_practice/settings/branches
   - 或：Settings → Branches → Branch protection rules

2. **添加规则**
   - 点击 "Add rule"
   - Branch name pattern: `main`

3. **启用以下保护规则**

   #### ✅ 必须启用的规则

   - [x] **Require a pull request before merging**
     - [x] Require approvals: 0（个人项目）或 1（团队项目）
     - [x] Dismiss stale pull request approvals when new commits are pushed
     - [x] Require review from Code Owners（可选）

   - [x] **Require status checks to pass before merging**
     - [x] Require branches to be up to date before merging
     - 添加必需的状态检查：
       - `Validate Branch Name`
       - `Run Tests`
       - `Lint Check`
       - `PR Size Check`

   - [x] **Require conversation resolution before merging**
     - 确保所有评论都被解决

   - [x] **Require linear history**
     - 强制使用 rebase 或 squash merge

   - [x] **Do not allow bypassing the above settings**
     - 即使是管理员也不能绕过规则

   #### ⚠️ 可选规则

   - [ ] **Require signed commits**（如果你使用 GPG 签名）
   - [ ] **Include administrators**（让管理员也遵守规则，推荐）
   - [ ] **Restrict who can push to matching branches**（团队项目推荐）

4. **保存规则**
   - 点击 "Create" 或 "Save changes"

---

## 🧪 测试保护规则

### 测试 1: 尝试直接推送到 main（应该被阻止）

```bash
# 这应该被 pre-push hook 阻止
git checkout main
echo "test" >> test.txt
git add test.txt
git commit -m "test"
git push origin main

# 预期输出：
# ❌ ERROR: Direct push to main branch is blocked!
```

### 测试 2: 通过 PR 流程（应该成功）

```bash
# 1. 创建 feature 分支
git checkout -b feat/test-branch-protection

# 2. 做一些修改
echo "test" >> test.txt
git add test.txt
git commit -m "feat: test branch protection"

# 3. 推送到远程
git push origin feat/test-branch-protection

# 4. 在 GitHub 上创建 PR
# 5. 等待 CI 检查通过
# 6. 合并 PR
```

### 测试 3: 错误的分支名（应该被警告）

```bash
# 这应该被 pre-push hook 警告
git checkout -b wrong-branch-name
git push origin wrong-branch-name

# 预期输出：
# ⚠️  WARNING: Branch name doesn't follow convention
```

---

## 📋 快速参考

### 允许的分支名格式

```
feat/<description>     # 新功能
fix/<description>      # Bug 修复
refactor/<description> # 重构
chore/<description>    # 配置/工具
docs/<description>     # 文档
test/<description>     # 测试
```

### 工作流命令

```bash
# 创建新分支
git checkout -b feat/your-feature

# 本地检查（推送前）
./scripts/check.sh

# 推送到远程
git push origin feat/your-feature

# 在 GitHub 上创建 PR
# 等待 CI 通过后合并
```

---

## 🔧 故障排除

### 问题 1: Pre-push hook 不工作

```bash
# 确保 hook 有执行权限
chmod +x .git/hooks/pre-push

# 测试 hook
.git/hooks/pre-push
```

### 问题 2: CI 检查失败

```bash
# 本地运行相同的检查
./scripts/check.sh

# 修复问题后重新推送
git push origin feat/your-feature
```

### 问题 3: PR 被阻止合并

- 检查 CI 状态，确保所有���查通过
- 检查是否有未解决的评论
- 检查 PR 大小是否超过限制

---

## 📚 相关文档

- [开发规则](./DEVELOPMENT_RULES.md) - 详细的开发规范
- [PR 模板](../.github/PULL_REQUEST_TEMPLATE.md) - PR 提交模板
- [CI 配置](../.github/workflows/pr-checks.yml) - CI 检查配置

---

## ✅ 配置完成检查清单

- [ ] GitHub 分支保护规则已配置
- [ ] Pre-push hook 已安装并可执行
- [ ] 本地检查脚本可用（`./scripts/check.sh`）
- [ ] 已测试直接推送到 main 被阻止
- [ ] 已测试 PR 流程正常工作
- [ ] 团队成员已了解新规则（如果是团队项目）

---

## 🎯 下一步

配置完成后：

1. 将这些变更提交到一个 feature 分支
2. 创建第一个 PR 来测试新流程
3. 确认所有 CI 检查正常工作
4. 合并后，新规则正式生效

```bash
# 示例：提交这些配置变更
git checkout -b chore/setup-branch-protection
git add .
git commit -m "chore: setup branch protection rules and CI checks"
git push origin chore/setup-branch-protection

# 然后在 GitHub 上创建 PR
```
