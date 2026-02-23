# 分支管理规则配置总结

## ✅ 已完成的配置

### 1. 本地保护机制

#### Pre-push Hook (`.git/hooks/pre-push`)
- ✅ 阻止直接推送到 main 分支
- ✅ 检查分支命名规范
- ✅ 自动执行，无需手动运行

#### 检查脚本 (`scripts/check.sh`)
- ✅ 检查分支命名
- ✅ 运行 ruff lint
- ✅ 检查代码格式
- ✅ 运行所有测试
- ✅ 检查 PR 大小
- ✅ 提供详细的统计信息

### 2. CI/CD 保护机制

#### GitHub Actions (`.github/workflows/pr-checks.yml`)
- ✅ 验证分支命名
- ✅ 运行测试套件
- ✅ 检查代码质量（lint + format）
- ✅ 检查 PR 大小（< 1000 行强制，< 500 行警告）
- ✅ 阻止直接推送到 main

### 3. PR 模板

#### Pull Request Template (`.github/PULL_REQUEST_TEMPLATE.md`)
- ✅ 标准化的 PR 描述格式
- ✅ 强制的检查清单
- ✅ 反过度工程化检查项
- ✅ 变更类型分类

### 4. 文档

#### 开发规则 (`docs/DEVELOPMENT_RULES.md`)
- ✅ 完整的分支管理规范
- ✅ 工作流程说明
- ✅ 最佳实践指南
- ✅ 常见问题解答

#### 快速开始 (`docs/QUICK_START_BRANCH_MANAGEMENT.md`)
- ✅ 快速参考指南
- ✅ 常用命令
- ✅ 故障排除

#### 配置指南 (`docs/BRANCH_PROTECTION_SETUP.md`)
- ✅ GitHub 分支保护设置步骤
- ✅ 测试方法
- ✅ 配置检查清单

---

## 🎯 规则概览

### 强制规则（违反会被阻止）

1. **禁止直接推送到 main**
   - Pre-push hook 会阻止
   - GitHub Actions 会拒绝

2. **分支命名必须符合规范**
   - 格式：`<type>/<description>`
   - 类型：feat, fix, refactor, chore, docs, test

3. **所有测试必须通过**
   - 本地检查脚本会验证
   - CI 会验证

4. **代码质量检查必须通过**
   - Ruff lint 无错误
   - Ruff format 检查通过

5. **PR 大小限制**
   - 净增加 < 1000 行（强制）
   - 修改文件 < 20 个（警告）

### 建议规则（违反会警告）

1. **PR 大小建议**
   - 净增加 < 500 行
   - 修改文件 < 10 个

2. **提交信息规范**
   - 遵循 Conventional Commits
   - 清晰描述变更

---

## 📋 使用流程

### 日常开发流程

```bash
# 1. 创建新分支
git checkout main
git pull origin main
git checkout -b feat/your-feature

# 2. 开发和提交
# ... 编写代码 ...
git add .
git commit -m "feat: add your feature"

# 3. 推送前检查（推荐）
./scripts/check.sh

# 4. 推送到远程
git push origin feat/your-feature

# 5. 在 GitHub 创建 PR
# 6. 等待 CI 通过
# 7. 合并后清理
git checkout main
git pull origin main
git branch -d feat/your-feature
```

### 快速检查命令

```bash
# 完整检查（推荐在推送前运行）
./scripts/check.sh

# 单独检查
uv run ruff check .              # Lint
uv run ruff format --check .     # Format
uv run python -m unittest discover -s tests -p "test_*.py" -v  # Tests
```

---

## 🚨 下一步：GitHub 配置

**重要**：你还需要在 GitHub 上配置分支保护规则。

### 配置步骤

1. 访问：https://github.com/iridite/nautilus_practice/settings/branches
2. 点击 "Add rule"
3. Branch name pattern: `main`
4. 启用以下规则：
   - ✅ Require a pull request before merging
   - ✅ Require status checks to pass before merging
     - 添加：Validate Branch Name, Run Tests, Lint Check, PR Size Check
   - ✅ Require conversation resolution before merging
   - ✅ Require linear history
   - ✅ Do not allow bypassing the above settings
5. 保存

详细步骤见：`docs/BRANCH_PROTECTION_SETUP.md`

---

## 🧪 测试建议

在正式使用前，建议测试以下场景：

### 测试 1: 直接推送到 main（应该被阻止）

```bash
git checkout main
echo "test" >> test.txt
git add test.txt
git commit -m "test"
git push origin main
# 预期：被 pre-push hook 阻止
```

### 测试 2: 错误的分支名（应该被警告）

```bash
git checkout -b wrong-name
git push origin wrong-name
# 预期：收到警告
```

### 测试 3: 正常的 PR 流程（应该成功）

```bash
git checkout -b feat/test-protection
echo "test" >> test.txt
git add test.txt
git commit -m "feat: test branch protection"
./scripts/check.sh  # 应该通过
git push origin feat/test-protection
# 在 GitHub 创建 PR，CI 应该通过
```

---

## 📊 预期效果

实施这些规则后，你应该看到：

### 短期效果（1-2 周）

- ✅ 所有代码变更都通过 PR
- ✅ main 分支保持稳定
- ✅ 代码质量更一致
- ✅ 测试覆盖率不会下降

### 中期效果（1-2 月）

- ✅ PR 大小更合理（< 500 行）
- ✅ 提交历史更清晰
- ✅ 更容易回滚问题代码
- ✅ 减少"快速修复"导致的 bug

### 长期效果（3-6 月）

- ✅ 代码库更稳定
- ✅ 新功能开发更有条理
- ✅ 技术债务减少
- ✅ 过度工程化问题得到控制

---

## 🎓 团队培训（如果是团队项目）

如果有其他开发者，需要培训以下内容：

1. **分支管理规则**
   - 阅读 `docs/DEVELOPMENT_RULES.md`
   - 理解为什么需要这些规则

2. **工作流程**
   - 演示完整的 PR 流程
   - 展示如何使用 `./scripts/check.sh`

3. **常见问题**
   - 如何处理 CI 失败
   - 如何拆分大 PR
   - 如何解决合并冲突

---

## 📚 相关文档索引

- `docs/DEVELOPMENT_RULES.md` - 完整的开发规范（必读）
- `docs/QUICK_START_BRANCH_MANAGEMENT.md` - 快速参考
- `docs/BRANCH_PROTECTION_SETUP.md` - GitHub 配置指南
- `.github/PULL_REQUEST_TEMPLATE.md` - PR 模板
- `.github/workflows/pr-checks.yml` - CI 配置
- `scripts/check.sh` - 本地检查脚本
- `.git/hooks/pre-push` - Pre-push hook

---

## ✅ 配置完成检查清单

在开始使用前，请确认：

- [ ] Pre-push hook 已安装并可执行（`ls -la .git/hooks/pre-push`）
- [ ] 检查脚本可执行（`ls -la scripts/check.sh`）
- [ ] 已测试 `./scripts/check.sh` 可以正常运行
- [ ] 已阅读 `docs/DEVELOPMENT_RULES.md`
- [ ] 已在 GitHub 上配置分支保护规则
- [ ] 已测试直接推送到 main 被阻止
- [ ] 已测试正常的 PR 流程
- [ ] 团队成员已了解新规则（如果适用）

---

## 🎯 成功指标

3 个月后，检查以下指标：

- [ ] main 分支上的直接提交数 = 0
- [ ] 所有变更都通过 PR
- [ ] 平均 PR 大小 < 500 行
- [ ] CI 通过率 > 95%
- [ ] 回滚次数减少
- [ ] 代码审查更容易

---

## 💡 最后的建议

1. **严格执行**：不要为"紧急修复"破例
2. **持续改进**：根据实际情况调整规则
3. **保持简单**：不要添加不必要的检查
4. **关注价值**：规则是为了提高代码质量，不是为了限制开发

**记住**：这些规则是为了防止过度工程化，而不是创造新的过度工程化！

---

## 📞 需要帮助？

如果遇到问题：

1. 查看 `docs/DEVELOPMENT_RULES.md` 的常见问题部分
2. 检查 CI 日志了解失败原因
3. 运行 `./scripts/check.sh` 查看详细错误信息

祝开发顺利！🚀
